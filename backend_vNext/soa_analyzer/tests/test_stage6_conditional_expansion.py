"""
Unit tests for Stage 6: Conditional Expansion.

Tests the extraction of conditions from SOA footnotes and linking to SAIs.
"""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from soa_analyzer.interpretation.stage6_conditional_expansion import (
    ConditionalExpander,
    ConditionalExpansionConfig,
    ConditionExtraction,
    ConditionPatternRegistry,
    Stage6Result,
    expand_conditions,
)
from soa_analyzer.models.condition import ConditionType


class TestConditionPatternRegistry:
    """Tests for the pattern validation registry."""

    def test_load_patterns(self):
        """Test loading patterns from config file."""
        registry = ConditionPatternRegistry()
        # Should load without error
        assert registry is not None

    def test_is_likely_non_condition(self):
        """Test detection of non-condition footnotes."""
        registry = ConditionPatternRegistry()

        # Should be non-conditions
        assert registry.is_likely_non_condition("Refer to Appendix B for details")
        assert registry.is_likely_non_condition("See section 8.1")
        assert registry.is_likely_non_condition("Must be performed before dosing")

        # Should be conditions (not matched as non-condition)
        assert not registry.is_likely_non_condition("Female subjects only")
        assert not registry.is_likely_non_condition("If clinically indicated")

    def test_get_pattern_match_demographic(self):
        """Test pattern matching for demographic conditions."""
        registry = ConditionPatternRegistry()

        # Female condition
        result = registry.get_pattern_match("For female subjects only")
        assert result is not None
        assert result[0] == "DEMOGRAPHIC_SEX"

        # WOCBP condition
        result = registry.get_pattern_match("Women of childbearing potential")
        assert result is not None
        assert result[0] == "DEMOGRAPHIC_FERTILITY"

        # Elderly condition
        result = registry.get_pattern_match("Subjects ≥65 years of age")
        assert result is not None
        assert result[0] == "DEMOGRAPHIC_AGE"

    def test_get_pattern_match_clinical(self):
        """Test pattern matching for clinical conditions."""
        registry = ConditionPatternRegistry()

        # Clinical indication
        result = registry.get_pattern_match("Perform if clinically indicated")
        assert result is not None
        assert result[0] == "CLINICAL_INDICATION"

        # Optional
        result = registry.get_pattern_match("At investigator discretion")
        assert result is not None
        assert result[0] == "VISIT_OPTIONAL"


class TestConditionExtraction:
    """Tests for ConditionExtraction dataclass."""

    def test_create_extraction(self):
        """Test creating a condition extraction."""
        extraction = ConditionExtraction(
            footnote_marker="a",
            footnote_text="For female subjects only",
            has_condition=True,
            condition_type="DEMOGRAPHIC_SEX",
            condition_name="Female Only",
            condition_text="For female subjects only",
            criterion={"sex": "F"},
            confidence=0.95,
            rationale="Explicit female population",
            source="llm",
        )

        assert extraction.footnote_marker == "a"
        assert extraction.has_condition is True
        assert extraction.confidence == 0.95

    def test_extraction_without_condition(self):
        """Test extraction that has no condition."""
        extraction = ConditionExtraction(
            footnote_marker="b",
            footnote_text="Refer to Appendix B",
            has_condition=False,
            rationale="Cross-reference, not a condition",
            source="llm",
        )

        assert extraction.has_condition is False
        assert extraction.condition_type is None


class TestStage6Result:
    """Tests for Stage6Result dataclass."""

    def test_empty_result(self):
        """Test empty result."""
        result = Stage6Result()
        assert result.conditions_created == 0
        assert result.footnotes_analyzed == 0
        summary = result.get_summary()
        assert summary["condition_coverage"] == 0

    def test_result_with_conditions(self):
        """Test result with conditions."""
        from soa_analyzer.models.condition import Condition

        result = Stage6Result()
        result.conditions.append(
            Condition(name="Test", text="Test condition")
        )
        result.conditions_created = 1
        result.footnotes_analyzed = 3
        result.high_confidence = 1

        summary = result.get_summary()
        assert summary["conditions_created"] == 1
        assert summary["condition_coverage"] == pytest.approx(1/3)


