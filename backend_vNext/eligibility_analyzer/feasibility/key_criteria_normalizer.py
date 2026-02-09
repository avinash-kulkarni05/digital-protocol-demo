"""
Key Criteria Normalizer - Select and prioritize ~10-15 key criteria.

This module implements the 80/20 rule for eligibility criteria:
- Identify the ~10-15 criteria that drive 80% of patient elimination
- Order criteria by elimination efficiency (highest impact first)
- Flag remaining criteria as secondary or requiring manual assessment
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from .data_models import (
    CriterionCategory,
    QueryableStatus,
    KeyCriterion,
    FunnelStageType,
    FunnelStage,
    PrevalenceEstimate,
)

logger = logging.getLogger(__name__)

# Target number of key criteria (80/20 rule)
TARGET_KEY_CRITERIA_COUNT = 15
MIN_KEY_CRITERIA_COUNT = 10
MAX_KEY_CRITERIA_COUNT = 20

# Configurable scoring weights (can be overridden by reference data)
DEFAULT_QUERYABILITY_WEIGHTS = {
    QueryableStatus.FULLY_QUERYABLE: 1.0,
    QueryableStatus.PARTIALLY_QUERYABLE: 0.7,
    QueryableStatus.REFERENCE_BASED: 0.5,
    QueryableStatus.NON_QUERYABLE: 0.2,
}

DEFAULT_CATEGORY_BONUS = {
    CriterionCategory.PRIMARY_ANCHOR: 0.2,
    CriterionCategory.BIOMARKER: 0.1,
    CriterionCategory.FUNCTIONAL: 0.05,
}

# Reference patterns for stage classification (configurable)
DEFAULT_PERFORMANCE_STATUS_PATTERNS = [
    "ecog", "karnofsky", "performance status", "ps =", "ps >=", "ps <="
]

DEFAULT_DEMOGRAPHIC_PATTERNS = [
    "age", "gender", "sex", "years old", "years of age", "adult", "pediatric",
    "male", "female", "woman", "man", "elderly"
]

# Elimination rate thresholds (configurable)
DEFAULT_ELIMINATION_THRESHOLDS = {
    CriterionCategory.FUNCTIONAL: 10.0,
    CriterionCategory.TREATMENT_HISTORY: 15.0,
    CriterionCategory.SAFETY_EXCLUSION: 10.0,
}

# Category to funnel stage mapping
CATEGORY_TO_STAGE: Dict[CriterionCategory, FunnelStageType] = {
    CriterionCategory.PRIMARY_ANCHOR: FunnelStageType.DISEASE_INDICATION,
    CriterionCategory.BIOMARKER: FunnelStageType.BIOMARKER_REQUIREMENTS,
    CriterionCategory.TREATMENT_HISTORY: FunnelStageType.TREATMENT_HISTORY,
    CriterionCategory.FUNCTIONAL: FunnelStageType.LAB_CRITERIA,
    CriterionCategory.SAFETY_EXCLUSION: FunnelStageType.SAFETY_EXCLUSIONS,
    CriterionCategory.ADMINISTRATIVE: FunnelStageType.SAFETY_EXCLUSIONS,
}

# Default funnel stage order
FUNNEL_STAGE_ORDER = [
    FunnelStageType.DISEASE_INDICATION,      # 1. Primary anchor - disease
    FunnelStageType.DEMOGRAPHICS,            # 2. Age, gender
    FunnelStageType.BIOMARKER_REQUIREMENTS,  # 3. Biomarkers
    FunnelStageType.TREATMENT_HISTORY,       # 4. Prior therapy
    FunnelStageType.PERFORMANCE_STATUS,      # 5. ECOG/Karnofsky
    FunnelStageType.LAB_CRITERIA,            # 6. Labs
    FunnelStageType.SAFETY_EXCLUSIONS,       # 7. Safety/comorbidities
]


class KeyCriteriaNormalizer:
    """
    Normalizes eligibility criteria to a prioritized set of key criteria.

    Implements:
    - Scoring criteria by elimination_power * queryability * data_availability
    - Selecting top 10-15 criteria that drive 80% elimination
    - Organizing criteria into funnel stages
    - Flagging non-queryable criteria for manual assessment
    """

    def __init__(
        self,
        reference_data_dir: Optional[Path] = None,
    ):
        """
        Initialize the normalizer.

        Args:
            reference_data_dir: Directory containing reference data files.
        """
        if reference_data_dir is None:
            reference_data_dir = Path(__file__).parent / "reference_data"
        self.reference_data_dir = reference_data_dir

        # Load reference data
        self.biomarker_frequencies = self._load_json("biomarker_frequencies.json")
        self.condition_prevalence = self._load_json("condition_prevalence.json")
        self.screen_fail_rates = self._load_json("screen_fail_rates.json")

        # Load configurable weights and patterns (or use defaults)
        scoring_config = self._load_json("scoring_config.json")
        self.queryability_weights = scoring_config.get("queryability_weights", DEFAULT_QUERYABILITY_WEIGHTS)
        self.category_bonus = scoring_config.get("category_bonus", DEFAULT_CATEGORY_BONUS)
        self.elimination_thresholds = scoring_config.get("elimination_thresholds", DEFAULT_ELIMINATION_THRESHOLDS)
        self.performance_status_patterns = scoring_config.get(
            "performance_status_patterns", DEFAULT_PERFORMANCE_STATUS_PATTERNS
        )
        self.demographic_patterns = scoring_config.get(
            "demographic_patterns", DEFAULT_DEMOGRAPHIC_PATTERNS
        )

        logger.info("KeyCriteriaNormalizer initialized")

    def _load_json(self, filename: str) -> Dict[str, Any]:
        """Load JSON reference data file."""
        path = self.reference_data_dir / filename
        if not path.exists():
            logger.warning(f"Reference file not found: {path}")
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _calculate_criterion_score(self, criterion: KeyCriterion) -> float:
        """
        Calculate composite score for criterion prioritization.

        Score = elimination_power * queryability_weight * data_availability

        Higher score = more impactful and queryable = higher priority.
        Uses configurable weights from reference data or defaults.
        """
        # Elimination power (0-1, from elimination rate)
        elimination_power = criterion.estimated_elimination_rate / 100.0

        # Queryability weight (configurable via reference data)
        queryability_weight = self.queryability_weights.get(criterion.queryable_status, 0.2)

        # Data availability (0-1)
        data_availability = criterion.data_availability_score

        # Bonus for certain categories (configurable via reference data)
        bonus = self.category_bonus.get(criterion.category, 0.0)

        score = (elimination_power * queryability_weight * max(data_availability, 0.3)) + bonus
        return score

    def _identify_killer_criteria(
        self,
        criteria: List[KeyCriterion],
        top_n: int = 8,
    ) -> List[str]:
        """
        Identify the top killer criteria by elimination impact.

        Args:
            criteria: List of key criteria.
            top_n: Number of killer criteria to identify.

        Returns:
            List of key criterion IDs.
        """
        # Sort by elimination rate (descending)
        sorted_criteria = sorted(
            criteria,
            key=lambda c: c.estimated_elimination_rate,
            reverse=True,
        )

        # Take top N queryable criteria
        killer_ids = []
        for c in sorted_criteria:
            if c.queryable_status in [QueryableStatus.FULLY_QUERYABLE, QueryableStatus.PARTIALLY_QUERYABLE]:
                killer_ids.append(c.key_id)
                if len(killer_ids) >= top_n:
                    break

        # Mark criteria as killer
        killer_set = set(killer_ids)
        for c in criteria:
            c.is_killer_criterion = c.key_id in killer_set

        return killer_ids

    def _assign_funnel_priority(self, criteria: List[KeyCriterion]) -> None:
        """
        Assign funnel priority to criteria based on category and score.

        Priority determines execution order:
        - 1-10: Primary anchors (disease, demographics)
        - 11-20: Biomarkers
        - 21-30: Treatment history
        - 31-40: Performance status
        - 41-50: Lab criteria
        - 51-60: Safety exclusions
        - 61+: Administrative/other
        """
        category_base_priority = {
            CriterionCategory.PRIMARY_ANCHOR: 1,
            CriterionCategory.BIOMARKER: 11,
            CriterionCategory.TREATMENT_HISTORY: 21,
            CriterionCategory.FUNCTIONAL: 31,
            CriterionCategory.SAFETY_EXCLUSION: 51,
            CriterionCategory.ADMINISTRATIVE: 61,
        }

        # Group by category
        by_category: Dict[CriterionCategory, List[KeyCriterion]] = {}
        for c in criteria:
            if c.category not in by_category:
                by_category[c.category] = []
            by_category[c.category].append(c)

        # Sort within each category by elimination rate (descending)
        for category, cat_criteria in by_category.items():
            base = category_base_priority.get(category, 70)
            sorted_cat = sorted(
                cat_criteria,
                key=lambda c: c.estimated_elimination_rate,
                reverse=True,
            )
            for i, c in enumerate(sorted_cat):
                c.funnel_priority = base + i

    def _group_into_stages(
        self,
        criteria: List[KeyCriterion],
    ) -> List[FunnelStage]:
        """
        Group criteria into funnel stages.

        Args:
            criteria: List of key criteria.

        Returns:
            List of funnel stages in execution order.
        """
        # Map category to stage type
        stage_criteria: Dict[FunnelStageType, List[KeyCriterion]] = {
            stage: [] for stage in FUNNEL_STAGE_ORDER
        }

        for c in criteria:
            # Special handling: split FUNCTIONAL into performance status vs labs
            # Uses configurable patterns from reference data
            if c.category == CriterionCategory.FUNCTIONAL:
                text_lower = c.normalized_text.lower()
                if any(term in text_lower for term in self.performance_status_patterns):
                    stage_criteria[FunnelStageType.PERFORMANCE_STATUS].append(c)
                else:
                    stage_criteria[FunnelStageType.LAB_CRITERIA].append(c)
            # Special handling: split PRIMARY_ANCHOR into disease vs demographics
            # Uses configurable patterns from reference data
            elif c.category == CriterionCategory.PRIMARY_ANCHOR:
                text_lower = c.normalized_text.lower()
                if any(term in text_lower for term in self.demographic_patterns):
                    stage_criteria[FunnelStageType.DEMOGRAPHICS].append(c)
                else:
                    stage_criteria[FunnelStageType.DISEASE_INDICATION].append(c)
            else:
                stage_type = CATEGORY_TO_STAGE.get(c.category, FunnelStageType.SAFETY_EXCLUSIONS)
                stage_criteria[stage_type].append(c)

        # Build stage objects
        stages = []
        for order, stage_type in enumerate(FUNNEL_STAGE_ORDER, start=1):
            stage_crit = stage_criteria.get(stage_type, [])
            if stage_crit:  # Only include non-empty stages
                # Sort criteria within stage by elimination rate
                stage_crit.sort(key=lambda c: c.estimated_elimination_rate, reverse=True)

                stage = FunnelStage(
                    stage_name=stage_type.value.replace("_", " ").title(),
                    stage_type=stage_type,
                    stage_order=order,
                    criteria=stage_crit,
                )
                stages.append(stage)

        return stages

    def _select_key_criteria(
        self,
        all_criteria: List[KeyCriterion],
        target_count: int = TARGET_KEY_CRITERIA_COUNT,
    ) -> Tuple[List[KeyCriterion], List[KeyCriterion]]:
        """
        Select key criteria from all classified criteria.

        Selection strategy:
        1. Always include all PRIMARY_ANCHOR criteria
        2. Include BIOMARKER criteria with high elimination
        3. Fill remaining slots with highest-scoring criteria
        4. Ensure category coverage

        Args:
            all_criteria: All classified criteria.
            target_count: Target number of key criteria.

        Returns:
            Tuple of (key_criteria, secondary_criteria).
        """
        # Calculate scores
        scored = [(c, self._calculate_criterion_score(c)) for c in all_criteria]
        scored.sort(key=lambda x: x[1], reverse=True)

        key_criteria = []
        secondary_criteria = []

        # Step 1: Always include PRIMARY_ANCHOR (disease indication)
        for c, score in scored:
            if c.category == CriterionCategory.PRIMARY_ANCHOR:
                key_criteria.append(c)

        # Step 2: Include queryable BIOMARKER criteria
        for c, score in scored:
            if c.category == CriterionCategory.BIOMARKER:
                if c.queryable_status != QueryableStatus.NON_QUERYABLE:
                    key_criteria.append(c)

        # Step 3: Include high-elimination FUNCTIONAL criteria (configurable threshold)
        functional_threshold = self.elimination_thresholds.get(CriterionCategory.FUNCTIONAL, 10.0)
        for c, score in scored:
            if c.category == CriterionCategory.FUNCTIONAL:
                if c.estimated_elimination_rate > functional_threshold:
                    key_criteria.append(c)

        # Step 4: Include high-elimination TREATMENT_HISTORY (configurable threshold)
        treatment_threshold = self.elimination_thresholds.get(CriterionCategory.TREATMENT_HISTORY, 15.0)
        for c, score in scored:
            if c.category == CriterionCategory.TREATMENT_HISTORY:
                if c.estimated_elimination_rate > treatment_threshold:
                    key_criteria.append(c)

        # Step 5: Include important SAFETY_EXCLUSION criteria (configurable threshold)
        safety_threshold = self.elimination_thresholds.get(CriterionCategory.SAFETY_EXCLUSION, 10.0)
        for c, score in scored:
            if c.category == CriterionCategory.SAFETY_EXCLUSION:
                if c.estimated_elimination_rate > safety_threshold and len(key_criteria) < target_count:
                    key_criteria.append(c)

        # Step 6: Fill remaining slots with highest-scoring criteria
        key_ids = {c.key_id for c in key_criteria}
        for c, score in scored:
            if c.key_id not in key_ids and len(key_criteria) < target_count:
                if c.queryable_status != QueryableStatus.NON_QUERYABLE:
                    key_criteria.append(c)
                    key_ids.add(c.key_id)

        # Remaining criteria are secondary
        for c, score in scored:
            if c.key_id not in key_ids:
                secondary_criteria.append(c)

        # Sort key criteria by funnel priority
        key_criteria.sort(key=lambda c: c.funnel_priority)

        logger.info(f"Selected {len(key_criteria)} key criteria, {len(secondary_criteria)} secondary")
        return key_criteria, secondary_criteria

    def normalize_criteria(
        self,
        classified_criteria: List[KeyCriterion],
    ) -> Tuple[List[KeyCriterion], List[FunnelStage], List[str], List[str]]:
        """
        Normalize criteria to key criteria and funnel stages.

        Args:
            classified_criteria: Criteria from classifier.

        Returns:
            Tuple of (key_criteria, funnel_stages, killer_ids, manual_assessment_ids).
        """
        logger.info(f"Normalizing {len(classified_criteria)} criteria")

        # Assign funnel priorities
        self._assign_funnel_priority(classified_criteria)

        # Select key criteria
        key_criteria, secondary = self._select_key_criteria(classified_criteria)

        # Identify killer criteria
        killer_ids = self._identify_killer_criteria(key_criteria)

        # Identify manual assessment criteria
        manual_assessment_ids = [
            c.key_id for c in classified_criteria
            if c.requires_manual_assessment or c.queryable_status == QueryableStatus.NON_QUERYABLE
        ]

        # Group into funnel stages
        funnel_stages = self._group_into_stages(key_criteria)

        logger.info(f"Normalized to {len(key_criteria)} key criteria in {len(funnel_stages)} stages")
        logger.info(f"Killer criteria: {killer_ids}")
        logger.info(f"Manual assessment required for {len(manual_assessment_ids)} criteria")

        return key_criteria, funnel_stages, killer_ids, manual_assessment_ids


def get_stage_name(stage_type: FunnelStageType) -> str:
    """Get human-readable stage name."""
    names = {
        FunnelStageType.DISEASE_INDICATION: "Disease Indication",
        FunnelStageType.DEMOGRAPHICS: "Demographics",
        FunnelStageType.BIOMARKER_REQUIREMENTS: "Biomarker Requirements",
        FunnelStageType.TREATMENT_HISTORY: "Treatment History",
        FunnelStageType.PERFORMANCE_STATUS: "Performance Status",
        FunnelStageType.LAB_CRITERIA: "Laboratory Criteria",
        FunnelStageType.SAFETY_EXCLUSIONS: "Safety Exclusions",
    }
    return names.get(stage_type, stage_type.value)
