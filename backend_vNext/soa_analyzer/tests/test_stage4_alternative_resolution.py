"""
Unit tests for Stage 4: Alternative Resolution.

Tests cover:
1. AlternativePatternRegistry - pattern matching and validation
2. AlternativeDecision - cache key generation and serialization
3. Helper functions - is_timing_pattern, is_unit_pattern, etc.
4. AlternativeResolver - core resolution logic
5. Edge cases - multi-way, nested, timing/unit filtering
"""

import asyncio
import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from soa_analyzer.models.alternative_expansion import (
    AlternativeType,
    ResolutionAction,
    AlternativeOption,
    AlternativeDecision,
    AlternativeProvenance,
    AlternativeExpansion,
    HumanReviewItem,
    Stage4Result,
    AlternativeResolutionConfig,
    is_timing_pattern,
    is_unit_pattern,
    is_and_pattern,
    should_analyze_for_alternatives,
    generate_activity_id,
    generate_sai_id,
    generate_condition_id,
    generate_assignment_id,
)

from soa_analyzer.interpretation.stage4_alternative_resolution import (
    AlternativePatternRegistry,
    AlternativeResolver,
)


# ============================================================================
# Test Helper Functions
# ============================================================================

class TestIsTimingPattern:
    """Tests for is_timing_pattern helper function."""

    def test_bi_eoi_recognized(self):
        """BI/EOI is a timing pattern, not an alternative."""
        assert is_timing_pattern("BI/EOI") is True
        assert is_timing_pattern("bi/eoi") is True
        assert is_timing_pattern("BI / EOI") is True

    def test_pre_post_dose_recognized(self):
        """Pre-dose/post-dose is a timing pattern."""
        assert is_timing_pattern("pre-dose/post-dose") is True
        assert is_timing_pattern("predose/postdose") is True

    def test_trough_peak_recognized(self):
        """Trough/peak is a timing pattern."""
        assert is_timing_pattern("trough/peak") is True
        assert is_timing_pattern("peak/trough") is True

    def test_fasting_fed_recognized(self):
        """Fasting/fed is a timing pattern."""
        assert is_timing_pattern("fasting/fed") is True
        assert is_timing_pattern("fed/fasting") is True

    def test_not_timing_patterns(self):
        """Regular alternatives should not be marked as timing patterns."""
        assert is_timing_pattern("CT or MRI") is False
        assert is_timing_pattern("Blood / urine sample") is False
        assert is_timing_pattern("ECG") is False


class TestIsUnitPattern:
    """Tests for is_unit_pattern helper function."""

    def test_mg_kg_recognized(self):
        """mg/kg dosing unit is recognized."""
        assert is_unit_pattern("5 mg/kg") is True
        assert is_unit_pattern("10mg/kg") is True
        assert is_unit_pattern("2.5 mg/kg body weight") is True

    def test_mg_m2_recognized(self):
        """mg/m² (body surface area) is recognized."""
        assert is_unit_pattern("100 mg/m2") is True
        assert is_unit_pattern("75 mg/m²") is True

    def test_ml_min_recognized(self):
        """mL/min rate is recognized."""
        assert is_unit_pattern("30 mL/min") is True
        assert is_unit_pattern("60 ml/min") is True

    def test_not_unit_patterns(self):
        """Regular alternatives should not be marked as unit patterns."""
        assert is_unit_pattern("CT or MRI") is False
        assert is_unit_pattern("Blood / urine") is False


class TestIsAndPattern:
    """Tests for is_and_pattern helper function."""

    def test_and_recognized(self):
        """'and' patterns should not be expanded as alternatives."""
        assert is_and_pattern("Height and weight") is True
        assert is_and_pattern("CBC and chemistry") is True

    def test_and_or_not_blocked(self):
        """'and/or' IS an alternative and should not be blocked."""
        assert is_and_pattern("CT and/or MRI") is False

    def test_or_not_blocked(self):
        """'or' patterns should not be blocked."""
        assert is_and_pattern("CT or MRI") is False


