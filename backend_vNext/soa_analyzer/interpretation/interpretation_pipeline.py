"""
SOA Interpretation Pipeline Orchestrator

Runs all 12 stages of the SOA interpretation pipeline in sequence with proper
error handling, timing, and result aggregation.

Design Principles:
1. Fail-safe execution - Non-critical stages don't block the pipeline
2. Stage result accumulation - Each stage receives results from prior stages
3. Comprehensive metrics - Timing and counts for all stages
4. Review package generation - Stage 10 receives all results for human review

Usage:
    from soa_analyzer.interpretation import (
        InterpretationPipeline,
        PipelineConfig,
        run_interpretation_pipeline,
    )

    # Option 1: Class-based
    pipeline = InterpretationPipeline()
    result = await pipeline.run(soa_output, config)
    final_usdm = result.final_usdm

    # Option 2: Convenience function
    result = await run_interpretation_pipeline(soa_output)
"""

import asyncio
import copy
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class PipelineConfig:
    """Configuration for the interpretation pipeline."""

    # Stage control
    skip_stages: List[int] = field(default_factory=list)  # Stages to skip
    stop_after_stage: Optional[int] = None  # Stop after this stage (for debugging)

    # Stage 2 & 9: Protocol-specific data sources
    extraction_outputs: Optional[Dict[str, Dict]] = None  # Module extraction results (lab, imaging, etc.)
    gemini_file_uri: Optional[str] = None  # Gemini Files API URI for PDF access

    # Stage 10 Human Review
    protocol_id: str = ""
    protocol_name: str = ""
    auto_approve_threshold: float = 0.95  # Auto-approve items above this confidence

    # Error handling
    fail_fast: bool = False  # Stop on first error
    continue_on_non_critical_failure: bool = True

    # Stage 11 Schedule Generation
    skip_stage_11: bool = False  # Now enabled by default - generates draft schedule
    draft_mode: bool = True  # Generate draft with all options for review
    review_decisions: Optional[Dict[str, Any]] = None  # Human review decisions (for final generation)

    # Output options
    save_intermediate_results: bool = False
    output_dir: Optional[Path] = None


# =============================================================================
# RESULT DATACLASS
# =============================================================================


