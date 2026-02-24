"""
Configuration loader for eligibility analyzer.

Loads YAML configuration files and provides typed access to settings.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import yaml

logger = logging.getLogger(__name__)

# Singleton instance
_config_instance: Optional["EligibilityConfig"] = None


class EligibilityConfig:
    """
    Loads and provides access to externalized mappings.

    Usage:
        config = load_config()  # Get singleton instance
        table = config.get_table_for_domain("Measurement")  # "measurement"
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """Load configuration from YAML files."""
        self.config_dir = config_dir or Path(__file__).parent
        self._omop_config: Dict = {}
        self._fhir_config: Dict = {}
        self._load_configs()

    def _load_configs(self) -> None:
        """Load all configuration files."""
        # Load OMOP mappings
        omop_path = self.config_dir / "omop_mappings.yaml"
        if omop_path.exists():
            with open(omop_path, "r") as f:
                self._omop_config = yaml.safe_load(f) or {}
            logger.debug(f"Loaded OMOP config from {omop_path}")
        else:
            logger.warning(f"OMOP config not found at {omop_path}")

        # Load FHIR mappings
        fhir_path = self.config_dir / "fhir_mappings.yaml"
        if fhir_path.exists():
            with open(fhir_path, "r") as f:
                self._fhir_config = yaml.safe_load(f) or {}
            logger.debug(f"Loaded FHIR config from {fhir_path}")
        else:
            logger.warning(f"FHIR config not found at {fhir_path}")

    # =========================================================================
    # OMOP Configuration
    # =========================================================================

    @property
    def domain_to_table(self) -> Dict[str, str]:
        """Get domain to OMOP table mapping."""
        return self._omop_config.get("domain_to_table", {})

    @property
    def table_to_concept_column(self) -> Dict[str, str]:
        """Get table to concept_id column mapping."""
        return self._omop_config.get("table_to_concept_column", {})

    @property
    def tables_with_value_as_number(self) -> Set[str]:
        """Get set of tables that support value_as_number."""
        return set(self._omop_config.get("tables_with_value_as_number", []))

    @property
    def category_to_stage(self) -> Dict[str, Dict]:
        """Get category to funnel stage mapping."""
        return self._omop_config.get("category_to_stage", {})

    def get_table_for_domain(self, domain: str) -> Optional[str]:
        """
        Get OMOP table for a domain.

        Args:
            domain: OMOP domain name (e.g., "Measurement", "Condition")

        Returns:
            Table name or None if not found (caller should handle unknown domains)
        """
        return self.domain_to_table.get(domain)

    def get_concept_column_for_table(self, table: str) -> str:
        """
        Get concept_id column name for a table.

        Args:
            table: OMOP table name

        Returns:
            Column name, with fallback pattern if not found
        """
        column = self.table_to_concept_column.get(table)
        if column:
            return column
        # Fallback: derive from table name
        return f"{table.replace('_occurrence', '').replace('_exposure', '')}_concept_id"

    def table_supports_value_column(self, table: str) -> bool:
        """Check if table supports value_as_number column."""
        return table in self.tables_with_value_as_number

    def get_stage_for_category(self, category: str) -> Optional[Tuple[str, str, int]]:
        """
        Get funnel stage info for a category.

        Returns:
            Tuple of (stage_id, display_name, order) or None
        """
        stage_info = self.category_to_stage.get(category)
        if stage_info:
            return (
                stage_info.get("stage_id"),
                stage_info.get("display_name"),
                stage_info.get("order"),
            )
        return None

    # =========================================================================
    # FHIR Configuration
    # =========================================================================

    @property
    def domain_to_fhir_resource(self) -> Dict[str, str]:
        """Get domain to FHIR resource type mapping."""
        return self._fhir_config.get("domain_to_fhir_resource", {})

    @property
    def vocabulary_to_fhir_system(self) -> Dict[str, str]:
        """Get vocabulary to FHIR system URL mapping."""
        return self._fhir_config.get("vocabulary_to_fhir_system", {})

    @property
    def domain_vocabulary_hints(self) -> Dict[str, List[str]]:
        """Get domain to vocabulary hints mapping."""
        return self._fhir_config.get("domain_vocabulary_hints", {})

    def get_fhir_resource_for_domain(self, domain: str) -> str:
        """
        Get FHIR resource type for an OMOP domain.

        Args:
            domain: OMOP domain name

        Returns:
            FHIR resource type, defaults to "Observation" for unknown
        """
        return self.domain_to_fhir_resource.get(domain, "Observation")

    def get_fhir_system_for_vocabulary(self, vocab: str) -> Optional[str]:
        """
        Get FHIR code system URL for a vocabulary.

        Args:
            vocab: Vocabulary name (e.g., "SNOMED", "LOINC")

        Returns:
            FHIR system URL or None if not found
        """
        return self.vocabulary_to_fhir_system.get(vocab)

    def get_vocabulary_hints_for_domain(self, domain: str) -> List[str]:
        """
        Get suggested vocabularies for a domain.

        Args:
            domain: OMOP domain name

        Returns:
            List of vocabulary names to search
        """
        return self.domain_vocabulary_hints.get(domain, [])


def load_config(config_dir: Optional[Path] = None) -> EligibilityConfig:
    """
    Get or create singleton config instance.

    Args:
        config_dir: Optional path to config directory (uses default if not specified)

    Returns:
        EligibilityConfig instance
    """
    global _config_instance

    if _config_instance is None:
        _config_instance = EligibilityConfig(config_dir)

    return _config_instance


def reset_config() -> None:
    """Reset singleton instance (for testing)."""
    global _config_instance
    _config_instance = None
