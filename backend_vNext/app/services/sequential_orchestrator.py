"""
Sequential orchestrator for module-by-module extraction.

Executes 10 modules in order with:
- Two-phase extraction per module
- Checkpoint after each module
- Resumption from last completed module
- SSE event emission for progress tracking
- Intermediate stage storage (like SOA pipeline)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.db import Job, Protocol
from app.module_registry import get_enabled_modules, get_module
from app.services.gemini_file_service import GeminiFileService
from app.services.two_phase_extractor import TwoPhaseExtractor
from app.services.checkpoint_service import CheckpointService
from app.services.usdm_sync_service import UsdmSyncService
from app.services.usdm_combiner import USDMCombiner

logger = logging.getLogger(__name__)


class SequentialOrchestrator:
    """
    Orchestrates sequential extraction across all modules.

    Execution flow:
    1. Upload PDF to Gemini (or use cached)
    2. For each module in order:
       a. Execute Pass 1 (values)
       b. Execute Pass 2 (provenance)
       c. Validate and save checkpoint
       d. Emit progress event
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
        output_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Run complete extraction pipeline.

        Args:
            job_id: Extraction job ID
            protocol_id: Protocol record ID
            pdf_path: Path to PDF file
            resume: Whether to resume from last checkpoint
            output_dir: Optional output directory for intermediate stages

        Returns:
            Extraction summary with all results
        """
        logger.info(f"Starting extraction for job {job_id}")

        # Create intermediate stages directory if output_dir provided
        intermediate_dir = None
        if output_dir:
            intermediate_dir = output_dir / "intermediate_stages"
            intermediate_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created intermediate stages directory: {intermediate_dir}")

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

            # Get modules to process
            if resume:
                pending_modules = self.checkpoint_service.get_pending_modules(job_id)
            else:
                pending_modules = [m.module_id for m in get_enabled_modules()]

            logger.info(f"Processing {len(pending_modules)} modules")

            # Extract each module sequentially
            results = []
            for module_id in pending_modules:
                try:
                    result = await self._extract_module(
                        job_id=job_id,
                        module_id=module_id,
                        gemini_file_uri=gemini_file_uri,
                        protocol_id=protocol.filename.replace(".pdf", ""),
                        protocol_uuid=protocol_id,  # Pass UUID for cache linking
                        pdf_path=pdf_path,  # Pass PDF path for cache key (same as main.py)
                        intermediate_dir=intermediate_dir,
                        use_cache=True,  # Enable caching (same as main.py default)
                    )
                    results.append(result)
                except Exception as e:
                    logger.error(f"Module {module_id} failed: {e}")
                    # Save failed result
                    self.checkpoint_service.save_module_result(
                        job_id=job_id,
                        module_id=module_id,
                        status="failed",
                        extracted_data={},
                        provenance_coverage=0.0,
                        pass1_duration=0.0,
                        pass2_duration=0.0,
                        error_details={"error": str(e)},
                    )
                    # Continue with next module (resilient execution)

            # Complete job
            failed_modules = self.checkpoint_service.get_job_status(job_id).get(
                "failed_modules", []
            )

            # Build USDM 4.0 document from module results (even if some modules failed)
            logger.info(f"Building USDM 4.0 document from extraction results...")
            usdm_document = self._build_usdm_document(job_id)

            if failed_modules:
                self.checkpoint_service.complete_job(
                    job_id=job_id,
                    status="completed_with_errors",
                    error_message=f"Failed modules: {', '.join(failed_modules)}",
                )
                # Save partial USDM even with errors
                if usdm_document:
                    protocol.usdm_json = usdm_document
                    protocol.extraction_status = "completed_with_errors"
                    self.db.commit()
                    logger.info(f"Saved partial USDM data to protocol {protocol_id} (some modules failed)")
            else:
                self.checkpoint_service.complete_job(job_id=job_id, status="completed")

                # Save USDM JSON to protocol record for frontend display
                if usdm_document:
                    protocol.usdm_json = usdm_document
                    protocol.extraction_status = "completed"
                    self.db.commit()
                    logger.info(f"Saved USDM data to protocol {protocol_id}")

                # Sync extraction results to usdm_documents table (for frontend review)
                logger.info(f"Syncing extraction results to usdm_documents table...")
                sync_service = UsdmSyncService(self.db)
                sync_success = sync_service.sync_to_usdm_documents(protocol_id, job_id)
                if sync_success:
                    logger.info(f"Successfully synced to usdm_documents")
                else:
                    logger.warning(f"Failed to sync to usdm_documents (non-fatal)")

            # Save final checkpoint file
            self.checkpoint_service.save_checkpoint_file(job_id)

            # Generate annotated PDF (if enabled in config)
            if output_dir and usdm_document:
                # Write PDF from database to temp file for annotation
                import tempfile
                pdf_temp_path = Path(tempfile.gettempdir()) / f"{protocol.filename}"
                if protocol.file_data:
                    with open(pdf_temp_path, 'wb') as f:
                        f.write(protocol.file_data)
                    logger.info(f"Wrote PDF to temp file: {pdf_temp_path}")

                    # Generate annotated PDF with provenance highlights
                    annotation_result = await self._generate_annotated_pdf(
                        job_id=job_id,
                        protocol_id=protocol_id,
                        pdf_path=pdf_temp_path,
                        usdm_document=usdm_document,
                        output_dir=output_dir
                    )
                else:
                    logger.warning(f"No PDF binary data in protocol {protocol_id}, skipping annotation")

            # Collect and save output file paths to database
            if output_dir:
                self._save_output_files_to_db(job_id, output_dir)

            # Generate summary
            return self._generate_summary(job_id, results)

        except Exception as e:
            logger.error(f"Extraction failed: {e}", exc_info=True)

            # Try to save partial USDM from any completed modules before failing
            try:
                logger.info("Attempting to save partial extraction results...")
                usdm_document = self._build_usdm_document(job_id)
                if usdm_document and protocol:
                    protocol.usdm_json = usdm_document
                    protocol.extraction_status = "failed"
                    self.db.commit()
                    logger.info(f"Saved partial USDM data to protocol {protocol_id}")
            except Exception as save_error:
                logger.warning(f"Could not save partial results: {save_error}")

            self.checkpoint_service.complete_job(
                job_id=job_id,
                status="failed",
                error_message=str(e),
            )
            raise

    async def _extract_module(
        self,
        job_id: UUID,
        module_id: str,
        gemini_file_uri: str,
        protocol_id: str,
        protocol_uuid: UUID,
        pdf_path: Path,
        intermediate_dir: Optional[Path] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Extract a single module with checkpointing.

        Uses extract_with_cache (same as main.py CLI) to ensure consistent
        extraction results between API and CLI paths.

        Args:
            job_id: Job ID
            module_id: Module to extract
            gemini_file_uri: Gemini file URI
            protocol_id: Protocol identifier (filename stem)
            protocol_uuid: Protocol UUID for database linking
            pdf_path: Path to PDF file (for cache key)
            intermediate_dir: Optional directory to save intermediate stages
            use_cache: Whether to use extraction cache (default: True)

        Returns:
            Extraction result with quality scores
        """
        import time
        module = get_module(module_id)
        logger.info(f"Extracting module: {module.display_name}")

        # Update current module
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.current_module = module_id
            self.db.commit()

        module_start = time.time()

        # Execute extraction with cache - SAME as main.py
        # This ensures consistent results between API and CLI
        result, quality, from_cache = await self.extractor.extract_with_cache(
            module_id=module_id,
            gemini_file_uri=gemini_file_uri,
            protocol_id=protocol_id,
            pdf_path=str(pdf_path),
            model_name=settings.gemini_model or "gemini-2.5-pro",
            use_cache=use_cache,
            max_retries=settings.max_retries,
            protocol_uuid=protocol_uuid,
        )

        module_duration = time.time() - module_start
        cache_status = "CACHE HIT" if from_cache else "EXTRACTED"
        logger.info(f"[{module_id}] {cache_status} in {module_duration:.2f}s")
        logger.info(f"[{module_id}] Quality: {quality.overall_score:.1%}")

        # Build quality scores dict - SAME format as main.py
        quality_scores = {
            "accuracy": quality.accuracy,
            "completeness": quality.completeness,
            "usdm_adherence": quality.usdm_adherence,
            "provenance": quality.provenance,
            "terminology": quality.terminology,
            "overall": quality.overall_score,
            "from_cache": from_cache,
            "duration_seconds": module_duration,
        }

        # Save result to database
        # Extract metadata and actual data separately
        metadata = result.get("_metadata", {})
        extracted_data = {k: v for k, v in result.items() if k != "_metadata"}

        self.checkpoint_service.save_module_result(
            job_id=job_id,
            module_id=module_id,
            status="completed",
            extracted_data=extracted_data,  # The actual extracted data (without _metadata)
            provenance_coverage=quality.provenance,  # Use quality.provenance for coverage
            pass1_duration=metadata.get("pass1_duration_seconds", 0.0),
            pass2_duration=metadata.get("pass2_duration_seconds", 0.0),
            quality_scores=quality_scores,  # Full 5D quality scores
            from_cache=from_cache,
        )

        # Save intermediate stage to filesystem (if output_dir provided)
        if intermediate_dir:
            self._save_intermediate_stage(
                intermediate_dir=intermediate_dir,
                module_id=module_id,
                module_display_name=module.display_name,
                result=result,
                coverage=quality.provenance,
                protocol_id=protocol_id,
                quality_scores=quality_scores,
            )

        return result

    def _save_intermediate_stage(
        self,
        intermediate_dir: Path,
        module_id: str,
        module_display_name: str,
        result: Dict[str, Any],
        coverage: float,
        protocol_id: str,
        quality_scores: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Save intermediate extraction stage to filesystem.

        Similar to SOA pipeline's intermediate stage storage pattern.

        Args:
            intermediate_dir: Directory to save stage files
            module_id: Module identifier
            module_display_name: Human-readable module name
            result: Extraction result with metadata
            coverage: Provenance coverage score
            protocol_id: Protocol identifier
            quality_scores: Full 5D quality scores (same as main.py)
        """
        try:
            # Extract metadata from result
            metadata = result.get("_metadata", {})
            pass1_duration = metadata.get("pass1_duration_seconds", 0.0)
            pass2_duration = metadata.get("pass2_duration_seconds", 0.0)
            pass2_skipped = metadata.get("pass2_skipped", False)

            # Get extracted data (without metadata)
            extracted_data = {k: v for k, v in result.items() if k != "_metadata"}

            # Build stage data structure
            stage_data = {
                "module_id": module_id,
                "module_name": module_display_name,
                "protocol_id": protocol_id,
                "timestamp": datetime.utcnow().isoformat(),
                "success": True,
                "metrics": {
                    "provenance_coverage": round(coverage, 4),
                    "pass1_duration_seconds": round(pass1_duration, 2),
                    "pass2_duration_seconds": round(pass2_duration, 2),
                    "total_duration_seconds": round(pass1_duration + pass2_duration, 2),
                    "pass2_skipped": pass2_skipped,
                },
                "quality_scores": quality_scores,  # Full 5D quality scores (same as main.py)
                "extracted_data": extracted_data,
            }

            # Save to file
            stage_file = intermediate_dir / f"{module_id}.json"
            with open(stage_file, "w") as f:
                json.dump(stage_data, f, indent=2, default=str)

            logger.info(f"Saved intermediate stage: {stage_file.name}")

        except Exception as e:
            logger.warning(f"Failed to save intermediate stage for {module_id}: {e}")
            # Don't fail extraction if intermediate save fails

    async def _generate_annotated_pdf(
        self,
        job_id: UUID,
        protocol_id: UUID,
        pdf_path: Path,
        usdm_document: dict,
        output_dir: Path
    ) -> Optional[Any]:
        """Generate annotated PDF with provenance highlights."""
        try:
            from app.services.pdf_annotation import PDFAnnotatorService
            from app.module_registry import get_config_yaml_path
            import yaml

            config_path = get_config_yaml_path()
            with open(config_path, 'r') as f:
                full_config = yaml.safe_load(f)
            annotation_config = full_config.get("annotation", {})

            if not annotation_config.get("enabled", True):
                logger.info("PDF annotation disabled in config.yaml")
                return None

            logger.info("Generating annotated PDF with provenance highlights")
            annotator = PDFAnnotatorService(config=annotation_config)

            protocol_name = pdf_path.stem
            annotation_result = annotator.annotate(
                pdf_path=pdf_path,
                usdm_json=usdm_document,
                output_dir=output_dir,
                protocol_id=protocol_name
            )

            if annotation_result.success:
                logger.info(f"Annotated PDF created: {annotation_result.annotated_pdf_path}")
            else:
                logger.warning(f"PDF annotation failed: {annotation_result.error}")

            return annotation_result

        except Exception as e:
            logger.error(f"PDF annotation failed (non-blocking): {e}", exc_info=True)
            return None

    def _save_output_files_to_db(
        self,
        job_id: UUID,
        output_dir: Path,
    ) -> None:
        """Save all output files to extraction_outputs table with binaries."""
        try:
            from app.db import ExtractionOutput
            import json

            job = self.db.query(Job).filter(Job.id == job_id).first()
            if not job:
                logger.warning(f"Job {job_id} not found")
                return

            protocol_id = job.protocol_id

            # File type mappings
            file_mappings = {
                "_usdm_4.0.json": ("usdm_json", "application/json"),
                "_extraction_results.json": ("extraction_results", "application/json"),
                "_quality_report.json": ("quality_report", "application/json"),
                "_annotated.pdf": ("annotated_pdf", "application/pdf"),
                "_annotation_report.json": ("annotation_report", "application/json"),
            }

            saved_count = 0

            for file_path in output_dir.glob("*"):
                if file_path.is_dir():
                    continue

                # Match file type
                file_type = None
                content_type = None
                for pattern, (ftype, ctype) in file_mappings.items():
                    if pattern in file_path.name:
                        file_type = ftype
                        content_type = ctype
                        break

                if not file_type:
                    continue

                file_size = file_path.stat().st_size

                # Read file
                if content_type == "application/pdf":
                    with open(file_path, "rb") as f:
                        file_data = f.read()
                    json_data = None
                else:
                    with open(file_path, "r") as f:
                        json_data = json.load(f)
                    file_data = None

                # Upsert
                existing = self.db.query(ExtractionOutput).filter(
                    ExtractionOutput.job_id == job_id,
                    ExtractionOutput.file_type == file_type
                ).first()

                if existing:
                    existing.file_name = file_path.name
                    existing.file_data = file_data
                    existing.json_data = json_data
                    existing.file_size = file_size
                    existing.content_type = content_type
                else:
                    output = ExtractionOutput(
                        job_id=job_id,
                        protocol_id=protocol_id,
                        file_type=file_type,
                        file_name=file_path.name,
                        file_data=file_data,
                        json_data=json_data,
                        file_size=file_size,
                        content_type=content_type
                    )
                    self.db.add(output)

                saved_count += 1
                logger.info(f"Saved {file_type} to database ({file_size} bytes)")

            self.db.commit()
            logger.info(f"Saved {saved_count} output files to database")

        except Exception as e:
            logger.error(f"Failed to save output files: {e}", exc_info=True)
            self.db.rollback()

    def _build_usdm_document(self, job_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Build USDM 4.0 document from all module results using USDMCombiner.

        Uses the same quality_report format as main.py to ensure consistent
        USDM output between API and CLI paths.

        Args:
            job_id: Job ID

        Returns:
            Complete USDM 4.0 document or None if build fails
        """
        try:
            # Get all completed module results
            module_results = self.checkpoint_service.get_module_results(job_id)

            if not module_results:
                logger.warning(f"No module results found for job {job_id}")
                return None

            # Convert module results to format expected by USDMCombiner
            # USDMCombiner expects: {module_id: extracted_data}
            # quality_report format (same as main.py): {module_id: {accuracy, completeness, ...}}
            agent_results = {}
            quality_report = {}

            for result in module_results:
                if result.get("status") == "completed" and result.get("extracted_data"):
                    module_id = result.get("module_id")
                    agent_results[module_id] = result["extracted_data"]
                    # Use quality_scores (full 5D scores) - same format as main.py
                    if result.get("quality_scores"):
                        quality_report[module_id] = result["quality_scores"]

            if not agent_results:
                logger.warning(f"No completed extractions for job {job_id}")
                return None

            # Get PDF path from job/protocol for sourceDocument metadata
            job = self.db.query(Job).filter(Job.id == job_id).first()
            protocol = self.db.query(Protocol).filter(Protocol.id == job.protocol_id).first()
            pdf_path = protocol.filename or f"protocol_{protocol.id}.pdf"

            # Use USDMCombiner for proper USDM 4.0 structure
            # Pass quality_report with full 5D scores (same as main.py)
            combiner = USDMCombiner()
            usdm_document = combiner.combine(
                agent_results=agent_results,
                pdf_path=pdf_path,
                model_name=settings.gemini_model or "gemini-2.5-pro",
                quality_report=quality_report if quality_report else None,
            )

            logger.info(f"Built USDM 4.0 document with {len(agent_results)} modules")
            return usdm_document

        except Exception as e:
            logger.error(f"Failed to build USDM document: {e}", exc_info=True)
            return None

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

        return {
            "job_id": str(job_id),
            "status": status["status"],
            "modules_completed": len(status.get("completed_modules", [])),
            "modules_failed": len(status.get("failed_modules", [])),
            "modules_total": status["progress"]["total"],
            "average_provenance_coverage": f"{avg_coverage:.1%}",
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
        protocol_uuid: UUID,
        pdf_path: Path,
        intermediate_dir: Optional[Path] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Run extraction for a single module (for testing/debugging).

        Args:
            job_id: Job ID
            module_id: Module to extract
            gemini_file_uri: Gemini file URI
            protocol_id: Protocol identifier (filename stem)
            protocol_uuid: Protocol UUID for database linking
            pdf_path: Path to PDF file (for cache key)
            intermediate_dir: Optional directory to save intermediate stages
            use_cache: Whether to use extraction cache (default: True)

        Returns:
            Module extraction result
        """
        return await self._extract_module(
            job_id=job_id,
            module_id=module_id,
            gemini_file_uri=gemini_file_uri,
            protocol_id=protocol_id,
            protocol_uuid=protocol_uuid,
            pdf_path=pdf_path,
            intermediate_dir=intermediate_dir,
            use_cache=use_cache,
        )

    def get_extraction_progress(self, job_id: UUID) -> Dict[str, Any]:
        """
        Get current extraction progress.

        Args:
            job_id: Job ID

        Returns:
            Progress dictionary
        """
        return self.checkpoint_service.get_job_status(job_id)
