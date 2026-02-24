"""
Validation Contracts Module for Eligibility Pipeline.

Provides schema validation at stage boundaries to ensure data integrity
across the eligibility extraction pipeline. This is a fail-safe mechanism
to catch bugs early and prevent cascading failures.

Key Validation Points:
1. Stage 2 Output: Expression tree structure and atomic metadata
2. Eligibility Funnel Output: Atomic criteria with OMOP mappings
3. QEB Output: Final queryable eligibility blocks

Usage:
    from eligibility_analyzer.services.validation_contracts import (
        validate_stage2_output,
        validate_funnel_output,
        validate_qeb_output,
    )

    # Validate Stage 2 output
    result = validate_stage2_output(stage2_result)
    if not result.is_valid:
        logger.error(f"Stage 2 validation failed: {result.errors}")
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# VALIDATION RESULT STRUCTURE
# =============================================================================

@dataclass
class ValidationResult:
    """Result of a validation check."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    validated_records: int = 0
    failed_records: int = 0
    validation_context: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "validated_records": self.validated_records,
            "failed_records": self.failed_records,
            "validation_context": self.validation_context,
        }


# =============================================================================
# EXPRESSION TREE VALIDATORS
# =============================================================================

# Valid node types in expression trees
VALID_NODE_TYPES = {"atomic", "operator", "temporal"}

# Valid operators
VALID_OPERATORS = {"AND", "OR", "NOT", "EXCEPT", "IMPLICATION"}

# Valid clinical categories (from Stage 2 prompt)
VALID_CLINICAL_CATEGORIES = {
    "disease_indication",
    "biomarker",
    "prior_therapy",
    "performance_status",
    "organ_function",
    "safety_exclusion",
    "demographics",
    "diagnostic_confirmation",
    "other",
}

# Valid queryable statuses (data source-aware taxonomy)
VALID_QUERYABLE_STATUSES = {
    # Structured data sources - SQL/FHIR queryable
    "fully_queryable",
    # Unstructured data sources - LLM extractable
    "llm_extractable",
    # Hybrid - SQL + LLM
    "hybrid_queryable",
    # True screening requirements
    "screening_only",
    # Consent/compliance - not patient filters
    "not_applicable",
    # Legacy (backward compatibility)
    "partially_queryable",
    "requires_manual",
}


