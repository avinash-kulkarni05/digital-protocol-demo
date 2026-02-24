"""
Pytest-compatible Regression Tests for OMOP RAG Mapping

Tests the RAG mapper against known problematic mappings, demographic terms,
clinical terms, caching behavior, batch processing, and performance.

Usage:
    # Run all OMOP RAG tests
    python -m pytest eligibility_analyzer/omop_rag/tests/test_rag_regression.py -v

    # Run a specific test class
    python -m pytest eligibility_analyzer/omop_rag/tests/test_rag_regression.py::TestKnownBugFixes -v

    # Run a single test
    python -m pytest eligibility_analyzer/omop_rag/tests/test_rag_regression.py::TestDemographicMappings::test_female -v
"""

import asyncio
import json
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_mapper_instance = None
_loop = None


def _get_loop():
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop


def _get_rag_mapper():
    """Lazy-initialize a shared RAGMapper instance across tests."""
    global _mapper_instance
    if _mapper_instance is None:
        env_path = Path(__file__).parent.parent.parent.parent.parent / ".env"
        if env_path.exists():
            from dotenv import load_dotenv
            load_dotenv(env_path)

        from eligibility_analyzer.omop_rag.rag_mapper import RAGMapper
        _mapper_instance = RAGMapper()
    return _mapper_instance


def _map(term, domain_hint=None):
    """Sync wrapper: map a single term."""
    mapper = _get_rag_mapper()
    return _get_loop().run_until_complete(mapper.map_term(term, domain_hint))


def _map_batch(terms, max_concurrent=10):
    """Sync wrapper: batch map terms."""
    mapper = _get_rag_mapper()
    return _get_loop().run_until_complete(
        mapper.map_terms_batch(terms, max_concurrent=max_concurrent)
    )


@pytest.fixture(scope="session")
def mapper():
    """Provide a shared RAGMapper instance for all tests in the session."""
    try:
        return _get_rag_mapper()
    except Exception as e:
        pytest.skip(f"RAGMapper initialization failed: {e}")


# ---------------------------------------------------------------------------
# Test 1: Known Bug Fixes
# ---------------------------------------------------------------------------

class TestKnownBugFixes:
    """Verify that previously known mapping bugs are fixed.

    These are real bugs found in protocol extractions where SQL pattern
    matching produced wrong results (e.g., "Patient is female" -> "Baby female").
    """

    def test_nct02203851_patient_is_female(self, mapper):
        """NCT02203851: 'Patient is female' should NOT map to 'Baby female' (4015271)."""
        result = _map("Patient is female", "Gender")
        assert result.is_mapped, "Expected mapped result for 'Patient is female'"
        assert result.concept_id == 8532, (
            f"Expected FEMALE (8532), got {result.concept_name} ({result.concept_id})"
        )
        assert result.concept_id != 4015271, "Bug regression: still mapping to 'Baby female'"

    def test_nct04983589_sex_is_female(self, mapper):
        """NCT04983589: 'Sex is female' should map to FEMALE (8532)."""
        result = _map("Sex is female", "Gender")
        assert result.is_mapped
        assert result.concept_id == 8532, (
            f"Expected FEMALE (8532), got {result.concept_name} ({result.concept_id})"
        )

    def test_nct04983589_sex_is_male(self, mapper):
        """NCT04983589: 'Sex is male' should NOT map to 'Maleo' (bird species, 4139950)."""
        result = _map("Sex is male", "Gender")
        assert result.is_mapped
        assert result.concept_id == 8507, (
            f"Expected MALE (8507), got {result.concept_name} ({result.concept_id})"
        )
        assert result.concept_id != 4139950, "Bug regression: still mapping to 'Maleo' (bird)"


# ---------------------------------------------------------------------------
# Test 2: Demographic Mappings
# ---------------------------------------------------------------------------

class TestDemographicMappings:
    """Test demographic term mappings (gender, race, ethnicity).

    These are deterministic Tier 1 mappings that should always return
    confidence=1.0 from the curated mapper.
    """

    # -- Gender terms --

    def test_female(self, mapper):
        result = _map("female")
        assert result.is_mapped and result.concept_id == 8532

    def test_male(self, mapper):
        result = _map("male")
        assert result.is_mapped and result.concept_id == 8507

    def test_woman(self, mapper):
        result = _map("woman")
        assert result.is_mapped and result.concept_id == 8532

    def test_men(self, mapper):
        result = _map("men")
        assert result.is_mapped and result.concept_id == 8507

    def test_patient_is_a_male(self, mapper):
        result = _map("Patient is a male")
        assert result.is_mapped and result.concept_id == 8507

    def test_female_patient(self, mapper):
        result = _map("Female patient")
        assert result.is_mapped and result.concept_id == 8532

    def test_gender_curated_confidence(self, mapper):
        """Gender mappings from curated mapper should have confidence=1.0."""
        result = _map("female", "Gender")
        assert result.confidence == 1.0
        assert result.source == "curated"

    # -- Race terms --

    def test_white(self, mapper):
        result = _map("White")
        assert result.is_mapped and result.concept_id == 8527

    def test_black_or_african_american(self, mapper):
        result = _map("Black or African American")
        assert result.is_mapped and result.concept_id == 8516

    def test_asian(self, mapper):
        result = _map("Asian")
        assert result.is_mapped and result.concept_id == 8515

    # -- Ethnicity terms --

    def test_hispanic(self, mapper):
        result = _map("Hispanic")
        assert result.is_mapped and result.concept_id == 38003563

    def test_non_hispanic(self, mapper):
        result = _map("Non-Hispanic")
        assert result.is_mapped and result.concept_id == 38003564


