"""
Unit tests for expression tree operator handling.

Tests cover:
- IMPLICATION operator processing (P → Q)
- Standard operators (AND, OR, NOT, EXCEPT)
- Temporal node handling
- Nested operator combinations
- Edge cases (empty operands, missing branches)
- Atomic count validation across stages
- Clinical metadata propagation
"""

import pytest
from typing import Dict, Any, List, Tuple


# =============================================================================
# TEST FIXTURES - Expression Tree Structures
# =============================================================================

@pytest.fixture
def simple_atomic_node() -> Dict[str, Any]:
    """Simple atomic node with clinical metadata."""
    return {
        "nodeId": "1",
        "nodeType": "atomic",
        "atomicText": "Patient has confirmed NSCLC diagnosis",
        "omopTable": "condition_occurrence",
        "strategy": "Standard diagnosis lookup",
        "clinicalCategory": "disease_indication",
        "queryableStatus": "fully_queryable",
        "clinicalConceptGroup": None,
    }


@pytest.fixture
def and_operator_node() -> Dict[str, Any]:
    """AND operator with two atomics."""
    return {
        "nodeId": "root",
        "nodeType": "operator",
        "operator": "AND",
        "operands": [
            {
                "nodeId": "1",
                "nodeType": "atomic",
                "atomicText": "Age >= 18 years",
                "omopTable": "person",
                "clinicalCategory": "demographics",
                "queryableStatus": "fully_queryable",
            },
            {
                "nodeId": "2",
                "nodeType": "atomic",
                "atomicText": "ECOG performance status 0-1",
                "omopTable": "observation",
                "clinicalCategory": "performance_status",
                "queryableStatus": "partially_queryable",
            },
        ],
    }


@pytest.fixture
def or_operator_node() -> Dict[str, Any]:
    """OR operator with three atomics (biomarker variants)."""
    return {
        "nodeId": "root",
        "nodeType": "operator",
        "operator": "OR",
        "operands": [
            {
                "nodeId": "1a",
                "nodeType": "atomic",
                "atomicText": "EGFR exon 19 deletion",
                "omopTable": "observation",
                "clinicalCategory": "biomarker",
                "queryableStatus": "fully_queryable",
                "clinicalConceptGroup": "egfr_activating_mutation",
            },
            {
                "nodeId": "1b",
                "nodeType": "atomic",
                "atomicText": "EGFR L858R mutation",
                "omopTable": "observation",
                "clinicalCategory": "biomarker",
                "queryableStatus": "fully_queryable",
                "clinicalConceptGroup": "egfr_activating_mutation",
            },
            {
                "nodeId": "1c",
                "nodeType": "atomic",
                "atomicText": "ALK gene rearrangement",
                "omopTable": "observation",
                "clinicalCategory": "biomarker",
                "queryableStatus": "fully_queryable",
                "clinicalConceptGroup": "alk_positive",
            },
        ],
    }


@pytest.fixture
def not_operator_node() -> Dict[str, Any]:
    """NOT operator with single operand."""
    return {
        "nodeId": "root",
        "nodeType": "operator",
        "operator": "NOT",
        "operands": [
            {
                "nodeId": "1",
                "nodeType": "atomic",
                "atomicText": "Active autoimmune disease",
                "omopTable": "condition_occurrence",
                "clinicalCategory": "safety_exclusion",
                "queryableStatus": "partially_queryable",
            },
        ],
    }


@pytest.fixture
def implication_operator_node() -> Dict[str, Any]:
    """IMPLICATION operator (P → Q): IF condition THEN requirement."""
    return {
        "nodeId": "root",
        "nodeType": "operator",
        "operator": "IMPLICATION",
        "condition": {
            "nodeId": "cond",
            "nodeType": "operator",
            "operator": "OR",
            "operands": [
                {
                    "nodeId": "cond_1",
                    "nodeType": "atomic",
                    "atomicText": "EGFR mutation positive",
                    "omopTable": "observation",
                    "clinicalCategory": "biomarker",
                    "queryableStatus": "fully_queryable",
                },
                {
                    "nodeId": "cond_2",
                    "nodeType": "atomic",
                    "atomicText": "ALK rearrangement positive",
                    "omopTable": "observation",
                    "clinicalCategory": "biomarker",
                    "queryableStatus": "fully_queryable",
                },
            ],
        },
        "requirement": {
            "nodeId": "req",
            "nodeType": "operator",
            "operator": "AND",
            "operands": [
                {
                    "nodeId": "req_1",
                    "nodeType": "atomic",
                    "atomicText": "Received prior targeted therapy",
                    "omopTable": "drug_exposure",
                    "clinicalCategory": "prior_therapy",
                    "queryableStatus": "partially_queryable",
                },
                {
                    "nodeId": "req_2",
                    "nodeType": "atomic",
                    "atomicText": "Disease progression documented",
                    "omopTable": "condition_occurrence",
                    "clinicalCategory": "disease_indication",
                    "queryableStatus": "partially_queryable",
                },
            ],
        },
    }


