"""
Unit tests for ComponentValidator (LLM-based component validation).

Tests:
- ValidatedComponent, DeduplicationGroup, ComponentValidationResult dataclasses
- Cache operations (load, save, lookup)
- Confidence threshold logic
- LLM validation with mocked responses
- Candidate extraction from snippets

Run with: python -m pytest soa_analyzer/tests/test_component_validator.py -v
"""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import os

# Import the ComponentValidator and related classes
from soa_analyzer.interpretation.component_validator import (
    ComponentValidator,
    ValidatedComponent,
    DeduplicationGroup,
    ComponentValidationResult,
)


class TestValidatedComponent:
    """Tests for ValidatedComponent dataclass."""

    def test_creation(self):
        """Test basic ValidatedComponent creation."""
        comp = ValidatedComponent(
            name="Hemoglobin",
            is_valid=True,
            confidence=0.95,
            canonical_form="Hemoglobin",
            rationale="Standard hematology test, LOINC-codable",
        )

        assert comp.name == "Hemoglobin"
        assert comp.is_valid is True
        assert comp.confidence == 0.95
        assert comp.canonical_form == "Hemoglobin"
        assert comp.rationale == "Standard hematology test, LOINC-codable"
        assert comp.source == "llm"  # default

    def test_to_dict(self):
        """Test serialization to dictionary."""
        comp = ValidatedComponent(
            name="WBC",
            is_valid=True,
            confidence=0.95,
            canonical_form="White Blood Cell Count",
            rationale="Standard abbreviation",
            source="cache",
        )
        d = comp.to_dict()

        assert d["name"] == "WBC"
        assert d["is_valid"] is True
        assert d["confidence"] == 0.95
        assert d["canonical_form"] == "White Blood Cell Count"
        assert d["source"] == "cache"


class TestDeduplicationGroup:
    """Tests for DeduplicationGroup dataclass."""

    def test_creation(self):
        """Test basic DeduplicationGroup creation."""
        group = DeduplicationGroup(
            canonical="White Blood Cell Count",
            duplicates=["WBC", "White blood cell count", "Leukocyte Count"],
            confidence=0.95,
            rationale="All refer to the same hematology test",
        )

        assert group.canonical == "White Blood Cell Count"
        assert len(group.duplicates) == 3
        assert "WBC" in group.duplicates
        assert group.confidence == 0.95

    def test_to_dict(self):
        """Test serialization to dictionary."""
        group = DeduplicationGroup(
            canonical="Hemoglobin",
            duplicates=["Hgb", "HGB"],
            confidence=0.95,
            rationale="Standard abbreviations",
        )
        d = group.to_dict()

        assert d["canonical"] == "Hemoglobin"
        assert d["duplicates"] == ["Hgb", "HGB"]
        assert d["confidence"] == 0.95


class TestComponentValidationResult:
    """Tests for ComponentValidationResult dataclass."""

    def test_creation(self):
        """Test basic ComponentValidationResult creation."""
        valid_comps = [
            ValidatedComponent(
                name="Hemoglobin", is_valid=True, confidence=0.95,
                canonical_form="Hemoglobin", rationale="Valid"
            )
        ]
        rejected = [
            ValidatedComponent(
                name="per Table 2", is_valid=False, confidence=0.98,
                canonical_form=None, rationale="Procedural reference"
            )
        ]
        result = ComponentValidationResult(
            valid_components=valid_comps,
            rejected_components=rejected,
            review_items=[],
            deduplication_groups=[],
        )

        assert len(result.valid_components) == 1
        assert len(result.rejected_components) == 1
        assert len(result.review_items) == 0

    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = ComponentValidationResult(
            valid_components=[
                ValidatedComponent(
                    name="WBC", is_valid=True, confidence=0.95,
                    canonical_form="White Blood Cell Count", rationale="Valid"
                )
            ],
            rejected_components=[],
            review_items=[],
            deduplication_groups=[
                DeduplicationGroup(
                    canonical="White Blood Cell Count",
                    duplicates=["WBC"],
                    confidence=0.95,
                    rationale="Same test"
                )
            ],
            llm_calls=1,
            cache_hits=0,
            total_candidates=1,
        )
        d = result.to_dict()

        assert len(d["valid_components"]) == 1
        assert len(d["deduplication_groups"]) == 1
        assert d["metrics"]["llm_calls"] == 1

    def test_get_valid_names(self):
        """Test getting set of valid canonical names."""
        result = ComponentValidationResult(
            valid_components=[
                ValidatedComponent(
                    name="WBC", is_valid=True, confidence=0.95,
                    canonical_form="White Blood Cell Count", rationale="Valid"
                ),
                ValidatedComponent(
                    name="Hemoglobin", is_valid=True, confidence=0.95,
                    canonical_form="Hemoglobin", rationale="Valid"
                )
            ],
        )
        names = result.get_valid_names()

        assert "white blood cell count" in names
        assert "wbc" in names  # original name also included
        assert "hemoglobin" in names


