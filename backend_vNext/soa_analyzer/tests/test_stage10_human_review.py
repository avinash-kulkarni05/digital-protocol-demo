"""
Unit tests for Stage 10: Human Review Assembly.

Tests the HumanReviewAssembler that aggregates review items from all pipeline stages
into an API-ready structure for React/Vue UI.
"""

import pytest
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from soa_analyzer.models.human_review import (
    ReviewItemType,
    ReviewPriority,
    ReviewAction,
    ReviewOption,
    ProvenanceDisplay,
    ReasoningDisplay,
    UnifiedReviewItem,
    StageReviewSection,
    HumanReviewPackage,
    ReviewDecisionRequest,
    BatchReviewRequest,
    Stage10Config,
    Stage10Result,
)
from soa_analyzer.interpretation.stage10_human_review import (
    HumanReviewAssembler,
    assemble_review_package,
)


# =============================================================================
# Mock Stage Result Classes (to simulate actual stage results)
# =============================================================================

@dataclass
class MockReviewItem:
    """Mock review item from stage results."""
    id: str = ""
    title: str = ""
    description: str = ""
    source_entity_id: str = ""
    source_entity_type: str = "activity"
    source_entity_name: str = ""
    options: List[Any] = field(default_factory=list)
    confidence: float = 0.0
    rationale: str = ""
    priority: str = "medium"
    provenance: Optional[Dict] = None


@dataclass
class MockStageResult:
    """Mock stage result with review_items attribute."""
    review_items: List[MockReviewItem] = field(default_factory=list)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_mock_review_item() -> MockReviewItem:
    """Create a sample mock review item."""
    return MockReviewItem(
        id="REV-ACT-001",
        title="Blood Collection Expansion",
        description="Review activity expansion for Blood Collection",
        source_entity_id="ACT-001",
        source_entity_type="activity",
        source_entity_name="Blood Collection",
        options=[
            {"id": "OPT-1", "label": "Expand to CBC, CMP, Lipid Panel", "confidence": 0.85},
            {"id": "OPT-2", "label": "Keep as single activity", "confidence": 0.15},
        ],
        confidence=0.85,
        rationale="Multiple lab panels detected in footnotes",
        priority="high",
    )


@pytest.fixture
def sample_stage4_result() -> MockStageResult:
    """Create a mock Stage4Result with alternative review items."""
    return MockStageResult(
        review_items=[
            MockReviewItem(
                id="ALT-001",
                title="Imaging Modality Selection",
                description="Select imaging modality for tumor assessment",
                source_entity_id="ACT-IMAGING-001",
                source_entity_type="activity",
                source_entity_name="Tumor Assessment",
                options=[
                    {"id": "OPT-CT", "label": "CT Scan", "confidence": 0.85, "is_recommended": True},
                    {"id": "OPT-MRI", "label": "MRI", "confidence": 0.65},
                ],
                confidence=0.75,
                rationale="CT mentioned more frequently",
                provenance={"page_numbers": [45, 46], "text_snippets": ["Tumor assessments using CT or MRI"]},
            ),
        ],
    )


@pytest.fixture
def sample_stage7_result() -> MockStageResult:
    """Create a mock Stage7Result with timing review items."""
    return MockStageResult(
        review_items=[
            MockReviewItem(
                id="TIM-001",
                title="PK Timing Expansion",
                description="Expand PK sample timing",
                source_entity_id="ACT-PK-001",
                source_entity_type="activity",
                source_entity_name="PK Sample Collection",
                options=[
                    {"id": "OPT-PRE", "label": "Pre-dose", "confidence": 0.92},
                    {"id": "OPT-1H", "label": "1h Post-dose", "confidence": 0.88},
                ],
                confidence=0.92,
                rationale="Standard PK sampling schedule detected",
            ),
        ],
    )


