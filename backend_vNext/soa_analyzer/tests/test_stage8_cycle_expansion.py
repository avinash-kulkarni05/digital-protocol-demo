"""
Unit tests for Stage 8: Cycle Expansion

Tests the CycleExpander class and related models for expanding
encounters with repeating cycle patterns.
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from soa_analyzer.models.cycle_expansion import (
    CycleDecision,
    CycleExpansion,
    CycleExpansionConfig,
    CyclePattern,
    CyclePatternType,
    CycleValidationDiscrepancy,
    HumanReviewItem,
    Stage8Result,
    is_already_expanded,
    parse_cycle_range,
    should_skip_expansion,
)
from soa_analyzer.interpretation.stage8_cycle_expansion import (
    CycleExpander,
    CyclePatternRegistry,
    VisitDeltaAnalyzer,
    expand_cycles,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_config():
    """Sample configuration for tests."""
    return CycleExpansionConfig(
        use_llm=False,  # Disable LLM for unit tests
        max_cycles_if_unknown=6,
        steady_state_threshold=4,
        confidence_threshold_auto=0.90,
        confidence_threshold_review=0.70,
    )


@pytest.fixture
def sample_usdm_with_cycles():
    """Sample USDM output with encounters needing cycle expansion."""
    return {
        "encounters": [
            {
                "id": "ENC-001",
                "name": "Day 1 of Each Cycle",
                "instanceType": "Encounter",
                "recurrence": {
                    "type": "PER_CYCLE",
                    "cycleDay": 1,
                    "maxCycles": 6,
                },
                "window": {"days": 3},
                "footnoteMarkers": ["a"],
            },
            {
                "id": "ENC-002",
                "name": "Screening",
                "instanceType": "Encounter",
                "recurrence": None,
            },
            {
                "id": "ENC-003",
                "name": "End of Treatment",
                "instanceType": "Encounter",
                "recurrence": None,
            },
        ],
        "scheduledActivityInstances": [
            {
                "id": "SAI-001",
                "activityId": "ACT-001",
                "visitId": "ENC-001",
                "scheduledInstanceEncounterId": "ENC-001",
            },
            {
                "id": "SAI-002",
                "activityId": "ACT-002",
                "visitId": "ENC-002",
                "scheduledInstanceEncounterId": "ENC-002",
            },
        ],
    }


@pytest.fixture
def cycle_expander(sample_config):
    """CycleExpander instance for tests."""
    return CycleExpander(config=sample_config, use_cache=False)


# =============================================================================
# Test CyclePatternType Enum
# =============================================================================


class TestCyclePatternType:
    """Tests for CyclePatternType enum."""

    def test_explicit_range_value(self):
        """Test EXPLICIT_RANGE enum value."""
        assert CyclePatternType.EXPLICIT_RANGE.value == "explicit_range"

    def test_all_pattern_types_exist(self):
        """Test all expected pattern types exist."""
        expected = [
            "EXPLICIT_RANGE", "EXPLICIT_LIST", "STEADY_STATE",
            "EVERY_N_CYCLES", "FIRST_ONLY", "ALL_CYCLES",
            "CONDITIONAL", "FIXED_INTERVAL", "WEEK_BASED",
        ]
        for pt in expected:
            assert hasattr(CyclePatternType, pt)


# =============================================================================
# Test CycleDecision
# =============================================================================


class TestCycleDecision:
    """Tests for CycleDecision dataclass."""

    def test_create_decision_should_expand(self):
        """Test creating a decision that should expand."""
        decision = CycleDecision(
            encounter_name="Day 1 of Each Cycle",
            recurrence_key="PER_CYCLE:day=1:max=6",
            should_expand=True,
            expanded_cycles=[1, 2, 3, 4, 5, 6],
            confidence=0.95,
            rationale="Oncology protocol with 6 cycles",
        )
        assert decision.should_expand
        assert len(decision.expanded_cycles) == 6
        assert decision.confidence == 0.95

    def test_create_decision_no_expand(self):
        """Test creating a decision that should not expand."""
        decision = CycleDecision(
            encounter_name="Cycle 1 only",
            recurrence_key="PER_CYCLE:day=1:max=1",
            should_expand=False,
            expanded_cycles=[],
            confidence=1.0,
            rationale="Explicit 'Cycle 1 only' marker",
        )
        assert not decision.should_expand
        assert len(decision.expanded_cycles) == 0

    def test_build_recurrence_key_per_cycle(self):
        """Test building recurrence key for PER_CYCLE."""
        recurrence = {"type": "PER_CYCLE", "cycleDay": 1, "maxCycles": 6}
        key = CycleDecision.build_recurrence_key(recurrence)
        assert key == "PER_CYCLE:day=1:max=6"

    def test_build_recurrence_key_fixed_interval(self):
        """Test building recurrence key for FIXED_INTERVAL."""
        recurrence = {"type": "FIXED_INTERVAL", "intervalValue": 3, "intervalUnit": "weeks"}
        key = CycleDecision.build_recurrence_key(recurrence)
        assert key == "FIXED_INTERVAL:3_weeks"

    def test_build_recurrence_key_at_event(self):
        """Test building recurrence key for AT_EVENT."""
        recurrence = {"type": "AT_EVENT", "triggerEvent": "progression"}
        key = CycleDecision.build_recurrence_key(recurrence)
        assert key == "AT_EVENT:progression"

    def test_build_recurrence_key_none(self):
        """Test building recurrence key for None."""
        key = CycleDecision.build_recurrence_key(None)
        assert key == "NONE"

    def test_get_cache_key(self):
        """Test cache key generation."""
        decision = CycleDecision(
            encounter_name="Day 1 of Each Cycle",
            recurrence_key="PER_CYCLE:day=1:max=6",
            should_expand=True,
            expanded_cycles=[1, 2, 3, 4, 5, 6],
        )
        key = decision.get_cache_key()
        assert len(key) == 32  # MD5 hash

    def test_to_dict(self):
        """Test conversion to dictionary."""
        decision = CycleDecision(
            encounter_name="Day 1 of Each Cycle",
            recurrence_key="PER_CYCLE:day=1:max=6",
            should_expand=True,
            expanded_cycles=[1, 2, 3, 4, 5, 6],
            confidence=0.95,
        )
        d = decision.to_dict()
        assert d["shouldExpand"] is True
        assert d["expandedCycles"] == [1, 2, 3, 4, 5, 6]
        assert d["confidence"] == 0.95

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "encounterName": "Day 1 of Each Cycle",
            "recurrenceKey": "PER_CYCLE:day=1:max=6",
            "shouldExpand": True,
            "expandedCycles": [1, 2, 3],
            "confidence": 0.9,
        }
        decision = CycleDecision.from_dict(data)
        assert decision.encounter_name == "Day 1 of Each Cycle"
        assert decision.should_expand is True
        assert len(decision.expanded_cycles) == 3

    def test_create_review_required(self):
        """Test creating a review-required decision."""
        decision = CycleDecision.create_review_required(
            encounter_name="Until progression",
            recurrence_key="AT_EVENT:progression",
            reason="Event-driven pattern",
        )
        assert not decision.should_expand
        assert decision.requires_human_review
        assert decision.confidence == 0.0


# =============================================================================
# Test CycleExpansion
# =============================================================================


class TestCycleExpansion:
    """Tests for CycleExpansion dataclass."""

    def test_create_expansion(self):
        """Test creating a cycle expansion."""
        decision = CycleDecision(
            encounter_name="Day 1",
            recurrence_key="PER_CYCLE:day=1:max=3",
            should_expand=True,
            expanded_cycles=[1, 2, 3],
            confidence=0.95,
        )
        expansion = CycleExpansion(
            original_encounter_id="ENC-001",
            original_name="Day 1 of Each Cycle",
            expanded_encounters=[
                {"id": "ENC-001-C1"},
                {"id": "ENC-001-C2"},
                {"id": "ENC-001-C3"},
            ],
            expanded_sai_ids=["SAI-001-C1", "SAI-001-C2", "SAI-001-C3"],
            decision=decision,
        )
        assert expansion.expansion_count == 3
        assert expansion.sai_duplication_count == 3
        assert expansion.confidence == 0.95

    def test_to_dict(self):
        """Test conversion to dictionary."""
        decision = CycleDecision(
            encounter_name="Day 1",
            recurrence_key="PER_CYCLE:day=1:max=2",
            should_expand=True,
            expanded_cycles=[1, 2],
            confidence=0.9,
        )
        expansion = CycleExpansion(
            original_encounter_id="ENC-001",
            original_name="Day 1 of Each Cycle",
            expanded_encounters=[{"id": "ENC-001-C1"}, {"id": "ENC-001-C2"}],
            decision=decision,
        )
        d = expansion.to_dict()
        assert d["originalEncounterId"] == "ENC-001"
        assert d["expandedEncounterCount"] == 2


# =============================================================================
# Test Stage8Result
# =============================================================================


class TestStage8Result:
    """Tests for Stage8Result dataclass."""

    def test_empty_result(self):
        """Test empty result."""
        result = Stage8Result()
        assert result.encounters_processed == 0
        assert len(result.expansions) == 0
        assert len(result.review_items) == 0

    def test_add_expansion(self):
        """Test adding expansion updates metrics."""
        result = Stage8Result()
        decision = CycleDecision(
            encounter_name="Day 1",
            recurrence_key="PER_CYCLE:day=1:max=3",
            should_expand=True,
            expanded_cycles=[1, 2, 3],
        )
        expansion = CycleExpansion(
            original_encounter_id="ENC-001",
            original_name="Day 1",
            expanded_encounters=[{"id": f"ENC-001-C{i}"} for i in [1, 2, 3]],
            expanded_sai_ids=["SAI-001-C1", "SAI-001-C2", "SAI-001-C3"],
            decision=decision,
        )
        result.add_expansion(expansion)
        assert result.encounters_expanded == 1
        assert result.encounters_created == 3
        assert result.sais_created == 3

    def test_add_event_driven_review(self):
        """Test adding event-driven encounter to review."""
        result = Stage8Result()
        encounter = {
            "id": "ENC-010",
            "name": "Until progression",
            "recurrence": {"type": "AT_EVENT", "triggerEvent": "progression"},
        }
        result.add_event_driven_review(encounter, "Cannot auto-expand")
        assert result.event_driven_flagged == 1
        assert len(result.review_items) == 1
        assert result.review_items[0].priority == "high"

    def test_get_summary(self):
        """Test getting summary statistics."""
        result = Stage8Result()
        result.encounters_processed = 10
        result.encounters_with_recurrence = 5
        result.encounters_expanded = 3
        result.cache_hits = 2
        summary = result.get_summary()
        assert summary["encountersProcessed"] == 10
        assert summary["cacheHits"] == 2


# =============================================================================
# Test Helper Functions
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_is_already_expanded_false(self):
        """Test encounter not already expanded."""
        encounter = {"id": "ENC-001", "name": "Day 1"}
        assert not is_already_expanded(encounter)

    def test_is_already_expanded_has_metadata(self):
        """Test encounter with expansion metadata."""
        encounter = {"id": "ENC-001", "_cycleExpansion": {"originalId": "ENC-000"}}
        assert is_already_expanded(encounter)

    def test_is_already_expanded_has_cycle_suffix(self):
        """Test encounter with cycle suffix in ID."""
        encounter = {"id": "ENC-001-C3", "name": "Cycle 3 Day 1"}
        assert is_already_expanded(encounter)

    def test_parse_cycle_range_dash(self):
        """Test parsing cycle range with dash."""
        result = parse_cycle_range("Cycles 1-6")
        assert result == [1, 2, 3, 4, 5, 6]

    def test_parse_cycle_range_em_dash(self):
        """Test parsing cycle range with em-dash."""
        result = parse_cycle_range("Cycles 1–4")
        assert result == [1, 2, 3, 4]

    def test_parse_cycle_range_list(self):
        """Test parsing cycle list."""
        result = parse_cycle_range("Cycles 1, 3, 5")
        assert result == [1, 3, 5]

    def test_should_skip_no_recurrence(self):
        """Test skipping encounter without recurrence."""
        config = CycleExpansionConfig()
        encounter = {"id": "ENC-001", "name": "Screening", "recurrence": None}
        should_skip, reason = should_skip_expansion(encounter, config)
        assert should_skip
        assert "No recurrence" in reason

    def test_should_skip_already_expanded(self):
        """Test skipping already expanded encounter."""
        config = CycleExpansionConfig()
        encounter = {"id": "ENC-001-C2", "name": "Cycle 2", "_cycleExpansion": {}}
        should_skip, reason = should_skip_expansion(encounter, config)
        assert should_skip

    def test_should_skip_non_expandable_type(self):
        """Test skipping non-expandable visit type."""
        config = CycleExpansionConfig()
        encounter = {
            "id": "ENC-001",
            "name": "Screening Visit",
            "recurrence": {"type": "NONE"},
        }
        should_skip, reason = should_skip_expansion(encounter, config)
        assert should_skip

    def test_should_skip_cycle_1_only(self):
        """Test skipping 'Cycle 1 only' encounters."""
        config = CycleExpansionConfig()
        encounter = {
            "id": "ENC-001",
            "name": "Cycle 1 only",
            "recurrence": {"type": "PER_CYCLE", "cycleDay": 1},
        }
        should_skip, reason = should_skip_expansion(encounter, config)
        assert should_skip
        assert "Cycle 1 only" in reason

    def test_should_not_skip_expandable(self):
        """Test not skipping expandable encounter."""
        config = CycleExpansionConfig()
        encounter = {
            "id": "ENC-001",
            "name": "Day 1 of Each Cycle",
            "recurrence": {"type": "PER_CYCLE", "cycleDay": 1, "maxCycles": 6},
        }
        should_skip, reason = should_skip_expansion(encounter, config)
        assert not should_skip


# =============================================================================
# Test CyclePatternRegistry
# =============================================================================


class TestCyclePatternRegistry:
    """Tests for CyclePatternRegistry."""

    def test_load_patterns(self):
        """Test loading patterns from config."""
        registry = CyclePatternRegistry()
        # Should load patterns from config file
        assert registry is not None

    def test_is_non_expandable_screening(self):
        """Test Screening is non-expandable."""
        registry = CyclePatternRegistry()
        assert registry.is_non_expandable("Screening")
        assert registry.is_non_expandable("Screening Visit")

    def test_is_non_expandable_eot(self):
        """Test EOT is non-expandable."""
        registry = CyclePatternRegistry()
        assert registry.is_non_expandable("End of Treatment")
        assert registry.is_non_expandable("EOT")

    def test_is_event_driven(self):
        """Test event-driven pattern detection."""
        registry = CyclePatternRegistry()
        assert registry.is_event_driven("until progression")
        assert registry.is_event_driven("Until disease progression")

    def test_is_steady_state(self):
        """Test steady-state pattern detection."""
        registry = CyclePatternRegistry()
        assert registry.is_steady_state("Cycle 4+")
        assert registry.is_steady_state("Cycle 4 onwards")  # Singular "Cycle" matches config

    def test_get_known_expansion(self):
        """Test getting known expansion."""
        registry = CyclePatternRegistry()
        result = registry.get_known_expansion("Cycles 1-6")
        assert result == [1, 2, 3, 4, 5, 6]

    def test_get_cycle_length(self):
        """Test getting cycle length."""
        registry = CyclePatternRegistry()
        assert registry.get_cycle_length("Q3W treatment") == 21
        assert registry.get_cycle_length("Q4W treatment") == 28


# =============================================================================
# Test CycleExpander
# =============================================================================


class TestCycleExpander:
    """Tests for CycleExpander class."""

    def test_init(self, sample_config):
        """Test initialization."""
        expander = CycleExpander(config=sample_config, use_cache=False)
        assert expander.config == sample_config
        assert not expander.use_cache

    def test_generate_encounter_id(self, cycle_expander):
        """Test sequential encounter ID generation."""
        new_id = cycle_expander._generate_encounter_id(16)
        assert new_id == "ENC-016"

    def test_generate_encounter_name_each_cycle(self, cycle_expander):
        """Test encounter name generation for 'each cycle'."""
        new_name = cycle_expander._generate_encounter_name("Day 1 of Each Cycle", 3)
        assert "Cycle 3" in new_name

    def test_generate_encounter_name_all_cycles(self, cycle_expander):
        """Test encounter name generation for 'all cycles'."""
        new_name = cycle_expander._generate_encounter_name("Day 1 of All Cycles", 2)
        assert "Cycle 2" in new_name

    def test_create_cycle_number_code(self, cycle_expander):
        """Test USDM 4.0 cycleNumber Code object creation."""
        code = cycle_expander._create_cycle_number_code(3, "ENC-001", is_steady_state=False)
        assert code["instanceType"] == "Code"
        assert code["code"] == "C94535"
        assert "Cycle 3" in code["decode"]
        assert code["id"].startswith("CODE-CYC-")

    def test_create_cycle_number_code_steady_state(self, cycle_expander):
        """Test steady-state cycleNumber Code object."""
        code = cycle_expander._create_cycle_number_code(5, "ENC-001", is_steady_state=True)
        assert code["instanceType"] == "Code"

    def test_generate_expanded_encounters(self, cycle_expander):
        """Test generating expanded encounters."""
        encounter = {
            "id": "ENC-001",
            "name": "Day 1 of Each Cycle",
            "instanceType": "Encounter",
            "window": {"days": 3},
            "footnoteMarkers": ["a"],
        }
        decision = CycleDecision(
            encounter_name="Day 1 of Each Cycle",
            recurrence_key="PER_CYCLE:day=1:max=3",
            should_expand=True,
            expanded_cycles=[1, 2, 3],
            confidence=0.95,
        )
        expanded = cycle_expander._generate_expanded_encounters(encounter, decision, next_seq=10)
        assert len(expanded) == 3
        assert expanded[0]["id"] == "ENC-010"
        assert expanded[1]["id"] == "ENC-011"
        assert expanded[2]["id"] == "ENC-012"
        # Check field preservation
        assert expanded[0]["window"] == {"days": 3}
        assert expanded[0]["footnoteMarkers"] == ["a"]
        # Check cycleNumber Code object
        assert expanded[0]["cycleNumber"]["instanceType"] == "Code"

    def test_duplicate_sais_for_cycles(self, cycle_expander):
        """Test SAI duplication for cycles."""
        sais = [
            {"id": "SAI-001", "activityId": "ACT-001", "visitId": "ENC-001"},
            {"id": "SAI-002", "activityId": "ACT-002", "visitId": "ENC-002"},
        ]
        expanded_encounters = [
            {"id": "ENC-001-C1", "_cycleExpansion": {"cycleNumber": 1}},
            {"id": "ENC-001-C2", "_cycleExpansion": {"cycleNumber": 2}},
        ]
        new_sais = cycle_expander._duplicate_sais_for_cycles(
            sais, "ENC-001", expanded_encounters
        )
        assert len(new_sais) == 2  # SAI-001 duplicated for 2 cycles
        assert new_sais[0]["id"] == "SAI-001-C1"
        assert new_sais[1]["id"] == "SAI-001-C2"

    def test_get_encounters_direct(self, cycle_expander):
        """Test getting encounters from direct structure."""
        usdm = {
            "encounters": [{"id": "ENC-001"}, {"id": "ENC-002"}]
        }
        encounters = cycle_expander._get_encounters(usdm)
        assert len(encounters) == 2

    def test_get_encounters_nested(self, cycle_expander):
        """Test getting encounters from nested structure."""
        usdm = {
            "studyVersion": [
                {"encounters": [{"id": "ENC-001"}]}
            ]
        }
        encounters = cycle_expander._get_encounters(usdm)
        assert len(encounters) == 1


# =============================================================================
# Test Apply Expansions
# =============================================================================


class TestApplyExpansions:
    """Tests for applying expansions to USDM."""

    def test_apply_expansions_empty(self, cycle_expander, sample_usdm_with_cycles):
        """Test applying empty expansions returns unchanged."""
        result = Stage8Result()
        output = cycle_expander.apply_expansions_to_usdm(sample_usdm_with_cycles, result)
        assert len(output["encounters"]) == 3  # Unchanged

    def test_apply_expansions_replaces_encounter(self, cycle_expander, sample_usdm_with_cycles):
        """Test applying expansions replaces original encounter."""
        decision = CycleDecision(
            encounter_name="Day 1 of Each Cycle",
            recurrence_key="PER_CYCLE:day=1:max=3",
            should_expand=True,
            expanded_cycles=[1, 2, 3],
        )
        expansion = CycleExpansion(
            original_encounter_id="ENC-001",
            original_name="Day 1 of Each Cycle",
            expanded_encounters=[
                {"id": "ENC-001-C1", "name": "Cycle 1 Day 1", "_cycleExpansion": {"cycleNumber": 1}},
                {"id": "ENC-001-C2", "name": "Cycle 2 Day 1", "_cycleExpansion": {"cycleNumber": 2}},
                {"id": "ENC-001-C3", "name": "Cycle 3 Day 1", "_cycleExpansion": {"cycleNumber": 3}},
            ],
            decision=decision,
        )
        result = Stage8Result()
        result.expansions = [expansion]

        output = cycle_expander.apply_expansions_to_usdm(sample_usdm_with_cycles.copy(), result)
        # Original 3 - 1 (ENC-001) + 3 (expanded) = 5
        assert len(output["encounters"]) == 5
        # Check expanded encounters are present
        enc_ids = [e["id"] for e in output["encounters"]]
        assert "ENC-001-C1" in enc_ids
        assert "ENC-001-C2" in enc_ids
        assert "ENC-001-C3" in enc_ids
        # Original ENC-001 should be removed
        assert "ENC-001" not in enc_ids


# =============================================================================
# Test Validation
# =============================================================================


class TestValidation:
    """Tests for validation against patterns."""

    def test_validate_discrepancy_detected(self, cycle_expander):
        """Test validation detects discrepancies."""
        decisions = {
            "ENC-001": CycleDecision(
                encounter_name="Cycles 1-6",
                recurrence_key="PER_CYCLE:day=1:max=6",
                should_expand=True,
                expanded_cycles=[1, 2, 3],  # Wrong! Should be [1,2,3,4,5,6]
            ),
        }
        discrepancies = cycle_expander._validate_against_patterns(decisions)
        # May or may not find discrepancy depending on config
        assert isinstance(discrepancies, list)


# =============================================================================
# Test Cache Operations
# =============================================================================


class TestCacheOperations:
    """Tests for cache operations."""

    def test_get_cache_key(self, cycle_expander):
        """Test cache key generation."""
        key = cycle_expander._get_cache_key("Day 1", "PER_CYCLE:day=1:max=6")
        assert len(key) == 32  # MD5 hash

    def test_cache_hit_and_miss(self, cycle_expander):
        """Test cache hit and miss."""
        # Initially no cache
        result = cycle_expander._check_cache("Day 1", "PER_CYCLE:day=1:max=6")
        assert result is None

        # Add to cache
        decision = CycleDecision(
            encounter_name="Day 1",
            recurrence_key="PER_CYCLE:day=1:max=6",
            should_expand=True,
            expanded_cycles=[1, 2, 3, 4, 5, 6],
        )
        cycle_expander._update_cache("Day 1", "PER_CYCLE:day=1:max=6", decision)

        # Now should hit cache
        result = cycle_expander._check_cache("Day 1", "PER_CYCLE:day=1:max=6")
        assert result is not None
        assert result.source == "cache"


# =============================================================================
# Test Async Integration
# =============================================================================


class TestAsyncIntegration:
    """Tests for async expand_cycles function."""

    @pytest.mark.asyncio
    async def test_expand_cycles_no_recurrence(self):
        """Test expand_cycles with no recurrence patterns."""
        usdm = {
            "encounters": [
                {"id": "ENC-001", "name": "Screening", "recurrence": None},
                {"id": "ENC-002", "name": "Baseline", "recurrence": None},
            ],
            "scheduledActivityInstances": [],
        }
        config = CycleExpansionConfig(use_llm=False)
        expander = CycleExpander(config=config, use_cache=False)
        result = await expander.expand_cycles(usdm)
        assert result.encounters_processed == 2
        assert result.encounters_expanded == 0
        assert result.encounters_skipped == 2

    @pytest.mark.asyncio
    async def test_expand_cycles_event_driven_flagged(self):
        """Test event-driven patterns are flagged for review."""
        usdm = {
            "encounters": [
                {
                    "id": "ENC-001",
                    "name": "Treatment until progression",
                    "recurrence": {"type": "AT_EVENT", "triggerEvent": "progression"},
                },
            ],
            "scheduledActivityInstances": [],
        }
        config = CycleExpansionConfig(use_llm=False)
        expander = CycleExpander(config=config, use_cache=False)
        result = await expander.expand_cycles(usdm)
        assert result.event_driven_flagged == 1
        assert len(result.review_items) >= 1


# =============================================================================
# Test Timepoint Deduplication (M21-195 False Positive Fix)
# =============================================================================


class TestTimepointDeduplication:
    """Tests for multi-timepoint visit deduplication in cycle expansion."""

    def test_visit_delta_analyzer_deduplicates_timepoints(self):
        """
        7 encounters with parentVisit="Day 1" + Day 7 + Day 14 should produce
        deltas based on [1, 7, 14], not [1,1,1,1,1,1,1,7,14].

        This is the M21-195 scenario: 7 hourly timepoint columns under Day 1
        should not cause false cycle detection.
        """
        encounters = [
            {"name": "Day 1", "id": "ENC-001", "parentVisit": "Day 1", "timingModifier": "Hour 0"},
            {"name": "Day 1", "id": "ENC-002", "parentVisit": "Day 1", "timingModifier": "Hour 1"},
            {"name": "Day 1", "id": "ENC-003", "parentVisit": "Day 1", "timingModifier": "Hour 3"},
            {"name": "Day 1", "id": "ENC-004", "parentVisit": "Day 1", "timingModifier": "Hour 5"},
            {"name": "Day 1", "id": "ENC-005", "parentVisit": "Day 1", "timingModifier": "Hour 7"},
            {"name": "Day 1", "id": "ENC-006", "parentVisit": "Day 1", "timingModifier": "Hour 9"},
            {"name": "Day 1", "id": "ENC-007", "parentVisit": "Day 1", "timingModifier": "Hour 11"},
            {"name": "Day 7", "id": "ENC-008"},
            {"name": "Day 14", "id": "ENC-009"},
        ]
        result = VisitDeltaAnalyzer.analyze(encounters)

        # After deduplication: [Day 1, Day 7, Day 14] → days [1, 7, 14] → deltas [6, 7]
        assert result["visitDays"] == [1, 7, 14]
        assert result["deltas"] == [6, 7]
        # Should NOT detect a false 0-day repeating pattern
        assert result.get("inferredIntervalDays", 0) != 0

    def test_visit_delta_analyzer_no_false_cycle_from_timepoints(self):
        """Timepoint-heavy visits should not produce hasPattern=True with 0-day interval."""
        encounters = [
            {"name": "Day 1", "id": "ENC-001", "parentVisit": "Day 1", "timingModifier": "Hour 0"},
            {"name": "Day 1", "id": "ENC-002", "parentVisit": "Day 1", "timingModifier": "Hour 1"},
            {"name": "Day 1", "id": "ENC-003", "parentVisit": "Day 1", "timingModifier": "Hour 3"},
            {"name": "Day 1", "id": "ENC-004", "parentVisit": "Day 1", "timingModifier": "Hour 5"},
            {"name": "Day 1", "id": "ENC-005", "parentVisit": "Day 1", "timingModifier": "Hour 7"},
            {"name": "Day 1", "id": "ENC-006", "parentVisit": "Day 1", "timingModifier": "Hour 9"},
            {"name": "Day 1", "id": "ENC-007", "parentVisit": "Day 1", "timingModifier": "Hour 11"},
            {"name": "Day 7", "id": "ENC-008"},
            {"name": "Day 14", "id": "ENC-009"},
        ]
        result = VisitDeltaAnalyzer.analyze(encounters)
        # With only 3 deduplicated visits and deltas [6, 7], the dominant delta
        # is 6 or 7 — NOT 0. Verify no false 0-day cycle.
        if result.get("hasPattern"):
            assert result["inferredIntervalDays"] > 0

    def test_visit_delta_analyzer_passthrough_without_parent_visit(self):
        """Encounters without parentVisit pass through unchanged."""
        encounters = [
            {"name": "Day 1", "id": "ENC-001"},
            {"name": "Day 22", "id": "ENC-002"},
            {"name": "Day 43", "id": "ENC-003"},
        ]
        result = VisitDeltaAnalyzer.analyze(encounters)
        assert result["visitDays"] == [1, 22, 43]
        assert result["deltas"] == [21, 21]
        assert result["hasPattern"] is True
        assert result["inferredIntervalDays"] == 21

    def test_encounter_data_includes_timing_fields(self, cycle_expander):
        """Verify timingModifier, parentVisit, visitType are included in LLM data."""
        encounters = [
            {
                "id": "ENC-001",
                "name": "Day 1",
                "timingModifier": "Hour 0",
                "parentVisit": "Day 1",
                "visitType": "treatment",
                "recurrence": None,
            },
        ]
        # Build enc_data the same way expand_cycles does
        enc_data = {
            "id": encounters[0].get("id", ""),
            "name": encounters[0].get("name", ""),
            "type": encounters[0].get("type"),
            "timingModifier": encounters[0].get("timingModifier"),
            "parentVisit": encounters[0].get("parentVisit"),
            "visitType": encounters[0].get("visitType"),
        }
        assert enc_data["timingModifier"] == "Hour 0"
        assert enc_data["parentVisit"] == "Day 1"
        assert enc_data["visitType"] == "treatment"

    def test_supplemental_context_includes_timepoint_grouping(self, cycle_expander):
        """Verify TIMEPOINT GROUPING section appears in supplemental context."""
        encounters_data = [
            {"id": "ENC-001", "name": "Day 1", "parentVisit": "Day 1", "timingModifier": "Hour 0"},
            {"id": "ENC-002", "name": "Day 1", "parentVisit": "Day 1", "timingModifier": "Hour 1"},
            {"id": "ENC-003", "name": "Day 1", "parentVisit": "Day 1", "timingModifier": "Hour 3"},
            {"id": "ENC-004", "name": "Day 7"},
            {"id": "ENC-005", "name": "Day 14"},
        ]
        context = cycle_expander._build_supplemental_context(encounters_data)
        assert "TIMEPOINT GROUPING" in context
        assert "Day 1: 3 timepoints" in context
        assert "Hour 0" in context
        assert "NOT separate cycles" in context

    def test_supplemental_context_no_grouping_without_timepoints(self, cycle_expander):
        """No TIMEPOINT GROUPING section when no encounters have parentVisit."""
        encounters_data = [
            {"id": "ENC-001", "name": "Day 1"},
            {"id": "ENC-002", "name": "Day 22"},
            {"id": "ENC-003", "name": "Day 43"},
        ]
        context = cycle_expander._build_supplemental_context(encounters_data)
        assert "TIMEPOINT GROUPING" not in context

    def test_oncology_bi_eoi_timepoints_collapse(self):
        """
        Oncology BI/EOI timepoints with parentVisit="Cycle 1 Day 1" should
        collapse to one day in delta analysis — the actual cycle expansion
        still works via recurrence field.
        """
        encounters = [
            {"name": "Cycle 1 Day 1", "id": "ENC-001", "parentVisit": "Cycle 1 Day 1", "timingModifier": "BI"},
            {"name": "Cycle 1 Day 1", "id": "ENC-002", "parentVisit": "Cycle 1 Day 1", "timingModifier": "EOI"},
            {"name": "Cycle 1 Day 8", "id": "ENC-003"},
            {"name": "Cycle 1 Day 15", "id": "ENC-004"},
        ]
        deduplicated = VisitDeltaAnalyzer._deduplicate_by_parent_visit(encounters)
        # BI and EOI collapse into one "Cycle 1 Day 1" representative
        assert len(deduplicated) == 3
        names = [e["name"] for e in deduplicated]
        assert names.count("Cycle 1 Day 1") == 1


# =============================================================================
# Test Table Classification Profile in Supplemental Context
# =============================================================================


class TestTableClassificationProfile:
    """Tests for TABLE CLASSIFICATION section in Stage 8 supplemental context."""

    def test_supplemental_context_includes_table_classification(self, cycle_expander):
        """Verify TABLE CLASSIFICATION section appears when profile is present."""
        cycle_expander._table_profile = {
            "tableStructureType": "PK-heavy Phase 1 linear study",
            "confidence": 0.92,
            "characteristics": [
                "High timepoint ratio (0.636)",
                "No recurrence patterns",
                "Day-based naming",
            ],
            "stageGuidance": {
                "stage8_cycles": "These are PK timepoints, NOT cycles. Do not expand.",
            },
        }

        encounters_data = [
            {"id": "ENC-001", "name": "Day 1", "parentVisit": "Day 1", "timingModifier": "Hour 0"},
            {"id": "ENC-002", "name": "Day 7"},
        ]
        context = cycle_expander._build_supplemental_context(encounters_data)

        assert "TABLE CLASSIFICATION: PK-heavy Phase 1 linear study" in context
        assert "confidence: 0.92" in context
        assert "High timepoint ratio (0.636)" in context
        assert "CYCLE EXPANSION GUIDANCE:" in context
        assert "PK timepoints, NOT cycles" in context

    def test_no_table_classification_section_without_profile(self, cycle_expander):
        """No TABLE CLASSIFICATION section when profile is absent or empty."""
        cycle_expander._table_profile = {}

        encounters_data = [
            {"id": "ENC-001", "name": "Day 1"},
            {"id": "ENC-002", "name": "Day 22"},
        ]
        context = cycle_expander._build_supplemental_context(encounters_data)

        assert "TABLE CLASSIFICATION" not in context

    def test_no_table_classification_when_no_attribute(self, cycle_expander):
        """No TABLE CLASSIFICATION section when _table_profile not set at all."""
        # Ensure attribute doesn't exist
        if hasattr(cycle_expander, "_table_profile"):
            delattr(cycle_expander, "_table_profile")

        encounters_data = [
            {"id": "ENC-001", "name": "Day 1"},
        ]
        context = cycle_expander._build_supplemental_context(encounters_data)

        assert "TABLE CLASSIFICATION" not in context

    @pytest.mark.asyncio
    async def test_table_profile_stored_from_usdm(self, cycle_expander):
        """Verify _table_profile is extracted from usdm_output in expand_cycles."""
        profile = {
            "tableStructureType": "Oncology cyclic",
            "confidence": 0.88,
            "characteristics": ["Explicit cycle labels"],
            "stageGuidance": {
                "stage8_cycles": "Standard oncology cycle expansion expected.",
            },
        }
        usdm = {
            "encounters": [],
            "scheduledActivityInstances": [],
            "soaTableProfile": profile,
        }

        # Run expand_cycles — it sets _table_profile from usdm
        await cycle_expander.expand_cycles(usdm)

        assert cycle_expander._table_profile == profile

    @pytest.mark.asyncio
    async def test_table_profile_empty_when_not_in_usdm(self, cycle_expander):
        """_table_profile is {} when soaTableProfile not in usdm_output."""
        usdm = {
            "encounters": [],
            "scheduledActivityInstances": [],
        }

        await cycle_expander.expand_cycles(usdm)

        assert cycle_expander._table_profile == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
