"""
Eligibility Extraction Worker - Human-in-the-Loop Pipeline

This module provides process-based isolation for eligibility extraction with a checkpoint
after section detection for human verification.

Architecture:
    Stage 1: Section Detection (runs when user starts eligibility analysis)
        - Detect eligibility sections using Gemini Vision
        - Save detected sections to database
        - Set status to 'awaiting_section_confirmation'
        - Wait for user confirmation

    Stage 2: Full Extraction (runs after user confirms/corrects sections)
        - Extract criteria using Claude two-phase
        - Run 12-stage interpretation pipeline
        - Validate results (5D quality scoring)
        - Save USDM output
"""

import asyncio
import logging
import multiprocessing
import os
import threading
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID


def _setup_worker_logging(job_id: str, stage: str) -> logging.Logger:
    """Configure logging for the eligibility worker process."""
    logger = logging.getLogger(f"eligibility_worker.{stage}.{job_id[:8]}")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(handler)

    return logger


def _update_eligibility_job(job_id: str, updates: Dict[str, Any], logger: Optional[logging.Logger] = None) -> bool:
    """
    Update eligibility job with a fresh database connection.

    Uses a fresh connection for each update to avoid NeonDB SSL timeout issues
    during long-running extraction pipelines.

    Args:
        job_id: The eligibility job UUID as a string
        updates: Dictionary of field names to values to update
        logger: Optional logger for error messages

    Returns:
        True if update succeeded, False otherwise
    """
    from app.db import get_session_factory, EligibilityJob

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        job = db.query(EligibilityJob).filter(EligibilityJob.id == UUID(job_id)).first()
        if job:
            for key, value in updates.items():
                setattr(job, key, value)
            job.updated_at = datetime.utcnow()
            db.commit()
            return True
        else:
            if logger:
                logger.error(f"Eligibility job not found: {job_id}")
            return False
    except Exception as e:
        if logger:
            logger.error(f"Failed to update eligibility job: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def _run_section_detection(
    job_id: str,
    protocol_id: str,
    pdf_path: str,
    database_url: str,
):
    """
    Stage 1: Run section detection only.

    This function runs in a separate OS process and detects eligibility sections,
    then pauses for user confirmation.
    """
    logger = _setup_worker_logging(job_id, "detection")
    logger.info(f"Eligibility section detection started for job {job_id}")

    try:
        os.environ.setdefault('ELIGIBILITY_WORKER', 'true')

        # Import after setting environment
        from app.db import get_session_factory, EligibilityJob, Protocol
        from eligibility_analyzer.eligibility_section_detector import (
            detect_eligibility_sections,
            DetectionResult,
        )

        # Create database session
        SessionLocal = get_session_factory()
        db = SessionLocal()

        try:
            # Update job status to detecting
            job = db.query(EligibilityJob).filter(EligibilityJob.id == UUID(job_id)).first()
            if not job:
                raise ValueError(f"Eligibility job not found: {job_id}")

            job.status = "detecting_sections"
            job.started_at = datetime.utcnow()
            job.current_phase = "detection"
            job.phase_progress = {"phase": "detection", "progress": 0}
            db.commit()

            # Run section detection
            logger.info(f"Detecting eligibility sections in {pdf_path}")
            detection_result: DetectionResult = detect_eligibility_sections(pdf_path, validate=True)

            if not detection_result.success:
                raise RuntimeError(f"Section detection failed: {detection_result.error}")

            # Extract section information for frontend
            sections = []

            if detection_result.inclusion_section:
                inc = detection_result.inclusion_section
                sections.append({
                    "id": "INCLUSION",
                    "type": "inclusion",
                    "pageStart": inc.page_start,
                    "pageEnd": inc.page_end,
                    "pages": list(range(inc.page_start, inc.page_end + 1)),
                    "title": inc.section_title or "Inclusion Criteria",
                    "confidence": inc.confidence,
                })

            if detection_result.exclusion_section:
                exc = detection_result.exclusion_section
                sections.append({
                    "id": "EXCLUSION",
                    "type": "exclusion",
                    "pageStart": exc.page_start,
                    "pageEnd": exc.page_end,
                    "pages": list(range(exc.page_start, exc.page_end + 1)),
                    "title": exc.section_title or "Exclusion Criteria",
                    "confidence": exc.confidence,
                })

            logger.info(f"Detected {len(sections)} eligibility section(s)")
            for section in sections:
                logger.info(f"  {section['id']}: pages {section['pageStart']}-{section['pageEnd']} (conf: {section['confidence']:.2f})")

            # Save detected sections and set status to awaiting confirmation
            detected_sections = {
                "totalSections": len(sections),
                "sections": sections,
                "crossReferences": [cr.to_dict() for cr in detection_result.cross_references],
                "geminiFileUri": detection_result.gemini_file_uri,
            }

            job.detected_sections = detected_sections
            job.status = "awaiting_section_confirmation"
            job.phase_progress = {"phase": "detection", "progress": 100}
            job.updated_at = datetime.utcnow()
            db.commit()

            logger.info(f"Section detection complete. Awaiting user confirmation for job {job_id}")

        except Exception as e:
            logger.error(f"Section detection failed: {e}", exc_info=True)

            # Mark job as failed
            try:
                job = db.query(EligibilityJob).filter(EligibilityJob.id == UUID(job_id)).first()
                if job:
                    job.status = "failed"
                    job.error_message = str(e)[:1000]
                    job.updated_at = datetime.utcnow()
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

    logger.info(f"Eligibility section detection worker finished for job {job_id}")
    sys.exit(0)


