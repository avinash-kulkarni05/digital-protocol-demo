"""
Unit Tests for SOA Interpretation Pipeline - Phase 2 (Stages 2-3)

Tests for:
- Stage 2: Activity Component Expansion
- Stage 3: Activity Hierarchy Building

Run with: python -m pytest soa_analyzer/tests/test_interpretation_phase2.py -v
"""

import json
import pytest
from pathlib import Path

# Import Stage 2 components
from soa_analyzer.interpretation.stage2_activity_expansion import (
    ActivityExpander,
    ExpansionConfig,
    Stage2Result,
    expand_activities,
)

# Import Stage 3 components
from soa_analyzer.interpretation.stage3_hierarchy_builder import (
    HierarchyBuilder,
    HierarchyConfig,
    Stage3Result,
    build_hierarchy,
    DOMAIN_INFO,
)

# Import models
from soa_analyzer.models.expansion_proposal import (
    ActivityComponent,
    ActivityExpansion,
    ActivityHierarchy,
    ActivityHierarchyNode,
    ExpansionType,
)


# ============================================================================
# Test Data
# ============================================================================

SAMPLE_ACTIVITIES = [
    {
        "id": "ACT-001",
        "name": "Hematology",
        "category": "LABORATORY",
        "cdashDomain": "LB",
    },
    {
        "id": "ACT-002",
        "name": "Clinical Chemistry",
        "category": "LABORATORY",
        "cdashDomain": "LB",
    },
    {
        "id": "ACT-003",
        "name": "Vital Signs",
        "category": "VITAL_SIGNS",
        "cdashDomain": "VS",
    },
    {
        "id": "ACT-004",
        "name": "12-Lead ECG",
        "category": "ECG",
        "cdashDomain": "EG",
    },
    {
        "id": "ACT-005",
        "name": "Serum Pregnancy Test",
        "category": "LABORATORY",
        "cdashDomain": "LB",
    },
    {
        "id": "ACT-006",
        "name": "CT/MRI chest",
        "category": "IMAGING",
        "cdashDomain": "MI",
    },
    {
        "id": "ACT-007",
        "name": "EORTC-QLQ-C30",
        "category": "QUESTIONNAIRE",
        "cdashDomain": "QS",
    },
    {
        "id": "ACT-HEADER",
        "name": "LABORATORY TESTS",
        "category": "LABORATORY",
        "cdashDomain": "LB",
    },
]

SAMPLE_USDM_OUTPUT = {
    "studyVersion": [
        {
            "activities": SAMPLE_ACTIVITIES,
        }
    ]
}


# ============================================================================
# Stage 2 Tests: Activity Component Expansion
# ============================================================================

class TestActivityExpander:
    """Tests for ActivityExpander class."""

    def test_expander_initialization(self):
        """Test that expander initializes correctly."""
        expander = ActivityExpander()
        assert expander is not None
        assert expander.config is not None
        assert len(expander._alias_index) > 0  # Should have loaded aliases

    def test_normalize_activity_name(self):
        """Test activity name normalization."""
        expander = ActivityExpander()
        assert expander._normalize_activity_name("Hematology") == "hematology"
        assert expander._normalize_activity_name("  CLINICAL CHEMISTRY  ") == "clinical chemistry"
        assert expander._normalize_activity_name("12-Lead ECG") == "12lead ecg"

    def test_find_library_match_exact(self):
        """Test exact matching against component library."""
        expander = ActivityExpander()

        # Exact match for hematology
        match = expander._find_library_match("hematology")
        assert match is not None
        panel_key, panel_data, confidence = match
        assert "hematology" in panel_key or "components" in panel_data
        assert confidence >= 0.95

    def test_find_library_match_alias(self):
        """Test alias matching."""
        expander = ActivityExpander()

        # Match via alias
        match = expander._find_library_match("CBC")
        assert match is not None
        panel_key, panel_data, confidence = match
        assert confidence >= 0.90

    def test_find_library_match_no_match(self):
        """Test no match for unknown activity."""
        expander = ActivityExpander()

        match = expander._find_library_match("Unknown Activity XYZ")
        assert match is None

    def test_should_expand_lab_activity(self):
        """Test that lab activities should be expanded."""
        expander = ActivityExpander()

        activity = {"name": "Hematology", "cdashDomain": "LB"}
        assert expander._should_expand(activity) is True

    def test_should_not_expand_imaging(self):
        """Test that imaging activities should NOT be expanded."""
        expander = ActivityExpander()

        activity = {"name": "CT Scan", "cdashDomain": "MI"}
        assert expander._should_expand(activity) is False

    def test_expand_hematology(self):
        """Test expansion of Hematology activity."""
        expander = ActivityExpander()
        config = ExpansionConfig(use_llm_fallback=False)
        expander.config = config

        usdm = {"activities": [{"id": "ACT-001", "name": "Hematology", "cdashDomain": "LB"}]}
        result = expander.expand_activities(usdm)

        assert result.activities_processed == 1
        assert result.activities_expanded == 1
        assert result.library_matches == 1
        assert len(result.expansions) == 1

        expansion = result.expansions[0]
        assert expansion.parent_activity_id == "ACT-001"
        assert len(expansion.components) >= 5  # CBC has at least 5 components

        # Check component details
        component_names = [c.name for c in expansion.components]
        assert any("Blood" in name or "Hemoglobin" in name for name in component_names)

    def test_expand_vital_signs(self):
        """Test expansion of Vital Signs activity."""
        expander = ActivityExpander()
        config = ExpansionConfig(use_llm_fallback=False)
        expander.config = config

        usdm = {"activities": [{"id": "ACT-003", "name": "Vital Signs", "cdashDomain": "VS"}]}
        result = expander.expand_activities(usdm)

        assert result.activities_expanded == 1
        assert len(result.expansions) == 1

        expansion = result.expansions[0]
        component_names = [c.name for c in expansion.components]

        # Should have blood pressure, heart rate, etc.
        assert any("Blood Pressure" in name or "Heart Rate" in name for name in component_names)

    def test_skip_pregnancy_test(self):
        """Test that single tests like pregnancy test are not expanded."""
        expander = ActivityExpander()
        config = ExpansionConfig(use_llm_fallback=False)
        expander.config = config

        usdm = {"activities": [{"id": "ACT-005", "name": "Serum Pregnancy Test", "cdashDomain": "LB"}]}
        result = expander.expand_activities(usdm)

        # Should find a match but with single component
        if result.activities_expanded > 0:
            expansion = result.expansions[0]
            assert len(expansion.components) <= 1

    def test_apply_expansions_to_usdm(self):
        """Test applying expansions back to USDM."""
        expander = ActivityExpander()
        config = ExpansionConfig(use_llm_fallback=False)
        expander.config = config

        usdm = {"activities": [{"id": "ACT-001", "name": "Hematology", "cdashDomain": "LB"}]}
        result = expander.expand_activities(usdm)
        updated = expander.apply_expansions_to_usdm(usdm, result)

        # Check that expansion metadata was added
        activity = updated["activities"][0]
        assert "_expansion" in activity
        assert activity["_expansion"]["componentCount"] >= 5


