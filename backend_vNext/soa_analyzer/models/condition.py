"""
USDM 4.0 Condition and ConditionAssignment Models

Implements formal condition resources for population-based and clinical activity conditions.

Current Problem:
    ALL SAIs have defaultConditionId: null (0% condition coverage)
    Footnotes like "females of childbearing potential" exist but aren't linked

Required USDM 4.0 Structure:
    Condition:
    {
        "id": "COND-001",
        "instanceType": "Condition",
        "name": "Female of Childbearing Potential",
        "text": "Subject is a female of childbearing potential",
        "contextIds": ["ACT-PREG-TEST", "ACT-CONTRACEPTION"]
    }

    ConditionAssignment:
    {
        "id": "CA-001",
        "instanceType": "ConditionAssignment",
        "conditionId": "COND-001",
        "conditionTargetId": "SAI-018"
    }

Usage:
    from soa_analyzer.models.condition import Condition, ConditionAssignment

    condition = Condition(
        name="Female of Childbearing Potential",
        text="females of childbearing potential",
        source_footnote_marker="f"
    )

    assignment = ConditionAssignment(
        condition_id=condition.id,
        target_id="SAI-018"
    )
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import uuid

# Path to condition type codes config
CONDITION_TYPE_CODES_PATH = Path(__file__).parent.parent / "config" / "condition_type_codes.json"
CONDITION_CRITERIA_CODES_PATH = Path(__file__).parent.parent / "config" / "condition_criteria_codes.json"

# Lazy-loaded code mappings
_condition_type_codes: Optional[Dict] = None
_condition_criteria_codes: Optional[Dict] = None


def _load_condition_type_codes() -> Dict:
    """Load condition type codes from config file."""
    global _condition_type_codes
    if _condition_type_codes is None:
        if CONDITION_TYPE_CODES_PATH.exists():
            with open(CONDITION_TYPE_CODES_PATH) as f:
                data = json.load(f)
            _condition_type_codes = data.get("condition_type_codes", {})
        else:
            _condition_type_codes = {}
    return _condition_type_codes


def _load_condition_criteria_codes() -> Dict:
    """Load condition criteria codes from config file."""
    global _condition_criteria_codes
    if _condition_criteria_codes is None:
        if CONDITION_CRITERIA_CODES_PATH.exists():
            with open(CONDITION_CRITERIA_CODES_PATH) as f:
                data = json.load(f)
            _condition_criteria_codes = data.get("criteria_codes", {})
        else:
            _condition_criteria_codes = {}
    return _condition_criteria_codes


def _create_code_object(code: str, decode: str, code_id_prefix: str = "CODE") -> Dict[str, Any]:
    """Create a USDM 4.0 compliant 6-field Code object."""
    return {
        "id": f"{code_id_prefix}-{uuid.uuid4().hex[:8].upper()}",
        "instanceType": "Code",
        "code": code,
        "decode": decode,
        "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
        "codeSystemVersion": "24.12",
    }


def _get_condition_type_code_object(condition_type: "ConditionType", condition_id: str) -> Optional[Dict[str, Any]]:
    """Get USDM 4.0 Code object for a condition type."""
    if condition_type is None:
        return None

    type_codes = _load_condition_type_codes()
    type_name = condition_type.name  # e.g., "DEMOGRAPHIC_SEX"

    if type_name in type_codes:
        code_data = type_codes[type_name]
        return {
            "id": f"CODE-{condition_id}-TYPE",
            "instanceType": "Code",
            "code": code_data["code"],
            "decode": code_data["decode"],
            "codeSystem": code_data.get("codeSystem", "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl"),
            "codeSystemVersion": code_data.get("codeSystemVersion", "24.12"),
        }

    # Fallback: create Code object with no code
    return {
        "id": f"CODE-{condition_id}-TYPE",
        "instanceType": "Code",
        "code": None,
        "decode": type_name.replace("_", " ").title(),
        "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
        "codeSystemVersion": "24.12",
    }


def _convert_criterion_to_code_objects(criterion: Optional[Dict], condition_id: str) -> Optional[Dict[str, Any]]:
    """Convert criterion dictionary to use CDISC Code objects where possible."""
    if criterion is None:
        return None

    criteria_codes = _load_condition_criteria_codes()
    result = {}
    idx = 0

    for key, value in criterion.items():
        idx += 1
        # Check if we have a CDISC code mapping for this criterion key+value
        key_codes = criteria_codes.get(key, {})

        if isinstance(value, str) and value in key_codes:
            # Convert to Code object
            code_data = key_codes[value]
            result[key] = {
                "id": f"CODE-{condition_id}-CRIT-{idx}",
                "instanceType": "Code",
                "code": code_data.get("code"),
                "decode": code_data.get("decode", value),
                "codeSystem": code_data.get("codeSystem", "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl"),
                "codeSystemVersion": code_data.get("codeSystemVersion", "24.12"),
            }
        elif isinstance(value, dict):
            # Already a dict (possibly a Code object or nested structure), keep as-is
            result[key] = value
        else:
            # Keep original value (number, bool, or unmapped string)
            result[key] = value

    return result


class ConditionType(Enum):
    """Types of conditions that can apply to activities."""

    # Demographic conditions
    DEMOGRAPHIC_SEX = "demographic_sex"  # Female only, Male only
    DEMOGRAPHIC_AGE = "demographic_age"  # Age ≥65, Pediatric
    DEMOGRAPHIC_FERTILITY = "demographic_fertility"  # Childbearing potential

    # Clinical conditions
    CLINICAL_INDICATION = "clinical_indication"  # If clinically indicated
    CLINICAL_RESULT = "clinical_result"  # If labs abnormal, repeat
    CLINICAL_EVENT = "clinical_event"  # If AE occurs

    # Temporal conditions
    TEMPORAL_PRIOR = "temporal_prior"  # If obtained within 72h
    TEMPORAL_SEQUENCE = "temporal_sequence"  # After completing X

    # Visit conditions
    VISIT_OPTIONAL = "visit_optional"  # At investigator discretion
    VISIT_TRIGGERED = "visit_triggered"  # If dose modification required


# Demographic condition patterns and their mappings
DEMOGRAPHIC_PATTERNS = {
    # Sex-based
    "female": {
        "type": ConditionType.DEMOGRAPHIC_SEX,
        "criterion": {"sex": "F"},
        "text": "Female subjects only",
    },
    "male": {
        "type": ConditionType.DEMOGRAPHIC_SEX,
        "criterion": {"sex": "M"},
        "text": "Male subjects only",
    },
    # Fertility-based
    "childbearing potential": {
        "type": ConditionType.DEMOGRAPHIC_FERTILITY,
        "criterion": {"fertilityStatus": "fertile"},
        "text": "Female subjects of childbearing potential",
    },
    "child-bearing potential": {
        "type": ConditionType.DEMOGRAPHIC_FERTILITY,
        "criterion": {"fertilityStatus": "fertile"},
        "text": "Female subjects of childbearing potential",
    },
    "wocbp": {
        "type": ConditionType.DEMOGRAPHIC_FERTILITY,
        "criterion": {"fertilityStatus": "fertile"},
        "text": "Women of childbearing potential",
    },
    "post-menopausal": {
        "type": ConditionType.DEMOGRAPHIC_FERTILITY,
        "criterion": {"fertilityStatus": "postmenopausal"},
        "text": "Post-menopausal subjects",
    },
    "postmenopausal": {
        "type": ConditionType.DEMOGRAPHIC_FERTILITY,
        "criterion": {"fertilityStatus": "postmenopausal"},
        "text": "Post-menopausal subjects",
    },
    # Age-based
    "age ≥65": {
        "type": ConditionType.DEMOGRAPHIC_AGE,
        "criterion": {"ageRange": {"min": 65}},
        "text": "Subjects aged 65 years or older",
    },
    "elderly": {
        "type": ConditionType.DEMOGRAPHIC_AGE,
        "criterion": {"ageRange": {"min": 65}},
        "text": "Elderly subjects (≥65 years)",
    },
    "pediatric": {
        "type": ConditionType.DEMOGRAPHIC_AGE,
        "criterion": {"ageRange": {"max": 18}},
        "text": "Pediatric subjects (<18 years)",
    },
}

# Clinical condition patterns
CLINICAL_PATTERNS = {
    "clinically indicated": {
        "type": ConditionType.CLINICAL_INDICATION,
        "text": "If clinically indicated based on investigator judgment",
    },
    "if indicated": {
        "type": ConditionType.CLINICAL_INDICATION,
        "text": "If clinically indicated",
    },
    "at investigator discretion": {
        "type": ConditionType.VISIT_OPTIONAL,
        "text": "At investigator discretion",
    },
    "if abnormal": {
        "type": ConditionType.CLINICAL_RESULT,
        "text": "If results are abnormal, repeat assessment",
    },
}


@dataclass
class Condition:
    """
    USDM 4.0 Condition resource.

    Represents a condition that must be met for an activity to apply.
    """
    name: str
    text: str
    id: str = field(default_factory=lambda: f"COND-{uuid.uuid4().hex[:8].upper()}")
    instanceType: str = "Condition"
    condition_type: Optional[ConditionType] = None
    criterion: Optional[Dict[str, Any]] = None
    source_footnote_marker: Optional[str] = None
    source_footnote_text: Optional[str] = None
    context_ids: List[str] = field(default_factory=list)
    applies_to_ids: List[str] = field(default_factory=list)
    confidence: float = 1.0
    provenance: Optional[Dict[str, Any]] = None

    @classmethod
    def from_footnote(
        cls,
        footnote_text: str,
        marker: str,
        page_number: Optional[int] = None,
    ) -> Optional["Condition"]:
        """
        Create Condition from footnote text by pattern matching.

        Args:
            footnote_text: The footnote text to analyze
            marker: The footnote marker (a, b, c, etc.)
            page_number: Source page number for provenance

        Returns:
            Condition if a pattern matches, None otherwise
        """
        text_lower = footnote_text.lower()

        # Check demographic patterns - prioritize more specific patterns first
        # Sort patterns by length (longer patterns first) to match most specific
        sorted_demographic = sorted(DEMOGRAPHIC_PATTERNS.items(), key=lambda x: len(x[0]), reverse=True)
        for pattern, config in sorted_demographic:
            if pattern in text_lower:
                return cls(
                    name=config["text"],
                    text=config["text"],
                    condition_type=config["type"],
                    criterion=config.get("criterion"),
                    source_footnote_marker=marker,
                    source_footnote_text=footnote_text,
                    provenance={
                        "page_number": page_number,
                        "text_snippet": footnote_text[:200],
                        "source": "footnote",
                    },
                )

        # Check clinical patterns - also sort by specificity
        sorted_clinical = sorted(CLINICAL_PATTERNS.items(), key=lambda x: len(x[0]), reverse=True)
        for pattern, config in sorted_clinical:
            if pattern in text_lower:
                return cls(
                    name=config["text"],
                    text=config["text"],
                    condition_type=config["type"],
                    source_footnote_marker=marker,
                    source_footnote_text=footnote_text,
                    provenance={
                        "page_number": page_number,
                        "text_snippet": footnote_text[:200],
                        "source": "footnote",
                    },
                )

        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to USDM 4.0 compliant dictionary with Code objects."""
        result = {
            "id": self.id,
            "instanceType": self.instanceType,
            "name": self.name,
            "text": self.text,
        }

        # Add condition type as Code object (USDM 4.0 compliant)
        if self.condition_type is not None:
            result["conditionType"] = _get_condition_type_code_object(
                self.condition_type, self.id
            )

        if self.context_ids:
            result["contextIds"] = self.context_ids

        if self.applies_to_ids:
            result["appliesToIds"] = self.applies_to_ids

        # Convert criterion to use Code objects where possible
        if self.criterion:
            result["criterion"] = _convert_criterion_to_code_objects(
                self.criterion, self.id
            )

        if self.provenance:
            result["provenance"] = self.provenance

        # Add source footnote info for traceability
        if self.source_footnote_marker:
            result["sourceFootnoteMarker"] = self.source_footnote_marker

        return result


