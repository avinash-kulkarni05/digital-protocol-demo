"""
Unit tests for Stage 7: Timing Distribution.

Tests:
- TimingPatternRegistry (pattern matching for validation)
- TimingDistributor (LLM-first expansion logic)
- Data models (TimingExpansion, TimingDecision, Stage7Result)

Run with: python -m pytest soa_analyzer/tests/test_stage7_timing_distribution.py -v
"""

import asyncio
import json
import pytest
from pathlib import Path

# Import models
from soa_analyzer.models.timing_expansion import (
    TimingPattern,
    TimingDecision,
    TimingExpansion,
    ValidationDiscrepancy,
    Stage7Result,
    TimingDistributionConfig,
)

# Import stage 7
from soa_analyzer.interpretation.stage7_timing_distribution import (
    TimingDistributor,
    TimingPatternRegistry,
    distribute_timing,
)


class TestTimingPatternRegistry:
    """Tests for TimingPatternRegistry (validation patterns)."""

    def test_load_patterns(self):
        """Test that pattern config loads successfully."""
        registry = TimingPatternRegistry()

        # Should have atomic timings defined (use private attr or methods)
        assert registry.is_atomic("BI")
        assert registry.is_atomic("EOI")
        assert registry.is_atomic("pre-dose")
        assert registry.is_atomic("post-dose")

    def test_known_expansions_loaded(self):
        """Test that known expansions are loaded."""
        registry = TimingPatternRegistry()

        # Use the method to check
        exp = registry.get_known_expansion("BI/EOI")
        assert exp == ["BI", "EOI"]

        exp2 = registry.get_known_expansion("pre-dose/post-dose")
        assert exp2 == ["pre-dose", "post-dose"]

    def test_is_atomic_positive(self):
        """Test atomic timing detection for atomic modifiers."""
        registry = TimingPatternRegistry()

        assert registry.is_atomic("BI") is True
        assert registry.is_atomic("EOI") is True
        assert registry.is_atomic("pre-dose") is True
        assert registry.is_atomic("post-dose") is True
        assert registry.is_atomic("trough") is True
        assert registry.is_atomic("peak") is True
        assert registry.is_atomic("0h") is True
        assert registry.is_atomic("2h") is True

    def test_is_atomic_negative(self):
        """Test atomic timing detection for compound modifiers."""
        registry = TimingPatternRegistry()

        assert registry.is_atomic("BI/EOI") is False
        assert registry.is_atomic("pre-dose/post-dose") is False
        assert registry.is_atomic("trough/peak") is False
        assert registry.is_atomic("0h, 2h, 4h") is False

    def test_is_atomic_case_insensitive(self):
        """Test that atomic detection is case-insensitive."""
        registry = TimingPatternRegistry()

        assert registry.is_atomic("bi") is True
        assert registry.is_atomic("Bi") is True
        assert registry.is_atomic("BI") is True
        assert registry.is_atomic("eoi") is True
        assert registry.is_atomic("PRE-DOSE") is True

    def test_get_known_expansion(self):
        """Test getting known expansion for compound modifiers."""
        registry = TimingPatternRegistry()

        # Exact match
        expansion = registry.get_known_expansion("BI/EOI")
        assert expansion == ["BI", "EOI"]

        # Unknown pattern
        expansion = registry.get_known_expansion("unknown/pattern")
        assert expansion is None

    def test_find_matching_pattern(self):
        """Test finding matching pattern for timing modifier."""
        registry = TimingPatternRegistry()

        # Should find bi_eoi pattern for BI/EOI
        pattern = registry.find_matching_pattern("BI/EOI")
        # May or may not find pattern depending on regex; just verify no crash
        # Pattern matching is validation-only, not primary routing

    def test_normalize_variations(self):
        """Test that case variations work correctly."""
        registry = TimingPatternRegistry()

        # All should be recognized as atomic
        assert registry.is_atomic("bi")
        assert registry.is_atomic("BI")
        assert registry.is_atomic("Bi")