@pytest.fixture
def sample_stage8_result() -> MockStageResult:
    """Create a mock Stage8Result with cycle review items."""
    return MockStageResult(
        review_items=[
            MockReviewItem(
                id="CYC-001",
                title="Cycle Count Decision",
                description="Determine number of treatment cycles",
                source_entity_id="ENC-C1D1",
                source_entity_type="encounter",
                source_entity_name="Cycle 1 Day 1",
                options=[
                    {"id": "OPT-8", "label": "8 cycles", "confidence": 0.88},
                    {"id": "OPT-6", "label": "6 cycles", "confidence": 0.12},
                ],
                confidence=0.88,
                rationale="8 cycles of Q3W treatment detected",
            ),
        ],
    )


@pytest.fixture
def sample_stage_results(
    sample_stage4_result,
    sample_stage7_result,
    sample_stage8_result,
) -> Dict[int, Any]:
    """Create combined stage results for full assembly test."""
    return {
        4: sample_stage4_result,
        7: sample_stage7_result,
        8: sample_stage8_result,
    }


@pytest.fixture
def assembler() -> HumanReviewAssembler:
    """Create a HumanReviewAssembler instance."""
    return HumanReviewAssembler()


# =============================================================================
# Data Model Tests
# =============================================================================

class TestReviewEnums:
    """Test enum definitions."""

    def test_review_item_type_values(self):
        """Verify all expected item types exist."""
        assert ReviewItemType.DOMAIN_MAPPING == "domain_mapping"
        assert ReviewItemType.ACTIVITY_EXPANSION == "activity_expansion"
        assert ReviewItemType.ALTERNATIVE_CHOICE == "alternative_choice"
        assert ReviewItemType.TIMING_EXPANSION == "timing_expansion"
        assert ReviewItemType.CYCLE_COUNT == "cycle_count"

    def test_review_priority_values(self):
        """Verify priority levels."""
        assert ReviewPriority.CRITICAL == "critical"
        assert ReviewPriority.HIGH == "high"
        assert ReviewPriority.MEDIUM == "medium"
        assert ReviewPriority.LOW == "low"

    def test_review_action_values(self):
        """Verify action states."""
        assert ReviewAction.PENDING == "pending"
        assert ReviewAction.APPROVED == "approved"
        assert ReviewAction.REJECTED == "rejected"
        assert ReviewAction.MODIFIED == "modified"
        assert ReviewAction.DEFERRED == "deferred"


class TestReviewOption:
    """Test ReviewOption dataclass."""

    def test_basic_creation(self):
        """Test creating a review option."""
        option = ReviewOption(
            id="OPT-001",
            label="Option A",
            description="First option",
            is_default=True,
            confidence=0.85,
        )
        assert option.id == "OPT-001"
        assert option.is_default is True
        assert option.confidence == 0.85

    def test_to_api(self):
        """Test API serialization."""
        option = ReviewOption(
            id="OPT-001",
            label="Option A",
            description="First option",
            is_recommended=True,
            confidence=0.90,
        )
        api = option.to_api()
        assert api["id"] == "OPT-001"
        assert api["isRecommended"] is True
        assert api["confidence"] == 0.90

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "id": "OPT-001",
            "label": "Option A",
            "description": "First option",
            "isRecommended": True,
            "confidence": 0.90,
        }
        option = ReviewOption.from_dict(data)
        assert option.id == "OPT-001"
        assert option.is_recommended is True


