"""
SOA Extraction Worker - Human-in-the-Loop Pipeline

This module provides process-based isolation for SOA extraction with a checkpoint
after page detection for human verification.

Architecture:
    Stage 1: Page Detection (runs immediately when user opens SOA Analysis)
        - Detect SOA pages using Gemini Vision
        - Save detected pages to database
        - Set status to 'awaiting_page_confirmation'
        - Wait for user confirmation

    Stage 2: Full Extraction (runs after user confirms/corrects pages)
        - Extract tables using LandingAI
        - Run 12-stage interpretation pipeline
        - Validate results
        - Save USDM output
"""

import asyncio
import logging
import multiprocessing
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID


def _setup_worker_logging(job_id: str, stage: str) -> logging.Logger:
    """Configure logging for the SOA worker process."""
    logger = logging.getLogger(f"soa_worker.{stage}.{job_id[:8]}")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(handler)

    return logger


def _update_soa_job(job_id: str, updates: Dict[str, Any], logger: Optional[logging.Logger] = None) -> bool:
    """
    Update SOA job with a fresh database connection.

    Uses a fresh connection for each update to avoid NeonDB SSL timeout issues
    during long-running extraction pipelines.

    Args:
        job_id: The SOA job UUID as a string
        updates: Dictionary of field names to values to update
        logger: Optional logger for error messages

    Returns:
        True if update succeeded, False otherwise
    """
    from app.db import get_session_factory, SOAJob
    from sqlalchemy.orm.attributes import flag_modified

    # JSONB fields that need flag_modified for SQLAlchemy to detect changes
    JSONB_FIELDS = {'detected_pages', 'confirmed_pages', 'phase_progress', 'usdm_data',
                    'quality_report', 'extraction_review', 'interpretation_review', 'merge_analysis',
                    'classification_review'}

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        soa_job = db.query(SOAJob).filter(SOAJob.id == UUID(job_id)).first()
        if soa_job:
            for key, value in updates.items():
                setattr(soa_job, key, value)
                # Flag JSONB fields as modified so SQLAlchemy detects the change
                if key in JSONB_FIELDS:
                    flag_modified(soa_job, key)
            soa_job.updated_at = datetime.utcnow()
            db.commit()
            return True
        else:
            if logger:
                logger.error(f"SOA job not found: {job_id}")
            return False
    except Exception as e:
        if logger:
            logger.error(f"Failed to update SOA job: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def _run_page_detection(
    soa_job_id: str,
    protocol_id: str,
    pdf_path: str,
    database_url: str,
):
    """
    Stage 1: Run page detection only.

    This function runs in a separate OS process and detects SOA pages,
    then pauses for user confirmation.
    """
    logger = _setup_worker_logging(soa_job_id, "detection")
    logger.info(f"SOA page detection started for job {soa_job_id}")

    try:
        os.environ.setdefault('SOA_WORKER', 'true')

        # Import after setting environment
        from app.db import get_session_factory, SOAJob, Protocol
        from soa_analyzer.soa_page_detector import detect_soa_pages_v2, get_merged_table_pages

        # Create database session
        SessionLocal = get_session_factory()
        db = SessionLocal()

        try:
            # Update job status to detecting
            soa_job = db.query(SOAJob).filter(SOAJob.id == UUID(soa_job_id)).first()
            if not soa_job:
                raise ValueError(f"SOA job not found: {soa_job_id}")

            soa_job.status = "detecting_pages"
            soa_job.started_at = datetime.utcnow()
            soa_job.current_phase = "detection"
            db.commit()

            # Run page detection
            logger.info(f"Detecting SOA pages in {pdf_path}")
            result = detect_soa_pages_v2(pdf_path)
            merged_tables = get_merged_table_pages(result)

            # Extract page information for frontend
            detected_pages = []
            for table in merged_tables:
                page_info = {
                    "id": table.get("id", "SOA-1"),
                    "pageStart": table.get("pageStart"),
                    "pageEnd": table.get("pageEnd"),
                    "category": table.get("tableCategory", "MAIN_SOA"),
                    "pages": list(range(table.get("pageStart", 1), table.get("pageEnd", 1) + 1)),
                }
                detected_pages.append(page_info)

            logger.info(f"Detected {len(detected_pages)} SOA table(s)")
            for page_info in detected_pages:
                logger.info(f"  {page_info['id']}: pages {page_info['pageStart']}-{page_info['pageEnd']}")

            # Save detected pages and set status to awaiting confirmation
            soa_job.detected_pages = {
                "totalSOAs": result.get("totalSOAs", 0),
                "tables": detected_pages,
                "raw_result": result,  # Keep raw result for Stage 2
            }
            soa_job.status = "awaiting_page_confirmation"
            soa_job.phase_progress = {"phase": "detection", "progress": 100}
            soa_job.updated_at = datetime.utcnow()
            db.commit()

            logger.info(f"Page detection complete. Awaiting user confirmation for job {soa_job_id}")

        except Exception as e:
            logger.error(f"Page detection failed: {e}", exc_info=True)

            # Mark job as failed
            try:
                soa_job = db.query(SOAJob).filter(SOAJob.id == UUID(soa_job_id)).first()
                if soa_job:
                    soa_job.status = "failed"
                    soa_job.error_message = str(e)[:1000]
                    soa_job.completed_at = datetime.utcnow()
                    soa_job.updated_at = datetime.utcnow()
                    db.commit()
            except Exception as db_error:
                logger.error(f"Failed to update job status: {db_error}")
                db.rollback()
            raise
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Worker process error: {e}", exc_info=True)
        sys.exit(1)

    logger.info(f"SOA page detection worker finished for job {soa_job_id}")
    sys.exit(0)