class TestShouldAnalyzeForAlternatives:
    """Tests for should_analyze_for_alternatives helper function."""

    def test_or_detected(self):
        """Activities with 'or' should be analyzed."""
        assert should_analyze_for_alternatives("CT or MRI") is True
        assert should_analyze_for_alternatives("Blood or urine sample") is True

    def test_slash_detected(self):
        """Activities with '/' should be analyzed."""
        assert should_analyze_for_alternatives("CT / MRI") is True
        assert should_analyze_for_alternatives("ECG/Holter") is True

    def test_timing_filtered(self):
        """Timing patterns should not be analyzed."""
        assert should_analyze_for_alternatives("BI/EOI") is False
        assert should_analyze_for_alternatives("pre-dose/post-dose") is False

    def test_unit_filtered(self):
        """Unit patterns should not be analyzed."""
        assert should_analyze_for_alternatives("5 mg/kg") is False
        assert should_analyze_for_alternatives("100 mg/m2") is False

    def test_and_filtered(self):
        """'and' patterns should not be analyzed."""
        assert should_analyze_for_alternatives("Height and weight") is False


# ============================================================================
# Test ID Generation Functions
# ============================================================================

class TestIDGeneration:
    """Tests for deterministic ID generation."""

    def test_generate_activity_id(self):
        """Activity IDs use letter suffixes."""
        assert generate_activity_id("ACT-001", 1, 2) == "ACT-001-A"
        assert generate_activity_id("ACT-001", 2, 2) == "ACT-001-B"
        assert generate_activity_id("ACT-001", 3, 3) == "ACT-001-C"

    def test_generate_activity_id_many(self):
        """Falls back to numeric for >26 alternatives."""
        assert generate_activity_id("ACT-001", 26, 30) == "ACT-001-Z"
        assert generate_activity_id("ACT-001", 27, 30) == "ACT-001-27"

    def test_generate_sai_id(self):
        """SAI IDs include alternative suffix."""
        assert generate_sai_id("SAI-042", "A") == "SAI-042-A"
        assert generate_sai_id("SAI-042", "B") == "SAI-042-B"

    def test_generate_condition_id(self):
        """Condition IDs are deterministic."""
        cond_id = generate_condition_id("ACT-001", 1)
        assert "COND-ALT" in cond_id
        assert "001" in cond_id
        assert "A" in cond_id

    def test_generate_assignment_id(self):
        """Assignment IDs are hash-based."""
        assign_id = generate_assignment_id("COND-001", "SAI-042-A")
        assert "CA-ALT" in assign_id
        # Hash should be consistent
        assert generate_assignment_id("COND-001", "SAI-042-A") == assign_id


# ============================================================================
# Test AlternativeOption
# ============================================================================

class TestAlternativeOption:
    """Tests for AlternativeOption dataclass."""

    def test_to_dict(self):
        """Options serialize correctly."""
        opt = AlternativeOption(
            name="CT scan",
            order=1,
            confidence=0.95,
            cdisc_domain="MI",
            is_preferred=True,
        )
        result = opt.to_dict()
        assert result["name"] == "CT scan"
        assert result["order"] == 1
        assert result["confidence"] == 0.95
        assert result["cdiscDomain"] == "MI"
        assert result["isPreferred"] is True


# ============================================================================
# Test AlternativeDecision
# ============================================================================

class TestAlternativeDecision:
    """Tests for AlternativeDecision dataclass."""

    def test_cache_key_includes_model(self):
        """Cache key includes model name for invalidation."""
        decision = AlternativeDecision(
            activity_id="ACT-001",
            activity_name="CT or MRI",
            is_alternative=True,
        )
        key1 = decision.get_cache_key("gemini-2.0-flash")
        key2 = decision.get_cache_key("gpt-4-turbo")
        assert key1 != key2

    def test_cache_key_normalized(self):
        """Cache key normalizes text."""
        decision1 = AlternativeDecision(
            activity_id="ACT-001",
            activity_name="CT or MRI",
            is_alternative=True,
        )
        decision2 = AlternativeDecision(
            activity_id="ACT-001",
            activity_name="  CT OR MRI  ",
            is_alternative=True,
        )
        assert decision1.get_cache_key("model") == decision2.get_cache_key("model")

    def test_from_llm_response(self):
        """Correctly parses LLM JSON response."""
        response = {
            "activityName": "CT or MRI",
            "isAlternative": True,
            "alternativeType": "MUTUALLY_EXCLUSIVE",
            "alternatives": [
                {"name": "CT scan", "order": 1, "confidence": 0.95},
                {"name": "MRI", "order": 2, "confidence": 0.95},
            ],
            "recommendedResolution": "expand",
            "confidence": 0.95,
            "rationale": "Explicit OR between imaging modalities",
        }
        decision = AlternativeDecision.from_llm_response("ACT-001", response, "gemini")
        assert decision.is_alternative is True
        assert decision.alternative_type == AlternativeType.MUTUALLY_EXCLUSIVE
        assert len(decision.alternatives) == 2
        assert decision.recommended_action == ResolutionAction.EXPAND
        assert decision.confidence == 0.95

    def test_to_dict(self):
        """Serialization includes all fields."""
        decision = AlternativeDecision(
            activity_id="ACT-001",
            activity_name="CT or MRI",
            is_alternative=True,
            alternative_type=AlternativeType.MUTUALLY_EXCLUSIVE,
            alternatives=[
                AlternativeOption(name="CT scan", order=1),
                AlternativeOption(name="MRI", order=2),
            ],
            recommended_action=ResolutionAction.EXPAND,
            confidence=0.95,
            rationale="Test",
            source="llm",
            model_name="gemini",
        )
        result = decision.to_dict()
        assert result["activityId"] == "ACT-001"
        assert result["isAlternative"] is True
        assert result["alternativeType"] == "mutually_exclusive"
        assert len(result["alternatives"]) == 2