class TestExpandActivitiesFunction:
    """Tests for expand_activities convenience function."""

    def test_expand_activities_basic(self):
        """Test basic expansion with convenience function."""
        config = ExpansionConfig(use_llm_fallback=False)
        usdm = {"activities": [{"id": "ACT-001", "name": "Hematology", "cdashDomain": "LB"}]}

        updated, result = expand_activities(usdm, config=config)

        assert result.activities_expanded >= 1
        assert "_expansion" in updated["activities"][0]


# ============================================================================
# Stage 3 Tests: Hierarchy Building
# ============================================================================

class TestHierarchyBuilder:
    """Tests for HierarchyBuilder class."""

    def test_builder_initialization(self):
        """Test that builder initializes correctly."""
        builder = HierarchyBuilder()
        assert builder is not None
        assert builder.config is not None

    def test_detect_header_rows(self):
        """Test detection of header rows."""
        builder = HierarchyBuilder()

        activities = [
            {"id": "ACT-HEADER", "name": "LABORATORY TESTS"},
            {"id": "ACT-001", "name": "Hematology"},
            {"id": "ACT-002", "name": "SAFETY ASSESSMENTS"},
        ]

        headers = builder._detect_header_rows(activities)

        assert "ACT-HEADER" in headers
        assert "ACT-002" in headers
        assert "ACT-001" not in headers

    def test_build_hierarchy_by_domain(self):
        """Test hierarchy building by domain."""
        builder = HierarchyBuilder()

        result = builder.build_hierarchy(SAMPLE_USDM_OUTPUT)

        assert result.activities_processed == len(SAMPLE_ACTIVITIES)
        assert result.categories_created > 0

        # Check that we have domain nodes
        domain_ids = [node.cdash_domain for node in result.hierarchy.root_nodes]
        assert "LB" in domain_ids
        assert "VS" in domain_ids
        assert "EG" in domain_ids

    def test_hierarchy_domain_counts(self):
        """Test that domain counts are correct."""
        builder = HierarchyBuilder()

        result = builder.build_hierarchy(SAMPLE_USDM_OUTPUT)

        # LB domain should have multiple activities (Hematology, Chemistry, Pregnancy)
        # But LABORATORY TESTS is a header, so 3 actual activities
        assert result.domain_counts.get("LB", 0) >= 2
        assert result.domain_counts.get("VS", 0) >= 1
        assert result.domain_counts.get("EG", 0) >= 1

    def test_hierarchy_sorting(self):
        """Test that hierarchy is sorted correctly."""
        builder = HierarchyBuilder()

        result = builder.build_hierarchy(SAMPLE_USDM_OUTPUT)
        result.hierarchy.sort_nodes()

        # Nodes should be sorted by order
        orders = [node.order for node in result.hierarchy.root_nodes]
        assert orders == sorted(orders)

    def test_header_rows_excluded(self):
        """Test that header rows are excluded from activity counts."""
        builder = HierarchyBuilder()

        result = builder.build_hierarchy(SAMPLE_USDM_OUTPUT)

        # Header row should be detected
        assert "ACT-HEADER" in result.header_rows

        # Header row should NOT be in any domain's activity list
        for node in result.hierarchy.root_nodes:
            assert "ACT-HEADER" not in node.activity_ids

    def test_apply_hierarchy_to_usdm(self):
        """Test applying hierarchy back to USDM."""
        builder = HierarchyBuilder()

        result = builder.build_hierarchy(SAMPLE_USDM_OUTPUT)
        updated = builder.apply_hierarchy_to_usdm(SAMPLE_USDM_OUTPUT.copy(), result)

        # Check that hierarchy was added
        assert "_activityHierarchy" in updated["studyVersion"][0]

        # Check that header row is marked
        activities = updated["studyVersion"][0]["activities"]
        header_activity = next((a for a in activities if a["id"] == "ACT-HEADER"), None)
        if header_activity:
            assert header_activity.get("_isHeaderRow", False) is True


