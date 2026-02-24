"""
Full Extraction Worker — orchestrates all 3 pipelines in parallel.

Used by "Extract All" mode to run main extraction + SOA + eligibility
simultaneously without any human checkpoints.

Architecture:
    1. Creates sub-jobs for main, SOA, and eligibility
    2. Spawns all 3 in separate processes
    3. Monitors progress via database polling
    4. Updates FullExtractionJob with combined progress
"""

import asyncio
import logging
import multiprocessing
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID


def _setup_worker_logging(job_id: str) -> logging.Logger:
    """Configure logging for the full extraction worker."""
    logger = logging.getLogger(f"full_extraction_worker.{job_id[:8]}")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(handler)

    return logger


def _update_full_job(job_id: str, updates: dict, logger: Optional[logging.Logger] = None) -> bool:
    """Update FullExtractionJob with a fresh database connection."""
    from app.db import get_session_factory, FullExtractionJob

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        job = db.query(FullExtractionJob).filter(FullExtractionJob.id == UUID(job_id)).first()
        if job:
            for key, value in updates.items():
                setattr(job, key, value)
            job.updated_at = datetime.utcnow()
            db.commit()
            return True
        else:
            if logger:
                logger.error(f"FullExtractionJob not found: {job_id}")
            return False
    except Exception as e:
        if logger:
            logger.error(f"Failed to update FullExtractionJob: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def _run_full_extraction(
    full_job_id: str,
    protocol_id: str,
    pdf_path: str,
    database_url: str,
):
    """
    Entry point for full extraction worker process.

    Spawns main extraction, SOA, and eligibility in parallel,
    then monitors them until all complete.
    """
    logger = _setup_worker_logging(full_job_id)
    logger.info(f"Full extraction worker started for job {full_job_id}")

    try:
        os.environ.setdefault('FULL_EXTRACTION_WORKER', 'true')

        from app.db import get_session_factory, FullExtractionJob, Protocol, Job, SOAJob, EligibilityJob
        from app.services.checkpoint_service import CheckpointService

        # Update status to running
        _update_full_job(full_job_id, {
            "status": "running",
            "started_at": datetime.utcnow(),
        }, logger)

        # Get protocol info
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            protocol = db.query(Protocol).filter(Protocol.id == UUID(protocol_id)).first()
            if not protocol:
                raise ValueError(f"Protocol not found: {protocol_id}")
            protocol_name = protocol.filename.replace('.pdf', '')

            # Update protocol status
            protocol.extraction_status = "processing"
            db.commit()
        finally:
            db.close()

        # --- Create sub-jobs ---

        # 1. Main extraction job
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            checkpoint_service = CheckpointService(db)
            main_job = checkpoint_service.create_job(protocol_id=UUID(protocol_id))
            main_job_id = str(main_job.id)
        finally:
            db.close()

        # 2. SOA job
        import uuid as uuid_module
        soa_job_id = str(uuid_module.uuid4())
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            soa_job = SOAJob(
                id=UUID(soa_job_id),
                protocol_id=UUID(protocol_id),
                protocol_name=protocol_name,
                status="detecting_pages",
            )
            db.add(soa_job)
            db.commit()
        finally:
            db.close()

        # 3. Eligibility job
        eligibility_job_id = str(uuid_module.uuid4())
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            eligibility_job = EligibilityJob(
                id=UUID(eligibility_job_id),
                protocol_id=UUID(protocol_id),
                protocol_name=protocol_name,
                status="detecting_sections",
            )
            db.add(eligibility_job)
            db.commit()
        finally:
            db.close()

        # Link sub-job IDs
        _update_full_job(full_job_id, {
            "main_job_id": UUID(main_job_id),
            "soa_job_id": UUID(soa_job_id),
            "eligibility_job_id": UUID(eligibility_job_id),
            "main_status": "running",
            "soa_status": "running",
            "eligibility_status": "running",
        }, logger)

        logger.info(f"Created sub-jobs: main={main_job_id[:8]}, soa={soa_job_id[:8]}, eligibility={eligibility_job_id[:8]}")

        # --- Spawn all 3 pipelines ---
        from app.services.extraction_worker import spawn_extraction_process
        from app.services.soa_worker import spawn_fully_automated_process as spawn_soa_auto
        from app.services.eligibility_worker import spawn_fully_automated_process as spawn_eligibility_auto

        main_process = spawn_extraction_process(
            job_id=UUID(main_job_id),
            protocol_id=UUID(protocol_id),
            pdf_path=pdf_path,
            resume=True,
        )

        soa_process = spawn_soa_auto(
            soa_job_id=UUID(soa_job_id),
            protocol_id=UUID(protocol_id),
            pdf_path=pdf_path,
        )

        eligibility_process = spawn_eligibility_auto(
            job_id=UUID(eligibility_job_id),
            protocol_id=UUID(protocol_id),
            pdf_path=pdf_path,
        )

        logger.info(f"Spawned all 3 pipelines: main PID={main_process.pid}, soa PID={soa_process.pid}, eligibility PID={eligibility_process.pid}")

        # --- Monitor progress ---
        TERMINAL_STATUSES = {"completed", "completed_with_errors", "failed"}
        poll_interval = 10  # seconds

        while True:
            time.sleep(poll_interval)

            # Poll each sub-job status
            SessionLocal = get_session_factory()
            db = SessionLocal()
            try:
                # Main job
                main_job_row = db.query(Job).filter(Job.id == UUID(main_job_id)).first()
                main_status = main_job_row.status if main_job_row else "unknown"
                main_completed = len(main_job_row.completed_modules or []) if main_job_row else 0
                main_total = main_job_row.total_modules or 16
                main_progress = int((main_completed / main_total) * 100) if main_total > 0 else 0
                if main_status in TERMINAL_STATUSES:
                    main_progress = 100

                # SOA job
                soa_job_row = db.query(SOAJob).filter(SOAJob.id == UUID(soa_job_id)).first()
                soa_status = soa_job_row.status if soa_job_row else "unknown"
                soa_phase_progress = soa_job_row.phase_progress if soa_job_row else {}
                soa_progress = soa_phase_progress.get("progress", 0) if soa_phase_progress else 0
                if soa_status in TERMINAL_STATUSES:
                    soa_progress = 100

                # Eligibility job
                elig_job_row = db.query(EligibilityJob).filter(EligibilityJob.id == UUID(eligibility_job_id)).first()
                elig_status = elig_job_row.status if elig_job_row else "unknown"
                elig_phase_progress = elig_job_row.phase_progress if elig_job_row else {}
                elig_progress = elig_phase_progress.get("progress", 0) if elig_phase_progress else 0
                if elig_status in TERMINAL_STATUSES:
                    elig_progress = 100

            finally:
                db.close()

            # Calculate combined progress (weighted: main=50%, SOA=30%, eligibility=20%)
            overall_progress = int(main_progress * 0.5 + soa_progress * 0.3 + elig_progress * 0.2)

            _update_full_job(full_job_id, {
                "main_status": main_status,
                "soa_status": soa_status,
                "eligibility_status": elig_status,
                "main_progress": main_progress,
                "soa_progress": soa_progress,
                "eligibility_progress": elig_progress,
                "overall_progress": overall_progress,
            }, logger)

            logger.info(
                f"Progress: main={main_progress}% ({main_status}), "
                f"soa={soa_progress}% ({soa_status}), "
                f"eligibility={elig_progress}% ({elig_status}), "
                f"overall={overall_progress}%"
            )

            # Check if all pipelines are done
            all_done = (
                main_status in TERMINAL_STATUSES
                and soa_status in TERMINAL_STATUSES
                and elig_status in TERMINAL_STATUSES
            )

            if all_done:
                break

        # --- Determine final status ---
        any_failed = main_status == "failed" or soa_status == "failed" or elig_status == "failed"
        any_with_errors = "completed_with_errors" in [main_status, soa_status, elig_status]

        if any_failed:
            final_status = "completed_with_errors"
            errors = []
            if main_status == "failed":
                errors.append("Main extraction failed")
            if soa_status == "failed":
                errors.append("SOA extraction failed")
            if elig_status == "failed":
                errors.append("Eligibility extraction failed")
            error_msg = "; ".join(errors)
        elif any_with_errors:
            final_status = "completed_with_errors"
            error_msg = "Some pipelines completed with errors"
        else:
            final_status = "completed"
            error_msg = None

        _update_full_job(full_job_id, {
            "status": final_status,
            "overall_progress": 100,
            "error_message": error_msg,
            "completed_at": datetime.utcnow(),
        }, logger)

        # Update protocol status
        SessionLocal = get_session_factory()
        db = SessionLocal()
        try:
            protocol = db.query(Protocol).filter(Protocol.id == UUID(protocol_id)).first()
            if protocol:
                protocol.extraction_status = final_status
                db.commit()
        finally:
            db.close()

        logger.info(f"Full extraction completed: {final_status}")

    except Exception as e:
        logger.error(f"Full extraction worker error: {e}", exc_info=True)
        _update_full_job(full_job_id, {
            "status": "failed",
            "error_message": str(e)[:1000],
            "completed_at": datetime.utcnow(),
        }, logger)
        sys.exit(1)

    sys.exit(0)


def spawn_full_extraction_process(
    full_job_id: UUID,
    protocol_id: UUID,
    pdf_path: str,
) -> multiprocessing.Process:
    """
    Spawn the full extraction orchestrator in a separate process.

    This process spawns and monitors all 3 sub-pipelines.
    """
    from app.config import settings

    ctx = multiprocessing.get_context('spawn')

    process = ctx.Process(
        target=_run_full_extraction,
        args=(
            str(full_job_id),
            str(protocol_id),
            pdf_path,
            settings.database_url,
        ),
        daemon=False,
        name=f"full-extraction-{str(full_job_id)[:8]}",
    )

    process.start()

    logging.getLogger(__name__).info(
        f"Spawned full extraction process {process.pid} for job {full_job_id}"
    )

    return process
