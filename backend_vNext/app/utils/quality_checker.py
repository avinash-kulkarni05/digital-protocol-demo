"""
Quality check framework for extraction outputs.

Evaluates extraction results against five dimensions:
- Accuracy: Values match expected patterns, no hallucinations
- Completeness: All required fields present
- USDM Adherence: Valid against USDM 4.0 JSON Schema
- Provenance: Every value has source citation
- Terminology: CDISC CT / NCI Thesaurus code validation

Provides detailed issue reports for feedback-based retry.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from app.config import settings
from app.utils.schema_validator import SchemaValidator
from app.utils.provenance_compliance import ProvenanceCompliance
from app.utils.cdisc_validator import CDISCTerminologyValidator

logger = logging.getLogger(__name__)


@dataclass
class QualityScore:
    """Quality assessment scores for extraction output."""

    accuracy: float  # 0.0 to 1.0
    completeness: float
    usdm_adherence: float  # JSON Schema validation against USDM 4.0
    provenance: float
    terminology: float = 1.0  # CDISC CT compliance

    # Detailed issues for feedback
    accuracy_issues: List[Dict[str, Any]] = field(default_factory=list)
    completeness_issues: List[Dict[str, Any]] = field(default_factory=list)
    usdm_adherence_issues: List[Dict[str, Any]] = field(default_factory=list)
    provenance_issues: List[Dict[str, Any]] = field(default_factory=list)
    terminology_issues: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def overall_score(self) -> float:
        """Weighted average of all dimensions."""
        weights = {
            "accuracy": 0.25,
            "completeness": 0.20,
            "usdm_adherence": 0.20,
            "provenance": 0.20,
            "terminology": 0.15,
        }
        return (
            self.accuracy * weights["accuracy"]
            + self.completeness * weights["completeness"]
            + self.usdm_adherence * weights["usdm_adherence"]
            + self.provenance * weights["provenance"]
            + self.terminology * weights["terminology"]
        )

    def passes_thresholds(self, thresholds: Dict[str, float]) -> bool:
        """Check if all dimensions meet thresholds."""
        return (
            self.accuracy >= thresholds.get("accuracy", 0.95)
            and self.completeness >= thresholds.get("completeness", 0.90)
            and self.usdm_adherence >= thresholds.get("usdm_adherence", 1.0)
            and self.provenance >= thresholds.get("provenance", 0.95)
            and self.terminology >= thresholds.get("terminology", 0.90)
        )

    def get_failed_dimensions(self, thresholds: Dict[str, float]) -> List[str]:
        """Return list of dimensions that failed thresholds."""
        failed = []
        if self.accuracy < thresholds.get("accuracy", 0.95):
            failed.append("accuracy")
        if self.completeness < thresholds.get("completeness", 0.90):
            failed.append("completeness")
        if self.usdm_adherence < thresholds.get("usdm_adherence", 1.0):
            failed.append("usdm_adherence")
        if self.provenance < thresholds.get("provenance", 0.95):
            failed.append("provenance")
        if self.terminology < thresholds.get("terminology", 0.90):
            failed.append("terminology")
        return failed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "accuracy": self.accuracy,
            "completeness": self.completeness,
            "usdm_adherence": self.usdm_adherence,
            "provenance": self.provenance,
            "terminology": self.terminology,
            "overall_score": self.overall_score,
            "accuracy_issues_count": len(self.accuracy_issues),
            "completeness_issues_count": len(self.completeness_issues),
            "usdm_adherence_issues_count": len(self.usdm_adherence_issues),
            "provenance_issues_count": len(self.provenance_issues),
            "terminology_issues_count": len(self.terminology_issues),
        }

    def __str__(self) -> str:
        """String representation for logging."""
        return (
            f"QualityScore(accuracy={self.accuracy:.1%}, "
            f"completeness={self.completeness:.1%}, "
            f"usdm_adherence={self.usdm_adherence:.1%}, "
            f"provenance={self.provenance:.1%}, "
            f"terminology={self.terminology:.1%}, "
            f"overall={self.overall_score:.1%})"
        )


class QualityChecker:
    """
    Generic quality check framework for extraction outputs.

    Evaluates data against all quality dimensions and returns
    detailed issue reports for targeted retry.
    """

    # Maximum snippet length (schema allows 500 chars)
    MAX_SNIPPET_LENGTH = 500

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

    def __init__(self):
        """Initialize with validators."""
        self.schema_validator = SchemaValidator()
        self.provenance_compliance = ProvenanceCompliance()
        self.terminology_validator = CDISCTerminologyValidator()

    def post_process(self, data: Dict[str, Any], module_id: str) -> Dict[str, Any]:
        """
        Post-process extraction data to fix common issues before validation.

        Performs:
        1. Truncate long text_snippets to schema max length (500 chars)
        2. Auto-correct CDISC codes based on decode values
        3. Ensure codeSystem and codeSystemVersion are present for all Code objects

        Args:
            data: Extracted data to post-process
            module_id: Module ID for context

        Returns:
            Post-processed data with auto-corrections applied
        """
        import copy
        data = copy.deepcopy(data)

        # 1. Truncate long snippets
        self._truncate_snippets(data)

        # 2. Auto-correct CDISC codes based on decode
        self._auto_correct_terminology(data, module_id)

        return data

    def _truncate_snippets(self, data: Any, path: str = "$") -> None:
        """
        Recursively truncate text_snippet fields to schema max length.

        Truncates at sentence boundary if possible, otherwise at word boundary.
        """
        if isinstance(data, dict):
            for key, value in data.items():
                if key == "text_snippet" and isinstance(value, str):
                    if len(value) > self.MAX_SNIPPET_LENGTH:
                        # Try to truncate at sentence boundary
                        truncated = value[:self.MAX_SNIPPET_LENGTH]
                        last_period = truncated.rfind('. ')
                        last_newline = truncated.rfind('\\n')
                        break_point = max(last_period, last_newline)

                        if break_point > self.MAX_SNIPPET_LENGTH * 0.6:
                            # Good sentence break found
                            data[key] = truncated[:break_point + 1].strip()
                        else:
                            # Truncate at word boundary
                            last_space = truncated.rfind(' ')
                            if last_space > self.MAX_SNIPPET_LENGTH * 0.8:
                                data[key] = truncated[:last_space].strip()
                            else:
                                data[key] = truncated.strip()

                        logger.debug(f"Truncated snippet at {path}.{key}: {len(value)} -> {len(data[key])} chars")
                elif isinstance(value, (dict, list)):
                    self._truncate_snippets(value, f"{path}.{key}")

        elif isinstance(data, list):
            for i, item in enumerate(data):
                self._truncate_snippets(item, f"{path}[{i}]")

    def _auto_correct_terminology(self, data: Any, module_id: str, path: str = "$") -> None:
        """
        Auto-correct CDISC codes based on decode values.

        If a decode is valid but the code is wrong, replace with correct code.
        Also ensures codeSystem and codeSystemVersion are present for Code objects.
        This handles common LLM errors like using wrong NCI codes or missing fields.
        """
        # CDISC Code System constants
        CDISC_CODE_SYSTEM = "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl"
        CDISC_CODE_SYSTEM_VERSION = "24.03e"

        if isinstance(data, dict):
            # Check if this dict has code/decode pair (is a Code object)
            if "code" in data and "decode" in data:
                code = data.get("code")
                decode = data.get("decode")

                if code and decode:
                    # Infer domain from path
                    domain = self._infer_domain_from_path(path)
                    if domain:
                        # Check if code matches decode
                        is_valid, error = self.terminology_validator.validate_code_decode_pair(
                            code, decode, domain
                        )
                        if not is_valid:
                            # Try to find correct code for this decode
                            correct_code = self.terminology_validator.get_code_for_decode(decode, domain)
                            if correct_code and correct_code != code:
                                logger.info(
                                    f"Auto-correcting code at {path}: "
                                    f"'{code}' -> '{correct_code}' for decode '{decode}'"
                                )
                                data["code"] = correct_code

                    # Ensure codeSystem and codeSystemVersion are present for Code objects
                    # This is required by schema for studyPhase, studyType, etc.
                    if "codeSystem" not in data or not data["codeSystem"]:
                        data["codeSystem"] = CDISC_CODE_SYSTEM
                        logger.debug(f"Added missing codeSystem at {path}")

                    if "codeSystemVersion" not in data or not data["codeSystemVersion"]:
                        data["codeSystemVersion"] = CDISC_CODE_SYSTEM_VERSION
                        logger.debug(f"Added missing codeSystemVersion at {path}")

            # Recurse into nested structures
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    self._auto_correct_terminology(value, module_id, f"{path}.{key}")

        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, (dict, list)):
                    self._auto_correct_terminology(item, module_id, f"{path}[{i}]")

    def _infer_domain_from_path(self, path: str) -> str | None:
        """Infer CDISC domain from JSON path."""
        path_lower = path.lower()

        if "studyphase" in path_lower:
            return "study_phase"
        if "studytype" in path_lower:
            return "study_type"
        if "sex" in path_lower:
            return "sex"
        if "blinding" in path_lower:
            return "blinding"
        if "armtype" in path_lower or ".arms[" in path_lower:
            return "arm_types"
        if "endpointtype" in path_lower:
            return "endpoint_type"
        if "route" in path_lower:
            return "route_of_administration"
        if "epoch" in path_lower:
            return "epoch_types"
        # Analysis population type (e.g., FAS, ITT, Safety, PK)
        if "population_type" in path_lower or "populationtype" in path_lower:
            return "population_type"
        # Endpoint and objective level codes
        # IMPORTANT: Check "objective" before "endpoint" because
        # paths like "protocol_endpoints.objectives" contain both strings
        if ".level" in path_lower:
            if "objective" in path_lower:
                return "objective_level"
            if "endpoint" in path_lower:
                return "endpoint_level"
        # Outcome type for endpoints (Time-to-Event, Binary, etc.)
        if "outcome_type" in path_lower or "outcometype" in path_lower:
            return "outcome_type"
        # ICE strategy for estimands
        if "strategy" in path_lower and "intercurrent" in path_lower:
            return "ice_strategy"
        # Summary measure for estimands
        if "summary_measure" in path_lower or "summarymeasure" in path_lower:
            return "summary_measure"

        return None

    def evaluate(
        self,
        data: Dict[str, Any],
        module_id: str,
        pass_type: str = "combined",  # "pass1", "pass2", or "combined"
    ) -> QualityScore:
        """
        Evaluate extraction output against all quality dimensions.

        Args:
            data: Extracted data to evaluate
            module_id: Module ID for schema lookup
            pass_type: Which pass output this is

        Returns:
            QualityScore with all dimension scores and issues
        """
        logger.debug(f"Evaluating quality for {module_id} ({pass_type})")

        # 1. Accuracy check
        accuracy, accuracy_issues = self._check_accuracy(data, module_id)

        # 2. Completeness check
        completeness, completeness_issues = self._check_completeness(data, module_id)

        # 3. USDM Adherence check (JSON Schema validation)
        usdm_adherence, usdm_adherence_issues = self._check_usdm_adherence(data, module_id)

        # 4. Provenance check
        provenance, provenance_issues = self._check_provenance(data, module_id)

        # 5. Terminology check (CDISC CT / NCI Thesaurus)
        terminology, terminology_issues = self._check_terminology_compliance(data, module_id)

        score = QualityScore(
            accuracy=accuracy,
            completeness=completeness,
            usdm_adherence=usdm_adherence,
            provenance=provenance,
            terminology=terminology,
            accuracy_issues=accuracy_issues,
            completeness_issues=completeness_issues,
            usdm_adherence_issues=usdm_adherence_issues,
            provenance_issues=provenance_issues,
            terminology_issues=terminology_issues,
        )

        logger.info(f"Quality evaluation for {module_id}: {score}")
        return score

    def evaluate_pass1(
        self,
        data: Dict[str, Any],
        module_id: str,
    ) -> QualityScore:
        """
        Evaluate Pass 1 output (values only, no provenance check).

        For Pass 1, we check accuracy, completeness, and compliance.
        Provenance and terminology are checked in Pass 2.
        """
        logger.debug(f"Evaluating Pass 1 quality for {module_id}")

        # 1. Accuracy check
        accuracy, accuracy_issues = self._check_accuracy(data, module_id)

        # 2. Completeness check
        completeness, completeness_issues = self._check_completeness(data, module_id)

        # 3. USDM Adherence check (JSON Schema) - catch schema violations early
        usdm_adherence, usdm_adherence_issues = self._check_usdm_adherence(data, module_id)

        return QualityScore(
            accuracy=accuracy,
            completeness=completeness,
            usdm_adherence=usdm_adherence,  # Now checked in Pass 1
            provenance=1.0,  # Not checked in Pass 1
            accuracy_issues=accuracy_issues,
            completeness_issues=completeness_issues,
            usdm_adherence_issues=usdm_adherence_issues,
            provenance_issues=[],
        )

    def _check_accuracy(
        self, data: Dict[str, Any], module_id: str
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Check accuracy: values match expected patterns, no obvious hallucinations.

        Checks:
        - Date formats (YYYY-MM-DD)
        - Numeric ranges (page numbers > 0, percentages 0-100)
        - Required enums match allowed values
        - No placeholder text ("TBD", "TODO", "PLACEHOLDER")
        - No empty strings for required fields
        """
        issues = []
        total_checks = 0
        passed_checks = 0

        def traverse(obj: Any, path: str = "$"):
            nonlocal total_checks, passed_checks, issues

            if isinstance(obj, dict):
                for key, value in obj.items():
                    field_path = f"{path}.{key}"

                    # Check date format
                    if "date" in key.lower() and isinstance(value, str) and value:
                        total_checks += 1
                        # Accept YYYY-MM-DD or partial dates
                        if re.match(r"^\d{4}(-\d{2}(-\d{2})?)?$", value):
                            passed_checks += 1
                        else:
                            issues.append({
                                "path": field_path,
                                "issue": "invalid_date_format",
                                "value": value,
                                "expected": "YYYY-MM-DD format",
                            })

                    # Check page numbers
                    if key == "page_number":
                        total_checks += 1
                        if isinstance(value, int) and value >= 1:
                            passed_checks += 1
                        elif value is None:
                            # Null page numbers are sometimes valid
                            passed_checks += 1
                        else:
                            issues.append({
                                "path": field_path,
                                "issue": "invalid_page_number",
                                "value": value,
                                "expected": "positive integer",
                            })

                    # Check for placeholder text
                    if isinstance(value, str) and value:
                        total_checks += 1
                        value_upper = value.upper()
                        has_placeholder = any(
                            p in value_upper for p in self.PLACEHOLDER_PATTERNS
                        )
                        if not has_placeholder:
                            passed_checks += 1
                        else:
                            issues.append({
                                "path": field_path,
                                "issue": "placeholder_text",
                                "value": value[:100],
                            })

                    # Check for suspiciously short snippets in provenance
                    if key == "text_snippet" and isinstance(value, str):
                        total_checks += 1
                        if len(value.strip()) >= 15:  # Aligned with provenance_compliance.py
                            passed_checks += 1
                        else:
                            issues.append({
                                "path": field_path,
                                "issue": "snippet_too_short",
                                "value": value,
                                "expected": "at least 15 characters",
                            })

                    # Recurse into nested structures
                    if isinstance(value, (dict, list)):
                        traverse(value, field_path)

            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    traverse(item, f"{path}[{i}]")

        traverse(data)
        accuracy = passed_checks / total_checks if total_checks > 0 else 1.0
        return accuracy, issues

    def _check_completeness(
        self, data: Dict[str, Any], module_id: str
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Check completeness: all required fields present.

        Uses JSON Schema 'required' arrays to identify mandatory fields.
        """
        try:
            schema = self.schema_validator.load_schema(module_id)
        except Exception as e:
            logger.warning(f"Could not load schema for {module_id}: {e}")
            return 1.0, []

        required_fields = schema.get("required", [])

        if not required_fields:
            return 1.0, []

        issues = []
        present = 0

        for field_name in required_fields:
            value = data.get(field_name)
            if value is not None and value != "" and value != []:
                present += 1
            else:
                issues.append({
                    "field": field_name,
                    "issue": "missing_required_field",
                })

        completeness = present / len(required_fields)
        return completeness, issues

    def _check_usdm_adherence(
        self, data: Dict[str, Any], module_id: str
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Check USDM adherence: validates against USDM 4.0 JSON Schema.

        Returns 1.0 if valid, proportional score if partially valid.
        """
        try:
            is_valid, errors = self.schema_validator.validate(data, module_id)
        except Exception as e:
            logger.warning(f"Schema validation failed for {module_id}: {e}")
            return 0.0, [{"error": str(e)}]

        if is_valid:
            return 1.0, []

        # Calculate adherence based on error severity
        # Each error reduces adherence proportionally
        error_count = len(errors)
        if error_count == 0:
            return 1.0, []

        # Cap adherence reduction at 10 errors
        usdm_adherence = max(0.0, 1.0 - (min(error_count, 10) * 0.1))
        return usdm_adherence, errors

    def _check_provenance(
        self, data: Dict[str, Any], module_id: str
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Check provenance: every extracted value has source citation.
        """
        try:
            coverage, missing = self.provenance_compliance.calculate_coverage(data)
        except Exception as e:
            logger.warning(f"Provenance check failed for {module_id}: {e}")
            return 0.0, [{"error": str(e)}]

        return coverage, missing

    def _check_terminology_compliance(
        self, data: Dict[str, Any], module_id: str
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Check terminology compliance: CDISC CT / NCI Thesaurus codes are valid.

        Uses recursive traversal to find and validate all code/decode pairs:
        - studyPhase, studyType, trialPhase, trialType
        - sex codes in studyPopulation
        - blinding, interventionModel, interventionType
        - arm types, endpoint levels, objective levels
        - population types, epoch types, routes
        - ICE strategies, summary measures (estimands)
        """
        try:
            issues = self.terminology_validator.validate_extraction_data(data)
            stats = self.terminology_validator.get_validation_stats(data)
        except Exception as e:
            logger.error(f"Terminology check failed for {module_id}: {e}")
            return 0.0, [{"error": str(e), "issue": "terminology_validation_failed"}]

        # Calculate score based on actual coded fields found
        if not issues:
            return 1.0, []

        # Use actual count of coded fields for accurate scoring
        total_coded_fields = stats.get("total_coded_fields", 1)
        recognized_fields = stats.get("recognized_fields", total_coded_fields)

        # Only count issues against recognized fields (those we can validate)
        if recognized_fields == 0:
            return 1.0, issues  # No fields to validate

        score = max(0.0, 1.0 - (len(issues) / recognized_fields))

        # Log validation stats for debugging
        logger.debug(
            f"Terminology check for {module_id}: "
            f"{len(issues)} issues in {recognized_fields} recognized fields "
            f"({stats.get('coverage_percentage', 0):.1f}% coverage)"
        )

        return score, issues

    def generate_feedback_prompt(
        self,
        quality: QualityScore,
        thresholds: Dict[str, float],
        max_issues: int = 10,
    ) -> str:
        """
        Generate feedback text for LLM retry prompt.

        Args:
            quality: Quality score with issues
            thresholds: Quality thresholds
            max_issues: Maximum issues to include per dimension

        Returns:
            Formatted feedback text for prompt injection
        """
        failed = quality.get_failed_dimensions(thresholds)

        if not failed:
            return ""

        lines = [
            "\n\n## QUALITY FEEDBACK - CORRECTIONS REQUIRED",
            "Your previous extraction had the following issues that MUST be fixed:\n",
        ]

        # Accuracy issues
        if "accuracy" in failed and quality.accuracy_issues:
            lines.append("### Accuracy Issues:")
            for issue in quality.accuracy_issues[:max_issues]:
                path = issue.get("path", "unknown")
                issue_type = issue.get("issue", "unknown")
                value = issue.get("value", "N/A")
                if isinstance(value, str) and len(value) > 50:
                    value = value[:50] + "..."
                lines.append(f"- `{path}`: {issue_type} (value: {value})")
            lines.append("")

        # Completeness issues
        if "completeness" in failed and quality.completeness_issues:
            lines.append("### Missing Required Fields:")
            for issue in quality.completeness_issues[:max_issues]:
                field_name = issue.get("field", "unknown")
                lines.append(f"- `{field_name}`: REQUIRED but not provided")
            lines.append("")

        # USDM Adherence issues
        if "usdm_adherence" in failed and quality.usdm_adherence_issues:
            lines.append("### Schema Adherence Errors:")
            for issue in quality.usdm_adherence_issues[:max_issues]:
                path = issue.get("path", "unknown")
                message = issue.get("message", "unknown error")
                lines.append(f"- `{path}`: {message}")
            lines.append("")

        # Provenance issues
        if "provenance" in failed and quality.provenance_issues:
            lines.append("### Fields Missing Provenance:")
            for issue in quality.provenance_issues[:max_issues]:
                path = issue.get("path", "unknown")
                value = issue.get("value", "N/A")
                if isinstance(value, str) and len(value) > 50:
                    value = value[:50] + "..."
                lines.append(f"- `{path}`: value={value}")
            lines.append("")

        # Terminology issues
        if "terminology" in failed and quality.terminology_issues:
            lines.append("### CDISC Terminology Issues:")
            for issue in quality.terminology_issues[:max_issues]:
                path = issue.get("path", "unknown")
                issue_type = issue.get("issue", "unknown")
                error = issue.get("error", "")
                lines.append(f"- `{path}`: {issue_type} - {error}")
            lines.append("")

        lines.append("### CORRECTIONS REQUIRED:")
        lines.append("1. Fix ALL issues listed above")
        lines.append("2. Ensure all required fields have values")
        lines.append("3. Add provenance (page_number, text_snippet) for every field")
        lines.append("4. Ensure text_snippet is an EXACT quote from the PDF (10-500 chars)")
        lines.append("5. Use valid CDISC CT codes (e.g., C49686 for Phase 3, C98388 for Interventional)")

        return "\n".join(lines)

    def generate_pass1_feedback(
        self,
        quality: QualityScore,
        previous_result: Dict[str, Any],
        max_issues: int = 5,
    ) -> str:
        """
        Generate feedback for Pass 1 retry.

        Includes accuracy, completeness, and compliance feedback.
        """
        lines = [
            "\n\n## QUALITY FEEDBACK - CORRECTIONS REQUIRED",
            "Your previous extraction had the following issues that MUST be fixed:\n",
        ]

        # Accuracy issues
        if quality.accuracy_issues:
            lines.append("### Accuracy Issues:")
            for issue in quality.accuracy_issues[:max_issues]:
                path = issue.get("path", "unknown")
                issue_type = issue.get("issue", "unknown")
                value = issue.get("value", "N/A")
                lines.append(f"- `{path}`: {issue_type} (value: {value})")
            lines.append("")

        # Completeness issues
        if quality.completeness_issues:
            lines.append("### Missing Required Fields:")
            for issue in quality.completeness_issues[:max_issues]:
                field_name = issue.get("field", "unknown")
                lines.append(f"- `{field_name}`: REQUIRED but not provided")
            lines.append("")

        # USDM Adherence issues (now checked in Pass 1)
        if quality.usdm_adherence_issues:
            lines.append("### Schema Adherence Errors:")
            for issue in quality.usdm_adherence_issues[:max_issues]:
                path = issue.get("path", "unknown")
                message = issue.get("message", "unknown error")
                lines.append(f"- `{path}`: {message}")
            lines.append("")

        # Include truncated previous output
        lines.append("### PREVIOUS OUTPUT (DO NOT REPEAT THESE ERRORS):")
        lines.append("```json")
        prev_json = json.dumps(previous_result, indent=2)
        if len(prev_json) > 2000:
            prev_json = prev_json[:2000] + "\n... (truncated)"
        lines.append(prev_json)
        lines.append("```")
        lines.append("")
        lines.append("Provide a CORRECTED extraction addressing ALL issues above.")

        return "\n".join(lines)

    def generate_pass2_feedback(
        self,
        quality: QualityScore,
        max_issues: int = 10,
    ) -> str:
        """
        Generate feedback for Pass 2 (provenance) retry.

        Focuses on provenance and compliance issues.
        """
        # Handle None quality (e.g., when previous attempt failed to parse JSON)
        if quality is None:
            return (
                "\n\n## QUALITY FEEDBACK - RETRY REQUIRED\n"
                "The previous extraction attempt failed to produce valid JSON.\n"
                "Please ensure your response is a complete, valid JSON object.\n"
                "Do not include any text before or after the JSON.\n"
            )

        lines = [
            "\n\n## QUALITY FEEDBACK - PROVENANCE CORRECTIONS REQUIRED",
            "Your previous provenance extraction had the following issues:\n",
        ]

        # Provenance issues
        if quality.provenance_issues:
            lines.append("### Fields Missing Provenance:")
            for issue in quality.provenance_issues[:max_issues]:
                path = issue.get("path", "unknown")
                value = issue.get("value", "N/A")
                if isinstance(value, str) and len(value) > 50:
                    value = value[:50] + "..."
                lines.append(f"- `{path}`: value={value}")
            lines.append("")

        # USDM Adherence issues
        if quality.usdm_adherence_issues:
            lines.append("### Schema Adherence Errors:")
            for issue in quality.usdm_adherence_issues[:max_issues]:
                path = issue.get("path", "unknown")
                message = issue.get("message", "unknown error")
                lines.append(f"- `{path}`: {message}")
            lines.append("")

        lines.append("### CORRECTIONS REQUIRED:")
        lines.append("1. Add provenance with page_number and text_snippet for EVERY field listed above")
        lines.append("2. Ensure text_snippet is an EXACT quote from the PDF (10-500 chars)")
        lines.append("3. Fix all schema compliance errors")
        lines.append("4. page_number must be a positive integer")

        return "\n".join(lines)