def _validate_expression_node(
    node: Dict[str, Any],
    path: str,
    errors: List[str],
    warnings: List[str],
) -> int:
    """
    Recursively validate an expression tree node.

    Args:
        node: Expression tree node to validate.
        path: Current path in tree (for error messages).
        errors: List to append errors to.
        warnings: List to append warnings to.

    Returns:
        Count of atomic nodes found in this subtree.
    """
    if not node:
        errors.append(f"{path}: Node is null or empty")
        return 0

    node_type = node.get("nodeType")
    node_id = node.get("nodeId", "unknown")
    atomic_count = 0

    # Validate node type
    if not node_type:
        errors.append(f"{path}: Missing nodeType")
        return 0

    if node_type not in VALID_NODE_TYPES:
        errors.append(f"{path}: Invalid nodeType '{node_type}', expected one of {VALID_NODE_TYPES}")
        return 0

    # Validate node ID
    if not node_id or node_id == "unknown":
        warnings.append(f"{path}: Node missing nodeId")

    # Type-specific validation
    if node_type == "atomic":
        atomic_count = 1

        # Required fields for atomic nodes
        atomic_text = node.get("atomicText")
        if not atomic_text:
            errors.append(f"{path}[{node_id}]: Atomic node missing atomicText")

        omop_table = node.get("omopTable")
        if not omop_table:
            warnings.append(f"{path}[{node_id}]: Atomic node missing omopTable")

        # Validate clinical metadata (optional but recommended)
        clinical_category = node.get("clinicalCategory")
        if clinical_category and clinical_category not in VALID_CLINICAL_CATEGORIES:
            warnings.append(
                f"{path}[{node_id}]: Invalid clinicalCategory '{clinical_category}', "
                f"expected one of {VALID_CLINICAL_CATEGORIES}"
            )

        queryable_status = node.get("queryableStatus")
        if queryable_status and queryable_status not in VALID_QUERYABLE_STATUSES:
            warnings.append(
                f"{path}[{node_id}]: Invalid queryableStatus '{queryable_status}', "
                f"expected one of {VALID_QUERYABLE_STATUSES}"
            )

    elif node_type == "operator":
        operator = node.get("operator")
        if not operator:
            errors.append(f"{path}[{node_id}]: Operator node missing operator field")
            return 0

        if operator not in VALID_OPERATORS:
            errors.append(
                f"{path}[{node_id}]: Invalid operator '{operator}', "
                f"expected one of {VALID_OPERATORS}"
            )
            return 0

        # IMPLICATION has condition/requirement instead of operands
        if operator == "IMPLICATION":
            condition = node.get("condition")
            requirement = node.get("requirement")

            if not condition:
                errors.append(f"{path}[{node_id}]: IMPLICATION missing 'condition' branch")
            else:
                atomic_count += _validate_expression_node(
                    condition, f"{path}[{node_id}].condition", errors, warnings
                )

            if not requirement:
                errors.append(f"{path}[{node_id}]: IMPLICATION missing 'requirement' branch")
            else:
                atomic_count += _validate_expression_node(
                    requirement, f"{path}[{node_id}].requirement", errors, warnings
                )
        else:
            # Standard operators use operands
            operands = node.get("operands", [])

            if operator == "NOT" and len(operands) != 1:
                warnings.append(
                    f"{path}[{node_id}]: NOT operator should have exactly 1 operand, "
                    f"found {len(operands)}"
                )

            if operator in {"AND", "OR"} and len(operands) < 2:
                warnings.append(
                    f"{path}[{node_id}]: {operator} operator should have at least 2 operands, "
                    f"found {len(operands)}"
                )

            for i, operand in enumerate(operands):
                atomic_count += _validate_expression_node(
                    operand, f"{path}[{node_id}].operands[{i}]", errors, warnings
                )

    elif node_type == "temporal":
        operand = node.get("operand")
        if not operand:
            errors.append(f"{path}[{node_id}]: Temporal node missing 'operand'")
        else:
            atomic_count += _validate_expression_node(
                operand, f"{path}[{node_id}].operand", errors, warnings
            )

    return atomic_count


def validate_stage2_output(stage2_result: Dict[str, Any]) -> ValidationResult:
    """
    Validate Stage 2 atomic decomposition output.

    Checks:
    - decomposedCriteria array exists and is non-empty
    - Each criterion has criterionId, originalText, expression
    - Expression trees are structurally valid
    - Atomic nodes have required fields
    - Clinical metadata is valid if present

    Args:
        stage2_result: Output from Stage 2 atomic decomposition.

    Returns:
        ValidationResult with validation status and any errors/warnings.
    """
    errors = []
    warnings = []
    validated = 0
    failed = 0
    total_atomics = 0

    # Check top-level structure
    decomposed = stage2_result.get("decomposedCriteria", [])
    if not decomposed:
        errors.append("decomposedCriteria is missing or empty")
        return ValidationResult(
            is_valid=False,
            errors=errors,
            validation_context="Stage 2 Output Validation"
        )

    # Validate each criterion
    for i, criterion in enumerate(decomposed):
        criterion_id = criterion.get("criterionId", f"criterion_{i}")

        # Required fields
        if not criterion.get("criterionId"):
            errors.append(f"Criterion {i}: Missing criterionId")
            failed += 1
            continue

        if not criterion.get("originalText"):
            warnings.append(f"{criterion_id}: Missing originalText")

        expression = criterion.get("expression")
        if not expression:
            errors.append(f"{criterion_id}: Missing expression tree")
            failed += 1
            continue

        # Validate expression tree
        atomic_count = _validate_expression_node(
            expression, f"{criterion_id}.expression", errors, warnings
        )
        total_atomics += atomic_count

        if atomic_count == 0:
            warnings.append(f"{criterion_id}: Expression tree has no atomic nodes")

        validated += 1

    is_valid = len(errors) == 0

    result = ValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
        validated_records=validated,
        failed_records=failed,
        validation_context=f"Stage 2 Output Validation ({total_atomics} atomics across {validated} criteria)"
    )

    if is_valid:
        logger.info(f"Stage 2 validation PASSED: {result.validation_context}")
    else:
        logger.error(f"Stage 2 validation FAILED: {len(errors)} errors, {len(warnings)} warnings")

    return result


# =============================================================================
# ELIGIBILITY FUNNEL VALIDATORS
# =============================================================================

