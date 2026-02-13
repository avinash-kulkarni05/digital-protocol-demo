"""
Checkpoint service for extraction state persistence and resumption.

Enables:
- Save state after each module completes
- Resume from last successful module on failure
- Track progress across extraction runs
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, PendingRollbackError
from sqlalchemy import text

from app.config import settings
from app.db import Job, ModuleResult, JobEvent, Protocol
from app.module_registry import get_module_ids

logger = logging.getLogger(__name__)

MAX_DB_RETRIES = 3
DB_RETRY_DELAY = 1.0  # seconds


class CheckpointService:
    """
    Service for managing extraction checkpoints.

    Checkpoints are stored in the database for persistence across restarts.
    Local JSON files provide quick access for debugging.
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def _safe_rollback(self):
        """Safely rollback the session, handling any errors."""
        try:
            self.db.rollback()
        except Exception as e:
            logger.warning(f"Rollback failed: {e}")

    def _reconnect_if_needed(self):
        """Try to reconnect the session if connection is broken."""
        try:
            # Try a simple query to test connection
            self.db.execute(text("SELECT 1"))
            self.db.commit()  # Commit test transaction to clear state
        except (OperationalError, PendingRollbackError):
            logger.warning("Database connection issue detected, rolling back...")
            self._safe_rollback()
            # Connection pool will provide new connection on next use

    def create_job(
        self,
        protocol_id: UUID,
        total_modules: Optional[int] = None,
    ) -> Job:
        """
        Create a new extraction job.

        Args:
            protocol_id: ID of protocol being extracted
            total_modules: Total number of modules (default: all enabled)

        Returns:
            Created job record
        """
        from app.module_registry import get_total_modules

        # Get protocol_name from protocol record
        protocol = self.db.query(Protocol).filter(Protocol.id == protocol_id).first()
        protocol_name = protocol.protocol_name if protocol else None

        job = Job(
            protocol_id=protocol_id,
            protocol_name=protocol_name,
            status="pending",
            total_modules=total_modules or get_total_modules(),
            completed_modules=[],
            failed_modules=[],
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        logger.info(f"Created extraction job: {job.id} for protocol: {protocol_name}")
        return job

    def start_job(self, job_id: UUID) -> Job:
        """
        Mark job as started.

        Args:
            job_id: ID of job to start

        Returns:
            Updated job record
        """
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        job.status = "running"
        job.started_at = datetime.utcnow()
        self.db.commit()

        self._emit_event(job_id, "job_started", None, {"status": "running"})
        return job

    def save_module_result(
        self,
        job_id: UUID,
        module_id: str,
        status: str,
        extracted_data: Dict[str, Any],
        provenance_coverage: float,
        pass1_duration: float,
        pass2_duration: float,
        quality_scores: Optional[Dict[str, Any]] = None,
        from_cache: bool = False,
        error_details: Optional[Dict[str, Any]] = None,
    ) -> ModuleResult:
        """
        Save result for a completed module.

        Args:
            job_id: Job ID
            module_id: Module ID
            status: "completed" or "failed"
            extracted_data: Extracted data with provenance
            provenance_coverage: Coverage percentage (0.0 to 1.0)
            pass1_duration: Pass 1 duration in seconds
            pass2_duration: Pass 2 duration in seconds
            quality_scores: Full 5D quality scores (accuracy, completeness, etc.)
            from_cache: Whether result was retrieved from cache
            error_details: Error details if failed

        Returns:
            Saved module result record
        """
        last_error = None
        for attempt in range(MAX_DB_RETRIES):
            try:
                # Reconnect if needed before operation
                if attempt > 0:
                    self._reconnect_if_needed()
                    logger.info(f"DB retry attempt {attempt + 1}/{MAX_DB_RETRIES} for {module_id}")

                # Check for existing result (for retries)
                existing = self.db.query(ModuleResult).filter(
                    ModuleResult.job_id == job_id,
                    ModuleResult.module_id == module_id,
                ).first()

                # Get protocol_name from job
                job = self.db.query(Job).filter(Job.id == job_id).first()
                protocol_name = job.protocol_name if job else None

                if existing:
                    existing.status = status
                    existing.extracted_data = extracted_data
                    existing.provenance_coverage = provenance_coverage
                    existing.pass1_duration_seconds = pass1_duration
                    existing.pass2_duration_seconds = pass2_duration
                    existing.quality_scores = quality_scores
                    existing.from_cache = from_cache
                    existing.error_details = error_details
                    existing.retry_count += 1
                    if existing.protocol_name is None:
                        existing.protocol_name = protocol_name
                    result = existing
                else:
                    result = ModuleResult(
                        job_id=job_id,
                        protocol_name=protocol_name,
                        module_id=module_id,
                        status=status,
                        extracted_data=extracted_data,
                        provenance_coverage=provenance_coverage,
                        pass1_duration_seconds=pass1_duration,
                        pass2_duration_seconds=pass2_duration,
                        quality_scores=quality_scores,
                        from_cache=from_cache,
                        error_details=error_details,
                    )
                    self.db.add(result)

                # Update job progress
                job = self.db.query(Job).filter(Job.id == job_id).first()
                if job:
                    if status == "completed":
                        completed = list(job.completed_modules or [])
                        if module_id not in completed:
                            completed.append(module_id)
                            job.completed_modules = completed
                    elif status == "failed":
                        failed = list(job.failed_modules or [])
                        if module_id not in failed:
                            failed.append(module_id)
                            job.failed_modules = failed

                    job.current_module = module_id

                self.db.commit()
                self.db.refresh(result)

                # Emit event
                self._emit_event(
                    job_id,
                    f"module_{status}",
                    module_id,
                    {
                        "provenance_coverage": provenance_coverage,
                        "duration": pass1_duration + pass2_duration,
                    },
                )

                logger.info(
                    f"Saved {status} result for {module_id} "
                    f"(coverage: {provenance_coverage:.1%})"
                )
                return result

            except (OperationalError, PendingRollbackError) as e:
                last_error = e
                logger.warning(
                    f"DB error saving {module_id} (attempt {attempt + 1}/{MAX_DB_RETRIES}): "
                    f"{type(e).__name__}: {str(e)[:200]}"
                )
                self._safe_rollback()

                if attempt < MAX_DB_RETRIES - 1:
                    backoff_delay = DB_RETRY_DELAY * (attempt + 1)
                    logger.info(f"Retrying in {backoff_delay}s...")
                    time.sleep(backoff_delay)
                else:
                    logger.error(f"All {MAX_DB_RETRIES} retry attempts exhausted for {module_id}")

        # All retries failed
        logger.error(f"Failed to save {module_id} after {MAX_DB_RETRIES} attempts: {type(last_error).__name__}: {last_error}")
        raise last_error

    def get_pending_modules(self, job_id: UUID) -> List[str]:
        """
        Get list of modules not yet completed.

        Args:
            job_id: Job ID

        Returns:
            List of pending module IDs in execution order
        """
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return get_module_ids()

        completed = set(job.completed_modules or [])
        all_modules = get_module_ids()

        return [m for m in all_modules if m not in completed]

    def get_completed_modules(self, job_id: UUID) -> List[str]:
        """
        Get list of completed modules.

        Args:
            job_id: Job ID

        Returns:
            List of completed module IDs
        """
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return []

        return list(job.completed_modules or [])

    def complete_job(
        self,
        job_id: UUID,
        status: str = "completed",
        error_message: Optional[str] = None,
    ) -> Job:
        """
        Mark job as completed or failed.

        Args:
            job_id: Job ID
            status: Final status ("completed" or "failed")
            error_message: Error message if failed

        Returns:
            Updated job record
        """
        last_error = None
        for attempt in range(MAX_DB_RETRIES):
            try:
                if attempt > 0:
                    self._reconnect_if_needed()
                    logger.info(f"DB retry attempt {attempt + 1}/{MAX_DB_RETRIES} for complete_job")

                job = self.db.query(Job).filter(Job.id == job_id).first()
                if not job:
                    raise ValueError(f"Job not found: {job_id}")

                job.status = status
                job.completed_at = datetime.utcnow()
                job.error_message = error_message
                job.current_module = None

                self.db.commit()

                self._emit_event(
                    job_id,
                    f"job_{status}",
                    None,
                    {"error": error_message} if error_message else None,
                )

                logger.info(f"Job {job_id} marked as {status}")
                return job

            except (OperationalError, PendingRollbackError) as e:
                last_error = e
                logger.warning(
                    f"DB error completing job (attempt {attempt + 1}/{MAX_DB_RETRIES}): "
                    f"{type(e).__name__}: {str(e)[:200]}"
                )
                self._safe_rollback()

                if attempt < MAX_DB_RETRIES - 1:
                    backoff_delay = DB_RETRY_DELAY * (attempt + 1)
                    logger.info(f"Retrying in {backoff_delay}s...")
                    time.sleep(backoff_delay)
                else:
                    logger.error(f"All {MAX_DB_RETRIES} retry attempts exhausted for complete_job")

        logger.error(f"Failed to complete job after {MAX_DB_RETRIES} attempts: {type(last_error).__name__}: {last_error}")
        raise last_error

    def get_job_status(self, job_id: UUID) -> Dict[str, Any]:
        """
        Get comprehensive job status.

        Args:
            job_id: Job ID

        Returns:
            Status dictionary with progress info
        """
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        completed = len(job.completed_modules or [])
        failed = len(job.failed_modules or [])

        return {
            "job_id": str(job.id),
            "protocol_id": str(job.protocol_id),
            "status": job.status,
            "current_module": job.current_module,
            "completed_modules": job.completed_modules,
            "failed_modules": job.failed_modules,
            "progress": {
                "completed": completed,
                "failed": failed,
                "total": job.total_modules,
                "percentage": (completed / job.total_modules * 100)
                if job.total_modules > 0
                else 0,
            },
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error_message": job.error_message,
        }

    def get_module_results(self, job_id: UUID) -> List[Dict[str, Any]]:
        """
        Get all module results for a job.

        Args:
            job_id: Job ID

        Returns:
            List of module results with extracted data and quality scores
        """
        results = self.db.query(ModuleResult).filter(
            ModuleResult.job_id == job_id
        ).all()

        return [
            {
                "module_id": r.module_id,
                "status": r.status,
                "extracted_data": r.extracted_data,  # CRITICAL: Include the actual extracted data
                "provenance_coverage": r.provenance_coverage,
                "quality_scores": r.quality_scores,  # Full 5D quality scores
                "from_cache": r.from_cache,
                "pass1_duration": r.pass1_duration_seconds,
                "pass2_duration": r.pass2_duration_seconds,
                "retry_count": r.retry_count,
            }
            for r in results
        ]

    def save_checkpoint_file(
        self,
        job_id: UUID,
        output_dir: Optional[Path] = None,
    ) -> Path:
        """
        Save checkpoint to JSON file for debugging/backup.

        Args:
            job_id: Job ID
            output_dir: Output directory (default: outputs/)

        Returns:
            Path to saved checkpoint file
        """
        output_dir = output_dir or settings.outputs_dir
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        checkpoint_path = output_dir / f"checkpoint_{job_id}.json"

        status = self.get_job_status(job_id)
        results = self.get_module_results(job_id)

        checkpoint = {
            "job": status,
            "module_results": results,
            "saved_at": datetime.utcnow().isoformat(),
        }

        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint, f, indent=2)

        logger.info(f"Saved checkpoint to {checkpoint_path}")
        return checkpoint_path

    def _emit_event(
        self,
        job_id: UUID,
        event_type: str,
        module_id: Optional[str],
        payload: Optional[Dict[str, Any]],
    ):
        """Emit job event for SSE streaming."""
        # Get protocol_name from job
        job = self.db.query(Job).filter(Job.id == job_id).first()
        protocol_name = job.protocol_name if job else None

        event = JobEvent(
            job_id=job_id,
            protocol_name=protocol_name,
            event_type=event_type,
            module_id=module_id,
            payload=payload,
        )
        self.db.add(event)
        self.db.commit()
