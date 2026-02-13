"""
Parallel orchestrator for wave-based module extraction.

Executes modules in dynamic waves with:
- Configurable parallelism (max_parallel_agents)
- Wave-based execution respecting dependencies
- Quality-based feedback loop for each module
- Checkpoint after each module/wave
- SSE event emission for progress tracking
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.db import Job, Protocol
from app.module_registry import (
    ExtractionModuleConfig,
    get_enabled_modules,
    get_module,
    get_modules_by_wave,
    get_wave_count,
)
from app.services.gemini_file_service import GeminiFileService
from app.services.two_phase_extractor import TwoPhaseExtractor
from app.services.checkpoint_service import CheckpointService
from app.utils.quality_checker import QualityScore

logger = logging.getLogger(__name__)


class ParallelOrchestrator:
    """
    Orchestrates parallel extraction across modules using wave-based execution.

    Execution flow:
    1. Upload PDF to Gemini (or use cached)
    2. For each wave (0, 1, 2, ...):
       a. Get modules in wave
       b. Execute modules in parallel (with max_parallel limit)
       c. Quality check and retry each module
       d. Save checkpoint after wave completes
       e. Emit progress events
    3. Complete job
    """

    def __init__(self, db: Session):
        """
        Initialize orchestrator with dependencies.

        Args:
            db: Database session
        """
        self.db = db
        self.gemini_service = GeminiFileService()
        self.extractor = TwoPhaseExtractor(self.gemini_service)
        self.checkpoint_service = CheckpointService(db)

    async def run_extraction(
        self,
        job_id: UUID,
        protocol_id: UUID,
        pdf_path: Path,
        resume: bool = True,
        parallel: bool = True,
    ) -> Dict[str, Any]:
        """
        Run complete extraction pipeline with parallel wave execution.

        Args:
            job_id: Extraction job ID
            protocol_id: Protocol record ID
            pdf_path: Path to PDF file
            resume: Whether to resume from last checkpoint
            parallel: Whether to run modules in parallel within waves

        Returns:
            Extraction summary with all results
        """
        logger.info(f"Starting parallel extraction for job {job_id}")

        # Get protocol record
        protocol = self.db.query(Protocol).filter(Protocol.id == protocol_id).first()
        if not protocol:
            raise ValueError(f"Protocol not found: {protocol_id}")

        # Start job
        self.checkpoint_service.start_job(job_id)

        try:
            # Upload PDF (or use cached)
            gemini_file_uri, _ = await self.gemini_service.get_or_upload_file(
                file_path=pdf_path,
                db=self.db,
            )
            logger.info(f"Using Gemini file: {gemini_file_uri}")

            # Get pending modules
            if resume:
                completed_modules = set(
                    self.checkpoint_service.get_job_status(job_id).get("completed_modules", [])
                )
            else:
                completed_modules = set()

            # Organize modules by wave
            waves = get_modules_by_wave()
            all_results = []

            for wave_num in sorted(waves.keys()):
                wave_modules = waves[wave_num]

                # Filter out completed modules
                pending_modules = [
                    m for m in wave_modules
                    if m.module_id not in completed_modules
                ]

                if not pending_modules:
                    logger.info(f"Wave {wave_num}: All modules already completed")
                    continue

                logger.info(
                    f"Wave {wave_num}: Starting {len(pending_modules)} modules "
                    f"(parallel={parallel}, max={settings.max_parallel_agents})"
                )

                # Execute wave
                if parallel and len(pending_modules) > 1:
                    wave_results = await self._execute_wave_parallel(
                        job_id=job_id,
                        wave_num=wave_num,
                        modules=pending_modules,
                        gemini_file_uri=gemini_file_uri,
                        protocol_id=protocol.filename.replace(".pdf", ""),
                    )
                else:
                    wave_results = await self._execute_wave_sequential(
                        job_id=job_id,
                        wave_num=wave_num,
                        modules=pending_modules,
                        gemini_file_uri=gemini_file_uri,
                        protocol_id=protocol.filename.replace(".pdf", ""),
                    )

                all_results.extend(wave_results)
                logger.info(f"Wave {wave_num}: Completed with {len(wave_results)} results")

            # Complete job
            failed_modules = self.checkpoint_service.get_job_status(job_id).get(
                "failed_modules", []
            )
            if failed_modules:
                self.checkpoint_service.complete_job(
                    job_id=job_id,
                    status="completed_with_errors",
                    error_message=f"Failed modules: {', '.join(failed_modules)}",
                )
            else:
                self.checkpoint_service.complete_job(job_id=job_id, status="completed")

            # Save final checkpoint file
            self.checkpoint_service.save_checkpoint_file(job_id)

            # Generate summary
            return self._generate_summary(job_id, all_results)

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            self.checkpoint_service.complete_job(
                job_id=job_id,
                status="failed",
                error_message=str(e),
            )
            raise

    async def _execute_wave_parallel(
        self,
        job_id: UUID,
        wave_num: int,
        modules: List[ExtractionModuleConfig],
        gemini_file_uri: str,
        protocol_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Execute modules in a wave with parallel execution.

        Uses semaphore to limit concurrency.
        """
        semaphore = asyncio.Semaphore(settings.max_parallel_agents)
        results = []

        async def extract_with_semaphore(module: ExtractionModuleConfig) -> Dict[str, Any]:
            async with semaphore:
                # Stagger start to avoid rate limits
                await asyncio.sleep(settings.wave_stagger_delay)
                return await self._extract_module_with_quality(
                    job_id=job_id,
                    module=module,
                    gemini_file_uri=gemini_file_uri,
                    protocol_id=protocol_id,
                )

        # Create tasks for all modules
        tasks = [extract_with_semaphore(m) for m in modules]

        # Execute with error handling
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for module, result in zip(modules, task_results):
            if isinstance(result, Exception):
                logger.error(f"Module {module.module_id} failed: {result}")
                # Save failed result
                self.checkpoint_service.save_module_result(
                    job_id=job_id,
                    module_id=module.module_id,
                    status="failed",
                    extracted_data={},
                    provenance_coverage=0.0,
                    pass1_duration=0.0,
                    pass2_duration=0.0,
                    error_details={"error": str(result)},
                )
            else:
                results.append(result)

        return results

    async def _execute_wave_sequential(
        self,
        job_id: UUID,
        wave_num: int,
        modules: List[ExtractionModuleConfig],
        gemini_file_uri: str,
        protocol_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Execute modules in a wave sequentially.

        Fallback when parallel=False or single module in wave.
        """
        results = []

        for module in modules:
            try:
                result = await self._extract_module_with_quality(
                    job_id=job_id,
                    module=module,
                    gemini_file_uri=gemini_file_uri,
                    protocol_id=protocol_id,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Module {module.module_id} failed: {e}")
                # Save failed result
                self.checkpoint_service.save_module_result(
                    job_id=job_id,
                    module_id=module.module_id,
                    status="failed",
                    extracted_data={},
                    provenance_coverage=0.0,
                    pass1_duration=0.0,
                    pass2_duration=0.0,
                    error_details={"error": str(e)},
                )
                # Continue with next module (resilient execution)

        return results

    async def _extract_module_with_quality(
        self,
        job_id: UUID,
        module: ExtractionModuleConfig,
        gemini_file_uri: str,
        protocol_id: str,
    ) -> Dict[str, Any]:
        """
        Extract a single module with quality-based feedback.

        Uses the new extract_with_quality_feedback method.
        """
        logger.info(f"Extracting module: {module.display_name}")

        # Update current module in job
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.current_module = module.module_id
            self.db.commit()

        # Execute extraction with quality feedback
        result, quality = await self.extractor.extract_with_quality_feedback(
            module_id=module.module_id,
            gemini_file_uri=gemini_file_uri,
            protocol_id=protocol_id,
        )

        # Calculate provenance coverage from quality score
        coverage = quality.provenance if quality else 0.0

        # Save result with quality metrics
        self.checkpoint_service.save_module_result(
            job_id=job_id,
            module_id=module.module_id,
            status="completed",
            extracted_data=result.get("extracted_data", {}),
            provenance_coverage=coverage,
            pass1_duration=result.get("pass1_duration_seconds", 0.0),
            pass2_duration=result.get("pass2_duration_seconds", 0.0),
            quality_score=quality.to_dict() if quality else None,
        )

        return result

    def _generate_summary(
        self,
        job_id: UUID,
        results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Generate extraction summary.

        Args:
            job_id: Job ID
            results: List of module results

        Returns:
            Summary dictionary
        """
        status = self.checkpoint_service.get_job_status(job_id)

        total_pass1_time = sum(r.get("pass1_duration_seconds", 0) for r in results)
        total_pass2_time = sum(r.get("pass2_duration_seconds", 0) for r in results)

        module_results = self.checkpoint_service.get_module_results(job_id)
        avg_coverage = (
            sum(r["provenance_coverage"] for r in module_results) / len(module_results)
            if module_results
            else 0.0
        )

        # Calculate average quality scores
        quality_scores = [
            r.get("quality_score", {})
            for r in results
            if r.get("quality_score")
        ]
        avg_accuracy = sum(q.get("accuracy", 0) for q in quality_scores) / len(quality_scores) if quality_scores else 0
        avg_completeness = sum(q.get("completeness", 0) for q in quality_scores) / len(quality_scores) if quality_scores else 0
        avg_compliance = sum(q.get("compliance", 0) for q in quality_scores) / len(quality_scores) if quality_scores else 0

        return {
            "job_id": str(job_id),
            "status": status["status"],
            "modules_completed": len(status.get("completed_modules", [])),
            "modules_failed": len(status.get("failed_modules", [])),
            "modules_total": status["progress"]["total"],
            "wave_count": get_wave_count(),
            "quality_metrics": {
                "average_accuracy": f"{avg_accuracy:.1%}",
                "average_completeness": f"{avg_completeness:.1%}",
                "average_compliance": f"{avg_compliance:.1%}",
                "average_provenance_coverage": f"{avg_coverage:.1%}",
            },
            "total_pass1_duration_seconds": total_pass1_time,
            "total_pass2_duration_seconds": total_pass2_time,
            "total_duration_seconds": total_pass1_time + total_pass2_time,
            "completed_at": status.get("completed_at"),
        }

    async def run_single_module(
        self,
        job_id: UUID,
        module_id: str,
        gemini_file_uri: str,
        protocol_id: str,
    ) -> Tuple[Dict[str, Any], QualityScore]:
        """
        Run extraction for a single module with quality feedback.

        Args:
            job_id: Job ID
            module_id: Module to extract
            gemini_file_uri: Gemini file URI
            protocol_id: Protocol identifier

        Returns:
            Tuple of (result, quality_score)
        """
        module = get_module(module_id)
        if not module:
            raise ValueError(f"Unknown module: {module_id}")

        result = await self._extract_module_with_quality(
            job_id=job_id,
            module=module,
            gemini_file_uri=gemini_file_uri,
            protocol_id=protocol_id,
        )

        # Get quality from result
        quality_dict = result.get("quality_score", {})
        quality = QualityScore(
            accuracy=quality_dict.get("accuracy", 0),
            completeness=quality_dict.get("completeness", 0),
            compliance=quality_dict.get("compliance", 0),
            provenance=quality_dict.get("provenance", 0),
        )

        return result, quality

    def get_extraction_progress(self, job_id: UUID) -> Dict[str, Any]:
        """
        Get current extraction progress with wave information.

        Args:
            job_id: Job ID

        Returns:
            Progress dictionary with wave details
        """
        status = self.checkpoint_service.get_job_status(job_id)

        # Add wave information
        waves = get_modules_by_wave()
        completed_modules = set(status.get("completed_modules", []))

        wave_progress = {}
        for wave_num, modules in waves.items():
            wave_completed = sum(1 for m in modules if m.module_id in completed_modules)
            wave_progress[f"wave_{wave_num}"] = {
                "total": len(modules),
                "completed": wave_completed,
                "modules": [m.module_id for m in modules],
            }

        status["wave_progress"] = wave_progress
        return status
