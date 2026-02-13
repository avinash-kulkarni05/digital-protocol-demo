"""
Unit tests for feasibility data models.
"""

import pytest
from datetime import datetime

from ..data_models import (
    CriterionCategory,
    QueryableStatus,
    FunnelStageType,
    KeyCriterion,
    FunnelStage,
    FunnelResult,
    PopulationEstimate,
    OptimizationOpportunity,
)


class TestCriterionCategory:
    """Tests for CriterionCategory enum."""

    def test_all_categories_defined(self):
        """Verify all expected categories exist."""
        expected = [
            "PRIMARY_ANCHOR", "BIOMARKER", "TREATMENT_HISTORY",
            "FUNCTIONAL", "SAFETY_EXCLUSION", "ADMINISTRATIVE"
        ]
        actual = [c.name for c in CriterionCategory]
        assert set(expected) == set(actual)

    def test_category_values(self):
        """Test enum value strings."""
        assert CriterionCategory.PRIMARY_ANCHOR.value == "primary_anchor"
        assert CriterionCategory.BIOMARKER.value == "biomarker"


class TestQueryableStatus:
    """Tests for QueryableStatus enum."""

    def test_all_statuses_defined(self):
        """Verify all expected statuses exist."""
        expected = [
            "FULLY_QUERYABLE", "PARTIALLY_QUERYABLE",
            "NON_QUERYABLE", "REFERENCE_BASED"
        ]
        actual = [s.name for s in QueryableStatus]
        assert set(expected) == set(actual)


class TestKeyCriterion:
    """Tests for KeyCriterion dataclass."""

    def test_create_minimal(self):
        """Test creating KeyCriterion with minimal fields."""
        kc = KeyCriterion(
            key_id="KC001",
            original_criterion_ids=["C001"],
            category=CriterionCategory.PRIMARY_ANCHOR,
            normalized_text="Test criterion",
            criterion_type="inclusion",
            queryable_status=QueryableStatus.FULLY_QUERYABLE,
        )
        assert kc.key_id == "KC001"
        assert kc.category == CriterionCategory.PRIMARY_ANCHOR
        assert kc.estimated_elimination_rate == 0.0
        assert kc.omop_mappings == []

    def test_create_full(self):
        """Test creating KeyCriterion with all fields."""
        kc = KeyCriterion(
            key_id="KC001",
            original_criterion_ids=["C001", "C002"],
            category=CriterionCategory.BIOMARKER,
            normalized_text="EGFR mutation positive",
            criterion_type="inclusion",
            queryable_status=QueryableStatus.REFERENCE_BASED,
            estimated_elimination_rate=85.0,
            is_killer_criterion=True,
            funnel_priority=3,
        )
        assert kc.estimated_elimination_rate == 85.0
        assert kc.is_killer_criterion is True
        assert len(kc.original_criterion_ids) == 2


class TestFunnelStage:
    """Tests for FunnelStage dataclass."""

    def test_calculate_elimination_rate(self):
        """Test elimination rate calculation."""
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
        rate = stage.calculate_elimination_rate()
        assert rate == 50.0
        assert stage.elimination_rate == 50.0

    def test_zero_entering_population(self):
        """Test elimination rate with zero entering."""
        stage = FunnelStage(
            stage_name="Test Stage",
            stage_type=FunnelStageType.DEMOGRAPHICS,
            stage_order=2,
            criteria=[],
            patients_entering=0,
            patients_exiting=0,
        )
        rate = stage.calculate_elimination_rate()
        assert rate == 0.0


class TestFunnelResult:
    """Tests for FunnelResult dataclass."""

    @pytest.fixture
    def sample_result(self):
        """Create a sample FunnelResult for testing."""
        kc1 = KeyCriterion(
            key_id="KC001",
            original_criterion_ids=["C001"],
            category=CriterionCategory.PRIMARY_ANCHOR,
            normalized_text="NSCLC diagnosis",
            criterion_type="inclusion",
            queryable_status=QueryableStatus.FULLY_QUERYABLE,
            estimated_elimination_rate=95.0,
            is_killer_criterion=True,
            funnel_priority=1,
        )
        kc2 = KeyCriterion(
            key_id="KC002",
            original_criterion_ids=["C002"],
            category=CriterionCategory.BIOMARKER,
            normalized_text="EGFR mutation positive",
            criterion_type="inclusion",
            queryable_status=QueryableStatus.REFERENCE_BASED,
            estimated_elimination_rate=85.0,
            is_killer_criterion=True,
            funnel_priority=3,
        )

        stage1 = FunnelStage(
            stage_name="Disease Indication",
            stage_type=FunnelStageType.DISEASE_INDICATION,
            stage_order=1,
            criteria=[kc1],
            patients_entering=1000000,
            patients_exiting=50000,
        )
        stage1.calculate_elimination_rate()

        stage2 = FunnelStage(
            stage_name="Biomarker Requirements",
            stage_type=FunnelStageType.BIOMARKER_REQUIREMENTS,
            stage_order=2,
            criteria=[kc2],
            patients_entering=50000,
            patients_exiting=7500,
        )
        stage2.calculate_elimination_rate()

        return FunnelResult(
            protocol_id="NCT12345678",
            key_criteria=[kc1, kc2],
            stages=[stage1, stage2],
            initial_population=1000000,
            final_eligible_estimate=PopulationEstimate(
                count=7500,
                confidence_low=5000,
                confidence_high=10000,
                estimation_method="prevalence",
            ),
            killer_criteria=["KC001", "KC002"],
        )

    def test_overall_elimination_rate(self, sample_result):
        """Test overall elimination rate calculation."""
        rate = sample_result.get_overall_elimination_rate()
        # 1,000,000 -> 7,500 = 99.25% elimination
        assert rate == pytest.approx(99.25, rel=0.01)

    def test_funnel_efficiency_score(self, sample_result):
        """Test funnel efficiency score calculation."""
        score = sample_result.get_funnel_efficiency_score()
        # Both killer criteria are in early stages (1 and 2)
        # With 2 killer criteria, and both in first 3 stages
        assert score == 100.0

    def test_to_dict(self, sample_result):
        """Test JSON serialization."""
        data = sample_result.to_dict()
        assert data["protocolId"] == "NCT12345678"
        assert len(data["keyCriteria"]) == 2
        assert len(data["funnelStages"]) == 2
        assert data["populationEstimates"]["initialPopulation"] == 1000000
        assert data["populationEstimates"]["finalEligibleEstimate"] == 7500
        assert data["killerCriteria"] == ["KC001", "KC002"]

    def test_empty_result(self):
        """Test result with no criteria/stages."""
        result = FunnelResult(protocol_id="NCT00000000")
        assert result.get_overall_elimination_rate() == 0.0
        assert result.get_funnel_efficiency_score() == 0.0
        data = result.to_dict()
        assert data["protocolId"] == "NCT00000000"
        assert data["keyCriteria"] == []


class TestPopulationEstimate:
    """Tests for PopulationEstimate dataclass."""

    def test_create(self):
        """Test creating PopulationEstimate."""
        est = PopulationEstimate(
            count=1000,
            confidence_low=700,
            confidence_high=1300,
            estimation_method="prevalence",
            data_sources=["biomarker_frequencies.json"],
        )
        assert est.count == 1000
        assert est.confidence_low == 700
        assert est.confidence_high == 1300
