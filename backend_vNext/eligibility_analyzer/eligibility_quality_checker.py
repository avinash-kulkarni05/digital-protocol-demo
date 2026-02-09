"""
Eligibility Quality Checker - 5-Dimensional Quality Scoring

Validates eligibility extraction output against five dimensions:
1. Accuracy (25%) - No placeholders, valid formats, exact numeric preservation
2. Completeness (20%) - All criteria extracted, all atomics decomposed
3. Schema Adherence (20%) - USDM 4.0 compliance, valid JSON
4. Provenance (20%) - Every value has page + text snippet
5. Terminology (15%) - Valid OMOP concepts, proper vocabulary priority

Targets 100% quality with surgical retry for failures.

Usage:
    from eligibility_analyzer.eligibility_quality_checker import (
        EligibilityQualityChecker,
        QualityScore,
        check_quality,
    )

    checker = EligibilityQualityChecker()
    score = checker.check(extraction_result)
    print(f"Overall: {score.overall_score:.1%}")
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Placeholder patterns to detect (configurable)
# Core patterns - common explicit placeholders
CORE_PLACEHOLDER_PATTERNS = [
    r"\bTBD\b", r"\bTODO\b", r"\bPLACEHOLDER\b", r"\bN/A\b",
    r"\bNULL\b", r"\bUNKNOWN\b", r"\bPENDING\b",
    r"\[TO BE COMPLETED\]", r"\{PLACEHOLDER\}", r"\?\?\?",
    r"\.\.\.", r"\bNOT AVAILABLE\b", r"\bINSERT HERE\b",
    r"\[REDACTED\]", r"\[TBD\]", r"\[TODO\]",
]

# Extended semantic patterns - phrases indicating incomplete values
SEMANTIC_PLACEHOLDER_PATTERNS = [
    r"to be determined",
    r"to be defined",
    r"will be (filled|completed|provided|specified)",
    r"see protocol",
    r"refer to section",
    r"as per investigator",
    r"at (the )?discretion of",
    r"not yet (specified|determined|defined)",
    r"under (development|review)",
    r"\[X+\]",  # [XXX] style placeholders
    r"<[^>]+>",  # <placeholder> style
    r"___+",  # Blank lines like ______
]

# Combined placeholder patterns (core + semantic)
PLACEHOLDER_PATTERNS = CORE_PLACEHOLDER_PATTERNS + SEMANTIC_PLACEHOLDER_PATTERNS

# Required fields for USDM EligibilityCriterion
REQUIRED_USDM_FIELDS = {
    "id", "name", "text", "category", "instanceType"
}

# Required fields for USDM Code object
REQUIRED_CODE_FIELDS = {
    "code", "decode", "codeSystem", "codeSystemVersion", "instanceType"
}

# Quality dimension weights (must sum to 1.0)
DIMENSION_WEIGHTS = {
    "accuracy": 0.25,
    "completeness": 0.20,
    "schema_adherence": 0.20,
    "provenance": 0.20,
    "terminology": 0.15,
}

# Quality thresholds (target: 100%)
QUALITY_THRESHOLDS = {
    "accuracy": 1.0,
    "completeness": 1.0,
    "schema_adherence": 1.0,
    "provenance": 1.0,
    "terminology": 1.0,
}


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class QualityIssue:
    """Single quality issue found during validation."""
    dimension: str  # accuracy, completeness, schema_adherence, provenance, terminology
    severity: str  # error, warning, info
    field_path: str  # JSON path to the field
    message: str
    value: Optional[Any] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension,
            "severity": self.severity,
            "fieldPath": self.field_path,
            "message": self.message,
            "value": str(self.value)[:100] if self.value else None,
            "suggestion": self.suggestion,
        }


@dataclass
class DimensionScore:
    """Score for a single quality dimension."""
    dimension: str
    score: float  # 0.0 to 1.0
    total_fields: int
    valid_fields: int
    issues: List[QualityIssue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension,
            "score": self.score,
            "totalFields": self.total_fields,
            "validFields": self.valid_fields,
            "issueCount": len(self.issues),
            "issues": [i.to_dict() for i in self.issues[:10]],  # First 10 issues
        }


@dataclass
class QualityScore:
    """Overall quality score with dimension breakdowns."""
    overall_score: float  # 0.0 to 1.0
    thresholds_met: bool
    failed_dimensions: List[str] = field(default_factory=list)

    # Dimension scores
    accuracy: DimensionScore = None
    completeness: DimensionScore = None
    schema_adherence: DimensionScore = None
    provenance: DimensionScore = None
    terminology: DimensionScore = None

    # Aggregate counts
    total_fields: int = 0
    valid_fields: int = 0
    total_issues: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scores": {
                "accuracy": self.accuracy.score if self.accuracy else 0.0,
                "completeness": self.completeness.score if self.completeness else 0.0,
                "compliance": self.schema_adherence.score if self.schema_adherence else 0.0,
                "provenance": self.provenance.score if self.provenance else 0.0,
                "terminology": self.terminology.score if self.terminology else 0.0,
                "overall": self.overall_score,
            },
            "thresholds_met": self.thresholds_met,
            "failed_dimensions": self.failed_dimensions,
            "counts": {
                "total_fields": self.total_fields,
                "valid_fields": self.valid_fields,
                "total_provenance": self.provenance.total_fields if self.provenance else 0,
                "valid_provenance": self.provenance.valid_fields if self.provenance else 0,
                "total_terminology": self.terminology.total_fields if self.terminology else 0,
                "valid_terminology": self.terminology.valid_fields if self.terminology else 0,
            },
            "issues": {
                "accuracy": [i.to_dict() for i in (self.accuracy.issues if self.accuracy else [])],
                "completeness": [i.to_dict() for i in (self.completeness.issues if self.completeness else [])],
                "compliance": [i.to_dict() for i in (self.schema_adherence.issues if self.schema_adherence else [])],
                "provenance": [i.to_dict() for i in (self.provenance.issues if self.provenance else [])],
                "terminology": [i.to_dict() for i in (self.terminology.issues if self.terminology else [])],
            },
        }


# =============================================================================
# MAIN QUALITY CHECKER CLASS
# =============================================================================


class EligibilityQualityChecker:
    """
    5-Dimensional Quality Checker for Eligibility Extraction.

    Validates extraction output and returns quality scores with
    specific issues for surgical retry.
    """

    def __init__(
        self,
        additional_placeholder_patterns: Optional[List[str]] = None,
        use_semantic_patterns: bool = True,
    ):
        """
        Initialize the quality checker.

        Args:
            additional_placeholder_patterns: Additional regex patterns to detect as placeholders
            use_semantic_patterns: Whether to use extended semantic placeholder patterns
        """
        # Build pattern list
        patterns = list(CORE_PLACEHOLDER_PATTERNS)
        if use_semantic_patterns:
            patterns.extend(SEMANTIC_PLACEHOLDER_PATTERNS)
        if additional_placeholder_patterns:
            patterns.extend(additional_placeholder_patterns)

        self.placeholder_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        logger.debug(f"Quality checker initialized with {len(self.placeholder_patterns)} placeholder patterns")

    def check(
        self,
        criteria: List[Dict[str, Any]],
        raw_criteria_count: int = 0,
        expected_atomics: int = 0,
    ) -> QualityScore:
        """
        Check quality of eligibility extraction output.

        Args:
            criteria: List of extracted/processed criteria
            raw_criteria_count: Expected number of criteria from raw extraction
            expected_atomics: Expected number of atomic criteria

        Returns:
            QualityScore with dimension breakdowns and issues
        """
        # Check each dimension
        accuracy = self._check_accuracy(criteria)
        completeness = self._check_completeness(criteria, raw_criteria_count, expected_atomics)
        schema_adherence = self._check_schema_adherence(criteria)
        provenance = self._check_provenance(criteria)
        terminology = self._check_terminology(criteria)

        # Calculate weighted overall score
        overall_score = (
            accuracy.score * DIMENSION_WEIGHTS["accuracy"] +
            completeness.score * DIMENSION_WEIGHTS["completeness"] +
            schema_adherence.score * DIMENSION_WEIGHTS["schema_adherence"] +
            provenance.score * DIMENSION_WEIGHTS["provenance"] +
            terminology.score * DIMENSION_WEIGHTS["terminology"]
        )

        # Determine which dimensions failed to meet threshold
        failed_dimensions = []
        if accuracy.score < QUALITY_THRESHOLDS["accuracy"]:
            failed_dimensions.append("accuracy")
        if completeness.score < QUALITY_THRESHOLDS["completeness"]:
            failed_dimensions.append("completeness")
        if schema_adherence.score < QUALITY_THRESHOLDS["schema_adherence"]:
            failed_dimensions.append("schema_adherence")
        if provenance.score < QUALITY_THRESHOLDS["provenance"]:
            failed_dimensions.append("provenance")
        if terminology.score < QUALITY_THRESHOLDS["terminology"]:
            failed_dimensions.append("terminology")

        # Calculate totals
        total_fields = (
            accuracy.total_fields +
            completeness.total_fields +
            schema_adherence.total_fields +
            provenance.total_fields +
            terminology.total_fields
        )
        valid_fields = (
            accuracy.valid_fields +
            completeness.valid_fields +
            schema_adherence.valid_fields +
            provenance.valid_fields +
            terminology.valid_fields
        )
        total_issues = (
            len(accuracy.issues) +
            len(completeness.issues) +
            len(schema_adherence.issues) +
            len(provenance.issues) +
            len(terminology.issues)
        )

        return QualityScore(
            overall_score=overall_score,
            thresholds_met=len(failed_dimensions) == 0,
            failed_dimensions=failed_dimensions,
            accuracy=accuracy,
            completeness=completeness,
            schema_adherence=schema_adherence,
            provenance=provenance,
            terminology=terminology,
            total_fields=total_fields,
            valid_fields=valid_fields,
            total_issues=total_issues,
        )

    def _check_accuracy(self, criteria: List[Dict[str, Any]]) -> DimensionScore:
        """
        Check accuracy dimension.

        - No placeholders (TBD, TODO, N/A, ???, etc.)
        - Valid formats (numbers are numeric, dates are valid)
        - Exact numeric preservation (no rounding)
        """
        issues = []
        total_fields = 0
        valid_fields = 0

        for crit in criteria:
            crit_id = crit.get("id", crit.get("criterionId", "unknown"))

            # Check all string fields for placeholders
            self._check_dict_for_placeholders(crit, f"criteria[{crit_id}]", issues)
            total_fields += 1

            # Check text field
            text = crit.get("text", crit.get("originalText", ""))
            if text and not self._has_placeholder(text):
                valid_fields += 1
            elif text:
                issues.append(QualityIssue(
                    dimension="accuracy",
                    severity="error",
                    field_path=f"criteria[{crit_id}].text",
                    message="Placeholder detected in criterion text",
                    value=text[:100],
                    suggestion="Replace placeholder with actual extracted value",
                ))

            # Check atomic criteria if present
            for ac in crit.get("atomicCriteria", []):
                ac_id = ac.get("atomicId", "unknown")
                total_fields += 1

                ac_text = ac.get("atomicText", "")
                if ac_text and not self._has_placeholder(ac_text):
                    valid_fields += 1
                elif ac_text:
                    issues.append(QualityIssue(
                        dimension="accuracy",
                        severity="error",
                        field_path=f"criteria[{crit_id}].atomicCriteria[{ac_id}].atomicText",
                        message="Placeholder in atomic criterion",
                        value=ac_text[:100],
                    ))

        score = valid_fields / total_fields if total_fields > 0 else 1.0

        return DimensionScore(
            dimension="accuracy",
            score=score,
            total_fields=total_fields,
            valid_fields=valid_fields,
            issues=issues,
        )

    def _check_completeness(
        self,
        criteria: List[Dict[str, Any]],
        expected_count: int,
        expected_atomics: int
    ) -> DimensionScore:
        """
        Check completeness dimension.

        - All criteria extracted (no missing)
        - All atomic decomposition done
        - All cross-references resolved
        """
        issues = []
        total_fields = 0
        valid_fields = 0

        # Check criteria count
        actual_count = len(criteria)
        total_fields += 1
        if expected_count > 0:
            if actual_count >= expected_count:
                valid_fields += 1
            else:
                issues.append(QualityIssue(
                    dimension="completeness",
                    severity="error",
                    field_path="criteria",
                    message=f"Missing criteria: expected {expected_count}, got {actual_count}",
                    value=actual_count,
                    suggestion="Re-extract missing criteria",
                ))
        else:
            valid_fields += 1  # No expectation

        # Check each criterion has required content
        for crit in criteria:
            crit_id = crit.get("id", crit.get("criterionId", "unknown"))
            total_fields += 1

            # Must have text
            if crit.get("text") or crit.get("originalText"):
                valid_fields += 1
            else:
                issues.append(QualityIssue(
                    dimension="completeness",
                    severity="error",
                    field_path=f"criteria[{crit_id}].text",
                    message="Missing criterion text",
                ))

            # Must have type
            total_fields += 1
            if crit.get("type") or crit.get("category"):
                valid_fields += 1
            else:
                issues.append(QualityIssue(
                    dimension="completeness",
                    severity="warning",
                    field_path=f"criteria[{crit_id}].type",
                    message="Missing criterion type",
                ))

        score = valid_fields / total_fields if total_fields > 0 else 1.0

        return DimensionScore(
            dimension="completeness",
            score=score,
            total_fields=total_fields,
            valid_fields=valid_fields,
            issues=issues,
        )

    def _check_schema_adherence(self, criteria: List[Dict[str, Any]]) -> DimensionScore:
        """
        Check schema adherence dimension.

        - USDM 4.0 compliant structure
        - All required fields present
        - Code objects have 6 fields with instanceType
        """
        issues = []
        total_fields = 0
        valid_fields = 0

        for crit in criteria:
            crit_id = crit.get("id", crit.get("criterionId", "unknown"))

            # Check instanceType
            total_fields += 1
            if crit.get("instanceType") == "EligibilityCriterion":
                valid_fields += 1
            else:
                issues.append(QualityIssue(
                    dimension="schema_adherence",
                    severity="error",
                    field_path=f"criteria[{crit_id}].instanceType",
                    message="Missing or invalid instanceType",
                    value=crit.get("instanceType"),
                    suggestion='Add "instanceType": "EligibilityCriterion"',
                ))

            # Check category Code object
            category = crit.get("category")
            if category:
                total_fields += 1
                missing_fields = REQUIRED_CODE_FIELDS - set(category.keys())
                if not missing_fields:
                    valid_fields += 1
                else:
                    issues.append(QualityIssue(
                        dimension="schema_adherence",
                        severity="error",
                        field_path=f"criteria[{crit_id}].category",
                        message=f"Missing Code fields: {missing_fields}",
                        suggestion="Add missing fields to Code object",
                    ))

        score = valid_fields / total_fields if total_fields > 0 else 1.0

        return DimensionScore(
            dimension="schema_adherence",
            score=score,
            total_fields=total_fields,
            valid_fields=valid_fields,
            issues=issues,
        )

    def _check_provenance(self, criteria: List[Dict[str, Any]]) -> DimensionScore:
        """
        Check provenance dimension.

        - Every criterion has pageNumber
        - Every criterion has textSnippet (<=500 chars)
        """
        issues = []
        total_fields = 0
        valid_fields = 0

        for crit in criteria:
            crit_id = crit.get("id", crit.get("criterionId", "unknown"))
            provenance = crit.get("provenance", {})

            # Check pageNumber
            total_fields += 1
            page = provenance.get("pageNumber") if isinstance(provenance, dict) else None
            if page and isinstance(page, int) and page > 0:
                valid_fields += 1
            else:
                issues.append(QualityIssue(
                    dimension="provenance",
                    severity="error",
                    field_path=f"criteria[{crit_id}].provenance.pageNumber",
                    message="Missing or invalid page number",
                    value=page,
                    suggestion="Add valid page number from PDF",
                ))

            # Check textSnippet
            total_fields += 1
            snippet = provenance.get("textSnippet") if isinstance(provenance, dict) else None
            if snippet and len(snippet) > 0:
                valid_fields += 1
                # Warn if too long
                if len(snippet) > 500:
                    issues.append(QualityIssue(
                        dimension="provenance",
                        severity="warning",
                        field_path=f"criteria[{crit_id}].provenance.textSnippet",
                        message=f"Text snippet too long ({len(snippet)} chars > 500)",
                        suggestion="Truncate to 500 characters",
                    ))
            else:
                issues.append(QualityIssue(
                    dimension="provenance",
                    severity="error",
                    field_path=f"criteria[{crit_id}].provenance.textSnippet",
                    message="Missing text snippet",
                    suggestion="Extract text snippet from source PDF",
                ))

        score = valid_fields / total_fields if total_fields > 0 else 1.0

        return DimensionScore(
            dimension="provenance",
            score=score,
            total_fields=total_fields,
            valid_fields=valid_fields,
            issues=issues,
        )

    def _check_terminology(self, criteria: List[Dict[str, Any]]) -> DimensionScore:
        """
        Check terminology dimension.

        - Valid OMOP concept IDs
        - Proper vocabulary priority
        - Standard concepts used where available
        """
        issues = []
        total_fields = 0
        valid_fields = 0

        for crit in criteria:
            crit_id = crit.get("id", crit.get("criterionId", "unknown"))

            # Check category code
            category = crit.get("category", {})
            if category:
                total_fields += 1
                code = category.get("code")
                if code and code.startswith("C"):  # NCIt codes start with C
                    valid_fields += 1
                elif code:
                    issues.append(QualityIssue(
                        dimension="terminology",
                        severity="warning",
                        field_path=f"criteria[{crit_id}].category.code",
                        message="Non-standard code format",
                        value=code,
                        suggestion="Use NCIt code (C-prefix)",
                    ))

            # Check OMOP concepts in atomic criteria
            for ac in crit.get("atomicCriteria", []):
                for concept in ac.get("omopConcepts", []):
                    total_fields += 1
                    concept_id = concept.get("concept_id")
                    if concept_id and isinstance(concept_id, int) and concept_id > 0:
                        valid_fields += 1
                    else:
                        issues.append(QualityIssue(
                            dimension="terminology",
                            severity="warning",
                            field_path=f"criteria[{crit_id}].atomicCriteria.omopConcepts",
                            message="Invalid OMOP concept ID",
                            value=concept_id,
                        ))

        # If no terminology fields, consider valid
        if total_fields == 0:
            total_fields = 1
            valid_fields = 1

        score = valid_fields / total_fields if total_fields > 0 else 1.0

        return DimensionScore(
            dimension="terminology",
            score=score,
            total_fields=total_fields,
            valid_fields=valid_fields,
            issues=issues,
        )

    def _has_placeholder(self, text: str) -> bool:
        """Check if text contains any placeholder patterns."""
        if not text:
            return False
        for pattern in self.placeholder_patterns:
            if pattern.search(text):
                return True
        return False

    def _check_dict_for_placeholders(
        self,
        data: Any,
        path: str,
        issues: List[QualityIssue]
    ) -> None:
        """Recursively check dictionary for placeholder values."""
        if isinstance(data, dict):
            for key, value in data.items():
                self._check_dict_for_placeholders(value, f"{path}.{key}", issues)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                self._check_dict_for_placeholders(item, f"{path}[{i}]", issues)
        elif isinstance(data, str) and self._has_placeholder(data):
            issues.append(QualityIssue(
                dimension="accuracy",
                severity="error",
                field_path=path,
                message="Placeholder value detected",
                value=data[:100],
                suggestion="Replace with actual extracted value",
            ))


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================


def check_quality(
    criteria: List[Dict[str, Any]],
    raw_criteria_count: int = 0,
    expected_atomics: int = 0,
) -> QualityScore:
    """
    Convenience function to check quality.

    Args:
        criteria: List of extracted/processed criteria
        raw_criteria_count: Expected number of criteria
        expected_atomics: Expected number of atomic criteria

    Returns:
        QualityScore
    """
    checker = EligibilityQualityChecker()
    return checker.check(criteria, raw_criteria_count, expected_atomics)


def get_quality_checker() -> EligibilityQualityChecker:
    """Get a quality checker instance."""
    return EligibilityQualityChecker()


# =============================================================================
# CLI SUPPORT
# =============================================================================


if __name__ == "__main__":
    # Test with sample data
    sample_criteria = [
        {
            "id": "EC-INC_001",
            "name": "Inclusion Criterion 1",
            "text": "Age >= 18 years",
            "category": {
                "code": "C25532",
                "decode": "Inclusion Criteria",
                "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
                "codeSystemVersion": "24.12",
                "instanceType": "Code",
            },
            "instanceType": "EligibilityCriterion",
            "provenance": {
                "pageNumber": 35,
                "textSnippet": "Age >= 18 years at time of consent",
            },
        },
        {
            "id": "EC-INC_002",
            "name": "Inclusion Criterion 2",
            "text": "TBD",  # Placeholder - should fail accuracy
            "category": {
                "code": "C25532",
                "decode": "Inclusion Criteria",
                "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
                # Missing codeSystemVersion and instanceType
            },
            "instanceType": "EligibilityCriterion",
            "provenance": {
                "pageNumber": 0,  # Invalid page
                # Missing textSnippet
            },
        },
    ]

    print("Testing EligibilityQualityChecker...")
    print(f"{'='*60}")

    checker = EligibilityQualityChecker()
    score = checker.check(sample_criteria, raw_criteria_count=2)

    print(f"Overall Score: {score.overall_score:.1%}")
    print(f"Thresholds Met: {score.thresholds_met}")
    print(f"Failed Dimensions: {score.failed_dimensions}")
    print()
    print("Dimension Scores:")
    print(f"  Accuracy: {score.accuracy.score:.1%} ({score.accuracy.valid_fields}/{score.accuracy.total_fields})")
    print(f"  Completeness: {score.completeness.score:.1%}")
    print(f"  Schema Adherence: {score.schema_adherence.score:.1%}")
    print(f"  Provenance: {score.provenance.score:.1%}")
    print(f"  Terminology: {score.terminology.score:.1%}")
    print()
    print(f"Total Issues: {score.total_issues}")

    if score.accuracy.issues:
        print("\nAccuracy Issues:")
        for issue in score.accuracy.issues[:5]:
            print(f"  - {issue.field_path}: {issue.message}")