class TestProvenanceDisplay:
    """Test ProvenanceDisplay dataclass."""

    def test_basic_creation(self):
        """Test creating provenance display."""
        prov = ProvenanceDisplay(
            page_numbers=[45, 46, 47],
            text_snippets=["First snippet", "Second snippet"],
            source_table="Schedule of Assessments Table 1",
        )
        assert prov.page_numbers == [45, 46, 47]
        assert len(prov.text_snippets) == 2
        assert prov.source_table is not None

    def test_to_api(self):
        """Test API serialization."""
        prov = ProvenanceDisplay(
            page_numbers=[45],
            text_snippets=["Test snippet"],
            cell_coordinates={"row": 5, "col": 3},
        )
        api = prov.to_api()
        assert api["pageNumbers"] == [45]
        assert api["cellCoordinates"] == {"row": 5, "col": 3}

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "pageNumbers": [45, 46],
            "textSnippets": ["snippet 1"],
            "sourceTable": "Table 1",
        }
        prov = ProvenanceDisplay.from_dict(data)
        assert prov.page_numbers == [45, 46]
        assert prov.source_table == "Table 1"


class TestReasoningDisplay:
    """Test ReasoningDisplay dataclass."""

    def test_basic_creation(self):
        """Test creating reasoning display."""
        reasoning = ReasoningDisplay(
            rationale="CT scans mentioned more frequently in protocol",
            decision_factors=["CT mentioned 5x", "MRI mentioned 2x"],
            confidence_breakdown={"frequency": 0.8, "context": 0.7},
        )
        assert "CT" in reasoning.rationale
        assert len(reasoning.decision_factors) == 2

    def test_to_api(self):
        """Test API serialization."""
        reasoning = ReasoningDisplay(
            rationale="Test rationale",
            decision_factors=["Factor 1"],
            confidence_breakdown={"accuracy": 0.9},
            model_used="gemini-2.0-flash",
        )
        api = reasoning.to_api()
        assert api["rationale"] == "Test rationale"
        assert api["decisionFactors"] == ["Factor 1"]
        assert api["modelUsed"] == "gemini-2.0-flash"


class TestUnifiedReviewItem:
    """Test UnifiedReviewItem dataclass."""

    def test_basic_creation(self):
        """Test creating a unified review item."""
        item = UnifiedReviewItem(
            id="REV-001",
            stage=4,
            stage_name="Alternative Resolution",
            item_type=ReviewItemType.ALTERNATIVE_CHOICE,
            title="Imaging Modality Selection",
            description="Select imaging modality for tumor assessment",
            priority=ReviewPriority.CRITICAL,
            source_entity_id="ACT-001",
            source_entity_type="activity",
            source_entity_name="Tumor Assessment",
            options=[
                ReviewOption(id="OPT-CT", label="CT", description="CT Scan"),
                ReviewOption(id="OPT-MRI", label="MRI", description="MRI Scan"),
            ],
            confidence=0.75,
        )
        assert item.stage == 4
        assert item.priority == ReviewPriority.CRITICAL
        assert len(item.options) == 2

    def test_to_api_camelcase(self):
        """Test API serialization uses camelCase."""
        item = UnifiedReviewItem(
            id="REV-001",
            stage=4,
            stage_name="Alternative Resolution",
            item_type=ReviewItemType.ALTERNATIVE_CHOICE,
            title="Test Item",
            description="Test description",
            priority=ReviewPriority.HIGH,
            source_entity_id="ACT-001",
            source_entity_type="activity",
            source_entity_name="Test Activity",
            options=[],
            allows_custom_value=True,
            auto_apply_threshold=0.95,
        )
        api = item.to_api()
        # Check camelCase keys
        assert "stageName" in api
        assert "itemType" in api
        assert "allowsCustomValue" in api
        # sourceEntity is nested
        assert "sourceEntity" in api
        assert api["sourceEntity"]["id"] == "ACT-001"
        assert api["sourceEntity"]["type"] == "activity"
        assert api["sourceEntity"]["name"] == "Test Activity"

    def test_can_auto_apply(self):
        """Test auto-apply property logic."""
        item = UnifiedReviewItem(
            id="REV-001",
            stage=4,
            stage_name="Test",
            item_type=ReviewItemType.ALTERNATIVE_CHOICE,
            title="Test",
            description="Test",
            priority=ReviewPriority.MEDIUM,
            source_entity_id="ACT-001",
            source_entity_type="activity",
            source_entity_name="Test",
            options=[],
            confidence=0.96,
            auto_apply_threshold=0.90,
        )
        assert item.can_auto_apply is True

        item.confidence = 0.85
        assert item.can_auto_apply is False

    def test_is_resolved(self):
        """Test is_resolved property."""
        item = UnifiedReviewItem(
            id="REV-001",
            stage=4,
            stage_name="Test",
            item_type=ReviewItemType.ALTERNATIVE_CHOICE,
            title="Test",
            description="Test",
            priority=ReviewPriority.MEDIUM,
            source_entity_id="ACT-001",
            source_entity_type="activity",
            source_entity_name="Test",
            options=[],
        )
        assert item.is_resolved is False

        item.action = ReviewAction.APPROVED
        assert item.is_resolved is True


