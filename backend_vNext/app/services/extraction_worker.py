"""
Extraction worker that runs in a separate OS process.

This module provides process-based isolation for extraction jobs, ensuring
the API server remains responsive during long-running LLM extractions.

Architecture:
    API Process                    Extraction Process
    ───────────                    ──────────────────
    1. Receive request
    2. Create job record
    3. spawn_extraction() ──────► 4. Worker process starts
    4. Return immediately          5. Run extraction (may take 30+ minutes)
    5. Handle other requests       6. Update DB directly
                                   7. Exit when complete

Key Design Decisions:
- Uses multiprocessing.Process for true OS-level isolation
- Worker connects to its own database session (required for separate process)
- No shared state between API and worker (communicates via database)
- Worker is fire-and-forget; API polls job status via /jobs/{id} endpoint
"""

import asyncio
import logging
import multiprocessing
import os
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

# Configure logging for worker process
def _setup_worker_logging(job_id: str) -> logging.Logger:
    """Configure logging for the extraction worker process."""
    logger = logging.getLogger(f"extraction_worker.{job_id[:8]}")
    logger.setLevel(logging.INFO)

    # Create handler if not exists
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(handler)

    return logger


def _run_extraction_in_process(
    job_id: str,
    protocol_id: str,
    pdf_path: str,
    resume: bool,
    database_url: str,
):
    """
    Entry point for extraction worker process.

    This function runs in a completely separate OS process from the API server.
    It creates its own database connection and runs extraction synchronously.

    Args:
        job_id: UUID of the extraction job
        protocol_id: UUID of the protocol
        pdf_path: Path to the PDF file
        resume: Whether to resume from checkpoint
        database_url: Database connection URL (passed explicitly to avoid import issues)
    """
    logger = _setup_worker_logging(job_id)
    logger.info(f"Extraction worker started for job {job_id}")

    try:
        # Import here to avoid issues with multiprocessing fork
        # Each process needs to initialize its own modules
        os.environ.setdefault('EXTRACTION_WORKER', 'true')

        # Import after setting environment
        from app.db import get_session_factory
        from app.services.sequential_orchestrator import SequentialOrchestrator

        # Create a new database session for this process
        SessionLocal = get_session_factory()
        db = SessionLocal()

        try:
            logger.info(f"Starting extraction for job {job_id}")

            # Get protocol record to determine output directory
            from app.db import Protocol
            protocol = db.query(Protocol).filter(Protocol.id == protocol_id).first()
            if not protocol:
                raise ValueError(f"Protocol not found: {protocol_id}")

            # Create output directory: outputs/{protocol_filename}/{timestamp}/
            protocol_name = protocol.filename.replace('.pdf', '')
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

            # Use project root's outputs directory (not protocols/)
            project_root = Path(__file__).parent.parent.parent  # backend_vNext/
            outputs_dir = project_root / "outputs" / protocol_name
            output_dir = outputs_dir / timestamp
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Output directory created: {output_dir}")

            # Create checkpoints directory for intermediate data
            checkpoints_dir = project_root / "checkpoints" / protocol_name
            checkpoints_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Checkpoints directory: {checkpoints_dir}")

            # Store output directory in job record
            from app.db import Job
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.output_directory = str(output_dir)
                db.commit()
                logger.info(f"Saved output directory to job record: {output_dir}")

            # Create orchestrator and run extraction
            orchestrator = SequentialOrchestrator(db)

            # Run the async extraction in a new event loop for this process
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                loop.run_until_complete(
                    orchestrator.run_extraction(
                        job_id=UUID(job_id),
                        protocol_id=UUID(protocol_id),
                        pdf_path=Path(pdf_path),
                        resume=resume,
                        output_dir=output_dir,
                    )
                )
                logger.info(f"Extraction completed for job {job_id}")
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"Extraction failed for job {job_id}: {e}", exc_info=True)

            # Mark job as failed in database
            try:
                from app.db import Job

                job = db.query(Job).filter(Job.id == UUID(job_id)).first()
                if job:
                    job.status = "failed"
                    job.error_message = str(e)[:1000]  # Truncate long errors
                    job.completed_at = datetime.utcnow()
                    db.commit()
            except Exception as db_error:
                logger.error(
                    f"Failed to update job status: {type(db_error).__name__}: {db_error}",
                    exc_info=True
                )
                # Attempt rollback to clear transaction state
                try:
                    db.rollback()
                except Exception:
                    pass  # Best effort

            raise
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Worker process error: {e}", exc_info=True)
        sys.exit(1)

    logger.info(f"Extraction worker finished for job {job_id}")
    sys.exit(0)


def spawn_extraction_process(
    job_id: UUID,
    protocol_id: UUID,
    pdf_path: str,
    resume: bool = True,
) -> multiprocessing.Process:
    """
    Spawn extraction in a separate OS process.

    This function returns immediately after starting the subprocess.
    The extraction runs completely independently of the API server.

    Args:
        job_id: UUID of the extraction job
        protocol_id: UUID of the protocol
        pdf_path: Path to the PDF file
        resume: Whether to resume from checkpoint

    Returns:
        The Process object (can be used to check if still running, but
        typically the API just polls the database for status)
    """
    from app.config import settings

    # Use 'spawn' method on macOS to avoid fork issues with async
    # This creates a fresh Python interpreter
    ctx = multiprocessing.get_context('spawn')

    process = ctx.Process(
        target=_run_extraction_in_process,
        args=(
            str(job_id),
            str(protocol_id),
            pdf_path,
            resume,
            settings.database_url,
        ),
        daemon=False,  # Don't kill when parent exits (let extraction complete)
        name=f"extraction-{str(job_id)[:8]}",
    )

    process.start()

    logging.getLogger(__name__).info(
        f"Spawned extraction process {process.pid} for job {job_id}"
    )

    return process


# Registry to track active extraction processes (optional, for monitoring)
_active_processes: dict[str, multiprocessing.Process] = {}


def get_active_extractions() -> dict[str, dict]:
    """
    Get status of active extraction processes.

    Returns:
        Dict mapping job_id to process info
    """
    result = {}
    for job_id, process in list(_active_processes.items()):
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
            # Clean up finished processes
            del _active_processes[job_id]
    return result


def register_extraction_process(job_id: str, process: multiprocessing.Process):
    """Register an extraction process for monitoring."""
    _active_processes[job_id] = process
