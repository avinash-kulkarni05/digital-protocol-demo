"""
Celery tasks for background extraction processing.

Tasks run asynchronously via Redis queue, enabling:
- Non-blocking API responses
- Reliable task execution with retries
- Progress tracking via database events
"""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from app.celery_app import celery_app
from app.db import get_session_factory
from app.services.sequential_orchestrator import SequentialOrchestrator

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run async coroutine in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    name="app.tasks.extraction_tasks.run_extraction_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run_extraction_task(
    self,
    job_id: str,
    protocol_id: str,
    pdf_path: str,
    resume: bool = True,
):
    """
    Run complete extraction pipeline as Celery task.

    Args:
        job_id: Extraction job ID
        protocol_id: Protocol record ID
        pdf_path: Path to PDF file
        resume: Whether to resume from checkpoint

    Returns:
        Extraction summary
    """
    logger.info(f"Starting extraction task for job {job_id}")

    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        orchestrator = SequentialOrchestrator(db)

        # Run async extraction in sync context
        result = run_async(
            orchestrator.run_extraction(
                job_id=UUID(job_id),
                protocol_id=UUID(protocol_id),
                pdf_path=Path(pdf_path),
                resume=resume,
            )
        )

        logger.info(f"Extraction completed for job {job_id}")
        return result

    except Exception as e:
        logger.error(f"Extraction task failed: {e}")

        # Retry on transient errors
        if "rate limit" in str(e).lower() or "timeout" in str(e).lower():
            raise self.retry(exc=e, countdown=120)

        raise

    finally:
        db.close()


@celery_app.task(
    name="app.tasks.extraction_tasks.run_single_module_task",
    bind=True,
)
def run_single_module_task(
    self,
    job_id: str,
    module_id: str,
    gemini_file_uri: str,
    protocol_id: str,
):
    """
    Run extraction for a single module (for testing/debugging).

    Args:
        job_id: Extraction job ID
        module_id: Module to extract
        gemini_file_uri: Cached Gemini file URI
        protocol_id: Protocol identifier

    Returns:
        Module extraction result
    """
    logger.info(f"Starting single module extraction: {module_id}")

    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        orchestrator = SequentialOrchestrator(db)

        result = run_async(
            orchestrator.run_single_module(
                job_id=UUID(job_id),
                module_id=module_id,
                gemini_file_uri=gemini_file_uri,
                protocol_id=protocol_id,
            )
        )

        logger.info(f"Module {module_id} extraction completed")
        return result

    except Exception as e:
        logger.error(f"Module extraction failed: {e}")
        raise

    finally:
        db.close()
