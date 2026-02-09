"""
Eligibility Criteria Interpretation Pipeline Orchestrator

Runs all 10 stages of the eligibility interpretation pipeline in sequence with
proper error handling, timing, and result aggregation.

Design Principles:
1. Fail-safe execution - Non-critical stages don't block the pipeline
2. Stage result accumulation - Each stage receives results from prior stages
3. Comprehensive metrics - Timing and counts for all stages
4. Review package generation - Stage 9 receives all results for human review
5. LLM-first concept expansion - Uses LLM for term normalization and domain hints

Usage:
    from eligibility_analyzer.interpretation import (
        InterpretationPipeline,
        PipelineConfig,
        run_interpretation_pipeline,
    )

    pipeline = InterpretationPipeline()
    result = await pipeline.run(raw_criteria)
"""

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Type alias for progress callback: (phase, stage, total_stages, stage_name) -> None
ProgressCallback = Optional[Callable[[str, int, int, str], None]]

from eligibility_analyzer.interpretation.omop_query_cache import (
    OMOPQueryCache,
    get_omop_cache,
)

# Parallel processing configuration for OMOP mapping
OMOP_PARALLEL_WORKERS = 10  # Number of parallel database query threads
OMOP_BATCH_SIZE = 20  # Number of terms to process in parallel batches

logger = logging.getLogger(__name__)

# Domain to OMOP table mapping (used when LLM provides domain hints)
DOMAIN_TO_TABLE = {
    "Condition": "condition_occurrence",
    "Drug": "drug_exposure",
    "Measurement": "measurement",
    "Procedure": "procedure_occurrence",
    "Observation": "observation",
    "Device": "device_exposure",
}

# Default vocabulary hints by domain (fallback when LLM unavailable)
DEFAULT_VOCAB_BY_DOMAIN = {
    "Condition": ["ICD10CM", "SNOMED", "ICD9CM"],
    "Drug": ["RxNorm", "RxNorm Extension", "NDC", "HemOnc"],
    "Measurement": ["LOINC", "SNOMED"],
    "Procedure": ["CPT4", "HCPCS", "ICD10PCS", "SNOMED"],
    "Observation": ["SNOMED", "NCIt", "LOINC"],
    "Device": ["SNOMED", "HCPCS"],
}

# ATHENA database path from environment variable (no hardcoded fallback)
# Set ATHENA_DB_PATH in .env file, e.g.: ATHENA_DB_PATH=/path/to/athena_concepts_full.db


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class PipelineConfig:
    """Configuration for the interpretation pipeline."""

    # Stage control
    skip_stages: List[int] = field(default_factory=list)
    stop_after_stage: Optional[int] = None

    # Protocol info
    protocol_id: str = ""
    protocol_name: str = ""
    pdf_path: Optional[str] = None  # For caching key

    # Quality thresholds
    auto_approve_threshold: float = 0.95

    # Error handling
    fail_fast: bool = False
    continue_on_non_critical_failure: bool = True

    # Draft mode
    draft_mode: bool = True

    # Output options
    save_intermediate_results: bool = True
    output_dir: Optional[Path] = None

    # External resources
    athena_db_path: Optional[str] = None  # ATHENA SQLite for OMOP lookup
    gemini_file_uri: Optional[str] = None  # For PDF access

    # Eligibility section page range (from Phase 1 detection)
    eligibility_page_start: Optional[int] = None  # First page of eligibility section
    eligibility_page_end: Optional[int] = None    # Last page of eligibility section

    # Caching
    use_cache: bool = False  # Disabled - always start fresh
    cache_ttl_days: int = 30  # Cache time-to-live


# =============================================================================
# RESULT DATACLASS
# =============================================================================