class TestStageReviewSection:
    """Test StageReviewSection dataclass."""

    def test_calculate_stats(self):
        """Test statistic calculation."""
        items = [
            UnifiedReviewItem(
                id=f"REV-{i}",
                stage=4,
                stage_name="Test",
                item_type=ReviewItemType.ALTERNATIVE_CHOICE,
                title=f"Item {i}",
                description="Test",
                priority=ReviewPriority.CRITICAL if i == 0 else ReviewPriority.HIGH,
                source_entity_id=f"ACT-{i}",
                source_entity_type="activity",
                source_entity_name=f"Activity {i}",
                options=[],
                action=ReviewAction.APPROVED if i == 2 else ReviewAction.PENDING,
            )
            for i in range(3)
        ]
        section = StageReviewSection(
            stage=4,
            stage_name="Alternative Resolution",
            description="Test section",
            items=items,
        )
        section.calculate_stats()
        assert section.total_items == 3
        assert section.pending_count == 2
        assert section.approved_count == 1
        assert section.critical_count == 1

    def test_to_api(self):
        """Test API serialization."""
        section = StageReviewSection(
            stage=4,
            stage_name="Alternative Resolution",
            description="Test section",
            items=[],
        )
        api = section.to_api()
        assert api["stage"] == 4
        assert api["stageName"] == "Alternative Resolution"
        # Stats are in "summary" sub-object
        assert api["summary"]["totalItems"] == 0