def _run_full_extraction(
    soa_job_id: str,
    protocol_id: str,
    pdf_path: str,
    confirmed_pages: Dict[str, Any],
    database_url: str,
):
    """
    Stage 2: Run full extraction after page confirmation.

    Uses the confirmed/corrected pages to run extraction and interpretation,
    storing per-table USDM results directly in the database.

    Note: Uses skip_interpretation=True to skip the 12-stage pipeline and
    return raw per-table USDM for immediate UI display.
    """
    import time

    logger = _setup_worker_logging(soa_job_id, "extraction")
    logger.info(f"SOA full extraction started for job {soa_job_id}")

    try:
        os.environ.setdefault('SOA_WORKER', 'true')

        # Import after setting environment
        from app.db import get_session_factory, SOAJob, SOATableResult, Protocol
        from soa_analyzer.soa_extraction_pipeline import run_soa_extraction

        # Update initial job status with fresh connection
        _update_soa_job(soa_job_id, {
            "status": "extracting",
            "current_phase": "extraction",
            "confirmed_pages": confirmed_pages,
            "phase_progress": {"phase": "extraction", "progress": 0},
        }, logger)

        # Get protocol info with fresh connection
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            protocol = db.query(Protocol).filter(Protocol.id == UUID(protocol_id)).first()
            if not protocol:
                raise ValueError(f"Protocol not found: {protocol_id}")
            protocol_name = protocol.filename.replace('.pdf', '')
            gemini_file_uri = protocol.gemini_file_uri
        finally:
            db.close()

        # Build detection result from confirmed pages for the pipeline
        source_tables = confirmed_pages.get("tables", []) or confirmed_pages.get("soaTables", [])
        merged_tables = []
        for table in source_tables:
            merged_tables.append({
                "id": table.get("id", "SOA-1"),
                "pageStart": table.get("pageStart"),
                "pageEnd": table.get("pageEnd"),
                "tableCategory": table.get("tableCategory") or table.get("category", "MAIN_SOA"),
            })

        detected_pages = {
            "totalSOAs": len(merged_tables),
            "mergedTables": merged_tables,
        }

        # Create async event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Run extraction with skip_interpretation=True for per-table raw USDM
            logger.info("Running SOA extraction pipeline (skip_interpretation=True)...")
            _update_soa_job(soa_job_id, {
                "current_phase": "extraction",
                "phase_progress": {"phase": "extraction", "progress": 10},
            }, logger)

            result = loop.run_until_complete(
                run_soa_extraction(
                    pdf_path=pdf_path,
                    protocol_id=protocol_name,
                    protocol_name=protocol_name,
                    skip_interpretation=True,  # Skip 12-stage pipeline, return raw per-table USDM
                    detected_pages=detected_pages,  # Use confirmed pages, skip detection
                    gemini_file_uri=gemini_file_uri,
                    use_cache=True,
                )
            )

            if not result.success:
                raise RuntimeError(f"Extraction failed: {'; '.join(result.errors)}")

            _update_soa_job(soa_job_id, {
                "phase_progress": {"phase": "extraction", "progress": 100},
            }, logger)

            # Save per-table results to database
            logger.info(f"Saving {len(result.per_table_results)} per-table results to database...")
            _update_soa_job(soa_job_id, {
                "status": "saving",
                "current_phase": "saving",
                "phase_progress": {"phase": "saving", "progress": 0},
            }, logger)

            # Save per-table USDM to SOATableResult
            SessionLocal = get_session_factory()
            db = SessionLocal()
            try:
                import uuid as uuid_module
                for i, ptr in enumerate(result.per_table_results):
                    table_result = SOATableResult(
                        id=uuid_module.uuid4(),
                        soa_job_id=UUID(soa_job_id),
                        protocol_id=UUID(protocol_id),
                        protocol_name=protocol_name,
                        table_id=ptr.table_id,
                        table_category=ptr.category,
                        page_start=ptr.usdm.get("_tableMetadata", {}).get("pageStart", 0) if ptr.usdm else 0,
                        page_end=ptr.usdm.get("_tableMetadata", {}).get("pageEnd", 0) if ptr.usdm else 0,
                        status="success" if ptr.success else "failed",
                        error_message=ptr.error,
                        usdm_data=ptr.usdm,
                        visits_count=ptr.counts.get("visits", 0),
                        activities_count=ptr.counts.get("activities", 0),
                        sais_count=ptr.counts.get("sais", 0),
                        footnotes_count=ptr.counts.get("footnotes", 0),
                    )
                    db.add(table_result)
                    logger.info(f"  Saved {ptr.table_id} ({ptr.category}): {ptr.counts}")

                db.commit()
                logger.info(f"Successfully saved {len(result.per_table_results)} table results to database")
            except Exception as db_error:
                logger.error(f"Failed to save table results: {db_error}")
                db.rollback()
                raise
            finally:
                db.close()

            # Build extraction review summary for the UI
            extraction_review_data = {
                "status": "pending_confirmation",
                "extractedAt": datetime.utcnow().isoformat(),
                "totalTables": len(result.per_table_results),
                "successfulTables": sum(1 for ptr in result.per_table_results if ptr.success),
                "tables": [
                    {
                        "tableId": ptr.table_id,
                        "category": ptr.category,
                        "status": "success" if ptr.success else "failed",
                        "error": ptr.error,
                        "counts": ptr.counts,
                    }
                    for ptr in result.per_table_results
                ],
            }

            # Set status to awaiting_extraction_review - STOP here for user review
            _update_soa_job(soa_job_id, {
                "status": "awaiting_extraction_review",
                "current_phase": "extraction_review",
                "phase_progress": {"phase": "extraction", "progress": 100},
                "extraction_review": extraction_review_data,
            }, logger)

            logger.info(f"Extraction complete. Awaiting user review for job {soa_job_id}")

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Full extraction failed: {e}", exc_info=True)

        # Mark job as failed with fresh connection
        _update_soa_job(soa_job_id, {
            "status": "failed",
            "error_message": str(e)[:1000],
            "completed_at": datetime.utcnow(),
        }, logger)

        sys.exit(1)

    logger.info(f"SOA full extraction worker finished for job {soa_job_id}")
    sys.exit(0)


def spawn_page_detection_process(
    soa_job_id: UUID,
    protocol_id: UUID,
    pdf_path: str,
) -> multiprocessing.Process:
    """
    Spawn Stage 1 (page detection) in a separate process.

    Returns immediately after starting the subprocess.
    """
    from app.config import settings

    ctx = multiprocessing.get_context('spawn')

    process = ctx.Process(
        target=_run_page_detection,
        args=(
            str(soa_job_id),
            str(protocol_id),
            pdf_path,
            settings.database_url,
        ),
        daemon=False,
        name=f"soa-detection-{str(soa_job_id)[:8]}",
    )

    process.start()

    logging.getLogger(__name__).info(
        f"Spawned SOA page detection process {process.pid} for job {soa_job_id}"
    )

    return process


def spawn_full_extraction_process(
    soa_job_id: UUID,
    protocol_id: UUID,
    pdf_path: str,
    confirmed_pages: Dict[str, Any],
) -> multiprocessing.Process:
    """
    Spawn Stage 2 (full extraction) in a separate process.

    Called after user confirms/corrects the detected pages.
    """
    from app.config import settings

    ctx = multiprocessing.get_context('spawn')

    process = ctx.Process(
        target=_run_full_extraction,
        args=(
            str(soa_job_id),
            str(protocol_id),
            pdf_path,
            confirmed_pages,
            settings.database_url,
        ),
        daemon=False,
        name=f"soa-extraction-{str(soa_job_id)[:8]}",
    )

    process.start()

    logging.getLogger(__name__).info(
        f"Spawned SOA full extraction process {process.pid} for job {soa_job_id}"
    )

    return process