class TestComponentValidator:
    """Tests for ComponentValidator class."""

    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary directory for cache testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def validator(self, temp_cache_dir):
        """Create a validator with a temporary cache directory."""
        return ComponentValidator(use_cache=True, cache_dir=temp_cache_dir)

    @pytest.fixture
    def validator_no_cache(self):
        """Create a validator without cache."""
        return ComponentValidator(use_cache=False)

    def test_initialization(self, validator):
        """Test validator initialization."""
        assert validator.use_cache is True
        assert validator._cache is not None
        assert isinstance(validator._cache, dict)

    def test_initialization_no_cache(self, validator_no_cache):
        """Test validator initialization without cache."""
        assert validator_no_cache.use_cache is False

    def test_check_cache_hit(self, validator):
        """Test cache hit scenario."""
        # Pre-populate cache
        validator._cache["hemoglobin"] = ValidatedComponent(
            name="Hemoglobin",
            is_valid=True,
            confidence=0.95,
            canonical_form="Hemoglobin",
            rationale="Standard test",
        )
        validator._cache["per table 2"] = ValidatedComponent(
            name="per Table 2",
            is_valid=False,
            confidence=0.98,
            canonical_form=None,
            rationale="Procedural reference",
        )
        validator._cache_loaded = True  # Mark as loaded

        candidates = [
            {"name": "Hemoglobin"},
            {"name": "per Table 2"},
            {"name": "New Test"},
        ]

        cached, uncached = validator._check_cache(candidates)

        assert len(cached) == 2
        assert len(uncached) == 1
        assert uncached[0]["name"] == "New Test"

    def test_check_cache_no_cache_mode(self, validator_no_cache):
        """Test cache check when cache is disabled."""
        candidates = [
            {"name": "Hemoglobin"},
            {"name": "WBC"},
        ]

        cached, uncached = validator_no_cache._check_cache(candidates)

        assert len(cached) == 0
        assert len(uncached) == 2

    def test_apply_thresholds_auto_accept(self, validator):
        """Test confidence threshold for auto-accept."""
        llm_result = {
            "validated_components": [
                {
                    "name": "Hemoglobin",
                    "is_valid": True,
                    "confidence": 0.95,  # >= 0.90, auto-accept
                    "canonical_form": "Hemoglobin",
                    "rationale": "Standard test",
                }
            ],
            "deduplication_groups": [],
        }

        valid, rejected, review = validator._apply_thresholds(llm_result)

        assert len(valid) == 1
        assert len(rejected) == 0
        assert len(review) == 0
        assert valid[0].name == "Hemoglobin"
        assert isinstance(valid[0], ValidatedComponent)

    def test_apply_thresholds_review(self, validator):
        """Test confidence threshold for review items."""
        llm_result = {
            "validated_components": [
                {
                    "name": "Neurological Evaluation",
                    "is_valid": True,
                    "confidence": 0.78,  # 0.70-0.89, needs review
                    "canonical_form": "Neurological Evaluation",
                    "rationale": "Ambiguous scope",
                }
            ],
            "deduplication_groups": [],
        }

        valid, rejected, review = validator._apply_thresholds(llm_result)

        assert len(valid) == 0
        assert len(rejected) == 0
        assert len(review) == 1
        assert review[0].name == "Neurological Evaluation"

    def test_apply_thresholds_reject_invalid(self, validator):
        """Test confidence threshold for rejection when is_valid is False."""
        llm_result = {
            "validated_components": [
                {
                    "name": "per Table 2",
                    "is_valid": False,
                    "confidence": 0.98,
                    "canonical_form": None,
                    "rationale": "Procedural reference",
                }
            ],
            "deduplication_groups": [],
        }

        valid, rejected, review = validator._apply_thresholds(llm_result)

        assert len(valid) == 0
        assert len(rejected) == 1
        assert len(review) == 0
        assert rejected[0].name == "per Table 2"

    def test_apply_thresholds_reject_low_confidence(self, validator):
        """Test confidence threshold for rejection due to low confidence."""
        llm_result = {
            "validated_components": [
                {
                    "name": "Unknown Thing",
                    "is_valid": True,
                    "confidence": 0.55,  # < 0.70, reject
                    "canonical_form": "Unknown Thing",
                    "rationale": "Too uncertain",
                }
            ],
            "deduplication_groups": [],
        }

        valid, rejected, review = validator._apply_thresholds(llm_result)

        assert len(valid) == 0
        assert len(rejected) == 1
        assert len(review) == 0

    def test_format_component_list(self, validator):
        """Test component list formatting for prompt."""
        candidates = [
            {"name": "Hemoglobin", "source_snippet": "Hematology tests include..."},
            {"name": "WBC"},
            {"name": "per Table 2", "source_snippet": "See per Table 2 for details"},
        ]

        formatted = validator._format_component_list(candidates)

        assert '1. "Hemoglobin"' in formatted
        assert '2. "WBC"' in formatted
        assert '3. "per Table 2"' in formatted

    def test_parse_response_valid_json(self, validator):
        """Test parsing valid LLM JSON response."""
        response = json.dumps({
            "validated_components": [
                {
                    "name": "Hemoglobin",
                    "is_valid": True,
                    "confidence": 0.95,
                    "canonical_form": "Hemoglobin",
                    "rationale": "Standard test",
                }
            ],
            "deduplication_groups": [],
            "summary": {"total_candidates": 1, "valid_count": 1},
        })

        result = validator._parse_response(response)

        assert result is not None
        assert "validated_components" in result
        assert len(result["validated_components"]) == 1
        assert result["validated_components"][0]["name"] == "Hemoglobin"

    def test_parse_response_with_markdown(self, validator):
        """Test parsing JSON wrapped in markdown code blocks."""
        response = """```json
{
    "validated_components": [
        {
            "name": "WBC",
            "is_valid": true,
            "confidence": 0.95,
            "canonical_form": "White Blood Cell Count",
            "rationale": "Standard abbreviation"
        }
    ],
    "deduplication_groups": []
}
```"""

        result = validator._parse_response(response)

        assert result is not None
        assert "validated_components" in result
        assert result["validated_components"][0]["canonical_form"] == "White Blood Cell Count"

    def test_parse_response_invalid_json(self, validator):
        """Test parsing invalid JSON returns None."""
        result = validator._parse_response("This is not JSON at all")
        assert result is None

    def test_conservative_fallback(self, validator):
        """Test conservative fallback when LLM fails."""
        candidates = [
            {"name": "Hemoglobin"},
            {"name": "WBC"},
        ]

        result = validator._conservative_fallback(candidates)

        assert "validated_components" in result
        assert len(result["validated_components"]) == 2
        # Conservative fallback should mark as needing review (0.75 confidence)
        for comp in result["validated_components"]:
            assert comp["confidence"] == 0.75
            assert comp["is_valid"] is True

    @pytest.mark.asyncio
    async def test_validate_components_cache_only(self, validator):
        """Test validation when all candidates are in cache."""
        # Pre-populate cache
        validator._cache["hemoglobin"] = ValidatedComponent(
            name="Hemoglobin",
            is_valid=True,
            confidence=0.95,
            canonical_form="Hemoglobin",
            rationale="Standard test",
        )
        validator._cache["wbc"] = ValidatedComponent(
            name="WBC",
            is_valid=True,
            confidence=0.95,
            canonical_form="White Blood Cell Count",
            rationale="Standard test",
        )
        validator._cache_loaded = True

        candidates = [
            {"name": "Hemoglobin"},
            {"name": "WBC"},
        ]

        result = await validator.validate_components(
            candidates, "Hematology", "LB"
        )

        assert len(result.valid_components) == 2
        assert len(result.rejected_components) == 0
        assert result.cache_hits == 2
        assert result.llm_calls == 0

    @pytest.mark.asyncio
    async def test_validate_components_with_llm(self, validator):
        """Test validation with mocked LLM call."""
        # Mock the LLM call - _call_gemini returns parsed dict (not JSON string)
        mock_response = {
            "validated_components": [
                {
                    "name": "Hemoglobin",
                    "is_valid": True,
                    "confidence": 0.95,
                    "canonical_form": "Hemoglobin",
                    "rationale": "Standard hematology test",
                },
                {
                    "name": "per Table 2",
                    "is_valid": False,
                    "confidence": 0.98,
                    "canonical_form": None,
                    "rationale": "Procedural reference",
                }
            ],
            "deduplication_groups": [],
            "summary": {"total_candidates": 2, "valid_count": 1, "invalid_count": 1},
        }

        with patch.object(
            validator, "_call_gemini", new=AsyncMock(return_value=mock_response)
        ):
            candidates = [
                {"name": "Hemoglobin"},
                {"name": "per Table 2"},
            ]

            result = await validator.validate_components(
                candidates, "Hematology", "LB"
            )

            assert len(result.valid_components) == 1
            assert len(result.rejected_components) == 1
            assert result.valid_components[0].name == "Hemoglobin"
            assert result.rejected_components[0].name == "per Table 2"
            assert result.llm_calls == 1

    @pytest.mark.asyncio
    async def test_validate_components_empty_input(self, validator):
        """Test with empty candidate list."""
        result = await validator.validate_components([], "Hematology", "LB")

        assert len(result.valid_components) == 0
        assert len(result.rejected_components) == 0
        assert len(result.review_items) == 0
        assert result.total_candidates == 0


