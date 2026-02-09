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
                    'quality_report', 'extraction_review', 'interpretation_review', 'merge_analysis'}

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

            # Save per-table USDM to local JSON files
            import json
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            pdf_dir = Path(pdf_path).parent
            output_dir = pdf_dir / "soa_output" / timestamp / "per_table_usdm"
            output_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Saving per-table USDM to local files: {output_dir}")

            saved_files = []
            for ptr in result.per_table_results:
                if ptr.usdm:
                    # Save individual table USDM
                    table_file = output_dir / f"{protocol_name}_{ptr.table_id}_{ptr.category}.json"
                    with open(table_file, 'w') as f:
                        json.dump(ptr.usdm, f, indent=2, default=str)
                    saved_files.append(str(table_file))
                    logger.info(f"  Saved: {table_file.name}")

            # Save summary file
            summary = {
                "protocolId": protocol_name,
                "timestamp": timestamp,
                "totalTables": len(result.per_table_results),
                "successfulTables": sum(1 for ptr in result.per_table_results if ptr.success),
                "tables": [
                    {
                        "tableId": ptr.table_id,
                        "category": ptr.category,
                        "status": "success" if ptr.success else "failed",
                        "error": ptr.error,
                        "counts": ptr.counts,
                        "file": f"{protocol_name}_{ptr.table_id}_{ptr.category}.json" if ptr.usdm else None,
                    }
                    for ptr in result.per_table_results
                ],
                "outputDir": str(output_dir),
            }
            summary_file = output_dir / f"{protocol_name}_per_table_summary.json"
            with open(summary_file, 'w') as f:
                json.dump(summary, f, indent=2, default=str)
            logger.info(f"  Saved summary: {summary_file.name}")

            # Also save merged USDM
            if result.usdm_data:
                merged_file = output_dir.parent / f"{protocol_name}_merged_usdm.json"
                with open(merged_file, 'w') as f:
                    json.dump(result.usdm_data, f, indent=2, default=str)
                logger.info(f"  Saved merged USDM: {merged_file.name}")

            logger.info(f"Successfully saved {len(saved_files)} per-table JSON files")

            # Final save - update SOA job with merged USDM and completion status
            final_updates = {
                "status": "completed",
                "usdm_data": result.usdm_data,  # Merged USDM from all tables
                "phase_progress": {"phase": "completed", "progress": 100},
                "completed_at": datetime.utcnow(),
            }

            # Try to save with retry
            if not _update_soa_job(soa_job_id, final_updates, logger):
                logger.warning("First attempt to save final results failed, retrying...")
                time.sleep(2)
                if not _update_soa_job(soa_job_id, final_updates, logger):
                    logger.error("Failed to save final results after retry")
                    raise RuntimeError("Failed to save final results to database")

            logger.info(f"SOA extraction completed for job {soa_job_id}")

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Full extraction failed: {e}", exc_info=True)

        # Mark job as failed with fresh connection
        _update_soa_job(soa_job_id, {
            "status": "failed",
            "error_message": str(e)[:1000],
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
            settings.effective_database_url,
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
            settings.effective_database_url,
        ),
        daemon=False,
        name=f"soa-extraction-{str(soa_job_id)[:8]}",
    )

    process.start()

    logging.getLogger(__name__).info(
        f"Spawned SOA full extraction process {process.pid} for job {soa_job_id}"
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
                    # Get decision level from the last level result in decision_path
                    decision_level = mg.decision_path[-1].level if mg.decision_path else 0
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
                    })

                # Also add standalone tables info
                for table_id in merge_plan.standalone_tables:
                    # Find existing group or this is already in a group
                    pass  # standalone_tables are already represented in merge_groups as single-table groups

                # Save merge plan directly to soa_job.merge_analysis
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
            settings.effective_database_url,
        ),
        daemon=False,
        name=f"soa-merge-analysis-{str(soa_job_id)[:8]}",
    )

    process.start()

    logging.getLogger(__name__).info(
        f"Spawned SOA merge analysis process {process.pid} for job {soa_job_id}"
    )

    return process


