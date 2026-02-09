"""
Eligibility Criteria Extraction Pipeline - Full End-to-End Pipeline

Complete pipeline for extracting eligibility criteria from clinical trial protocol PDFs
and transforming them into USDM 4.0 compliant JSON with OMOP concept mapping.

Pipeline Phases:
    Phase 1: Detection - Find eligibility sections in PDF (Gemini File API)
    Phase 2: Extraction - Extract all criteria with provenance (Claude two-phase)
    Phase 3: Interpretation - 10-stage pipeline (atomic decomposition, OMOP mapping)
    Phase 4: Validation - 5D quality scoring + surgical retry
    Phase 5: Output - Save results (USDM JSON, SQL templates, quality report)

Usage:
    from eligibility_analyzer.eligibility_extraction_pipeline import (
        EligibilityExtractionPipeline,
        run_eligibility_extraction,
    )

    # Option 1: Class-based
    pipeline = EligibilityExtractionPipeline()
    result = await pipeline.run("/path/to/protocol.pdf")

    # Option 2: Convenience function
    result = await run_eligibility_extraction("/path/to/protocol.pdf")

    # Access results
    print(f"Success: {result.success}")
    print(f"Quality: {result.quality_score.overall_score:.1%}")
"""

import argparse
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Type alias for progress callback: (phase, stage, total_stages, stage_name) -> None
ProgressCallback = Optional[Callable[[str, int, int, str], None]]

from dotenv import load_dotenv

load_dotenv()

# Import pipeline components
from eligibility_analyzer.eligibility_section_detector import (
    detect_eligibility_sections,
    DetectionResult,
    resolve_cross_references,
)
from eligibility_analyzer.eligibility_criteria_extractor import (
    EligibilityCriteriaExtractor,
    ExtractionResult as CriteriaExtractionResult,
)
from eligibility_analyzer.eligibility_quality_checker import (
    EligibilityQualityChecker,
    QualityScore,
    get_quality_checker,
)
from eligibility_analyzer.interpretation import (
    InterpretationPipeline,
    PipelineConfig as InterpretationConfig,
    PipelineResult as InterpretationResult,
)

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class PhaseResult:
    """Result from a pipeline phase."""
    phase: str
    success: bool
    data: Any = None
    duration: float = 0.0
    from_cache: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "success": self.success,
            "duration_seconds": round(self.duration, 2),
            "from_cache": self.from_cache,
            "error": self.error,
        }


@dataclass
class ExtractionResult:
    """Result from the full extraction pipeline."""
    success: bool
    protocol_id: str
    is_draft: bool = True
    phases: List[PhaseResult] = field(default_factory=list)

    # Core outputs
    usdm_data: Optional[Dict[str, Any]] = None
    interpretation_result: Optional[InterpretationResult] = None
    quality_score: Optional[QualityScore] = None
    raw_criteria: Optional[List[Dict[str, Any]]] = None

    # Feasibility outputs (Stage 11)
    feasibility_result: Optional[Dict[str, Any]] = None
    key_criteria_count: int = 0
    estimated_eligible_population: int = 0

    # Review JSONs for UI
    extraction_review: Optional[Dict[str, Any]] = None
    interpretation_review: Optional[Dict[str, Any]] = None

    # Files
    output_files: List[str] = field(default_factory=list)
    output_dir: Optional[str] = None

    # Metrics
    total_duration: float = 0.0
    errors: List[str] = field(default_factory=list)

    # Counts
    inclusion_count: int = 0
    exclusion_count: int = 0
    atomic_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "success": self.success,
            "protocol_id": self.protocol_id,
            "is_draft": self.is_draft,
            "phases": [p.to_dict() for p in self.phases],
            "quality": self.quality_score.to_dict() if self.quality_score else None,
            "counts": {
                "inclusion": self.inclusion_count,
                "exclusion": self.exclusion_count,
                "atomics": self.atomic_count,
                "total": self.inclusion_count + self.exclusion_count,
                "keyCriteria": self.key_criteria_count,
                "estimatedEligiblePopulation": self.estimated_eligible_population,
            },
            "output_dir": self.output_dir,
            "output_files": self.output_files,
            "total_duration_seconds": round(self.total_duration, 2),
            "errors": self.errors,
        }
        if self.feasibility_result:
            result["feasibility"] = self.feasibility_result
        return result

    def get_summary(self) -> str:
        """Get summary string."""
        status = "SUCCESS" if self.success else "FAILED"
        quality = f"{self.quality_score.overall_score:.1%}" if self.quality_score else "N/A"
        summary = (
            f"Eligibility Extraction: {status} - {self.total_duration:.2f}s - "
            f"Quality: {quality} - "
            f"{self.inclusion_count} inclusion, {self.exclusion_count} exclusion, "
            f"{self.atomic_count} atomics"
        )
        if self.key_criteria_count > 0:
            summary += f" - {self.key_criteria_count} key criteria, ~{self.estimated_eligible_population:,} eligible"
        return summary


