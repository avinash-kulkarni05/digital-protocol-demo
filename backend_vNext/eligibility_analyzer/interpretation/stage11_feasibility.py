"""
Stage 11: Feasibility Analysis - Patient Funnel Generation.

This stage takes the extracted and interpreted eligibility criteria and:
1. Classifies criteria into funnel categories (LLM-based)
2. Normalizes to ~10-15 key criteria (80/20 rule)
3. Builds patient funnel with sequential elimination
4. Generates population estimates and optimization opportunities
5. Generates V2 queryable funnel with atomic criteria and FHIR queries
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# Import feasibility module components
from ..feasibility import (
    CriterionCategory,
    QueryableStatus,
    KeyCriterion,
    FunnelStage,
    FunnelResult,
    PopulationEstimate,
)
from ..feasibility.criterion_classifier import CriterionClassifier, load_criteria_from_extraction
from ..feasibility.key_criteria_normalizer import KeyCriteriaNormalizer
from ..feasibility.population_estimator import PopulationEstimator
from ..feasibility.eligibility_funnel_builder import (
    EligibilityFunnelBuilder,
    save_eligibility_funnel,
)

logger = logging.getLogger(__name__)


class Stage11Feasibility:
    """
    Stage 11: Patient Funnel and Feasibility Analysis.

    Generates site feasibility insights from eligibility criteria by:
    - Classifying criteria into clinically meaningful categories
    - Selecting key criteria that drive 80% of patient elimination
    - Building a sequential patient funnel
    - Estimating final eligible population
    - Identifying protocol optimization opportunities
    """

    STAGE_NUMBER = 11
    STAGE_NAME = "Feasibility Analysis"

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        population_base: int = 1000000,
    ):
        """
        Initialize Stage 11.

        Args:
            output_dir: Directory for output files.
            population_base: Base population for estimation.
        """
        self.output_dir = output_dir
        self.population_base = population_base

        # Initialize components
        self.classifier = None
        self.normalizer = None
        self.funnel_builder = None
        self.population_estimator = None

        logger.info(f"Stage {self.STAGE_NUMBER} ({self.STAGE_NAME}) initialized")

    def _initialize_components(self) -> None:
        """Lazily initialize components when needed."""
        if self.classifier is None:
            self.classifier = CriterionClassifier()
        if self.normalizer is None:
            self.normalizer = KeyCriteriaNormalizer()
        # Note: Legacy funnel_builder (SyntheticFunnelBuilder) has been removed.
        # Use run_with_v2_funnel() or EligibilityFunnelBuilder directly instead.
        if self.population_estimator is None:
            self.population_estimator = PopulationEstimator()

    def _load_criteria_from_interpretation(
        self,
        interpretation_result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Extract criteria from interpretation pipeline result.

        Args:
            interpretation_result: Result from interpretation pipeline.

        Returns:
            List of criterion dictionaries.
        """
        criteria = interpretation_result.get("criteria", [])

        if not criteria:
            # Try alternative structure
            criteria = interpretation_result.get("eligibility_criteria", {}).get("criteria", [])

        if not criteria:
            logger.warning("No criteria found in interpretation result")
            return []

        logger.info(f"Loaded {len(criteria)} criteria from interpretation result")
        return criteria

    def _extract_omop_mappings(
        self,
        interpretation_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Extract OMOP mappings from interpretation result.

        Args:
            interpretation_result: Result from interpretation pipeline.

        Returns:
            Dictionary of OMOP mappings keyed by criterion_id.
        """
        omop_mappings = {}

        # Look for OMOP mappings in various locations
        mappings = interpretation_result.get("omop_mappings", {}).get("mappings", [])
        if not mappings:
            mappings = interpretation_result.get("concept_mappings", [])

        for mapping in mappings:
            criterion_id = mapping.get("criterion_id") or mapping.get("criterionId", "")
            if criterion_id:
                omop_mappings[criterion_id] = mapping

        logger.info(f"Extracted OMOP mappings for {len(omop_mappings)} criteria")
        return omop_mappings

    async def run(
        self,
        interpretation_result: Dict[str, Any],
        protocol_id: str,
        eligibility_json_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Execute Stage 11 feasibility analysis.

        Args:
            interpretation_result: Result from Stage 1-10 interpretation.
            protocol_id: Protocol identifier.
            eligibility_json_path: Optional path to eligibility_criteria.json.

        Returns:
            Stage result dictionary.
        """
        start_time = time.time()
        logger.info(f"Starting Stage {self.STAGE_NUMBER}: {self.STAGE_NAME}")

        try:
            # Initialize components
            self._initialize_components()

            # Step 1: Load criteria
            if eligibility_json_path and eligibility_json_path.exists():
                criteria, omop_mappings = load_criteria_from_extraction(eligibility_json_path)
            else:
                criteria = self._load_criteria_from_interpretation(interpretation_result)
                omop_mappings = self._extract_omop_mappings(interpretation_result)

            if not criteria:
                return {
                    "success": False,
                    "stage": self.STAGE_NUMBER,
                    "stage_name": self.STAGE_NAME,
                    "error": "No criteria found for feasibility analysis",
                    "duration_seconds": time.time() - start_time,
                }

            # Step 2: Classify criteria using LLM
            logger.info("Step 2: Classifying criteria into funnel categories")
            classified_criteria, classification_metadata = await self.classifier.classify_criteria(
                criteria=criteria,
                omop_mappings=omop_mappings,
            )

            # Step 3: Normalize to key criteria
            logger.info("Step 3: Normalizing to key criteria (80/20 rule)")
            key_criteria, funnel_stages, killer_ids, manual_ids = self.normalizer.normalize_criteria(
                classified_criteria=classified_criteria,
            )

            # Step 4: Build patient funnel
            # Note: Legacy V1 funnel builder (SyntheticFunnelBuilder) has been removed.
            # Use run_with_v2_funnel() instead for the new EligibilityFunnelBuilder.
            logger.warning(
                "Legacy V1 funnel builder is deprecated. "
                "Use run_with_v2_funnel() or the interpretation pipeline for EligibilityFunnelBuilder."
            )

            # Create a minimal result for backward compatibility
            funnel_result = FunnelResult(
                protocol_id=protocol_id,
                key_criteria=key_criteria,
                stages=funnel_stages,
                killer_criteria=killer_ids,
                manual_assessment_criteria=manual_ids,
                initial_population=self.population_base,
                final_eligible_estimate=PopulationEstimate(
                    count=0,
                    confidence_low=0,
                    confidence_high=0,
                    estimation_method="deprecated_v1_funnel",
                ),
                optimization_opportunities=[],
            )

            # Step 5: Save outputs
            if self.output_dir:
                await self._save_outputs(funnel_result, protocol_id)

            duration = time.time() - start_time
            logger.info(
                f"Stage {self.STAGE_NUMBER} complete in {duration:.2f}s: "
                f"{len(key_criteria)} key criteria (V1 funnel deprecated)"
            )

            return {
                "success": True,
                "stage": self.STAGE_NUMBER,
                "stage_name": self.STAGE_NAME,
                "duration_seconds": duration,
                "funnel_result": funnel_result.to_dict(),
                "summary": {
                    "protocol_id": protocol_id,
                    "total_criteria_analyzed": len(criteria),
                    "key_criteria_count": len(key_criteria),
                    "funnel_stages_count": len(funnel_stages),
                    "initial_population": funnel_result.initial_population,
                    "final_eligible_estimate": funnel_result.final_eligible_estimate.count,
                    "overall_elimination_rate": funnel_result.get_overall_elimination_rate(),
                    "killer_criteria": killer_ids,
                    "manual_assessment_count": len(manual_ids),
                    "optimization_opportunities_count": len(funnel_result.optimization_opportunities),
                },
                "classification_metadata": classification_metadata,
            }

        except Exception as e:
            logger.error(f"Stage {self.STAGE_NUMBER} failed: {e}", exc_info=True)
            return {
                "success": False,
                "stage": self.STAGE_NUMBER,
                "stage_name": self.STAGE_NAME,
                "error": str(e),
                "duration_seconds": time.time() - start_time,
            }

    def run_sync(
        self,
        interpretation_result: Dict[str, Any],
        protocol_id: str,
        eligibility_json_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Synchronous wrapper for run()."""
        import asyncio
        return asyncio.run(self.run(interpretation_result, protocol_id, eligibility_json_path))

    async def _save_outputs(self, funnel_result: FunnelResult, protocol_id: str) -> None:
        """Save feasibility outputs to files."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Save full funnel result (V1)
        funnel_path = self.output_dir / f"{protocol_id}_funnel_result.json"
        with open(funnel_path, "w", encoding="utf-8") as f:
            json.dump(funnel_result.to_dict(), f, indent=2)
        logger.info(f"Saved funnel result to: {funnel_path}")

        # Save key criteria summary
        key_criteria_path = self.output_dir / f"{protocol_id}_key_criteria.json"
        key_criteria_data = {
            "protocol_id": protocol_id,
            "generated_at": datetime.utcnow().isoformat(),
            "key_criteria": [
                {
                    "key_id": kc.key_id,
                    "category": kc.category.value,
                    "text": kc.normalized_text,
                    "type": kc.criterion_type,
                    "queryable_status": kc.queryable_status.value,
                    "elimination_rate": kc.estimated_elimination_rate,
                    "is_killer": kc.is_killer_criterion,
                    "funnel_priority": kc.funnel_priority,
                }
                for kc in funnel_result.key_criteria
            ],
        }
        with open(key_criteria_path, "w", encoding="utf-8") as f:
            json.dump(key_criteria_data, f, indent=2)
        logger.info(f"Saved key criteria to: {key_criteria_path}")

        # Save funnel summary (for quick review)
        summary_path = self.output_dir / f"{protocol_id}_funnel_summary.json"
        summary_data = {
            "protocol_id": protocol_id,
            "generated_at": datetime.utcnow().isoformat(),
            "population": {
                "initial": funnel_result.initial_population,
                "final_estimate": funnel_result.final_eligible_estimate.count,
                "confidence_low": funnel_result.final_eligible_estimate.confidence_low,
                "confidence_high": funnel_result.final_eligible_estimate.confidence_high,
                "overall_elimination_rate": funnel_result.get_overall_elimination_rate(),
            },
            "funnel_stages": [
                {
                    "name": stage.stage_name,
                    "order": stage.stage_order,
                    "entering": stage.patients_entering,
                    "exiting": stage.patients_exiting,
                    "elimination_rate": stage.elimination_rate,
                    "criteria_count": len(stage.criteria),
                }
                for stage in funnel_result.stages
            ],
            "killer_criteria": funnel_result.killer_criteria,
            "optimization_opportunities": [
                {
                    "criterion_id": opp.criterion_id,
                    "suggestion": opp.suggestion,
                    "impact": opp.potential_impact_percent,
                }
                for opp in funnel_result.optimization_opportunities
            ],
            "manual_assessment_required": funnel_result.manual_assessment_criteria,
        }
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2)
        logger.info(f"Saved funnel summary to: {summary_path}")

        # Generate V2 queryable funnel output (async LLM-powered)
        await self._generate_v2_funnel(protocol_id, key_criteria_data.get("key_criteria", []))

    async def _generate_v2_funnel(
        self,
        protocol_id: str,
        key_criteria: List[Dict[str, Any]],
    ) -> None:
        """
        Generate V2 queryable funnel output with atomic criteria and FHIR queries.

        This integrates Stage 2 (atomics), Stage 5 (OMOP mappings), and Stage 6 (SQL)
        to produce a funnel output suitable for drag-and-drop query execution.

        Uses LLM-first semantic matching for:
        - Category inference (replaces keyword patterns)
        - OMOP mapping selection (replaces Jaccard similarity)
        - Key criteria matching (replaces text matching)

        Args:
            protocol_id: Protocol identifier.
            key_criteria: Key criteria from V1 funnel for impact metrics.
        """
        stages_dir = self.output_dir / "interpretation_stages"

        # Check if required stage files exist
        stage2_path = stages_dir / "stage02_result.json"
        stage5_path = stages_dir / "stage05_result.json"
        stage6_path = stages_dir / "stage06_result.json"

        if not all([stage2_path.exists(), stage5_path.exists(), stage6_path.exists()]):
            logger.warning(
                "V2 funnel generation skipped: missing stage files. "
                f"Stage 2: {stage2_path.exists()}, Stage 5: {stage5_path.exists()}, "
                f"Stage 6: {stage6_path.exists()}"
            )
            return

        try:
            # Load stage outputs
            with open(stage2_path, "r", encoding="utf-8") as f:
                stage2_result = json.load(f)
            with open(stage5_path, "r", encoding="utf-8") as f:
                stage5_result = json.load(f)
            with open(stage6_path, "r", encoding="utf-8") as f:
                stage6_result = json.load(f)

            # Get ATHENA database path
            athena_db_path = os.environ.get('ATHENA_DB_PATH')

            # Build eligibility funnel using async LLM-powered matching
            builder = EligibilityFunnelBuilder(athena_db_path, use_llm=True)
            try:
                v2_result = await builder.build_from_stage_outputs(
                    protocol_id=protocol_id,
                    stage2_result=stage2_result,
                    stage5_result=stage5_result,
                    stage6_result=stage6_result,
                    key_criteria=key_criteria,
                )

                # Save eligibility funnel output
                v2_path = save_eligibility_funnel(v2_result, self.output_dir, protocol_id)
                logger.info(
                    f"Generated eligibility funnel (LLM-first): {len(v2_result.atomic_criteria)} atomics, "
                    f"{len(v2_result.logical_groups)} groups"
                )

            finally:
                builder.close()

        except Exception as e:
            logger.error(f"V2 funnel generation failed: {e}", exc_info=True)
            # V2 is optional - don't fail the whole stage


def run_stage11(
    interpretation_result: Dict[str, Any],
    protocol_id: str,
    output_dir: Optional[Path] = None,
    eligibility_json_path: Optional[Path] = None,
    population_base: int = 1000000,
) -> Dict[str, Any]:
    """
    Convenience function to run Stage 11 feasibility analysis.

    Args:
        interpretation_result: Result from Stage 1-10 interpretation.
        protocol_id: Protocol identifier.
        output_dir: Directory for output files.
        eligibility_json_path: Optional path to eligibility_criteria.json.
        population_base: Base population for estimation.

    Returns:
        Stage result dictionary.
    """
    stage = Stage11Feasibility(output_dir=output_dir, population_base=population_base)
    return stage.run_sync(interpretation_result, protocol_id, eligibility_json_path)