@dataclass
class ConditionAssignment:
    """
    USDM 4.0 ConditionAssignment resource.

    Links a Condition to its target entity (SAI, Activity, etc.).
    """
    condition_id: str
    target_id: str
    id: str = field(default_factory=lambda: f"CA-{uuid.uuid4().hex[:8].upper()}")
    instanceType: str = "ConditionAssignment"
    provenance: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to USDM 4.0 compliant dictionary."""
        result = {
            "id": self.id,
            "instanceType": self.instanceType,
            "conditionId": self.condition_id,
            "conditionTargetId": self.target_id,
        }

        if self.provenance:
            result["provenance"] = self.provenance

        return result


@dataclass
class ScheduledDecisionInstance:
    """
    USDM 4.0 ScheduledDecisionInstance for conditional activities.

    Used for "if clinically indicated" type activities where
    execution depends on clinical judgment at point of care.
    """
    name: str
    condition_text: str
    activity_id: str
    id: str = field(default_factory=lambda: f"SDI-{uuid.uuid4().hex[:8].upper()}")
    instanceType: str = "ScheduledDecisionInstance"
    default_condition_id: Optional[str] = None
    condition_assignments: List[ConditionAssignment] = field(default_factory=list)
    provenance: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to USDM 4.0 compliant dictionary."""
        result = {
            "id": self.id,
            "instanceType": self.instanceType,
            "name": self.name,
            "conditionText": self.condition_text,
            "activityId": self.activity_id,
        }

        if self.default_condition_id:
            result["defaultConditionId"] = self.default_condition_id

        if self.condition_assignments:
            result["conditionAssignments"] = [ca.to_dict() for ca in self.condition_assignments]

        if self.provenance:
            result["provenance"] = self.provenance

        return result


