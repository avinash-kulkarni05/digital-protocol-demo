"""
Validators - Input validation and schema validation for feasibility module.

This module provides validation functions for:
- Input criteria validation
- Output schema validation
- Data integrity checks
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import jsonschema
from jsonschema import validate, ValidationError

from .data_models import (
    CriterionCategory,
    QueryableStatus,
    KeyCriterion,
    FunnelStage,
    FunnelResult,
)

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom validation error with details."""

    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict] = None):
        super().__init__(message)
        self.field = field
        self.details = details or {}


def validate_criteria_input(criteria: Any) -> List[Dict[str, Any]]:
    """
    Validate and normalize input criteria.

    Args:
        criteria: Input criteria (should be list of dicts).

    Returns:
        Validated list of criterion dictionaries.

    Raises:
        ValidationError: If input is invalid.
    """
    if criteria is None:
        raise ValidationError("Criteria cannot be None", field="criteria")

    if not isinstance(criteria, list):
        raise ValidationError(
            f"Criteria must be a list, got {type(criteria).__name__}",
            field="criteria"
        )

    if len(criteria) == 0:
        raise ValidationError("Criteria list cannot be empty", field="criteria")

    validated = []
    for i, criterion in enumerate(criteria):
        if not isinstance(criterion, dict):
            raise ValidationError(
                f"Criterion at index {i} must be a dictionary",
                field=f"criteria[{i}]"
            )

        # Ensure required fields exist (with flexible naming)
        criterion_id = (
            criterion.get("criterion_id") or
            criterion.get("id") or
            criterion.get("criterionId") or
            f"C{i+1:03d}"  # Generate ID if missing
        )

        text = (
            criterion.get("text") or
            criterion.get("criterion_text") or
            criterion.get("criterionText") or
            ""
        )

        if not text.strip():
            logger.warning(f"Criterion {criterion_id} has empty text")

        criterion_type = (
            criterion.get("criterion_type") or
            criterion.get("type") or
            "inclusion"
        ).lower()

        if criterion_type not in ["inclusion", "exclusion"]:
            criterion_type = "inclusion"

        validated.append({
            "criterion_id": criterion_id,
            "text": text.strip(),
            "criterion_type": criterion_type,
            # Preserve other fields
            **{k: v for k, v in criterion.items()
               if k not in ["criterion_id", "id", "criterionId", "text", "criterion_text", "criterionText", "criterion_type", "type"]}
        })

    logger.info(f"Validated {len(validated)} criteria")
    return validated


def validate_funnel_result(result: FunnelResult) -> Tuple[bool, List[str]]:
    """
    Validate a FunnelResult for completeness and consistency.

    Args:
        result: FunnelResult to validate.

    Returns:
        Tuple of (is_valid, list of warning messages).
    """
    warnings = []

    # Check required fields
    if not result.protocol_id:
        warnings.append("Missing protocol_id")

    if not result.key_criteria:
        warnings.append("No key criteria generated")

    if not result.stages:
        warnings.append("No funnel stages generated")

    # Check population consistency
    if result.initial_population <= 0:
        warnings.append("Initial population must be positive")

    if result.final_eligible_estimate:
        if result.final_eligible_estimate.count < 0:
            warnings.append("Final eligible estimate cannot be negative")
        if result.final_eligible_estimate.count > result.initial_population:
            warnings.append("Final eligible cannot exceed initial population")

    # Check stage consistency
    prev_exiting = result.initial_population
    for stage in result.stages:
        if stage.patients_entering != prev_exiting:
            warnings.append(
                f"Stage '{stage.stage_name}' entering ({stage.patients_entering}) "
                f"doesn't match previous exiting ({prev_exiting})"
            )
        if stage.patients_exiting > stage.patients_entering:
            warnings.append(
                f"Stage '{stage.stage_name}' exiting ({stage.patients_exiting}) "
                f"exceeds entering ({stage.patients_entering})"
            )
        prev_exiting = stage.patients_exiting

    # Check killer criteria exist
    key_ids = {kc.key_id for kc in result.key_criteria}
    for killer_id in result.killer_criteria:
        if killer_id not in key_ids:
            warnings.append(f"Killer criterion {killer_id} not in key criteria")

    is_valid = len([w for w in warnings if "cannot" in w or "must" in w]) == 0
    return is_valid, warnings


def validate_against_schema(data: Dict[str, Any], schema_path: Path) -> Tuple[bool, List[str]]:
    """
    Validate data against JSON schema.

    Args:
        data: Data dictionary to validate.
        schema_path: Path to JSON schema file.

    Returns:
        Tuple of (is_valid, list of error messages).
    """
    if not schema_path.exists():
        return True, [f"Schema file not found: {schema_path}"]

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        validate(instance=data, schema=schema)
        return True, []

    except jsonschema.ValidationError as e:
        return False, [f"Schema validation failed: {e.message} at {e.json_path}"]
    except json.JSONDecodeError as e:
        return False, [f"Invalid schema JSON: {e}"]


def validate_key_criterion(criterion: KeyCriterion) -> List[str]:
    """
    Validate a single KeyCriterion.

    Args:
        criterion: KeyCriterion to validate.

    Returns:
        List of validation issues (empty if valid).
    """
    issues = []

    if not criterion.key_id:
        issues.append("Missing key_id")

    if not criterion.normalized_text:
        issues.append("Missing normalized_text")

    if not isinstance(criterion.category, CriterionCategory):
        issues.append(f"Invalid category: {criterion.category}")

    if not isinstance(criterion.queryable_status, QueryableStatus):
        issues.append(f"Invalid queryable_status: {criterion.queryable_status}")

    if criterion.estimated_elimination_rate < 0 or criterion.estimated_elimination_rate > 100:
        issues.append(f"Elimination rate out of range: {criterion.estimated_elimination_rate}")

    if criterion.funnel_priority < 0:
        issues.append(f"Funnel priority cannot be negative: {criterion.funnel_priority}")

    return issues


def validate_funnel_output_for_export(result: FunnelResult) -> Tuple[bool, Dict[str, Any]]:
    """
    Validate funnel result before export, including schema validation.

    Args:
        result: FunnelResult to validate.

    Returns:
        Tuple of (is_valid, validation_report).
    """
    report = {
        "is_valid": True,
        "errors": [],
        "warnings": [],
        "summary": {},
    }

    # Validate result object
    is_valid, warnings = validate_funnel_result(result)
    report["warnings"].extend(warnings)
    if not is_valid:
        report["is_valid"] = False
        report["errors"].append("FunnelResult validation failed")

    # Validate each key criterion
    for kc in result.key_criteria:
        issues = validate_key_criterion(kc)
        if issues:
            report["warnings"].extend([f"{kc.key_id}: {issue}" for issue in issues])

    # Schema validation
    schema_path = Path(__file__).parent / "schemas" / "funnel_output_schema.json"
    if schema_path.exists():
        schema_valid, schema_errors = validate_against_schema(result.to_dict(), schema_path)
        if not schema_valid:
            report["is_valid"] = False
            report["errors"].extend(schema_errors)

    # Summary
    report["summary"] = {
        "total_key_criteria": len(result.key_criteria),
        "total_stages": len(result.stages),
        "killer_criteria_count": len(result.killer_criteria),
        "manual_assessment_count": len(result.manual_assessment_criteria),
        "optimization_opportunities": len(result.optimization_opportunities),
    }

    return report["is_valid"], report
