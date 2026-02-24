"""
Unit tests for SOA Table Classifier

Tests the SOATableClassifier class for structural feature computation,
LLM classification, caching, and pipeline integration.
"""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from soa_analyzer.interpretation.soa_table_classifier import (
    SOATableClassifier,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def classifier():
    """SOATableClassifier instance with caching disabled."""
    return SOATableClassifier(use_cache=False)


@pytest.fixture
def pk_heavy_usdm():
    """M21-195-like PK-heavy USDM output with dense timepoints."""
    return {
        "encounters": [
            {"id": "ENC-001", "name": "Screening", "recurrence": None},
            {"id": "ENC-002", "name": "Day 1", "parentVisit": "Day 1", "timingModifier": "Hour 0", "recurrence": None},
            {"id": "ENC-003", "name": "Day 1", "parentVisit": "Day 1", "timingModifier": "Hour 1", "recurrence": None},
            {"id": "ENC-004", "name": "Day 1", "parentVisit": "Day 1", "timingModifier": "Hour 3", "recurrence": None},
            {"id": "ENC-005", "name": "Day 1", "parentVisit": "Day 1", "timingModifier": "Hour 5", "recurrence": None},
            {"id": "ENC-006", "name": "Day 1", "parentVisit": "Day 1", "timingModifier": "Hour 7", "recurrence": None},
            {"id": "ENC-007", "name": "Day 1", "parentVisit": "Day 1", "timingModifier": "Hour 9", "recurrence": None},
            {"id": "ENC-008", "name": "Day 1", "parentVisit": "Day 1", "timingModifier": "Hour 11", "recurrence": None},
            {"id": "ENC-009", "name": "Day 7", "recurrence": None},
            {"id": "ENC-010", "name": "Day 14", "recurrence": None},
            {"id": "ENC-011", "name": "End of Study", "recurrence": None},
        ],
        "activities": [
            {"id": "ACT-001", "name": "PK Blood Draw", "categories": ["Laboratory"]},
            {"id": "ACT-002", "name": "Vital Signs", "categories": ["Vital Signs"]},
        ],
        "scheduledActivityInstances": [],
        "qualityMetrics": {
            "totalVisits": 11,
            "timepointEncounters": 7,
            "standaloneEncounters": 4,
            "visitsWithRecurrence": 0,
            "visitGroupCount": 1,
            "matrixCoverage": 0.65,
            "footnoteCategoryDistribution": {"dosing": 2, "pk": 3},
        },
        "visitGroups": {
            "Day 1": ["ENC-002", "ENC-003", "ENC-004", "ENC-005", "ENC-006", "ENC-007", "ENC-008"],
        },
    }


@pytest.fixture
def oncology_usdm():
    """Cyclic oncology USDM output with explicit cycle labels."""
    return {
        "encounters": [
            {"id": "ENC-001", "name": "Screening", "recurrence": None},
            {"id": "ENC-002", "name": "Cycle 1 Day 1", "recurrence": {"type": "PER_CYCLE", "cycleDay": 1, "maxCycles": 6}},
            {"id": "ENC-003", "name": "Cycle 1 Day 8", "recurrence": {"type": "PER_CYCLE", "cycleDay": 8, "maxCycles": 6}},
            {"id": "ENC-004", "name": "Cycle 1 Day 15", "recurrence": {"type": "PER_CYCLE", "cycleDay": 15, "maxCycles": 6}},
            {"id": "ENC-005", "name": "Cycle 2+ Day 1", "recurrence": {"type": "PER_CYCLE", "cycleDay": 1, "maxCycles": 6}},
            {"id": "ENC-006", "name": "End of Treatment", "recurrence": None},
            {"id": "ENC-007", "name": "Follow-up", "recurrence": None},
        ],
        "activities": [
            {"id": "ACT-001", "name": "CBC", "domainCode": {"code": "C49547", "decode": "Laboratory"}},
            {"id": "ACT-002", "name": "CT Scan", "domainCode": {"code": "C17369", "decode": "Imaging"}},
            {"id": "ACT-003", "name": "Vital Signs", "domainCode": {"code": "C49148", "decode": "Vital Signs"}},
        ],
        "scheduledActivityInstances": [],
        "qualityMetrics": {
            "totalVisits": 7,
            "timepointEncounters": 0,
            "standaloneEncounters": 7,
            "visitsWithRecurrence": 3,
            "visitGroupCount": 0,
            "matrixCoverage": 0.80,
            "footnoteCategoryDistribution": {"dosing": 3, "cycle": 2},
        },
        "visitGroups": {},
    }


@pytest.fixture
def linear_usdm():
    """Linear day-based naming USDM output (no cycle labels)."""
    return {
        "encounters": [
            {"id": "ENC-001", "name": "Day 1", "recurrence": None},
            {"id": "ENC-002", "name": "Day 22", "recurrence": None},
            {"id": "ENC-003", "name": "Day 43", "recurrence": None},
            {"id": "ENC-004", "name": "Day 64", "recurrence": None},
            {"id": "ENC-005", "name": "End of Treatment", "recurrence": None},
        ],
        "activities": [],
        "scheduledActivityInstances": [],
        "qualityMetrics": {},
        "visitGroups": {},
    }


@pytest.fixture
def sample_profile():
    """Sample valid classification profile."""
    return {
        "tableStructureType": "PK-heavy Phase 1 linear study",
        "confidence": 0.92,
        "characteristics": [
            "High timepoint ratio (0.636) indicates dense PK sampling",
            "No recurrence patterns detected",
            "Day-based naming without cycle labels",
        ],
        "stageGuidance": {
            "stage7_timing": "BI/EOI columns are sub-visit timing modifiers within Day 1.",
            "stage8_cycles": "These are PK timepoints, NOT cycles. Do not expand as cycles.",
            "stage9_mining": "Focus on PK sampling windows and bioanalytical methods.",
            "general": "PK-heavy Phase 1 study with dense Day 1 timepoint columns.",
        },
    }


# =============================================================================
# Test compute_structural_features
# =============================================================================


class TestComputeStructuralFeatures:
    """Tests for compute_structural_features()."""

    def test_pk_heavy_features(self, classifier, pk_heavy_usdm):
        """M21-195-like PK-heavy input produces high timepointRatio, low recurrence."""
        features = classifier.compute_structural_features(pk_heavy_usdm)

        assert features["totalVisits"] == 11
        assert features["timepointEncounters"] == 7
        assert features["standaloneEncounters"] == 4
        assert features["timepointRatio"] == round(7 / 11, 3)
        assert features["visitsWithRecurrence"] == 0
        assert features["visitGroupCount"] == 1
        assert features["hasExplicitCycleLabels"] is False
        assert features["hasDayBasedNaming"] is True
        assert features["recurrenceTypes"] == []
        assert len(features["encounterNameSample"]) == 11
        assert "Day 1" in features["visitGroups"]

    def test_oncology_features(self, classifier, oncology_usdm):
        """Cyclic oncology input produces hasExplicitCycleLabels=True, high recurrence."""
        features = classifier.compute_structural_features(oncology_usdm)

        assert features["totalVisits"] == 7
        assert features["timepointEncounters"] == 0
        assert features["timepointRatio"] == 0.0
        assert features["visitsWithRecurrence"] == 3
        assert features["hasExplicitCycleLabels"] is True
        assert features["hasDayBasedNaming"] is True  # "Day 1" etc.
        assert "PER_CYCLE" in features["recurrenceTypes"]

    def test_linear_features(self, classifier, linear_usdm):
        """Day 1/22/43 linear protocol produces hasDayBasedNaming=True, no cycle labels."""
        features = classifier.compute_structural_features(linear_usdm)

        assert features["totalVisits"] == 5
        assert features["timepointEncounters"] == 0
        assert features["timepointRatio"] == 0.0
        assert features["hasExplicitCycleLabels"] is False
        assert features["hasDayBasedNaming"] is True
        assert features["visitsWithRecurrence"] == 0

    def test_empty_usdm(self, classifier):
        """Empty USDM produces zero-value features."""
        features = classifier.compute_structural_features({})

        assert features["totalVisits"] == 0
        assert features["timepointEncounters"] == 0
        assert features["timepointRatio"] == 0.0
        assert features["hasExplicitCycleLabels"] is False
        assert features["hasDayBasedNaming"] is False

    def test_activity_domain_distribution_from_domain_code(self, classifier, oncology_usdm):
        """Activities with domainCode dict produce proper domain distribution."""
        features = classifier.compute_structural_features(oncology_usdm)

        dist = features["activityDomainDistribution"]
        assert "Laboratory" in dist
        assert "Imaging" in dist
        assert "Vital Signs" in dist

    def test_activity_domain_distribution_from_categories(self, classifier, pk_heavy_usdm):
        """Activities with raw categories produce domain distribution."""
        features = classifier.compute_structural_features(pk_heavy_usdm)

        dist = features["activityDomainDistribution"]
        assert "Laboratory" in dist

    def test_footnote_categories_preserved(self, classifier, pk_heavy_usdm):
        """Footnote categories from qualityMetrics are preserved."""
        features = classifier.compute_structural_features(pk_heavy_usdm)

        assert features["footnoteCategories"] == {"dosing": 2, "pk": 3}

    def test_encounter_name_sample_capped_at_20(self, classifier):
        """encounterNameSample is capped at 20 entries."""
        usdm = {
            "encounters": [{"id": f"ENC-{i:03d}", "name": f"Visit {i}"} for i in range(30)],
        }
        features = classifier.compute_structural_features(usdm)
        assert len(features["encounterNameSample"]) == 20

    def test_features_without_quality_metrics(self, classifier, linear_usdm):
        """Features computed correctly when qualityMetrics is empty."""
        linear_usdm["qualityMetrics"] = {}
        features = classifier.compute_structural_features(linear_usdm)

        # Should compute from encounters directly
        assert features["totalVisits"] == 5
        assert features["timepointEncounters"] == 0
        assert features["standaloneEncounters"] == 5


# =============================================================================
# Test classify
# =============================================================================


class TestClassify:
    """Tests for classify() method."""

    @pytest.mark.asyncio
    async def test_classify_returns_valid_profile(self, classifier, pk_heavy_usdm, sample_profile):
        """Mock LLM returns valid profile with all required fields."""
        with patch.object(
            classifier, "_classify_with_llm", return_value=sample_profile
        ):
            profile = await classifier.classify(pk_heavy_usdm)

        assert profile["tableStructureType"] == "PK-heavy Phase 1 linear study"
        assert profile["confidence"] == 0.92
        assert isinstance(profile["characteristics"], list)
        assert len(profile["characteristics"]) == 3
        assert "stage8_cycles" in profile["stageGuidance"]
        assert "stage7_timing" in profile["stageGuidance"]
        assert "stage9_mining" in profile["stageGuidance"]
        assert "general" in profile["stageGuidance"]
        # Structural features are embedded
        assert "structuralFeatures" in profile
        assert profile["structuralFeatures"]["totalVisits"] == 11

    @pytest.mark.asyncio
    async def test_classify_fallback_on_llm_failure(self, classifier, pk_heavy_usdm):
        """If all LLMs fail, returns safe default profile."""
        with patch.object(classifier, "_classify_with_llm", return_value=None):
            profile = await classifier.classify(pk_heavy_usdm)

        assert profile["tableStructureType"] == "unknown"
        assert profile["confidence"] == 0.0
        assert profile["characteristics"] == []
        assert profile["stageGuidance"] == {}
        # Structural features are still computed
        assert profile["structuralFeatures"]["totalVisits"] == 11

    @pytest.mark.asyncio
    async def test_classify_with_extraction_outputs(self, classifier, pk_heavy_usdm, sample_profile):
        """extraction_outputs are passed to protocol context."""
        extraction_outputs = {
            "study_metadata": {
                "studyPhase": "Phase 1",
                "therapeuticArea": {"value": "Healthy Volunteers"},
                "indication": {"value": "PK Study"},
            }
        }

        with patch.object(
            classifier, "_classify_with_llm", return_value=sample_profile
        ) as mock_llm:
            profile = await classifier.classify(
                pk_heavy_usdm, extraction_outputs=extraction_outputs
            )
            # Verify LLM was called
            mock_llm.assert_called_once()

        assert profile["tableStructureType"] == "PK-heavy Phase 1 linear study"


# =============================================================================
# Test _parse_response
# =============================================================================


class TestParseResponse:
    """Tests for _parse_response()."""

    def test_parse_valid_json(self, classifier, sample_profile):
        """Valid JSON string is parsed correctly."""
        json_str = json.dumps(sample_profile)
        result = classifier._parse_response(json_str)
        assert result["tableStructureType"] == "PK-heavy Phase 1 linear study"
        assert result["confidence"] == 0.92

    def test_parse_markdown_wrapped_json(self, classifier, sample_profile):
        """JSON wrapped in ```json``` is parsed correctly."""
        json_str = f"```json\n{json.dumps(sample_profile)}\n```"
        result = classifier._parse_response(json_str)
        assert result is not None
        assert result["tableStructureType"] == "PK-heavy Phase 1 linear study"

    def test_parse_invalid_json_returns_none(self, classifier):
        """Invalid JSON returns None."""
        result = classifier._parse_response("not valid json")
        assert result is None

    def test_parse_missing_required_field_returns_none(self, classifier):
        """Missing required field returns None."""
        incomplete = {"tableStructureType": "test", "confidence": 0.5}
        result = classifier._parse_response(json.dumps(incomplete))
        assert result is None

    def test_parse_clamps_confidence(self, classifier, sample_profile):
        """Confidence is clamped to [0.0, 1.0]."""
        sample_profile["confidence"] = 1.5
        result = classifier._parse_response(json.dumps(sample_profile))
        assert result["confidence"] == 1.0

        sample_profile["confidence"] = -0.3
        result = classifier._parse_response(json.dumps(sample_profile))
        assert result["confidence"] == 0.0


# =============================================================================
# Test Caching
# =============================================================================


class TestCaching:
    """Tests for classification caching."""

    def test_cache_hit(self, tmp_path):
        """Same features produce cached result, no LLM call."""
        classifier = SOATableClassifier(use_cache=True, cache_dir=tmp_path)

        features = {
            "totalVisits": 10,
            "timepointEncounters": 5,
            "standaloneEncounters": 5,
            "timepointRatio": 0.5,
            "visitsWithRecurrence": 0,
            "visitGroupCount": 1,
            "matrixCoverage": 0.7,
            "encounterNameSample": ["Day 1", "Day 2"],
            "visitGroups": {},
            "activityDomainDistribution": {},
            "footnoteCategories": {},
            "hasExplicitCycleLabels": False,
            "hasDayBasedNaming": True,
            "recurrenceTypes": [],
        }

        profile = {
            "tableStructureType": "test",
            "confidence": 0.9,
            "characteristics": ["test"],
            "stageGuidance": {
                "stage7_timing": "test",
                "stage8_cycles": "test",
                "stage9_mining": "test",
                "general": "test",
            },
        }

        # Save to cache
        classifier._save_to_cache(features, profile)

        # Should hit cache
        cached = classifier._check_cache(features)
        assert cached is not None
        assert cached["tableStructureType"] == "test"
        assert cached["confidence"] == 0.9

    def test_cache_miss(self, tmp_path):
        """Different features produce cache miss."""
        classifier = SOATableClassifier(use_cache=True, cache_dir=tmp_path)

        features = {
            "totalVisits": 10,
            "timepointEncounters": 5,
        }

        # No prior cache
        cached = classifier._check_cache(features)
        assert cached is None

    def test_features_hash_deterministic(self, classifier):
        """Same features always produce the same hash."""
        features = {"totalVisits": 10, "timepointRatio": 0.5}
        hash1 = classifier._compute_features_hash(features)
        hash2 = classifier._compute_features_hash(features)
        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 hex digest

    def test_features_hash_different_for_different_features(self, classifier):
        """Different features produce different hashes."""
        features1 = {"totalVisits": 10}
        features2 = {"totalVisits": 20}
        assert classifier._compute_features_hash(features1) != classifier._compute_features_hash(features2)


# =============================================================================
# Test Pipeline Integration
# =============================================================================


class TestPipelineIntegration:
    """Tests for profile flow through the pipeline."""

    @pytest.mark.asyncio
    async def test_profile_flows_through_pipeline(self, pk_heavy_usdm, sample_profile):
        """Verify soaTableProfile exists in working_usdm after classification."""
        classifier = SOATableClassifier(use_cache=False)

        with patch.object(
            classifier, "_classify_with_llm", return_value=sample_profile
        ):
            profile = await classifier.classify(pk_heavy_usdm)

        # Simulate pipeline behavior: store in working_usdm
        pk_heavy_usdm["soaTableProfile"] = profile

        assert "soaTableProfile" in pk_heavy_usdm
        assert pk_heavy_usdm["soaTableProfile"]["tableStructureType"] == "PK-heavy Phase 1 linear study"
        assert "structuralFeatures" in pk_heavy_usdm["soaTableProfile"]

    @pytest.mark.asyncio
    async def test_profile_empty_on_failure(self, pk_heavy_usdm):
        """On LLM failure, soaTableProfile is safe empty dict."""
        classifier = SOATableClassifier(use_cache=False)

        with patch.object(classifier, "_classify_with_llm", return_value=None):
            profile = await classifier.classify(pk_heavy_usdm)

        pk_heavy_usdm["soaTableProfile"] = profile

        # Stages that call usdm.get("soaTableProfile", {}) will get empty guidance
        assert pk_heavy_usdm["soaTableProfile"]["stageGuidance"] == {}
        # But structuralFeatures are still available
        assert pk_heavy_usdm["soaTableProfile"]["structuralFeatures"]["totalVisits"] == 11


# =============================================================================
# Test Protocol Context Extraction
# =============================================================================


class TestProtocolContextExtraction:
    """Tests for _extract_protocol_context()."""

    def test_extract_with_full_metadata(self, classifier):
        """Full extraction outputs produce rich context string."""
        extraction_outputs = {
            "study_metadata": {
                "studyPhase": "Phase 1",
                "therapeuticArea": {"value": "Oncology"},
                "indication": {"value": "Non-Small Cell Lung Cancer"},
                "treatmentDesign": {
                    "description": "Q3W dosing for 6 cycles",
                    "duration": "18 weeks",
                    "cycles": "6",
                },
                "studyType": "Interventional",
            }
        }
        context = classifier._extract_protocol_context(extraction_outputs)
        assert "Phase 1" in context
        assert "Oncology" in context
        assert "Non-Small Cell Lung Cancer" in context
        assert "Q3W dosing" in context
        assert "18 weeks" in context

    def test_extract_with_no_outputs(self, classifier):
        """None extraction outputs produce default string."""
        context = classifier._extract_protocol_context(None)
        assert "No protocol context" in context

    def test_extract_with_empty_metadata(self, classifier):
        """Empty extraction outputs produce default string."""
        context = classifier._extract_protocol_context({})
        assert "No protocol context" in context

    def test_extract_therapeutic_area_string(self, classifier):
        """Therapeutic area as string (not dict) is handled."""
        extraction_outputs = {
            "study_metadata": {
                "therapeuticArea": "Dermatology",
            }
        }
        context = classifier._extract_protocol_context(extraction_outputs)
        assert "Dermatology" in context


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
