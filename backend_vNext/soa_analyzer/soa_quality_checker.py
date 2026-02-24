"""
SOA Quality Checker - 5-Dimensional Quality Framework

Evaluates SOA extraction results against five quality dimensions:
1. Accuracy (95%): No placeholders, valid formats, no hallucinations
2. Completeness (90%): Required USDM fields present, activities mapped
3. Compliance (100%): Valid against USDM 4.0 JSON schema
4. Provenance (95%): Source page reference for extracted values
5. Terminology (90%): Valid CDISC codes, OMOP mappings

Usage:
    from soa_analyzer.soa_quality_checker import SOAQualityChecker, QualityScore

    checker = SOAQualityChecker()

    # Evaluate extraction
    score = checker.evaluate(usdm_data)
    print(score.overall_score)  # 0.95
    print(score.passes_thresholds())  # True/False

    # Get detailed issues
    for issue in score.accuracy_issues:
        print(issue)
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import jsonschema
from jsonschema import Draft7Validator

from soa_analyzer.soa_terminology_mapper import TerminologyMapper, get_mapper
from soa_analyzer.models import FootnoteLinkageResult

logger = logging.getLogger(__name__)

# Lazy import LLM mapper to avoid circular imports
_llm_mapper = None


def _get_llm_mapper():
    """Get LLM terminology mapper (lazy loaded)."""
    global _llm_mapper
    if _llm_mapper is None:
        try:
            from soa_analyzer.soa_llm_terminology_mapper import get_llm_mapper
            _llm_mapper = get_llm_mapper()
        except Exception as e:
            logger.warning(f"Failed to load LLM terminology mapper: {e}")
    return _llm_mapper

# USDM schema path
DEFAULT_USDM_SCHEMA_PATH = Path(__file__).parent.parent.parent / "USDM_API.json"

# Default quality thresholds
DEFAULT_THRESHOLDS = {
    "accuracy": 0.95,
    "completeness": 0.90,
    "compliance": 1.00,  # Must be 100%
    "provenance": 0.95,
    "terminology": 0.90,
}

# Required USDM fields by entity type
REQUIRED_FIELDS = {
    "ScheduleTimeline": ["id", "name", "mainTimeline", "instanceType"],
    "Activity": ["id", "name", "instanceType"],
    "Encounter": ["id", "name", "type", "instanceType"],
    "Timing": ["id", "name", "type", "value", "instanceType"],
    "ScheduledActivityInstance": ["id", "name", "instanceType"],
}

# Placeholder patterns to detect
PLACEHOLDER_PATTERNS = [
    "TBD",
    "TODO",
    "PLACEHOLDER",
    "N/A",
    "???",
    "[PLACEHOLDER]",
    "[TBD]",
    "[TODO]",
    "[N/A]",
    "NOT AVAILABLE",
    "NOT SPECIFIED",
    "VALUE_NOT_FOUND",
    "EXTRACTED_VALUE",
    "UNKNOWN",
    "UNSPECIFIED",
    "TO BE DETERMINED",
    "TO BE CONFIRMED",
    "PENDING",
    "<PLACEHOLDER>",
    "<TBD>",
    "STRING",
    "NULL",
    "NONE",
]


@dataclass
class QualityIssue:
    """Represents a quality issue found during evaluation."""
    dimension: str  # accuracy, completeness, compliance, provenance, terminology
    severity: str   # error, warning
    path: str       # JSON path to the issue
    message: str    # Description of the issue
    value: Any = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension,
            "severity": self.severity,
            "path": self.path,
            "message": self.message,
            "value": str(self.value) if self.value else None,
            "suggestion": self.suggestion,
        }


@dataclass
class QualityScore:
    """Quality assessment scores for SOA extraction output."""

    accuracy: float = 0.0     # 0.0 to 1.0
    completeness: float = 0.0
    compliance: float = 0.0
    provenance: float = 0.0
    terminology: float = 0.0

    # Detailed issues by dimension
    accuracy_issues: List[QualityIssue] = field(default_factory=list)
    completeness_issues: List[QualityIssue] = field(default_factory=list)
    compliance_issues: List[QualityIssue] = field(default_factory=list)
    provenance_issues: List[QualityIssue] = field(default_factory=list)
    terminology_issues: List[QualityIssue] = field(default_factory=list)

    # Counts for calculating scores
    total_fields: int = 0
    valid_fields: int = 0
    total_provenance: int = 0
    valid_provenance: int = 0
    total_terminology: int = 0
    valid_terminology: int = 0

    # Track unmapped terms for LLM fallback (term, path)
    unmapped_terms: List[Tuple[str, str]] = field(default_factory=list)
    llm_mapped_count: int = 0  # Count of terms mapped by LLM fallback

    # Linking quality metrics (Phase 4 - Cell-Level Linking)
    linking_coverage: float = 0.0         # Ratio of markers linked
    linking_confidence: float = 0.0       # Average confidence of links
    linking_precision: float = 0.0        # 1 - ambiguity rate
    linking_overall: float = 0.0          # Combined linking quality
    linking_strategy: str = "none"        # Strategy used for linking
    has_linking_result: bool = False      # Whether linking was performed

    @property
    def overall_score(self) -> float:
        """Weighted average of all dimensions."""
        weights = {
            "accuracy": 0.25,
            "completeness": 0.20,
            "compliance": 0.20,
            "provenance": 0.20,
            "terminology": 0.15,
        }
        return (
            self.accuracy * weights["accuracy"]
            + self.completeness * weights["completeness"]
            + self.compliance * weights["compliance"]
            + self.provenance * weights["provenance"]
            + self.terminology * weights["terminology"]
        )

    @property
    def status(self) -> str:
        """Return PASS or FAIL based on whether all thresholds are met."""
        return "PASS" if self.passes_thresholds() else "FAIL"

    def passes_thresholds(self, thresholds: Optional[Dict[str, float]] = None) -> bool:
        """Check if all dimensions meet thresholds."""
        t = thresholds or DEFAULT_THRESHOLDS
        return (
            self.accuracy >= t.get("accuracy", 0.95)
            and self.completeness >= t.get("completeness", 0.90)
            and self.compliance >= t.get("compliance", 1.0)
            and self.provenance >= t.get("provenance", 0.95)
            and self.terminology >= t.get("terminology", 0.90)
        )

    def get_failed_dimensions(self, thresholds: Optional[Dict[str, float]] = None) -> List[str]:
        """Return list of dimensions that failed thresholds."""
        t = thresholds or DEFAULT_THRESHOLDS
        failed = []
        if self.accuracy < t.get("accuracy", 0.95):
            failed.append("accuracy")
        if self.completeness < t.get("completeness", 0.90):
            failed.append("completeness")
        if self.compliance < t.get("compliance", 1.0):
            failed.append("compliance")
        if self.provenance < t.get("provenance", 0.95):
            failed.append("provenance")
        if self.terminology < t.get("terminology", 0.90):
            failed.append("terminology")
        return failed

    def all_issues(self) -> List[QualityIssue]:
        """Return all issues across all dimensions."""
        return (
            self.accuracy_issues
            + self.completeness_issues
            + self.compliance_issues
            + self.provenance_issues
            + self.terminology_issues
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "scores": {
                "accuracy": round(self.accuracy, 4),
                "completeness": round(self.completeness, 4),
                "compliance": round(self.compliance, 4),
                "provenance": round(self.provenance, 4),
                "terminology": round(self.terminology, 4),
                "overall": round(self.overall_score, 4),
            },
            "thresholds_met": self.passes_thresholds(),
            "failed_dimensions": self.get_failed_dimensions(),
            "counts": {
                "total_fields": self.total_fields,
                "valid_fields": self.valid_fields,
                "total_provenance": self.total_provenance,
                "valid_provenance": self.valid_provenance,
                "total_terminology": self.total_terminology,
                "valid_terminology": self.valid_terminology,
            },
            "issues": {
                "accuracy": [i.to_dict() for i in self.accuracy_issues],
                "completeness": [i.to_dict() for i in self.completeness_issues],
                "compliance": [i.to_dict() for i in self.compliance_issues],
                "provenance": [i.to_dict() for i in self.provenance_issues],
                "terminology": [i.to_dict() for i in self.terminology_issues],
            },
        }

        # Add linking metrics if linking was performed
        if self.has_linking_result:
            result["linking"] = {
                "coverage": round(self.linking_coverage, 4),
                "confidence": round(self.linking_confidence, 4),
                "precision": round(self.linking_precision, 4),
                "overall": round(self.linking_overall, 4),
                "strategy": self.linking_strategy,
            }

        return result

    def __str__(self) -> str:
        """String representation for logging."""
        status = "PASS" if self.passes_thresholds() else "FAIL"
        return (
            f"QualityScore({status}): "
            f"accuracy={self.accuracy:.1%}, "
            f"completeness={self.completeness:.1%}, "
            f"compliance={self.compliance:.1%}, "
            f"provenance={self.provenance:.1%}, "
            f"terminology={self.terminology:.1%}, "
            f"overall={self.overall_score:.1%}"
        )


class SOAQualityChecker:
    """
    Quality checker for SOA extraction outputs.

    Evaluates data against 5 dimensions:
    1. Accuracy - No placeholders, valid formats
    2. Completeness - Required USDM fields present
    3. Compliance - Valid against USDM 4.0 schema
    4. Provenance - Page references present
    5. Terminology - CDISC/OMOP codes valid
    """

    def __init__(
        self,
        usdm_schema_path: Optional[Path] = None,
        terminology_mapper: Optional[TerminologyMapper] = None,
        thresholds: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize quality checker.

        Args:
            usdm_schema_path: Path to USDM 4.0 OpenAPI schema
            terminology_mapper: TerminologyMapper instance
            thresholds: Custom quality thresholds
        """
        self.usdm_schema_path = usdm_schema_path or DEFAULT_USDM_SCHEMA_PATH
        self.thresholds = thresholds or DEFAULT_THRESHOLDS
        self.terminology_mapper = terminology_mapper

        # Load USDM schema
        self._usdm_schema: Optional[Dict[str, Any]] = None
        self._load_schema()

        logger.info(f"SOAQualityChecker initialized (schema: {self.usdm_schema_path})")

    def _load_schema(self):
        """Load USDM schema for compliance validation."""
        if not self.usdm_schema_path.exists():
            logger.warning(f"USDM schema not found: {self.usdm_schema_path}")
            return

        try:
            with open(self.usdm_schema_path, 'r') as f:
                openapi_schema = json.load(f)
            # Extract component schemas
            self._usdm_schema = openapi_schema.get("components", {}).get("schemas", {})
            logger.info(f"Loaded USDM schema with {len(self._usdm_schema)} definitions")
        except Exception as e:
            logger.error(f"Failed to load USDM schema: {e}")

    def _get_terminology_mapper(self) -> TerminologyMapper:
        """Get or create terminology mapper."""
        if self.terminology_mapper is None:
            self.terminology_mapper = get_mapper()
        return self.terminology_mapper

    def _extract_study_version_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract study version data, handling both flat and nested USDM 4.0 structures.

        USDM 4.0 structure nests data under studyVersion[0], but we may also receive
        flat structures from intermediate processing.

        Args:
            data: USDM-formatted SOA extraction output

        Returns:
            The study version data with scheduleTimelines, encounters, activities, etc.
        """
        # Check for USDM 4.0 nested structure: studyVersion[0]
        if "studyVersion" in data and isinstance(data["studyVersion"], list):
            if len(data["studyVersion"]) > 0:
                return data["studyVersion"][0]

        # Already flat structure or interpretation output (has visits/activities directly)
        # Map 'visits' to 'encounters' and 'scheduledActivityInstances' for backwards compat
        if "visits" in data and "encounters" not in data:
            result = dict(data)
            result["encounters"] = data.get("visits", [])
            return result

        return data

    def evaluate(
        self,
        data: Dict[str, Any],
        linking_result: Optional[FootnoteLinkageResult] = None,
    ) -> QualityScore:
        """
        Evaluate SOA extraction quality across all 5 dimensions.

        Args:
            data: USDM-formatted SOA extraction output
            linking_result: Optional cell-level linking result from Stage 6.5

        Returns:
            QualityScore with detailed issues
        """
        score = QualityScore()

        # Extract study version data (handles nested USDM 4.0 structure)
        study_version_data = self._extract_study_version_data(data)

        # 1. Check Accuracy (against full data for placeholder detection)
        self._check_accuracy(data, score)

        # 2. Check Completeness (against extracted study version)
        self._check_completeness(study_version_data, score)

        # 3. Check Compliance (against full data for schema validation)
        self._check_compliance(study_version_data, score)

        # 4. Check Provenance (against extracted study version)
        self._check_provenance(study_version_data, score)

        # 5. Check Terminology (against extracted study version)
        self._check_terminology(study_version_data, score)

        # 6. Check Linking Quality (if linking result provided)
        if linking_result:
            self._check_linking_quality(linking_result, score)

        logger.info(f"Quality evaluation: {score}")
        return score

    def _check_accuracy(self, data: Dict[str, Any], score: QualityScore, path: str = "$"):
        """
        Check accuracy dimension.

        Validates:
        - No placeholder values
        - Valid date/time formats
        - No empty required fields
        """
        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}"
                score.total_fields += 1

                # Check for placeholder values
                if isinstance(value, str):
                    if self._is_placeholder(value):
                        score.accuracy_issues.append(QualityIssue(
                            dimension="accuracy",
                            severity="error",
                            path=current_path,
                            message="Placeholder value detected",
                            value=value,
                            suggestion="Extract actual value from protocol",
                        ))
                    else:
                        score.valid_fields += 1

                    # Check date format if applicable
                    if key in ["date", "startDate", "endDate", "validFrom", "validTo"]:
                        if not self._is_valid_date(value):
                            score.accuracy_issues.append(QualityIssue(
                                dimension="accuracy",
                                severity="warning",
                                path=current_path,
                                message="Invalid date format",
                                value=value,
                                suggestion="Use ISO 8601 format (YYYY-MM-DD)",
                            ))

                    # Check time format if applicable
                    # Exclude ID reference fields (e.g., scheduledInstanceTimelineId) from time format validation
                    is_id_field = key.endswith("Id") or key.endswith("_id")
                    if ("time" in key.lower() or "duration" in key.lower()) and not is_id_field:
                        if not self._is_valid_time_or_duration(value):
                            score.accuracy_issues.append(QualityIssue(
                                dimension="accuracy",
                                severity="warning",
                                path=current_path,
                                message="Invalid time/duration format",
                                value=value,
                            ))
                elif value is not None:
                    score.valid_fields += 1

                # Recurse into nested structures
                self._check_accuracy(value, score, current_path)

        elif isinstance(data, list):
            for i, item in enumerate(data):
                self._check_accuracy(item, score, f"{path}[{i}]")

        # Calculate accuracy score
        if score.total_fields > 0:
            error_count = len([i for i in score.accuracy_issues if i.severity == "error"])
            score.accuracy = max(0, (score.total_fields - error_count) / score.total_fields)
        else:
            score.accuracy = 1.0

    def _is_placeholder(self, value: str) -> bool:
        """Check if value is a placeholder."""
        if not value:
            return False
        upper = value.upper().strip()
        return any(p in upper for p in PLACEHOLDER_PATTERNS)

    def _is_valid_date(self, value: str) -> bool:
        """Check if value is a valid ISO 8601 date."""
        date_patterns = [
            r"^\d{4}-\d{2}-\d{2}$",  # YYYY-MM-DD
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",  # ISO datetime
            r"^\d{4}-\d{2}$",  # YYYY-MM
            r"^\d{4}$",  # YYYY
        ]
        return any(re.match(p, value) for p in date_patterns)

    def _is_valid_time_or_duration(self, value: str) -> bool:
        """Check if value is a valid time or duration format."""
        patterns = [
            r"^PT?\d+[HMSDY]",  # ISO 8601 duration (PT1H, P1D, etc.)
            r"^\d+\s*(hours?|minutes?|days?|weeks?|months?|years?)",  # Natural language
            r"^\d{2}:\d{2}(:\d{2})?$",  # HH:MM or HH:MM:SS
            r"^[-+]?\d+$",  # Numeric value
        ]
        return any(re.match(p, value, re.IGNORECASE) for p in patterns)

    def _check_completeness(self, data: Dict[str, Any], score: QualityScore):
        """
        Check completeness dimension.

        Validates:
        - Required USDM fields present
        - Activities are mapped
        - Encounters are defined
        """
        required_count = 0
        present_count = 0

        # Check top-level required arrays
        top_level_required = ["scheduleTimelines", "activities", "encounters"]
        for field in top_level_required:
            required_count += 1
            if field in data and data[field]:
                present_count += 1
            else:
                score.completeness_issues.append(QualityIssue(
                    dimension="completeness",
                    severity="error",
                    path=f"$.{field}",
                    message=f"Required array '{field}' is missing or empty",
                ))

        # Check entity-specific required fields
        entity_mapping = {
            "scheduleTimelines": "ScheduleTimeline",
            "activities": "Activity",
            "encounters": "Encounter",
            "timings": "Timing",
        }

        for array_name, entity_type in entity_mapping.items():
            if array_name in data and isinstance(data[array_name], list):
                for i, item in enumerate(data[array_name]):
                    if isinstance(item, dict):
                        for required_field in REQUIRED_FIELDS.get(entity_type, []):
                            required_count += 1
                            if required_field in item and item[required_field]:
                                present_count += 1
                            else:
                                score.completeness_issues.append(QualityIssue(
                                    dimension="completeness",
                                    severity="error",
                                    path=f"$.{array_name}[{i}].{required_field}",
                                    message=f"Required field '{required_field}' missing in {entity_type}",
                                ))

        # Calculate completeness score
        if required_count > 0:
            score.completeness = present_count / required_count
        else:
            score.completeness = 1.0

    def _check_compliance(self, data: Dict[str, Any], score: QualityScore):
        """
        Check compliance dimension.

        Validates against USDM 4.0 schema using jsonschema.
        """
        if not self._usdm_schema:
            logger.warning("USDM schema not loaded, skipping compliance check")
            score.compliance = 1.0
            return

        # For each entity type, validate against corresponding schema
        entity_mapping = {
            "scheduleTimelines": "ScheduleTimeline-Output",
            "activities": "Activity-Output",
            "encounters": "Encounter-Output",
            "timings": "Timing-Output",
        }

        total_validations = 0
        passed_validations = 0

        for array_name, schema_name in entity_mapping.items():
            if array_name not in data or not isinstance(data[array_name], list):
                continue

            schema_def = self._usdm_schema.get(schema_name)
            if not schema_def:
                continue

            for i, item in enumerate(data[array_name]):
                total_validations += 1
                try:
                    # Build a validator with refs resolved
                    validator = Draft7Validator(
                        schema_def,
                        resolver=jsonschema.RefResolver.from_schema(
                            {"components": {"schemas": self._usdm_schema}}
                        )
                    )

                    errors = list(validator.iter_errors(item))
                    if not errors:
                        passed_validations += 1
                    else:
                        for error in errors[:3]:  # Limit to first 3 errors
                            score.compliance_issues.append(QualityIssue(
                                dimension="compliance",
                                severity="error",
                                path=f"$.{array_name}[{i}]",
                                message=error.message,
                                value=str(error.instance)[:100] if error.instance else None,
                            ))
                except Exception as e:
                    logger.warning(f"Schema validation error for {array_name}[{i}]: {e}")
                    # Don't count as failure if validation itself fails
                    passed_validations += 1

        # Calculate compliance score
        if total_validations > 0:
            score.compliance = passed_validations / total_validations
        else:
            score.compliance = 1.0

    def _check_provenance(self, data: Dict[str, Any], score: QualityScore, path: str = "$"):
        """
        Check provenance dimension.

        Validates that extracted values have source page references.
        """
        if isinstance(data, dict):
            # Check if this dict has a provenance field
            has_provenance = "provenance" in data or "page_number" in data or "pageNumber" in data

            # Count value fields that need provenance
            value_fields = ["value", "name", "description", "label"]
            for field in value_fields:
                if field in data and data[field]:
                    # Skip window.description - it's a derived/computed field that doesn't need provenance
                    if field == "description" and path.endswith(".window"):
                        continue

                    score.total_provenance += 1
                    if has_provenance:
                        score.valid_provenance += 1
                    else:
                        score.provenance_issues.append(QualityIssue(
                            dimension="provenance",
                            severity="warning",
                            path=f"{path}.{field}",
                            message="Value lacks provenance (page reference)",
                            value=str(data[field])[:50],
                        ))

            # Check nested provenance object
            if "provenance" in data and isinstance(data["provenance"], dict):
                prov = data["provenance"]
                if "page_number" not in prov and "pageNumber" not in prov:
                    score.provenance_issues.append(QualityIssue(
                        dimension="provenance",
                        severity="warning",
                        path=f"{path}.provenance",
                        message="Provenance object missing page_number",
                    ))

            # Recurse
            for key, value in data.items():
                if key != "provenance":  # Don't recurse into provenance itself
                    self._check_provenance(value, score, f"{path}.{key}")

        elif isinstance(data, list):
            for i, item in enumerate(data):
                self._check_provenance(item, score, f"{path}[{i}]")

        # Calculate provenance score
        if score.total_provenance > 0:
            score.provenance = score.valid_provenance / score.total_provenance
        else:
            score.provenance = 1.0

    def _check_terminology(self, data: Dict[str, Any], score: QualityScore, path: str = "$"):
        """
        Check terminology dimension.

        Validates CDISC codes and OMOP concept mappings.
        Note: Skips OMOP queries during validation (already done in enrichment stage)
        to avoid slow 17GB database queries. Only validates in-memory CDISC concepts.
        """
        mapper = self._get_terminology_mapper()

        if isinstance(data, dict):
            # Check CDISC code fields
            cdisc_fields = ["cdiscCode", "cdisc_code", "domain", "testCode"]
            for field in cdisc_fields:
                if field in data and data[field]:
                    score.total_terminology += 1
                    # For now, mark as valid - actual validation would check against cdisc_concepts.json
                    score.valid_terminology += 1

            # Check activity/procedure names for terminology mapping
            # Use CDISC-only lookup (in-memory) to avoid slow OMOP queries
            if "name" in data and isinstance(data["name"], str):
                name = data["name"]
                # Only check if it looks like a clinical term (not an ID)
                if not name.startswith(("ACT-", "ENC-", "TIM-", "SCH-", "SAI-")):
                    # Fast in-memory lookup: CDISC concepts + CDISC codelists (skip OMOP)
                    cdisc_match = mapper._match_cdisc_exact(name) or mapper._match_cdisc_fuzzy(name)
                    codelist_match = mapper._match_codelist(name) if not cdisc_match else None
                    if cdisc_match or codelist_match:
                        score.total_terminology += 1
                        score.valid_terminology += 1
                    else:
                        # Track for LLM fallback (deterministic failed)
                        score.total_terminology += 1
                        score.unmapped_terms.append((name, path))
                        score.terminology_issues.append(QualityIssue(
                            dimension="terminology",
                            severity="warning",
                            path=path,
                            message="Clinical term not mapped to CDISC terminology",
                            value=name,
                            suggestion="Consider mapping to CDISC concept",
                        ))

            # Recurse
            for key, value in data.items():
                self._check_terminology(value, score, f"{path}.{key}")

        elif isinstance(data, list):
            for i, item in enumerate(data):
                self._check_terminology(item, score, f"{path}[{i}]")

        # Calculate terminology score
        if score.total_terminology > 0:
            score.terminology = score.valid_terminology / score.total_terminology
        else:
            score.terminology = 1.0

    def _check_linking_quality(
        self,
        linking_result: FootnoteLinkageResult,
        score: QualityScore,
    ) -> None:
        """
        Check linking quality dimension (Phase 4 - Cell-Level Linking).

        Evaluates the quality of footnote-to-cell linking:
        - Coverage: Ratio of markers successfully linked
        - Confidence: Average confidence of links
        - Precision: 1 - ambiguity rate (markers in >3 cells)

        These metrics contribute to the Provenance dimension's quality.
        """
        score.has_linking_result = True
        score.linking_strategy = linking_result.strategy_used.value

        # Calculate linking coverage
        if linking_result.total_markers > 0:
            score.linking_coverage = linking_result.markers_linked / linking_result.total_markers
        else:
            score.linking_coverage = 1.0

        # Calculate average confidence
        if linking_result.linked_footnotes:
            confidences = [fn.linkage_confidence for fn in linking_result.linked_footnotes]
            score.linking_confidence = sum(confidences) / len(confidences)
        else:
            score.linking_confidence = 0.0

        # Calculate precision (1 - ambiguity rate)
        if linking_result.markers_linked > 0:
            ambiguity_rate = linking_result.ambiguous_markers / linking_result.markers_linked
            score.linking_precision = 1.0 - ambiguity_rate
        else:
            score.linking_precision = 1.0

        # Calculate overall linking quality
        # Weighted combination: coverage 40%, precision 30%, confidence 30%
        score.linking_overall = (
            score.linking_coverage * 0.4
            + score.linking_precision * 0.3
            + score.linking_confidence * 0.3
        )

        # Add issues for low quality linking
        thresholds = {
            "min_coverage": 0.50,
            "min_confidence": 0.60,
            "min_precision": 0.80,
        }

        if score.linking_coverage < thresholds["min_coverage"]:
            score.provenance_issues.append(QualityIssue(
                dimension="provenance",
                severity="warning",
                path="$.linking.coverage",
                message=f"Low linking coverage: {score.linking_coverage:.0%}",
                value=f"{linking_result.markers_linked}/{linking_result.total_markers} markers linked",
                suggestion="Review unlinked footnotes for OCR errors or missing markers",
            ))

        if score.linking_confidence < thresholds["min_confidence"]:
            score.provenance_issues.append(QualityIssue(
                dimension="provenance",
                severity="warning",
                path="$.linking.confidence",
                message=f"Low linking confidence: {score.linking_confidence:.0%}",
                suggestion="Review low-confidence links for accuracy",
            ))

        if score.linking_precision < thresholds["min_precision"]:
            score.provenance_issues.append(QualityIssue(
                dimension="provenance",
                severity="warning",
                path="$.linking.precision",
                message=f"High ambiguity in linking: {linking_result.ambiguous_markers} ambiguous markers",
                value=f"{linking_result.ambiguous_markers} markers linked to >3 cells",
                suggestion="Review ambiguous markers for scope determination",
            ))

        # Log linking quality summary
        logger.info(
            f"Linking quality: coverage={score.linking_coverage:.0%}, "
            f"confidence={score.linking_confidence:.0%}, "
            f"precision={score.linking_precision:.0%}, "
            f"overall={score.linking_overall:.0%}, "
            f"strategy={score.linking_strategy}"
        )

        # Integrate linking quality into provenance score
        # Adjust provenance based on linking quality (25% weight)
        if score.total_provenance > 0:
            base_provenance = score.valid_provenance / score.total_provenance
            # Blend: 75% page references + 25% cell linking
            score.provenance = base_provenance * 0.75 + score.linking_overall * 0.25
        else:
            # If no provenance checks, use linking quality directly
            score.provenance = score.linking_overall

    async def _apply_llm_fallback(self, score: QualityScore) -> None:
        """
        Apply LLM fallback for unmapped terminology.

        Uses batch LLM call to map all unmapped terms efficiently.
        Updates score and removes issues for successfully mapped terms.
        """
        if not score.unmapped_terms:
            logger.debug("No unmapped terms for LLM fallback")
            return

        llm_mapper = _get_llm_mapper()
        if not llm_mapper:
            logger.warning("LLM mapper not available for fallback")
            return

        # Extract unique terms (avoid duplicate LLM calls)
        unique_terms = list(set(term for term, _ in score.unmapped_terms))
        logger.info(f"LLM terminology fallback for {len(unique_terms)} unique terms...")

        try:
            # Batch LLM call (single API call for efficiency)
            batch_result = await llm_mapper.map_batch(unique_terms)

            # Track which terms were successfully mapped
            mapped_paths: Set[str] = set()
            mapped_count = 0

            for term, path in score.unmapped_terms:
                mapping = batch_result.get_mapping(term)
                if mapping and mapping.is_mapped():
                    mapped_paths.add(path)
                    mapped_count += 1

            # Update score
            score.valid_terminology += mapped_count
            score.llm_mapped_count = mapped_count

            # Remove issues for terms that were successfully mapped
            if mapped_paths:
                score.terminology_issues = [
                    issue for issue in score.terminology_issues
                    if issue.path not in mapped_paths
                ]

            # Recalculate terminology score
            if score.total_terminology > 0:
                score.terminology = score.valid_terminology / score.total_terminology
            else:
                score.terminology = 1.0

            logger.info(
                f"LLM fallback complete: {mapped_count}/{len(unique_terms)} terms mapped, "
                f"cache hits={batch_result.cache_hits}, llm calls={batch_result.llm_calls}"
            )

        except Exception as e:
            logger.error(f"LLM terminology fallback failed: {e}")
            # Don't modify score if LLM fails - keep deterministic results

    async def evaluate_with_llm(
        self,
        data: Dict[str, Any],
        linking_result: Optional[FootnoteLinkageResult] = None,
        use_llm_fallback: bool = True,
    ) -> QualityScore:
        """
        Evaluate SOA extraction quality with optional LLM terminology fallback.

        This async version first runs deterministic evaluation, then applies
        LLM-based terminology mapping as a fallback for unmapped terms.

        Args:
            data: USDM-formatted SOA extraction output
            linking_result: Optional cell-level linking result
            use_llm_fallback: Whether to use LLM for unmapped terms (default: True)

        Returns:
            QualityScore with detailed issues
        """
        # Run deterministic evaluation first
        score = self.evaluate(data, linking_result)

        # Apply LLM fallback if enabled and there are unmapped terms
        if use_llm_fallback and score.unmapped_terms:
            await self._apply_llm_fallback(score)

        return score

    def generate_report(self, score: QualityScore) -> str:
        """
        Generate a human-readable quality report.

        Args:
            score: QualityScore from evaluate()

        Returns:
            Formatted report string
        """
        lines = []
        lines.append("=" * 60)
        lines.append("SOA QUALITY REPORT")
        lines.append("=" * 60)
        lines.append("")

        # Overall status
        status = "PASS" if score.passes_thresholds(self.thresholds) else "FAIL"
        lines.append(f"Overall Status: {status}")
        lines.append(f"Overall Score: {score.overall_score:.1%}")
        lines.append("")

        # Dimension scores
        lines.append("DIMENSION SCORES")
        lines.append("-" * 40)
        dimensions = [
            ("Accuracy", score.accuracy, self.thresholds.get("accuracy", 0.95)),
            ("Completeness", score.completeness, self.thresholds.get("completeness", 0.90)),
            ("Compliance", score.compliance, self.thresholds.get("compliance", 1.0)),
            ("Provenance", score.provenance, self.thresholds.get("provenance", 0.95)),
            ("Terminology", score.terminology, self.thresholds.get("terminology", 0.90)),
        ]

        for name, value, threshold in dimensions:
            status_icon = "PASS" if value >= threshold else "FAIL"
            lines.append(f"  {name}: {value:.1%} (threshold: {threshold:.0%}) [{status_icon}]")

        # Add linking quality if available
        if score.has_linking_result:
            lines.append("")
            lines.append("CELL LINKING QUALITY")
            lines.append("-" * 40)
            lines.append(f"  Strategy: {score.linking_strategy}")
            lines.append(f"  Coverage: {score.linking_coverage:.1%}")
            lines.append(f"  Confidence: {score.linking_confidence:.1%}")
            lines.append(f"  Precision: {score.linking_precision:.1%}")
            lines.append(f"  Overall: {score.linking_overall:.1%}")

        # Add LLM terminology stats if used
        if score.llm_mapped_count > 0:
            lines.append("")
            lines.append("LLM TERMINOLOGY FALLBACK")
            lines.append("-" * 40)
            lines.append(f"  Terms mapped by LLM: {score.llm_mapped_count}")
            lines.append(f"  Remaining unmapped: {len(score.terminology_issues)}")

        lines.append("")

        # Issues summary
        lines.append("ISSUES SUMMARY")
        lines.append("-" * 40)
        issue_counts = {
            "Accuracy": len(score.accuracy_issues),
            "Completeness": len(score.completeness_issues),
            "Compliance": len(score.compliance_issues),
            "Provenance": len(score.provenance_issues),
            "Terminology": len(score.terminology_issues),
        }

        total_issues = sum(issue_counts.values())
        lines.append(f"  Total Issues: {total_issues}")
        for dim, count in issue_counts.items():
            if count > 0:
                lines.append(f"    {dim}: {count}")

        # Detailed issues (first 5 per dimension)
        if total_issues > 0:
            lines.append("")
            lines.append("TOP ISSUES")
            lines.append("-" * 40)

            all_issues = score.all_issues()
            for issue in all_issues[:10]:
                lines.append(f"  [{issue.dimension.upper()}] {issue.path}")
                lines.append(f"    {issue.message}")
                if issue.value:
                    lines.append(f"    Value: {issue.value}")
                if issue.suggestion:
                    lines.append(f"    Suggestion: {issue.suggestion}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)


# Singleton instance
_checker_instance: Optional[SOAQualityChecker] = None


def get_quality_checker() -> SOAQualityChecker:
    """Get the singleton quality checker instance."""
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = SOAQualityChecker()
    return _checker_instance


# CLI support
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    def print_usage():
        print("Usage: python soa_quality_checker.py <usdm_json_file>")
        print("\nEvaluates SOA extraction quality against 5 dimensions.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print_usage()

    json_path = sys.argv[1]
    if not Path(json_path).exists():
        print(f"Error: File not found: {json_path}")
        sys.exit(1)

    try:
        with open(json_path, 'r') as f:
            data = json.load(f)

        checker = get_quality_checker()
        score = checker.evaluate(data)

        # Print report
        print(checker.generate_report(score))

        # Exit with appropriate code
        sys.exit(0 if score.passes_thresholds() else 1)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