def _run_merge_interpretation(
    soa_job_id: str,
    protocol_id: str,
    pdf_path: str,
    confirmed_plan: Dict[str, Any],
    database_url: str,
):
    """
    Stage 3: Run 12-stage interpretation on confirmed merge groups.

    This function runs after the merge plan is confirmed. It processes
    each merge group sequentially, running the full interpretation pipeline.
    Group results are stored in soa_job.merge_analysis.groupResults.
    """
    import time
    from sqlalchemy.orm.attributes import flag_modified

    logger = _setup_worker_logging(soa_job_id, "interpretation")
    logger.info(f"SOA merge interpretation started for job {soa_job_id}")

    try:
        os.environ.setdefault('SOA_WORKER', 'true')

        # Import after setting environment
        from app.db import get_session_factory, SOAJob, SOATableResult, Protocol
        from soa_analyzer.table_merge_analyzer import combine_table_usdm
        from soa_analyzer.interpretation import InterpretationPipeline, PipelineConfig as InterpretationConfig

        # Update initial job status
        _update_soa_job(soa_job_id, {
            "status": "interpreting",
            "current_phase": "interpretation",
            "phase_progress": {"phase": "interpretation", "progress": 0},
        }, logger)

        # Get protocol info and merge plan from soa_job
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            protocol = db.query(Protocol).filter(Protocol.id == UUID(protocol_id)).first()
            if not protocol:
                raise ValueError(f"Protocol not found: {protocol_id}")
            protocol_name = protocol.filename.replace('.pdf', '')
            gemini_file_uri = protocol.gemini_file_uri

            # Get merge plan from soa_job.merge_analysis
            soa_job = db.query(SOAJob).filter(SOAJob.id == UUID(soa_job_id)).first()
            if not soa_job or not soa_job.merge_analysis:
                raise ValueError(f"Merge analysis not found for job: {soa_job_id}")
            original_plan = soa_job.merge_analysis

            # Get all per-table results for this job
            table_results = db.query(SOATableResult).filter(
                SOATableResult.soa_job_id == UUID(soa_job_id)
            ).all()

            # Build a list compatible with combine_table_usdm
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
                # Use original group as-is
                groups_to_process.append({
                    "id": group_id,
                    "table_ids": original_group.get("tableIds", []),
                    "merge_type": original_group.get("mergeType", "unknown"),
                })
            elif is_confirmed:
                # Standalone table
                groups_to_process.append({
                    "id": group_id,
                    "table_ids": [group_id.replace("MG-", "SOA-")],  # Convert back
                    "merge_type": "standalone",
                })

        logger.info(f"Processing {len(groups_to_process)} merge groups")

        # Initialize group results list to store in merge_analysis
        group_results = []

        # Create async event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Stage-level progress tracking
        total_groups = len(groups_to_process)
        total_stages = total_groups * 12  # 12 stages per group

        # Mutable state for progress callback (allows callback to access current group info)
        progress_state = {
            "group_idx": 0,
            "group_id": "",
            "stages_in_current_group": 0,
        }

        def stage_progress_callback(stage_num: int, stage_name: str, status: str):
            """Callback to update database after each stage completes."""
            progress_state["stages_in_current_group"] += 1

            # Calculate overall progress: (completed_groups * 12 + current_stage) / total_stages * 100
            group_idx = progress_state["group_idx"]
            completed_stages = (group_idx * 12) + progress_state["stages_in_current_group"]
            progress_pct = int((completed_stages / total_stages) * 100) if total_stages > 0 else 0

            _update_soa_job(soa_job_id, {
                "phase_progress": {
                    "phase": "interpretation",
                    "progress": progress_pct,
                    "current_group": progress_state["group_id"],
                    "current_stage": stage_num,
                    "current_stage_name": stage_name,
                    "current_stage_status": status,
                    "groups_completed": group_idx,
                    "groups_total": total_groups,
                },
            }, logger)

            logger.debug(f"[Progress] Stage {stage_num} ({stage_name}): {status} - Overall: {progress_pct}%")

        try:
            interpretation_pipeline = InterpretationPipeline(progress_callback=stage_progress_callback)

            for i, group in enumerate(groups_to_process):
                group_id = group["id"]
                table_ids = group["table_ids"]
                merge_type = group["merge_type"]

                logger.info(f"Processing group {group_id} ({i+1}/{total_groups}): tables {table_ids}")

                # Update progress state for the callback to use
                progress_state["group_idx"] = i
                progress_state["group_id"] = group_id
                progress_state["stages_in_current_group"] = 0

                # Initial progress update at start of group
                initial_progress = int((i * 12 / total_stages) * 100) if total_stages > 0 else 0
                _update_soa_job(soa_job_id, {
                    "phase_progress": {
                        "phase": "interpretation",
                        "progress": initial_progress,
                        "current_group": group_id,
                        "current_stage": 0,
                        "current_stage_name": "Starting...",
                        "groups_completed": i,
                        "groups_total": total_groups,
                    },
                }, logger)

                # Initialize group result entry for merge_analysis.groupResults
                import uuid as uuid_module
                group_result_entry = {
                    "id": group_id,
                    "mergeGroupId": group_id,
                    "sourceTableIds": table_ids,
                    "mergeType": merge_type,
                    "status": "interpreting",
                    "createdAt": datetime.utcnow().isoformat(),
                }

                try:
                    # Combine USDM from tables in this group
                    combined_usdm = combine_table_usdm(per_table_results, table_ids)

                    if not combined_usdm:
                        raise ValueError(f"No USDM data found for tables: {table_ids}")

                    group_result_entry["mergedUsdm"] = combined_usdm

                    # Run 12-stage interpretation pipeline
                    # Determine output directory for saving intermediate results
                    pdf_dir = Path(pdf_path).parent
                    output_dir = pdf_dir / "soa_output" / datetime.utcnow().strftime("%Y%m%d_%H%M%S") / f"group_{group_id}"
                    output_dir.mkdir(parents=True, exist_ok=True)

                    interp_config = InterpretationConfig(
                        protocol_id=f"{protocol_name}_{group_id}",
                        protocol_name=protocol_name,
                        gemini_file_uri=gemini_file_uri,
                        skip_stage_11=True,
                        continue_on_non_critical_failure=True,
                        save_intermediate_results=True,
                        output_dir=output_dir,
                    )

                    pipeline_result = loop.run_until_complete(
                        interpretation_pipeline.run(combined_usdm, interp_config)
                    )

                    # Serialize stage results for storage
                    serialized_stage_results = {}
                    stage_results = getattr(pipeline_result, 'stage_results', {}) or {}
                    for stage_num, stage_result in stage_results.items():
                        if stage_result is not None:
                            try:
                                if hasattr(stage_result, 'to_dict'):
                                    serialized_stage_results[stage_num] = stage_result.to_dict()
                                elif hasattr(stage_result, '__dict__'):
                                    # Filter out private attributes and non-serializable items
                                    serialized_stage_results[stage_num] = {
                                        k: v for k, v in stage_result.__dict__.items()
                                        if not k.startswith('_') and not callable(v)
                                    }
                                elif isinstance(stage_result, dict):
                                    serialized_stage_results[stage_num] = stage_result
                                else:
                                    serialized_stage_results[stage_num] = str(stage_result)
                            except Exception as se:
                                logger.warning(f"    Could not serialize stage {stage_num} result: {se}")
                                serialized_stage_results[stage_num] = {"error": str(se)}

                    # Update group result with interpretation output
                    final_usdm = pipeline_result.final_usdm or combined_usdm
                    group_result_entry["status"] = "completed"
                    group_result_entry["interpretationResult"] = {
                        **(pipeline_result.to_dict() if hasattr(pipeline_result, 'to_dict') else {}),
                        "stageResults": serialized_stage_results,  # Add full stage results
                    }
                    group_result_entry["stageResults"] = serialized_stage_results  # Also store at top level for easy access
                    group_result_entry["finalUsdm"] = final_usdm
                    group_result_entry["counts"] = {
                        "visits": len(final_usdm.get("visits", [])),
                        "activities": len(final_usdm.get("activities", [])),
                        "sais": len(final_usdm.get("scheduledActivityInstances", [])),
                        "footnotes": len(final_usdm.get("footnotes", [])),
                    }
                    group_result_entry["completedAt"] = datetime.utcnow().isoformat()

                    logger.info(f"  Group {group_id} completed: {pipeline_result.get_summary() if hasattr(pipeline_result, 'get_summary') else 'OK'}")
                    logger.info(f"    Saved {len(serialized_stage_results)} stage results")

                except Exception as e:
                    logger.error(f"  Group {group_id} failed: {e}")
                    group_result_entry["status"] = "failed"
                    group_result_entry["errorMessage"] = str(e)[:1000]
                    group_result_entry["completedAt"] = datetime.utcnow().isoformat()

                # Add to results list
                group_results.append(group_result_entry)

                # Update merge_analysis.groupResults in database after each group
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

            logger.info(f"SOA merge interpretation completed for job {soa_job_id}")

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Merge interpretation failed: {e}", exc_info=True)

        # Mark job as failed
        _update_soa_job(soa_job_id, {
            "status": "failed",
            "error_message": str(e)[:1000],
        }, logger)

        sys.exit(1)

    logger.info(f"SOA merge interpretation worker finished for job {soa_job_id}")
    sys.exit(0)


def spawn_merge_interpretation_process(
    soa_job_id: UUID,
    protocol_id: UUID,
    pdf_path: str,
    confirmed_plan: Dict[str, Any],
) -> multiprocessing.Process:
    """
    Spawn Stage 3 (merge interpretation) in a separate process.

    Called after user confirms the merge plan.
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
            settings.effective_database_url,
        ),
        daemon=False,
        name=f"soa-interpretation-{str(soa_job_id)[:8]}",
    )

    process.start()

    logging.getLogger(__name__).info(
        f"Spawned SOA merge interpretation process {process.pid} for job {soa_job_id}"
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