class TestConditionalExpander:
    """Tests for the ConditionalExpander class."""

    def test_init_default_config(self):
        """Test initialization with default config."""
        expander = ConditionalExpander()
        assert expander.config.use_llm is True
        assert expander.config.confidence_threshold_auto == 0.90

    def test_init_custom_config(self):
        """Test initialization with custom config."""
        config = ConditionalExpansionConfig(
            use_llm=False,
            confidence_threshold_auto=0.95,
        )
        expander = ConditionalExpander(config)
        assert expander.config.use_llm is False
        assert expander.config.confidence_threshold_auto == 0.95

    def test_cache_key_generation(self):
        """Test cache key generation is consistent."""
        expander = ConditionalExpander()

        key1 = expander._get_cache_key("Female subjects only")
        key2 = expander._get_cache_key("female subjects only")
        key3 = expander._get_cache_key("  Female subjects only  ")

        # Keys should be the same after normalization
        assert key1 == key2 == key3

    def test_parse_condition_type(self):
        """Test condition type parsing."""
        expander = ConditionalExpander()

        assert expander._parse_condition_type("DEMOGRAPHIC_SEX") == ConditionType.DEMOGRAPHIC_SEX
        assert expander._parse_condition_type("CLINICAL_INDICATION") == ConditionType.CLINICAL_INDICATION
        assert expander._parse_condition_type("VISIT_OPTIONAL") == ConditionType.VISIT_OPTIONAL
        assert expander._parse_condition_type("UNKNOWN_TYPE") is None
        assert expander._parse_condition_type(None) is None

    @pytest.mark.asyncio
    async def test_expand_conditions_empty_footnotes(self):
        """Test expansion with no footnotes."""
        expander = ConditionalExpander()
        usdm = {"footnotes": []}

        result = await expander.expand_conditions(usdm)

        assert result.footnotes_analyzed == 0
        assert result.conditions_created == 0

    @pytest.mark.asyncio
    async def test_expand_conditions_no_llm(self):
        """Test expansion without LLM (cache only)."""
        config = ConditionalExpansionConfig(use_llm=False)
        expander = ConditionalExpander(config)

        usdm = {
            "footnotes": [
                {"marker": "a", "text": "For female subjects only"},
            ]
        }

        result = await expander.expand_conditions(usdm)

        # Without LLM and without cache, no conditions created
        assert result.footnotes_analyzed == 1
        # Cache will be empty, so no conditions from this run
        assert result.llm_calls == 0

    def test_parse_llm_response_valid(self):
        """Test parsing valid LLM response."""
        expander = ConditionalExpander()

        response = json.dumps({
            "conditions": [
                {
                    "footnote_marker": "a",
                    "has_condition": True,
                    "condition_type": "DEMOGRAPHIC_SEX",
                    "condition_name": "Female Only",
                    "condition_text": "For female subjects only",
                    "criterion": {"sex": "F"},
                    "confidence": 0.95,
                    "rationale": "Explicit female population",
                },
                {
                    "footnote_marker": "b",
                    "has_condition": False,
                    "rationale": "Cross-reference",
                },
            ]
        })

        footnotes = [
            {"marker": "a", "text": "For female subjects only"},
            {"marker": "b", "text": "See Appendix B"},
        ]

        result = expander._parse_llm_response(response, footnotes)

        assert "a" in result
        assert "b" in result
        assert result["a"].has_condition is True
        assert result["b"].has_condition is False

    def test_parse_llm_response_with_markdown(self):
        """Test parsing LLM response with markdown code fences."""
        expander = ConditionalExpander()

        response = """```json
{
    "conditions": [
        {
            "footnote_marker": "a",
            "has_condition": true,
            "condition_type": "CLINICAL_INDICATION",
            "condition_name": "Clinically Indicated",
            "condition_text": "If clinically indicated",
            "confidence": 0.90,
            "rationale": "Clinical judgment required"
        }
    ]
}
```"""

        footnotes = [{"marker": "a", "text": "If clinically indicated"}]

        result = expander._parse_llm_response(response, footnotes)

        assert "a" in result
        assert result["a"].has_condition is True
        assert result["a"].condition_type == "CLINICAL_INDICATION"

    def test_parse_llm_response_invalid_json(self):
        """Test parsing invalid JSON response."""
        expander = ConditionalExpander()

        response = "This is not valid JSON"
        footnotes = [{"marker": "a", "text": "Test"}]

        result = expander._parse_llm_response(response, footnotes)

        # Should return empty dict on error
        assert result == {}

    def test_apply_conditions_to_usdm(self):
        """Test applying conditions to USDM output."""
        from soa_analyzer.models.condition import Condition

        expander = ConditionalExpander()

        # Create result with a condition
        result = Stage6Result()
        condition = Condition(
            name="Female Only",
            text="For female subjects only",
            source_footnote_marker="a",
        )
        result.conditions.append(condition)
        result.marker_to_condition["a"] = condition.id

        # USDM with SAI having footnote marker
        usdm = {
            "conditions": [],
            "conditionAssignments": [],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "footnoteMarkers": ["a"],
                    "_hasFootnoteCondition": True,
                }
            ],
        }

        updated = expander.apply_conditions_to_usdm(usdm, result)

        # Condition should be added
        assert len(updated["conditions"]) == 1
        assert updated["conditions"][0]["name"] == "Female Only"

        # Assignment should be created
        assert len(updated["conditionAssignments"]) == 1
        assert updated["conditionAssignments"][0]["conditionTargetId"] == "SAI-001"

        # SAI should have defaultConditionId set
        assert updated["scheduledActivityInstances"][0]["defaultConditionId"] == condition.id

        # Stage 7 flags should be removed
        assert "_hasFootnoteCondition" not in updated["scheduledActivityInstances"][0]

    def test_apply_conditions_deduplication(self):
        """Test that duplicate conditions are not created."""
        from soa_analyzer.models.condition import Condition

        expander = ConditionalExpander()

        # Create result with duplicate conditions
        result = Stage6Result()
        condition = Condition(
            name="Female Only",
            text="For female subjects only",
        )
        result.conditions.append(condition)
        result.marker_to_condition["a"] = condition.id
        result.marker_to_condition["c"] = condition.id  # Same condition

        usdm = {
            "conditions": [],
            "conditionAssignments": [],
            "scheduledActivityInstances": [
                {"id": "SAI-001", "footnoteMarkers": ["a"]},
                {"id": "SAI-002", "footnoteMarkers": ["c"]},
            ],
        }

        updated = expander.apply_conditions_to_usdm(usdm, result)

        # Only one condition should be added
        assert len(updated["conditions"]) == 1

        # But two assignments should be created
        assert len(updated["conditionAssignments"]) == 2