@pytest.fixture
def temporal_node() -> Dict[str, Any]:
    """Temporal node with nested atomic."""
    return {
        "nodeId": "root",
        "nodeType": "temporal",
        "temporalConstraint": {
            "referencePoint": "screening",
            "direction": "before",
            "durationValue": 28,
            "durationUnit": "days",
        },
        "operand": {
            "nodeId": "1",
            "nodeType": "atomic",
            "atomicText": "Brain MRI performed",
            "omopTable": "procedure_occurrence",
            "clinicalCategory": "diagnostic_confirmation",
            "queryableStatus": "screening_only",
        },
    }


@pytest.fixture
def nested_complex_tree() -> Dict[str, Any]:
    """Complex nested tree: AND(OR(...), IMPLICATION(...), TEMPORAL(...))."""
    return {
        "nodeId": "root",
        "nodeType": "operator",
        "operator": "AND",
        "operands": [
            # First operand: simple atomic
            {
                "nodeId": "1",
                "nodeType": "atomic",
                "atomicText": "Confirmed NSCLC",
                "omopTable": "condition_occurrence",
                "clinicalCategory": "disease_indication",
                "queryableStatus": "fully_queryable",
            },
            # Second operand: OR of biomarkers
            {
                "nodeId": "2",
                "nodeType": "operator",
                "operator": "OR",
                "operands": [
                    {
                        "nodeId": "2a",
                        "nodeType": "atomic",
                        "atomicText": "EGFR mutation",
                        "omopTable": "observation",
                        "clinicalCategory": "biomarker",
                        "queryableStatus": "fully_queryable",
                    },
                    {
                        "nodeId": "2b",
                        "nodeType": "atomic",
                        "atomicText": "ALK rearrangement",
                        "omopTable": "observation",
                        "clinicalCategory": "biomarker",
                        "queryableStatus": "fully_queryable",
                    },
                ],
            },
            # Third operand: IMPLICATION
            {
                "nodeId": "3",
                "nodeType": "operator",
                "operator": "IMPLICATION",
                "condition": {
                    "nodeId": "3_cond",
                    "nodeType": "atomic",
                    "atomicText": "Has targetable mutation",
                    "omopTable": "observation",
                    "clinicalCategory": "biomarker",
                    "queryableStatus": "fully_queryable",
                },
                "requirement": {
                    "nodeId": "3_req",
                    "nodeType": "atomic",
                    "atomicText": "Prior TKI therapy",
                    "omopTable": "drug_exposure",
                    "clinicalCategory": "prior_therapy",
                    "queryableStatus": "partially_queryable",
                },
            },
        ],
    }


# =============================================================================
# HELPER FUNCTIONS FOR TESTING
# =============================================================================

def count_atomics_in_tree(node: Dict[str, Any]) -> int:
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
            count += count_atomics_in_tree(condition)
            count += count_atomics_in_tree(requirement)
        else:
            for operand in node.get("operands", []):
                count += count_atomics_in_tree(operand)

        return count

    if node_type == "temporal":
        operand = node.get("operand", {})
        return count_atomics_in_tree(operand)

    return 0