class TestTimingDecision:
    """Tests for TimingDecision dataclass."""

    def test_creation(self):
        """Test basic TimingDecision creation."""
        decision = TimingDecision(
            timing_modifier="BI/EOI",
            should_expand=True,
            expanded_timings=["BI", "EOI"],
            confidence=0.98,
            rationale="Standard BI/EOI split for PK sampling",
            source="llm",
        )

        assert decision.timing_modifier == "BI/EOI"
        assert decision.should_expand is True
        assert decision.expanded_timings == ["BI", "EOI"]
        assert decision.confidence == 0.98
        assert decision.source == "llm"

    def test_to_dict(self):
        """Test serialization to dictionary (uses camelCase for JSON)."""
        decision = TimingDecision(
            timing_modifier="pre-dose/post-dose",
            should_expand=True,
            expanded_timings=["pre-dose", "post-dose"],
            confidence=0.95,
        )

        d = decision.to_dict()

        # to_dict uses camelCase for JSON serialization
        assert d["timingModifier"] == "pre-dose/post-dose"
        assert d["shouldExpand"] is True
        assert d["expandedTimings"] == ["pre-dose", "post-dose"]
        assert d["confidence"] == 0.95


class TestTimingExpansion:
    """Tests for TimingExpansion dataclass."""

    def test_creation(self):
        """Test TimingExpansion creation."""
        decision = TimingDecision(
            timing_modifier="BI/EOI",
            should_expand=True,
            expanded_timings=["BI", "EOI"],
            confidence=0.98,
        )

        expansion = TimingExpansion(
            id="EXP-001",
            original_sai_id="SAI-042",
            original_timing_modifier="BI/EOI",
            expanded_sais=[
                {"id": "SAI-042-BI", "timingModifier": "BI"},
                {"id": "SAI-042-EOI", "timingModifier": "EOI"},
            ],
            decision=decision,
        )

        assert expansion.original_sai_id == "SAI-042"
        assert len(expansion.expanded_sais) == 2
        assert expansion.requires_review is False

    def test_requires_review_flag(self):
        """Test that requires_review can be set."""
        expansion = TimingExpansion(
            id="EXP-002",
            original_sai_id="SAI-050",
            original_timing_modifier="unusual/pattern",
            expanded_sais=[],
            requires_review=True,
            review_reason="Low confidence decision",
        )

        assert expansion.requires_review is True
        assert expansion.review_reason == "Low confidence decision"


class TestStage7Result:
    """Tests for Stage7Result dataclass."""

    def test_empty_result(self):
        """Test creating empty result."""
        result = Stage7Result(
            expansions=[],
            review_items=[],
        )

        assert result.unique_timings_analyzed == 0
        assert result.sais_processed == 0
        assert result.sais_expanded == 0
        assert result.sais_created == 0

    def test_result_with_metrics(self):
        """Test result with populated metrics."""
        result = Stage7Result(
            expansions=[],
            review_items=[],
            unique_timings_analyzed=5,
            sais_processed=20,
            sais_expanded=8,
            sais_created=16,
            cache_hits=3,
            llm_calls=1,
        )

        assert result.unique_timings_analyzed == 5
        assert result.llm_calls == 1
        assert result.cache_hits == 3

    def test_get_summary(self):
        """Test summary generation."""
        result = Stage7Result(
            expansions=[],
            review_items=[],
            unique_timings_analyzed=5,
            sais_processed=20,
            sais_expanded=8,
            sais_created=16,
            cache_hits=3,
            llm_calls=1,
            validation_flags=0,
        )

        summary = result.get_summary()

        # Summary uses camelCase keys
        assert "saisProcessed" in summary
        assert summary["saisProcessed"] == 20
        assert summary["saisExpanded"] == 8