class TestHumanReviewPackage:
    """Test HumanReviewPackage dataclass."""

    def test_calculate_stats(self):
        """Test summary calculation."""
        section1 = StageReviewSection(
            stage=4,
            stage_name="Test 1",
            description="",
            items=[
                UnifiedReviewItem(
                    id="REV-1",
                    stage=4,
                    stage_name="Test 1",
                    item_type=ReviewItemType.ALTERNATIVE_CHOICE,
                    title="Test",
                    description="",
                    priority=ReviewPriority.CRITICAL,
                    source_entity_id="ACT-1",
                    source_entity_type="activity",
                    source_entity_name="Test",
                    options=[],
                ),
            ],
        )
        section1.calculate_stats()
        section2 = StageReviewSection(
            stage=7,
            stage_name="Test 2",
            description="",
            items=[
                UnifiedReviewItem(
                    id="REV-2",
                    stage=7,
                    stage_name="Test 2",
                    item_type=ReviewItemType.TIMING_EXPANSION,
                    title="Test",
                    description="",
                    priority=ReviewPriority.MEDIUM,
                    source_entity_id="ACT-2",
                    source_entity_type="activity",
                    source_entity_name="Test",
                    options=[],
                ),
            ],
        )
        section2.calculate_stats()
        package = HumanReviewPackage(
            id="PKG-001",
            protocol_id="NCT12345",
            protocol_name="Test Protocol",
            created_at=datetime.now().isoformat(),
            sections=[section1, section2],
        )
        package.calculate_stats()
        assert package.total_items == 2
        assert package.total_pending == 2
        assert package.can_generate_schedule is False  # Critical item pending

    def test_can_generate_when_no_critical(self):
        """Test schedule generation allowed when no critical pending."""
        section = StageReviewSection(
            stage=4,
            stage_name="Test",
            description="",
            items=[
                UnifiedReviewItem(
                    id="REV-1",
                    stage=4,
                    stage_name="Test",
                    item_type=ReviewItemType.ALTERNATIVE_CHOICE,
                    title="Test",
                    description="",
                    priority=ReviewPriority.MEDIUM,  # Not critical
                    source_entity_id="ACT-1",
                    source_entity_type="activity",
                    source_entity_name="Test",
                    options=[],
                ),
            ],
        )
        section.calculate_stats()
        package = HumanReviewPackage(
            id="PKG-001",
            protocol_id="NCT12345",
            protocol_name="Test Protocol",
            created_at=datetime.now().isoformat(),
            sections=[section],
        )
        package.calculate_stats()
        assert package.can_generate_schedule is True

    def test_get_item_by_id(self):
        """Test finding item by ID."""
        item = UnifiedReviewItem(
            id="REV-TARGET",
            stage=4,
            stage_name="Test",
            item_type=ReviewItemType.ALTERNATIVE_CHOICE,
            title="Target Item",
            description="",
            priority=ReviewPriority.MEDIUM,
            source_entity_id="ACT-1",
            source_entity_type="activity",
            source_entity_name="Test",
            options=[],
        )
        section = StageReviewSection(
            stage=4,
            stage_name="Test",
            description="",
            items=[item],
        )
        package = HumanReviewPackage(
            id="PKG-001",
            protocol_id="NCT12345",
            protocol_name="Test",
            created_at=datetime.now().isoformat(),
            sections=[section],
        )
        found = package.get_item_by_id("REV-TARGET")
        assert found is not None
        assert found.title == "Target Item"

        not_found = package.get_item_by_id("NON-EXISTENT")
        assert not_found is None


# =============================================================================
# Assembler Tests
# =============================================================================