class TestBuildHierarchyFunction:
    """Tests for build_hierarchy convenience function."""

    def test_build_hierarchy_basic(self):
        """Test basic hierarchy building with convenience function."""
        updated, result = build_hierarchy(SAMPLE_USDM_OUTPUT)

        assert result.categories_created > 0
        assert "_activityHierarchy" in updated["studyVersion"][0]


# ============================================================================
# Integration Tests: Stages 2-3 Together
# ============================================================================

class TestStages2And3Integration:
    """Integration tests for Stages 2 and 3 together."""

    def test_expansion_then_hierarchy(self):
        """Test running Stage 2 then Stage 3."""
        # Stage 2: Expand activities
        config2 = ExpansionConfig(use_llm_fallback=False)
        usdm, expansion_result = expand_activities(SAMPLE_USDM_OUTPUT, config=config2)

        # Stage 3: Build hierarchy
        usdm, hierarchy_result = build_hierarchy(usdm)

        # Both stages should have processed activities
        assert expansion_result.activities_processed > 0
        assert hierarchy_result.activities_processed > 0

        # Hierarchy should still work after expansions added
        assert hierarchy_result.categories_created > 0

    def test_full_pipeline_metadata(self):
        """Test that all metadata is preserved through stages."""
        # Run both stages
        config2 = ExpansionConfig(use_llm_fallback=False)
        usdm, _ = expand_activities(SAMPLE_USDM_OUTPUT, config=config2)
        usdm, _ = build_hierarchy(usdm)

        activities = usdm["studyVersion"][0]["activities"]

        # Find hematology (should have expansion)
        hematology = next((a for a in activities if a["name"] == "Hematology"), None)
        assert hematology is not None
        if "_expansion" in hematology:
            assert hematology["_expansion"]["componentCount"] >= 5

        # Check hierarchy exists
        assert "_activityHierarchy" in usdm["studyVersion"][0]


# ============================================================================
# Model Tests
# ============================================================================

class TestActivityComponent:
    """Tests for ActivityComponent model."""

    def test_component_creation(self):
        """Test creating an activity component."""
        comp = ActivityComponent(
            name="White Blood Cell Count",
            loinc_code="6690-2",
            unit="10*3/uL",
        )

        assert comp.name == "White Blood Cell Count"
        assert comp.loinc_code == "6690-2"
        assert comp.unit == "10*3/uL"
        assert comp.id.startswith("COMP-")

    def test_component_to_dict(self):
        """Test component to_dict method."""
        comp = ActivityComponent(
            name="Hemoglobin",
            loinc_code="718-7",
            unit="g/dL",
        )

        data = comp.to_dict()
        assert data["name"] == "Hemoglobin"
        assert data["loincCode"] == "718-7"
        assert data["unit"] == "g/dL"


class TestActivityHierarchy:
    """Tests for ActivityHierarchy model."""

    def test_hierarchy_creation(self):
        """Test creating a hierarchy."""
        hierarchy = ActivityHierarchy()
        assert hierarchy.id.startswith("HIER-")
        assert len(hierarchy.root_nodes) == 0

    def test_add_activity_to_domain(self):
        """Test adding activity to domain."""
        hierarchy = ActivityHierarchy()
        hierarchy.add_activity_to_domain("ACT-001", "Hematology", "LB")

        assert len(hierarchy.root_nodes) == 1
        assert hierarchy.root_nodes[0].cdash_domain == "LB"
        assert "ACT-001" in hierarchy.root_nodes[0].activity_ids

    def test_hierarchy_to_dict(self):
        """Test hierarchy to_dict method."""
        hierarchy = ActivityHierarchy()
        hierarchy.add_activity_to_domain("ACT-001", "Hematology", "LB")

        data = hierarchy.to_dict()
        assert "rootNodes" in data
        assert len(data["rootNodes"]) == 1


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