@dataclass
class PipelineResult:
    """Result from the full interpretation pipeline."""
    success: bool = False
    final_usdm: Optional[Dict[str, Any]] = None

    # Draft schedule (from Stage 11 draft mode)
    draft_usdm: Optional[Dict[str, Any]] = None
    is_draft: bool = False  # True if final_usdm is a draft

    # Stage results
    stage_results: Dict[int, Any] = field(default_factory=dict)
    stage_durations: Dict[int, float] = field(default_factory=dict)
    stage_statuses: Dict[int, str] = field(default_factory=dict)  # success, failed, skipped

    # Aggregate metrics
    total_duration_seconds: float = 0.0
    stages_completed: int = 0
    stages_failed: int = 0
    stages_skipped: int = 0

    # Human review package (from Stage 10)
    review_package: Optional[Any] = None

    # Errors and warnings
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def get_summary(self) -> str:
        """Get summary string."""
        return (
            f"Pipeline: {'SUCCESS' if self.success else 'FAILED'} - "
            f"Completed {self.stages_completed}/{len(self.stage_durations)} stages "
            f"in {self.total_duration_seconds:.2f}s "
            f"(failed={self.stages_failed}, skipped={self.stages_skipped})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "isDraft": self.is_draft,
            "totalDurationSeconds": self.total_duration_seconds,
            "stagesCompleted": self.stages_completed,
            "stagesFailed": self.stages_failed,
            "stagesSkipped": self.stages_skipped,
            "stageDurations": self.stage_durations,
            "stageStatuses": self.stage_statuses,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# =============================================================================
# MAIN PIPELINE CLASS
# =============================================================================


class InterpretationPipeline:
    """
    12-Stage SOA Interpretation Pipeline Orchestrator.

    Executes all interpretation stages in sequence, accumulating results
    and handling errors appropriately.
    """

    # Stage execution order
    # Stage 11 (draft generation) runs before Stage 10 (review assembly)
    # so the review package includes the draft schedule
    STAGE_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 11, 10]

    # Critical stages - pipeline fails if these fail
    CRITICAL_STAGES = {1, 12}  # Domain Categorization, USDM Compliance

    # Stage names for logging
    STAGE_NAMES = {
        1: "Domain Categorization",
        2: "Activity Expansion",
        3: "Hierarchy Building",
        4: "Alternative Resolution",
        5: "Specimen Enrichment",
        6: "Conditional Expansion",
        7: "Timing Distribution",
        8: "Cycle Expansion",
        9: "Protocol Mining",
        10: "Human Review Assembly",
        11: "Schedule Generation",
        12: "USDM Compliance",
    }

    def __init__(self, progress_callback: Optional[Callable[[int, str, str], None]] = None):
        """
        Initialize the pipeline.

        Args:
            progress_callback: Optional callback for stage progress updates.
                               Called with (stage_number, stage_name, status) after each stage.
        """
        self._stage_handlers: Dict[int, Any] = {}
        self._progress_callback = progress_callback
        self._initialize_handlers()

    def _initialize_handlers(self) -> None:
        """Lazy-initialize stage handlers."""
        # Handlers are initialized on demand to avoid circular imports
        pass

    def _get_handler(self, stage: int) -> Optional[Any]:
        """Get or create handler for a stage."""
        if stage in self._stage_handlers:
            return self._stage_handlers[stage]

        try:
            if stage == 1:
                from .stage1_domain_categorization import DomainCategorizer
                self._stage_handlers[stage] = DomainCategorizer()
            elif stage == 2:
                from .stage2_activity_expansion import ActivityExpander
                self._stage_handlers[stage] = ActivityExpander()
            elif stage == 3:
                from .stage3_hierarchy_builder import HierarchyBuilder
                self._stage_handlers[stage] = HierarchyBuilder()
            elif stage == 4:
                from .stage4_alternative_resolution import AlternativeResolver
                self._stage_handlers[stage] = AlternativeResolver()
            elif stage == 5:
                from .stage5_specimen_enrichment import SpecimenEnricher
                self._stage_handlers[stage] = SpecimenEnricher()
            elif stage == 6:
                from .stage6_conditional_expansion import ConditionalExpander
                self._stage_handlers[stage] = ConditionalExpander()
            elif stage == 7:
                from .stage7_timing_distribution import TimingDistributor
                self._stage_handlers[stage] = TimingDistributor()
            elif stage == 8:
                from .stage8_cycle_expansion import CycleExpander
                self._stage_handlers[stage] = CycleExpander()
            elif stage == 9:
                from .stage9_protocol_mining import ProtocolMiner
                self._stage_handlers[stage] = ProtocolMiner()
            elif stage == 10:
                from .stage10_human_review import HumanReviewAssembler
                self._stage_handlers[stage] = HumanReviewAssembler()
            elif stage == 11:
                from .stage11_schedule_generation import ScheduleGenerator
                self._stage_handlers[stage] = ScheduleGenerator()
            elif stage == 12:
                from .stage12_usdm_compliance import USDMComplianceChecker
                self._stage_handlers[stage] = USDMComplianceChecker()

            return self._stage_handlers.get(stage)

        except ImportError as e:
            logger.error(f"Failed to import handler for stage {stage}: {e}")
            return None

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    async def run(
        self,
        soa_output: Dict[str, Any],
        config: Optional[PipelineConfig] = None,
    ) -> PipelineResult:
        """
        Run the full 12-stage interpretation pipeline.

        Args:
            soa_output: Raw SOA extraction output (from SOAHTMLInterpreter)
            config: Optional pipeline configuration

        Returns:
            PipelineResult with final USDM and all stage results
        """
        start_time = time.time()
        config = config or PipelineConfig()
        result = PipelineResult()

        # Ensure visits/encounters compatibility
        working_usdm = self._normalize_input(soa_output)

        logger.info("=" * 60)
        logger.info("Starting 12-Stage SOA Interpretation Pipeline")
        logger.info("=" * 60)

        # Determine stages to run
        stages_to_run = [
            s for s in self.STAGE_ORDER
            if s not in config.skip_stages
        ]

        # Optionally add Stage 11
        if not config.skip_stage_11 and 11 not in stages_to_run:
            stages_to_run.append(11)

        # Stop after specific stage if configured
        if config.stop_after_stage:
            stages_to_run = [s for s in stages_to_run if s <= config.stop_after_stage]

        # Execute each stage
        for stage in stages_to_run:
            stage_name = self.STAGE_NAMES.get(stage, f"Stage {stage}")

            # Check if we should skip
            if stage in config.skip_stages:
                logger.info(f"[Stage {stage}] {stage_name} - SKIPPED (config)")
                result.stage_statuses[stage] = "skipped"
                result.stages_skipped += 1
                # Call progress callback for skipped stage
                if self._progress_callback:
                    try:
                        self._progress_callback(stage, stage_name, "skipped")
                    except Exception as cb_err:
                        logger.warning(f"Progress callback error: {cb_err}")
                continue

            logger.info(f"\n[Stage {stage}] {stage_name} - Starting...")
            stage_start = time.time()

            try:
                stage_result = await self._execute_stage(
                    stage, working_usdm, result.stage_results, config
                )

                stage_duration = time.time() - stage_start
                result.stage_durations[stage] = stage_duration

                if stage_result is not None:
                    result.stage_results[stage] = stage_result
                    result.stage_statuses[stage] = "success"
                    result.stages_completed += 1

                    # Call progress callback if provided
                    if self._progress_callback:
                        try:
                            self._progress_callback(stage, stage_name, "success")
                        except Exception as cb_err:
                            logger.warning(f"Progress callback error: {cb_err}")

                    # Update working USDM if stage returns updated output
                    updated = self._get_updated_usdm(stage, stage_result, working_usdm)
                    if updated:
                        working_usdm = updated

                    # Auto-approve high-confidence items after Stage 10 completes
                    if stage == 10 and hasattr(stage_result, "package") and stage_result.package:
                        handler = self._get_handler(10)
                        if handler:
                            stage_result.package, auto_approved = handler.auto_approve_high_confidence(
                                stage_result.package,
                                threshold=config.auto_approve_threshold,
                            )
                            if auto_approved > 0:
                                logger.info(f"           Auto-approved {auto_approved} high-confidence items (≥{config.auto_approve_threshold})")
                            stage_result.auto_approved_count = auto_approved

                    # Get summary from result if available
                    summary = self._get_stage_summary(stage_result)
                    logger.info(f"[Stage {stage}] {stage_name} - Completed in {stage_duration:.2f}s")
                    if summary:
                        logger.info(f"           {summary}")
                else:
                    result.stage_statuses[stage] = "failed"
                    result.stages_failed += 1
                    logger.warning(f"[Stage {stage}] {stage_name} - Returned None")

                    # Call progress callback for failure
                    if self._progress_callback:
                        try:
                            self._progress_callback(stage, stage_name, "failed")
                        except Exception as cb_err:
                            logger.warning(f"Progress callback error: {cb_err}")

                    # Check if critical
                    if stage in self.CRITICAL_STAGES:
                        result.errors.append(f"Critical stage {stage} ({stage_name}) failed")
                        if config.fail_fast:
                            break

            except Exception as e:
                stage_duration = time.time() - stage_start
                result.stage_durations[stage] = stage_duration
                result.stage_statuses[stage] = "failed"
                result.stages_failed += 1

                error_msg = f"Stage {stage} ({stage_name}) error: {str(e)}"
                logger.error(f"[Stage {stage}] {stage_name} - FAILED: {e}", exc_info=True)

                # Call progress callback for exception
                if self._progress_callback:
                    try:
                        self._progress_callback(stage, stage_name, "failed")
                    except Exception as cb_err:
                        logger.warning(f"Progress callback error: {cb_err}")

                # Check if critical
                if stage in self.CRITICAL_STAGES:
                    result.errors.append(f"Critical stage failed: {error_msg}")
                    if config.fail_fast:
                        break
                elif config.continue_on_non_critical_failure:
                    result.warnings.append(f"Non-critical stage failed: {error_msg}")
                else:
                    result.errors.append(error_msg)
                    break

            # Save intermediate results if configured
            if config.save_intermediate_results and config.output_dir:
                self._save_intermediate(stage, result.stage_results.get(stage), config.output_dir)

        # Finalize result
        result.total_duration_seconds = time.time() - start_time
        result.final_usdm = working_usdm

        # Check if Stage 11 produced a draft
        stage11_result = result.stage_results.get(11)
        if stage11_result and hasattr(stage11_result, "is_draft") and stage11_result.is_draft:
            result.is_draft = True
            result.draft_usdm = stage11_result.draft_usdm

        # Set success based on critical stages
        critical_failed = any(
            result.stage_statuses.get(s) == "failed"
            for s in self.CRITICAL_STAGES
            if s not in config.skip_stages
        )
        result.success = not critical_failed and len(result.errors) == 0

        # Extract review package from Stage 10 if available
        stage10_result = result.stage_results.get(10)
        if stage10_result and hasattr(stage10_result, "package"):
            result.review_package = stage10_result.package

        logger.info("=" * 60)
        logger.info(result.get_summary())
        logger.info("=" * 60)

        return result

    # =========================================================================
    # STAGE EXECUTION
    # =========================================================================

    async def _execute_stage(
        self,
        stage: int,
        usdm: Dict[str, Any],
        prior_results: Dict[int, Any],
        config: PipelineConfig,
    ) -> Optional[Any]:
        """Execute a single stage with appropriate parameters."""
        handler = self._get_handler(stage)
        if not handler:
            logger.warning(f"No handler available for stage {stage}")
            return None

        # Stage-specific execution logic
        if stage == 1:
            # Domain Categorization - expects list of activities
            activities = usdm.get("activities", [])
            if not activities:
                logger.warning("No activities found in USDM for domain categorization")
                return None
            return await self._run_async_or_sync(handler.categorize_activities, activities)

        elif stage == 2:
            # Activity Expansion (v2.0: protocol-driven with extraction data + PDF)
            result = self._run_sync(
                handler.expand_activities,
                usdm,
                extraction_outputs=config.extraction_outputs,
                gemini_file_uri=config.gemini_file_uri,
            )
            # Apply expansions to USDM (adds component metadata to activities)
            if result and result.expansions:
                handler.apply_expansions_to_usdm(usdm, result)
                logger.info(f"           Applied {len(result.expansions)} expansions to USDM")
            return result

        elif stage == 3:
            # Hierarchy Building (enhanced with Stage 2 expansions)
            stage2_result = prior_results.get(2)
            # Convert Stage2Result object to dict for build_hierarchy
            stage2_dict = stage2_result.to_dict() if stage2_result and hasattr(stage2_result, 'to_dict') else stage2_result
            return self._run_sync(handler.build_hierarchy, usdm, stage2_dict)

        elif stage == 4:
            # Alternative Resolution
            return await self._run_async_or_sync(handler.resolve_alternatives, usdm)

        elif stage == 5:
            # Specimen Enrichment (v2.0: uses biospecimen_handling + PDF validation)
            return await self._run_async_or_sync(
                handler.enrich_specimens,
                usdm,
                extraction_outputs=config.extraction_outputs,
                gemini_file_uri=config.gemini_file_uri,
            )

        elif stage == 6:
            # Conditional Expansion
            result = await self._run_async_or_sync(handler.expand_conditions, usdm)
            # Apply conditions to USDM (creates assignments, links SAIs to conditions)
            if result and result.conditions:
                handler.apply_conditions_to_usdm(usdm, result)
                logger.info(
                    f"           Applied {result.conditions_created} conditions, "
                    f"created {result.assignments_created} assignments, "
                    f"linked {result.sais_linked} SAIs"
                )
            return result

        elif stage == 7:
            # Timing Distribution
            return await self._run_async_or_sync(handler.distribute_timing, usdm)

        elif stage == 8:
            # Cycle Expansion
            return await self._run_async_or_sync(handler.expand_cycles, usdm)

        elif stage == 9:
            # Protocol Mining (optional extraction_outputs + PDF validation)
            return await handler.mine_protocol(
                usdm,
                config.extraction_outputs,
                gemini_file_uri=config.gemini_file_uri,
            )

        elif stage == 10:
            # Human Review Assembly (needs all prior results)
            return handler.assemble_review_package(
                stage_results=prior_results,
                protocol_id=config.protocol_id or "UNKNOWN",
                protocol_name=config.protocol_name or "Unknown Protocol",
            )

        elif stage == 11:
            # Schedule Generation - Draft or Final mode
            # Check if we have human review decisions from a prior review cycle
            if config.review_decisions:
                # Final generation mode - apply human review decisions
                logger.info("Stage 11: Final generation mode (applying review decisions)")
                return handler.generate_schedule(usdm, config.review_decisions)
            elif config.draft_mode:
                # Draft mode - generate draft with all options for review
                logger.info("Stage 11: Draft generation mode (all options included)")
                return handler.generate_draft_schedule(usdm, prior_results)
            else:
                # No review decisions and draft mode disabled
                logger.warning("Stage 11 skipped - no review decisions and draft mode disabled")
                return None

        elif stage == 12:
            # USDM Compliance
            return await self._run_async_or_sync(handler.ensure_compliance, usdm)

        return None

    async def _run_async_or_sync(self, method: Any, *args, **kwargs) -> Any:
        """Run a method whether it's async or sync."""
        if asyncio.iscoroutinefunction(method):
            return await method(*args, **kwargs)
        else:
            return method(*args, **kwargs)

    def _run_sync(self, method: Any, *args, **kwargs) -> Any:
        """Run a synchronous method."""
        return method(*args, **kwargs)

    # =========================================================================
    # RESULT EXTRACTION
    # =========================================================================

    def _get_updated_usdm(
        self,
        stage: int,
        result: Any,
        current_usdm: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Extract updated USDM from stage result if available."""
        # Stage 1 returns CategorizationResult with categorized_activities
        if stage == 1:
            if hasattr(result, "categorized_activities"):
                usdm = copy.deepcopy(current_usdm)
                # Merge categorized activities
                for cat in result.categorized_activities:
                    activity_id = cat.activity_id
                    for key in ["activities", "scheduledActivityInstances"]:
                        for item in usdm.get(key, []):
                            if item.get("id") == activity_id or item.get("activityId") == activity_id:
                                if hasattr(cat, "domain_code") and cat.domain_code:
                                    item["domainCode"] = cat.domain_code.to_dict() if hasattr(cat.domain_code, "to_dict") else cat.domain_code
                return usdm

        # Stage 11 returns Stage11Result with draft_usdm or final_usdm
        if stage == 11:
            if hasattr(result, "draft_usdm") and result.draft_usdm:
                return result.draft_usdm
            if hasattr(result, "final_usdm") and result.final_usdm:
                return result.final_usdm

        # Stage 12 returns ComplianceResult with compliant_usdm
        if stage == 12:
            if hasattr(result, "compliant_usdm") and result.compliant_usdm:
                return result.compliant_usdm

        return None

    def _get_stage_summary(self, result: Any) -> str:
        """Get summary string from stage result."""
        if hasattr(result, "get_summary"):
            try:
                return result.get_summary()
            except Exception:
                pass

        # Try common attributes
        parts = []
        for attr in ["activities_analyzed", "activities_expanded", "items_collected",
                     "enrichments_added", "issues_found", "decisions_applied"]:
            if hasattr(result, attr):
                value = getattr(result, attr)
                if value:
                    parts.append(f"{attr}={value}")

        return ", ".join(parts) if parts else ""

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _normalize_input(self, soa_output: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize input to ensure consistent field names."""
        usdm = copy.deepcopy(soa_output)

        # Ensure encounters field exists (some stages expect 'encounters', others 'visits')
        if "visits" in usdm and "encounters" not in usdm:
            usdm["encounters"] = usdm["visits"]
        elif "encounters" in usdm and "visits" not in usdm:
            usdm["visits"] = usdm["encounters"]

        return usdm

    def _save_intermediate(
        self,
        stage: int,
        result: Any,
        output_dir: Path,
    ) -> None:
        """Save intermediate stage result to file."""
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"stage{stage:02d}_result.json"

            if hasattr(result, "to_dict"):
                data = result.to_dict()
            elif isinstance(result, dict):
                data = result
            else:
                data = {"result": str(result)}

            # Add _agentDefinition for downstream system automation context
            from .agent_definitions import get_agent_definition
            agent_def = get_agent_definition(stage)
            if agent_def:
                data["_agentDefinition"] = agent_def

            with open(output_file, "w") as f:
                json.dump(data, f, indent=2, default=str)

            logger.debug(f"Saved intermediate result to {output_file}")

        except Exception as e:
            logger.warning(f"Failed to save intermediate result for stage {stage}: {e}")


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================


async def run_interpretation_pipeline(
    soa_output: Dict[str, Any],
    protocol_id: str = "",
    protocol_name: str = "",
    extraction_outputs: Optional[Dict[str, Dict]] = None,
    gemini_file_uri: Optional[str] = None,
    skip_stages: Optional[List[int]] = None,
    auto_approve_threshold: float = 0.95,
    save_intermediate: bool = False,
    output_dir: Optional[Union[str, Path]] = None,
) -> PipelineResult:
    """
    Convenience function to run the full interpretation pipeline.

    Args:
        soa_output: Raw SOA extraction output
        protocol_id: Protocol identifier
        protocol_name: Protocol display name
        extraction_outputs: Module extraction results for Stage 2 and Stage 9
        gemini_file_uri: Gemini Files API URI for PDF access (Stage 2)
        skip_stages: List of stages to skip
        auto_approve_threshold: Confidence threshold for auto-approval
        save_intermediate: Whether to save intermediate results
        output_dir: Directory for intermediate results

    Returns:
        PipelineResult with final USDM and stage results
    """
    config = PipelineConfig(
        protocol_id=protocol_id,
        protocol_name=protocol_name,
        extraction_outputs=extraction_outputs,
        gemini_file_uri=gemini_file_uri,
        skip_stages=skip_stages or [],
        auto_approve_threshold=auto_approve_threshold,
        save_intermediate_results=save_intermediate,
        output_dir=Path(output_dir) if output_dir else None,
    )

    pipeline = InterpretationPipeline()
    return await pipeline.run(soa_output, config)