# =============================================================================
# MAIN PIPELINE CLASS
# =============================================================================


class EligibilityExtractionPipeline:
    """
    Eligibility Criteria Extraction Pipeline - Full End-to-End.

    Phases:
        1. Detection - Find eligibility sections in PDF
        2. Extraction - Extract all criteria with provenance
        3. Interpretation - 10-stage interpretation pipeline
        4. Validation - 5D quality scoring
        5. Output - Save results
    """

    def __init__(self, athena_db_path: Optional[str] = None):
        """
        Initialize the extraction pipeline.

        Args:
            athena_db_path: Path to ATHENA SQLite database for OMOP lookup
        """
        self.athena_db_path = athena_db_path
        self.quality_checker = get_quality_checker()
        self.interpretation_pipeline = InterpretationPipeline()
        self._cache = None

        logger.info("EligibilityExtractionPipeline initialized")

    def _get_cache(self):
        """Get or initialize the cache instance."""
        if self._cache is None:
            from eligibility_analyzer.eligibility_cache import get_eligibility_cache
            self._cache = get_eligibility_cache()
        return self._cache

    async def run(
        self,
        pdf_path: str,
        output_dir: Optional[str] = None,
        protocol_id: Optional[str] = None,
        protocol_name: Optional[str] = None,
        use_cache: bool = False,
        skip_feasibility: bool = False,
        progress_callback: ProgressCallback = None,
    ) -> ExtractionResult:
        """
        Run the full eligibility extraction pipeline.

        Args:
            pdf_path: Path to protocol PDF
            output_dir: Output directory (default: adjacent to PDF)
            protocol_id: Protocol identifier (default: PDF filename stem)
            protocol_name: Protocol display name (default: protocol_id)
            use_cache: Whether to use caching for expensive stages (default: True)
            skip_feasibility: Whether to skip feasibility analysis (Stage 11)
            progress_callback: Optional callback for progress updates (phase, stage, total, name)

        Returns:
            ExtractionResult with all outputs
        """
        self.use_cache = use_cache
        self.skip_feasibility = skip_feasibility
        self.pdf_path = pdf_path
        self.progress_callback = progress_callback
        start_time = time.time()

        # Setup
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            return ExtractionResult(
                success=False,
                protocol_id=protocol_id or "UNKNOWN",
                errors=[f"PDF not found: {pdf_path}"],
            )

        protocol_id = protocol_id or pdf_file.stem
        protocol_name = protocol_name or protocol_id

        # Create timestamped output directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if output_dir:
            output_path = Path(output_dir) / timestamp
        else:
            output_path = pdf_file.parent / "eligibility_output" / timestamp
        output_path.mkdir(parents=True, exist_ok=True)

        result = ExtractionResult(
            success=True,
            protocol_id=protocol_id,
            output_dir=str(output_path),
        )

        try:
            # Phase 1: Detection
            phase1 = await self._phase_detection(str(pdf_file))
            result.phases.append(phase1)

            if not phase1.success:
                result.success = False
                result.errors.append(f"Phase 1 failed: {phase1.error}")
                self._save_result(result, output_path, protocol_id)
                return result

            detection_result: DetectionResult = phase1.data

            # Report detection complete
            if self.progress_callback:
                self.progress_callback("extraction", 1, 2, "Section detection complete")

            # Phase 2: Extraction
            phase2 = await self._phase_extraction(str(pdf_file), detection_result)
            result.phases.append(phase2)

            if not phase2.success:
                result.success = False
                result.errors.append(f"Phase 2 failed: {phase2.error}")
                self._save_result(result, output_path, protocol_id)
                return result

            extraction_result: CriteriaExtractionResult = phase2.data
            result.inclusion_count = extraction_result.inclusion_count
            result.exclusion_count = extraction_result.exclusion_count
            result.raw_criteria = [c.to_dict() for c in extraction_result.criteria]

            # Report extraction complete
            if self.progress_callback:
                self.progress_callback("extraction", 2, 2, "Criteria extraction complete")

            # Phase 3: Interpretation (will report per-stage progress)
            phase3 = await self._phase_interpretation(
                extraction_result,
                protocol_id,
                protocol_name,
                output_path,
                detection_result,
                self.progress_callback
            )
            result.phases.append(phase3)

            if phase3.success:
                result.interpretation_result = phase3.data
                if phase3.data:
                    result.atomic_count = phase3.data.atomic_count
                    result.is_draft = phase3.data.is_draft
                    # Extract feasibility results from Stage 11
                    result.key_criteria_count = phase3.data.key_criteria_count
                    result.estimated_eligible_population = phase3.data.estimated_eligible_population
                    result.feasibility_result = phase3.data.feasibility_result

            # Phase 4: Validation
            phase4 = await self._phase_validation(
                result.raw_criteria or [],
                extraction_result.inclusion_count + extraction_result.exclusion_count,
            )
            result.phases.append(phase4)

            if phase4.success:
                result.quality_score = phase4.data

            # Phase 5: Output
            phase5 = await self._phase_output(
                result,
                output_path,
                protocol_id,
            )
            result.phases.append(phase5)

            if phase5.success:
                result.output_files = phase5.data or []

        except Exception as e:
            logger.error(f"Pipeline failed with exception: {e}")
            result.success = False
            result.errors.append(str(e))

        # Calculate total duration
        result.total_duration = time.time() - start_time

        # Save final summary
        self._save_result(result, output_path, protocol_id)

        logger.info(result.get_summary())
        return result

    async def _phase_detection(self, pdf_path: str) -> PhaseResult:
        """Phase 1: Detect eligibility sections in PDF."""
        logger.info("Phase 1: Detecting eligibility sections...")
        start_time = time.time()
        cache_hit = False

        try:
            # Check cache first if enabled
            if self.use_cache:
                cache = self._get_cache()
                cached = cache.get(pdf_path, "section_detection")
                if cached:
                    logger.info("Phase 1: CACHE HIT")
                    # Reconstruct DetectionResult from cached data
                    from eligibility_analyzer.eligibility_section_detector import (
                        DetectionResult, SectionLocation, CrossReference
                    )
                    cached_data = cached.get("data", {})

                    # Reconstruct cross references if present
                    cross_refs = []
                    for cr_data in cached_data.get("cross_references", []):
                        if isinstance(cr_data, dict):
                            cross_refs.append(CrossReference(
                                reference_id=cr_data.get("referenceId") or cr_data.get("reference_id") or "",
                                reference_text=cr_data.get("referenceText") or cr_data.get("reference_text") or cr_data.get("source_text") or "",
                                target_section=cr_data.get("targetSection") or cr_data.get("target_section") or "",
                                target_page=cr_data.get("targetPage") or cr_data.get("target_page"),
                                context=cr_data.get("context") or "",
                            ))

                    detection_result = DetectionResult(
                        success=cached_data.get("success", True),
                        inclusion_section=SectionLocation(**cached_data["inclusion_section"]) if cached_data.get("inclusion_section") else None,
                        exclusion_section=SectionLocation(**cached_data["exclusion_section"]) if cached_data.get("exclusion_section") else None,
                        cross_references=cross_refs,
                        gemini_file_uri=cached_data.get("gemini_file_uri"),
                    )
                    cache_hit = True
                    return PhaseResult(
                        phase="Detection",
                        success=True,
                        data=detection_result,
                        duration=time.time() - start_time,
                        from_cache=True,
                    )

            # No cache hit - run detection
            detection_result = detect_eligibility_sections(pdf_path, validate=True)

            if not detection_result.success:
                return PhaseResult(
                    phase="Detection",
                    success=False,
                    error=detection_result.error,
                    duration=time.time() - start_time,
                )

            # Check confidence
            inc_conf = detection_result.inclusion_section.confidence if detection_result.inclusion_section else 0
            exc_conf = detection_result.exclusion_section.confidence if detection_result.exclusion_section else 0

            if inc_conf < 0.7 or exc_conf < 0.7:
                logger.warning(f"Low confidence detection: inclusion={inc_conf:.2f}, exclusion={exc_conf:.2f}")

            # Store in cache if enabled
            if self.use_cache:
                cache = self._get_cache()
                cache_data = {
                    "success": detection_result.success,
                    "inclusion_section": detection_result.inclusion_section.__dict__ if detection_result.inclusion_section else None,
                    "exclusion_section": detection_result.exclusion_section.__dict__ if detection_result.exclusion_section else None,
                    "cross_references": [cr.to_dict() for cr in detection_result.cross_references],
                    "gemini_file_uri": detection_result.gemini_file_uri,
                }
                cache.set(pdf_path, "section_detection", cache_data, duration_seconds=time.time() - start_time)

            logger.info(
                f"Phase 1 complete: "
                f"inclusion pages {detection_result.inclusion_section.page_start}-{detection_result.inclusion_section.page_end if detection_result.inclusion_section else 'N/A'}, "
                f"exclusion pages {detection_result.exclusion_section.page_start}-{detection_result.exclusion_section.page_end if detection_result.exclusion_section else 'N/A'}"
            )

            return PhaseResult(
                phase="Detection",
                success=True,
                data=detection_result,
                duration=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Phase 1 failed: {e}")
            return PhaseResult(
                phase="Detection",
                success=False,
                error=str(e),
                duration=time.time() - start_time,
            )

    async def _phase_extraction(
        self,
        pdf_path: str,
        detection_result: DetectionResult
    ) -> PhaseResult:
        """Phase 2: Extract criteria with provenance."""
        logger.info("Phase 2: Extracting criteria...")
        start_time = time.time()

        try:
            # Check cache first if enabled
            if self.use_cache:
                cache = self._get_cache()
                cached = cache.get(pdf_path, "criteria_extraction")
                if cached:
                    logger.info("Phase 2: CACHE HIT")
                    # Reconstruct ExtractionResult from cached data
                    from eligibility_analyzer.eligibility_criteria_extractor import (
                        ExtractionResult as CriteriaExtrResult, RawCriterion, Provenance, SubCriterion
                    )
                    cached_data = cached.get("data", {})

                    # Reconstruct criteria from cached data (convert camelCase to snake_case)
                    criteria = []
                    for c in cached_data.get("criteria", []):
                        provenance = None
                        if c.get("provenance"):
                            prov_data = c["provenance"]
                            provenance = Provenance(
                                page_number=prov_data.get("pageNumber") or prov_data.get("page_number"),
                                text_snippet=prov_data.get("textSnippet") or prov_data.get("text_snippet", ""),
                                confidence=prov_data.get("confidence", 0.0),
                            )

                        sub_criteria = []
                        for sc in c.get("subCriteria", []) or c.get("sub_criteria", []):
                            sub_criteria.append(SubCriterion(
                                sub_id=sc.get("subId") or sc.get("sub_id", ""),
                                text=sc.get("text", ""),
                            ))

                        criteria.append(RawCriterion(
                            criterion_id=c.get("criterionId") or c.get("criterion_id") or "",  # Ensure never None
                            original_text=c.get("originalText") or c.get("original_text") or "",
                            criterion_type=c.get("type") or c.get("criterion_type") or "Inclusion",
                            has_sub_criteria=c.get("hasSubCriteria") or c.get("has_sub_criteria", False),
                            sub_criteria=sub_criteria,
                            cross_references=c.get("crossReferences") or c.get("cross_references", []),
                            provenance=provenance,
                            resolved_references=c.get("resolvedReferences") or c.get("resolved_references", {}),
                        ))

                    extraction_result = CriteriaExtrResult(
                        success=cached_data.get("success", True),
                        criteria=criteria,
                        inclusion_count=cached_data.get("inclusion_count", 0),
                        exclusion_count=cached_data.get("exclusion_count", 0),
                    )
                    return PhaseResult(
                        phase="Extraction",
                        success=True,
                        data=extraction_result,
                        duration=time.time() - start_time,
                        from_cache=True,
                    )

            # No cache hit - run extraction
            extractor = EligibilityCriteriaExtractor()
            extraction_result = extractor.extract(pdf_path, detection_result)

            if not extraction_result.success:
                return PhaseResult(
                    phase="Extraction",
                    success=False,
                    error=extraction_result.error,
                    duration=time.time() - start_time,
                )

            # Store in cache if enabled
            if self.use_cache:
                cache = self._get_cache()
                cache_data = {
                    "success": extraction_result.success,
                    "criteria": [c.to_dict() for c in extraction_result.criteria],
                    "inclusion_count": extraction_result.inclusion_count,
                    "exclusion_count": extraction_result.exclusion_count,
                }
                cache.set(
                    pdf_path,
                    "criteria_extraction",
                    cache_data,
                    duration_seconds=time.time() - start_time,
                    item_count=len(extraction_result.criteria)
                )

            logger.info(
                f"Phase 2 complete: "
                f"{extraction_result.inclusion_count} inclusion, "
                f"{extraction_result.exclusion_count} exclusion criteria"
            )

            return PhaseResult(
                phase="Extraction",
                success=True,
                data=extraction_result,
                duration=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Phase 2 failed: {e}")
            return PhaseResult(
                phase="Extraction",
                success=False,
                error=str(e),
                duration=time.time() - start_time,
            )

    async def _phase_interpretation(
        self,
        extraction_result: CriteriaExtractionResult,
        protocol_id: str,
        protocol_name: str,
        output_path: Path,
        detection_result: Optional[DetectionResult] = None,
        progress_callback: ProgressCallback = None
    ) -> PhaseResult:
        """Phase 3: Run 11-stage interpretation pipeline."""
        logger.info("Phase 3: Running interpretation pipeline...")
        start_time = time.time()

        try:
            # Prepare raw criteria for interpretation
            raw_criteria = [c.to_dict() for c in extraction_result.criteria]

            # Build resolved references
            resolved_refs = {}
            for c in extraction_result.criteria:
                if c.resolved_references:
                    resolved_refs.update(c.resolved_references)

            # Determine stages to skip
            skip_stages = []
            if getattr(self, 'skip_feasibility', False):
                skip_stages.append(11)  # Skip Stage 11 (Feasibility Analysis)

            # Calculate eligibility section page range from detection result
            eligibility_page_start = None
            eligibility_page_end = None
            if detection_result:
                # Get the full page range covering both inclusion and exclusion sections
                inc_start = detection_result.inclusion_section.page_start if detection_result.inclusion_section else None
                inc_end = detection_result.inclusion_section.page_end if detection_result.inclusion_section else None
                exc_start = detection_result.exclusion_section.page_start if detection_result.exclusion_section else None
                exc_end = detection_result.exclusion_section.page_end if detection_result.exclusion_section else None

                # Calculate overall range
                starts = [s for s in [inc_start, exc_start] if s is not None]
                ends = [e for e in [inc_end, exc_end] if e is not None]
                if starts:
                    eligibility_page_start = min(starts)
                if ends:
                    eligibility_page_end = max(ends)

            # Configure interpretation pipeline
            config = InterpretationConfig(
                protocol_id=protocol_id,
                protocol_name=protocol_name,
                pdf_path=self.pdf_path,  # For cache key
                save_intermediate_results=True,
                output_dir=output_path,
                athena_db_path=self.athena_db_path,
                draft_mode=True,
                use_cache=getattr(self, 'use_cache', False),  # Caching disabled by default
                skip_stages=skip_stages,
                eligibility_page_start=eligibility_page_start,
                eligibility_page_end=eligibility_page_end,
            )

            # Run interpretation
            interpretation_result = await self.interpretation_pipeline.run(
                raw_criteria,
                config,
                resolved_refs,
                progress_callback
            )

            logger.info(
                f"Phase 3 complete: "
                f"{interpretation_result.stages_completed} stages completed, "
                f"{interpretation_result.atomic_count} atomics"
            )

            return PhaseResult(
                phase="Interpretation",
                success=interpretation_result.success,
                data=interpretation_result,
                duration=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Phase 3 failed: {e}")
            return PhaseResult(
                phase="Interpretation",
                success=False,
                error=str(e),
                duration=time.time() - start_time,
            )

    async def _phase_validation(
        self,
        criteria: List[Dict[str, Any]],
        expected_count: int
    ) -> PhaseResult:
        """Phase 4: 5D quality scoring."""
        logger.info("Phase 4: Running quality validation...")
        start_time = time.time()

        try:
            quality_score = self.quality_checker.check(
                criteria,
                raw_criteria_count=expected_count,
            )

            logger.info(
                f"Phase 4 complete: "
                f"Overall={quality_score.overall_score:.1%}, "
                f"Accuracy={quality_score.accuracy.score:.1%}, "
                f"Completeness={quality_score.completeness.score:.1%}, "
                f"Schema={quality_score.schema_adherence.score:.1%}, "
                f"Provenance={quality_score.provenance.score:.1%}, "
                f"Terminology={quality_score.terminology.score:.1%}"
            )

            return PhaseResult(
                phase="Validation",
                success=True,
                data=quality_score,
                duration=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Phase 4 failed: {e}")
            return PhaseResult(
                phase="Validation",
                success=False,
                error=str(e),
                duration=time.time() - start_time,
            )

    async def _phase_output(
        self,
        result: ExtractionResult,
        output_path: Path,
        protocol_id: str
    ) -> PhaseResult:
        """Phase 5: Save output files with merged interpretation data."""
        logger.info("Phase 5: Saving output files...")
        start_time = time.time()

        try:
            output_files = []

            # Merge interpretation results into criteria
            merged_criteria = self._merge_interpretation_into_criteria(
                result.raw_criteria or [],
                result.interpretation_result
            )

            # Populate usdm_data for the API response
            result.usdm_data = {"criteria": merged_criteria}

            # Save merged eligibility criteria (main output)
            criteria_file = output_path / f"{protocol_id}_eligibility_criteria.json"
            with open(criteria_file, "w") as f:
                json.dump({
                    "protocolId": protocol_id,
                    "criteria": merged_criteria,
                    "summary": {
                        "totalCriteria": len(merged_criteria),
                        "inclusionCount": result.inclusion_count,
                        "exclusionCount": result.exclusion_count,
                        "atomicCount": result.atomic_count,
                    }
                }, f, indent=2)
            output_files.append(str(criteria_file))

            # Save quality report
            quality_file = output_path / f"{protocol_id}_eligibility_quality.json"
            with open(quality_file, "w") as f:
                json.dump(
                    result.quality_score.to_dict() if result.quality_score else {},
                    f,
                    indent=2
                )
            output_files.append(str(quality_file))

            # Save interpretation results if available (full audit trail)
            if result.interpretation_result:
                interp_file = output_path / f"{protocol_id}_interpretation_result.json"
                with open(interp_file, "w") as f:
                    json.dump(result.interpretation_result.to_dict(), f, indent=2)
                output_files.append(str(interp_file))

            # Save SQL templates as separate file for easy access
            if result.interpretation_result and result.interpretation_result.stage_results.get(6):
                sql_file = output_path / f"{protocol_id}_sql_templates.json"
                with open(sql_file, "w") as f:
                    json.dump(result.interpretation_result.stage_results[6], f, indent=2)
                output_files.append(str(sql_file))

            # Save OMOP mappings as separate file
            if result.interpretation_result and result.interpretation_result.stage_results.get(5):
                omop_file = output_path / f"{protocol_id}_omop_mappings.json"
                with open(omop_file, "w") as f:
                    json.dump(result.interpretation_result.stage_results[5], f, indent=2)
                output_files.append(str(omop_file))

            logger.info(f"Phase 5 complete: {len(output_files)} files saved")

            return PhaseResult(
                phase="Output",
                success=True,
                data=output_files,
                duration=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"Phase 5 failed: {e}")
            return PhaseResult(
                phase="Output",
                success=False,
                error=str(e),
                duration=time.time() - start_time,
            )

    def _merge_interpretation_into_criteria(
        self,
        raw_criteria: List[Dict[str, Any]],
        interpretation_result: Optional[InterpretationResult]
    ) -> List[Dict[str, Any]]:
        """
        Merge interpretation stage results into the raw criteria.

        This merges:
        - Stage 2: Atomic decomposition (atomicCriteria, options, logicOperator)
        - Stage 5: OMOP concepts
        - Stage 6: SQL templates
        - Stage 8: Tier assignments

        IMPORTANT: Uses composite keys (criterionId, type) to avoid collisions
        between Inclusion and Exclusion criteria with the same numeric ID.
        """
        if not interpretation_result:
            return raw_criteria

        merged = []

        # Get stage results
        stage2_result = interpretation_result.stage_results.get(2, {})
        stage5_result = interpretation_result.stage_results.get(5, {})
        stage6_result = interpretation_result.stage_results.get(6, {})
        stage8_result = interpretation_result.stage_results.get(8, {})

        # Build lookup maps for efficient merging
        # CRITICAL: Use composite key (criterionId, type) to avoid collisions
        # between Inclusion criteria "1" and Exclusion criteria "1"
        decomposed_map = {}
        if stage2_result and isinstance(stage2_result, dict):
            for dc in stage2_result.get("decomposedCriteria", []):
                # Validate criterionId exists to prevent silent data loss
                crit_id = dc.get("criterionId")
                if not crit_id:
                    logger.warning(f"Skipping decomposed criterion with missing criterionId: {dc}")
                    continue
                # Composite key: (criterionId, type)
                key = (crit_id, dc.get("type", "Inclusion"))
                decomposed_map[key] = dc

        omop_map = {}
        if stage5_result and isinstance(stage5_result, dict):
            for mapping in stage5_result.get("mappings", []):
                # Include type in the key for OMOP mappings too
                key = (
                    mapping.get("criterionId"),
                    mapping.get("type", "Inclusion"),
                    mapping.get("atomicId")
                )
                if key not in omop_map:
                    omop_map[key] = []
                omop_map[key].append(mapping)

        sql_map = {}
        if stage6_result and isinstance(stage6_result, dict):
            for template in stage6_result.get("templates", []):
                # Composite key: (criterionId, type)
                key = (template.get("criterionId"), template.get("type", "Inclusion"))
                sql_map[key] = template

        tier_map = {"tier1": [], "tier2": [], "tier3": []}
        if stage8_result and isinstance(stage8_result, dict):
            tier_map = stage8_result

        # Merge each criterion
        for criterion in raw_criteria:
            criterion_id = criterion.get("criterionId")
            criterion_type = criterion.get("type", "Inclusion")
            composite_key = (criterion_id, criterion_type)
            merged_criterion = criterion.copy()

            # Merge Stage 2: Atomic decomposition
            if composite_key in decomposed_map:
                dc = decomposed_map[composite_key]
                merged_criterion["logicOperator"] = dc.get("logicOperator", "AND")
                merged_criterion["decompositionStrategy"] = dc.get("decompositionStrategy")

                # Check if using expression tree (new format)
                if dc.get("useExpressionTree") and dc.get("expression"):
                    # Expression tree format - copy the tree and extract atomics
                    merged_criterion["useExpressionTree"] = True
                    merged_criterion["hasNestedLogic"] = dc.get("hasNestedLogic", True)
                    merged_criterion["expression"] = dc.get("expression")

                    # Extract flattened atomic criteria from expression tree for convenience
                    atomics = self._extract_atomics_from_expression(dc.get("expression"))
                    merged_criterion["atomicCriteria"] = self._enrich_atomics_with_omop(
                        atomics, criterion_id, criterion_type, omop_map
                    )
                elif dc.get("logicOperator") == "AND":
                    # AND-logic: use atomicCriteria (legacy format)
                    atomics = dc.get("atomicCriteria", [])
                    merged_criterion["atomicCriteria"] = self._enrich_atomics_with_omop(
                        atomics, criterion_id, criterion_type, omop_map
                    )
                else:
                    # OR-logic: use options (legacy format)
                    options = dc.get("options", [])
                    merged_criterion["options"] = self._enrich_options_with_omop(
                        options, criterion_id, criterion_type, omop_map
                    )

            # Merge Stage 6: SQL template
            if composite_key in sql_map:
                merged_criterion["sqlTemplate"] = sql_map[composite_key].get("sqlTemplate")
                merged_criterion["sqlComponents"] = sql_map[composite_key].get("components")

            # Merge Stage 8: Tier assignment
            # Note: tier_map uses simple criterionId, may need composite keys if issues arise
            if criterion_id in tier_map.get("tier1", []):
                merged_criterion["tier"] = 1
            elif criterion_id in tier_map.get("tier2", []):
                merged_criterion["tier"] = 2
            elif criterion_id in tier_map.get("tier3", []):
                merged_criterion["tier"] = 3

            merged.append(merged_criterion)

        return merged

    def _enrich_atomics_with_omop(
        self,
        atomics: List[Dict[str, Any]],
        criterion_id: str,
        criterion_type: str,
        omop_map: Dict
    ) -> List[Dict[str, Any]]:
        """Enrich atomic criteria with OMOP concepts."""
        enriched = []
        for atomic in atomics:
            atomic_copy = atomic.copy()
            # Composite key: (criterionId, type, atomicId)
            key = (criterion_id, criterion_type, atomic.get("atomicId"))
            if key in omop_map:
                mappings = omop_map[key]
                # Collect all OMOP concepts for this atomic
                concepts = []
                for mapping in mappings:
                    concepts.extend(mapping.get("concepts", []))
                atomic_copy["omopConcepts"] = concepts
            enriched.append(atomic_copy)
        return enriched

    def _enrich_options_with_omop(
        self,
        options: List[Dict[str, Any]],
        criterion_id: str,
        criterion_type: str,
        omop_map: Dict
    ) -> List[Dict[str, Any]]:
        """Enrich OR-logic options with OMOP concepts."""
        enriched = []
        for option in options:
            option_copy = option.copy()
            conditions = option.get("conditions", [])
            option_copy["conditions"] = self._enrich_atomics_with_omop(
                conditions, criterion_id, criterion_type, omop_map
            )
            enriched.append(option_copy)
        return enriched

    def _extract_atomics_from_expression(
        self,
        node: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Recursively extract all atomic nodes from an expression tree.

        This flattens the tree structure into a list of atomic criteria,
        useful for OMOP concept enrichment and display purposes.
        """
        atomics = []
        if not node:
            return atomics

        node_type = node.get("nodeType")

        if node_type == "atomic":
            # Found an atomic node - extract it
            atomic = {
                "atomicId": node.get("nodeId"),
                "atomicText": node.get("atomicText"),
                "omopTable": node.get("omopTable"),
                "strategy": node.get("strategy"),
            }
            # Include optional structured constraints if present
            if node.get("valueConstraint"):
                atomic["valueConstraint"] = node.get("valueConstraint")
            if node.get("timeConstraint"):
                atomic["timeConstraint"] = node.get("timeConstraint")
            if node.get("timeFrameStructured"):
                atomic["timeFrameStructured"] = node.get("timeFrameStructured")
            if node.get("numericConstraintStructured"):
                atomic["numericConstraintStructured"] = node.get("numericConstraintStructured")
            if node.get("numericRangeStructured"):
                atomic["numericRangeStructured"] = node.get("numericRangeStructured")
            atomics.append(atomic)

        elif node_type == "operator":
            # Recursively process operands
            for operand in node.get("operands", []):
                atomics.extend(self._extract_atomics_from_expression(operand))

        elif node_type == "temporal":
            # Temporal node wraps a single operand
            operand = node.get("operand")
            if operand:
                atomics.extend(self._extract_atomics_from_expression(operand))

        return atomics

    def _save_result(
        self,
        result: ExtractionResult,
        output_path: Path,
        protocol_id: str
    ) -> None:
        """Save pipeline summary."""
        try:
            summary_file = output_path / f"{protocol_id}_pipeline_summary.json"
            with open(summary_file, "w") as f:
                summary = {
                    "timestamp": datetime.now().isoformat(),
                    "protocol_id": protocol_id,
                    "is_draft": result.is_draft,
                    "counts": {
                        "inclusion": result.inclusion_count,
                        "exclusion": result.exclusion_count,
                        "atomics": result.atomic_count,
                    },
                    "quality": result.quality_score.to_dict() if result.quality_score else None,
                    "interpretation_pipeline": result.interpretation_result.to_dict() if result.interpretation_result else None,
                    "output_files": result.output_files,
                }
                json.dump(summary, f, indent=2)
            result.output_files.append(str(summary_file))
        except Exception as e:
            logger.warning(f"Failed to save pipeline summary: {e}")


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================


async def run_eligibility_extraction(
    pdf_path: str,
    output_dir: Optional[str] = None,
    protocol_id: Optional[str] = None,
    athena_db_path: Optional[str] = None,
    use_cache: bool = False,
    skip_feasibility: bool = False,
) -> ExtractionResult:
    """
    Convenience function to run eligibility extraction.

    Args:
        pdf_path: Path to protocol PDF
        output_dir: Output directory
        protocol_id: Protocol identifier
        athena_db_path: Path to ATHENA database
        use_cache: Whether to use caching for expensive stages (default: True)
        skip_feasibility: Whether to skip feasibility analysis (Stage 11)

    Returns:
        ExtractionResult
    """
    pipeline = EligibilityExtractionPipeline(athena_db_path=athena_db_path)
    return await pipeline.run(
        pdf_path,
        output_dir,
        protocol_id,
        use_cache=use_cache,
        skip_feasibility=skip_feasibility,
    )


# =============================================================================
# CLI SUPPORT
# =============================================================================


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Extract eligibility criteria from clinical trial protocol PDF"
    )
    parser.add_argument(
        "pdf_path",
        help="Path to protocol PDF file"
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory (default: adjacent to PDF)"
    )
    parser.add_argument(
        "--protocol-id",
        help="Protocol identifier (default: PDF filename)"
    )
    parser.add_argument(
        "--athena-db",
        help="Path to ATHENA SQLite database"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable caching (force fresh extraction)"
    )
    parser.add_argument(
        "--no-feasibility",
        action="store_true",
        help="Skip feasibility analysis (Stage 11)"
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Log cache status
    use_cache = not args.no_cache
    if not use_cache:
        logger.info("Caching disabled - running fresh extraction")

    # Log feasibility status
    skip_feasibility = args.no_feasibility
    if skip_feasibility:
        logger.info("Feasibility analysis (Stage 11) disabled")

    # Run extraction
    async def run():
        result = await run_eligibility_extraction(
            pdf_path=args.pdf_path,
            output_dir=args.output_dir,
            protocol_id=args.protocol_id,
            athena_db_path=args.athena_db,
            use_cache=use_cache,
            skip_feasibility=skip_feasibility,
        )
        return result

    result = asyncio.run(run())

    # Print summary
    print(f"\n{'='*60}")
    print("ELIGIBILITY EXTRACTION RESULTS")
    print(f"{'='*60}")
    print(result.get_summary())

    if result.success:
        print(f"\nOutput directory: {result.output_dir}")
        print(f"Output files:")
        for f in result.output_files:
            print(f"  - {Path(f).name}")

        if result.quality_score:
            print(f"\nQuality Scores:")
            print(f"  Accuracy: {result.quality_score.accuracy.score:.1%}")
            print(f"  Completeness: {result.quality_score.completeness.score:.1%}")
            print(f"  Schema Adherence: {result.quality_score.schema_adherence.score:.1%}")
            print(f"  Provenance: {result.quality_score.provenance.score:.1%}")
            print(f"  Terminology: {result.quality_score.terminology.score:.1%}")
            print(f"  Overall: {result.quality_score.overall_score:.1%}")

        if result.feasibility_result:
            print(f"\nFeasibility Analysis:")
            print(f"  Key Criteria: {result.key_criteria_count}")
            print(f"  Estimated Eligible Population: {result.estimated_eligible_population:,}")
            if result.feasibility_result.get("funnel_result"):
                funnel = result.feasibility_result["funnel_result"]
                print(f"  Funnel Stages: {len(funnel.get('funnelStages', []))}")
                print(f"  Killer Criteria: {len(funnel.get('killerCriteria', []))}")
                print(f"  Optimization Opportunities: {len(funnel.get('optimizationOpportunities', []))}")
    else:
        print(f"\nErrors:")
        for error in result.errors:
            print(f"  - {error}")

    return 0 if result.success else 1


if __name__ == "__main__":
    exit(main())