# ---------------------------------------------------------------------------
# Test 3: Clinical Term Mappings
# ---------------------------------------------------------------------------

class TestClinicalMappings:
    """Test clinical term mappings (conditions, measurements).

    These may use Tier 1 (curated), Tier 2 (semantic), or Tier 3 (LLM validated)
    depending on whether ATHENA DB and vector store are available.
    """

    def test_diabetes_mellitus(self, mapper):
        result = _map("diabetes mellitus", "Condition")
        assert result.is_mapped, "diabetes mellitus should be mapped"
        assert result.concept_id == 201820, (
            f"Expected 'Diabetes mellitus' (201820), got {result.concept_name} ({result.concept_id})"
        )

    def test_type_2_diabetes(self, mapper):
        result = _map("type 2 diabetes", "Condition")
        assert result.is_mapped, "type 2 diabetes should be mapped"
        assert result.concept_id == 201826, (
            f"Expected 'Type 2 diabetes mellitus' (201826), got {result.concept_name} ({result.concept_id})"
        )

    def test_hypertension(self, mapper):
        result = _map("hypertension", "Condition")
        assert result.is_mapped, "hypertension should be mapped"
        assert result.concept_id == 316866, (
            f"Expected 'Hypertensive disorder' (316866), got {result.concept_name} ({result.concept_id})"
        )

    def test_breast_cancer(self, mapper):
        result = _map("breast cancer", "Condition")
        assert result.is_mapped, "breast cancer should be mapped"
        assert result.concept_id == 4112853, (
            f"Expected 'Malignant tumor of breast' (4112853), got {result.concept_name} ({result.concept_id})"
        )


# ---------------------------------------------------------------------------
# Test 4: Caching Behavior
# ---------------------------------------------------------------------------

class TestCaching:
    """Test that the in-memory LRU cache works correctly."""

    def test_cache_returns_same_result(self, mapper):
        """Mapping the same term twice should return identical concept IDs."""
        result1 = _map("Patient is female")
        result2 = _map("Patient is female")
        assert result1.concept_id == result2.concept_id, (
            f"Cache inconsistency: first={result1.concept_id}, second={result2.concept_id}"
        )

    def test_cache_is_faster(self, mapper):
        """Second call should be faster (served from cache)."""
        result1 = _map("female", "Gender")
        result2 = _map("female", "Gender")
        assert result2.processing_time_ms <= result1.processing_time_ms + 1, (
            f"Cache not faster: first={result1.processing_time_ms:.1f}ms, "
            f"second={result2.processing_time_ms:.1f}ms"
        )

    def test_cache_hits_registered(self, mapper):
        """Cache hits should be tracked in statistics."""
        _map("male", "Gender")
        _map("male", "Gender")
        stats = mapper.get_stats()
        assert stats.get("cache_hits", 0) > 0, (
            f"Expected cache_hits > 0, got {stats.get('cache_hits', 0)}"
        )


# ---------------------------------------------------------------------------
# Test 5: Batch Processing
# ---------------------------------------------------------------------------

class TestBatchProcessing:
    """Test the batch mapping API."""

    def test_batch_maps_all_terms(self, mapper):
        """Batch processing should return a result for every input term."""
        terms = [
            {"term": "female", "domain_hint": "Gender"},
            {"term": "male", "domain_hint": "Gender"},
            {"term": "diabetes mellitus", "domain_hint": "Condition"},
        ]
        results = _map_batch(terms)
        assert len(results) == len(terms), (
            f"Expected {len(terms)} results, got {len(results)}"
        )

    def test_batch_preserves_order(self, mapper):
        """Results should match the order of input terms."""
        terms = [
            {"term": "female", "domain_hint": "Gender"},
            {"term": "male", "domain_hint": "Gender"},
        ]
        results = _map_batch(terms)
        assert results[0].term == "female"
        assert results[1].term == "male"

    def test_batch_empty_input(self, mapper):
        """Empty input should return empty results."""
        results = _map_batch([])
        assert results == []

    def test_batch_concurrent_execution(self, mapper):
        """Batch with many terms should use parallel execution."""
        terms = [
            {"term": f"term_{i}", "domain_hint": "Condition"}
            for i in range(20)
        ]
        results = _map_batch(terms, max_concurrent=10)
        assert len(results) == 20