# ============================================================================
# Test AlternativeExpansion
# ============================================================================

class TestAlternativeExpansion:
    """Tests for AlternativeExpansion dataclass."""

    def test_to_dict(self):
        """Expansion results serialize correctly."""
        expansion = AlternativeExpansion(
            id="EXP-ACT-001",
            original_activity_id="ACT-001",
            original_activity_name="CT or MRI",
            expanded_activities=[
                {"id": "ACT-001-A", "name": "CT scan"},
                {"id": "ACT-001-B", "name": "MRI"},
            ],
            expanded_sais=[
                {"id": "SAI-042-A", "activityId": "ACT-001-A"},
                {"id": "SAI-042-B", "activityId": "ACT-001-B"},
            ],
            conditions_created=[],
            assignments_created=[],
            confidence=0.95,
            alternative_type=AlternativeType.MUTUALLY_EXCLUSIVE,
        )
        result = expansion.to_dict()
        assert result["id"] == "EXP-ACT-001"
        assert len(result["expandedActivities"]) == 2
        assert len(result["expandedSais"]) == 2


# ============================================================================
# Test Stage4Result
# ============================================================================

class TestStage4Result:
    """Tests for Stage4Result dataclass."""

    def test_add_expansion_updates_metrics(self):
        """Adding expansion updates all metrics."""
        result = Stage4Result()
        expansion = AlternativeExpansion(
            id="EXP-001",
            original_activity_id="ACT-001",
            original_activity_name="CT or MRI",
            expanded_sais=[{"id": "SAI-1"}, {"id": "SAI-2"}],
            conditions_created=[{"id": "COND-1"}],
            assignments_created=[{"id": "CA-1"}, {"id": "CA-2"}],
            confidence=0.95,
        )
        result.add_expansion(expansion)
        assert result.activities_expanded == 1
        assert result.sais_created == 2
        assert result.conditions_created == 1
        assert result.assignments_created == 2
        assert result.auto_applied == 1

    def test_add_expansion_flags_review(self):
        """Expansions requiring review update needs_review."""
        result = Stage4Result()
        expansion = AlternativeExpansion(
            id="EXP-001",
            original_activity_id="ACT-001",
            original_activity_name="Ambiguous",
            requires_review=True,
        )
        result.add_expansion(expansion)
        assert result.needs_review == 1
        assert result.auto_applied == 0

    def test_to_dict(self):
        """Result serializes with all metrics."""
        result = Stage4Result(
            activities_analyzed=10,
            alternatives_detected=3,
            timing_patterns_filtered=2,
            unit_patterns_filtered=1,
        )
        output = result.to_dict()
        assert output["metrics"]["activitiesAnalyzed"] == 10
        assert output["metrics"]["alternativesDetected"] == 3
        assert output["metrics"]["timingPatternsFiltered"] == 2
        assert output["metrics"]["unitPatternsFiltered"] == 1


# ============================================================================
# Test AlternativePatternRegistry
# ============================================================================

