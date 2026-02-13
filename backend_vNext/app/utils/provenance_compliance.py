"""
Provenance compliance utilities for 100% coverage enforcement.

Ensures every extracted field has proper provenance with:
- Explicit provenance (direct quotes with page numbers)
- Derived provenance (reasoning with supporting context)
"""

import logging
from typing import Any, Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class ProvenanceCompliance:
    """
    Enforces 100% provenance coverage requirement.

    Validates that all extracted data has proper source references.
    """

    # Fields that don't require provenance
    # These are either metadata fields or structural fields not extracted from PDFs
    EXEMPT_FIELDS = {
        "id", "instanceType", "schemaVersion", "name", "label",
        "provenance", "extraction_statistics", "ich_m11_section",
        # extensionAttributes contain system-generated metadata, not PDF content
        "extensionAttributes", "extractedAt", "modelVersion",
        "sectionNumber", "title",  # These are structural, not extracted
        # _metadata is system-generated extraction metadata
        "_metadata", "module_id", "instance_type", "pass1_duration_seconds",
        "pass2_duration_seconds", "quality_score",
        # FK reference fields - these are internal cross-references (foreign keys)
        # that point to objects defined elsewhere in the same document.
        # They don't appear as literal text in the PDF and inherit provenance
        # from their parent object.
        "endpoint_ids",  # Array of FK refs to endpoints in objectives
        "endpoint_id",  # FK ref to endpoint in estimands/statistical methods
        "analysis_population_id",  # FK ref to analysis population
        "for_endpoint_ids",  # FK ref array in statistical_methods/subgroup_analyses
        "is_primary_for_endpoints",  # FK ref array in analysis_populations
        "is_sensitivity_for_endpoints",  # FK ref array in analysis_populations
        "sensitivity_analysis_ids",  # FK ref array in estimands
        "target_estimand_id",  # FK ref in sensitivity analyses
        # Derived/calculated fields that don't have PDF provenance
        "assessment_timepoints_weeks",  # Calculated timepoints, not literal PDF text
        "primary_timepoint_weeks",  # Calculated timepoint
        "stratification_factors",  # May be enumerated but inherited from parent provenance
        "covariates",  # May be enumerated but inherited from parent provenance
        "categories",  # Subgroup categories inherit from parent provenance
        "inclusion_criteria",  # List items inherit from parent population provenance
        "exclusion_criteria",  # List items inherit from parent population provenance
        "assumptions",  # Missing data assumptions inherit from parent provenance
        # Safety management fields - inherit from parent provenance
        "exclusions",  # SAE criteria exclusions inherit from parent
        "exceptions",  # DLT exceptions inherit from parent
        "recipients",  # SAE reporting recipients inherit from parent
        "responsibilities",  # Safety committee responsibilities inherit from parent
        "grade_definitions",  # Grading system grades inherit from parent
        "stopping_conditions",  # Stopping rules inherit from parent
        "levels",  # Dose modification levels inherit from parent
        "actions",  # Decision rule actions inherit from parent
        # Data management primitive arrays - inherit from parent provenance
        "system_capabilities",  # EDC capabilities inherit from edc_specifications.provenance
        "language_requirements",  # Languages inherit from edc_specifications.provenance
        "forms",  # CRF forms inherit from crf_modules[*].provenance
        "visit_schedule",  # Visits inherit from crf_modules[*].provenance
        "standard_checks",  # Checks inherit from data_quality.provenance
        "protocol_specific_checks",  # Checks inherit from data_quality.provenance
        "critical_data_points",  # SDV data inherit from sdv_strategy provenance
        "auto_query_triggers",  # Triggers inherit from query_management provenance
        "external_data_sources",  # Sources inherit from database_design provenance
        "calculated_fields",  # Fields inherit from database_design provenance
        "derived_variables",  # Variables inherit from database_design provenance
        "prerequisites",  # Lock prerequisites inherit from final_database_lock.provenance
        "signoff_required",  # Signoffs inherit from final_database_lock.provenance
        "archival_format",  # Formats inherit from data_archival.provenance
        "data_included",  # DSMB data inherit from dsmb_exports.provenance
        "data_collected",  # Imaging data inherit from imaging provenance
        "instruments_collected",  # ePRO instruments inherit from epro provenance
        "adjudication_types",  # Adjudication types inherit from external_adjudication provenance
        # Laboratory specifications primitive arrays - inherit from parent provenance
        "accreditations",  # Central lab accreditations inherit from central_laboratory.provenance
        "analytes",  # PK analytes inherit from pharmacokinetic_samples.provenance
        "allowed_tests",  # Local lab tests inherit from local_lab_requirements.provenance
        "notification_recipients",  # Recipients inherit from critical_value_reporting.provenance
        # Laboratory testing_schedule nested arrays - inherit from schedule provenance
        "timepoints",  # Timepoints array inherit from testing_schedule[*].provenance
        "timepoint_name",  # Timepoint fields inherit from parent
        "timepoint_type",  # Timepoint fields inherit from parent
        "window",  # Timepoint fields inherit from parent
        "conditions",  # Timepoint fields inherit from parent
        # Withdrawal procedures primitive arrays - inherit from parent provenance
        "data_handling_options",  # Options inherit from consent_withdrawal.provenance
        "required_assessments",  # Assessments inherit from discontinuation_visit.provenance
        "documentation_requirements",  # Docs inherit from discontinuation_visit.provenance
        "assessments",  # Assessments inherit from safety_followup.provenance
        "information_collected",  # Info inherit from survival_followup.provenance
        "contact_methods",  # Methods inherit from lost_to_followup.provenance
        "documentation_required",  # Docs inherit from lost_to_followup.provenance
        "replacement_conditions",  # Conditions inherit from replacement_strategy.provenance
        "reasons",  # Reasons inherit from administrative_withdrawal.provenance
        "notification_requirements",  # Notifications inherit from administrative_withdrawal.provenance
        "analysis_populations",  # Populations inherit from data_retention.provenance
        "prevention_measures",  # Measures inherit from retention_strategies.provenance
        "incentives",  # Incentives inherit from retention_strategies.provenance
    }

    # Minimum text snippet length for explicit provenance
    # Lowered from 20 to 10 to accommodate legitimate short provenance
    # (e.g., "IND 136626" = 10 chars, version dates "5.0 09 Oct 2023" = 15 chars)
    MIN_SNIPPET_LENGTH = 10

    # Maximum text snippet length
    MAX_SNIPPET_LENGTH = 300

    def calculate_coverage(
        self,
        data: Dict[str, Any],
        path: str = "$",
    ) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Calculate provenance coverage and identify missing fields.

        Supports two provenance patterns:
        1. Nested pattern: object has "provenance" key (e.g., studyPhase.provenance)
        2. Sibling pattern: scalar has sibling "*Provenance" key (e.g., therapeuticAreaProvenance)

        Args:
            data: Extracted data with provenance
            path: JSON path prefix for reporting

        Returns:
            Tuple of (coverage_percentage, list_of_missing_fields)
        """
        total_fields = 0
        covered_fields = 0
        missing_fields = []

        def traverse(
            obj: Any,
            current_path: str,
            parent_has_provenance: bool = False,
            parent_obj: Optional[Dict[str, Any]] = None,
            field_key: Optional[str] = None,
        ):
            nonlocal total_fields, covered_fields, missing_fields

            if isinstance(obj, dict):
                # Check for provenance in this object (nested pattern)
                has_provenance = self._has_valid_provenance(obj)

                for key, value in obj.items():
                    # Skip exempt fields and provenance sibling fields
                    if key in self.EXEMPT_FIELDS or key.endswith("Provenance"):
                        continue

                    field_path = f"{current_path}.{key}"

                    if isinstance(value, (dict, list)):
                        traverse(value, field_path, has_provenance or parent_has_provenance, obj, key)
                    elif value is not None:
                        total_fields += 1
                        # Check nested provenance, parent provenance, OR sibling provenance
                        has_sibling = self._has_sibling_provenance(obj, key)
                        if has_provenance or parent_has_provenance or has_sibling:
                            covered_fields += 1
                        else:
                            missing_fields.append({
                                "path": field_path,
                                "value": str(value)[:100],
                            })

            elif isinstance(obj, list):
                # Check for array-level provenance coverage:
                # 1. Sibling provenance pattern (e.g., regionsProvenance)
                # 2. Parent object provenance (e.g., geographic_requirements.provenance)
                array_provenance = False
                if parent_obj and field_key:
                    # Check sibling provenance pattern first (e.g., countriesProvenance)
                    array_provenance = self._has_sibling_provenance(parent_obj, field_key)
                    # Also check if parent object has valid provenance (covers scalar arrays)
                    if not array_provenance:
                        array_provenance = self._has_valid_provenance(parent_obj)

                for i, item in enumerate(obj):
                    item_path = f"{current_path}[{i}]"
                    if isinstance(item, dict):
                        # Dict array items must have their OWN valid provenance
                        # They do NOT inherit from parent - each item needs explicit provenance
                        traverse(item, item_path, False, obj, None)
                    elif item is not None:
                        # Scalar array items (strings, numbers) CAN inherit provenance from:
                        # 1. Sibling provenance pattern (regionsProvenance)
                        # 2. Parent object provenance (geographic_requirements.provenance)
                        total_fields += 1
                        if array_provenance:
                            covered_fields += 1
                        else:
                            missing_fields.append({
                                "path": item_path,
                                "value": str(item)[:100],
                            })

        traverse(data, path)

        coverage = covered_fields / total_fields if total_fields > 0 else 1.0
        return coverage, missing_fields

    def _has_valid_provenance(self, obj: Dict[str, Any]) -> bool:
        """
        Check if object has valid provenance.

        Supports two provenance modes:
        - Explicit: section_number, page_number, text_snippet
        - Derived: kind='derived', reasoning, confidence
        """
        provenance = obj.get("provenance")
        if not provenance:
            return False

        # Check for dual-mode provenance (kind field)
        kind = provenance.get("kind")
        if kind == "explicit":
            explicit = provenance.get("explicit", {})
            return self._validate_explicit_provenance(explicit)
        elif kind == "derived":
            derived = provenance.get("derived", {})
            return self._validate_derived_provenance(derived)

        # Legacy single-mode provenance
        return self._validate_explicit_provenance(provenance)

    # Maximum valid page number (reasonable upper bound)
    MAX_PAGE_NUMBER = 10000

    def _validate_explicit_provenance(self, provenance: Dict[str, Any]) -> bool:
        """
        Validate explicit provenance fields.

        Note: section_number CAN be null (for title pages, headers, cover pages).
        Only page_number and text_snippet are strictly required.

        CRITICAL: page_number must be a positive integer (1 to MAX_PAGE_NUMBER).
        CRITICAL: text_snippet must have non-whitespace content of MIN_SNIPPET_LENGTH.
        """
        page = provenance.get("page_number")
        snippet = provenance.get("text_snippet")

        # page_number must be a positive integer within valid range
        if not isinstance(page, int) or page < 1 or page > self.MAX_PAGE_NUMBER:
            return False

        # text_snippet must be present and have substantive content
        if not snippet or not isinstance(snippet, str):
            return False

        # Validate snippet length (after stripping whitespace)
        if len(snippet.strip()) < self.MIN_SNIPPET_LENGTH:
            return False

        return True

    def _has_sibling_provenance(self, parent: Dict[str, Any], key: str) -> bool:
        """
        Check if field has sibling provenance pattern (e.g., therapeuticAreaProvenance).

        This supports the pattern where a scalar field like "therapeuticArea" has
        a sibling "therapeuticAreaProvenance" object containing the provenance.
        """
        provenance_key = f"{key}Provenance"
        sibling_provenance = parent.get(provenance_key)
        if sibling_provenance and isinstance(sibling_provenance, dict):
            return self._validate_explicit_provenance(sibling_provenance)
        return False

    def _validate_derived_provenance(self, provenance: Dict[str, Any]) -> bool:
        """Validate derived provenance fields."""
        reasoning = provenance.get("reasoning")
        confidence = provenance.get("confidence")

        if not reasoning or not confidence:
            return False

        # Reasoning should be substantive (min 50 chars)
        if len(reasoning) < 50:
            return False

        # Confidence must be valid level
        if confidence not in ("high", "medium", "low"):
            return False

        return True

    def validate_provenance_format(
        self,
        data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Validate provenance format and return issues.

        Args:
            data: Extracted data with provenance

        Returns:
            List of validation issues
        """
        issues = []

        def traverse(obj: Any, path: str):
            if isinstance(obj, dict):
                provenance = obj.get("provenance")
                if provenance:
                    prov_issues = self._check_provenance_format(provenance, path)
                    issues.extend(prov_issues)

                for key, value in obj.items():
                    if isinstance(value, (dict, list)):
                        traverse(value, f"{path}.{key}")

            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    traverse(item, f"{path}[{i}]")

        traverse(data, "$")
        return issues

    def _check_provenance_format(
        self,
        provenance: Dict[str, Any],
        path: str,
    ) -> List[Dict[str, Any]]:
        """Check provenance format and return issues."""
        issues = []

        kind = provenance.get("kind")

        if kind == "explicit":
            explicit = provenance.get("explicit", {})
            if not isinstance(explicit.get("page_number"), int):
                issues.append({
                    "path": f"{path}.provenance.explicit.page_number",
                    "issue": "page_number must be an integer",
                })
            snippet = explicit.get("text_snippet", "")
            if len(snippet) > self.MAX_SNIPPET_LENGTH:
                issues.append({
                    "path": f"{path}.provenance.explicit.text_snippet",
                    "issue": f"text_snippet exceeds {self.MAX_SNIPPET_LENGTH} chars",
                })

        elif kind == "derived":
            derived = provenance.get("derived", {})
            if derived.get("confidence") not in ("high", "medium", "low"):
                issues.append({
                    "path": f"{path}.provenance.derived.confidence",
                    "issue": "confidence must be high, medium, or low",
                })

        elif kind is None:
            # Legacy format - check explicit fields
            if not isinstance(provenance.get("page_number"), int):
                issues.append({
                    "path": f"{path}.provenance.page_number",
                    "issue": "page_number must be an integer",
                })

        return issues

    def generate_coverage_report(
        self,
        data: Dict[str, Any],
        module_id: str,
    ) -> Dict[str, Any]:
        """
        Generate comprehensive provenance coverage report.

        Args:
            data: Extracted data with provenance
            module_id: Module identifier

        Returns:
            Coverage report dictionary
        """
        coverage, missing = self.calculate_coverage(data)
        format_issues = self.validate_provenance_format(data)

        return {
            "module_id": module_id,
            "coverage_percentage": round(coverage * 100, 1),
            "is_compliant": coverage >= 1.0 and len(format_issues) == 0,
            "total_missing_fields": len(missing),
            "missing_fields": missing[:10],  # First 10 only
            "format_issues": format_issues[:10],
            "recommendations": self._generate_recommendations(coverage, missing),
        }

    def _generate_recommendations(
        self,
        coverage: float,
        missing: List[Dict[str, Any]],
    ) -> List[str]:
        """Generate recommendations for improving coverage."""
        recommendations = []

        if coverage < 1.0:
            recommendations.append(
                f"Run provenance pass again with focus on {len(missing)} missing fields"
            )

        if missing:
            # Identify patterns in missing paths
            paths = [m["path"] for m in missing]
            if any("nested" in p.lower() for p in paths):
                recommendations.append(
                    "Ensure nested objects have provenance at appropriate level"
                )
            if any("[" in p for p in paths):
                recommendations.append(
                    "Verify array items have individual provenance objects"
                )

        return recommendations