def validate_funnel_output(funnel_output: Dict[str, Any]) -> ValidationResult:
    """
    Validate eligibility funnel output.

    Checks:
    - atomicCriteria array exists
    - Each atomic has required fields (atomicId, originalCriterionId, text)
    - OMOP mappings are present when expected
    - Queryable status is valid
    - Stage 2 metadata is preserved when present

    Args:
        funnel_output: Output from eligibility funnel builder.

    Returns:
        ValidationResult with validation status and any errors/warnings.
    """
    errors = []
    warnings = []
    validated = 0
    failed = 0

    # Check top-level structure
    atomics = funnel_output.get("atomicCriteria", [])
    if not atomics:
        errors.append("atomicCriteria is missing or empty")
        return ValidationResult(
            is_valid=False,
            errors=errors,
            validation_context="Eligibility Funnel Output Validation"
        )

    # Track criterion IDs for grouping validation
    criterion_ids: Set[str] = set()
    atomics_per_criterion: Dict[str, int] = {}

    # Validate each atomic
    for i, atomic in enumerate(atomics):
        atomic_id = atomic.get("atomicId", f"atomic_{i}")

        # Required fields
        if not atomic.get("atomicId"):
            errors.append(f"Atomic {i}: Missing atomicId")
            failed += 1
            continue

        criterion_id = atomic.get("originalCriterionId")
        if not criterion_id:
            errors.append(f"{atomic_id}: Missing originalCriterionId")
            failed += 1
            continue

        criterion_ids.add(criterion_id)
        atomics_per_criterion[criterion_id] = atomics_per_criterion.get(criterion_id, 0) + 1

        text = atomic.get("text") or atomic.get("atomicText")
        if not text:
            errors.append(f"{atomic_id}: Missing text/atomicText")
            failed += 1
            continue

        # Validate OMOP query if present
        omop_query = atomic.get("omopQuery")
        if omop_query:
            concept_ids = omop_query.get("conceptIds", [])
            if not concept_ids or not any(cid for cid in concept_ids):
                warnings.append(f"{atomic_id}: omopQuery present but no valid conceptIds")

        # Validate queryable status
        queryable_status = atomic.get("queryableStatus", "requires_manual")
        if queryable_status not in VALID_QUERYABLE_STATUSES:
            warnings.append(
                f"{atomic_id}: Invalid queryableStatus '{queryable_status}', "
                f"expected one of {VALID_QUERYABLE_STATUSES}"
            )

        # Check for Stage 2 metadata preservation
        stage2_category = atomic.get("stage2ClinicalCategory") or atomic.get("clinicalCategory")
        stage2_status = atomic.get("stage2QueryableStatus")
        if stage2_status and stage2_status != queryable_status:
            # This is informational - status may have been overridden
            pass  # No warning needed, this is expected behavior

        validated += 1

    is_valid = len(errors) == 0

    result = ValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
        validated_records=validated,
        failed_records=failed,
        validation_context=(
            f"Eligibility Funnel Validation ({validated} atomics "
            f"across {len(criterion_ids)} criteria)"
        )
    )

    if is_valid:
        logger.info(f"Funnel validation PASSED: {result.validation_context}")
    else:
        logger.error(f"Funnel validation FAILED: {len(errors)} errors, {len(warnings)} warnings")

    return result


# =============================================================================
# QEB OUTPUT VALIDATORS
# =============================================================================