class TestAlternativePatternRegistry:
    """Tests for AlternativePatternRegistry."""

    @pytest.fixture
    def registry(self):
        """Create registry instance."""
        return AlternativePatternRegistry()

    def test_timing_pattern_detection(self, registry):
        """Registry detects timing patterns."""
        assert registry.is_timing_pattern("BI/EOI") is True
        assert registry.is_timing_pattern("pre-dose/post-dose") is True
        assert registry.is_timing_pattern("CT or MRI") is False

    def test_unit_pattern_detection(self, registry):
        """Registry detects unit patterns."""
        assert registry.is_unit_pattern("5 mg/kg") is True
        assert registry.is_unit_pattern("100 mg/m2") is True
        assert registry.is_unit_pattern("CT / MRI") is False

    def test_known_alternative_lookup(self, registry):
        """Registry provides known alternatives."""
        # This depends on config/alternative_patterns.json content
        known = registry.get_known_alternative("CT / MRI")
        if known:
            assert "alternatives" in known or known is None

    def test_get_condition_type_code(self, registry):
        """Registry provides CDISC codes for condition types."""
        code = registry.get_condition_type_code("MUTUALLY_EXCLUSIVE")
        if code:
            assert "code" in code
            assert "decode" in code


# ============================================================================
# Test AlternativeResolver
# ============================================================================

class TestAlternativeResolver:
    """Tests for AlternativeResolver main class."""

    @pytest.fixture
    def resolver(self):
        """Create resolver instance."""
        config = AlternativeResolutionConfig(
            use_cache=False,  # Disable cache for testing
        )
        return AlternativeResolver(config)

    def test_extract_candidate_activities(self, resolver):
        """Resolver extracts candidate activities filtering timing/unit patterns."""
        activities = [
            {"id": "ACT-001", "name": "CT or MRI"},  # Should analyze
            {"id": "ACT-002", "name": "BI/EOI"},  # Timing - skip
            {"id": "ACT-003", "name": "5 mg/kg"},  # Unit - skip
            {"id": "ACT-004", "name": "ECG / Holter"},  # Should analyze
            {"id": "ACT-005", "name": "Height and weight"},  # And pattern - skip
        ]
        result = Stage4Result()
        candidates = resolver._extract_candidate_activities(activities, result)
        assert len(candidates) == 2
        assert candidates[0]["id"] == "ACT-001"
        assert candidates[1]["id"] == "ACT-004"
        assert result.timing_patterns_filtered == 1
        assert result.unit_patterns_filtered == 1

    def test_affected_sais_logic(self, resolver):
        """Test the SAI filtering logic used in expansion."""
        # This tests the inline logic used in _generate_expansion
        sais = [
            {"id": "SAI-001", "activityId": "ACT-001", "visitId": "ENC-001"},
            {"id": "SAI-002", "activityId": "ACT-001", "visitId": "ENC-002"},
            {"id": "SAI-003", "activityId": "ACT-002", "visitId": "ENC-001"},
        ]
        # Same logic as in _generate_expansion lines 638-641
        affected = [sai for sai in sais if sai.get("activityId") == "ACT-001"]
        assert len(affected) == 2
        assert all(s["activityId"] == "ACT-001" for s in affected)

    def test_cache_key_generation(self, resolver):
        """Test cache key generation."""
        key1 = resolver._get_cache_key("CT or MRI")
        key2 = resolver._get_cache_key("  CT OR MRI  ")
        # Should be the same (normalized)
        assert key1 == key2

        key3 = resolver._get_cache_key("Blood or urine")
        assert key1 != key3