def extract_conditions_from_footnotes(
    footnotes: List[Dict[str, Any]]
) -> tuple[List[Condition], Dict[str, str]]:
    """
    Extract USDM Conditions from SOA footnotes.

    Deduplicates conditions with the same type/criterion to avoid creating
    multiple identical conditions from different footnotes.

    Args:
        footnotes: List of footnote dictionaries from SOA extraction

    Returns:
        Tuple of (list of Conditions, mapping of marker -> condition_id)
    """
    conditions: List[Condition] = []
    marker_to_condition: Dict[str, str] = {}

    # Track unique conditions by (type, criterion_hash) to deduplicate
    seen_conditions: Dict[str, Condition] = {}

    for fn in footnotes:
        marker = fn.get("marker", "")
        text = fn.get("text", "") or fn.get("content", "")
        page = fn.get("provenance", {}).get("page_number") or fn.get("page_number")

        condition = Condition.from_footnote(text, marker, page)
        if condition:
            # Create a unique key based on condition type and criterion
            criterion_str = str(condition.criterion) if condition.criterion else ""
            condition_key = f"{condition.condition_type}:{criterion_str}"

            if condition_key in seen_conditions:
                # Reuse existing condition
                existing = seen_conditions[condition_key]
                marker_to_condition[marker] = existing.id
            else:
                # New unique condition
                seen_conditions[condition_key] = condition
                conditions.append(condition)
                marker_to_condition[marker] = condition.id

    return conditions, marker_to_condition