def collect_leaf_nodes(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Collect all atomic (leaf) nodes from expression tree."""
    leaves = []
    node_type = node.get("nodeType", "")

    if node_type == "atomic":
        leaves.append(node)
    elif node_type == "operator":
        operator = node.get("operator", "")

        if operator == "IMPLICATION":
            condition = node.get("condition", {})
            requirement = node.get("requirement", {})
            if condition:
                leaves.extend(collect_leaf_nodes(condition))
            if requirement:
                leaves.extend(collect_leaf_nodes(requirement))
        else:
            for operand in node.get("operands", []):
                leaves.extend(collect_leaf_nodes(operand))
    elif node_type == "temporal":
        operand = node.get("operand", {})
        if operand:
            leaves.extend(collect_leaf_nodes(operand))

    return leaves


def collect_operators(node: Dict[str, Any]) -> List[str]:
    """Collect all operators from expression tree."""
    operators = []

    if not node:
        return operators

    node_type = node.get("nodeType", "")

    if node_type == "operator":
        operator = node.get("operator", "")
        if operator:
            operators.append(operator)

        if operator == "IMPLICATION":
            condition = node.get("condition", {})
            requirement = node.get("requirement", {})
            if condition:
                operators.extend(collect_operators(condition))
            if requirement:
                operators.extend(collect_operators(requirement))
        else:
            for operand in node.get("operands", []):
                operators.extend(collect_operators(operand))

    elif node_type == "temporal":
        operators.append("TEMPORAL")
        operand = node.get("operand", {})
        if operand:
            operators.extend(collect_operators(operand))

    return operators


# =============================================================================
# TEST CLASSES
# =============================================================================

class TestAtomicCounting:
    """Tests for atomic node counting in expression trees."""

    def test_single_atomic(self, simple_atomic_node):
        """Test counting single atomic node."""
        count = count_atomics_in_tree(simple_atomic_node)
        assert count == 1

    def test_and_operator_atomics(self, and_operator_node):
        """Test counting atomics in AND operator."""
        count = count_atomics_in_tree(and_operator_node)
        assert count == 2

    def test_or_operator_atomics(self, or_operator_node):
        """Test counting atomics in OR operator."""
        count = count_atomics_in_tree(or_operator_node)
        assert count == 3

    def test_not_operator_atomics(self, not_operator_node):
        """Test counting atomics in NOT operator."""
        count = count_atomics_in_tree(not_operator_node)
        assert count == 1

    def test_implication_operator_atomics(self, implication_operator_node):
        """Test counting atomics in IMPLICATION operator.

        IMPLICATION has condition (2 atomics) + requirement (2 atomics) = 4 total.
        """
        count = count_atomics_in_tree(implication_operator_node)
        assert count == 4, f"Expected 4 atomics in IMPLICATION, got {count}"

    def test_temporal_node_atomics(self, temporal_node):
        """Test counting atomics in temporal node."""
        count = count_atomics_in_tree(temporal_node)
        assert count == 1

    def test_nested_complex_tree_atomics(self, nested_complex_tree):
        """Test counting atomics in complex nested tree.

        Tree structure:
        - AND root
          - Atomic "Confirmed NSCLC" (1)
          - OR (2a, 2b) = 2 atomics
          - IMPLICATION (3_cond, 3_req) = 2 atomics
        Total: 1 + 2 + 2 = 5 atomics
        """
        count = count_atomics_in_tree(nested_complex_tree)
        assert count == 5, f"Expected 5 atomics in nested tree, got {count}"

    def test_empty_node(self):
        """Test counting atomics in empty/None node."""
        assert count_atomics_in_tree(None) == 0
        assert count_atomics_in_tree({}) == 0


class TestLeafNodeCollection:
    """Tests for collecting leaf (atomic) nodes from expression trees."""

    def test_collect_from_implication(self, implication_operator_node):
        """Test collecting leaf nodes from IMPLICATION operator."""
        leaves = collect_leaf_nodes(implication_operator_node)
        assert len(leaves) == 4

        node_ids = [leaf.get("nodeId") for leaf in leaves]
        assert "cond_1" in node_ids
        assert "cond_2" in node_ids
        assert "req_1" in node_ids
        assert "req_2" in node_ids

    def test_collect_from_temporal(self, temporal_node):
        """Test collecting leaf nodes from temporal node."""
        leaves = collect_leaf_nodes(temporal_node)
        assert len(leaves) == 1
        assert leaves[0].get("nodeId") == "1"

    def test_collect_from_nested_tree(self, nested_complex_tree):
        """Test collecting leaf nodes from complex nested tree."""
        leaves = collect_leaf_nodes(nested_complex_tree)
        assert len(leaves) == 5

        node_ids = [leaf.get("nodeId") for leaf in leaves]
        assert "1" in node_ids  # Root atomic
        assert "2a" in node_ids  # OR branch
        assert "2b" in node_ids  # OR branch
        assert "3_cond" in node_ids  # IMPLICATION condition
        assert "3_req" in node_ids  # IMPLICATION requirement

    def test_leaf_metadata_preserved(self, or_operator_node):
        """Test that leaf node clinical metadata is preserved."""
        leaves = collect_leaf_nodes(or_operator_node)

        for leaf in leaves:
            assert leaf.get("clinicalCategory") == "biomarker"
            assert leaf.get("queryableStatus") == "fully_queryable"

        # Check concept groups are preserved
        egfr_leaves = [l for l in leaves if "EGFR" in l.get("atomicText", "")]
        for leaf in egfr_leaves:
            assert leaf.get("clinicalConceptGroup") == "egfr_activating_mutation"


class TestOperatorCollection:
    """Tests for collecting operators from expression trees."""

    def test_collect_simple_operators(self, and_operator_node):
        """Test collecting operators from simple AND tree."""
        operators = collect_operators(and_operator_node)
        assert operators == ["AND"]

    def test_collect_implication_operator(self, implication_operator_node):
        """Test collecting IMPLICATION and nested operators."""
        operators = collect_operators(implication_operator_node)
        assert "IMPLICATION" in operators
        assert "OR" in operators  # condition branch
        assert "AND" in operators  # requirement branch

    def test_collect_temporal_operator(self, temporal_node):
        """Test collecting TEMPORAL pseudo-operator."""
        operators = collect_operators(temporal_node)
        assert "TEMPORAL" in operators

    def test_collect_nested_operators(self, nested_complex_tree):
        """Test collecting operators from complex nested tree."""
        operators = collect_operators(nested_complex_tree)
        assert "AND" in operators  # root
        assert "OR" in operators  # biomarker branch
        assert "IMPLICATION" in operators  # implication branch


class TestImplicationOperator:
    """Tests specific to IMPLICATION operator handling."""

    def test_implication_structure_valid(self, implication_operator_node):
        """Test that IMPLICATION node has correct structure."""
        assert implication_operator_node.get("operator") == "IMPLICATION"
        assert "condition" in implication_operator_node
        assert "requirement" in implication_operator_node
        # IMPLICATION should NOT have operands
        assert "operands" not in implication_operator_node or not implication_operator_node.get("operands")

    def test_implication_condition_branch(self, implication_operator_node):
        """Test IMPLICATION condition branch is processed."""
        condition = implication_operator_node.get("condition")
        assert condition is not None
        assert condition.get("nodeType") == "operator"
        assert condition.get("operator") == "OR"

        condition_atomics = count_atomics_in_tree(condition)
        assert condition_atomics == 2

    def test_implication_requirement_branch(self, implication_operator_node):
        """Test IMPLICATION requirement branch is processed."""
        requirement = implication_operator_node.get("requirement")
        assert requirement is not None
        assert requirement.get("nodeType") == "operator"
        assert requirement.get("operator") == "AND"

        requirement_atomics = count_atomics_in_tree(requirement)
        assert requirement_atomics == 2

    def test_implication_missing_condition(self):
        """Test handling of IMPLICATION with missing condition."""
        invalid_node = {
            "nodeId": "root",
            "nodeType": "operator",
            "operator": "IMPLICATION",
            "requirement": {
                "nodeId": "req",
                "nodeType": "atomic",
                "atomicText": "Some requirement",
            },
            # Missing condition
        }

        # Should still count atomics in requirement
        count = count_atomics_in_tree(invalid_node)
        assert count == 1

    def test_implication_missing_requirement(self):
        """Test handling of IMPLICATION with missing requirement."""
        invalid_node = {
            "nodeId": "root",
            "nodeType": "operator",
            "operator": "IMPLICATION",
            "condition": {
                "nodeId": "cond",
                "nodeType": "atomic",
                "atomicText": "Some condition",
            },
            # Missing requirement
        }

        # Should still count atomics in condition
        count = count_atomics_in_tree(invalid_node)
        assert count == 1

    def test_implication_empty_branches(self):
        """Test handling of IMPLICATION with empty branches."""
        invalid_node = {
            "nodeId": "root",
            "nodeType": "operator",
            "operator": "IMPLICATION",
            "condition": {},
            "requirement": {},
        }

        count = count_atomics_in_tree(invalid_node)
        assert count == 0


class TestClinicalMetadataPreservation:
    """Tests for clinical metadata preservation through expression tree processing."""

    def test_clinical_category_preserved(self, or_operator_node):
        """Test clinicalCategory is preserved in leaf nodes."""
        leaves = collect_leaf_nodes(or_operator_node)
        for leaf in leaves:
            assert "clinicalCategory" in leaf
            assert leaf["clinicalCategory"] == "biomarker"

    def test_queryable_status_preserved(self, and_operator_node):
        """Test queryableStatus is preserved in leaf nodes."""
        leaves = collect_leaf_nodes(and_operator_node)
        statuses = [leaf.get("queryableStatus") for leaf in leaves]
        assert "fully_queryable" in statuses
        assert "partially_queryable" in statuses

    def test_concept_group_preserved(self, or_operator_node):
        """Test clinicalConceptGroup is preserved in leaf nodes."""
        leaves = collect_leaf_nodes(or_operator_node)
        groups = [leaf.get("clinicalConceptGroup") for leaf in leaves]
        assert "egfr_activating_mutation" in groups
        assert "alk_positive" in groups

    def test_screening_only_status_preserved(self, temporal_node):
        """Test screening_only status is preserved in temporal nodes."""
        leaves = collect_leaf_nodes(temporal_node)
        assert len(leaves) == 1
        assert leaves[0].get("queryableStatus") == "screening_only"


class TestEdgeCases:
    """Tests for edge cases in expression tree handling."""

    def test_empty_operands_list(self):
        """Test AND operator with empty operands list."""
        node = {
            "nodeId": "root",
            "nodeType": "operator",
            "operator": "AND",
            "operands": [],
        }
        count = count_atomics_in_tree(node)
        assert count == 0

    def test_missing_node_type(self):
        """Test node with missing nodeType."""
        node = {
            "nodeId": "1",
            "atomicText": "Some text",
        }
        count = count_atomics_in_tree(node)
        assert count == 0

    def test_unknown_operator(self):
        """Test handling of unknown operator type."""
        node = {
            "nodeId": "root",
            "nodeType": "operator",
            "operator": "XOR",  # Unknown operator
            "operands": [
                {"nodeId": "1", "nodeType": "atomic", "atomicText": "A"},
                {"nodeId": "2", "nodeType": "atomic", "atomicText": "B"},
            ],
        }
        # Should still count atomics in operands
        count = count_atomics_in_tree(node)
        assert count == 2

    def test_deeply_nested_tree(self):
        """Test deeply nested expression tree (5 levels)."""
        node = {
            "nodeId": "L1",
            "nodeType": "operator",
            "operator": "AND",
            "operands": [{
                "nodeId": "L2",
                "nodeType": "operator",
                "operator": "OR",
                "operands": [{
                    "nodeId": "L3",
                    "nodeType": "operator",
                    "operator": "AND",
                    "operands": [{
                        "nodeId": "L4",
                        "nodeType": "operator",
                        "operator": "NOT",
                        "operands": [{
                            "nodeId": "L5",
                            "nodeType": "atomic",
                            "atomicText": "Deep atomic",
                        }],
                    }],
                }],
            }],
        }
        count = count_atomics_in_tree(node)
        assert count == 1

        leaves = collect_leaf_nodes(node)
        assert len(leaves) == 1
        assert leaves[0].get("nodeId") == "L5"

    def test_temporal_with_nested_operator(self):
        """Test temporal node containing nested operator structure."""
        node = {
            "nodeId": "root",
            "nodeType": "temporal",
            "temporalConstraint": {
                "direction": "within",
                "durationValue": 7,
                "durationUnit": "days",
            },
            "operand": {
                "nodeId": "nested_op",
                "nodeType": "operator",
                "operator": "OR",
                "operands": [
                    {"nodeId": "1", "nodeType": "atomic", "atomicText": "Test A"},
                    {"nodeId": "2", "nodeType": "atomic", "atomicText": "Test B"},
                ],
            },
        }
        count = count_atomics_in_tree(node)
        assert count == 2


class TestAtomicCountValidation:
    """Tests for atomic count reconciliation validation logic."""

    def test_count_matches(self, nested_complex_tree):
        """Test that expected and actual counts match."""
        expected = 5  # Known from tree structure
        actual = count_atomics_in_tree(nested_complex_tree)
        leaves = collect_leaf_nodes(nested_complex_tree)

        assert actual == expected
        assert len(leaves) == expected

    def test_implication_count_consistency(self, implication_operator_node):
        """Test IMPLICATION atomic count is consistent between methods."""
        count_method = count_atomics_in_tree(implication_operator_node)
        leaves_method = len(collect_leaf_nodes(implication_operator_node))

        assert count_method == leaves_method == 4

    def test_count_after_tree_modification(self, and_operator_node):
        """Test count updates correctly after tree modification."""
        initial_count = count_atomics_in_tree(and_operator_node)
        assert initial_count == 2

        # Add a new atomic
        and_operator_node["operands"].append({
            "nodeId": "3",
            "nodeType": "atomic",
            "atomicText": "New atomic",
        })

        new_count = count_atomics_in_tree(and_operator_node)
        assert new_count == 3


# =============================================================================
# INTEGRATION TESTS WITH VALIDATION CONTRACTS
# =============================================================================

class TestValidationContractsIntegration:
    """Integration tests with validation contracts module.

    These tests are marked to skip if the validation_contracts module
    is not importable (e.g., when running tests in isolation).
    """

    @pytest.fixture
    def validation_contracts(self):
        """Try to import validation contracts module."""
        try:
            import sys
            # Add parent paths if needed
            from pathlib import Path
            module_path = Path(__file__).parent.parent.parent / "services"
            if str(module_path) not in sys.path:
                sys.path.insert(0, str(module_path.parent))

            from eligibility_analyzer.services.validation_contracts import (
                validate_stage2_output,
                validate_stage_consistency,
            )
            return {
                "validate_stage2_output": validate_stage2_output,
                "validate_stage_consistency": validate_stage_consistency,
            }
        except ImportError:
            return None

    def test_stage2_validation_with_implication(self, implication_operator_node, validation_contracts):
        """Test Stage 2 validation accepts IMPLICATION trees."""
        if validation_contracts is None:
            pytest.skip("validation_contracts module not available")

        validate_stage2_output = validation_contracts["validate_stage2_output"]

        stage2_result = {
            "decomposedCriteria": [
                {
                    "criterionId": "INC_1",
                    "originalText": "If EGFR/ALK+, must have progressed on prior TKI",
                    "expression": implication_operator_node,
                }
            ]
        }

        result = validate_stage2_output(stage2_result)
        assert result.is_valid, f"Validation errors: {result.errors}"

    def test_stage2_validation_catches_missing_node_type(self, validation_contracts):
        """Test Stage 2 validation catches nodes with missing nodeType."""
        if validation_contracts is None:
            pytest.skip("validation_contracts module not available")

        validate_stage2_output = validation_contracts["validate_stage2_output"]

        invalid_tree = {
            "nodeId": "1",
            # Missing nodeType
            "atomicText": "Some text",
        }

        stage2_result = {
            "decomposedCriteria": [
                {
                    "criterionId": "INC_1",
                    "originalText": "Test",
                    "expression": invalid_tree,
                }
            ]
        }

        result = validate_stage2_output(stage2_result)
        assert not result.is_valid or len(result.warnings) > 0

    def test_cross_stage_atomic_count_validation(self, nested_complex_tree, validation_contracts):
        """Test cross-stage atomic count validation."""
        if validation_contracts is None:
            pytest.skip("validation_contracts module not available")

        validate_stage_consistency = validation_contracts["validate_stage_consistency"]

        # Expected: 5 atomics
        stage2_result = {
            "decomposedCriteria": [
                {
                    "criterionId": "INC_1",
                    "originalText": "Complex criterion",
                    "expression": nested_complex_tree,
                }
            ]
        }

        # Simulate funnel output with correct count
        funnel_output = {
            "atomicCriteria": [
                {"atomicId": f"A{i}", "originalCriterionId": "INC_1", "text": f"Atomic {i}"}
                for i in range(1, 6)  # 5 atomics
            ]
        }

        # Simulate QEB output
        qeb_output = {
            "queryableBlocks": [
                {
                    "qebId": "QEB_INC_1",
                    "originalCriterionId": "INC_1",
                    "atomicIds": ["A1", "A2", "A3", "A4", "A5"],
                    "atomicCount": 5,
                }
            ],
            "funnelStages": [],
        }

        result = validate_stage_consistency(stage2_result, funnel_output, qeb_output)
        # Should pass since counts match
        assert result.is_valid or len(result.errors) == 0