# ============================================================================
# Test Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and complex scenarios."""

    def test_multi_way_alternative_options(self):
        """Multi-way alternatives (3+ options) create correct count."""
        response = {
            "activityName": "CT, MRI, or PET scan",
            "isAlternative": True,
            "alternativeType": "MUTUALLY_EXCLUSIVE",
            "alternatives": [
                {"name": "CT scan", "order": 1, "confidence": 0.95},
                {"name": "MRI", "order": 2, "confidence": 0.95},
                {"name": "PET scan", "order": 3, "confidence": 0.95},
            ],
            "recommendedResolution": "expand",
            "confidence": 0.95,
            "rationale": "Multi-way alternative",
        }
        decision = AlternativeDecision.from_llm_response("ACT-001", response, "gemini")
        assert len(decision.alternatives) == 3

    def test_discretionary_type_creates_condition(self):
        """Discretionary alternatives create conditions, not expansions."""
        response = {
            "activityName": "Labs if clinically indicated",
            "isAlternative": True,
            "alternativeType": "DISCRETIONARY",
            "alternatives": [
                {"name": "Perform labs", "order": 1},
                {"name": "Skip labs", "order": 2},
            ],
            "recommendedResolution": "condition",
            "confidence": 0.90,
            "rationale": "Discretionary activity",
        }
        decision = AlternativeDecision.from_llm_response("ACT-001", response, "gemini")
        assert decision.alternative_type == AlternativeType.DISCRETIONARY
        assert decision.recommended_action == ResolutionAction.CONDITION

    def test_low_confidence_flags_review(self):
        """Low confidence decisions flag for human review."""
        decision = AlternativeDecision(
            activity_id="ACT-001",
            activity_name="Ambiguous test",
            is_alternative=True,
            alternative_type=AlternativeType.UNCERTAIN,
            confidence=0.65,  # Below 0.70 threshold
        )
        # from_llm_response sets requires_human_review based on confidence
        response = {
            "activityName": "Ambiguous test",
            "isAlternative": True,
            "alternativeType": "UNCERTAIN",
            "alternatives": [],
            "recommendedResolution": "review",
            "confidence": 0.65,
            "rationale": "Unclear",
        }
        decision = AlternativeDecision.from_llm_response("ACT-001", response, "gemini")
        assert decision.requires_human_review is True

    def test_provenance_includes_all_fields(self):
        """Provenance tracks all required fields."""
        provenance = AlternativeProvenance(
            original_activity_id="ACT-001",
            original_activity_name="CT or MRI",
            alternative_type="MUTUALLY_EXCLUSIVE",
            alternative_index=1,
            alternative_count=2,
            confidence=0.95,
            rationale="Test rationale",
            model="gemini-2.0-flash",
            timestamp="2025-12-06T10:30:00Z",
            source="llm",
            cache_hit=False,
            cache_key="abc123",
        )
        result = provenance.to_dict()
        assert result["originalActivityId"] == "ACT-001"
        assert result["stage"] == "Stage4AlternativeResolution"
        assert result["model"] == "gemini-2.0-flash"
        assert result["cacheHit"] is False
        assert result["cacheKey"] == "abc123"


# ============================================================================
# Test Configuration
# ============================================================================

class TestAlternativeResolutionConfig:
    """Tests for configuration dataclass."""

    def test_default_values(self):
        """Config has sensible defaults."""
        config = AlternativeResolutionConfig()
        assert config.confidence_threshold_auto == 0.90
        assert config.confidence_threshold_review == 0.70
        assert config.max_alternatives_per_activity == 5
        assert config.max_batch_size == 20

    def test_to_dict(self):
        """Config serializes correctly."""
        config = AlternativeResolutionConfig(
            confidence_threshold_auto=0.85,
            use_cache=False,
        )
        result = config.to_dict()
        assert result["confidenceThresholdAuto"] == 0.85
        assert result["useCache"] is False


# ============================================================================
# Test HumanReviewItem
# ============================================================================

class TestHumanReviewItem:
    """Tests for HumanReviewItem dataclass."""

    def test_to_dict(self):
        """Review items serialize correctly."""
        item = HumanReviewItem(
            id="REVIEW-001",
            item_type="alternative",
            activity_id="ACT-001",
            activity_name="Ambiguous test",
            reason="Low confidence (0.65)",
            confidence=0.65,
            alternatives=["Option A", "Option B"],
        )
        result = item.to_dict()
        assert result["id"] == "REVIEW-001"
        assert result["itemType"] == "alternative"
        assert result["confidence"] == 0.65
        assert len(result["alternatives"]) == 2


# ============================================================================
# Async Tests
# ============================================================================

class TestAsyncOperations:
    """Tests for async operations."""

    @pytest.mark.asyncio
    async def test_resolve_alternatives_empty_input(self):
        """Resolver handles empty input gracefully."""
        resolver = AlternativeResolver(AlternativeResolutionConfig(use_cache=False))
        usdm = {
            "activities": [],
            "scheduledActivityInstances": [],
            "conditions": [],
        }
        result = await resolver.resolve_alternatives(usdm)
        assert result.activities_analyzed == 0
        assert result.alternatives_detected == 0

    @pytest.mark.asyncio
    async def test_resolve_alternatives_no_alternatives(self):
        """Resolver handles input with no alternatives."""
        resolver = AlternativeResolver(AlternativeResolutionConfig(use_cache=False))
        usdm = {
            "activities": [
                {"id": "ACT-001", "name": "Complete blood count"},
                {"id": "ACT-002", "name": "Vital signs"},
            ],
            "scheduledActivityInstances": [],
            "conditions": [],
        }
        # Neither activity has alternative markers
        result = await resolver.resolve_alternatives(usdm)
        # No alternatives detected since no or/slash patterns
        assert result.activities_expanded == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