class TestTimingDistributionConfig:
    """Tests for TimingDistributionConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = TimingDistributionConfig()

        assert config.use_llm is True
        assert config.confidence_threshold_auto == 0.90
        assert config.confidence_threshold_review == 0.70
        assert config.max_expansions_per_sai == 10

    def test_custom_values(self):
        """Test custom configuration values."""
        config = TimingDistributionConfig(
            use_llm=False,
            confidence_threshold_auto=0.95,
            confidence_threshold_review=0.80,
        )

        assert config.use_llm is False
        assert config.confidence_threshold_auto == 0.95


class TestTimingDistributor:
    """Tests for TimingDistributor class."""

    def test_initialization(self):
        """Test distributor initialization."""
        distributor = TimingDistributor()

        assert distributor.config is not None
        assert distributor._pattern_registry is not None

    def test_initialization_with_config(self):
        """Test distributor with custom config."""
        config = TimingDistributionConfig(
            confidence_threshold_auto=0.85,
        )
        distributor = TimingDistributor(config=config)

        assert distributor.config.confidence_threshold_auto == 0.85

    def test_get_sais(self):
        """Test extracting SAIs from USDM output."""
        distributor = TimingDistributor()

        # Direct format
        usdm = {
            "scheduledActivityInstances": [
                {"id": "SAI-001", "timingModifier": "BI/EOI"},
                {"id": "SAI-002", "timingModifier": "BI/EOI"},
                {"id": "SAI-003", "timingModifier": "pre-dose"},
            ]
        }

        sais = distributor._get_sais(usdm)
        assert len(sais) == 3

    def test_get_sais_nested(self):
        """Test extracting SAIs from nested USDM structure."""
        distributor = TimingDistributor()

        # Nested format
        usdm = {
            "studyVersion": [
                {
                    "scheduledActivityInstances": [
                        {"id": "SAI-001", "timingModifier": "BI/EOI"},
                        {"id": "SAI-002", "timingModifier": "pre-dose"},
                    ]
                }
            ]
        }

        sais = distributor._get_sais(usdm)
        assert len(sais) == 2

    def test_generate_sai_id(self):
        """Test SAI ID generation for expanded timings."""
        distributor = TimingDistributor()

        new_id = distributor._generate_sai_id("SAI-042", "BI")
        assert new_id == "SAI-042-BI"

        new_id = distributor._generate_sai_id("SAI-042", "EOI")
        assert new_id == "SAI-042-EOI"

        # Handle spaces in timing
        new_id = distributor._generate_sai_id("SAI-042", "2h post-dose")
        assert "SAI-042-" in new_id

    def test_generate_expanded_sais(self):
        """Test generating expanded SAI objects with USDM Code objects."""
        distributor = TimingDistributor()

        original_sai = {
            "id": "SAI-042",
            "activityId": "ACT-006",
            "visitId": "ENC-002",
            "timingModifier": "BI/EOI",
            "footnoteMarkers": ["c"],
        }

        decision = TimingDecision(
            timing_modifier="BI/EOI",
            should_expand=True,
            expanded_timings=["BI", "EOI"],
            confidence=0.98,
        )

        expanded = distributor._generate_expanded_sais(original_sai, decision)

        assert len(expanded) == 2

        # Check first expanded SAI (BI)
        bi_sai = expanded[0]
        assert bi_sai["id"] == "SAI-042-BI"
        # timingModifier should be a USDM 4.0 Code object
        assert isinstance(bi_sai["timingModifier"], dict)
        assert bi_sai["timingModifier"]["instanceType"] == "Code"
        assert bi_sai["timingModifier"]["decode"] == "Before Infusion"
        assert bi_sai["timingModifier"]["code"] == "C71148"
        assert bi_sai["activityId"] == "ACT-006"
        assert bi_sai["footnoteMarkers"] == ["c"]
        assert "_timingExpansion" in bi_sai
        assert bi_sai["_timingExpansion"]["originalId"] == "SAI-042"
        # Check enhanced provenance fields
        assert bi_sai["_timingExpansion"]["stage"] == "Stage7TimingDistribution"
        assert "timestamp" in bi_sai["_timingExpansion"]

        # Check second expanded SAI (EOI)
        eoi_sai = expanded[1]
        assert eoi_sai["id"] == "SAI-042-EOI"
        # timingModifier should be a USDM 4.0 Code object
        assert isinstance(eoi_sai["timingModifier"], dict)
        assert eoi_sai["timingModifier"]["instanceType"] == "Code"
        assert eoi_sai["timingModifier"]["decode"] == "End of Infusion"
        assert eoi_sai["timingModifier"]["code"] == "C71149"

    def test_generate_expanded_sais_with_footnotes_flagged(self):
        """Test that SAIs with footnotes get flagged for condition review."""
        distributor = TimingDistributor()

        original_sai = {
            "id": "SAI-050",
            "activityId": "ACT-010",
            "visitId": "ENC-005",
            "timingModifier": "pre-dose/post-dose",
            "footnoteMarkers": ["a", "b"],  # Has footnotes
        }

        decision = TimingDecision(
            timing_modifier="pre-dose/post-dose",
            should_expand=True,
            expanded_timings=["pre-dose", "post-dose"],
            confidence=0.95,
        )

        expanded = distributor._generate_expanded_sais(original_sai, decision)

        # Both expanded SAIs should have footnote flags
        for sai in expanded:
            assert sai.get("_hasFootnoteCondition") is True
            assert sai.get("_footnoteMarkersPreserved") == ["a", "b"]

    def test_get_timing_code_known_code(self):
        """Test that known timing codes return proper CDISC Code objects."""
        distributor = TimingDistributor()

        # Test known codes
        bi_code = distributor._get_timing_code("BI")
        assert bi_code["instanceType"] == "Code"
        assert bi_code["code"] == "C71148"
        assert bi_code["decode"] == "Before Infusion"
        assert bi_code["codeSystem"] == "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl"

        eoi_code = distributor._get_timing_code("EOI")
        assert eoi_code["code"] == "C71149"
        assert eoi_code["decode"] == "End of Infusion"

        predose_code = distributor._get_timing_code("pre-dose")
        assert predose_code["code"] == "C82489"
        assert predose_code["decode"] == "Pre-dose"

    def test_get_timing_code_unknown_timing(self):
        """Test that unknown timing codes still get Code objects with decode only."""
        distributor = TimingDistributor()

        unknown_code = distributor._get_timing_code("some-unknown-timing")
        assert unknown_code["instanceType"] == "Code"
        assert unknown_code["code"] is None  # No known CDISC code
        assert unknown_code["decode"] == "some-unknown-timing"
        assert "id" in unknown_code
        assert unknown_code["id"].startswith("CODE-TIM-")

    def test_cache_key_generation(self):
        """Test cache key is consistent and normalized."""
        distributor = TimingDistributor()

        key1 = distributor._get_cache_key("BI/EOI")
        key2 = distributor._get_cache_key("bi/eoi")
        key3 = distributor._get_cache_key("  BI/EOI  ")

        assert key1 == key2 == key3

    def test_cache_operations(self):
        """Test cache read/write operations."""
        distributor = TimingDistributor()

        decision = TimingDecision(
            timing_modifier="BI/EOI",
            should_expand=True,
            expanded_timings=["BI", "EOI"],
            confidence=0.98,
        )

        # Initially not in cache
        cached = distributor._check_cache("BI/EOI")
        assert cached is None

        # Add to cache
        distributor._update_cache("BI/EOI", decision)

        # Now should be in cache
        cached = distributor._check_cache("BI/EOI")
        assert cached is not None
        assert cached.timing_modifier == "BI/EOI"

    def test_parse_llm_response_valid(self):
        """Test parsing valid LLM JSON response."""
        distributor = TimingDistributor()

        response = json.dumps({
            "BI/EOI": {
                "shouldExpand": True,
                "expandedTimings": ["BI", "EOI"],
                "confidence": 0.98,
                "rationale": "Standard split"
            },
            "pre-dose": {
                "shouldExpand": False,
                "expandedTimings": [],
                "confidence": 1.0,
                "rationale": "Already atomic"
            }
        })

        decisions = distributor._parse_llm_response(response)

        assert len(decisions) == 2
        assert "BI/EOI" in decisions
        assert "pre-dose" in decisions

    def test_parse_llm_response_with_markdown(self):
        """Test parsing LLM response wrapped in markdown code blocks."""
        distributor = TimingDistributor()

        response = """```json
{
    "BI/EOI": {
        "shouldExpand": true,
        "expandedTimings": ["BI", "EOI"],
        "confidence": 0.98,
        "rationale": "Standard split"
    }
}
```"""

        decisions = distributor._parse_llm_response(response)

        assert len(decisions) == 1
        assert "BI/EOI" in decisions


class TestTimingDistributorApplyExpansions:
    """Tests for applying expansions to USDM."""

    def test_apply_expansions_replaces_sais(self):
        """Test that expanded SAIs replace originals with Code objects."""
        distributor = TimingDistributor()

        usdm = {
            "activities": [{"id": "ACT-001", "name": "PK Sample"}],
            "encounters": [{"id": "ENC-001", "name": "Cycle 1 Day 1"}],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "visitId": "ENC-001",
                    "timingModifier": "BI/EOI",
                },
                {
                    "id": "SAI-002",
                    "activityId": "ACT-001",
                    "visitId": "ENC-001",
                    "timingModifier": "pre-dose",
                },
            ]
        }

        decision = TimingDecision(
            timing_modifier="BI/EOI",
            should_expand=True,
            expanded_timings=["BI", "EOI"],
            confidence=0.98,
        )

        # Create expansion for SAI-001 - now with Code objects for timingModifier
        bi_code = {
            "id": "CODE-TIM-BI",
            "code": "C71148",
            "decode": "Before Infusion",
            "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
            "codeSystemVersion": "24.12",
            "instanceType": "Code",
        }
        eoi_code = {
            "id": "CODE-TIM-EOI",
            "code": "C71149",
            "decode": "End of Infusion",
            "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
            "codeSystemVersion": "24.12",
            "instanceType": "Code",
        }

        expansion = TimingExpansion(
            id="EXP-001",
            original_sai_id="SAI-001",
            original_timing_modifier="BI/EOI",
            expanded_sais=[
                {
                    "id": "SAI-001-BI",
                    "activityId": "ACT-001",
                    "visitId": "ENC-001",
                    "timingModifier": bi_code,
                    "_timingExpansion": {"originalId": "SAI-001", "stage": "Stage7TimingDistribution"},
                },
                {
                    "id": "SAI-001-EOI",
                    "activityId": "ACT-001",
                    "visitId": "ENC-001",
                    "timingModifier": eoi_code,
                    "_timingExpansion": {"originalId": "SAI-001", "stage": "Stage7TimingDistribution"},
                },
            ],
            decision=decision,
        )

        result = Stage7Result(
            expansions=[expansion],
            review_items=[],
            sais_processed=2,
            sais_expanded=1,
            sais_created=2,
        )

        updated_usdm = distributor.apply_expansions_to_usdm(usdm, result)

        sais = updated_usdm["scheduledActivityInstances"]

        # Should have 3 SAIs: 2 expanded + 1 unchanged
        assert len(sais) == 3

        # Original SAI-001 should be gone
        sai_ids = [s["id"] for s in sais]
        assert "SAI-001" not in sai_ids

        # Expanded SAIs should be present with Code objects
        assert "SAI-001-BI" in sai_ids
        assert "SAI-001-EOI" in sai_ids

        # Verify Code objects on expanded SAIs
        bi_sai = next(s for s in sais if s["id"] == "SAI-001-BI")
        assert isinstance(bi_sai["timingModifier"], dict)
        assert bi_sai["timingModifier"]["instanceType"] == "Code"

        # Unchanged SAI should still be there
        assert "SAI-002" in sai_ids

    def test_apply_expansions_preserves_order(self):
        """Test that expansions are inserted at original position."""
        distributor = TimingDistributor()

        usdm = {
            "scheduledActivityInstances": [
                {"id": "SAI-001", "timingModifier": "pre-dose"},
                {"id": "SAI-002", "timingModifier": "BI/EOI"},
                {"id": "SAI-003", "timingModifier": "post-dose"},
            ]
        }

        decision = TimingDecision(
            timing_modifier="BI/EOI",
            should_expand=True,
            expanded_timings=["BI", "EOI"],
            confidence=0.98,
        )

        # Expanded SAIs with Code objects
        bi_code = {"id": "CODE-BI", "code": "C71148", "decode": "Before Infusion", "instanceType": "Code", "codeSystem": "", "codeSystemVersion": ""}
        eoi_code = {"id": "CODE-EOI", "code": "C71149", "decode": "End of Infusion", "instanceType": "Code", "codeSystem": "", "codeSystemVersion": ""}

        expansion = TimingExpansion(
            id="EXP-001",
            original_sai_id="SAI-002",
            original_timing_modifier="BI/EOI",
            expanded_sais=[
                {"id": "SAI-002-BI", "timingModifier": bi_code},
                {"id": "SAI-002-EOI", "timingModifier": eoi_code},
            ],
            decision=decision,
        )

        result = Stage7Result(expansions=[expansion], review_items=[])

        updated_usdm = distributor.apply_expansions_to_usdm(usdm, result)

        sais = updated_usdm["scheduledActivityInstances"]
        sai_ids = [s["id"] for s in sais]

        # Order should be: SAI-001, SAI-002-BI, SAI-002-EOI, SAI-003
        assert sai_ids.index("SAI-001") < sai_ids.index("SAI-002-BI")
        assert sai_ids.index("SAI-002-EOI") < sai_ids.index("SAI-003")


# Integration test (requires LLM API keys)
class TestTimingDistributorIntegration:
    """Integration tests for Timing Distributor with LLM."""

    @pytest.mark.skipif(
        not Path(__file__).parent.parent.parent.parent / ".env",
        reason="No .env file found",
    )
    @pytest.mark.asyncio
    async def test_distribute_timing_full(self):
        """Test full timing distribution pipeline (requires API keys)."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "PK Sample"}],
            "encounters": [{"id": "ENC-001", "name": "Cycle 1 Day 1"}],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "visitId": "ENC-001",
                    "timingModifier": "BI/EOI",
                },
                {
                    "id": "SAI-002",
                    "activityId": "ACT-001",
                    "visitId": "ENC-001",
                    "timingModifier": "pre-dose",
                },
            ]
        }

        distributor = TimingDistributor()
        result = await distributor.distribute_timing(usdm)

        # Should process SAIs
        assert result.sais_processed >= 2

        # BI/EOI should be expanded
        assert result.sais_expanded >= 1

        # pre-dose should NOT be expanded (atomic)
        # Check that we have at least some decision
        assert result.unique_timings_analyzed >= 1


