"""
CDISC Controlled Terminology normalizer.

Normalizes extracted values to CDISC CT codes and decodes
for USDM 4.0 compliance.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# CDISC Controlled Terminology mappings
# Source: NCI Thesaurus (NCIt)

OBJECTIVE_LEVEL = {
    "Primary": {"code": "C85826", "decode": "Primary"},
    "Secondary": {"code": "C85827", "decode": "Secondary"},
    "Exploratory": {"code": "C174265", "decode": "Exploratory"},
    "Safety": {"code": "C49657", "decode": "Safety"},
    # Aliases
    "primary": {"code": "C85826", "decode": "Primary"},
    "secondary": {"code": "C85827", "decode": "Secondary"},
    "exploratory": {"code": "C174265", "decode": "Exploratory"},
    "tertiary": {"code": "C174265", "decode": "Exploratory"},  # Map to Exploratory
}

ENDPOINT_LEVEL = {
    "Primary": {"code": "C98747", "decode": "Primary"},
    "Secondary": {"code": "C98748", "decode": "Secondary"},
    "Exploratory": {"code": "C174264", "decode": "Exploratory"},
    "Safety": {"code": "C49656", "decode": "Safety"},
    # Aliases
    "primary": {"code": "C98747", "decode": "Primary"},
    "secondary": {"code": "C98748", "decode": "Secondary"},
    "exploratory": {"code": "C174264", "decode": "Exploratory"},
    "tertiary": {"code": "C174264", "decode": "Exploratory"},
}

OUTCOME_TYPE = {
    "Binary Endpoint": {"code": "C82583", "decode": "Binary Endpoint"},
    "Continuous Variable": {"code": "C25513", "decode": "Continuous Variable"},
    "Time-to-Event Endpoint": {"code": "C25208", "decode": "Time-to-Event Endpoint"},
    "Count Endpoint": {"code": "C25463", "decode": "Count Endpoint"},
    "Ordinal Endpoint": {"code": "C25284", "decode": "Ordinal Endpoint"},
    # Aliases
    "binary": {"code": "C82583", "decode": "Binary Endpoint"},
    "continuous": {"code": "C25513", "decode": "Continuous Variable"},
    "time-to-event": {"code": "C25208", "decode": "Time-to-Event Endpoint"},
    "tte": {"code": "C25208", "decode": "Time-to-Event Endpoint"},
    "count": {"code": "C25463", "decode": "Count Endpoint"},
    "ordinal": {"code": "C25284", "decode": "Ordinal Endpoint"},
}

ARM_TYPE = {
    "Experimental Arm": {"code": "C98388", "decode": "Experimental Arm"},
    "Active Comparator Arm": {"code": "C98389", "decode": "Active Comparator Arm"},
    "Placebo Comparator Arm": {"code": "C98390", "decode": "Placebo Comparator Arm"},
    "No Intervention Arm": {"code": "C98391", "decode": "No Intervention Arm"},
    # Aliases
    "experimental": {"code": "C98388", "decode": "Experimental Arm"},
    "active_comparator": {"code": "C98389", "decode": "Active Comparator Arm"},
    "placebo": {"code": "C98390", "decode": "Placebo Comparator Arm"},
    "no_intervention": {"code": "C98391", "decode": "No Intervention Arm"},
}

ICE_STRATEGY = {
    "Treatment Policy Strategy": {"code": "C178899", "decode": "Treatment Policy Strategy"},
    "Composite Strategy": {"code": "C178900", "decode": "Composite Strategy"},
    "Hypothetical Strategy": {"code": "C178901", "decode": "Hypothetical Strategy"},
    "While on Treatment Strategy": {"code": "C178902", "decode": "While on Treatment Strategy"},
    "Principal Stratum Strategy": {"code": "C178903", "decode": "Principal Stratum Strategy"},
    # Aliases
    "treatment_policy": {"code": "C178899", "decode": "Treatment Policy Strategy"},
    "composite": {"code": "C178900", "decode": "Composite Strategy"},
    "hypothetical": {"code": "C178901", "decode": "Hypothetical Strategy"},
    "while_on_treatment": {"code": "C178902", "decode": "While on Treatment Strategy"},
    "principal_stratum": {"code": "C178903", "decode": "Principal Stratum Strategy"},
}

SUMMARY_MEASURE = {
    "Hazard Ratio": {"code": "C16859", "decode": "Hazard Ratio"},
    "Risk Difference": {"code": "C68680", "decode": "Risk Difference"},
    "Odds Ratio": {"code": "C16932", "decode": "Odds Ratio"},
    "Difference in Means": {"code": "C53338", "decode": "Difference in Means"},
    # Aliases
    "hazard_ratio": {"code": "C16859", "decode": "Hazard Ratio"},
    "hr": {"code": "C16859", "decode": "Hazard Ratio"},
    "risk_difference": {"code": "C68680", "decode": "Risk Difference"},
    "rd": {"code": "C68680", "decode": "Risk Difference"},
    "odds_ratio": {"code": "C16932", "decode": "Odds Ratio"},
    "or": {"code": "C16932", "decode": "Odds Ratio"},
    "difference_in_means": {"code": "C53338", "decode": "Difference in Means"},
}

POPULATION_TYPE = {
    "Intent-to-Treat Population": {"code": "C71104", "decode": "Intent-to-Treat Population"},
    "Modified Intent-to-Treat Population": {"code": "C93001", "decode": "Modified Intent-to-Treat Population"},
    "Per-Protocol Population": {"code": "C70927", "decode": "Per-Protocol Population"},
    "Safety Population": {"code": "C115932", "decode": "Safety Population"},
    "Full Analysis Set": {"code": "C71105", "decode": "Full Analysis Set"},
    # Aliases
    "ITT": {"code": "C71104", "decode": "Intent-to-Treat Population"},
    "itt": {"code": "C71104", "decode": "Intent-to-Treat Population"},
    "mITT": {"code": "C93001", "decode": "Modified Intent-to-Treat Population"},
    "mitt": {"code": "C93001", "decode": "Modified Intent-to-Treat Population"},
    "PP": {"code": "C70927", "decode": "Per-Protocol Population"},
    "pp": {"code": "C70927", "decode": "Per-Protocol Population"},
    "Safety": {"code": "C115932", "decode": "Safety Population"},
    "FAS": {"code": "C71105", "decode": "Full Analysis Set"},
    "fas": {"code": "C71105", "decode": "Full Analysis Set"},
}

ANALYSIS_TYPE = {
    "Primary Analysis": {"code": "C82547", "decode": "Primary Analysis"},
    "Sensitivity Analysis": {"code": "C173329", "decode": "Sensitivity Analysis"},
    "Supplementary Analysis": {"code": "C173330", "decode": "Supplementary Analysis"},
    "Subgroup Analysis": {"code": "C77742", "decode": "Subgroup Analysis"},
    # Aliases
    "primary": {"code": "C82547", "decode": "Primary Analysis"},
    "sensitivity": {"code": "C173329", "decode": "Sensitivity Analysis"},
    "supplementary": {"code": "C173330", "decode": "Supplementary Analysis"},
    "subgroup": {"code": "C77742", "decode": "Subgroup Analysis"},
}

# SAE Criteria codes
SAE_CRITERION_TYPE = {
    "Death": {"code": "C48275", "decode": "Results in death"},
    "Life-Threatening": {"code": "C84266", "decode": "Is life-threatening"},
    "Hospitalization": {"code": "C83052", "decode": "Requires inpatient hospitalization or prolongation"},
    "Disability": {"code": "C21079", "decode": "Results in persistent or significant disability/incapacity"},
    "Congenital Anomaly": {"code": "C87162", "decode": "Is a congenital anomaly/birth defect"},
    "Medically Important": {"code": "C113380", "decode": "Is medically important event"},
}

# Code system for CDISC CT
CDISC_CODE_SYSTEM = "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl"
CDISC_CODE_SYSTEM_VERSION = "24.03e"


class CDISCNormalizer:
    """
    Normalizes extracted values to CDISC Controlled Terminology.

    Provides code/decode pairs for USDM 4.0 compliance.
    """

    def __init__(self):
        """Initialize normalizer with terminology mappings."""
        self.terminologies = {
            "objective_level": OBJECTIVE_LEVEL,
            "endpoint_level": ENDPOINT_LEVEL,
            "outcome_type": OUTCOME_TYPE,
            "arm_type": ARM_TYPE,
            "ice_strategy": ICE_STRATEGY,
            "summary_measure": SUMMARY_MEASURE,
            "population_type": POPULATION_TYPE,
            "analysis_type": ANALYSIS_TYPE,
            "sae_criterion_type": SAE_CRITERION_TYPE,
        }

    def normalize(
        self,
        value: str,
        terminology: str,
    ) -> Optional[Dict[str, str]]:
        """
        Normalize a value to CDISC CT code/decode.

        Args:
            value: Value to normalize
            terminology: Terminology type (e.g., 'objective_level')

        Returns:
            Dictionary with code, decode, codeSystem, codeSystemVersion
            or None if not found
        """
        term_map = self.terminologies.get(terminology)
        if not term_map:
            logger.warning(f"Unknown terminology: {terminology}")
            return None

        # Try exact match first
        result = term_map.get(value)
        if not result:
            # Try case-insensitive match
            value_lower = value.lower().strip()
            result = term_map.get(value_lower)

        if not result:
            # Try partial match
            for key, val in term_map.items():
                if key.lower() in value_lower or value_lower in key.lower():
                    result = val
                    break

        if result:
            return {
                "code": result["code"],
                "decode": result["decode"],
                "codeSystem": CDISC_CODE_SYSTEM,
                "codeSystemVersion": CDISC_CODE_SYSTEM_VERSION,
            }

        logger.debug(f"No CDISC CT match for '{value}' in {terminology}")
        return None

    def normalize_data(
        self,
        data: Dict[str, Any],
        field_mappings: Dict[str, str],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Normalize multiple fields in extracted data.

        Args:
            data: Extracted data dictionary
            field_mappings: Mapping of field paths to terminology types

        Returns:
            Tuple of (normalized_data, normalization_log)
        """
        import copy
        normalized = copy.deepcopy(data)
        log = []

        for field_path, terminology in field_mappings.items():
            value = self._get_nested(normalized, field_path)
            if value and isinstance(value, str):
                result = self.normalize(value, terminology)
                if result:
                    self._set_nested(normalized, field_path, result)
                    log.append({
                        "path": field_path,
                        "original": value,
                        "normalized": result,
                    })

        return normalized, log

    def _get_nested(self, data: Dict, path: str) -> Any:
        """Get nested value by dot-notation path."""
        keys = path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current

    def _set_nested(self, data: Dict, path: str, value: Any):
        """Set nested value by dot-notation path."""
        keys = path.split(".")
        current = data
        for key in keys[:-1]:
            if isinstance(current, dict):
                current = current.setdefault(key, {})
        if isinstance(current, dict):
            current[keys[-1]] = value

    def get_all_codes(self, terminology: str) -> List[Dict[str, str]]:
        """
        Get all valid codes for a terminology.

        Args:
            terminology: Terminology type

        Returns:
            List of valid code/decode pairs
        """
        term_map = self.terminologies.get(terminology, {})
        seen_codes = set()
        codes = []

        for entry in term_map.values():
            if entry["code"] not in seen_codes:
                seen_codes.add(entry["code"])
                codes.append({
                    "code": entry["code"],
                    "decode": entry["decode"],
                })

        return codes

    def validate_code(self, code: str, terminology: str) -> bool:
        """
        Validate if a code exists in the terminology.

        Args:
            code: CDISC CT code (e.g., 'C85826')
            terminology: Terminology type

        Returns:
            True if code is valid
        """
        term_map = self.terminologies.get(terminology, {})
        valid_codes = {v["code"] for v in term_map.values()}
        return code in valid_codes
