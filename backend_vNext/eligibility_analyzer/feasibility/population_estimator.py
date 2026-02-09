"""
Population Estimator - Calculate patient population estimates.

This module provides comprehensive population estimation by:
1. Combining query-based and prevalence-based estimates
2. Calculating confidence intervals
3. Projecting screen failure rates
4. Supporting multi-site aggregation
"""

import json
import logging
import math
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING

from .data_models import (
    KeyCriterion,
    FunnelStage,
    PopulationEstimate,
    PrevalenceEstimate,
    CriterionCategory,
    QueryableStatus,
    SiteRanking,
)

if TYPE_CHECKING:
    from .data_adapters.base_adapter import BaseDataAdapter

logger = logging.getLogger(__name__)


class PopulationEstimator:
    """
    Estimates patient populations for feasibility analysis.

    Supports multiple estimation methods:
    - Query-based: Direct SQL/FHIR queries against EHR
    - Prevalence-based: Published population rates
    - Hybrid: Combination of query and prevalence
    """

    def __init__(
        self,
        reference_data_dir: Optional[Path] = None,
        default_confidence_level: float = 0.90,
    ):
        """
        Initialize the population estimator.

        Args:
            reference_data_dir: Directory containing reference data files.
            default_confidence_level: Default CI level (0.90 = 90% CI).
        """
        if reference_data_dir is None:
            reference_data_dir = Path(__file__).parent / "reference_data"
        self.reference_data_dir = reference_data_dir

        self.default_confidence_level = default_confidence_level

        # Load reference data
        self.biomarker_frequencies = self._load_json("biomarker_frequencies.json")
        self.condition_prevalence = self._load_json("condition_prevalence.json")
        self.screen_fail_rates = self._load_json("screen_fail_rates.json")

        logger.info("PopulationEstimator initialized")

    def _load_json(self, filename: str) -> Dict[str, Any]:
        """Load JSON reference data file."""
        path = self.reference_data_dir / filename
        if not path.exists():
            logger.warning(f"Reference file not found: {path}")
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _calculate_confidence_interval(
        self,
        count: int,
        total: int,
        confidence_level: float = 0.90,
        method: str = "prevalence",
    ) -> Tuple[int, int]:
        """
        Calculate confidence interval for population estimate.

        Args:
            count: Estimated count.
            total: Total population.
            confidence_level: Confidence level (e.g., 0.90 for 90%).
            method: Estimation method ("query" or "prevalence").

        Returns:
            Tuple of (lower_bound, upper_bound).
        """
        if count == 0 or total == 0:
            return (0, 0)

        # Use different uncertainty based on method
        if method == "query":
            # Query-based: narrower interval (±15%)
            uncertainty = 0.15
        elif method == "prevalence":
            # Prevalence-based: wider interval (±30%)
            uncertainty = 0.30
        else:
            # Hybrid: moderate interval (±20%)
            uncertainty = 0.20

        # Scale uncertainty by confidence level
        z_score = 1.645 if confidence_level >= 0.90 else 1.28

        lower = int(count * (1 - uncertainty * z_score))
        upper = int(count * (1 + uncertainty * z_score))

        # Ensure bounds are valid
        lower = max(0, lower)
        upper = min(total, upper)

        return (lower, upper)

    def estimate_disease_population(
        self,
        disease_key: str,
        base_population: int = 1000000,
        stage: Optional[str] = None,
    ) -> PopulationEstimate:
        """
        Estimate disease-specific population using prevalence data.

        Args:
            disease_key: Disease identifier (e.g., "NSCLC", "breast_cancer").
            base_population: Total population base.
            stage: Optional disease stage filter.

        Returns:
            PopulationEstimate with count and CI.
        """
        oncology_data = self.condition_prevalence.get("oncology", {})

        if disease_key not in oncology_data:
            logger.warning(f"Disease {disease_key} not found in reference data")
            # Return conservative estimate
            return PopulationEstimate(
                count=int(base_population * 0.001),  # 0.1% default
                confidence_low=int(base_population * 0.0005),
                confidence_high=int(base_population * 0.002),
                estimation_method="prevalence",
                data_sources=["default_estimate"],
                notes=f"Disease {disease_key} not in reference data",
            )

        disease_data = oncology_data[disease_key]
        prevalence_per_100k = disease_data.get("prevalence_per_100k", 10)
        prevalence_rate = prevalence_per_100k / 100000

        # Apply stage filter if specified
        if stage:
            stage_dist = disease_data.get("stage_distribution", {})
            stage_rate = stage_dist.get(stage, 1.0)
            prevalence_rate *= stage_rate

        count = int(base_population * prevalence_rate)
        lower, upper = self._calculate_confidence_interval(
            count, base_population, method="prevalence"
        )

        return PopulationEstimate(
            count=count,
            confidence_low=lower,
            confidence_high=upper,
            estimation_method="prevalence",
            data_sources=[f"condition_prevalence:{disease_key}"],
            notes=f"Prevalence: {prevalence_per_100k}/100k" + (f", stage: {stage}" if stage else ""),
        )

    def estimate_biomarker_population(
        self,
        tumor_type: str,
        biomarker: str,
        disease_population: int,
    ) -> PopulationEstimate:
        """
        Estimate biomarker-positive population within disease cohort.

        Args:
            tumor_type: Tumor type key.
            biomarker: Biomarker identifier.
            disease_population: Population with the disease.

        Returns:
            PopulationEstimate with count and CI.
        """
        tumor_data = self.biomarker_frequencies.get(tumor_type, {})
        biomarkers = tumor_data.get("biomarkers", {})

        if biomarker not in biomarkers:
            logger.warning(f"Biomarker {biomarker} not found for {tumor_type}")
            # Default 10% frequency
            frequency = 0.10
            source = "default_estimate"
        else:
            biomarker_data = biomarkers[biomarker]
            frequency = biomarker_data.get("frequency", 0.10)
            source = biomarker_data.get("source", "unknown")

        count = int(disease_population * frequency)

        # Use frequency range if available for CI
        if biomarker in biomarkers:
            freq_range = biomarkers[biomarker].get("frequency_range", {})
            lower = int(disease_population * freq_range.get("low", frequency * 0.7))
            upper = int(disease_population * freq_range.get("high", frequency * 1.3))
        else:
            lower, upper = self._calculate_confidence_interval(
                count, disease_population, method="prevalence"
            )

        return PopulationEstimate(
            count=count,
            confidence_low=lower,
            confidence_high=upper,
            estimation_method="prevalence",
            data_sources=[f"biomarker_frequencies:{tumor_type}:{biomarker}"],
            notes=f"{biomarker} frequency: {frequency:.1%} ({source})",
        )

    def apply_screen_fail_adjustment(
        self,
        population: int,
        criterion_category: CriterionCategory,
        criterion_subtype: Optional[str] = None,
    ) -> Tuple[int, float]:
        """
        Apply screen failure rate adjustment to population.

        Args:
            population: Current population count.
            criterion_category: Criterion category.
            criterion_subtype: Optional subtype for more specific rates.

        Returns:
            Tuple of (adjusted_population, elimination_rate).
        """
        rates = self.screen_fail_rates.get("oncology_phase3", {}).get("by_criterion_category", {})

        # Map category to screen fail data
        category_key = criterion_category.value

        if category_key == "functional":
            func_rates = rates.get("functional", {})
            if criterion_subtype == "ecog":
                rate = func_rates.get("ecog_status", {}).get("ecog_0_1", {}).get("typical_elimination", 0.20)
            elif criterion_subtype == "labs":
                rate = func_rates.get("lab_criteria", {}).get("typical_elimination", 0.25)
            else:
                rate = 0.20
        elif category_key == "safety_exclusion":
            safety_rates = rates.get("safety_exclusion", {})
            if criterion_subtype == "cns":
                rate = safety_rates.get("cns_metastases", {}).get("active_excluded", {}).get("typical_elimination", 0.15)
            elif criterion_subtype == "cardiac":
                rate = safety_rates.get("cardiac", {}).get("qtc_prolongation", {}).get("typical_elimination", 0.05)
            else:
                rate = 0.10
        elif category_key == "treatment_history":
            tx_rates = rates.get("treatment_history", {})
            if criterion_subtype == "first_line":
                rate = tx_rates.get("prior_lines", {}).get("first_line", {}).get("typical_elimination", 0.30)
            else:
                rate = 0.25
        elif category_key == "biomarker":
            # Biomarkers use specific frequencies, not screen fail rates
            rate = 0.0  # Already applied via biomarker frequencies
        elif category_key == "administrative":
            admin_rates = rates.get("administrative", {})
            rate = admin_rates.get("compliance_concerns", {}).get("typical_elimination", 0.05)
        else:
            rate = 0.10  # Default

        adjusted = int(population * (1 - rate))
        return adjusted, rate * 100

    def estimate_from_criteria(
        self,
        key_criteria: List[KeyCriterion],
        base_population: int = 1000000,
        data_adapter: Optional["BaseDataAdapter"] = None,
    ) -> PopulationEstimate:
        """
        Estimate final eligible population from key criteria.

        Applies criteria in funnel order using a combination of:
        - Query-based estimates (if adapter available)
        - Prevalence-based estimates
        - Screen failure adjustments

        Args:
            key_criteria: List of key criteria in funnel order.
            base_population: Starting population.
            data_adapter: Optional data adapter for queries.

        Returns:
            Final PopulationEstimate.
        """
        logger.info(f"Estimating population from {len(key_criteria)} criteria")

        current_population = base_population
        estimation_method = "prevalence"
        data_sources = []

        # Sort criteria by funnel priority
        sorted_criteria = sorted(key_criteria, key=lambda c: c.funnel_priority)

        for criterion in sorted_criteria:
            # Calculate elimination for this criterion
            elimination_rate = criterion.estimated_elimination_rate / 100.0

            if criterion.criterion_type == "inclusion":
                # Inclusion: patients must have this (elimination = those who don't)
                remaining_rate = 1 - elimination_rate
            else:
                # Exclusion: patients must NOT have this (elimination = those who do)
                remaining_rate = 1 - elimination_rate

            current_population = int(current_population * remaining_rate)
            data_sources.append(f"{criterion.key_id}:{criterion.category.value}")

            logger.debug(
                f"After {criterion.key_id}: {current_population:,} "
                f"(elimination: {elimination_rate:.1%})"
            )

        # Calculate confidence interval
        lower, upper = self._calculate_confidence_interval(
            current_population, base_population, method=estimation_method
        )

        return PopulationEstimate(
            count=current_population,
            confidence_low=lower,
            confidence_high=upper,
            estimation_method=estimation_method,
            data_sources=data_sources,
            notes=f"Applied {len(key_criteria)} criteria sequentially",
        )

    def estimate_by_stage(
        self,
        funnel_stages: List[FunnelStage],
        initial_population: int,
    ) -> Dict[str, PopulationEstimate]:
        """
        Generate population estimates for each funnel stage.

        Args:
            funnel_stages: List of funnel stages.
            initial_population: Starting population.

        Returns:
            Dictionary mapping stage name to PopulationEstimate.
        """
        estimates = {}
        current_population = initial_population

        for stage in funnel_stages:
            stage_estimate = PopulationEstimate(
                count=stage.patients_exiting,
                confidence_low=int(stage.patients_exiting * 0.7),
                confidence_high=int(stage.patients_exiting * 1.3),
                estimation_method="prevalence",
                data_sources=[f"stage:{stage.stage_name}"],
                notes=f"Stage {stage.stage_order}: {stage.elimination_rate:.1f}% elimination",
            )
            estimates[stage.stage_name] = stage_estimate
            current_population = stage.patients_exiting

        return estimates

    def project_enrollment(
        self,
        eligible_population: int,
        enrollment_rate: float = 0.10,
        study_duration_months: int = 24,
        monthly_decay: float = 0.02,
    ) -> Dict[str, Any]:
        """
        Project enrollment over study duration.

        Args:
            eligible_population: Estimated eligible patients.
            enrollment_rate: Expected enrollment rate (fraction).
            study_duration_months: Study duration.
            monthly_decay: Rate at which enrollment decays.

        Returns:
            Enrollment projection dictionary.
        """
        projections = []
        cumulative = 0
        remaining = eligible_population

        for month in range(1, study_duration_months + 1):
            # Decay enrollment rate over time
            current_rate = enrollment_rate * (1 - monthly_decay) ** (month - 1)
            monthly_enrollment = int(remaining * current_rate)
            cumulative += monthly_enrollment
            remaining -= monthly_enrollment

            projections.append({
                "month": month,
                "monthly_enrollment": monthly_enrollment,
                "cumulative_enrollment": cumulative,
                "remaining_eligible": remaining,
            })

        return {
            "eligible_population": eligible_population,
            "enrollment_rate": enrollment_rate,
            "study_duration_months": study_duration_months,
            "projected_total_enrollment": cumulative,
            "monthly_projections": projections,
        }

    def rank_sites(
        self,
        site_results: List[Dict[str, Any]],
    ) -> List[SiteRanking]:
        """
        Rank sites by feasibility score.

        Args:
            site_results: List of site data with population estimates.

        Returns:
            Sorted list of SiteRanking objects.
        """
        rankings = []

        for site_data in site_results:
            site_id = site_data.get("site_id", "unknown")
            site_name = site_data.get("site_name", site_id)
            eligible = site_data.get("eligible_patients", 0)
            initial = site_data.get("initial_population", 0)
            data_completeness = site_data.get("data_completeness", 0.5)
            queryable_pct = site_data.get("queryable_criteria_percent", 50)

            # Calculate composite score
            # Weight: 60% eligible patients, 20% data completeness, 20% queryability
            if initial > 0:
                eligibility_score = (eligible / initial) * 100
            else:
                eligibility_score = 0

            score = (
                eligibility_score * 0.60 +
                data_completeness * 100 * 0.20 +
                queryable_pct * 0.20
            )

            estimate = PopulationEstimate(
                count=eligible,
                confidence_low=int(eligible * 0.7),
                confidence_high=int(eligible * 1.3),
                estimation_method="hybrid",
            )

            ranking = SiteRanking(
                site_id=site_id,
                site_name=site_name,
                initial_population=initial,
                final_eligible_estimate=estimate,
                rank=0,  # Will be set after sorting
                score=score,
                data_completeness_score=data_completeness,
                queryable_criteria_percent=queryable_pct,
            )
            rankings.append(ranking)

        # Sort by score (descending) and assign ranks
        rankings.sort(key=lambda r: r.score, reverse=True)
        for i, ranking in enumerate(rankings):
            ranking.rank = i + 1

        return rankings