# ---------------------------------------------------------------------------
# Test 6: MappingResult Structure
# ---------------------------------------------------------------------------

class TestMappingResultStructure:
    """Test that MappingResult has correct structure and serialization."""

    def test_mapped_result_fields(self, mapper):
        """A mapped result should have all required fields populated."""
        result = _map("female", "Gender")
        assert result.is_mapped
        assert result.concept_id is not None
        assert result.concept_name is not None
        assert result.confidence > 0
        assert result.source in ("curated", "semantic", "llm_validated", "athena_fallback")
        assert result.processing_time_ms >= 0

    def test_unmapped_result_fields(self, mapper):
        """An unmapped result should have correct default values."""
        result = _map("xyzzy_nonexistent_term_12345")
        assert not result.is_mapped
        assert result.source == "unmapped"
        assert result.confidence == 0.0

    def test_to_dict_serialization(self, mapper):
        """to_dict() should produce valid JSON-serializable output."""
        result = _map("female", "Gender")
        d = result.to_dict()
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["term"] == "female"
        assert parsed["isMapped"] is True
        assert "conceptId" in parsed
        assert "confidence" in parsed


# ---------------------------------------------------------------------------
# Test 7: Statistics Tracking
# ---------------------------------------------------------------------------

class TestStatistics:
    """Test that the RAG mapper tracks statistics correctly."""

    def test_stats_structure(self, mapper):
        """Stats should include all expected keys."""
        _map("female")
        stats = mapper.get_stats()
        assert "total_lookups" in stats
        assert "cache_hits" in stats
        assert "curated_hits" in stats
        assert "semantic_hits" in stats
        assert "unmapped" in stats

    def test_stats_rates(self, mapper):
        """Stats rates should be between 0 and 1."""
        _map("female")
        stats = mapper.get_stats()
        for key in ("cache_hit_rate", "curated_rate", "unmapped_rate"):
            if key in stats:
                assert 0 <= stats[key] <= 1, f"{key}={stats[key]} out of range"

    def test_total_lookups_increment(self, mapper):
        """Each map_term call should increment total_lookups."""
        stats_before = mapper.get_stats()
        before_count = stats_before.get("total_lookups", 0)
        _map("unique_test_term_for_stats_check")
        stats_after = mapper.get_stats()
        assert stats_after["total_lookups"] == before_count + 1


# ---------------------------------------------------------------------------
# Test 8: Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_string(self, mapper):
        """Empty string should return unmapped result without error."""
        result = _map("")
        assert not result.is_mapped

    def test_whitespace_only(self, mapper):
        """Whitespace-only input should return unmapped result."""
        result = _map("   ")
        assert not result.is_mapped

    def test_case_insensitive(self, mapper):
        """Mapping should be case-insensitive."""
        result_lower = _map("female")
        result_upper = _map("FEMALE")
        result_mixed = _map("Female")
        assert result_lower.concept_id == result_upper.concept_id == result_mixed.concept_id

    def test_long_term(self, mapper):
        """Very long terms should not crash the mapper."""
        long_term = "Patient with documented history of " * 20 + "diabetes mellitus"
        result = _map(long_term, "Condition")
        # Should not raise - result may or may not be mapped

    def test_special_characters(self, mapper):
        """Terms with special characters should not crash."""
        result = _map("HbA1c >= 7.0%", "Measurement")
        # Should not raise

    def test_domain_hint_none(self, mapper):
        """Mapping without domain hint should still work."""
        result = _map("female", None)
        assert result.is_mapped


# ---------------------------------------------------------------------------
# Test 9: Performance Benchmarks
# ---------------------------------------------------------------------------

class TestPerformance:
    """Performance benchmarks - run with -v to see timing details."""

    def test_curated_mapping_speed(self, mapper):
        """Curated (Tier 1) mappings should complete in < 50ms average."""
        # Warm cache
        _map("female", "Gender")
        timings = []
        for _ in range(10):
            start = time.time()
            _map("female", "Gender")
            timings.append((time.time() - start) * 1000)
        avg_ms = sum(timings) / len(timings)
        assert avg_ms < 50, f"Average curated mapping time {avg_ms:.1f}ms exceeds 50ms threshold"

    def test_batch_throughput(self, mapper):
        """Batch processing should handle 50 terms in reasonable time."""
        terms = [
            {"term": "female", "domain_hint": "Gender"},
            {"term": "male", "domain_hint": "Gender"},
            {"term": "diabetes", "domain_hint": "Condition"},
            {"term": "hypertension", "domain_hint": "Condition"},
            {"term": "breast cancer", "domain_hint": "Condition"},
        ] * 10  # 50 terms

        start = time.time()
        results = _map_batch(terms, max_concurrent=10)
        elapsed = time.time() - start

        assert len(results) == 50
        assert elapsed < 30, f"Batch of 50 terms took {elapsed:.1f}s (> 30s threshold)"
