"""
Unit tests for feasibility validators.
"""

import pytest
from pathlib import Path

from ..validators import (
    validate_criteria_input,
    validate_funnel_result,
    validate_key_criterion,
    ValidationError,
)
from ..data_models import (
    CriterionCategory,
    QueryableStatus,
    KeyCriterion,
    FunnelStage,
    FunnelStageType,
    FunnelResult,
    PopulationEstimate,
)


class TestValidateCriteriaInput:
    """Tests for validate_criteria_input function."""

    def test_valid_input(self):
        """Test with valid criteria list."""
        criteria = [
            {"criterion_id": "C001", "text": "Test criterion", "criterion_type": "inclusion"},
            {"criterion_id": "C002", "text": "Another criterion", "criterion_type": "exclusion"},
        ]
        result = validate_criteria_input(criteria)
        assert len(result) == 2
        assert result[0]["criterion_id"] == "C001"
        assert result[1]["criterion_type"] == "exclusion"

    def test_none_input(self):
        """Test with None input."""
        with pytest.raises(ValidationError) as exc_info:
            validate_criteria_input(None)
        assert "cannot be None" in str(exc_info.value)

    def test_empty_list(self):
        """Test with empty list."""
        with pytest.raises(ValidationError) as exc_info:
            validate_criteria_input([])
        assert "cannot be empty" in str(exc_info.value)

    def test_non_list_input(self):
        """Test with non-list input."""
        with pytest.raises(ValidationError) as exc_info:
            validate_criteria_input("not a list")
        assert "must be a list" in str(exc_info.value)

    def test_non_dict_criterion(self):
        """Test with non-dict criterion."""
        with pytest.raises(ValidationError) as exc_info:
            validate_criteria_input(["not a dict"])
        assert "must be a dictionary" in str(exc_info.value)

    def test_missing_id_generates_one(self):
        """Test that missing ID is auto-generated."""
        criteria = [{"text": "Test criterion"}]
        result = validate_criteria_input(criteria)
        assert result[0]["criterion_id"] == "C001"

    def test_alternate_field_names(self):
        """Test with alternate field names."""
        criteria = [
            {"id": "C001", "criterionText": "Test", "type": "exclusion"},
        ]
        result = validate_criteria_input(criteria)
        assert result[0]["criterion_id"] == "C001"
        assert result[0]["text"] == "Test"
        assert result[0]["criterion_type"] == "exclusion"

    def test_invalid_criterion_type_defaults(self):
        """Test that invalid criterion type defaults to inclusion."""
        criteria = [
            {"criterion_id": "C001", "text": "Test", "criterion_type": "invalid"},
        ]
        result = validate_criteria_input(criteria)
        assert result[0]["criterion_type"] == "inclusion"


class TestValidateFunnelResult:
    """Tests for validate_funnel_result function."""

    @pytest.fixture
    def valid_result(self):
        """Create a valid FunnelResult."""
        kc = KeyCriterion(
            key_id="KC001",
            original_criterion_ids=["C001"],
            category=CriterionCategory.PRIMARY_ANCHOR,
            normalized_text="Test",
            criterion_type="inclusion",
            queryable_status=QueryableStatus.FULLY_QUERYABLE,
        )
        stage = FunnelStage(
            stage_name="Test Stage",
            stage_type=FunnelStageType.DISEASE_INDICATION,
            stage_order=1,
            criteria=[kc],
            patients_entering=1000,
            patients_exiting=500,
        )
        return FunnelResult(
            protocol_id="NCT12345678",
            key_criteria=[kc],
            stages=[stage],
            initial_population=1000,
            final_eligible_estimate=PopulationEstimate(
                count=500,
                confidence_low=350,
                confidence_high=650,
                estimation_method="prevalence",
            ),
            killer_criteria=["KC001"],
        )

    def test_valid_result(self, valid_result):
        """Test with valid result."""
        is_valid, warnings = validate_funnel_result(valid_result)
        assert is_valid is True
        assert len(warnings) == 0

    def test_missing_protocol_id(self):
        """Test with missing protocol_id."""
        result = FunnelResult(protocol_id="")
        is_valid, warnings = validate_funnel_result(result)
        assert "Missing protocol_id" in warnings

    def test_no_key_criteria(self):
        """Test with no key criteria."""
        result = FunnelResult(protocol_id="NCT12345678")
        is_valid, warnings = validate_funnel_result(result)
        assert "No key criteria generated" in warnings

    def test_negative_population(self):
        """Test with negative initial population."""
        result = FunnelResult(
            protocol_id="NCT12345678",
            initial_population=-100,
        )
        is_valid, warnings = validate_funnel_result(result)
        assert any("must be positive" in w for w in warnings)

    def test_invalid_killer_criterion_reference(self, valid_result):
        """Test with killer criterion not in key criteria."""
        valid_result.killer_criteria.append("KC999")
        is_valid, warnings = validate_funnel_result(valid_result)
        assert any("KC999 not in key criteria" in w for w in warnings)


class TestValidateKeyCriterion:
    """Tests for validate_key_criterion function."""

    def test_valid_criterion(self):
        """Test with valid criterion."""
        kc = KeyCriterion(
            key_id="KC001",
            original_criterion_ids=["C001"],
            category=CriterionCategory.BIOMARKER,
            normalized_text="EGFR mutation positive",
            criterion_type="inclusion",
            queryable_status=QueryableStatus.REFERENCE_BASED,
            estimated_elimination_rate=85.0,
            funnel_priority=3,
        )
        issues = validate_key_criterion(kc)
        assert len(issues) == 0

    def test_missing_key_id(self):
        """Test with missing key_id."""
        kc = KeyCriterion(
            key_id="",
            original_criterion_ids=["C001"],
            category=CriterionCategory.BIOMARKER,
            normalized_text="Test",
            criterion_type="inclusion",
            queryable_status=QueryableStatus.FULLY_QUERYABLE,
        )
        issues = validate_key_criterion(kc)
        assert any("Missing key_id" in i for i in issues)

    def test_invalid_elimination_rate(self):
        """Test with out-of-range elimination rate."""
        kc = KeyCriterion(
            key_id="KC001",
            original_criterion_ids=["C001"],
            category=CriterionCategory.BIOMARKER,
            normalized_text="Test",
            criterion_type="inclusion",
            queryable_status=QueryableStatus.FULLY_QUERYABLE,
            estimated_elimination_rate=150.0,
        )
        issues = validate_key_criterion(kc)
        assert any("out of range" in i for i in issues)

    def test_negative_funnel_priority(self):
        """Test with negative funnel priority."""
        kc = KeyCriterion(
            key_id="KC001",
            original_criterion_ids=["C001"],
            category=CriterionCategory.BIOMARKER,
            normalized_text="Test",
            criterion_type="inclusion",
            queryable_status=QueryableStatus.FULLY_QUERYABLE,
            funnel_priority=-1,
        )
        issues = validate_key_criterion(kc)
        assert any("cannot be negative" in i for i in issues)