class TestIntegration:
    """Integration tests for Stage 2 with ComponentValidator."""

    def test_extract_candidates_from_snippets(self):
        """Test candidate extraction from text snippets."""
        from soa_analyzer.interpretation.stage2_activity_expansion import ActivityExpander

        expander = ActivityExpander()

        components = [
            {
                "name": "CBC",
                "text_snippet": "Hematology panel includes WBC, RBC, Hemoglobin, Hematocrit, Platelet Count",
                "page_number": 45,
                "source": "pdf_text",
            }
        ]

        candidates = expander._extract_candidates_from_snippets(components)

        # Should have extracted components from comma-separated list
        assert len(candidates) > 0
        names = [c["name"] for c in candidates]
        # Check that comma-separated items were extracted
        assert any("WBC" in n for n in names)
        assert any("RBC" in n for n in names)


class TestDeduplicationGroups:
    """Tests for deduplication group handling."""

    @pytest.fixture
    def validator(self):
        """Create validator without cache."""
        return ComponentValidator(use_cache=False)

    def test_build_deduplication_groups(self, validator):
        """Test building deduplication groups from LLM result."""
        llm_result = {
            "validated_components": [],
            "deduplication_groups": [
                {
                    "canonical": "White Blood Cell Count",
                    "duplicates": ["WBC", "Leukocyte Count"],
                    "confidence": 0.95,
                    "rationale": "All refer to the same test",
                },
                {
                    "canonical": "Hemoglobin",
                    "duplicates": ["Hgb", "HGB"],
                    "confidence": 0.95,
                    "rationale": "Standard abbreviations",
                }
            ],
        }

        groups = validator._build_deduplication_groups(llm_result)

        assert len(groups) == 2
        assert groups[0].canonical == "White Blood Cell Count"
        assert "WBC" in groups[0].duplicates
        assert isinstance(groups[0], DeduplicationGroup)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