def _run_interpretation(
    soa_job_id: str,
    protocol_id: str,
    pdf_path: str,
    database_url: str,
    classification_profiles: Optional[Dict[str, Any]] = None,
):
    """
    Phase 3b: Run 12-stage interpretation on each per-table USDM.

    Called after user confirms classification results.
    Reads per-table USDM from SOATableResult rows, runs interpretation,
    and updates each row with the interpreted USDM.
    If classification_profiles is provided, passes the profile for each table
    as pre_computed_profile to the interpretation pipeline.
    """
    import time
    import json

    logger = _setup_worker_logging(soa_job_id, "interpretation")
    logger.info(f"SOA per-table interpretation started for job {soa_job_id}")

    try:
        os.environ.setdefault('SOA_WORKER', 'true')

        from app.db import get_session_factory, SOAJob, SOATableResult, Protocol
        from soa_analyzer.interpretation import InterpretationPipeline, PipelineConfig as InterpretationConfig
        from soa_analyzer.soa_extraction_pipeline import auto_discover_extraction_outputs, propagate_provenance
        from app.services.gemini_file_service import GeminiFileService

        # Update job status
        _update_soa_job(soa_job_id, {
            "status": "interpreting_tables",
            "current_phase": "interpreting_tables",
            "phase_progress": {"phase": "interpreting_tables", "progress": 0},
        }, logger)

        # Get protocol info
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            protocol = db.query(Protocol).filter(Protocol.id == UUID(protocol_id)).first()
            if not protocol:
                raise ValueError(f"Protocol not found: {protocol_id}")
            protocol_name = protocol.filename.replace('.pdf', '')
            gemini_file_uri = protocol.gemini_file_uri

            # Upload PDF to Gemini if not already cached (needed for Stage 2 Activity Expansion)
            if not gemini_file_uri:
                try:
                    gemini_service = GeminiFileService()
                    upload_loop = asyncio.new_event_loop()
                    gemini_file_uri, _ = upload_loop.run_until_complete(
                        gemini_service.get_or_upload_file_from_protocol(UUID(protocol_id), db)
                    )
                    upload_loop.close()
                    logger.info(f"Uploaded PDF to Gemini for Stage 2: {gemini_file_uri[:60]}...")
                except Exception as upload_err:
                    logger.warning(f"Gemini file upload failed (Stage 2 will run without PDF): {upload_err}")

            # Get per-table results from database
            table_results = db.query(SOATableResult).filter(
                SOATableResult.soa_job_id == UUID(soa_job_id),
                SOATableResult.status == "success",
            ).order_by(SOATableResult.table_id).all()

            if not table_results:
                raise ValueError("No successful per-table results found")

            # Build list of (table_id, usdm) pairs
            tables_to_interpret = []
            for tr in table_results:
                if tr.usdm_data:
                    tables_to_interpret.append({
                        "table_id": tr.table_id,
                        "category": tr.table_category,
                        "usdm": tr.usdm_data,
                    })
        finally:
            db.close()

        logger.info(f"Found {len(tables_to_interpret)} tables to interpret")

        # Auto-discover extraction outputs for Stage 9
        effective_extraction_outputs = auto_discover_extraction_outputs(Path(pdf_path))
        if effective_extraction_outputs:
            logger.info(f"  Auto-discovered {len(effective_extraction_outputs)} extraction modules")

        # Create async event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            total_tables = len(tables_to_interpret)
            all_usdm_results = []

            for table_idx, table_info in enumerate(tables_to_interpret):
                tid = table_info["table_id"]
                usdm = table_info["usdm"]
                logger.info(f"  Interpreting table {tid} ({table_idx+1}/{total_tables})...")

                def make_table_progress_callback(t_idx, t_total):
                    stages_done = [0]
                    def cb(stage_num: int, stage_name: str, status: str):
                        stages_done[0] += 1
                        completed = (t_idx * 12) + stages_done[0]
                        total = t_total * 12
                        pct = int((completed / total) * 100) if total > 0 else 0
                        _update_soa_job(soa_job_id, {
                            "phase_progress": {
                                "phase": "interpreting_tables",
                                "progress": pct,
                                "current_table": tid,
                                "current_stage": stage_num,
                                "current_stage_name": stage_name,
                                "tables_completed": t_idx,
                                "tables_total": t_total,
                            },
                        }, logger)
                    return cb

                try:
                    table_pipeline = InterpretationPipeline(
                        progress_callback=make_table_progress_callback(table_idx, total_tables)
                    )

                    # Get classification profile for this table if available
                    table_profile = None
                    if classification_profiles:
                        table_profile = classification_profiles.get(tid)

                    interp_config = InterpretationConfig(
                        protocol_id=f"{protocol_name}_{tid}",
                        protocol_name=protocol_name,
                        extraction_outputs=effective_extraction_outputs,
                        gemini_file_uri=gemini_file_uri,
                        skip_stage_11=True,
                        continue_on_non_critical_failure=True,
                        pre_computed_profile=table_profile,
                    )

                    pipeline_result = loop.run_until_complete(
                        table_pipeline.run(usdm, interp_config)
                    )

                    final_usdm = usdm
                    if pipeline_result.final_usdm:
                        propagate_provenance(pipeline_result.final_usdm)
                        final_usdm = pipeline_result.final_usdm
                        logger.info(f"    {tid}: {pipeline_result.get_summary()}")
                    else:
                        logger.warning(f"    {tid}: No final USDM from interpretation, keeping raw")

                    # Serialize stage results
                    serialized_stage_results = {}
                    stage_results = getattr(pipeline_result, 'stage_results', {}) or {}
                    for stage_num, stage_result in stage_results.items():
                        if stage_result is not None:
                            try:
                                if hasattr(stage_result, 'to_dict'):
                                    serialized_stage_results[stage_num] = stage_result.to_dict()
                                elif hasattr(stage_result, '__dict__'):
                                    serialized_stage_results[stage_num] = {
                                        k: v for k, v in stage_result.__dict__.items()
                                        if not k.startswith('_') and not callable(v)
                                    }
                                elif isinstance(stage_result, dict):
                                    serialized_stage_results[stage_num] = stage_result
                                else:
                                    serialized_stage_results[stage_num] = str(stage_result)
                            except Exception as se:
                                logger.warning(f"    Could not serialize stage {stage_num}: {se}")
                                serialized_stage_results[stage_num] = {"error": str(se)}

                    # Inject stage durations into serialized results
                    stage_durations = getattr(pipeline_result, 'stage_durations', {}) or {}
                    for stage_num, duration in stage_durations.items():
                        if stage_num in serialized_stage_results:
                            if isinstance(serialized_stage_results[stage_num], dict):
                                serialized_stage_results[stage_num]["duration"] = round(duration, 2)

                    # Update SOATableResult in DB with interpreted USDM
                    SessionLocal = get_session_factory()
                    db = SessionLocal()
                    try:
                        from sqlalchemy.orm.attributes import flag_modified
                        table_row = db.query(SOATableResult).filter(
                            SOATableResult.soa_job_id == UUID(soa_job_id),
                            SOATableResult.table_id == tid,
                        ).first()
                        if table_row:
                            # Snapshot raw extraction USDM before interpretation overwrites it
                            table_row.raw_usdm_data = table_row.usdm_data
                            flag_modified(table_row, "raw_usdm_data")
                            table_row.usdm_data = final_usdm
                            flag_modified(table_row, "usdm_data")
                            table_row.interpretation_stages = serialized_stage_results
                            flag_modified(table_row, "interpretation_stages")
                            table_row.visits_count = len(final_usdm.get("visits", final_usdm.get("encounters", [])))
                            table_row.activities_count = len(final_usdm.get("activities", []))
                            table_row.sais_count = len(final_usdm.get("scheduledActivityInstances", []))
                            table_row.footnotes_count = len(final_usdm.get("footnotes", []))
                            db.commit()
                            logger.info(f"    Updated {tid} in DB with interpreted USDM")
                    except Exception as db_err:
                        logger.error(f"    Failed to update {tid} in DB: {db_err}")
                        db.rollback()
                    finally:
                        db.close()

                    all_usdm_results.append(final_usdm)

                except Exception as e:
                    logger.error(f"    {tid} interpretation failed: {e}", exc_info=True)
                    all_usdm_results.append(usdm)  # Keep raw

            logger.info(f"[Phase 3b] Per-table interpretation complete")

            # Save per-table USDM to local JSON files
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            pdf_dir = Path(pdf_path).parent
            output_dir = pdf_dir / "soa_output" / timestamp / "per_table_usdm"
            output_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Saving per-table USDM to local files: {output_dir}")

            saved_files = []
            for table_info, final_usdm in zip(tables_to_interpret, all_usdm_results):
                table_file = output_dir / f"{protocol_name}_{table_info['table_id']}_{table_info['category']}.json"
                with open(table_file, 'w') as f:
                    json.dump(final_usdm, f, indent=2, default=str)
                saved_files.append(str(table_file))
                logger.info(f"  Saved: {table_file.name}")

            logger.info(f"Successfully saved {len(saved_files)} per-table JSON files")

            # Mark interpretation as done — user reviews results before merge analysis
            _update_soa_job(soa_job_id, {
                "status": "awaiting_merge_review",
                "phase_progress": {"phase": "interpretation_complete", "progress": 100},
            }, logger)

            logger.info(f"SOA interpretation completed for job {soa_job_id}. Awaiting user review before merge analysis.")

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Interpretation failed: {e}", exc_info=True)

        _update_soa_job(soa_job_id, {
            "status": "failed",
            "error_message": f"Interpretation failed: {str(e)[:500]}",
            "completed_at": datetime.utcnow(),
        }, logger)

        sys.exit(1)

    logger.info(f"SOA interpretation worker finished for job {soa_job_id}")
    sys.exit(0)


def spawn_interpretation_process(
    soa_job_id: UUID,
    protocol_id: UUID,
    pdf_path: str,
    classification_profiles: Optional[Dict[str, Any]] = None,
) -> multiprocessing.Process:
    """
    Spawn Phase 3b (per-table interpretation) in a separate process.

    Called after user confirms classification results.
    """
    from app.config import settings

    ctx = multiprocessing.get_context('spawn')

    process = ctx.Process(
        target=_run_interpretation,
        args=(
            str(soa_job_id),
            str(protocol_id),
            pdf_path,
            settings.database_url,
            classification_profiles,
        ),
        daemon=False,
        name=f"soa-interpretation-{str(soa_job_id)[:8]}",
    )

    process.start()

    logging.getLogger(__name__).info(
        f"Spawned SOA interpretation process {process.pid} for job {soa_job_id}"
    )

    return process