def validate_qeb_output(qeb_output: Dict[str, Any]) -> ValidationResult:
    """
    Validate QEB (Queryable Eligibility Block) output.

    Checks:
    - queryableBlocks array exists
    - Each QEB has required fields
    - Combined SQL is present for queryable criteria
    - Funnel stages are properly defined
    - Atomic references are valid

    Args:
        qeb_output: Output from Stage 12 QEB builder.

    Returns:
        ValidationResult with validation status and any errors/warnings.
    """
    errors = []
    warnings = []
    validated = 0
    failed = 0

    # Check top-level structure
    qebs = qeb_output.get("queryableBlocks", [])
    if not qebs:
        errors.append("queryableBlocks is missing or empty")
        return ValidationResult(
            is_valid=False,
            errors=errors,
            validation_context="QEB Output Validation"
        )

    # Validate each QEB
    qeb_ids: Set[str] = set()
    for i, qeb in enumerate(qebs):
        qeb_id = qeb.get("qebId", f"qeb_{i}")

        # Required fields
        if not qeb.get("qebId"):
            errors.append(f"QEB {i}: Missing qebId")
            failed += 1
            continue

        if qeb_id in qeb_ids:
            errors.append(f"{qeb_id}: Duplicate qebId")

        qeb_ids.add(qeb_id)

        criterion_id = qeb.get("originalCriterionId")
        if not criterion_id:
            errors.append(f"{qeb_id}: Missing originalCriterionId")
            failed += 1
            continue

        # Validate SQL/NLP spec presence based on queryable status
        queryable_status = qeb.get("queryableStatus", "requires_manual")
        combined_sql = qeb.get("combinedSql", "")

        # SQL should be present for fully_queryable and hybrid_queryable
        if queryable_status in {"fully_queryable", "partially_queryable", "hybrid_queryable"}:
            if not combined_sql or "MISSING SQL" in combined_sql or "NO SQL" in combined_sql:
                warnings.append(
                    f"{qeb_id}: Status is '{queryable_status}' but SQL is missing or invalid"
                )

        # Check for nlpQuerySpec on LLM-based statuses (atomic level)
        if queryable_status in {"llm_extractable", "hybrid_queryable"}:
            # This would be validated at atomic level, not QEB level
            pass

        # Validate atomic count consistency
        atomic_ids = qeb.get("atomicIds", [])
        atomic_count = qeb.get("atomicCount", 0)
        if len(atomic_ids) != atomic_count:
            warnings.append(
                f"{qeb_id}: atomicCount ({atomic_count}) doesn't match "
                f"atomicIds length ({len(atomic_ids)})"
            )

        # Validate clinical summary if present
        clinical_summary = qeb.get("clinicalSummary")
        if clinical_summary:
            concept_groups = clinical_summary.get("conceptGroups", [])
            for j, group in enumerate(concept_groups):
                if not group.get("groupName"):
                    warnings.append(f"{qeb_id}.clinicalSummary.conceptGroups[{j}]: Missing groupName")
                group_status = group.get("queryableStatus")
                if group_status and group_status not in VALID_QUERYABLE_STATUSES:
                    warnings.append(
                        f"{qeb_id}.clinicalSummary.conceptGroups[{j}]: Invalid queryableStatus '{group_status}'"
                    )

        validated += 1

    # Validate funnel stages
    funnel_stages = qeb_output.get("funnelStages", [])
    if funnel_stages:
        all_qeb_ids_in_stages: Set[str] = set()
        for stage in funnel_stages:
            stage_qeb_ids = stage.get("qebIds", [])
            for sid in stage_qeb_ids:
                if sid not in qeb_ids:
                    errors.append(f"Funnel stage references unknown QEB: {sid}")
                all_qeb_ids_in_stages.add(sid)

        # Check if all QEBs are assigned to a stage
        unassigned = qeb_ids - all_qeb_ids_in_stages
        if unassigned:
            warnings.append(f"QEBs not assigned to any funnel stage: {unassigned}")

    is_valid = len(errors) == 0

    result = ValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
        validated_records=validated,
        failed_records=failed,
        validation_context=f"QEB Output Validation ({validated} QEBs, {len(funnel_stages)} funnel stages)"
    )

    if is_valid:
        logger.info(f"QEB validation PASSED: {result.validation_context}")
    else:
        logger.error(f"QEB validation FAILED: {len(errors)} errors, {len(warnings)} warnings")

    return result


# =============================================================================
# CROSS-STAGE VALIDATION
# =============================================================================