def _run_full_extraction(
    job_id: str,
    protocol_id: str,
    pdf_path: str,
    confirmed_sections: Dict[str, Any],
    skip_feasibility: bool,
    use_cache: bool,
    database_url: str,
):
    """
    Stage 2: Run full extraction after section confirmation.

    Uses the confirmed/corrected sections to run extraction, interpretation,
    validation, and output phases.

    Note: Uses fresh DB connections for each update to avoid NeonDB SSL timeout
    during the 10-15 minute extraction process.
    """
    import time

    logger = _setup_worker_logging(job_id, "extraction")
    logger.info(f"Eligibility full extraction started for job {job_id}")

    try:
        os.environ.setdefault('ELIGIBILITY_WORKER', 'true')

        # Import after setting environment
        from app.db import get_session_factory, EligibilityJob, Protocol
        from eligibility_analyzer.eligibility_extraction_pipeline import EligibilityExtractionPipeline

        # Update initial job status with fresh connection
        _update_eligibility_job(job_id, {
            "status": "extracting",
            "current_phase": "extraction",
            "confirmed_sections": confirmed_sections,
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
        finally:
            db.close()

        # Create output directory
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        project_root = Path(__file__).parent.parent.parent
        output_dir = project_root / "protocols" / protocol_name / "eligibility_output" / timestamp
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory: {output_dir}")

        # ATHENA database path for OMOP concept mapping
        # Use environment variable if set, otherwise fall back to relative path from backend_vNext
        athena_db_path = os.environ.get('ATHENA_DB_PATH') or str(
            Path(__file__).parent.parent.parent / "athena_concepts_full.db"
        )

        # Create pipeline instance with ATHENA database
        pipeline = EligibilityExtractionPipeline(athena_db_path=athena_db_path)

        # Create async event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Run the full pipeline
            logger.info("Starting eligibility extraction pipeline")

            # Progress callback for real-time updates
            def on_progress(phase: str, stage: int, total_stages: int, stage_name: str):
                # Map progress: extraction=10-20%, interpretation=20-80%, validation=80-90%
                if phase == "extraction":
                    progress = 10 + int((stage / max(total_stages, 1)) * 10)
                elif phase == "interpretation":
                    progress = 20 + int((stage / max(total_stages, 1)) * 60)
                elif phase == "validation":
                    progress = 80 + int((stage / max(total_stages, 1)) * 10)
                else:
                    progress = 90

                _update_eligibility_job(job_id, {
                    "current_phase": phase,
                    "phase_progress": {
                        "phase": phase,
                        "progress": progress,
                        "stage": stage,
                        "totalStages": total_stages,
                        "stageName": stage_name
                    },
                }, logger)
                logger.info(f"Progress: {phase} - Stage {stage}/{total_stages}: {stage_name} ({progress}%)")

            # Update status to extracting
            _update_eligibility_job(job_id, {
                "current_phase": "extraction",
                "phase_progress": {"phase": "extraction", "progress": 10},
            }, logger)

            # Run the pipeline with progress callback
            result = loop.run_until_complete(
                pipeline.run(
                    pdf_path=pdf_path,
                    output_dir=str(output_dir),
                    protocol_id=protocol_name,
                    protocol_name=protocol_name,
                    use_cache=use_cache,
                    skip_feasibility=skip_feasibility,
                    progress_callback=on_progress,
                )
            )

            if not result.success:
                raise RuntimeError(f"Extraction failed: {result.errors}")

            # Update progress for each phase
            for phase in result.phases:
                phase_name = phase.phase.lower()
                if phase_name == "interpretation":
                    _update_eligibility_job(job_id, {
                        "status": "interpreting",
                        "current_phase": "interpretation",
                        "phase_progress": {"phase": "interpretation", "progress": 50},
                    }, logger)
                elif phase_name == "validation":
                    _update_eligibility_job(job_id, {
                        "status": "validating",
                        "current_phase": "validation",
                        "phase_progress": {"phase": "validation", "progress": 80},
                    }, logger)

            # Final save with retry logic for robustness
            final_updates = {
                "status": "completed",
                "current_phase": "completed",
                "usdm_data": result.usdm_data,
                "quality_report": result.quality_score.to_dict() if result.quality_score else None,
                "interpretation_result": result.interpretation_result.to_dict() if result.interpretation_result else None,
                "raw_criteria": result.raw_criteria,
                "feasibility_result": result.feasibility_result,
                "qeb_result": result.interpretation_result.qeb_result if result.interpretation_result else None,
                "inclusion_count": result.inclusion_count,
                "exclusion_count": result.exclusion_count,
                "atomic_count": result.atomic_count,
                "phase_progress": {"phase": "completed", "progress": 100},
                "completed_at": datetime.utcnow(),
            }

            # Try to save with retry
            if not _update_eligibility_job(job_id, final_updates, logger):
                logger.warning("First attempt to save final results failed, retrying...")
                time.sleep(2)
                if not _update_eligibility_job(job_id, final_updates, logger):
                    logger.error("Failed to save final results after retry")
                    raise RuntimeError("Failed to save final results to database")

            logger.info(f"Eligibility extraction completed for job {job_id}")
            logger.info(result.get_summary())

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Full extraction failed: {e}", exc_info=True)

        # Mark job as failed with fresh connection
        _update_eligibility_job(job_id, {
            "status": "failed",
            "error_message": str(e)[:1000],
        }, logger)

        sys.exit(1)

    logger.info(f"Eligibility full extraction worker finished for job {job_id}")
    sys.exit(0)


def spawn_section_detection_process(
    job_id: UUID,
    protocol_id: UUID,
    pdf_path: str,
) -> multiprocessing.Process:
    """
    Spawn Stage 1 (section detection) in a separate process.

    Returns immediately after starting the subprocess.
    """
    from app.config import settings

    ctx = multiprocessing.get_context('spawn')

    process = ctx.Process(
        target=_run_section_detection,
        args=(
            str(job_id),
            str(protocol_id),
            pdf_path,
            settings.effective_database_url,
        ),
        daemon=False,
        name=f"eligibility-detection-{str(job_id)[:8]}",
    )

    process.start()

    logging.getLogger(__name__).info(
        f"Spawned eligibility section detection process {process.pid} for job {job_id}"
    )

    return process


def spawn_full_extraction_process(
    job_id: UUID,
    protocol_id: UUID,
    pdf_path: str,
    confirmed_sections: Dict[str, Any],
    skip_feasibility: bool = False,
    use_cache: bool = False,
) -> multiprocessing.Process:
    """
    Spawn Stage 2 (full extraction) in a separate process.

    Called after user confirms/corrects the detected sections.
    """
    from app.config import settings

    ctx = multiprocessing.get_context('spawn')

    process = ctx.Process(
        target=_run_full_extraction,
        args=(
            str(job_id),
            str(protocol_id),
            pdf_path,
            confirmed_sections,
            skip_feasibility,
            use_cache,
            settings.effective_database_url,
        ),
        daemon=False,
        name=f"eligibility-extraction-{str(job_id)[:8]}",
    )

    process.start()

    logging.getLogger(__name__).info(
        f"Spawned eligibility full extraction process {process.pid} for job {job_id}"
    )

    return process


# Registry to track active eligibility processes (thread-safe)
_process_lock = threading.Lock()
_active_eligibility_processes: dict[str, multiprocessing.Process] = {}


def get_active_eligibility_extractions() -> dict[str, dict]:
    """Get status of active eligibility extraction processes."""
    result = {}
    with _process_lock:
        for job_id, process in list(_active_eligibility_processes.items()):
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
                del _active_eligibility_processes[job_id]
    return result


def register_eligibility_process(job_id: str, process: multiprocessing.Process):
    """Register an eligibility extraction process for monitoring."""
    with _process_lock:
        _active_eligibility_processes[job_id] = process