def _run_merge_analysis(
    soa_job_id: str,
    protocol_id: str,
    pdf_path: str,
    database_url: str,
):
    """
    Phase 3.5: Run merge analysis on per-table USDM results.

    This function analyzes per-table results and creates a merge plan
    suggesting which tables should be processed together.
    """
    import time
    import uuid as uuid_module

    logger = _setup_worker_logging(soa_job_id, "merge_analysis")
    logger.info(f"SOA merge analysis started for job {soa_job_id}")

    try:
        os.environ.setdefault('SOA_WORKER', 'true')

        # Import after setting environment
        from app.db import get_session_factory, SOAJob, SOATableResult, Protocol
        from soa_analyzer.table_merge_analyzer import TableMergeAnalyzer

        # Update initial job status
        _update_soa_job(soa_job_id, {
            "status": "analyzing_merges",
            "current_phase": "merge_analysis",
            "phase_progress": {"phase": "merge_analysis", "progress": 10},
        }, logger)

        # Get per-table results from database
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            # Get protocol info
            protocol = db.query(Protocol).filter(Protocol.id == UUID(protocol_id)).first()
            if not protocol:
                raise ValueError(f"Protocol not found: {protocol_id}")
            protocol_name = protocol.filename.replace('.pdf', '')

            # Get all per-table results
            table_results = db.query(SOATableResult).filter(
                SOATableResult.soa_job_id == UUID(soa_job_id)
            ).order_by(SOATableResult.page_start).all()

            if not table_results:
                raise ValueError("No per-table results found")

            logger.info(f"Found {len(table_results)} per-table results for merge analysis")

            # Convert to format expected by TableMergeAnalyzer
            class PerTableResultAdapter:
                def __init__(self, tr):
                    self.table_id = tr.table_id
                    self.category = tr.table_category
                    self.success = tr.status == "success"
                    self.usdm = tr.usdm_data or {}
                    self.error = tr.error_message
                    self.counts = {
                        "visits": tr.visits_count or 0,
                        "activities": tr.activities_count or 0,
                        "sais": tr.sais_count or 0,
                        "footnotes": tr.footnotes_count or 0,
                    }
                    # Add page range to USDM metadata if not present
                    if "_tableMetadata" not in self.usdm:
                        self.usdm["_tableMetadata"] = {}
                    self.usdm["_tableMetadata"]["pageStart"] = tr.page_start
                    self.usdm["_tableMetadata"]["pageEnd"] = tr.page_end
                    self.usdm["_tableMetadata"]["tableId"] = tr.table_id
                    self.usdm["_tableMetadata"]["tableCategory"] = tr.table_category

            per_table_results = [PerTableResultAdapter(tr) for tr in table_results]

            _update_soa_job(soa_job_id, {
                "phase_progress": {"phase": "merge_analysis", "progress": 30},
            }, logger)

            # Run merge analysis
            logger.info("Running TableMergeAnalyzer...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                analyzer = TableMergeAnalyzer()
                merge_plan = loop.run_until_complete(
                    analyzer.analyze_merge_candidates(per_table_results, protocol_name)
                )

                _update_soa_job(soa_job_id, {
                    "phase_progress": {"phase": "merge_analysis", "progress": 80},
                }, logger)

                logger.info(f"Merge analysis complete: {len(merge_plan.merge_groups)} groups suggested")

                # Build merge plan data for database
                merge_plan_data = {
                    "protocolId": protocol_name,
                    "analysisTimestamp": datetime.utcnow().isoformat(),
                    "status": "pending_confirmation",
                    "totalTablesInput": merge_plan.total_tables,
                    "suggestedMergeGroups": len(merge_plan.merge_groups),
                    "mergeGroups": [],
                    "analysisDetails": merge_plan.analysis_summary,
                }

                # Build page ranges and categories for UI
                page_ranges = {}
                table_categories = {}
                for tr in table_results:
                    page_ranges[tr.table_id] = {"start": tr.page_start, "end": tr.page_end}
                    table_categories[tr.table_id] = tr.table_category

                for mg in merge_plan.merge_groups:
                    # Use the actual decisive level (not last analyzed)
                    decision_level = mg.decision_level
                    # merge_type is an enum, get its value
                    merge_type_str = mg.merge_type.value if hasattr(mg.merge_type, 'value') else str(mg.merge_type)

                    merge_plan_data["mergeGroups"].append({
                        "id": mg.id,
                        "tableIds": mg.table_ids,
                        "mergeType": merge_type_str,
                        "decisionLevel": decision_level,
                        "confidence": mg.confidence,
                        "reasoning": mg.reasoning,
                        "confirmed": None,
                        "userOverride": None,
                        "pageRanges": {tid: page_ranges.get(tid, {}) for tid in mg.table_ids},
                        "tableCategories": {tid: table_categories.get(tid, "") for tid in mg.table_ids},
                        "decisionPath": [lr.to_dict() for lr in mg.decision_path],
                    })

                # Also add standalone tables info
                for table_id in merge_plan.standalone_tables:
                    # Find existing group or this is already in a group
                    pass  # standalone_tables are already represented in merge_groups as single-table groups

                # Save to soa_job.merge_analysis
                _update_soa_job(soa_job_id, {
                    "status": "awaiting_merge_confirmation",
                    "current_phase": "merge_confirmation",
                    "phase_progress": {"phase": "merge_analysis", "progress": 100},
                    "merge_analysis": merge_plan_data,
                }, logger)

                logger.info(f"Saved merge analysis to soa_job {soa_job_id}")
                logger.info(f"Merge analysis complete. Awaiting user confirmation for job {soa_job_id}")

            finally:
                loop.close()

        except Exception as e:
            logger.error(f"Merge analysis failed: {e}", exc_info=True)
            db.rollback()
            raise
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Merge analysis worker error: {e}", exc_info=True)

        # Mark job as failed
        _update_soa_job(soa_job_id, {
            "status": "failed",
            "error_message": f"Merge analysis failed: {str(e)[:500]}",
            "completed_at": datetime.utcnow(),
        }, logger)

        sys.exit(1)

    logger.info(f"SOA merge analysis worker finished for job {soa_job_id}")
    sys.exit(0)


def spawn_merge_analysis_process(
    soa_job_id: UUID,
    protocol_id: UUID,
    pdf_path: str,
) -> multiprocessing.Process:
    """
    Spawn Phase 3.5 (merge analysis) in a separate process.

    Called after per-table extraction is complete to analyze which tables
    should be merged together.
    """
    from app.config import settings

    ctx = multiprocessing.get_context('spawn')

    process = ctx.Process(
        target=_run_merge_analysis,
        args=(
            str(soa_job_id),
            str(protocol_id),
            pdf_path,
            settings.database_url,
        ),
        daemon=False,
        name=f"soa-merge-analysis-{str(soa_job_id)[:8]}",
    )

    process.start()

    logging.getLogger(__name__).info(
        f"Spawned SOA merge analysis process {process.pid} for job {soa_job_id}"
    )

    return process


def _run_classification(
    soa_job_id: str,
    protocol_id: str,
    pdf_path: str,
    database_url: str,
):
    """
    Phase 3.6: Run table classification on confirmed merge groups.

    After merge plan is confirmed, this classifies each merge group's combined USDM
    using the SOATableClassifier. Results are stored in soa_job.classification_review
    for human review before interpretation begins.
    """
    logger = _setup_worker_logging(soa_job_id, "classification")
    logger.info(f"SOA classification started for job {soa_job_id}")

    try:
        os.environ.setdefault('SOA_WORKER', 'true')

        from app.db import get_session_factory, SOAJob, SOATableResult, Protocol
        from soa_analyzer.table_merge_analyzer import combine_table_usdm_naive as combine_table_usdm
        from soa_analyzer.interpretation.soa_table_classifier import SOATableClassifier

        # Update initial job status
        _update_soa_job(soa_job_id, {
            "status": "classifying",
            "current_phase": "classification",
            "phase_progress": {"phase": "classification", "progress": 0},
        }, logger)

        # Get protocol info and merge plan
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            protocol = db.query(Protocol).filter(Protocol.id == UUID(protocol_id)).first()
            if not protocol:
                raise ValueError(f"Protocol not found: {protocol_id}")
            protocol_name = protocol.filename.replace('.pdf', '')

            soa_job = db.query(SOAJob).filter(SOAJob.id == UUID(soa_job_id)).first()
            if not soa_job or not soa_job.merge_analysis:
                raise ValueError(f"Merge analysis not found for job: {soa_job_id}")
            merge_plan_data = soa_job.merge_analysis

            # Get per-table results
            table_results = db.query(SOATableResult).filter(
                SOATableResult.soa_job_id == UUID(soa_job_id)
            ).all()

            class TableResultAdapter:
                def __init__(self, tr):
                    self.table_id = tr.table_id
                    self.category = tr.table_category
                    self.success = tr.status == "success"
                    self.usdm = tr.usdm_data
                    self.error = tr.error_message
                    self.counts = {
                        "visits": tr.visits_count or 0,
                        "activities": tr.activities_count or 0,
                        "sais": tr.sais_count or 0,
                        "footnotes": tr.footnotes_count or 0,
                    }

            per_table_results = [TableResultAdapter(tr) for tr in table_results]
        finally:
            db.close()

        # Get confirmed groups from merge plan
        confirmed_groups = merge_plan_data.get("confirmedGroups", [])
        groups_to_classify = []
        for cg in confirmed_groups:
            group_id = cg.get("id")
            is_confirmed = cg.get("confirmed", True)
            user_override = cg.get("userOverride")

            original_group = None
            for mg in merge_plan_data.get("mergeGroups", []):
                if mg.get("id") == group_id:
                    original_group = mg
                    break

            if user_override and user_override.get("action") == "split":
                new_groups = user_override.get("new_groups", [])
                for i, ng in enumerate(new_groups):
                    groups_to_classify.append({
                        "id": f"{group_id}-{i+1}",
                        "table_ids": ng.get("table_ids", []),
                    })
            elif is_confirmed and original_group:
                groups_to_classify.append({
                    "id": group_id,
                    "table_ids": original_group.get("tableIds", []),
                })
            elif is_confirmed:
                groups_to_classify.append({
                    "id": group_id,
                    "table_ids": [group_id.replace("MG-", "SOA-")],
                })

        logger.info(f"Classifying {len(groups_to_classify)} merge groups")

        # Create async event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            classifier = SOATableClassifier()
            classification_results = {}
            total_groups = len(groups_to_classify)

            for i, group in enumerate(groups_to_classify):
                group_id = group["id"]
                table_ids = group["table_ids"]

                progress_pct = int(((i + 1) / total_groups) * 90)
                _update_soa_job(soa_job_id, {
                    "phase_progress": {"phase": "classification", "progress": progress_pct, "current_group": group_id},
                }, logger)

                logger.info(f"Classifying group {group_id} ({i+1}/{total_groups}): tables {table_ids}")

                try:
                    combined_usdm = combine_table_usdm(per_table_results, table_ids)
                    if not combined_usdm:
                        raise ValueError(f"No USDM data for tables: {table_ids}")

                    profile = loop.run_until_complete(classifier.classify(combined_usdm))
                    classification_results[group_id] = profile
                    logger.info(f"  Group {group_id}: {profile.get('tableStructureType', 'unknown')} (confidence: {profile.get('confidence', 0):.2f})")

                except Exception as e:
                    logger.error(f"  Group {group_id} classification failed: {e}")
                    classification_results[group_id] = {
                        "tableStructureType": "classification_failed",
                        "confidence": 0.0,
                        "characteristics": [f"Classification error: {str(e)[:200]}"],
                        "stageGuidance": {},
                        "structuralFeatures": {},
                    }

            # Save classification results
            classification_review = {
                "status": "pending_confirmation",
                "classifiedAt": datetime.utcnow().isoformat(),
                "groups": classification_results,
            }

            _update_soa_job(soa_job_id, {
                "status": "awaiting_classification_review",
                "current_phase": "classification_review",
                "phase_progress": {"phase": "classification", "progress": 100},
                "classification_review": classification_review,
            }, logger)

            logger.info(f"Classification complete. Awaiting user review for job {soa_job_id}")

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Classification failed: {e}", exc_info=True)
        _update_soa_job(soa_job_id, {
            "status": "failed",
            "error_message": f"Classification failed: {str(e)[:500]}",
            "completed_at": datetime.utcnow(),
        }, logger)
        sys.exit(1)

    logger.info(f"SOA classification worker finished for job {soa_job_id}")
    sys.exit(0)


def _run_per_table_classification(
    soa_job_id: str,
    protocol_id: str,
    pdf_path: str,
    database_url: str,
):
    """
    Per-table classification: classify each extracted table individually.

    Called after user confirms extraction results, before interpretation.
    Each table gets a classification profile that provides context
    (table structure type, stage guidance) for the 12-stage interpretation pipeline.
    """
    logger = _setup_worker_logging(soa_job_id, "per_table_classification")
    logger.info(f"Per-table classification started for job {soa_job_id}")

    try:
        os.environ.setdefault('SOA_WORKER', 'true')

        from app.db import get_session_factory, SOAJob, SOATableResult, Protocol
        from soa_analyzer.interpretation.soa_table_classifier import SOATableClassifier

        _update_soa_job(soa_job_id, {
            "status": "classifying",
            "current_phase": "classification",
            "phase_progress": {"phase": "classification", "progress": 0},
        }, logger)

        # Get per-table results
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            table_results = db.query(SOATableResult).filter(
                SOATableResult.soa_job_id == UUID(soa_job_id),
                SOATableResult.status == "success",
            ).order_by(SOATableResult.table_id).all()

            if not table_results:
                raise ValueError("No successful per-table results found")

            tables_to_classify = []
            for tr in table_results:
                if tr.usdm_data:
                    tables_to_classify.append({
                        "table_id": tr.table_id,
                        "category": tr.table_category,
                        "usdm": tr.usdm_data,
                    })
        finally:
            db.close()

        logger.info(f"Classifying {len(tables_to_classify)} individual tables")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            classifier = SOATableClassifier()
            classification_results = {}
            total_tables = len(tables_to_classify)

            for i, table_info in enumerate(tables_to_classify):
                tid = table_info["table_id"]
                usdm = table_info["usdm"]

                progress_pct = int(((i + 1) / total_tables) * 90)
                _update_soa_job(soa_job_id, {
                    "phase_progress": {"phase": "classification", "progress": progress_pct, "current_group": tid},
                }, logger)

                logger.info(f"Classifying table {tid} ({i+1}/{total_tables})")

                try:
                    profile = loop.run_until_complete(classifier.classify(usdm))
                    classification_results[tid] = profile
                    logger.info(f"  {tid}: {profile.get('tableStructureType', 'unknown')} (confidence: {profile.get('confidence', 0):.2f})")
                except Exception as e:
                    logger.error(f"  {tid} classification failed: {e}")
                    classification_results[tid] = {
                        "tableStructureType": table_info["category"],
                        "confidence": 0.5,
                        "characteristics": [f"Fallback to extraction category: {table_info['category']}"],
                        "stageGuidance": {},
                        "structuralFeatures": {},
                    }

            classification_review = {
                "status": "pending_confirmation",
                "classifiedAt": datetime.utcnow().isoformat(),
                "groups": classification_results,
            }

            _update_soa_job(soa_job_id, {
                "status": "awaiting_classification_review",
                "current_phase": "classification_review",
                "phase_progress": {"phase": "classification", "progress": 100},
                "classification_review": classification_review,
            }, logger)

            logger.info(f"Per-table classification complete. Awaiting user review for job {soa_job_id}")

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Per-table classification failed: {e}", exc_info=True)
        _update_soa_job(soa_job_id, {
            "status": "failed",
            "error_message": f"Classification failed: {str(e)[:500]}",
            "completed_at": datetime.utcnow(),
        }, logger)
        sys.exit(1)

    logger.info(f"Per-table classification worker finished for job {soa_job_id}")
    sys.exit(0)


def spawn_per_table_classification_process(
    soa_job_id: UUID,
    protocol_id: UUID,
    pdf_path: str,
) -> multiprocessing.Process:
    """Spawn per-table classification in a separate process."""
    from app.config import settings

    ctx = multiprocessing.get_context('spawn')

    process = ctx.Process(
        target=_run_per_table_classification,
        args=(
            str(soa_job_id),
            str(protocol_id),
            pdf_path,
            settings.database_url,
        ),
        daemon=False,
        name=f"soa-per-table-classify-{str(soa_job_id)[:8]}",
    )

    process.start()

    logging.getLogger(__name__).info(
        f"Spawned per-table classification process {process.pid} for job {soa_job_id}"
    )

    return process


def spawn_classification_process(
    soa_job_id: UUID,
    protocol_id: UUID,
    pdf_path: str,
) -> multiprocessing.Process:
    """
    Spawn Phase 3.6 (classification) in a separate process.

    Called after merge plan is confirmed, before interpretation.
    """
    from app.config import settings

    ctx = multiprocessing.get_context('spawn')

    process = ctx.Process(
        target=_run_classification,
        args=(
            str(soa_job_id),
            str(protocol_id),
            pdf_path,
            settings.database_url,
        ),
        daemon=False,
        name=f"soa-classification-{str(soa_job_id)[:8]}",
    )

    process.start()

    logging.getLogger(__name__).info(
        f"Spawned SOA classification process {process.pid} for job {soa_job_id}"
    )

    return process


def _run_merge_interpretation(
    soa_job_id: str,
    protocol_id: str,
    pdf_path: str,
    confirmed_plan: Dict[str, Any],
    database_url: str,
    confirmed_profiles: Optional[Dict[str, Any]] = None,
):
    """
    Timeline assembly for confirmed merge groups.

    Tables are already fully interpreted (12-stage) during Phase 3b.
    This function assembles already-interpreted per-table USDMs into
    scheduleTimelines per group — no LLM calls, no deduplication.
    Group results are stored in soa_job.merge_analysis JSONB.
    """
    from sqlalchemy.orm.attributes import flag_modified

    logger = _setup_worker_logging(soa_job_id, "assembly")
    logger.info(f"SOA timeline assembly started for job {soa_job_id}")

    try:
        os.environ.setdefault('SOA_WORKER', 'true')

        from app.db import get_session_factory, SOAJob, SOATableResult, Protocol

        # Update initial job status
        _update_soa_job(soa_job_id, {
            "status": "assembling",
            "current_phase": "assembly",
            "phase_progress": {"phase": "assembly", "progress": 0},
        }, logger)

        # Get protocol info and per-table results from database
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            protocol = db.query(Protocol).filter(Protocol.id == UUID(protocol_id)).first()
            if not protocol:
                raise ValueError(f"Protocol not found: {protocol_id}")
            protocol_name = protocol.filename.replace('.pdf', '')

            # Use confirmed_plan passed in as the original plan
            original_plan = confirmed_plan

            # Get all per-table results (already interpreted in Phase 3b)
            table_results = db.query(SOATableResult).filter(
                SOATableResult.soa_job_id == UUID(soa_job_id)
            ).all()

            # Build lookup by table_id
            table_usdm_map = {}
            table_stages_map = {}
            table_counts_map = {}
            for tr in table_results:
                table_usdm_map[tr.table_id] = tr.usdm_data
                table_stages_map[tr.table_id] = tr.interpretation_stages
                table_counts_map[tr.table_id] = {
                    "visits": tr.visits_count or 0,
                    "activities": tr.activities_count or 0,
                    "sais": tr.sais_count or 0,
                    "footnotes": tr.footnotes_count or 0,
                }

        finally:
            db.close()

        # Get confirmed groups from the plan
        confirmed_groups = confirmed_plan.get("confirmedGroups", [])

        # Build final groups to process
        groups_to_process = []
        for cg in confirmed_groups:
            group_id = cg.get("id")
            is_confirmed = cg.get("confirmed", True)
            user_override = cg.get("userOverride")

            # Find original group info
            original_group = None
            for mg in original_plan.get("mergeGroups", []):
                if mg.get("id") == group_id:
                    original_group = mg
                    break

            if user_override and user_override.get("action") == "split":
                # User split the group - process new groups separately
                new_groups = user_override.get("new_groups", [])
                for i, ng in enumerate(new_groups):
                    groups_to_process.append({
                        "id": f"{group_id}-{i+1}",
                        "table_ids": ng.get("table_ids", []),
                        "merge_type": "user_split",
                        "original_group": group_id,
                    })
            elif is_confirmed and original_group:
                groups_to_process.append({
                    "id": group_id,
                    "table_ids": original_group.get("tableIds", []),
                    "merge_type": original_group.get("mergeType", "unknown"),
                })
            elif is_confirmed:
                groups_to_process.append({
                    "id": group_id,
                    "table_ids": [group_id.replace("MG-", "SOA-")],
                    "merge_type": "standalone",
                })

        logger.info(f"Assembling {len(groups_to_process)} timeline groups")

        # Assemble timelines from already-interpreted per-table USDMs
        group_results = []
        total_groups = len(groups_to_process)

        for i, group in enumerate(groups_to_process):
            group_id = group["id"]
            table_ids = group["table_ids"]
            merge_type = group["merge_type"]

            progress_pct = int(((i + 1) / total_groups) * 100) if total_groups > 0 else 100
            _update_soa_job(soa_job_id, {
                "phase_progress": {
                    "phase": "assembly",
                    "progress": progress_pct,
                    "current_group": group_id,
                    "groups_completed": i,
                    "groups_total": total_groups,
                },
            }, logger)

            logger.info(f"  Assembling group {group_id} ({i+1}/{total_groups}): tables {table_ids}")

            # Build scheduleTimelines — each table is its own timeline (no dedup)
            schedule_timelines = []
            for tid in table_ids:
                usdm = table_usdm_map.get(tid)
                if usdm:
                    schedule_timelines.append({
                        "timelineId": f"ST-{group_id}-{tid}",
                        "sourceTableId": tid,
                        "usdm": usdm,
                        "counts": table_counts_map.get(tid, {}),
                        "interpretationStages": table_stages_map.get(tid),
                    })

            now = datetime.utcnow()
            counts = {
                "timelines": len(schedule_timelines),
                "visits": sum(t.get("counts", {}).get("visits", 0) for t in schedule_timelines),
                "activities": sum(t.get("counts", {}).get("activities", 0) for t in schedule_timelines),
                "sais": sum(t.get("counts", {}).get("sais", 0) for t in schedule_timelines),
                "footnotes": sum(t.get("counts", {}).get("footnotes", 0) for t in schedule_timelines),
            }

            # Build finalUsdm (first table's USDM or merged)
            final_usdm = None
            if schedule_timelines:
                if len(schedule_timelines) == 1:
                    final_usdm = schedule_timelines[0]["usdm"]
                else:
                    # Simple merge for backward-compat (no name dedup — keep all)
                    merged = {
                        "protocolId": protocol_name,
                        "visits": [],
                        "encounters": [],
                        "activities": [],
                        "scheduledActivityInstances": [],
                        "footnotes": [],
                        "_sourceTimelines": [t["timelineId"] for t in schedule_timelines],
                    }
                    for tl in schedule_timelines:
                        u = tl["usdm"]
                        merged["visits"].extend(u.get("visits", u.get("encounters", [])))
                        merged["activities"].extend(u.get("activities", []))
                        merged["scheduledActivityInstances"].extend(u.get("scheduledActivityInstances", []))
                        merged["footnotes"].extend(u.get("footnotes", []))
                    merged["encounters"] = merged["visits"]
                    final_usdm = merged

            group_result_entry = {
                "id": group_id,
                "mergeGroupId": group_id,
                "sourceTableIds": table_ids,
                "mergeType": merge_type,
                "status": "completed",
                "scheduleTimelines": schedule_timelines,
                "counts": counts,
                "finalUsdm": final_usdm,
                "createdAt": now.isoformat(),
                "completedAt": now.isoformat(),
            }

            group_results.append(group_result_entry)

            # Update merge_analysis.groupResults JSONB
            SessionLocal = get_session_factory()
            db = SessionLocal()
            try:
                soa_job = db.query(SOAJob).filter(SOAJob.id == UUID(soa_job_id)).first()
                if soa_job and soa_job.merge_analysis:
                    merge_analysis = dict(soa_job.merge_analysis)
                    merge_analysis["groupResults"] = group_results
                    soa_job.merge_analysis = merge_analysis
                    flag_modified(soa_job, "merge_analysis")

                db.commit()
            finally:
                db.close()

        # Final update - mark job as completed
        _update_soa_job(soa_job_id, {
            "status": "completed",
            "phase_progress": {"phase": "completed", "progress": 100},
            "completed_at": datetime.utcnow(),
        }, logger)

        logger.info(f"SOA timeline assembly completed for job {soa_job_id}")

    except Exception as e:
        logger.error(f"Timeline assembly failed: {e}", exc_info=True)

        # Mark job as failed
        _update_soa_job(soa_job_id, {
            "status": "failed",
            "error_message": str(e)[:1000],
            "completed_at": datetime.utcnow(),
        }, logger)

        sys.exit(1)

    logger.info(f"SOA timeline assembly worker finished for job {soa_job_id}")
    sys.exit(0)


def spawn_merge_interpretation_process(
    soa_job_id: UUID,
    protocol_id: UUID,
    pdf_path: str,
    confirmed_plan: Dict[str, Any],
    confirmed_profiles: Optional[Dict[str, Any]] = None,
) -> multiprocessing.Process:
    """
    Spawn Stage 3 (merge interpretation) in a separate process.

    Called after user confirms the merge plan (and optionally classification profiles).
    """
    from app.config import settings

    ctx = multiprocessing.get_context('spawn')

    process = ctx.Process(
        target=_run_merge_interpretation,
        args=(
            str(soa_job_id),
            str(protocol_id),
            pdf_path,
            confirmed_plan,
            settings.database_url,
            confirmed_profiles,
        ),
        daemon=False,
        name=f"soa-interpretation-{str(soa_job_id)[:8]}",
    )

    process.start()

    logging.getLogger(__name__).info(
        f"Spawned SOA merge interpretation process {process.pid} for job {soa_job_id}"
    )

    return process


def _run_fully_automated(
    soa_job_id: str,
    protocol_id: str,
    pdf_path: str,
    database_url: str,
):
    """
    Fully automated SOA extraction — no human checkpoints.

    Runs the entire pipeline end-to-end:
    1. Page detection
    2. Extraction (auto-confirms detected pages)
    3. Per-table classification (auto-confirms extraction)
    4. Per-table interpretation (auto-confirms classification)
    5. Merge analysis
    6. Timeline assembly (auto-confirms merge plan)

    Used by "Extract All" mode to run SOA without user intervention.
    """
    import time
    import json

    logger = _setup_worker_logging(soa_job_id, "auto")
    logger.info(f"SOA fully automated extraction started for job {soa_job_id}")

    try:
        os.environ.setdefault('SOA_WORKER', 'true')

        from app.db import get_session_factory, SOAJob, SOATableResult, Protocol
        from soa_analyzer.soa_page_detector import detect_soa_pages_v2, get_merged_table_pages
        from soa_analyzer.soa_extraction_pipeline import run_soa_extraction, auto_discover_extraction_outputs, propagate_provenance
        from soa_analyzer.interpretation import InterpretationPipeline, PipelineConfig as InterpretationConfig
        from soa_analyzer.interpretation.soa_table_classifier import SOATableClassifier
        from app.services.gemini_file_service import GeminiFileService

        # --- Phase 1: Page Detection ---
        logger.info("[Phase 1] Detecting SOA pages...")
        _update_soa_job(soa_job_id, {
            "status": "detecting_pages",
            "started_at": datetime.utcnow(),
            "current_phase": "detection",
            "phase_progress": {"phase": "detection", "progress": 0},
        }, logger)

        result = detect_soa_pages_v2(pdf_path)
        merged_tables = get_merged_table_pages(result)

        detected_pages = []
        for table in merged_tables:
            detected_pages.append({
                "id": table.get("id", "SOA-1"),
                "pageStart": table.get("pageStart"),
                "pageEnd": table.get("pageEnd"),
                "category": table.get("tableCategory", "MAIN_SOA"),
                "pages": list(range(table.get("pageStart", 1), table.get("pageEnd", 1) + 1)),
            })

        logger.info(f"[Phase 1] Detected {len(detected_pages)} SOA table(s)")

        _update_soa_job(soa_job_id, {
            "detected_pages": {"totalSOAs": result.get("totalSOAs", 0), "tables": detected_pages, "raw_result": result},
            "phase_progress": {"phase": "detection", "progress": 100},
        }, logger)

        if not detected_pages:
            logger.warning("No SOA pages detected, marking as completed with no data")
            _update_soa_job(soa_job_id, {
                "status": "completed",
                "completed_at": datetime.utcnow(),
                "phase_progress": {"phase": "completed", "progress": 100},
            }, logger)
            sys.exit(0)

        # --- Phase 2: Extraction (auto-confirm pages) ---
        logger.info("[Phase 2] Running extraction (auto-confirmed pages)...")
        confirmed_pages = {"tables": detected_pages}

        _update_soa_job(soa_job_id, {
            "status": "extracting",
            "current_phase": "extraction",
            "confirmed_pages": confirmed_pages,
            "phase_progress": {"phase": "extraction", "progress": 0},
        }, logger)

        # Get protocol info
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            protocol = db.query(Protocol).filter(Protocol.id == UUID(protocol_id)).first()
            if not protocol:
                raise ValueError(f"Protocol not found: {protocol_id}")
            protocol_name = protocol.filename.replace('.pdf', '')
            gemini_file_uri = protocol.gemini_file_uri
        finally:
            db.close()

        # Build detection result
        extraction_merged_tables = []
        for table in detected_pages:
            extraction_merged_tables.append({
                "id": table["id"],
                "pageStart": table["pageStart"],
                "pageEnd": table["pageEnd"],
                "tableCategory": table.get("category", "MAIN_SOA"),
            })

        extraction_detected_pages = {
            "totalSOAs": len(extraction_merged_tables),
            "mergedTables": extraction_merged_tables,
        }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            extraction_result = loop.run_until_complete(
                run_soa_extraction(
                    pdf_path=pdf_path,
                    protocol_id=protocol_name,
                    protocol_name=protocol_name,
                    skip_interpretation=True,
                    detected_pages=extraction_detected_pages,
                    gemini_file_uri=gemini_file_uri,
                    use_cache=True,
                )
            )

            if not extraction_result.success:
                raise RuntimeError(f"Extraction failed: {'; '.join(extraction_result.errors)}")

            _update_soa_job(soa_job_id, {
                "phase_progress": {"phase": "extraction", "progress": 100},
            }, logger)

            # Save per-table results to database
            logger.info(f"[Phase 2] Saving {len(extraction_result.per_table_results)} per-table results...")
            SessionLocal = get_session_factory()
            db = SessionLocal()
            try:
                import uuid as uuid_module
                for ptr in extraction_result.per_table_results:
                    table_result = SOATableResult(
                        id=uuid_module.uuid4(),
                        soa_job_id=UUID(soa_job_id),
                        protocol_id=UUID(protocol_id),
                        protocol_name=protocol_name,
                        table_id=ptr.table_id,
                        table_category=ptr.category,
                        page_start=ptr.usdm.get("_tableMetadata", {}).get("pageStart", 0) if ptr.usdm else 0,
                        page_end=ptr.usdm.get("_tableMetadata", {}).get("pageEnd", 0) if ptr.usdm else 0,
                        status="success" if ptr.success else "failed",
                        error_message=ptr.error,
                        usdm_data=ptr.usdm,
                        visits_count=ptr.counts.get("visits", 0),
                        activities_count=ptr.counts.get("activities", 0),
                        sais_count=ptr.counts.get("sais", 0),
                        footnotes_count=ptr.counts.get("footnotes", 0),
                    )
                    db.add(table_result)
                db.commit()
            except Exception as db_error:
                logger.error(f"Failed to save table results: {db_error}")
                db.rollback()
                raise
            finally:
                db.close()

            # --- Phase 3: Per-table classification (auto-confirm extraction) ---
            logger.info("[Phase 3] Running per-table classification...")
            _update_soa_job(soa_job_id, {
                "status": "classifying",
                "current_phase": "classification",
                "phase_progress": {"phase": "classification", "progress": 0},
            }, logger)

            # Get tables to classify
            SessionLocal = get_session_factory()
            db = SessionLocal()
            try:
                table_rows = db.query(SOATableResult).filter(
                    SOATableResult.soa_job_id == UUID(soa_job_id),
                    SOATableResult.status == "success",
                ).order_by(SOATableResult.table_id).all()

                tables_to_classify = []
                for tr in table_rows:
                    if tr.usdm_data:
                        tables_to_classify.append({
                            "table_id": tr.table_id,
                            "category": tr.table_category,
                            "usdm": tr.usdm_data,
                        })
            finally:
                db.close()

            classifier = SOATableClassifier()
            classification_profiles = {}

            for i, table_info in enumerate(tables_to_classify):
                tid = table_info["table_id"]
                progress_pct = int(((i + 1) / len(tables_to_classify)) * 100)
                _update_soa_job(soa_job_id, {
                    "phase_progress": {"phase": "classification", "progress": progress_pct},
                }, logger)

                try:
                    profile = loop.run_until_complete(classifier.classify(table_info["usdm"]))
                    classification_profiles[tid] = profile
                    logger.info(f"  {tid}: {profile.get('tableStructureType', 'unknown')}")
                except Exception as e:
                    logger.error(f"  {tid} classification failed: {e}")
                    classification_profiles[tid] = {
                        "tableStructureType": table_info["category"],
                        "confidence": 0.5,
                        "characteristics": [f"Fallback: {table_info['category']}"],
                        "stageGuidance": {},
                        "structuralFeatures": {},
                    }

            # --- Phase 4: Per-table interpretation (auto-confirm classification) ---
            logger.info("[Phase 4] Running per-table interpretation...")
            _update_soa_job(soa_job_id, {
                "status": "interpreting_tables",
                "current_phase": "interpreting_tables",
                "phase_progress": {"phase": "interpreting_tables", "progress": 0},
            }, logger)

            # Upload PDF to Gemini if needed
            if not gemini_file_uri:
                try:
                    gemini_service = GeminiFileService()
                    db_temp = get_session_factory()()
                    gemini_file_uri, _ = loop.run_until_complete(
                        gemini_service.get_or_upload_file_from_protocol(UUID(protocol_id), db_temp)
                    )
                    db_temp.close()
                except Exception as upload_err:
                    logger.warning(f"Gemini upload failed: {upload_err}")

            effective_extraction_outputs = auto_discover_extraction_outputs(Path(pdf_path))

            total_tables = len(tables_to_classify)
            all_usdm_results = []

            for table_idx, table_info in enumerate(tables_to_classify):
                tid = table_info["table_id"]
                usdm = table_info["usdm"]
                logger.info(f"  Interpreting table {tid} ({table_idx+1}/{total_tables})...")

                def make_progress_cb(t_idx, t_total):
                    stages_done = [0]
                    def cb(stage_num, stage_name, status):
                        stages_done[0] += 1
                        pct = int(((t_idx * 12 + stages_done[0]) / (t_total * 12)) * 100)
                        _update_soa_job(soa_job_id, {
                            "phase_progress": {"phase": "interpreting_tables", "progress": pct, "current_table": tid},
                        }, logger)
                    return cb

                try:
                    pipeline = InterpretationPipeline(progress_callback=make_progress_cb(table_idx, total_tables))
                    table_profile = classification_profiles.get(tid)

                    interp_config = InterpretationConfig(
                        protocol_id=f"{protocol_name}_{tid}",
                        protocol_name=protocol_name,
                        extraction_outputs=effective_extraction_outputs,
                        gemini_file_uri=gemini_file_uri,
                        skip_stage_11=True,
                        continue_on_non_critical_failure=True,
                        pre_computed_profile=table_profile,
                    )

                    pipeline_result = loop.run_until_complete(pipeline.run(usdm, interp_config))

                    final_usdm = usdm
                    if pipeline_result.final_usdm:
                        propagate_provenance(pipeline_result.final_usdm)
                        final_usdm = pipeline_result.final_usdm

                    # Serialize stage results for frontend display
                    serialized_stage_results = {}
                    stage_results = getattr(pipeline_result, 'stage_results', {}) or {}
                    for stage_num, stage_result in stage_results.items():
                        if stage_result is not None:
                            try:
                                if hasattr(stage_result, 'to_dict'):
                                    serialized_stage_results[stage_num] = stage_result.to_dict()
                                elif hasattr(stage_result, '__dict__'):
                                    serialized_stage_results[stage_num] = {
                                        k: v for k, v in stage_result.__dict__.items()
                                        if not k.startswith('_') and not callable(v)
                                    }
                                elif isinstance(stage_result, dict):
                                    serialized_stage_results[stage_num] = stage_result
                                else:
                                    serialized_stage_results[stage_num] = str(stage_result)
                            except Exception as se:
                                logger.warning(f"    Could not serialize stage {stage_num}: {se}")
                                serialized_stage_results[stage_num] = {"error": str(se)}

                    # Inject stage durations into serialized results
                    stage_durations = getattr(pipeline_result, 'stage_durations', {}) or {}
                    for stage_num, duration in stage_durations.items():
                        if stage_num in serialized_stage_results:
                            if isinstance(serialized_stage_results[stage_num], dict):
                                serialized_stage_results[stage_num]["duration"] = round(duration, 2)

                    # Update DB with interpreted USDM
                    SessionLocal = get_session_factory()
                    db = SessionLocal()
                    try:
                        from sqlalchemy.orm.attributes import flag_modified
                        table_row = db.query(SOATableResult).filter(
                            SOATableResult.soa_job_id == UUID(soa_job_id),
                            SOATableResult.table_id == tid,
                        ).first()
                        if table_row:
                            table_row.raw_usdm_data = table_row.usdm_data
                            flag_modified(table_row, "raw_usdm_data")
                            table_row.usdm_data = final_usdm
                            flag_modified(table_row, "usdm_data")
                            table_row.interpretation_stages = serialized_stage_results
                            flag_modified(table_row, "interpretation_stages")
                            table_row.visits_count = len(final_usdm.get("visits", final_usdm.get("encounters", [])))
                            table_row.activities_count = len(final_usdm.get("activities", []))
                            table_row.sais_count = len(final_usdm.get("scheduledActivityInstances", []))
                            table_row.footnotes_count = len(final_usdm.get("footnotes", []))
                            db.commit()
                    except Exception as db_err:
                        logger.error(f"Failed to update {tid}: {db_err}")
                        db.rollback()
                    finally:
                        db.close()

                    all_usdm_results.append(final_usdm)
                except Exception as e:
                    logger.error(f"  {tid} interpretation failed: {e}", exc_info=True)
                    all_usdm_results.append(usdm)

            # --- Phase 5: Build final merged USDM and mark completed ---
            logger.info("[Phase 5] Building final USDM output...")
            _update_soa_job(soa_job_id, {
                "status": "assembling",
                "current_phase": "assembly",
                "phase_progress": {"phase": "assembly", "progress": 50},
            }, logger)

            # Build combined USDM from all tables
            final_usdm = None
            if all_usdm_results:
                if len(all_usdm_results) == 1:
                    final_usdm = all_usdm_results[0]
                else:
                    final_usdm = {
                        "protocolId": protocol_name,
                        "visits": [],
                        "encounters": [],
                        "activities": [],
                        "scheduledActivityInstances": [],
                        "footnotes": [],
                    }
                    for u in all_usdm_results:
                        final_usdm["visits"].extend(u.get("visits", u.get("encounters", [])))
                        final_usdm["activities"].extend(u.get("activities", []))
                        final_usdm["scheduledActivityInstances"].extend(u.get("scheduledActivityInstances", []))
                        final_usdm["footnotes"].extend(u.get("footnotes", []))
                    final_usdm["encounters"] = final_usdm["visits"]

            _update_soa_job(soa_job_id, {
                "status": "completed",
                "current_phase": "completed",
                "usdm_data": final_usdm,
                "phase_progress": {"phase": "completed", "progress": 100},
                "completed_at": datetime.utcnow(),
            }, logger)

            logger.info(f"SOA fully automated extraction completed for job {soa_job_id}")

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Fully automated SOA extraction failed: {e}", exc_info=True)
        _update_soa_job(soa_job_id, {
            "status": "failed",
            "error_message": str(e)[:1000],
            "completed_at": datetime.utcnow(),
        }, logger)
        sys.exit(1)

    sys.exit(0)


def spawn_fully_automated_process(
    soa_job_id: UUID,
    protocol_id: UUID,
    pdf_path: str,
) -> multiprocessing.Process:
    """
    Spawn fully automated SOA extraction (no human checkpoints).

    Used by "Extract All" mode.
    """
    from app.config import settings

    ctx = multiprocessing.get_context('spawn')

    process = ctx.Process(
        target=_run_fully_automated,
        args=(
            str(soa_job_id),
            str(protocol_id),
            pdf_path,
            settings.database_url,
        ),
        daemon=False,
        name=f"soa-auto-{str(soa_job_id)[:8]}",
    )

    process.start()

    logging.getLogger(__name__).info(
        f"Spawned fully automated SOA process {process.pid} for job {soa_job_id}"
    )

    return process


# Registry to track active SOA processes
_active_soa_processes: dict[str, multiprocessing.Process] = {}


def get_active_soa_extractions() -> dict[str, dict]:
    """Get status of active SOA extraction processes."""
    result = {}
    for job_id, process in list(_active_soa_processes.items()):
        if process.is_alive():
            result[job_id] = {
                "pid": process.pid,
                "alive": True,
                "exitcode": None,
            }
        else:
            result[job_id] = {
                "pid": process.pid,
                "alive": False,
                "exitcode": process.exitcode,
            }
            del _active_soa_processes[job_id]
    return result


def register_soa_process(job_id: str, process: multiprocessing.Process):
    """Register an SOA extraction process for monitoring."""
    _active_soa_processes[job_id] = process
