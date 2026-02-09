"""
Reference Data Manager - Centralized loading and caching of reference data.

This module provides a singleton-like manager for loading reference data
files (biomarker frequencies, condition prevalence, screen fail rates)
to avoid redundant file I/O across multiple components.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ReferenceDataManager:
    """
    Centralized manager for reference data files.

    Uses caching to avoid repeated file reads. Thread-safe through
    module-level singleton pattern.
    """

    _instance: Optional["ReferenceDataManager"] = None
    _initialized: bool = False

    def __new__(cls, reference_data_dir: Optional[Path] = None):
        """Singleton pattern - return existing instance if available."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, reference_data_dir: Optional[Path] = None):
        """
        Initialize the reference data manager.

        Args:
            reference_data_dir: Directory containing reference data files.
        """
        # Only initialize once
        if ReferenceDataManager._initialized:
            return

        if reference_data_dir is None:
            reference_data_dir = Path(__file__).parent / "reference_data"
        self.reference_data_dir = reference_data_dir

        # Cache for loaded data
        self._cache: Dict[str, Dict[str, Any]] = {}

        # Pre-load all reference data
        self._load_all()

        ReferenceDataManager._initialized = True
        logger.info(f"ReferenceDataManager initialized from: {reference_data_dir}")

    def _load_all(self) -> None:
        """Pre-load all reference data files."""
        files_to_load = [
            "biomarker_frequencies.json",
            "condition_prevalence.json",
            "screen_fail_rates.json",
        ]
        for filename in files_to_load:
            self._load_file(filename)

    def _load_file(self, filename: str) -> Dict[str, Any]:
        """
        Load a single reference data file.

        Args:
            filename: Name of the JSON file to load.

        Returns:
            Loaded data dictionary.

        Raises:
            FileNotFoundError: If file doesn't exist.
            json.JSONDecodeError: If file contains invalid JSON.
        """
        if filename in self._cache:
            return self._cache[filename]

        path = self.reference_data_dir / filename
        if not path.exists():
            logger.warning(f"Reference file not found: {path}")
            self._cache[filename] = {}
            return {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._cache[filename] = data
            logger.debug(f"Loaded reference data: {filename}")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {filename}: {e}")
            raise

    @property
    def biomarker_frequencies(self) -> Dict[str, Any]:
        """Get biomarker frequency data."""
        return self._cache.get("biomarker_frequencies.json", {})

    @property
    def condition_prevalence(self) -> Dict[str, Any]:
        """Get condition prevalence data."""
        return self._cache.get("condition_prevalence.json", {})

    @property
    def screen_fail_rates(self) -> Dict[str, Any]:
        """Get screen failure rate data."""
        return self._cache.get("screen_fail_rates.json", {})

    def get_biomarker_frequency(
        self,
        tumor_type: str,
        biomarker: str,
        default: float = 0.1,
    ) -> float:
        """
        Get biomarker frequency for a tumor type.

        Args:
            tumor_type: Tumor type key (e.g., "NSCLC").
            biomarker: Biomarker key (e.g., "EGFR_mutation").
            default: Default value if not found.

        Returns:
            Frequency rate (0-1).
        """
        tumor_data = self.biomarker_frequencies.get(tumor_type, {})
        biomarkers = tumor_data.get("biomarkers", {})

        if biomarker in biomarkers:
            return biomarkers[biomarker].get("frequency", default)
        return default

    def get_condition_prevalence(
        self,
        condition_key: str,
        default_per_100k: float = 10,
    ) -> float:
        """
        Get condition prevalence rate.

        Args:
            condition_key: Condition key (e.g., "NSCLC").
            default_per_100k: Default prevalence per 100,000.

        Returns:
            Prevalence rate (0-1).
        """
        oncology_data = self.condition_prevalence.get("oncology", {})

        if condition_key in oncology_data:
            prev_per_100k = oncology_data[condition_key].get("prevalence_per_100k", default_per_100k)
            return prev_per_100k / 100000

        return default_per_100k / 100000

    def get_screen_fail_rate(
        self,
        criterion_type: str,
        subtype: Optional[str] = None,
        phase: str = "oncology_phase3",
        default: float = 0.10,
    ) -> float:
        """
        Get screen failure rate for a criterion type.

        Args:
            criterion_type: Type of criterion (e.g., "functional").
            subtype: Specific subtype (e.g., "ecog", "labs").
            phase: Trial phase (e.g., "oncology_phase3").
            default: Default elimination rate.

        Returns:
            Elimination rate (0-1).
        """
        rates = self.screen_fail_rates.get(phase, {}).get("by_criterion_category", {})

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

        return default

    def get_optimization_opportunity(self, opportunity_key: str) -> Dict[str, Any]:
        """
        Get optimization opportunity data.

        Args:
            opportunity_key: Key like "ecog_0_1_to_0_2".

        Returns:
            Opportunity data dictionary.
        """
        opportunities = self.screen_fail_rates.get("optimization_benchmarks", {}).get("opportunities", {})
        return opportunities.get(opportunity_key, {})

    def reload(self) -> None:
        """Force reload of all reference data."""
        self._cache.clear()
        self._load_all()
        logger.info("Reference data reloaded")

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance (for testing)."""
        cls._instance = None
        cls._initialized = False


# Module-level convenience function
def get_reference_data_manager(reference_data_dir: Optional[str] = None) -> ReferenceDataManager:
    """
    Get or create the reference data manager singleton.

    Args:
        reference_data_dir: Optional path to reference data directory.

    Returns:
        ReferenceDataManager instance.
    """
    path = Path(reference_data_dir) if reference_data_dir else None
    return ReferenceDataManager(path)