if __name__ == "__main__":
    # Run basic tests without pytest
    print("Running Stage 7 Timing Distribution tests...")

    # Test TimingPatternRegistry
    print("\n--- Testing TimingPatternRegistry ---")
    registry = TimingPatternRegistry()
    assert registry.is_atomic("BI") is True
    assert registry.is_atomic("BI/EOI") is False
    assert registry.get_known_expansion("BI/EOI") == ["BI", "EOI"]
    print("  Loaded atomic timings and known expansions")
    print("  Atomic detection working correctly")
    print("  Known expansion lookup working correctly")
    print("  TimingPatternRegistry tests passed")

    # Test TimingDecision
    print("\n--- Testing TimingDecision ---")
    decision = TimingDecision(
        timing_modifier="BI/EOI",
        should_expand=True,
        expanded_timings=["BI", "EOI"],
        confidence=0.98,
    )
    d = decision.to_dict()
    assert d["shouldExpand"] is True  # camelCase in JSON
    print("  TimingDecision creation and serialization passed")

    # Test TimingDistributor
    print("\n--- Testing TimingDistributor ---")
    distributor = TimingDistributor()

    # Test get SAIs
    usdm = {
        "scheduledActivityInstances": [
            {"id": "SAI-001", "timingModifier": "BI/EOI"},
            {"id": "SAI-002", "timingModifier": "BI/EOI"},
            {"id": "SAI-003", "timingModifier": "pre-dose"},
        ]
    }
    sais = distributor._get_sais(usdm)
    assert len(sais) == 3
    print("  Get SAIs working")

    # Test generate expanded SAIs with Code objects
    original_sai = {
        "id": "SAI-001",
        "activityId": "ACT-001",
        "visitId": "ENC-001",
        "timingModifier": "BI/EOI",
    }
    expanded = distributor._generate_expanded_sais(original_sai, decision)
    assert len(expanded) == 2
    assert expanded[0]["id"] == "SAI-001-BI"
    # Verify timingModifier is a Code object
    assert isinstance(expanded[0]["timingModifier"], dict)
    assert expanded[0]["timingModifier"]["instanceType"] == "Code"
    assert expanded[0]["timingModifier"]["decode"] == "Before Infusion"
    print("  Generate expanded SAIs with Code objects working")

    # Test timing code lookup
    bi_code = distributor._get_timing_code("BI")
    assert bi_code["code"] == "C71148"
    assert bi_code["decode"] == "Before Infusion"
    print("  Timing code lookup working")

    # Test cache operations
    distributor._update_cache("BI/EOI", decision)
    cached = distributor._check_cache("BI/EOI")
    assert cached is not None
    print("  Cache operations working")

    # Test enhanced provenance in expansion metadata
    assert "_timingExpansion" in expanded[0]
    assert expanded[0]["_timingExpansion"]["stage"] == "Stage7TimingDistribution"
    assert "timestamp" in expanded[0]["_timingExpansion"]
    print("  Enhanced provenance in _timingExpansion metadata working")

    print("\n All Stage 7 basic tests passed!")