class TestExpandConditionsConvenience:
    """Tests for the expand_conditions convenience function."""

    @pytest.mark.asyncio
    async def test_expand_conditions_function(self):
        """Test the convenience function."""
        usdm = {
            "footnotes": [],
            "conditions": [],
            "conditionAssignments": [],
            "scheduledActivityInstances": [],
        }

        updated, result = await expand_conditions(usdm)

        assert isinstance(result, Stage6Result)
        assert "conditions" in updated


class TestConditionPatternValidation:
    """Tests for pattern validation in Stage 6."""

    def test_demographic_sex_patterns(self):
        """Test demographic sex pattern matching."""
        registry = ConditionPatternRegistry()

        female_texts = [
            "For female subjects only",
            "Women only",
            "Female patients",
        ]

        for text in female_texts:
            result = registry.get_pattern_match(text)
            assert result is not None, f"Failed to match: {text}"
            assert result[0] == "DEMOGRAPHIC_SEX"

    def test_fertility_patterns(self):
        """Test fertility pattern matching."""
        registry = ConditionPatternRegistry()

        fertility_texts = [
            "Women of childbearing potential",
            "WOCBP",
            "Females of reproductive potential",
        ]

        for text in fertility_texts:
            result = registry.get_pattern_match(text)
            assert result is not None, f"Failed to match: {text}"
            assert result[0] == "DEMOGRAPHIC_FERTILITY"

    def test_clinical_indication_patterns(self):
        """Test clinical indication pattern matching."""
        registry = ConditionPatternRegistry()

        clinical_texts = [
            "If clinically indicated",
            "As needed",
            "When indicated",
        ]

        for text in clinical_texts:
            result = registry.get_pattern_match(text)
            assert result is not None, f"Failed to match: {text}"
            assert result[0] == "CLINICAL_INDICATION"

    def test_visit_optional_patterns(self):
        """Test visit optional pattern matching."""
        registry = ConditionPatternRegistry()

        optional_texts = [
            "At investigator discretion",
            "Optional",
            "May be performed",
        ]

        for text in optional_texts:
            result = registry.get_pattern_match(text)
            assert result is not None, f"Failed to match: {text}"
            assert result[0] == "VISIT_OPTIONAL"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