@dataclass
class PipelineResult:
    """Result from the full interpretation pipeline."""
    success: bool = False
    final_usdm: Optional[Dict[str, Any]] = None
    is_draft: bool = True

    # Stage results
    stage_results: Dict[int, Any] = field(default_factory=dict)
    stage_durations: Dict[int, float] = field(default_factory=dict)
    stage_statuses: Dict[int, str] = field(default_factory=dict)

    # Aggregate metrics
    total_duration_seconds: float = 0.0
    stages_completed: int = 0
    stages_failed: int = 0
    stages_skipped: int = 0

    # Human review package (from Stage 9)
    review_package: Optional[Any] = None

    # Counts
    criteria_count: int = 0
    atomic_count: int = 0
    omop_concepts_count: int = 0

    # Feasibility analysis (Stage 11)
    feasibility_result: Optional[Dict[str, Any]] = None
    key_criteria_count: int = 0
    estimated_eligible_population: int = 0

    # QEB result (Stage 12)
    qeb_result: Optional[Dict[str, Any]] = None

    # Errors and warnings
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def get_summary(self) -> str:
        """Get summary string."""
        return (
            f"Pipeline: {'SUCCESS' if self.success else 'FAILED'} - "
            f"Completed {self.stages_completed}/11 stages "
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
            "counts": {
                "criteria": self.criteria_count,
                "atomics": self.atomic_count,
                "omopConcepts": self.omop_concepts_count,
                "keyCriteria": self.key_criteria_count,
                "estimatedEligiblePopulation": self.estimated_eligible_population,
            },
            "feasibility": self.feasibility_result,
            "qeb_result": self.qeb_result,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# =============================================================================
# MAIN PIPELINE CLASS
# =============================================================================


class InterpretationPipeline:
    """
    11-Stage Eligibility Interpretation Pipeline Orchestrator.

    Stages:
        1. Cohort Detection
        2. Atomic Decomposition (CRITICAL)
        3. Clinical Categorization
        4. Term Extraction
        5. OMOP Concept Mapping (CRITICAL)
        6. SQL Template Generation
        7. USDM Compliance (CRITICAL)
        8. Tier Assignment
        9. Human Review Assembly
        10. Final Output Generation
        11. Feasibility Analysis (Patient Funnel)
    """

    # Stage execution order
    STAGE_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]

    # Critical stages - pipeline fails if these fail
    CRITICAL_STAGES = {2, 5, 7}  # Atomic Decomposition, OMOP Mapping, USDM Compliance

    # Stage names for logging
    STAGE_NAMES = {
        1: "Cohort Detection",
        2: "Atomic Decomposition",
        3: "Clinical Categorization",
        4: "Term Extraction",
        5: "OMOP Concept Mapping",
        6: "SQL Template Generation",
        7: "USDM Compliance",
        8: "Tier Assignment",
        9: "Human Review Assembly",
        10: "Final Output Generation",
        11: "Feasibility Analysis",
        12: "QEB Builder",
    }

    # Stage to cache key mapping
    STAGE_CACHE_KEYS = {
        1: "stage1_cohort_detection",
        2: "stage2_atomic_decomposition",
        3: "stage3_clinical_categorization",
        4: "stage4_term_extraction",
        5: "stage5_omop_mapping",
        6: "stage6_sql_generation",
        7: "stage7_usdm_compliance",
        8: "stage8_tier_assignment",
        9: "stage9_human_review",
        10: "stage10_final_output",
        11: "stage11_feasibility",
        12: "stage12_qeb_builder",
    }

    # Stages worth caching (expensive LLM/DB operations)
    CACHEABLE_STAGES = {2, 5, 11, 12}  # Atomic Decomposition, OMOP Mapping, Feasibility, QEB Builder

    def __init__(self):
        """Initialize the pipeline."""
        self._stage_handlers: Dict[int, Any] = {}
        self._cache = None
        self._demographic_reference = self._load_demographic_reference()

    def _load_demographic_reference(self) -> Dict[str, Any]:
        """Load demographic OMOP concepts from reference data."""
        ref_path = Path(__file__).parent.parent / "reference_data" / "omop_demographic_concepts.json"
        if ref_path.exists():
            try:
                with open(ref_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load demographic reference: {e}")
        return {}

    def _is_age_criterion(self, text: str) -> bool:
        """Check if text represents an age criterion using reference patterns."""
        text_lower = text.lower()
        patterns = self._demographic_reference.get("demographic_patterns", {}).get("age", [])
        if not patterns:
            # Fallback patterns
            patterns = ["age", "years old", "years of age", "adult", "pediatric"]
        return any(p in text_lower for p in patterns)

    def _is_gender_criterion(self, text: str) -> Tuple[bool, Optional[str]]:
        """Check if text represents a gender criterion and return the gender if detected."""
        text_lower = text.lower()
        patterns = self._demographic_reference.get("demographic_patterns", {}).get("gender", [])
        if not patterns:
            patterns = ["gender", "sex", "male", "female", "woman", "man", "men", "women"]

        if not any(p in text_lower for p in patterns):
            return False, None

        # Determine which gender
        if "female" in text_lower or "woman" in text_lower or "women" in text_lower:
            return True, "female"
        elif "male" in text_lower or "man" in text_lower or "men" in text_lower:
            return True, "male"
        return True, None

    def _get_gender_concept_id(self, gender: str) -> int:
        """Get OMOP concept ID for a gender from reference data."""
        gender_ref = self._demographic_reference.get("gender", {})
        if gender and gender in gender_ref:
            return gender_ref[gender].get("concept_id", 0)
        # Fallback to hardcoded values if reference not loaded
        fallback = {"female": 8532, "male": 8507}
        return fallback.get(gender, 0)

    def _get_cache(self):
        """Get or initialize the cache instance."""
        if self._cache is None:
            from eligibility_analyzer.eligibility_cache import get_eligibility_cache
            self._cache = get_eligibility_cache()
        return self._cache

    def _get_handler(self, stage: int) -> Optional[Any]:
        """Get or create handler for a stage."""
        if stage in self._stage_handlers:
            return self._stage_handlers[stage]

        try:
            if stage == 2:
                from .stage2_atomic_decomposition import AtomicDecomposer
                self._stage_handlers[stage] = AtomicDecomposer()
            # Other stages will be implemented similarly
            else:
                logger.warning(f"Stage {stage} handler not yet implemented")
                return None

            return self._stage_handlers.get(stage)
        except Exception as e:
            logger.error(f"Failed to initialize handler for stage {stage}: {e}")
            return None

    async def run(
        self,
        raw_criteria: List[Dict[str, Any]],
        config: Optional[PipelineConfig] = None,
        resolved_references: Optional[Dict[str, str]] = None,
        progress_callback: ProgressCallback = None,
    ) -> PipelineResult:
        """
        Run the full interpretation pipeline.

        Args:
            raw_criteria: List of raw criteria from Phase 2
            config: Pipeline configuration
            resolved_references: Optional resolved cross-references
            progress_callback: Optional callback for progress updates (phase, stage, total, name)

        Returns:
            PipelineResult with all outputs
        """
        config = config or PipelineConfig()
        start_time = time.time()

        result = PipelineResult()
        result.criteria_count = len(raw_criteria)

        # Accumulated data across stages
        accumulated_data = {
            "raw_criteria": raw_criteria,
            "resolved_references": resolved_references or {},
            "decomposed_criteria": [],
            "categorized_criteria": [],
            "term_extractions": [],
            "omop_mappings": [],
            "sql_templates": [],
            "usdm_criteria": [],
            "tier_assignments": [],
        }

        # Execute stages in order
        for stage_num in self.STAGE_ORDER:
            # Check if stage should be skipped
            if stage_num in config.skip_stages:
                logger.info(f"Stage {stage_num} ({self.STAGE_NAMES[stage_num]}): SKIPPED (config)")
                result.stage_statuses[stage_num] = "skipped"
                result.stages_skipped += 1
                continue

            # Check stop condition
            if config.stop_after_stage and stage_num > config.stop_after_stage:
                logger.info(f"Stage {stage_num}: SKIPPED (stop_after_stage={config.stop_after_stage})")
                result.stage_statuses[stage_num] = "skipped"
                result.stages_skipped += 1
                continue

            # Execute stage (with caching for expensive stages)
            stage_start = time.time()
            stage_name = self.STAGE_NAMES.get(stage_num, f"Stage {stage_num}")
            cache_key = self.STAGE_CACHE_KEYS.get(stage_num)
            cache_hit = False

            logger.info(f"Stage {stage_num} ({stage_name}): Starting...")

            # Report progress via callback
            if progress_callback:
                # Find stage position in STAGE_ORDER (1-indexed for user display)
                stage_index = self.STAGE_ORDER.index(stage_num) + 1
                total_stages = len(self.STAGE_ORDER)
                progress_callback("interpretation", stage_index, total_stages, stage_name)

            try:
                stage_result = None

                # Check cache for cacheable stages
                if (config.use_cache and
                    config.pdf_path and
                    stage_num in self.CACHEABLE_STAGES and
                    cache_key):

                    cache = self._get_cache()
                    cached = cache.get(config.pdf_path, cache_key)
                    if cached:
                        stage_result = cached.get("data")
                        cache_hit = True
                        logger.info(f"Stage {stage_num} ({stage_name}): CACHE HIT")

                        # Restore accumulated data from cached result
                        if stage_num == 2 and stage_result:
                            # Reconstruct DecompositionResult from cached dict
                            accumulated_data["decomposed_criteria"] = stage_result
                        elif stage_num == 5 and stage_result:
                            accumulated_data["omop_mappings"] = stage_result
                        elif stage_num == 11 and stage_result:
                            # Re-save feasibility files to current output directory
                            accumulated_data["feasibility_result"] = stage_result
                            if config.output_dir:
                                self._save_feasibility_files_from_cache(
                                    stage_result, config.protocol_id, config.output_dir
                                )
                        elif stage_num == 12 and stage_result:
                            # Re-save QEB output to current output directory
                            accumulated_data["qeb_result"] = stage_result
                            if config.output_dir:
                                self._save_qeb_files_from_cache(
                                    stage_result, config.protocol_id, config.output_dir
                                )

                # Execute if not cached
                if not cache_hit:
                    stage_result = await self._execute_stage(
                        stage_num, accumulated_data, config
                    )

                    # Store in cache for cacheable stages
                    if (config.use_cache and
                        config.pdf_path and
                        stage_num in self.CACHEABLE_STAGES and
                        cache_key and
                        stage_result is not None):

                        stage_duration_for_cache = time.time() - stage_start
                        cache = self._get_cache()

                        # Determine item count for analytics
                        item_count = None
                        if stage_num == 2 and hasattr(stage_result, "total_atomics"):
                            item_count = stage_result.total_atomics
                        elif stage_num == 5 and isinstance(stage_result, dict):
                            item_count = len(stage_result.get("mappings", []))

                        # Convert to dict for caching if needed
                        cache_data = stage_result
                        if hasattr(stage_result, "to_dict"):
                            cache_data = stage_result.to_dict()

                        cache.set(
                            config.pdf_path,
                            cache_key,
                            cache_data,
                            duration_seconds=stage_duration_for_cache,
                            item_count=item_count,
                        )

                stage_duration = time.time() - stage_start
                result.stage_durations[stage_num] = stage_duration
                result.stage_results[stage_num] = stage_result

                if stage_result is not None:
                    result.stage_statuses[stage_num] = "success" if not cache_hit else "cached"
                    result.stages_completed += 1
                    status_msg = "CACHE HIT" if cache_hit else f"SUCCESS ({stage_duration:.2f}s)"
                    logger.info(f"Stage {stage_num} ({stage_name}): {status_msg}")

                    # Save intermediate results if configured
                    if config.save_intermediate_results and config.output_dir:
                        self._save_stage_result(stage_num, stage_result, config.output_dir)
                else:
                    result.stage_statuses[stage_num] = "skipped"
                    result.stages_skipped += 1
                    logger.warning(f"Stage {stage_num} ({stage_name}): No result (handler not implemented)")

            except Exception as e:
                stage_duration = time.time() - stage_start
                result.stage_durations[stage_num] = stage_duration
                result.stage_statuses[stage_num] = "failed"
                result.stages_failed += 1
                error_msg = f"Stage {stage_num} ({stage_name}) failed: {str(e)}"
                result.errors.append(error_msg)
                logger.error(error_msg)

                # Check if critical stage
                if stage_num in self.CRITICAL_STAGES:
                    logger.error(f"Critical stage {stage_num} failed - pipeline aborted")
                    if config.fail_fast:
                        break
                elif not config.continue_on_non_critical_failure:
                    break

        # Calculate totals
        result.total_duration_seconds = time.time() - start_time
        result.is_draft = config.draft_mode

        # Determine success
        result.success = (
            result.stages_failed == 0 or
            not any(s in self.CRITICAL_STAGES for s, status in result.stage_statuses.items() if status == "failed")
        )

        # Extract final counts
        if accumulated_data.get("decomposed_criteria"):
            decomposed = accumulated_data["decomposed_criteria"]
            if hasattr(decomposed, "decomposed_criteria"):
                result.atomic_count = decomposed.total_atomics

        # Populate feasibility result from Stage 11
        result.feasibility_result = accumulated_data.get("feasibility_result")

        # Populate QEB result from Stage 12
        result.qeb_result = accumulated_data.get("qeb_result")

        logger.info(result.get_summary())
        return result

    async def _execute_stage(
        self,
        stage_num: int,
        accumulated_data: Dict[str, Any],
        config: PipelineConfig
    ) -> Any:
        """Execute a single stage."""

        if stage_num == 1:
            # Stage 1: Cohort Detection
            # For now, return simple cohort structure
            return {"cohorts": [{"cohortId": "ALL", "name": "All Subjects"}]}

        elif stage_num == 2:
            # Stage 2: Atomic Decomposition (CRITICAL)
            handler = self._get_handler(2)
            if handler:
                result = await handler.decompose(
                    accumulated_data["raw_criteria"],
                    accumulated_data.get("resolved_references")
                )
                accumulated_data["decomposed_criteria"] = result
                return result.to_dict() if hasattr(result, "to_dict") else result
            return None

        elif stage_num == 3:
            # Stage 3: Clinical Categorization
            # Assign clinical domains based on decomposed criteria
            categories = self._categorize_criteria(accumulated_data.get("decomposed_criteria"))
            accumulated_data["categorized_criteria"] = categories
            return categories

        elif stage_num == 4:
            # Stage 4: Term Extraction + LLM Concept Expansion
            # Extract searchable terms and use LLM for concept normalization
            terms = await self._extract_and_expand_terms(accumulated_data.get("decomposed_criteria"))
            accumulated_data["term_extractions"] = terms
            return terms

        elif stage_num == 5:
            # Stage 5: OMOP Concept Mapping (CRITICAL)
            # Map to OMOP concepts using ATHENA database
            mappings = await self._map_to_omop(
                accumulated_data.get("term_extractions"),
                config.athena_db_path
            )
            accumulated_data["omop_mappings"] = mappings
            return mappings

        elif stage_num == 6:
            # Stage 6: SQL Template Generation
            # Generate OMOP CDM SQL queries
            templates = self._generate_sql_templates(
                accumulated_data.get("decomposed_criteria"),
                accumulated_data.get("omop_mappings")
            )
            accumulated_data["sql_templates"] = templates
            return templates

        elif stage_num == 7:
            # Stage 7: USDM Compliance (CRITICAL)
            # Transform to USDM 4.0 format
            usdm_criteria = self._ensure_usdm_compliance(
                accumulated_data.get("decomposed_criteria"),
                accumulated_data.get("omop_mappings"),
                config.protocol_id
            )
            accumulated_data["usdm_criteria"] = usdm_criteria
            return usdm_criteria

        elif stage_num == 8:
            # Stage 8: Tier Assignment
            # Assign criticality tiers
            tier_assignments = self._assign_tiers(accumulated_data.get("usdm_criteria"))
            accumulated_data["tier_assignments"] = tier_assignments
            return tier_assignments

        elif stage_num == 9:
            # Stage 9: Human Review Assembly
            # Package for human review
            review_package = self._assemble_review_package(
                accumulated_data,
                config
            )
            return review_package

        elif stage_num == 10:
            # Stage 10: Final Output Generation
            # Generate final output files
            final_output = self._generate_final_output(
                accumulated_data,
                config
            )
            return final_output

        elif stage_num == 11:
            # Stage 11: Feasibility Analysis (Patient Funnel)
            # Generate patient funnel and key criteria
            feasibility_result = await self._run_feasibility_analysis(
                accumulated_data,
                config
            )
            accumulated_data["feasibility_result"] = feasibility_result
            return feasibility_result

        elif stage_num == 12:
            # Stage 12: QEB Builder
            # Build Queryable Eligibility Blocks from atomic criteria
            qeb_result = await self._run_qeb_builder(
                accumulated_data,
                config
            )
            accumulated_data["qeb_result"] = qeb_result
            return qeb_result

        return None

    def _categorize_criteria(self, decomposed: Any) -> Dict[str, Any]:
        """Stage 3: Categorize criteria by clinical domain.

        Now uses LLM-provided domain hints from Stage 4 concept expansion
        (via llm_expansions in accumulated_data). Falls back to OMOP table
        inference if LLM expansion not available.
        """
        categories = {
            "demographics": [],
            "oncology": [],
            "biomarkers": [],
            "labs": [],
            "medications": [],
            "procedures": [],
            "medical_history": [],
            "other": [],
        }

        # Simple categorization based on OMOP table (Stage 4 will provide better hints)
        if decomposed and hasattr(decomposed, "decomposed_criteria"):
            for dc in decomposed.decomposed_criteria:
                if dc.logic_operator == "AND":
                    for ac in dc.atomic_criteria:
                        category = self._determine_category_from_domain(ac.omop_table)
                        categories[category].append({
                            "criterionId": dc.criterion_id,
                            "atomicId": ac.atomic_id,
                            "text": ac.atomic_text,
                        })
                else:
                    for opt in dc.options:
                        for cond in opt.conditions:
                            category = self._determine_category_from_domain(cond.omop_table)
                            categories[category].append({
                                "criterionId": dc.criterion_id,
                                "optionId": opt.option_id,
                                "atomicId": cond.atomic_id,
                                "text": cond.atomic_text,
                            })

        return categories

    def _determine_category_from_domain(self, omop_table: str) -> str:
        """Map OMOP table to clinical category (used before LLM expansion available)."""
        table_to_category = {
            "observation": "demographics",  # Default, will be refined by LLM
            "measurement": "labs",
            "drug_exposure": "medications",
            "procedure_occurrence": "procedures",
            "condition_occurrence": "medical_history",
            "device_exposure": "other",
        }
        return table_to_category.get(omop_table, "other")

    async def _extract_and_expand_terms(self, decomposed: Any) -> Dict[str, Any]:
        """Stage 4: Extract searchable terms and expand using LLM.

        This method:
        1. Extracts all atomic terms from decomposed criteria
        2. Calls LLM batch expansion for concept normalization
        3. Returns enriched terms with LLM-provided domain/vocabulary hints

        Supports both:
        - Expression tree format (use_expression_tree=True) - new format with ExpressionNode
        - Legacy flat format (atomic_criteria/options) - backward compatibility
        """
        term_extractions = []
        all_primary_terms = []  # Collect all terms for batch LLM expansion

        if decomposed and hasattr(decomposed, "decomposed_criteria"):
            for dc in decomposed.decomposed_criteria:
                extraction = {
                    "criterionId": dc.criterion_id,
                    "terms": [],
                }

                # Check for expression tree format (new)
                if dc.use_expression_tree and dc.expression:
                    # Use expression tree's recursive method to get all atomic nodes
                    atomic_nodes = dc.expression.get_all_atomics()
                    for node in atomic_nodes:
                        if node.atomic_text:
                            term_info = {
                                "atomicId": node.node_id,
                                "primaryTerm": node.atomic_text,
                                "omopTable": node.omop_table or "observation",
                            }
                            extraction["terms"].append(term_info)
                            all_primary_terms.append(node.atomic_text)
                else:
                    # Legacy flat format
                    atomics = []
                    if dc.logic_operator == "AND":
                        atomics = dc.atomic_criteria
                    else:
                        for opt in dc.options:
                            atomics.extend(opt.conditions)

                    for ac in atomics:
                        term_info = {
                            "atomicId": ac.atomic_id,
                            "primaryTerm": ac.atomic_text,
                            "omopTable": ac.omop_table,
                        }
                        extraction["terms"].append(term_info)
                        all_primary_terms.append(ac.atomic_text)

                term_extractions.append(extraction)

        # Batch LLM expansion for all terms
        llm_expansions = {}
        if all_primary_terms:
            try:
                from eligibility_analyzer.interpretation.term_normalizer import TermNormalizer
                normalizer = TermNormalizer(use_llm=True)
                llm_expansions = await normalizer.normalize_batch_async(all_primary_terms)
                logger.info(f"Stage 4 LLM expansion: {len(llm_expansions)} terms expanded")
            except Exception as e:
                logger.warning(f"LLM batch expansion failed: {e}. Using fallback.")

        # Enrich term extractions with LLM expansion results
        for extraction in term_extractions:
            for term in extraction.get("terms", []):
                primary_term = term.get("primaryTerm", "")
                if primary_term in llm_expansions:
                    expansion = llm_expansions[primary_term]
                    # Add LLM-provided hints to term info
                    term["llmExpansion"] = {
                        "primary": expansion.get("primary"),
                        "abbreviationExpansion": expansion.get("abbreviation_expansion"),
                        "variants": expansion.get("variants", []),
                        "omopDomainHint": expansion.get("omop_domain_hint"),
                        "vocabularyHints": expansion.get("vocabulary_hints", []),
                        "confidence": expansion.get("confidence", 0.5),
                        "source": expansion.get("source", "fallback"),
                    }

                    # Update OMOP table based on LLM domain hint (if different from Stage 2)
                    llm_domain = expansion.get("omop_domain_hint")
                    if llm_domain and llm_domain in DOMAIN_TO_TABLE:
                        term["omopTableFromLLM"] = DOMAIN_TO_TABLE[llm_domain]

        return {
            "extractions": term_extractions,
            "llmExpansions": llm_expansions,  # Include full expansions for Stage 5
            "statistics": {
                "totalTerms": len(all_primary_terms),
                "llmExpandedCount": len(llm_expansions),
            }
        }

    async def _map_to_omop(
        self,
        term_extractions: Dict[str, Any],
        athena_db_path: Optional[str]
    ) -> Dict[str, Any]:
        """
        Stage 5: Map terms to OMOP concepts using ATHENA database (PARALLELIZED).

        This performs real OMOP concept lookups using:
        1. LLM-provided synonyms and abbreviation expansions (from Stage 4)
        2. LLM-provided domain and vocabulary hints (per-term)
        3. Exact name matching against ATHENA
        4. Pattern matching (LIKE queries)
        5. Synonym lookup via concept_synonym table

        OPTIMIZATION: Uses ThreadPoolExecutor for parallel database queries.
        Each worker thread gets its own SQLite connection for concurrent reads.

        LLM-FIRST: Uses per-term vocabulary hints from LLM instead of hardcoded mappings.
        """
        db_path = athena_db_path or os.environ.get('ATHENA_DB_PATH')

        if not db_path:
            logger.error("ATHENA_DB_PATH not configured. Set ATHENA_DB_PATH environment variable.")
            return {"mappings": [], "unmapped": [], "error": "ATHENA_DB_PATH environment variable not set"}

        if not db_path or not Path(db_path).exists():
            logger.warning(f"ATHENA database not found at {db_path}, returning empty mappings")
            return {"mappings": [], "unmapped": [], "error": "ATHENA database not found"}

        mappings = {"mappings": [], "unmapped": [], "statistics": {}}

        # Get LLM expansions from Stage 4 (if available)
        llm_expansions = term_extractions.get("llmExpansions", {}) if term_extractions else {}

        # Collect all terms to process with LLM hints
        terms_to_process = []
        if term_extractions:
            for extraction in term_extractions.get("extractions", []):
                criterion_id = extraction.get("criterionId")
                for term in extraction.get("terms", []):
                    primary_term = term.get("primaryTerm", "")
                    llm_exp = term.get("llmExpansion", {})

                    # Build term info with LLM hints
                    term_info = {
                        "criterionId": criterion_id,
                        "atomicId": term.get("atomicId"),
                        "primaryTerm": primary_term,
                        "omopTable": term.get("omopTable", "observation"),
                        # LLM-provided hints (per-term)
                        "llmDomainHint": llm_exp.get("omopDomainHint"),
                        "llmVocabHints": llm_exp.get("vocabularyHints", []),
                        "llmVariants": llm_exp.get("variants", []),
                        "llmAbbreviationExpansion": llm_exp.get("abbreviationExpansion"),
                        "llmPrimary": llm_exp.get("primary"),
                        "llmConfidence": llm_exp.get("confidence", 0.5),
                        "llmSource": llm_exp.get("source", "fallback"),
                    }
                    terms_to_process.append(term_info)

        total_terms = len(terms_to_process)
        if total_terms == 0:
            mappings["statistics"] = {"totalTerms": 0, "mappedCount": 0, "unmappedCount": 0, "mappingRate": 0}
            return mappings

        llm_expanded_count = sum(1 for t in terms_to_process if t.get("llmSource") == "llm")
        logger.info(f"Stage 5: Processing {total_terms} terms ({llm_expanded_count} LLM-expanded) with {OMOP_PARALLEL_WORKERS} workers")

        def search_single_term(term_info: Dict[str, Any]) -> Dict[str, Any]:
            """Worker function to search for a single term (runs in thread pool)."""
            # Each thread gets its own connection for thread safety
            thread_conn = sqlite3.connect(db_path)
            thread_conn.row_factory = sqlite3.Row

            try:
                primary_term = term_info["primaryTerm"]
                omop_table = term_info["omopTable"]

                # Use LLM-provided domain/vocab hints (falls back to hardcoded if unavailable)
                domain, vocab_priority = self._get_domain_and_vocab_priority_with_llm(
                    omop_table,
                    term_info.get("llmDomainHint"),
                    term_info.get("llmVocabHints"),
                )

                # Build search terms list from LLM expansion
                search_terms = [primary_term]
                if term_info.get("llmAbbreviationExpansion"):
                    search_terms.insert(0, term_info["llmAbbreviationExpansion"])
                if term_info.get("llmPrimary") and term_info["llmPrimary"] != primary_term:
                    search_terms.append(term_info["llmPrimary"])
                for variant in (term_info.get("llmVariants") or [])[:5]:
                    if variant and variant not in search_terms:
                        search_terms.append(variant)

                concepts = self._search_omop_concepts_with_variants(
                    thread_conn, search_terms, domain, vocab_priority
                )

                if concepts:
                    return {
                        "mapped": True,
                        "result": {
                            "criterionId": term_info["criterionId"],
                            "atomicId": term_info["atomicId"],
                            "term": primary_term,
                            "domain": domain,
                            "concepts": concepts,
                            "confidence": self._calculate_confidence(concepts, primary_term),
                            "llmSource": term_info.get("llmSource", "fallback"),
                            "searchTermsUsed": len(search_terms),
                        }
                    }
                else:
                    return {
                        "mapped": False,
                        "result": {
                            "criterionId": term_info["criterionId"],
                            "atomicId": term_info["atomicId"],
                            "term": primary_term,
                            "domain": domain,
                            "reason": "No matching OMOP concept found",
                            "llmSource": term_info.get("llmSource", "fallback"),
                            "searchTermsUsed": len(search_terms),
                        }
                    }
            finally:
                thread_conn.close()

        mapped_count = 0
        unmapped_count = 0

        try:
            # Use ThreadPoolExecutor for parallel processing
            with ThreadPoolExecutor(max_workers=OMOP_PARALLEL_WORKERS) as executor:
                # Submit all tasks
                future_to_term = {
                    executor.submit(search_single_term, term): term
                    for term in terms_to_process
                }

                # Collect results as they complete
                for future in as_completed(future_to_term):
                    try:
                        result = future.result()
                        if result["mapped"]:
                            mapped_count += 1
                            mappings["mappings"].append(result["result"])
                        else:
                            unmapped_count += 1
                            mappings["unmapped"].append(result["result"])
                    except Exception as e:
                        term = future_to_term[future]
                        logger.error(f"Error mapping term '{term.get('primaryTerm', '?')}': {e}")
                        unmapped_count += 1
                        mappings["unmapped"].append({
                            "criterionId": term.get("criterionId"),
                            "atomicId": term.get("atomicId"),
                            "term": term.get("primaryTerm", ""),
                            "domain": "Unknown",
                            "reason": f"Error: {str(e)}",
                        })

        except Exception as e:
            logger.error(f"OMOP mapping error: {e}")
            mappings["error"] = str(e)

        mappings["statistics"] = {
            "totalTerms": total_terms,
            "mappedCount": mapped_count,
            "unmappedCount": unmapped_count,
            "mappingRate": round(mapped_count / total_terms, 2) if total_terms > 0 else 0,
            "llmExpandedCount": llm_expanded_count,
        }

        logger.info(f"Stage 5 OMOP Mapping: {mapped_count}/{total_terms} terms mapped ({mappings['statistics']['mappingRate']:.0%})")

        # Log cache performance
        cache = get_omop_cache()
        cache_stats = cache.get_stats_summary()
        logger.info(f"Stage 5 cache stats: concept_hits={cache_stats['concept_hit_rate']}, source_hits={cache_stats['source_mapping_hit_rate']}")

        # Stage 5.5: LLM Clinical Reasoning for unmapped terms
        if unmapped_count > 0:
            logger.info(f"Stage 5.5: Applying clinical reasoning to {unmapped_count} unmapped terms")
            try:
                stage_5_5_result = await self._apply_clinical_reasoning(
                    mappings["unmapped"],
                    db_path
                )

                # Merge newly mapped terms
                if stage_5_5_result.get("newly_mapped"):
                    newly_mapped = stage_5_5_result["newly_mapped"]
                    mappings["mappings"].extend(newly_mapped)
                    mapped_count += len(newly_mapped)

                # Update unmapped list
                if stage_5_5_result.get("still_unmapped"):
                    mappings["unmapped"] = stage_5_5_result["still_unmapped"]
                    unmapped_count = len(stage_5_5_result["still_unmapped"])

                # Update statistics
                mappings["statistics"]["mappedCount"] = mapped_count
                mappings["statistics"]["unmappedCount"] = unmapped_count
                mappings["statistics"]["mappingRate"] = round(mapped_count / total_terms, 2) if total_terms > 0 else 0
                mappings["statistics"]["llmReasonedCount"] = stage_5_5_result.get("reasoned_count", 0)
                mappings["statistics"]["newlyMappedFromReasoning"] = len(stage_5_5_result.get("newly_mapped", []))

                logger.info(
                    f"Stage 5.5 complete: {len(stage_5_5_result.get('newly_mapped', []))} newly mapped from clinical reasoning, "
                    f"final rate: {mappings['statistics']['mappingRate']:.0%}"
                )
            except Exception as e:
                logger.error(f"Stage 5.5 clinical reasoning failed: {e}")
                mappings["stage_5_5_error"] = str(e)

        return mappings

    async def _apply_clinical_reasoning(
        self,
        unmapped_terms: List[Dict[str, Any]],
        db_path: str,
    ) -> Dict[str, Any]:
        """
        Apply LLM clinical reasoning to unmapped terms (Stage 5.5).

        Uses clinical reasoning to interpret the intent of complex eligibility criteria
        and suggest simpler, mappable clinical concepts for ATHENA lookup.

        Args:
            unmapped_terms: List of unmapped term dicts from Stage 5 with format:
                {
                    "criterionId": str,
                    "atomicId": str,
                    "term": str,
                    "domain": str,
                    "reason": str
                }
            db_path: Path to ATHENA database

        Returns:
            Dict with:
                - "newly_mapped": List of mappings created from clinical reasoning
                - "still_unmapped": List of terms that still couldn't be mapped
                - "reasoned_count": Number of terms processed by LLM
        """
        from .llm_clinical_reasoner import get_clinical_reasoner, ClinicalReasoning

        result = {
            "newly_mapped": [],
            "still_unmapped": [],
            "reasoned_count": 0,
        }

        if not unmapped_terms:
            return result

        # Get clinical reasoning for unmapped terms
        reasoner = get_clinical_reasoner()
        reasoning_result = await reasoner.reason_unmapped_terms(unmapped_terms)

        result["reasoned_count"] = len(reasoning_result.reasonings)
        logger.info(f"Stage 5.5: LLM reasoned {result['reasoned_count']} unmapped terms")

        # Re-query ATHENA with suggested concepts from clinical reasoning
        if not reasoning_result.reasonings:
            result["still_unmapped"] = unmapped_terms
            return result

        # Open database connection for re-querying
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            for unmapped in unmapped_terms:
                term = unmapped.get("term", "")
                reasoning = reasoning_result.reasonings.get(term)

                if not reasoning or not reasoning.mappable_concepts:
                    # No reasoning available, term stays unmapped
                    result["still_unmapped"].append(unmapped)
                    continue

                # Try to map using suggested concepts
                mapped = False
                for mappable_concept in reasoning.mappable_concepts:
                    concept_str = mappable_concept.concept
                    domain = mappable_concept.domain
                    vocab_hints = mappable_concept.vocabulary_hints or DEFAULT_VOCAB_BY_DOMAIN.get(domain, ["SNOMED", "NCIt"])

                    # Search ATHENA with the suggested concept
                    search_terms = [concept_str]
                    concepts = self._search_omop_concepts_with_variants(
                        conn,
                        search_terms,
                        domain,
                        vocab_hints,
                        limit=3,
                    )

                    if concepts:
                        # Found mapping - create result
                        best_concept = concepts[0]
                        mapping_entry = {
                            "criterionId": unmapped.get("criterionId", ""),
                            "atomicId": unmapped.get("atomicId", ""),
                            "term": term,
                            "omopTable": DOMAIN_TO_TABLE.get(domain, "observation"),
                            "conceptId": best_concept["concept_id"],
                            "conceptCode": best_concept["concept_code"],
                            "conceptName": best_concept["concept_name"],
                            "vocabularyId": best_concept["vocabulary_id"],
                            "domainId": best_concept["domain_id"],
                            "standardConcept": best_concept.get("standard_concept", ""),
                            "matchedTerm": concept_str,
                            "matchType": "clinical_reasoning",
                            "confidence": reasoning.confidence,
                            "source": "llm_clinical_reasoning",
                            "clinical_interpretation": reasoning.clinical_interpretation,
                        }
                        result["newly_mapped"].append(mapping_entry)
                        mapped = True
                        logger.debug(
                            f"Stage 5.5: '{term}' → '{concept_str}' → {best_concept['concept_name']} "
                            f"({best_concept['vocabulary_id']})"
                        )
                        break  # Found mapping, stop trying other concepts

                if not mapped:
                    # Still couldn't map even with clinical reasoning
                    unmapped["clinical_reasoning"] = {
                        "interpretation": reasoning.clinical_interpretation,
                        "suggested_concepts": [
                            {
                                "concept": mc.concept,
                                "domain": mc.domain,
                                "vocabulary_hints": mc.vocabulary_hints,
                            }
                            for mc in reasoning.mappable_concepts
                        ],
                        "confidence": reasoning.confidence,
                    }
                    result["still_unmapped"].append(unmapped)

            conn.close()

        except Exception as e:
            logger.error(f"Stage 5.5 database error: {e}")
            result["still_unmapped"] = unmapped_terms
            raise

        logger.info(
            f"Stage 5.5 complete: {len(result['newly_mapped'])} newly mapped, "
            f"{len(result['still_unmapped'])} still unmapped"
        )

        return result

    def _get_domain_and_vocab_priority_with_llm(
        self,
        omop_table: str,
        llm_domain_hint: Optional[str],
        llm_vocab_hints: Optional[List[str]],
    ) -> Tuple[str, List[str]]:
        """Get OMOP domain and vocabulary priority using LLM hints (falls back to defaults).

        This replaces the hardcoded mapping with LLM-provided per-term hints.
        """
        # Use LLM domain if provided
        if llm_domain_hint:
            domain = llm_domain_hint
            # Use LLM vocab hints if provided, otherwise use defaults for the LLM domain
            if llm_vocab_hints:
                vocab_priority = llm_vocab_hints
            else:
                vocab_priority = DEFAULT_VOCAB_BY_DOMAIN.get(llm_domain_hint, ["SNOMED", "NCIt"])
            return (domain, vocab_priority)

        # Fallback: infer from OMOP table (legacy behavior)
        return self._get_domain_and_vocab_priority_fallback(omop_table)

    def _get_domain_and_vocab_priority_fallback(self, omop_table: str) -> Tuple[str, List[str]]:
        """Fallback: Get OMOP domain and vocabulary priority based on table (used when LLM unavailable)."""
        domain_map = {
            "condition_occurrence": ("Condition", ["ICD10CM", "SNOMED", "ICD9CM"]),
            "drug_exposure": ("Drug", ["RxNorm", "RxNorm Extension", "NDC", "HemOnc"]),
            "measurement": ("Measurement", ["LOINC", "SNOMED"]),
            "observation": ("Observation", ["SNOMED", "NCIt", "LOINC"]),
            "procedure_occurrence": ("Procedure", ["CPT4", "HCPCS", "ICD10PCS", "SNOMED"]),
            "device_exposure": ("Device", ["SNOMED", "HCPCS"]),
        }
        return domain_map.get(omop_table, ("Observation", ["SNOMED", "NCIt"]))

    def _search_omop_concepts_with_variants(
        self,
        conn: sqlite3.Connection,
        search_terms: List[str],
        domain: str,
        vocab_priority: List[str],
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search ATHENA database using pre-built search terms from LLM expansion.

        This method uses search terms already expanded by the LLM (from Stage 4),
        rather than calling the normalizer again. This is more efficient and uses
        the LLM's superior medical knowledge for synonym generation.

        Strategy:
        1. Check cache for previously searched terms
        2. Exact name match for each LLM-provided variant (case-insensitive)
        3. Pattern match with wildcards for top variants
        4. Synonym lookup in concept_synonym table
        5. Cache results for future lookups

        Args:
            conn: SQLite database connection
            search_terms: Pre-built list of search terms from LLM expansion
            domain: OMOP domain (e.g., "Condition", "Drug")
            vocab_priority: Priority-ordered vocabulary list from LLM
            limit: Maximum concepts to return

        Returns:
            List of matching OMOP concepts
        """
        # Check cache first
        cache = get_omop_cache()
        cache_key = cache.make_concept_key(search_terms, domain, vocab_priority)
        cached_concepts = cache.get_concepts(cache_key)
        if cached_concepts is not None:
            # Re-enrich with source mappings (also cached)
            return self._enrich_concepts_with_source_mappings(conn, cached_concepts)

        cursor = conn.cursor()
        concepts = []
        seen_ids = set()

        # Remove duplicates while preserving order
        seen_terms = set()
        unique_search_terms = []
        for t in search_terms:
            if t:
                t_lower = t.lower().strip()
                if t_lower and t_lower not in seen_terms:
                    seen_terms.add(t_lower)
                    unique_search_terms.append(t)

        if not unique_search_terms:
            return concepts

        # Check if "family history" is being explicitly searched
        # If NOT, we should exclude "family history" concepts from results
        # This prevents patient smoking status from matching "Family history of tobacco use"
        search_terms_combined = " ".join(unique_search_terms).lower()
        exclude_family_history = "family history" not in search_terms_combined

        # Check if we're searching for biomarkers (EGFR, ALK, etc.)
        # to exclude irrelevant imaging procedure matches
        biomarker_terms = ["egfr", "alk", "ros1", "braf", "kras", "nras", "her2", "brca", "pd-l1", "pd-1"]
        is_biomarker_search = any(term in search_terms_combined for term in biomarker_terms)

        # Known false positive patterns to exclude
        irrelevant_imaging_patterns = [
            "ct of ear", "computed tomography of ear", "ct scan of ear",
            "mri of ear", "magnetic resonance of ear",
            "x-ray of ear", "radiography of ear",
        ]

        def should_include_concept(concept_name: str) -> bool:
            """Filter out irrelevant concepts based on search context."""
            concept_lower = concept_name.lower()

            # Filter out family history when not explicitly searching for it
            if exclude_family_history and "family history" in concept_lower:
                return False

            # Filter out irrelevant imaging procedures for biomarker searches
            if is_biomarker_search:
                for pattern in irrelevant_imaging_patterns:
                    if pattern in concept_lower:
                        return False

            return True

        # Determine if domain filtering should be applied (Bug #1 fix)
        # When LLM provides domain hint, use it to filter out wrong domains (e.g., "Sage" for "Age")
        apply_domain_filter = domain and domain.lower() not in ("unknown", "")

        # Phase 1: Exact match for each search term (highest priority)
        for search_term in unique_search_terms:
            if len(concepts) >= limit:
                break

            search_term_clean = search_term.strip()

            for vocab in vocab_priority:
                if len(concepts) >= limit:
                    break

                if apply_domain_filter:
                    cursor.execute("""
                        SELECT concept_id, concept_code, concept_name, vocabulary_id,
                               domain_id, concept_class_id, standard_concept
                        FROM concept
                        WHERE LOWER(concept_name) = LOWER(?)
                          AND vocabulary_id = ?
                          AND domain_id = ?
                          AND (standard_concept = 'S' OR vocabulary_id IN ('NCIt', 'CIViC', 'ICD10CM', 'ICD9CM'))
                        LIMIT ?
                    """, (search_term_clean, vocab, domain, limit - len(concepts)))
                else:
                    cursor.execute("""
                        SELECT concept_id, concept_code, concept_name, vocabulary_id,
                               domain_id, concept_class_id, standard_concept
                        FROM concept
                        WHERE LOWER(concept_name) = LOWER(?)
                          AND vocabulary_id = ?
                          AND (standard_concept = 'S' OR vocabulary_id IN ('NCIt', 'CIViC', 'ICD10CM', 'ICD9CM'))
                        LIMIT ?
                    """, (search_term_clean, vocab, limit - len(concepts)))

                for row in cursor.fetchall():
                    if row['concept_id'] not in seen_ids and should_include_concept(row['concept_name']):
                        seen_ids.add(row['concept_id'])
                        concepts.append(self._row_to_concept(row, match_type="exact"))

        # Phase 2: Pattern match for each search term (if exact match didn't find enough)
        if len(concepts) < limit:
            for search_term in unique_search_terms[:3]:  # Limit pattern searches
                if len(concepts) >= limit:
                    break

                pattern = f"%{search_term.lower().strip()}%"

                for vocab in vocab_priority:
                    if len(concepts) >= limit:
                        break

                    if apply_domain_filter:
                        cursor.execute("""
                            SELECT concept_id, concept_code, concept_name, vocabulary_id,
                                   domain_id, concept_class_id, standard_concept
                            FROM concept
                            WHERE LOWER(concept_name) LIKE ?
                              AND vocabulary_id = ?
                              AND domain_id = ?
                              AND (standard_concept = 'S' OR vocabulary_id IN ('NCIt', 'CIViC', 'ICD10CM', 'ICD9CM'))
                            ORDER BY LENGTH(concept_name) ASC
                            LIMIT ?
                        """, (pattern, vocab, domain, limit - len(concepts)))
                    else:
                        cursor.execute("""
                            SELECT concept_id, concept_code, concept_name, vocabulary_id,
                                   domain_id, concept_class_id, standard_concept
                            FROM concept
                            WHERE LOWER(concept_name) LIKE ?
                              AND vocabulary_id = ?
                              AND (standard_concept = 'S' OR vocabulary_id IN ('NCIt', 'CIViC', 'ICD10CM', 'ICD9CM'))
                            ORDER BY LENGTH(concept_name) ASC
                            LIMIT ?
                        """, (pattern, vocab, limit - len(concepts)))

                    for row in cursor.fetchall():
                        if row['concept_id'] not in seen_ids and should_include_concept(row['concept_name']):
                            seen_ids.add(row['concept_id'])
                            concepts.append(self._row_to_concept(row, match_type="pattern"))

        # Phase 3: Synonym lookup using concept_synonym table (if still need more)
        if len(concepts) < limit:
            for search_term in unique_search_terms[:2]:  # Limit synonym searches
                if len(concepts) >= limit:
                    break

                pattern = f"%{search_term.lower().strip()}%"

                try:
                    if apply_domain_filter:
                        cursor.execute("""
                            SELECT c.concept_id, c.concept_code, c.concept_name, c.vocabulary_id,
                                   c.domain_id, c.concept_class_id, c.standard_concept
                            FROM concept c
                            JOIN concept_synonym cs ON c.concept_id = cs.concept_id
                            WHERE LOWER(cs.concept_synonym_name) LIKE ?
                              AND c.domain_id = ?
                              AND (c.standard_concept = 'S' OR c.vocabulary_id IN ('NCIt', 'CIViC', 'ICD10CM'))
                            ORDER BY LENGTH(c.concept_name) ASC
                            LIMIT ?
                        """, (pattern, domain, limit - len(concepts)))
                    else:
                        cursor.execute("""
                            SELECT c.concept_id, c.concept_code, c.concept_name, c.vocabulary_id,
                                   c.domain_id, c.concept_class_id, c.standard_concept
                            FROM concept c
                            JOIN concept_synonym cs ON c.concept_id = cs.concept_id
                            WHERE LOWER(cs.concept_synonym_name) LIKE ?
                              AND (c.standard_concept = 'S' OR c.vocabulary_id IN ('NCIt', 'CIViC', 'ICD10CM'))
                            ORDER BY LENGTH(c.concept_name) ASC
                            LIMIT ?
                        """, (pattern, limit - len(concepts)))

                    for row in cursor.fetchall():
                        if row['concept_id'] not in seen_ids and should_include_concept(row['concept_name']):
                            seen_ids.add(row['concept_id'])
                            concepts.append(self._row_to_concept(row, match_type="synonym"))
                except sqlite3.OperationalError:
                    # concept_synonym table may not exist in some ATHENA versions
                    pass

        # Cache the base concepts (before enrichment) for future lookups
        if concepts:
            # Cache a copy without source_mappings (those are cached separately)
            cache.set_concepts(cache_key, [
                {k: v for k, v in c.items() if k != 'source_mappings'}
                for c in concepts
            ])

        # Enrich standard concepts with source vocabulary mappings (ICD10CM, HCPCS, etc.)
        if concepts:
            concepts = self._enrich_concepts_with_source_mappings(conn, concepts)

        return concepts

    def _get_term_normalizer(self):
        """Get or initialize the term normalizer."""
        if not hasattr(self, '_term_normalizer'):
            from eligibility_analyzer.interpretation.term_normalizer import TermNormalizer
            self._term_normalizer = TermNormalizer()
        return self._term_normalizer

    def _search_omop_concepts(
        self,
        conn: sqlite3.Connection,
        term: str,
        domain: str,
        vocab_priority: List[str],
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search ATHENA database for matching OMOP concepts with term normalization.

        Strategy:
        1. Generate normalized variants (abbreviation expansion, synonyms, core concepts)
        2. Exact name match for each variant (case-insensitive)
        3. Pattern match with wildcards
        4. Synonym lookup in concept_synonym table
        """
        cursor = conn.cursor()
        concepts = []
        seen_ids = set()

        # Get term normalizer and generate search variants
        from eligibility_analyzer.interpretation.term_normalizer import TermNormalizer
        normalizer = TermNormalizer()

        # Get all normalized forms to search
        normalized_result = normalizer.normalize_for_omop_lookup(term)
        search_terms = [term.strip()]  # Start with original

        # Add primary normalized term
        if normalized_result.get("primary"):
            search_terms.append(normalized_result["primary"])

        # Add abbreviation expansion (high priority)
        if normalized_result.get("abbreviation_expansion"):
            search_terms.insert(1, normalized_result["abbreviation_expansion"])

        # Add core concept (without numeric constraints)
        if normalized_result.get("core_concept"):
            search_terms.append(normalized_result["core_concept"])

        # Add all variants (limited to top 5 to avoid too many queries)
        variants = normalized_result.get("variants", [])
        for v in variants[:5]:
            if v not in search_terms:
                search_terms.append(v)

        # Remove duplicates while preserving order
        seen_terms = set()
        unique_search_terms = []
        for t in search_terms:
            t_lower = t.lower().strip()
            if t_lower and t_lower not in seen_terms:
                seen_terms.add(t_lower)
                unique_search_terms.append(t)

        logger.debug(f"OMOP search for '{term}': trying {len(unique_search_terms)} variants")

        # Check if "family history" is being explicitly searched
        # If NOT, we should exclude "family history" concepts from results
        # This prevents patient smoking status from matching "Family history of tobacco use"
        search_terms_combined = " ".join(unique_search_terms).lower()
        exclude_family_history = "family history" not in search_terms_combined

        # Check if we're searching for biomarkers (EGFR, ALK, etc.)
        # to exclude irrelevant imaging procedure matches
        biomarker_terms = ["egfr", "alk", "ros1", "braf", "kras", "nras", "her2", "brca", "pd-l1", "pd-1"]
        is_biomarker_search = any(term in search_terms_combined for term in biomarker_terms)

        # Known false positive patterns to exclude
        irrelevant_imaging_patterns = [
            "ct of ear", "computed tomography of ear", "ct scan of ear",
            "mri of ear", "magnetic resonance of ear",
            "x-ray of ear", "radiography of ear",
        ]

        def should_include_concept(concept_name: str) -> bool:
            """Filter out irrelevant concepts based on search context."""
            concept_lower = concept_name.lower()

            # Filter out family history when not explicitly searching for it
            if exclude_family_history and "family history" in concept_lower:
                return False

            # Filter out irrelevant imaging procedures for biomarker searches
            if is_biomarker_search:
                for pattern in irrelevant_imaging_patterns:
                    if pattern in concept_lower:
                        return False

            return True

        # Determine if domain filtering should be applied (Bug #1 fix)
        # When LLM provides domain hint, use it to filter out wrong domains
        apply_domain_filter = domain and domain.lower() not in ("unknown", "")

        # Phase 1: Exact match for each search term (highest priority)
        for search_term in unique_search_terms:
            if len(concepts) >= limit:
                break

            search_term_clean = search_term.strip()

            for vocab in vocab_priority:
                if len(concepts) >= limit:
                    break

                if apply_domain_filter:
                    cursor.execute("""
                        SELECT concept_id, concept_code, concept_name, vocabulary_id,
                               domain_id, concept_class_id, standard_concept
                        FROM concept
                        WHERE LOWER(concept_name) = LOWER(?)
                          AND vocabulary_id = ?
                          AND domain_id = ?
                          AND (standard_concept = 'S' OR vocabulary_id IN ('NCIt', 'CIViC', 'ICD10CM', 'ICD9CM'))
                        LIMIT ?
                    """, (search_term_clean, vocab, domain, limit - len(concepts)))
                else:
                    cursor.execute("""
                        SELECT concept_id, concept_code, concept_name, vocabulary_id,
                               domain_id, concept_class_id, standard_concept
                        FROM concept
                        WHERE LOWER(concept_name) = LOWER(?)
                          AND vocabulary_id = ?
                          AND (standard_concept = 'S' OR vocabulary_id IN ('NCIt', 'CIViC', 'ICD10CM', 'ICD9CM'))
                        LIMIT ?
                    """, (search_term_clean, vocab, limit - len(concepts)))

                for row in cursor.fetchall():
                    if row['concept_id'] not in seen_ids and should_include_concept(row['concept_name']):
                        seen_ids.add(row['concept_id'])
                        concepts.append(self._row_to_concept(row, match_type="exact"))

        # Phase 2: Pattern match for each search term (if exact match didn't find enough)
        if len(concepts) < limit:
            for search_term in unique_search_terms[:3]:  # Limit pattern searches
                if len(concepts) >= limit:
                    break

                pattern = f"%{search_term.lower().strip()}%"

                for vocab in vocab_priority:
                    if len(concepts) >= limit:
                        break

                    if apply_domain_filter:
                        cursor.execute("""
                            SELECT concept_id, concept_code, concept_name, vocabulary_id,
                                   domain_id, concept_class_id, standard_concept
                            FROM concept
                            WHERE LOWER(concept_name) LIKE ?
                              AND vocabulary_id = ?
                              AND domain_id = ?
                              AND (standard_concept = 'S' OR vocabulary_id IN ('NCIt', 'CIViC', 'ICD10CM', 'ICD9CM'))
                            ORDER BY LENGTH(concept_name) ASC
                            LIMIT ?
                        """, (pattern, vocab, domain, limit - len(concepts)))
                    else:
                        cursor.execute("""
                            SELECT concept_id, concept_code, concept_name, vocabulary_id,
                                   domain_id, concept_class_id, standard_concept
                            FROM concept
                            WHERE LOWER(concept_name) LIKE ?
                              AND vocabulary_id = ?
                              AND (standard_concept = 'S' OR vocabulary_id IN ('NCIt', 'CIViC', 'ICD10CM', 'ICD9CM'))
                            ORDER BY LENGTH(concept_name) ASC
                            LIMIT ?
                        """, (pattern, vocab, limit - len(concepts)))

                    for row in cursor.fetchall():
                        if row['concept_id'] not in seen_ids and should_include_concept(row['concept_name']):
                            seen_ids.add(row['concept_id'])
                            concepts.append(self._row_to_concept(row, match_type="pattern"))

        # Phase 3: Synonym lookup using concept_synonym table (if still need more)
        if len(concepts) < limit:
            for search_term in unique_search_terms[:2]:  # Limit synonym searches
                if len(concepts) >= limit:
                    break

                pattern = f"%{search_term.lower().strip()}%"

                try:
                    if apply_domain_filter:
                        cursor.execute("""
                            SELECT c.concept_id, c.concept_code, c.concept_name, c.vocabulary_id,
                                   c.domain_id, c.concept_class_id, c.standard_concept
                            FROM concept c
                            JOIN concept_synonym cs ON c.concept_id = cs.concept_id
                            WHERE LOWER(cs.concept_synonym_name) LIKE ?
                              AND c.domain_id = ?
                              AND (c.standard_concept = 'S' OR c.vocabulary_id IN ('NCIt', 'CIViC', 'ICD10CM'))
                            ORDER BY LENGTH(c.concept_name) ASC
                            LIMIT ?
                        """, (pattern, domain, limit - len(concepts)))
                    else:
                        cursor.execute("""
                            SELECT c.concept_id, c.concept_code, c.concept_name, c.vocabulary_id,
                                   c.domain_id, c.concept_class_id, c.standard_concept
                            FROM concept c
                            JOIN concept_synonym cs ON c.concept_id = cs.concept_id
                            WHERE LOWER(cs.concept_synonym_name) LIKE ?
                              AND (c.standard_concept = 'S' OR c.vocabulary_id IN ('NCIt', 'CIViC', 'ICD10CM'))
                            ORDER BY LENGTH(c.concept_name) ASC
                            LIMIT ?
                        """, (pattern, limit - len(concepts)))

                    for row in cursor.fetchall():
                        if row['concept_id'] not in seen_ids and should_include_concept(row['concept_name']):
                            seen_ids.add(row['concept_id'])
                            concepts.append(self._row_to_concept(row, match_type="synonym"))
                except sqlite3.OperationalError:
                    # concept_synonym table may not exist in some ATHENA versions
                    pass

        # Enrich standard concepts with source vocabulary mappings (ICD10CM, HCPCS, etc.)
        # This fallback search function also needs enrichment for consistency
        if concepts:
            concepts = self._enrich_concepts_with_source_mappings(conn, concepts)

        return concepts

    def _row_to_concept(self, row: sqlite3.Row, match_type: str) -> Dict[str, Any]:
        """Convert database row to concept dict."""
        return {
            "concept_id": row['concept_id'],
            "concept_code": row['concept_code'],
            "concept_name": row['concept_name'],
            "vocabulary_id": row['vocabulary_id'],
            "domain_id": row['domain_id'],
            "concept_class_id": row['concept_class_id'],
            "standard_concept": row['standard_concept'],
            "match_type": match_type,
        }

    def _get_source_mappings(
        self,
        conn: sqlite3.Connection,
        standard_concept_id: int,
        target_vocabularies: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get source vocabulary mappings for a standard concept via concept_relationship.

        For a SNOMED concept, finds related ICD10CM, HCPCS, ICDO3, HemOnc, etc. codes
        that map TO this standard concept.

        Args:
            conn: SQLite database connection
            standard_concept_id: The standard concept ID (typically SNOMED)
            target_vocabularies: List of vocabularies to fetch mappings for
                               (default: ICD10CM, ICD9CM, HCPCS, ICDO3, HemOnc, OncoTree)

        Returns:
            List of mapped source concepts with vocabulary_id, concept_code, concept_name
        """
        if target_vocabularies is None:
            target_vocabularies = ['ICD10CM', 'ICD9CM', 'HCPCS', 'ICDO3', 'HemOnc', 'OncoTree', 'CPT4']

        cursor = conn.cursor()
        source_mappings = []

        try:
            # Find source concepts that map TO this standard concept
            # Using "Maps to" relationship: source_concept_id (id_1) -> standard_concept_id (id_2)
            cursor.execute("""
                SELECT c.concept_id, c.concept_code, c.concept_name, c.vocabulary_id,
                       c.domain_id, c.concept_class_id
                FROM concept_relationship cr
                JOIN concept c ON cr.concept_id_1 = c.concept_id
                WHERE cr.concept_id_2 = ?
                  AND cr.relationship_id = 'Maps to'
                  AND c.vocabulary_id IN ({})
                  AND c.concept_id != ?
                ORDER BY
                    CASE c.vocabulary_id
                        WHEN 'ICD10CM' THEN 1
                        WHEN 'ICD9CM' THEN 2
                        WHEN 'CPT4' THEN 3
                        WHEN 'HCPCS' THEN 4
                        WHEN 'ICDO3' THEN 5
                        WHEN 'HemOnc' THEN 6
                        WHEN 'OncoTree' THEN 7
                        ELSE 10
                    END,
                    LENGTH(c.concept_code) ASC
                LIMIT 10
            """.format(','.join('?' * len(target_vocabularies))),
            [standard_concept_id] + target_vocabularies + [standard_concept_id])

            for row in cursor.fetchall():
                source_mappings.append({
                    "concept_id": row['concept_id'],
                    "concept_code": row['concept_code'],
                    "concept_name": row['concept_name'],
                    "vocabulary_id": row['vocabulary_id'],
                    "domain_id": row['domain_id'],
                    "concept_class_id": row['concept_class_id'],
                })

        except sqlite3.OperationalError as e:
            logger.debug(f"Could not fetch source mappings for concept {standard_concept_id}: {e}")

        return source_mappings

    def _enrich_concepts_with_source_mappings(
        self,
        conn: sqlite3.Connection,
        concepts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Enrich standard concepts with their source vocabulary mappings.

        OPTIMIZED: Uses batch query instead of N+1 individual queries.
        Also uses cache to avoid redundant lookups.

        Adds a 'source_mappings' field to each concept containing related
        ICD10CM, HCPCS, CPT4, etc. codes.
        """
        if not concepts:
            return concepts

        cache = get_omop_cache()

        # Collect all standard concept IDs that need enrichment
        standard_concept_ids = [
            c['concept_id'] for c in concepts
            if c.get('standard_concept') == 'S' and c.get('concept_id')
        ]

        if not standard_concept_ids:
            # No standard concepts to enrich
            for concept in concepts:
                concept['source_mappings'] = []
            return concepts

        # Check cache for already cached mappings
        cached_mappings, uncached_ids = cache.get_source_mappings_batch(standard_concept_ids)

        # Batch query for uncached IDs
        new_mappings = {}
        if uncached_ids:
            new_mappings = self._batch_get_source_mappings(conn, uncached_ids)
            # Cache the new mappings
            cache.set_source_mappings_batch(new_mappings)

        # Merge cached and new mappings
        all_mappings = {**cached_mappings, **new_mappings}

        # Assign mappings to each concept
        for concept in concepts:
            if concept.get('standard_concept') == 'S':
                concept_id = concept.get('concept_id')
                concept['source_mappings'] = all_mappings.get(concept_id, [])
            else:
                concept['source_mappings'] = []

        return concepts

    def _batch_get_source_mappings(
        self,
        conn: sqlite3.Connection,
        concept_ids: List[int],
        target_vocabularies: Optional[List[str]] = None
    ) -> Dict[int, List[Dict[str, Any]]]:
        """
        Batch fetch source mappings for multiple standard concepts.

        OPTIMIZED: Single query for all concept IDs instead of N individual queries.

        Args:
            conn: SQLite database connection
            concept_ids: List of standard concept IDs
            target_vocabularies: List of vocabularies to fetch mappings for

        Returns:
            Dict mapping concept_id to list of source mappings
        """
        if not concept_ids:
            return {}

        if target_vocabularies is None:
            target_vocabularies = ['ICD10CM', 'ICD9CM', 'HCPCS', 'ICDO3', 'HemOnc', 'OncoTree', 'CPT4']

        cursor = conn.cursor()
        mappings_by_id: Dict[int, List[Dict[str, Any]]] = {cid: [] for cid in concept_ids}

        try:
            # Build placeholders for IN clause
            id_placeholders = ','.join('?' * len(concept_ids))
            vocab_placeholders = ','.join('?' * len(target_vocabularies))

            # Single batch query for all concept IDs
            cursor.execute(f"""
                SELECT cr.concept_id_2 as standard_concept_id,
                       c.concept_id, c.concept_code, c.concept_name, c.vocabulary_id,
                       c.domain_id, c.concept_class_id
                FROM concept_relationship cr
                JOIN concept c ON cr.concept_id_1 = c.concept_id
                WHERE cr.concept_id_2 IN ({id_placeholders})
                  AND cr.relationship_id = 'Maps to'
                  AND c.vocabulary_id IN ({vocab_placeholders})
                  AND c.concept_id NOT IN ({id_placeholders})
                ORDER BY
                    cr.concept_id_2,
                    CASE c.vocabulary_id
                        WHEN 'ICD10CM' THEN 1
                        WHEN 'ICD9CM' THEN 2
                        WHEN 'CPT4' THEN 3
                        WHEN 'HCPCS' THEN 4
                        WHEN 'ICDO3' THEN 5
                        WHEN 'HemOnc' THEN 6
                        WHEN 'OncoTree' THEN 7
                        ELSE 10
                    END,
                    LENGTH(c.concept_code) ASC
            """, concept_ids + target_vocabularies + concept_ids)

            # Group results by standard concept ID (limit 10 per concept)
            counts: Dict[int, int] = {}
            for row in cursor.fetchall():
                std_id = row['standard_concept_id']
                counts[std_id] = counts.get(std_id, 0) + 1
                if counts[std_id] <= 10:  # Limit 10 per concept
                    mappings_by_id[std_id].append({
                        "concept_id": row['concept_id'],
                        "concept_code": row['concept_code'],
                        "concept_name": row['concept_name'],
                        "vocabulary_id": row['vocabulary_id'],
                        "domain_id": row['domain_id'],
                        "concept_class_id": row['concept_class_id'],
                    })

        except sqlite3.OperationalError as e:
            logger.debug(f"Could not batch fetch source mappings: {e}")

        return mappings_by_id

    def _calculate_confidence(self, concepts: List[Dict], term: str) -> float:
        """Calculate confidence score for mapping."""
        if not concepts:
            return 0.0

        best_concept = concepts[0]
        match_type = best_concept.get("match_type", "pattern")

        # Base confidence by match type
        if match_type == "exact":
            confidence = 0.95
        elif match_type == "synonym":
            confidence = 0.85
        else:  # pattern
            confidence = 0.70

        # Boost for standard concepts
        if best_concept.get("standard_concept") == "S":
            confidence = min(1.0, confidence + 0.05)

        # Boost if concept name closely matches search term
        concept_name_lower = best_concept.get("concept_name", "").lower()
        term_lower = term.lower()
        if concept_name_lower == term_lower:
            confidence = 0.98

        return round(confidence, 2)

    def _generate_sql_templates(
        self,
        decomposed: Any,
        omop_mappings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Stage 6: Generate real OMOP CDM SQL templates.

        Generates executable SQL queries for patient screening against OMOP CDM databases.
        Each atomic criterion is translated to a SQL component that can be combined
        with AND/OR logic.

        OMOP CDM tables used:
        - person: Demographics (age, gender)
        - condition_occurrence: Diagnoses (ICD-10, SNOMED)
        - drug_exposure: Medications (RxNorm)
        - measurement: Lab tests (LOINC)
        - observation: Clinical observations
        - procedure_occurrence: Procedures (CPT, ICD-10-PCS)
        """
        templates = {"templates": [], "statistics": {}}

        # Build concept ID lookup from OMOP mappings
        concept_lookup = {}
        if omop_mappings:
            for mapping in omop_mappings.get("mappings", []):
                key = (mapping.get("criterionId"), mapping.get("atomicId"))
                concepts = mapping.get("concepts", [])
                if concepts:
                    # Get all standard concept IDs
                    concept_ids = [c.get("concept_id") for c in concepts if c.get("concept_id")]
                    if concept_ids:
                        concept_lookup[key] = {
                            "concept_ids": concept_ids,
                            "domain": mapping.get("domain", "Observation"),
                        }

        if decomposed and hasattr(decomposed, "decomposed_criteria"):
            for dc in decomposed.decomposed_criteria:
                criterion_id = dc.criterion_id
                criterion_type = dc.criterion_type
                logic_operator = dc.logic_operator

                # Check if expression tree is available (Phase 1 & 2)
                use_expression_tree = getattr(dc, 'use_expression_tree', False)
                expression = getattr(dc, 'expression', None)

                if use_expression_tree and expression:
                    # NEW: Use recursive expression tree SQL generation
                    expr_dict = expression.to_dict() if hasattr(expression, 'to_dict') else expression
                    full_sql = self._generate_expression_tree_sql(
                        expr_dict, concept_lookup, criterion_id, criterion_type
                    )

                    # Wrap exclusion criteria with NOT IN
                    if criterion_type == "Exclusion" and full_sql and not full_sql.startswith("--"):
                        full_sql = f"""-- EXCLUSION: Exclude patients matching this criterion
SELECT person_id FROM person
WHERE person_id NOT IN (
{full_sql}
)"""

                    # Collect atomics from tree for components
                    if hasattr(expression, 'get_all_atomics'):
                        atomics = expression.get_all_atomics()
                        sql_components = []
                        for atomic in atomics:
                            sql_comp = self._generate_atomic_sql_from_tree(
                                atomic.to_dict() if hasattr(atomic, 'to_dict') else atomic,
                                concept_lookup, criterion_id
                            )
                            sql_components.append({
                                "atomicId": atomic.node_id if hasattr(atomic, 'node_id') else "",
                                "atomicText": atomic.atomic_text if hasattr(atomic, 'atomic_text') else "",
                                "omopTable": atomic.omop_table if hasattr(atomic, 'omop_table') else "observation",
                                "sql": sql_comp,
                            })
                    else:
                        sql_components = []

                    template = {
                        "criterionId": criterion_id,
                        "type": criterion_type,
                        "logicOperator": logic_operator,
                        "useExpressionTree": True,
                        "expression": expr_dict,
                        "sqlTemplate": full_sql,
                        "components": sql_components,
                    }

                else:
                    # LEGACY: Use flat format (backward compatible)
                    sql_components = []

                    if logic_operator == "AND":
                        for atomic in dc.atomic_criteria:
                            sql_comp = self._generate_atomic_sql(
                                criterion_id, atomic, concept_lookup
                            )
                            sql_components.append(sql_comp)

                        # Combine with AND
                        full_sql = self._combine_sql_components(sql_components, "AND", criterion_type)

                    else:  # OR logic with options
                        option_sqls = []
                        for option in dc.options:
                            option_components = []
                            for cond in option.conditions:
                                sql_comp = self._generate_atomic_sql(
                                    criterion_id, cond, concept_lookup
                                )
                                option_components.append(sql_comp)

                            # Each option's conditions are ANDed together
                            if option_components:
                                option_sql = self._combine_sql_components(
                                    option_components, "AND", criterion_type, is_subquery=True
                                )
                                option_sqls.append({
                                    "optionId": option.option_id,
                                    "sql": option_sql,
                                })

                        # Options are ORed together
                        full_sql = self._combine_option_sqls(option_sqls, criterion_type)
                        sql_components = option_sqls

                    template = {
                        "criterionId": criterion_id,
                        "type": criterion_type,
                        "logicOperator": logic_operator,
                        "sqlTemplate": full_sql,
                        "components": sql_components if logic_operator == "AND" else option_sqls,
                    }

                templates["templates"].append(template)

        templates["statistics"] = {
            "totalCriteria": len(templates["templates"]),
            "conceptsCovered": len(concept_lookup),
        }

        logger.info(f"Stage 6 SQL Generation: {len(templates['templates'])} criteria templates generated")
        return templates

    def _generate_atomic_sql(
        self,
        criterion_id: str,
        atomic: Any,
        concept_lookup: Dict
    ) -> Dict[str, Any]:
        """Generate SQL for a single atomic criterion."""
        atomic_id = atomic.atomic_id if hasattr(atomic, 'atomic_id') else atomic.get("atomicId")
        atomic_text = atomic.atomic_text if hasattr(atomic, 'atomic_text') else atomic.get("atomicText", "")
        omop_table = atomic.omop_table if hasattr(atomic, 'omop_table') else atomic.get("omopTable", "observation")
        value_constraint = atomic.value_constraint if hasattr(atomic, 'value_constraint') else atomic.get("valueConstraint")
        time_constraint = atomic.time_constraint if hasattr(atomic, 'time_constraint') else atomic.get("timeConstraint")
        numeric_constraint = None

        # Get structured constraints if available
        if hasattr(atomic, 'numeric_constraint_structured'):
            numeric_constraint = atomic.numeric_constraint_structured
        elif isinstance(atomic, dict) and atomic.get("numericConstraintStructured"):
            numeric_constraint = atomic.get("numericConstraintStructured")

        time_frame = None
        if hasattr(atomic, 'time_frame_structured'):
            time_frame = atomic.time_frame_structured
        elif isinstance(atomic, dict) and atomic.get("timeFrameStructured"):
            time_frame = atomic.get("timeFrameStructured")

        # Get concept IDs from lookup
        key = (criterion_id, atomic_id)
        concept_info = concept_lookup.get(key, {})
        concept_ids = concept_info.get("concept_ids", [])

        # Generate SQL based on OMOP table type
        sql = self._generate_table_specific_sql(
            omop_table, concept_ids, numeric_constraint, time_frame, atomic_text
        )

        return {
            "atomicId": atomic_id,
            "atomicText": atomic_text,
            "omopTable": omop_table,
            "conceptIds": concept_ids,
            "sql": sql,
            "hasConceptMapping": len(concept_ids) > 0,
        }

    def _generate_table_specific_sql(
        self,
        omop_table: str,
        concept_ids: List[int],
        numeric_constraint: Optional[Dict],
        time_frame: Optional[Dict],
        atomic_text: str,
        numeric_range: Optional[Dict] = None
    ) -> str:
        """Generate table-specific OMOP CDM SQL.

        Args:
            omop_table: OMOP CDM table name
            concept_ids: List of concept IDs to match
            numeric_constraint: Single value constraint (e.g., >= 18)
            time_frame: Time constraint structure
            atomic_text: Original atomic text for context
            numeric_range: Range constraint (e.g., BETWEEN 0 AND 1)
        """

        # Format concept IDs clause
        if concept_ids:
            concept_clause = f"IN ({', '.join(str(c) for c in concept_ids)})"
        else:
            concept_clause = "IN (/* UNMAPPED - requires manual concept selection */)"

        # Time constraint
        time_clause = ""
        if time_frame:
            # Handle both dict and dataclass objects
            if hasattr(time_frame, 'value'):
                value = time_frame.value if time_frame.value is not None else 14
                unit = time_frame.unit if hasattr(time_frame, 'unit') and time_frame.unit else "days"
                operator = time_frame.operator if hasattr(time_frame, 'operator') and time_frame.operator else "within"
                relative_event = time_frame.relative_event if hasattr(time_frame, 'relative_event') and time_frame.relative_event else "reference_date"
            else:
                value = time_frame.get("value", 14)
                unit = time_frame.get("unit", "days")
                operator = time_frame.get("operator", "within")
                relative_event = time_frame.get("relativeEvent", "reference_date")

            if unit == "days":
                time_clause = f"\n  AND {self._get_date_column(omop_table)} >= @reference_date - INTERVAL '{value} days'"
            elif unit == "months":
                time_clause = f"\n  AND {self._get_date_column(omop_table)} >= @reference_date - INTERVAL '{value} months'"
            elif unit == "years":
                time_clause = f"\n  AND {self._get_date_column(omop_table)} >= @reference_date - INTERVAL '{value} years'"

        # Numeric constraint for measurements - use helper method that handles both
        # numericConstraintStructured and numericRangeStructured
        numeric_clause = self._build_numeric_clause(numeric_constraint, numeric_range, omop_table)

        # Generate table-specific SQL
        if omop_table == "condition_occurrence":
            return f"""SELECT DISTINCT co.person_id
FROM condition_occurrence co
WHERE co.condition_concept_id {concept_clause}{time_clause}"""

        elif omop_table == "drug_exposure":
            return f"""SELECT DISTINCT de.person_id
FROM drug_exposure de
WHERE de.drug_concept_id {concept_clause}{time_clause}"""

        elif omop_table == "measurement":
            return f"""SELECT DISTINCT m.person_id
FROM measurement m
WHERE m.measurement_concept_id {concept_clause}{numeric_clause}{time_clause}"""

        elif omop_table == "observation":
            # Special handling for demographic observations using reference data
            if self._is_age_criterion(atomic_text):
                # Handle age range (e.g., "18-65 years")
                if numeric_range:
                    if hasattr(numeric_range, 'min') and not isinstance(numeric_range, dict):
                        min_val = numeric_range.min
                        max_val = numeric_range.max
                    elif isinstance(numeric_range, dict):
                        min_val = numeric_range.get("min")
                        max_val = numeric_range.get("max")
                    else:
                        min_val = None
                        max_val = None

                    if min_val is not None and max_val is not None:
                        return f"""SELECT DISTINCT p.person_id
FROM person p
WHERE EXTRACT(YEAR FROM AGE(@reference_date, p.birth_datetime)) BETWEEN {min_val} AND {max_val}"""
                    elif min_val is not None:
                        return f"""SELECT DISTINCT p.person_id
FROM person p
WHERE EXTRACT(YEAR FROM AGE(@reference_date, p.birth_datetime)) >= {min_val}"""
                    elif max_val is not None:
                        return f"""SELECT DISTINCT p.person_id
FROM person p
WHERE EXTRACT(YEAR FROM AGE(@reference_date, p.birth_datetime)) <= {max_val}"""

                # Handle single age constraint (e.g., ">= 18")
                elif numeric_constraint:
                    # Handle both dict and dataclass objects
                    if hasattr(numeric_constraint, 'value') and not isinstance(numeric_constraint, dict):
                        value = numeric_constraint.value if numeric_constraint.value is not None else 18
                        operator = numeric_constraint.operator if hasattr(numeric_constraint, 'operator') and numeric_constraint.operator else ">="
                    elif isinstance(numeric_constraint, dict):
                        value = numeric_constraint.get("value", 18)
                        operator = numeric_constraint.get("operator", ">=")
                    else:
                        value = 18
                        operator = ">="
                    op_map = {"≥": ">=", "≤": "<=", ">": ">", "<": "<", "=": "="}
                    sql_op = op_map.get(operator, operator)
                    return f"""SELECT DISTINCT p.person_id
FROM person p
WHERE EXTRACT(YEAR FROM AGE(@reference_date, p.birth_datetime)) {sql_op} {value}"""

            # Use reference-data-driven gender detection
            is_gender, detected_gender = self._is_gender_criterion(atomic_text)
            if is_gender and detected_gender:
                concept_id = self._get_gender_concept_id(detected_gender)
                gender_name = detected_gender.upper()
                return f"""SELECT DISTINCT p.person_id
FROM person p
WHERE p.gender_concept_id = {concept_id}  -- {gender_name}"""

            return f"""SELECT DISTINCT o.person_id
FROM observation o
WHERE o.observation_concept_id {concept_clause}{time_clause}"""

        elif omop_table == "procedure_occurrence":
            return f"""SELECT DISTINCT po.person_id
FROM procedure_occurrence po
WHERE po.procedure_concept_id {concept_clause}{time_clause}"""

        elif omop_table == "device_exposure":
            return f"""SELECT DISTINCT de.person_id
FROM device_exposure de
WHERE de.device_concept_id {concept_clause}{time_clause}"""

        else:
            return f"""-- Unknown table: {omop_table}
-- Atomic text: {atomic_text}
-- Requires manual SQL generation"""

    def _get_date_column(self, omop_table: str) -> str:
        """Get the date column for each OMOP table."""
        date_columns = {
            "condition_occurrence": "co.condition_start_date",
            "drug_exposure": "de.drug_exposure_start_date",
            "measurement": "m.measurement_date",
            "observation": "o.observation_date",
            "procedure_occurrence": "po.procedure_date",
            "device_exposure": "de.device_exposure_start_date",
        }
        return date_columns.get(omop_table, "start_date")

    def _build_numeric_clause(
        self,
        numeric_constraint: Any,
        numeric_range: Any,
        omop_table: str
    ) -> str:
        """Build numeric constraint clause for measurements.

        Handles both:
        - numericConstraintStructured: single value with operator (e.g., >= 18)
        - numericRangeStructured: range with min/max (e.g., ECOG 0-1, HbA1c 9-13%)

        Args:
            numeric_constraint: Single value constraint {value, operator, unit, parameter}
            numeric_range: Range constraint {min, max, unit, parameter}
            omop_table: OMOP table name (affects column name)

        Returns:
            SQL clause string (e.g., "\n  AND m.value_as_number >= 18")
        """
        if omop_table != "measurement":
            return ""

        # Map of Unicode operators to SQL operators
        op_map = {"≥": ">=", "≤": "<=", ">": ">", "<": "<", "=": "=", ">=": ">=", "<=": "<="}

        # Handle numericRangeStructured (BETWEEN min AND max)
        if numeric_range:
            if hasattr(numeric_range, 'min') and not isinstance(numeric_range, dict):
                min_val = numeric_range.min
                max_val = numeric_range.max
            elif isinstance(numeric_range, dict):
                min_val = numeric_range.get("min")
                max_val = numeric_range.get("max")
            else:
                min_val = None
                max_val = None

            if min_val is not None and max_val is not None:
                return f"\n  AND m.value_as_number BETWEEN {min_val} AND {max_val}"
            elif min_val is not None:
                return f"\n  AND m.value_as_number >= {min_val}"
            elif max_val is not None:
                return f"\n  AND m.value_as_number <= {max_val}"

        # Handle numericConstraintStructured (single value with operator)
        if numeric_constraint:
            if hasattr(numeric_constraint, 'value') and not isinstance(numeric_constraint, dict):
                value = numeric_constraint.value
                operator = numeric_constraint.operator if hasattr(numeric_constraint, 'operator') and numeric_constraint.operator else ">="
            elif isinstance(numeric_constraint, dict):
                value = numeric_constraint.get("value")
                operator = numeric_constraint.get("operator", ">=")
            else:
                value = None
                operator = ">="

            sql_op = op_map.get(operator, operator)
            if value is not None:
                return f"\n  AND m.value_as_number {sql_op} {value}"

        return ""

    # =========================================================================
    # EXPRESSION TREE SQL GENERATION (Phase 1 & 2)
    # =========================================================================

    def _generate_expression_tree_sql(
        self,
        expression: Dict[str, Any],
        concept_lookup: Dict[Tuple[str, str], Dict],
        criterion_id: str,
        criterion_type: str = "Inclusion"
    ) -> str:
        """
        Recursively generate SQL from an expression tree.

        Handles:
        - Phase 1: AND, OR, NOT, EXCEPT operators
        - Phase 2: WITHIN, BEFORE, AFTER temporal operators

        Args:
            expression: Expression tree node (dict)
            concept_lookup: Map of (criterion_id, atomic_id) -> {concept_ids: [...]}
            criterion_id: Parent criterion ID for lookup
            criterion_type: "Inclusion" or "Exclusion"

        Returns:
            SQL query string
        """
        node_type = expression.get("nodeType", "atomic")
        node_id = expression.get("nodeId", "")

        if node_type == "atomic":
            return self._generate_atomic_sql_from_tree(
                expression, concept_lookup, criterion_id
            )

        elif node_type == "operator":
            return self._generate_operator_sql(
                expression, concept_lookup, criterion_id, criterion_type
            )

        elif node_type == "temporal":
            return self._generate_temporal_sql(
                expression, concept_lookup, criterion_id
            )

        else:
            return f"-- Unknown node type: {node_type}"

    def _generate_atomic_sql_from_tree(
        self,
        node: Dict[str, Any],
        concept_lookup: Dict[Tuple[str, str], Dict],
        criterion_id: str
    ) -> str:
        """Generate SQL for an atomic node in the expression tree."""
        atomic_id = node.get("nodeId", "")
        atomic_text = node.get("atomicText", "")
        omop_table = node.get("omopTable", "observation")

        numeric_constraint = node.get("numericConstraintStructured")
        numeric_range = node.get("numericRangeStructured")
        time_frame = node.get("timeFrameStructured")

        # Get concept IDs from lookup
        key = (criterion_id, atomic_id)
        concept_info = concept_lookup.get(key, {})
        concept_ids = concept_info.get("concept_ids", [])

        return self._generate_table_specific_sql(
            omop_table, concept_ids, numeric_constraint, time_frame, atomic_text,
            numeric_range=numeric_range
        )

    def _generate_operator_sql(
        self,
        node: Dict[str, Any],
        concept_lookup: Dict[Tuple[str, str], Dict],
        criterion_id: str,
        criterion_type: str
    ) -> str:
        """Generate SQL for an operator node (AND, OR, NOT, EXCEPT)."""
        operator = node.get("operator", "AND")
        operands = node.get("operands", [])

        if not operands:
            return "-- No operands in operator node"

        # Recursively generate SQL for each operand
        operand_sqls = []
        for operand in operands:
            sql = self._generate_expression_tree_sql(
                operand, concept_lookup, criterion_id, criterion_type
            )
            if sql and not sql.startswith("--"):
                operand_sqls.append(sql)

        if not operand_sqls:
            return "-- No valid SQL from operands"

        if operator == "AND":
            # INTERSECT all operand queries
            if len(operand_sqls) == 1:
                return operand_sqls[0]
            return "\nINTERSECT\n".join([f"({sql})" for sql in operand_sqls])

        elif operator == "OR":
            # UNION all operand queries
            if len(operand_sqls) == 1:
                return operand_sqls[0]
            return "\nUNION\n".join([f"({sql})" for sql in operand_sqls])

        elif operator == "NOT":
            # EXCEPT from all patients
            if len(operand_sqls) != 1:
                return "-- NOT operator requires exactly 1 operand"
            return f"""SELECT person_id FROM person
EXCEPT
({operand_sqls[0]})"""

        elif operator == "EXCEPT":
            # First operand minus second operand
            if len(operand_sqls) != 2:
                return "-- EXCEPT operator requires exactly 2 operands"
            return f"""({operand_sqls[0]})
EXCEPT
({operand_sqls[1]})"""

        else:
            return f"-- Unknown operator: {operator}"

    def _generate_temporal_sql(
        self,
        node: Dict[str, Any],
        concept_lookup: Dict[Tuple[str, str], Dict],
        criterion_id: str
    ) -> str:
        """Generate SQL for a temporal constraint node.

        Temporal constraints apply time windows relative to anchor events
        (screening, first_dose, randomization, reference_date).

        The implementation injects the temporal filter directly into the
        atomic SQL rather than using CTEs, as the underlying OMOP query
        already has access to the date columns.
        """
        temporal_constraint = node.get("temporalConstraint", {})
        operand = node.get("operand")

        if not operand:
            return "-- Temporal node has no operand"

        if not temporal_constraint:
            # No temporal constraint, just generate operand SQL
            return self._generate_expression_tree_sql(
                operand, concept_lookup, criterion_id, "Inclusion"
            )

        # Extract temporal parameters
        temp_operator = temporal_constraint.get("operator", "WITHIN")
        value = temporal_constraint.get("value")
        unit = temporal_constraint.get("unit", "days")
        anchor = temporal_constraint.get("anchor", "reference_date")
        anchor_end = temporal_constraint.get("anchorEnd")

        # Map anchor to SQL variable (users will replace @anchor_name with actual dates)
        anchor_var = f"@{anchor}" if anchor else "@reference_date"

        # Determine the OMOP table from the operand to get correct date column
        omop_table = operand.get("omopTable", "observation") if operand.get("nodeType") == "atomic" else "observation"
        date_column = self._get_date_column(omop_table)

        # Build time window clause based on operator
        if temp_operator.upper() == "WITHIN":
            if value and unit:
                interval = f"INTERVAL '{value} {unit}'"
                # WITHIN means condition occurred within X time of anchor (before or after)
                time_condition = f"{date_column} BETWEEN {anchor_var} - {interval} AND {anchor_var} + {interval}"
            else:
                time_condition = f"{date_column} IS NOT NULL"

        elif temp_operator.upper() == "BEFORE":
            if value and unit:
                interval = f"INTERVAL '{value} {unit}'"
                # Condition occurred within X time BEFORE the anchor
                time_condition = f"{date_column} BETWEEN {anchor_var} - {interval} AND {anchor_var}"
            else:
                # Just before the anchor (no time limit)
                time_condition = f"{date_column} < {anchor_var}"

        elif temp_operator.upper() == "AFTER":
            if value and unit:
                interval = f"INTERVAL '{value} {unit}'"
                # Condition occurred within X time AFTER the anchor
                time_condition = f"{date_column} BETWEEN {anchor_var} AND {anchor_var} + {interval}"
            else:
                # Just after the anchor (no time limit)
                time_condition = f"{date_column} > {anchor_var}"

        elif temp_operator.upper() == "BETWEEN":
            # Between two anchor events
            anchor_end_var = f"@{anchor_end}" if anchor_end else f"{anchor_var} + INTERVAL '1 day'"
            time_condition = f"{date_column} BETWEEN {anchor_var} AND {anchor_end_var}"

        else:
            # Unknown temporal operator, return base SQL without temporal filter
            return self._generate_expression_tree_sql(
                operand, concept_lookup, criterion_id, "Inclusion"
            )

        # Generate the operand SQL and inject temporal filter
        # For atomic nodes, we can inject directly; for complex nodes, use CTE approach
        if operand.get("nodeType") == "atomic":
            # Generate atomic SQL with temporal constraint injected
            return self._generate_atomic_sql_with_temporal(
                operand, concept_lookup, criterion_id, time_condition, temp_operator, value, unit, anchor
            )
        else:
            # For complex operands (nested operators), use CTE approach
            base_sql = self._generate_expression_tree_sql(
                operand, concept_lookup, criterion_id, "Inclusion"
            )
            return f"""-- Temporal constraint: {temp_operator} {value or ''} {unit or ''} of {anchor}
-- Note: For complex nested operands, temporal filter applied at outer level
WITH temporal_base AS (
{base_sql}
)
SELECT DISTINCT person_id
FROM temporal_base
WHERE EXISTS (
    -- Verify temporal constraint is met
    -- This requires joining back to source table with date filtering
    SELECT 1 WHERE {time_condition.replace(date_column, anchor_var)}
)"""

    def _generate_atomic_sql_with_temporal(
        self,
        node: Dict[str, Any],
        concept_lookup: Dict[Tuple[str, str], Dict],
        criterion_id: str,
        time_condition: str,
        temp_operator: str,
        value: Any,
        unit: str,
        anchor: str
    ) -> str:
        """Generate SQL for an atomic node with temporal constraint injected."""
        atomic_id = node.get("nodeId", "")
        atomic_text = node.get("atomicText", "")
        omop_table = node.get("omopTable", "observation")

        numeric_constraint = node.get("numericConstraintStructured")
        numeric_range = node.get("numericRangeStructured")

        # Get concept IDs from lookup
        key = (criterion_id, atomic_id)
        concept_info = concept_lookup.get(key, {})
        concept_ids = concept_info.get("concept_ids", [])

        # Format concept IDs clause
        if concept_ids:
            concept_clause = f"IN ({', '.join(str(c) for c in concept_ids)})"
        else:
            concept_clause = "IN (/* UNMAPPED - requires manual concept selection */)"

        # Build numeric constraint clause
        numeric_clause = self._build_numeric_clause(numeric_constraint, numeric_range, omop_table)

        # Add temporal comment
        temporal_comment = f"-- Temporal: {temp_operator} {value or ''} {unit or ''} of {anchor}"

        # Generate table-specific SQL with temporal filter
        if omop_table == "condition_occurrence":
            return f"""{temporal_comment}
SELECT DISTINCT co.person_id
FROM condition_occurrence co
WHERE co.condition_concept_id {concept_clause}
  AND {time_condition}"""

        elif omop_table == "drug_exposure":
            return f"""{temporal_comment}
SELECT DISTINCT de.person_id
FROM drug_exposure de
WHERE de.drug_concept_id {concept_clause}
  AND {time_condition}"""

        elif omop_table == "measurement":
            return f"""{temporal_comment}
SELECT DISTINCT m.person_id
FROM measurement m
WHERE m.measurement_concept_id {concept_clause}{numeric_clause}
  AND {time_condition}"""

        elif omop_table == "observation":
            return f"""{temporal_comment}
SELECT DISTINCT o.person_id
FROM observation o
WHERE o.observation_concept_id {concept_clause}
  AND {time_condition}"""

        elif omop_table == "procedure_occurrence":
            return f"""{temporal_comment}
SELECT DISTINCT po.person_id
FROM procedure_occurrence po
WHERE po.procedure_concept_id {concept_clause}
  AND {time_condition}"""

        elif omop_table == "device_exposure":
            return f"""{temporal_comment}
SELECT DISTINCT de.person_id
FROM device_exposure de
WHERE de.device_concept_id {concept_clause}
  AND {time_condition}"""

        else:
            return f"""-- Unknown table: {omop_table} with temporal constraint
-- Atomic text: {atomic_text}
-- {temporal_comment}
-- Requires manual SQL generation"""

    def _combine_sql_components(
        self,
        components: List[Dict],
        operator: str,
        criterion_type: str,
        is_subquery: bool = False
    ) -> str:
        """Combine SQL components with AND/OR logic."""
        if not components:
            return "-- No SQL components generated"

        valid_sqls = [c["sql"] for c in components if c.get("sql") and not c["sql"].startswith("--")]

        if not valid_sqls:
            return "-- No valid SQL components"

        if len(valid_sqls) == 1:
            return valid_sqls[0]

        # For inclusion criteria: INTERSECT (AND)
        # For exclusion criteria: Patients NOT IN the set
        if operator == "AND":
            combined = "\nINTERSECT\n".join([f"({sql})" for sql in valid_sqls])
        else:  # OR
            combined = "\nUNION\n".join([f"({sql})" for sql in valid_sqls])

        if criterion_type == "Exclusion":
            return f"""-- EXCLUSION: Exclude patients matching this criterion
SELECT person_id FROM person
WHERE person_id NOT IN (
{combined}
)"""

        return combined

    def _combine_option_sqls(
        self,
        option_sqls: List[Dict],
        criterion_type: str
    ) -> str:
        """Combine OR-logic options."""
        if not option_sqls:
            return "-- No option SQL components"

        # Options are ORed together (UNION)
        valid_options = [opt for opt in option_sqls if opt.get("sql") and not opt["sql"].startswith("--")]

        if not valid_options:
            return "-- No valid option SQL components"

        combined = "\nUNION\n".join([f"-- Option {opt['optionId']}\n({opt['sql']})" for opt in valid_options])

        if criterion_type == "Exclusion":
            return f"""-- EXCLUSION: Exclude patients matching ANY option
SELECT person_id FROM person
WHERE person_id NOT IN (
{combined}
)"""

        return f"""-- Include patients matching ANY option (OR-logic)
{combined}"""

    def _ensure_usdm_compliance(
        self,
        decomposed: Any,
        omop_mappings: Dict[str, Any],
        protocol_id: str
    ) -> Dict[str, Any]:
        """Stage 7: Ensure USDM 4.0 compliance."""
        usdm_criteria = []

        if decomposed and hasattr(decomposed, "decomposed_criteria"):
            for dc in decomposed.decomposed_criteria:
                usdm_crit = {
                    "id": f"EC-{dc.criterion_id}",
                    "name": f"{dc.criterion_type} Criterion {dc.criterion_id}",
                    "text": dc.original_text,
                    "category": {
                        "code": "C25532" if dc.criterion_type == "Inclusion" else "C25370",
                        "decode": f"{dc.criterion_type} Criteria",
                        "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
                        "codeSystemVersion": "24.12",
                        "instanceType": "Code",
                    },
                    "identifier": dc.criterion_id,
                    "instanceType": "EligibilityCriterion",
                    "provenance": dc.provenance,
                }
                usdm_criteria.append(usdm_crit)

        return {"criteria": usdm_criteria}

    def _assign_tiers(self, usdm_criteria: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 8: Assign criticality tiers."""
        tier_assignments = {"tier1": [], "tier2": [], "tier3": []}

        for crit in usdm_criteria.get("criteria", []):
            # Simple heuristic - would be more sophisticated
            tier_assignments["tier1"].append(crit.get("id"))

        return tier_assignments

    def _assemble_review_package(
        self,
        accumulated_data: Dict[str, Any],
        config: PipelineConfig
    ) -> Dict[str, Any]:
        """Stage 9: Assemble human review package."""
        return {
            "protocolId": config.protocol_id,
            "protocolName": config.protocol_name,
            "reviewItems": [],
            "autoApproved": [],
            "statistics": {
                "totalCriteria": len(accumulated_data.get("raw_criteria", [])),
            },
        }

    def _generate_final_output(
        self,
        accumulated_data: Dict[str, Any],
        config: PipelineConfig
    ) -> Dict[str, Any]:
        """Stage 10: Generate final output."""
        return {
            "eligibilityCriteria": accumulated_data.get("usdm_criteria", {}).get("criteria", []),
            "sqlTemplates": accumulated_data.get("sql_templates", {}),
            "tierAssignments": accumulated_data.get("tier_assignments", {}),
            "isDraft": config.draft_mode,
        }

    async def _run_feasibility_analysis(
        self,
        accumulated_data: Dict[str, Any],
        config: PipelineConfig
    ) -> Dict[str, Any]:
        """
        Stage 11: Run feasibility analysis to generate patient funnel.

        Uses the Stage11Feasibility class to:
        1. Classify criteria into funnel categories
        2. Normalize to ~10-15 key criteria (80/20 rule)
        3. Build patient funnel with sequential elimination
        4. Generate population estimates and optimization opportunities
        """
        from .stage11_feasibility import Stage11Feasibility

        # Build interpretation result structure for Stage 11 input
        interpretation_result = {
            "criteria": accumulated_data.get("raw_criteria", []),
            "decomposed_criteria": accumulated_data.get("decomposed_criteria"),
            "omop_mappings": accumulated_data.get("omop_mappings"),
            "usdm_criteria": accumulated_data.get("usdm_criteria"),
        }

        # Initialize and run Stage 11
        stage11 = Stage11Feasibility(
            output_dir=config.output_dir,
            population_base=1000000,  # Default US population base
        )

        result = await stage11.run(
            interpretation_result=interpretation_result,
            protocol_id=config.protocol_id or "UNKNOWN",
        )

        return result

    async def _run_qeb_builder(
        self,
        accumulated_data: Dict[str, Any],
        config: PipelineConfig
    ) -> Dict[str, Any]:
        """
        Stage 12: Run QEB Builder to create Queryable Eligibility Blocks.

        Uses the Stage12QEBBuilder class to:
        1. Group atomics by original criterion ID
        2. Build combined SQL from expression trees
        3. Generate clinical names using LLM
        4. Cluster into funnel stages using LLM
        5. Assess queryable status and identify killer criteria
        """
        from .stage12_qeb_builder import Stage12QEBBuilder

        # Get eligibility funnel from Stage 11
        feasibility_result = accumulated_data.get("feasibility_result", {})
        funnel_result = feasibility_result.get("funnel_result", {})

        # If funnel_result has no atomicCriteria, try to load from eligibility_funnel.json
        # Note: V1 funnel (from Stage 11 run()) has keyCriteria but no atomics
        # V2 funnel (from eligibility_funnel.json) has atomicCriteria that Stage 12 needs
        if not funnel_result.get("atomicCriteria") and config.output_dir:
            funnel_file = config.output_dir / f"{config.protocol_id}_eligibility_funnel.json"
            if funnel_file.exists():
                try:
                    with open(funnel_file, "r", encoding="utf-8") as f:
                        funnel_result = json.load(f)
                    logger.info(f"Loaded eligibility funnel from {funnel_file}")
                except Exception as e:
                    logger.warning(f"Failed to load eligibility funnel: {e}")
            else:
                # File doesn't exist in current output dir (cache hit scenario)
                # Look in sibling directories (previous runs) for the funnel file
                parent_dir = config.output_dir.parent
                if parent_dir.exists():
                    # Find all eligibility_funnel.json files in sibling directories
                    sibling_funnels = sorted(
                        parent_dir.glob(f"*/{config.protocol_id}_eligibility_funnel.json"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True  # Most recent first
                    )
                    if sibling_funnels:
                        try:
                            with open(sibling_funnels[0], "r", encoding="utf-8") as f:
                                funnel_result = json.load(f)
                            logger.info(f"Loaded eligibility funnel from previous run: {sibling_funnels[0]}")
                        except Exception as e:
                            logger.warning(f"Failed to load eligibility funnel from previous run: {e}")

        # Get Stage 2 result (decomposed criteria with expression trees)
        decomposed = accumulated_data.get("decomposed_criteria")
        stage2_result = {}
        if decomposed:
            if hasattr(decomposed, "to_dict"):
                stage2_result = decomposed.to_dict()
            elif isinstance(decomposed, dict):
                stage2_result = decomposed
            else:
                # Try to load from file
                if config.output_dir:
                    stage2_file = config.output_dir / "interpretation_stages" / "stage02_result.json"
                    if stage2_file.exists():
                        try:
                            with open(stage2_file, "r", encoding="utf-8") as f:
                                stage2_result = json.load(f)
                        except Exception as e:
                            logger.warning(f"Failed to load stage 2 result: {e}")

        # Get raw criteria
        raw_criteria = accumulated_data.get("raw_criteria", [])

        # Determine therapeutic area from protocol name, ID, or criteria content
        therapeutic_area = None
        protocol_name = (config.protocol_name or config.protocol_id or "").lower()

        # Define therapeutic area keywords
        oncology_terms = ["nsclc", "lung cancer", "non-small cell", "small cell", "oncolog",
                         "cancer", "tumor", "tumour", "carcinoma", "melanoma", "lymphoma",
                         "leukemia", "sarcoma", "metastatic", "malignant", "neoplasm",
                         "chemotherapy", "immunotherapy"]
        cardiology_terms = ["cardio", "heart", "cardiac", "myocardial", "coronary",
                           "arrhythmia", "atrial", "ventricular", "hypertension"]
        immunology_terms = ["immuno", "autoimmune", "rheumat", "lupus", "arthritis",
                           "multiple sclerosis", "crohn", "psoriasis"]

        # First check protocol name/ID
        if any(term in protocol_name for term in oncology_terms):
            therapeutic_area = "Oncology"
        elif any(term in protocol_name for term in cardiology_terms):
            therapeutic_area = "Cardiology"
        elif any(term in protocol_name for term in immunology_terms):
            therapeutic_area = "Immunology"

        # If not found, check raw criteria content
        if therapeutic_area is None and raw_criteria:
            criteria_text = " ".join([
                str(c.get("originalText", "") or c.get("text", "") or c.get("criterion_text", ""))
                for c in raw_criteria if isinstance(c, dict)
            ]).lower()

            if any(term in criteria_text for term in oncology_terms):
                therapeutic_area = "Oncology"
            elif any(term in criteria_text for term in cardiology_terms):
                therapeutic_area = "Cardiology"
            elif any(term in criteria_text for term in immunology_terms):
                therapeutic_area = "Immunology"

        # Initialize and run Stage 12
        stage12 = Stage12QEBBuilder(output_dir=config.output_dir)

        result = await stage12.run(
            eligibility_funnel=funnel_result,
            stage2_result=stage2_result,
            raw_criteria=raw_criteria,
            protocol_id=config.protocol_id or "UNKNOWN",
            therapeutic_area=therapeutic_area,
            eligibility_page_start=config.eligibility_page_start,
            eligibility_page_end=config.eligibility_page_end,
        )

        return result

    def _save_stage_result(
        self,
        stage_num: int,
        result: Any,
        output_dir: Path
    ) -> None:
        """Save stage result to file."""
        stages_dir = output_dir / "interpretation_stages"
        stages_dir.mkdir(parents=True, exist_ok=True)

        output_file = stages_dir / f"stage{stage_num:02d}_result.json"

        try:
            with open(output_file, "w") as f:
                if hasattr(result, "to_dict"):
                    json.dump(result.to_dict(), f, indent=2)
                elif isinstance(result, dict):
                    json.dump(result, f, indent=2)
                else:
                    json.dump({"result": str(result)}, f, indent=2)
            logger.debug(f"Saved stage {stage_num} result to {output_file}")
        except Exception as e:
            logger.warning(f"Failed to save stage {stage_num} result: {e}")

    def _save_feasibility_files_from_cache(
        self,
        feasibility_result: Dict[str, Any],
        protocol_id: str,
        output_dir: Path
    ) -> None:
        """
        Save feasibility files from cached Stage 11 result.

        When Stage 11 is served from cache, this method re-saves the
        funnel_result.json, key_criteria.json, and funnel_summary.json
        files to the current output directory.
        """
        from datetime import datetime

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Save full funnel result
            funnel_path = output_dir / f"{protocol_id}_funnel_result.json"
            with open(funnel_path, "w", encoding="utf-8") as f:
                json.dump(feasibility_result.get("funnel_result", feasibility_result), f, indent=2)
            logger.info(f"Saved funnel result (from cache) to: {funnel_path}")

            # Save key criteria summary
            key_criteria_data = {
                "protocol_id": protocol_id,
                "generated_at": datetime.utcnow().isoformat(),
                "key_criteria": []
            }

            # Extract key criteria from funnel_result
            funnel_data = feasibility_result.get("funnel_result", feasibility_result)
            if "keyCriteria" in funnel_data:
                for kc in funnel_data["keyCriteria"]:
                    key_criteria_data["key_criteria"].append({
                        "key_id": kc.get("keyId", ""),
                        "category": kc.get("category", ""),
                        "text": kc.get("normalizedText", ""),
                        "type": kc.get("criterionType", ""),
                        "queryable_status": kc.get("queryableStatus", ""),
                        "elimination_rate": kc.get("estimatedEliminationRate", 0),
                        "is_killer": kc.get("isKillerCriterion", False),
                        "funnel_priority": kc.get("funnelPriority", 99),
                    })

            key_criteria_path = output_dir / f"{protocol_id}_key_criteria.json"
            with open(key_criteria_path, "w", encoding="utf-8") as f:
                json.dump(key_criteria_data, f, indent=2)
            logger.info(f"Saved key criteria (from cache) to: {key_criteria_path}")

            # Save funnel summary
            summary_data = {
                "protocol_id": protocol_id,
                "generated_at": datetime.utcnow().isoformat(),
                "population": {},
                "funnel_stages": [],
                "killer_criteria": funnel_data.get("killerCriteria", []),
                "optimization_opportunities": [],
                "manual_assessment_required": funnel_data.get("manualAssessmentCriteria", []),
            }

            # Extract population estimates
            pop_est = funnel_data.get("populationEstimates", {})
            summary_data["population"] = {
                "initial": pop_est.get("initialPopulation", 0),
                "final_estimate": pop_est.get("finalEligibleEstimate", 0),
                "confidence_low": pop_est.get("confidenceInterval", {}).get("low", 0),
                "confidence_high": pop_est.get("confidenceInterval", {}).get("high", 0),
                "overall_elimination_rate": funnel_data.get("metadata", {}).get("overallEliminationRate", 0),
            }

            # Extract funnel stages
            for stage in funnel_data.get("funnelStages", []):
                summary_data["funnel_stages"].append({
                    "name": stage.get("stageName", ""),
                    "order": stage.get("stageOrder", 0),
                    "entering": stage.get("patientsEntering", 0),
                    "exiting": stage.get("patientsExiting", 0),
                    "elimination_rate": stage.get("eliminationRate", 0),
                    "criteria_count": stage.get("criteriaCount", 0),
                })

            summary_path = output_dir / f"{protocol_id}_funnel_summary.json"
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, indent=2)
            logger.info(f"Saved funnel summary (from cache) to: {summary_path}")

        except Exception as e:
            logger.warning(f"Failed to save feasibility files from cache: {e}")

    def _save_qeb_files_from_cache(
        self,
        qeb_result: Dict[str, Any],
        protocol_id: str,
        output_dir: Path
    ) -> None:
        """
        Save QEB files from cached Stage 12 result.

        When Stage 12 is served from cache, this method re-saves the
        qeb_output.json file to the current output directory.
        """
        from ..feasibility.qeb_models import save_qeb_output, QEBOutput

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Get the QEB output data
            qeb_output = qeb_result.get("qeb_output", qeb_result)

            # Save QEB output
            qeb_path = output_dir / f"{protocol_id}_qeb_output.json"
            with open(qeb_path, "w", encoding="utf-8") as f:
                json.dump(qeb_output, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved QEB output (from cache) to: {qeb_path}")

        except Exception as e:
            logger.warning(f"Failed to save QEB files from cache: {e}")


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================


async def run_interpretation_pipeline(
    raw_criteria: List[Dict[str, Any]],
    config: Optional[PipelineConfig] = None,
    resolved_references: Optional[Dict[str, str]] = None,
) -> PipelineResult:
    """
    Convenience function to run the interpretation pipeline.

    Args:
        raw_criteria: List of raw criteria from Phase 2
        config: Pipeline configuration
        resolved_references: Optional resolved cross-references

    Returns:
        PipelineResult
    """
    pipeline = InterpretationPipeline()
    return await pipeline.run(raw_criteria, config, resolved_references)