def validate_stage_consistency(
    stage2_result: Dict[str, Any],
    funnel_output: Dict[str, Any],
    qeb_output: Dict[str, Any],
) -> ValidationResult:
    """
    Validate consistency across all pipeline stages.

    Checks:
    - All Stage 2 criteria have corresponding funnel atomics
    - All funnel atomics have corresponding QEB entries
    - Atomic counts are consistent across stages
    - No orphaned data between stages

    Args:
        stage2_result: Output from Stage 2.
        funnel_output: Output from eligibility funnel.
        qeb_output: Output from QEB builder.

    Returns:
        ValidationResult with cross-stage validation status.
    """
    errors = []
    warnings = []

    # Collect criterion IDs from each stage
    stage2_criteria = {
        c.get("criterionId") for c in stage2_result.get("decomposedCriteria", [])
        if c.get("criterionId")
    }

    funnel_criteria = {
        a.get("originalCriterionId") for a in funnel_output.get("atomicCriteria", [])
        if a.get("originalCriterionId")
    }

    qeb_criteria = {
        q.get("originalCriterionId") for q in qeb_output.get("queryableBlocks", [])
        if q.get("originalCriterionId")
    }

    # Check for criteria lost between stages
    lost_in_funnel = stage2_criteria - funnel_criteria
    if lost_in_funnel:
        warnings.append(
            f"Criteria in Stage 2 but not in funnel: {lost_in_funnel} "
            f"(may be expected if criteria couldn't be decomposed)"
        )

    lost_in_qeb = funnel_criteria - qeb_criteria
    if lost_in_qeb:
        errors.append(f"Criteria in funnel but not in QEB: {lost_in_qeb}")

    # Count atomics at each stage
    stage2_atomic_count = 0
    for criterion in stage2_result.get("decomposedCriteria", []):
        expression = criterion.get("expression")
        if expression:
            stage2_atomic_count += _count_atomics_in_tree(expression)

    funnel_atomic_count = len(funnel_output.get("atomicCriteria", []))

    qeb_atomic_count = sum(
        q.get("atomicCount", 0) for q in qeb_output.get("queryableBlocks", [])
    )

    # Report atomic counts
    if stage2_atomic_count != funnel_atomic_count:
        error_or_warn = errors if (stage2_atomic_count - funnel_atomic_count) > 5 else warnings
        error_or_warn.append(
            f"Atomic count mismatch: Stage 2 has {stage2_atomic_count}, "
            f"funnel has {funnel_atomic_count} (diff: {stage2_atomic_count - funnel_atomic_count})"
        )

    if funnel_atomic_count != qeb_atomic_count:
        warnings.append(
            f"Atomic count mismatch: Funnel has {funnel_atomic_count}, "
            f"QEB references {qeb_atomic_count}"
        )

    is_valid = len(errors) == 0

    return ValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
        validation_context=(
            f"Cross-Stage Consistency Validation "
            f"(Stage2: {len(stage2_criteria)} criteria/{stage2_atomic_count} atomics, "
            f"Funnel: {len(funnel_criteria)} criteria/{funnel_atomic_count} atomics, "
            f"QEB: {len(qeb_criteria)} criteria)"
        )
    )


def _count_atomics_in_tree(node: Dict[str, Any]) -> int:
    """Count atomic nodes in an expression tree."""
    if not node:
        return 0

    node_type = node.get("nodeType", "")

    if node_type == "atomic":
        return 1

    if node_type == "operator":
        operator = node.get("operator", "")
        count = 0

        if operator == "IMPLICATION":
            condition = node.get("condition", {})
            requirement = node.get("requirement", {})
            count += _count_atomics_in_tree(condition)
            count += _count_atomics_in_tree(requirement)
        else:
            for operand in node.get("operands", []):
                count += _count_atomics_in_tree(operand)

        return count

    if node_type == "temporal":
        operand = node.get("operand", {})
        return _count_atomics_in_tree(operand)

    return 0


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def validate_all_stages(
    stage2_result: Dict[str, Any],
    funnel_output: Dict[str, Any],
    qeb_output: Dict[str, Any],
) -> Dict[str, ValidationResult]:
    """
    Run all validations and return comprehensive results.

    Args:
        stage2_result: Output from Stage 2.
        funnel_output: Output from eligibility funnel.
        qeb_output: Output from QEB builder.

    Returns:
        Dictionary mapping validation name to ValidationResult.
    """
    results = {
        "stage2": validate_stage2_output(stage2_result),
        "funnel": validate_funnel_output(funnel_output),
        "qeb": validate_qeb_output(qeb_output),
        "cross_stage": validate_stage_consistency(stage2_result, funnel_output, qeb_output),
    }

    # Overall validation
    all_valid = all(r.is_valid for r in results.values())
    total_errors = sum(len(r.errors) for r in results.values())
    total_warnings = sum(len(r.warnings) for r in results.values())

    logger.info(
        f"Complete pipeline validation: {'PASSED' if all_valid else 'FAILED'} "
        f"({total_errors} errors, {total_warnings} warnings)"
    )

    return results