class TestHumanReviewAssembler:
    """Test HumanReviewAssembler class."""

    def test_initialization(self, assembler):
        """Test assembler initializes correctly."""
        assert assembler is not None
        assert assembler.config is not None
        assert assembler._stage_info is not None

    def test_stage_info_loaded(self, assembler):
        """Test stage info is loaded from config."""
        assert 4 in assembler._stage_info
        assert assembler._stage_info[4]["name"] == "Alternative Resolution"

    def test_convert_mock_review_item(self, assembler, sample_mock_review_item):
        """Test converting mock review item to UnifiedReviewItem."""
        unified = assembler._convert_human_review_item(
            item=sample_mock_review_item,
            stage=2,
            item_type=ReviewItemType.ACTIVITY_EXPANSION,
        )
        assert unified is not None
        assert unified.id == "REV-ACT-001"
        assert unified.stage == 2
        assert unified.item_type == ReviewItemType.ACTIVITY_EXPANSION
        assert unified.confidence == 0.85

    def test_collect_stage4_items(self, assembler, sample_stage4_result):
        """Test collecting alternative resolution items."""
        items = assembler._collect_stage4_items(sample_stage4_result)
        assert len(items) == 1
        assert items[0].item_type == ReviewItemType.ALTERNATIVE_CHOICE
        assert items[0].stage == 4
        # Stage 4 items get CRITICAL priority
        assert items[0].priority == ReviewPriority.CRITICAL

    def test_collect_stage7_items(self, assembler, sample_stage7_result):
        """Test collecting timing distribution items."""
        items = assembler._collect_stage7_items(sample_stage7_result)
        assert len(items) == 1
        assert items[0].item_type == ReviewItemType.TIMING_EXPANSION
        assert items[0].stage == 7

    def test_collect_stage8_items(self, assembler, sample_stage8_result):
        """Test collecting cycle expansion items."""
        items = assembler._collect_stage8_items(sample_stage8_result)
        assert len(items) == 1
        assert items[0].item_type == ReviewItemType.CYCLE_COUNT
        assert items[0].stage == 8
        # Stage 8 items get CRITICAL priority
        assert items[0].priority == ReviewPriority.CRITICAL

    def test_build_section(self, assembler, sample_stage4_result):
        """Test building a stage section."""
        items = assembler._collect_stage4_items(sample_stage4_result)
        section = assembler._build_section(stage=4, items=items)
        assert section.stage == 4
        assert section.stage_name == "Alternative Resolution"
        assert section.total_items == 1

    def test_assemble_review_package(self, assembler, sample_stage_results):
        """Test full package assembly."""
        result = assembler.assemble_review_package(
            stage_results=sample_stage_results,
            protocol_id="NCT12345678",
            protocol_name="Test Phase 2 Study",
        )
        assert isinstance(result, Stage10Result)
        assert result.package is not None
        assert result.items_collected == 3
        assert 4 in result.items_by_stage
        assert 7 in result.items_by_stage
        assert 8 in result.items_by_stage

    def test_auto_approve_high_confidence(self, assembler):
        """Test auto-approval of high confidence items."""
        # Create item with very high confidence
        item = UnifiedReviewItem(
            id="REV-001",
            stage=7,
            stage_name="Timing Distribution",
            item_type=ReviewItemType.TIMING_EXPANSION,
            title="Test",
            description="Test",
            priority=ReviewPriority.HIGH,
            source_entity_id="ACT-001",
            source_entity_type="activity",
            source_entity_name="Test Activity",
            options=[
                ReviewOption(
                    id="OPT-001",
                    label="Option 1",
                    description="First option",
                    is_recommended=True,
                ),
            ],
            confidence=0.96,
            auto_apply_threshold=0.95,
        )
        section = StageReviewSection(
            stage=7,
            stage_name="Timing Distribution",
            description="Test",
            items=[item],
        )
        section.calculate_stats()
        package = HumanReviewPackage(
            id="PKG-001",
            protocol_id="NCT12345",
            protocol_name="Test",
            created_at=datetime.now().isoformat(),
            sections=[section],
        )
        package.calculate_stats()

        updated_package, count = assembler.auto_approve_high_confidence(
            package=package,
            threshold=0.95,
        )
        assert count == 1
        assert updated_package.sections[0].items[0].action == ReviewAction.APPROVED

    def test_apply_single_decision(self, assembler):
        """Test applying a single review decision."""
        item = UnifiedReviewItem(
            id="REV-001",
            stage=4,
            stage_name="Alternative Resolution",
            item_type=ReviewItemType.ALTERNATIVE_CHOICE,
            title="Test",
            description="Test",
            priority=ReviewPriority.CRITICAL,
            source_entity_id="ACT-001",
            source_entity_type="activity",
            source_entity_name="Test",
            options=[
                ReviewOption(id="OPT-A", label="A", description="Option A"),
                ReviewOption(id="OPT-B", label="B", description="Option B"),
            ],
        )
        section = StageReviewSection(
            stage=4,
            stage_name="Alternative Resolution",
            description="Test",
            items=[item],
        )
        section.calculate_stats()
        package = HumanReviewPackage(
            id="PKG-001",
            protocol_id="NCT12345",
            protocol_name="Test",
            created_at=datetime.now().isoformat(),
            sections=[section],
        )
        package.calculate_stats()

        decision = ReviewDecisionRequest(
            item_id="REV-001",
            action=ReviewAction.APPROVED,
            selected_option_id="OPT-A",
            reviewer_notes="Selected based on protocol language",
        )
        updated = assembler.apply_decisions(package, [decision])
        target_item = updated.sections[0].items[0]
        assert target_item.action == ReviewAction.APPROVED
        assert target_item.selected_option_id == "OPT-A"
        assert target_item.reviewer_notes == "Selected based on protocol language"

    def test_apply_batch_decisions(self, assembler):
        """Test applying batch review decisions."""
        items = [
            UnifiedReviewItem(
                id=f"REV-{i}",
                stage=4,
                stage_name="Test",
                item_type=ReviewItemType.ALTERNATIVE_CHOICE,
                title=f"Item {i}",
                description="Test",
                priority=ReviewPriority.HIGH,
                source_entity_id=f"ACT-{i}",
                source_entity_type="activity",
                source_entity_name=f"Activity {i}",
                options=[
                    ReviewOption(id="OPT-1", label="Option 1", description="First"),
                ],
            )
            for i in range(3)
        ]
        section = StageReviewSection(
            stage=4,
            stage_name="Test",
            description="Test",
            items=items,
        )
        section.calculate_stats()
        package = HumanReviewPackage(
            id="PKG-001",
            protocol_id="NCT12345",
            protocol_name="Test",
            created_at=datetime.now().isoformat(),
            sections=[section],
        )

        # BatchReviewRequest takes list of decisions
        batch = BatchReviewRequest(
            decisions=[
                ReviewDecisionRequest(item_id="REV-0", action=ReviewAction.APPROVED),
                ReviewDecisionRequest(item_id="REV-1", action=ReviewAction.APPROVED),
                ReviewDecisionRequest(item_id="REV-2", action=ReviewAction.APPROVED),
            ],
        )
        updated = assembler.apply_batch_decisions(package, batch)
        for item in updated.sections[0].items:
            assert item.action == ReviewAction.APPROVED

    def test_export_for_stage11(self, assembler):
        """Test exporting approved decisions for Stage 11."""
        item = UnifiedReviewItem(
            id="REV-001",
            stage=4,
            stage_name="Alternative Resolution",
            item_type=ReviewItemType.ALTERNATIVE_CHOICE,
            title="Imaging Selection",
            description="Test",
            priority=ReviewPriority.CRITICAL,
            source_entity_id="ACT-IMAGING-001",
            source_entity_type="activity",
            source_entity_name="Tumor Assessment",
            options=[
                ReviewOption(id="OPT-CT", label="CT", description="CT Scan"),
            ],
            action=ReviewAction.APPROVED,
            selected_option_id="OPT-CT",
        )
        section = StageReviewSection(
            stage=4,
            stage_name="Alternative Resolution",
            description="Test",
            items=[item],
        )
        section.calculate_stats()
        package = HumanReviewPackage(
            id="PKG-001",
            protocol_id="NCT12345",
            protocol_name="Test",
            created_at=datetime.now().isoformat(),
            sections=[section],
        )

        export = assembler.export_for_stage11(package)
        assert "decisions_by_stage" in export
        assert 4 in export["decisions_by_stage"]
        assert len(export["decisions_by_stage"][4]["decisions"]) == 1
        assert export["decisions_by_stage"][4]["decisions"][0]["item_id"] == "REV-001"
        assert export["decisions_by_stage"][4]["decisions"][0]["selected_option_id"] == "OPT-CT"


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunction:
    """Test the assemble_review_package convenience function."""

    def test_basic_assembly(self, sample_stage_results):
        """Test basic package assembly via convenience function."""
        package, result = assemble_review_package(
            stage_results=sample_stage_results,
            protocol_id="NCT12345678",
            protocol_name="Test Protocol",
        )
        assert package is not None
        assert result.items_collected == 3

    def test_with_auto_approve(self):
        """Test assembly with auto-approve enabled."""
        # Create result with high confidence item
        high_conf_result = MockStageResult(
            review_items=[
                MockReviewItem(
                    id="HIGH-001",
                    title="High Confidence Item",
                    description="Test",
                    source_entity_id="ACT-001",
                    source_entity_name="Test Activity",
                    options=[{"id": "OPT-1", "label": "Option 1", "is_recommended": True}],
                    confidence=0.98,
                ),
            ],
        )
        stage_results = {7: high_conf_result}

        package, result = assemble_review_package(
            stage_results=stage_results,
            protocol_id="NCT12345678",
            protocol_name="Test Protocol",
            auto_approve_threshold=0.95,
        )
        assert result.auto_approved_count == 1


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_stage_results(self, assembler):
        """Test handling empty stage results."""
        result = assembler.assemble_review_package(
            stage_results={},
            protocol_id="NCT12345",
            protocol_name="Empty Test",
        )
        assert result.items_collected == 0
        assert len(result.package.sections) == 0

    def test_stage_with_no_review_items(self, assembler):
        """Test handling stage result with no review items."""
        stage_results = {
            4: MockStageResult(review_items=[]),
        }
        result = assembler.assemble_review_package(
            stage_results=stage_results,
            protocol_id="NCT12345",
            protocol_name="Test",
        )
        # Empty sections should be filtered out
        assert result.items_collected == 0

    def test_missing_optional_fields(self, assembler):
        """Test handling items with missing optional fields."""
        stage_results = {
            4: MockStageResult(
                review_items=[
                    MockReviewItem(
                        id="ALT-001",
                        title="Test",
                        source_entity_id="ACT-001",
                        source_entity_name="Test Activity",
                        # Missing: confidence, rationale, provenance
                    ),
                ],
            ),
        }
        result = assembler.assemble_review_package(
            stage_results=stage_results,
            protocol_id="NCT12345",
            protocol_name="Test",
        )
        assert result.items_collected == 1
        item = result.package.sections[0].items[0]
        assert item.confidence == 0.0  # Default
        assert item.provenance is None  # Optional

    def test_invalid_decision_item_id(self, assembler):
        """Test applying decision with non-existent item ID."""
        section = StageReviewSection(
            stage=4,
            stage_name="Test",
            description="Test",
            items=[],
        )
        package = HumanReviewPackage(
            id="PKG-001",
            protocol_id="NCT12345",
            protocol_name="Test",
            created_at=datetime.now().isoformat(),
            sections=[section],
        )
        decision = ReviewDecisionRequest(
            item_id="NON-EXISTENT",
            action=ReviewAction.APPROVED,
        )
        # Should not raise, just skip the invalid ID
        updated = assembler.apply_decisions(package, [decision])
        assert updated is not None


