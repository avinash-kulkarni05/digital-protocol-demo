"""
Synthetic Data Adapter - Prevalence-based population estimation.

This adapter provides patient population estimates using published
prevalence data when no EHR data source is available.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from .base_adapter import BaseDataAdapter, ConnectionConfig, QueryResult

logger = logging.getLogger(__name__)


class SyntheticAdapter(BaseDataAdapter):
    """
    Synthetic data adapter using prevalence-based estimation.

    Uses published prevalence data from reference files to estimate
    patient populations when EHR data is not available.
    """

    def __init__(
        self,
        population_size: int = 1000000,
        reference_data_dir: Optional[Path] = None,
    ):
        """
        Initialize synthetic adapter.

        Args:
            population_size: Assumed total population size.
            reference_data_dir: Directory containing reference data files.
        """
        super().__init__(config=None)

        self.population_size = population_size

        if reference_data_dir is None:
            reference_data_dir = Path(__file__).parent.parent / "reference_data"
        self.reference_data_dir = reference_data_dir

        # Load reference data
        self.biomarker_frequencies = self._load_json("biomarker_frequencies.json")
        self.condition_prevalence = self._load_json("condition_prevalence.json")
        self.screen_fail_rates = self._load_json("screen_fail_rates.json")

        self._connected = True  # Always "connected"
        logger.info(f"SyntheticAdapter initialized with population size: {population_size:,}")

    def _load_json(self, filename: str) -> Dict[str, Any]:
        """Load JSON reference data file."""
        path = self.reference_data_dir / filename
        if not path.exists():
            logger.warning(f"Reference file not found: {path}")
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def connect(self) -> bool:
        """Always returns True for synthetic adapter."""
        self._connected = True
        return True

    def disconnect(self) -> None:
        """No-op for synthetic adapter."""
        pass

    def get_total_population(self) -> int:
        """Get configured population size."""
        return self.population_size

    def _get_condition_prevalence(self, condition_key: str) -> float:
        """
        Get prevalence rate for a condition.

        Args:
            condition_key: Condition key (e.g., "NSCLC", "breast_cancer").

        Returns:
            Prevalence rate (0-1).
        """
        oncology_data = self.condition_prevalence.get("oncology", {})

        if condition_key in oncology_data:
            condition = oncology_data[condition_key]
            # Calculate from incidence and prevalence per 100k
            prevalence_per_100k = condition.get("prevalence_per_100k", 0)
            return prevalence_per_100k / 100000

        return 0.001  # Default very low prevalence

    def _get_biomarker_frequency(
        self,
        tumor_type: str,
        biomarker: str,
    ) -> float:
        """
        Get biomarker frequency for a tumor type.

        Args:
            tumor_type: Tumor type key (e.g., "NSCLC", "breast_cancer").
            biomarker: Biomarker key (e.g., "EGFR_mutation", "HER2_positive").

        Returns:
            Frequency rate (0-1).
        """
        tumor_data = self.biomarker_frequencies.get(tumor_type, {})
        biomarkers = tumor_data.get("biomarkers", {})

        if biomarker in biomarkers:
            return biomarkers[biomarker].get("frequency", 0.0)

        return 0.1  # Default 10% if unknown

    def _get_screen_fail_rate(
        self,
        criterion_type: str,
        subtype: Optional[str] = None,
    ) -> float:
        """
        Get screen failure rate for a criterion type.

        Args:
            criterion_type: Type of criterion.
            subtype: Specific subtype.

        Returns:
            Elimination rate (0-1).
        """
        rates = self.screen_fail_rates.get("oncology_phase3", {}).get("by_criterion_category", {})

        if criterion_type == "functional":
            func_rates = rates.get("functional", {})
            if subtype == "ecog":
                return func_rates.get("ecog_status", {}).get("ecog_0_1", {}).get("typical_elimination", 0.20)
            elif subtype == "labs":
                return func_rates.get("lab_criteria", {}).get("typical_elimination", 0.25)
            return 0.20

        if criterion_type == "safety_exclusion":
            safety_rates = rates.get("safety_exclusion", {})
            if subtype == "cns":
                return safety_rates.get("cns_metastases", {}).get("active_excluded", {}).get("typical_elimination", 0.15)
            elif subtype == "cardiac":
                return safety_rates.get("cardiac", {}).get("qtc_prolongation", {}).get("typical_elimination", 0.05)
            return 0.10

        if criterion_type == "treatment_history":
            tx_rates = rates.get("treatment_history", {})
            if subtype == "first_line":
                return tx_rates.get("prior_lines", {}).get("first_line", {}).get("typical_elimination", 0.30)
            return 0.25

        return 0.10  # Default 10% elimination

    def query_condition(
        self,
        concept_ids: List[int],
        include_descendants: bool = True,
    ) -> QueryResult:
        """
        Estimate patients with conditions using prevalence data.

        Note: This is a prevalence-based estimate, not actual query.
        """
        if not concept_ids:
            return QueryResult(patient_count=0, error="No concept IDs provided")

        # Use a moderate prevalence estimate for cancer
        # In practice, would map concept IDs to specific conditions
        prevalence = 0.01  # 1% default for cancer

        count = int(self.population_size * prevalence)

        return QueryResult(
            patient_count=count,
            query_executed=f"SYNTHETIC: condition prevalence estimate for {len(concept_ids)} concepts",
            metadata={"estimation_method": "prevalence", "prevalence_rate": prevalence},
        )

    def query_measurement(
        self,
        concept_ids: List[int],
        value_operator: str = ">=",
        value_threshold: float = 0.0,
        unit_concept_id: Optional[int] = None,
    ) -> QueryResult:
        """Estimate patients meeting measurement criteria."""
        if not concept_ids:
            return QueryResult(patient_count=0, error="No concept IDs provided")

        # Lab criteria typically eliminate ~20-30%
        pass_rate = 1 - self._get_screen_fail_rate("functional", "labs")
        count = int(self.population_size * pass_rate)

        return QueryResult(
            patient_count=count,
            query_executed=f"SYNTHETIC: measurement estimate ({value_operator} {value_threshold})",
            metadata={"estimation_method": "screen_fail_rate", "pass_rate": pass_rate},
        )

    def query_drug_exposure(
        self,
        concept_ids: List[int],
        include_descendants: bool = True,
        days_supply_min: Optional[int] = None,
    ) -> QueryResult:
        """Estimate patients with drug exposures."""
        if not concept_ids:
            return QueryResult(patient_count=0, error="No concept IDs provided")

        # Treatment history criteria
        pass_rate = 1 - self._get_screen_fail_rate("treatment_history", "first_line")
        count = int(self.population_size * pass_rate)

        return QueryResult(
            patient_count=count,
            query_executed=f"SYNTHETIC: drug exposure estimate for {len(concept_ids)} drugs",
            metadata={"estimation_method": "screen_fail_rate", "pass_rate": pass_rate},
        )

    def query_procedure(
        self,
        concept_ids: List[int],
        include_descendants: bool = True,
    ) -> QueryResult:
        """Estimate patients with procedures."""
        if not concept_ids:
            return QueryResult(patient_count=0, error="No concept IDs provided")

        # Procedures typically available for ~80% of population
        pass_rate = 0.80
        count = int(self.population_size * pass_rate)

        return QueryResult(
            patient_count=count,
            query_executed=f"SYNTHETIC: procedure estimate for {len(concept_ids)} procedures",
            metadata={"estimation_method": "prevalence", "pass_rate": pass_rate},
        )

    def query_observation(
        self,
        concept_ids: List[int],
        value_as_concept_id: Optional[int] = None,
        value_as_string: Optional[str] = None,
    ) -> QueryResult:
        """Estimate patients with observations."""
        if not concept_ids:
            return QueryResult(patient_count=0, error="No concept IDs provided")

        # Observations typically available for ~70% of population
        pass_rate = 0.70
        count = int(self.population_size * pass_rate)

        return QueryResult(
            patient_count=count,
            query_executed=f"SYNTHETIC: observation estimate for {len(concept_ids)} observations",
            metadata={"estimation_method": "prevalence", "pass_rate": pass_rate},
        )

    def query_demographics(
        self,
        min_age: Optional[int] = None,
        max_age: Optional[int] = None,
        gender_concept_id: Optional[int] = None,
    ) -> QueryResult:
        """Estimate patients by demographics."""
        # Use US population age distribution
        demographics = self.condition_prevalence.get("demographics", {}).get("us_population", {})
        age_dist = demographics.get("age_distribution", {})
        gender_dist = demographics.get("gender_distribution", {})

        pass_rate = 1.0

        # Apply age filter
        if min_age is not None or max_age is not None:
            # Simplified age calculation
            if min_age and min_age >= 65:
                pass_rate *= age_dist.get("65_plus", 0.17)
            elif min_age and min_age >= 45:
                pass_rate *= (age_dist.get("45_64", 0.25) + age_dist.get("65_plus", 0.17))
            elif min_age and min_age >= 18:
                pass_rate *= (1 - age_dist.get("0_17", 0.22))

            if max_age and max_age < 65:
                pass_rate *= 0.85  # Exclude some elderly
            if max_age and max_age < 45:
                pass_rate *= 0.70  # More restrictive

        # Apply gender filter
        if gender_concept_id:
            if gender_concept_id == 8507:  # Male
                pass_rate *= gender_dist.get("male", 0.49)
            elif gender_concept_id == 8532:  # Female
                pass_rate *= gender_dist.get("female", 0.51)

        count = int(self.population_size * pass_rate)

        return QueryResult(
            patient_count=count,
            query_executed=f"SYNTHETIC: demographics (age {min_age}-{max_age}, gender {gender_concept_id})",
            metadata={"estimation_method": "prevalence", "pass_rate": pass_rate},
        )

    def estimate_biomarker_positive(
        self,
        tumor_type: str,
        biomarker: str,
        disease_population: int,
    ) -> QueryResult:
        """
        Estimate biomarker-positive patients within a disease population.

        Args:
            tumor_type: Tumor type key.
            biomarker: Biomarker key.
            disease_population: Population with the disease.

        Returns:
            QueryResult with biomarker-positive count.
        """
        frequency = self._get_biomarker_frequency(tumor_type, biomarker)
        count = int(disease_population * frequency)

        return QueryResult(
            patient_count=count,
            query_executed=f"SYNTHETIC: {biomarker} in {tumor_type} (freq={frequency:.2%})",
            metadata={
                "estimation_method": "biomarker_frequency",
                "tumor_type": tumor_type,
                "biomarker": biomarker,
                "frequency": frequency,
            },
        )

    def get_adapter_info(self) -> Dict[str, Any]:
        """Get adapter metadata."""
        info = super().get_adapter_info()
        info.update({
            "adapter_type": "SyntheticAdapter",
            "population_size": self.population_size,
            "estimation_method": "prevalence_based",
            "reference_data_loaded": {
                "biomarker_frequencies": bool(self.biomarker_frequencies),
                "condition_prevalence": bool(self.condition_prevalence),
                "screen_fail_rates": bool(self.screen_fail_rates),
            },
        })
        return info