# =============================================================================
# Config Tests
# =============================================================================

class TestStage10Config:
    """Test Stage10Config dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = Stage10Config()
        assert config.auto_approve_threshold == 0.95
        assert config.confidence_threshold_high == 0.90
        assert config.confidence_threshold_medium == 0.70
        assert config.include_empty_sections is False
        assert config.sort_items_by_priority is True

    def test_custom_values(self):
        """Test custom configuration."""
        config = Stage10Config(
            auto_approve_threshold=0.90,
            include_empty_sections=True,
            sort_items_by_priority=False,
        )
        assert config.auto_approve_threshold == 0.90
        assert config.include_empty_sections is True
        assert config.sort_items_by_priority is False


class TestStage10Result:
    """Test Stage10Result dataclass."""

    def test_to_dict(self):
        """Test dictionary serialization."""
        package = HumanReviewPackage(
            id="PKG-001",
            protocol_id="NCT12345",
            protocol_name="Test",
            created_at=datetime.now().isoformat(),
            sections=[],
        )
        result = Stage10Result(
            package=package,
            items_collected=10,
            items_by_stage={4: 3, 7: 4, 8: 3},
            auto_approved_count=2,
        )
        data = result.to_dict()
        assert data["metrics"]["itemsCollected"] == 10
        assert data["metrics"]["itemsByStage"] == {4: 3, 7: 4, 8: 3}
        assert data["metrics"]["autoApprovedCount"] == 2
        assert "package" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
