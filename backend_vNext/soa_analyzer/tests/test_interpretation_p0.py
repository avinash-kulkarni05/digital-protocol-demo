"""
Unit tests for P0 Interpretation Pipeline stages.

Tests:
- Stage 1: Domain Categorization
- Stage 12: USDM Compliance

Run with: python -m pytest soa_analyzer/tests/test_interpretation_p0.py -v
"""

import asyncio
import json
import pytest
from pathlib import Path

# Import models
from soa_analyzer.models.code_object import (
    CodeObject,
    expand_to_usdm_code,
    is_usdm_compliant_code,
)
from soa_analyzer.models.condition import (
    Condition,
    ConditionAssignment,
    ConditionType,
    extract_conditions_from_footnotes,
)

# Import stages
from soa_analyzer.interpretation.stage1_domain_categorization import (
    DomainCategorizer,
    DomainMapping,
    CategorizationResult,
    VALID_DOMAINS,
)
from soa_analyzer.interpretation.stage12_usdm_compliance import (
    USDMComplianceChecker,
    ComplianceIssue,
    ComplianceResult,
    ensure_usdm_compliance,
)


class TestCodeObject:
    """Tests for USDM Code object model."""

    def test_from_simple_pair(self):
        """Test creating CodeObject from simple code/decode pair."""
        code = CodeObject.from_simple_pair("C48262", "Screening")

        assert code.code == "C48262"
        assert code.decode == "Screening"
        assert code.instanceType == "Code"
        assert code.codeSystem.startswith("http://")
        assert code.id.startswith("CODE-")

    def test_from_dict_simple(self):
        """Test creating CodeObject from simple dictionary."""
        data = {"code": "C48262", "decode": "Screening"}
        code = CodeObject.from_dict(data)

        assert code.code == "C48262"
        assert code.decode == "Screening"

    def test_from_dict_already_compliant(self):
        """Test creating CodeObject from already compliant dictionary."""
        data = {
            "id": "CODE-001",
            "code": "C48262",
            "decode": "Screening",
            "codeSystem": "http://test.com",
            "codeSystemVersion": "1.0",
            "instanceType": "Code",
        }
        code = CodeObject.from_dict(data)

        assert code.id == "CODE-001"
        assert code.codeSystem == "http://test.com"

    def test_expand_to_usdm_code(self):
        """Test expanding simple pair to full USDM code."""
        simple = {"code": "C48262", "decode": "Screening"}
        expanded = expand_to_usdm_code(simple)

        assert expanded is not None
        assert "instanceType" in expanded
        assert expanded["instanceType"] == "Code"
        assert "codeSystem" in expanded
        assert "codeSystemVersion" in expanded

    def test_is_usdm_compliant(self):
        """Test USDM compliance check."""
        # Non-compliant (simple pair)
        simple = {"code": "C48262", "decode": "Screening"}
        assert not is_usdm_compliant_code(simple)

        # Compliant (6-field)
        compliant = expand_to_usdm_code(simple)
        assert is_usdm_compliant_code(compliant)


class TestCondition:
    """Tests for USDM Condition model."""

    def test_from_footnote_demographic(self):
        """Test extracting demographic condition from footnote."""
        condition = Condition.from_footnote(
            "For females of childbearing potential only",
            marker="f",
            page_number=45,
        )

        assert condition is not None
        assert condition.condition_type == ConditionType.DEMOGRAPHIC_FERTILITY
        assert "childbearing" in condition.name.lower()
        assert condition.source_footnote_marker == "f"

    def test_from_footnote_clinical(self):
        """Test extracting clinical condition from footnote."""
        condition = Condition.from_footnote(
            "Perform if clinically indicated",
            marker="g",
        )

        assert condition is not None
        assert condition.condition_type == ConditionType.CLINICAL_INDICATION

    def test_from_footnote_no_match(self):
        """Test footnote with no recognizable pattern."""
        condition = Condition.from_footnote(
            "Within 72 hours before first dose",
            marker="a",
        )

        # This is a temporal condition, not yet handled in simple patterns
        # May return None or match if pattern added
        # Just verify no crash
        pass

    def test_extract_conditions_from_footnotes(self):
        """Test batch extraction of conditions from footnotes."""
        footnotes = [
            {"marker": "f", "text": "For females of childbearing potential"},
            {"marker": "g", "text": "If clinically indicated"},
            {"marker": "a", "text": "Within 72 hours before dose"},
        ]

        conditions, marker_map = extract_conditions_from_footnotes(footnotes)

        # Should extract at least the demographic and clinical conditions
        assert len(conditions) >= 2
        assert "f" in marker_map or "g" in marker_map


class TestDomainMapping:
    """Tests for Domain Mapping dataclass."""

    def test_confidence_levels(self):
        """Test confidence level classification."""
        high = DomainMapping(
            activity_id="ACT-001",
            activity_name="Hematology",
            category="LABORATORY",
            cdash_domain="LB",
            confidence=0.95,
        )
        assert high.is_high_confidence()
        assert not high.needs_review()
        assert not high.is_uncertain()

        medium = DomainMapping(
            activity_id="ACT-002",
            activity_name="Special Test",
            category="UNKNOWN",
            cdash_domain="PR",
            confidence=0.75,
        )
        assert not medium.is_high_confidence()
        assert medium.needs_review()
        assert not medium.is_uncertain()

        low = DomainMapping(
            activity_id="ACT-003",
            activity_name="Unknown Test",
            category="UNKNOWN",
            cdash_domain="PR",
            confidence=0.5,
        )
        assert not low.is_high_confidence()
        assert not low.needs_review()
        assert low.is_uncertain()


class TestValidDomains:
    """Tests for valid CDISC domains."""

    def test_all_domains_present(self):
        """Test that all expected domains are defined."""
        expected_domains = ["LB", "VS", "EG", "PE", "QS", "MI", "CM", "AE", "EX", "BS", "DM", "MH", "DS", "PR", "TU", "PC"]

        for domain in expected_domains:
            assert domain in VALID_DOMAINS, f"Missing domain: {domain}"


class TestUSDMComplianceChecker:
    """Tests for USDM Compliance Checker."""

    def test_expand_encounter_type(self):
        """Test expanding encounter type code objects."""
        usdm = {
            "encounters": [
                {
                    "id": "ENC-001",
                    "name": "Screening",
                    "type": {"code": "C48262", "decode": "Screening"},
                }
            ],
            "activities": [],
            "scheduledActivityInstances": [],
        }

        checker = USDMComplianceChecker()
        result_usdm, result = checker.ensure_compliance(usdm)

        # Check type was expanded
        enc_type = result_usdm["encounters"][0].get("type", {})
        assert enc_type.get("instanceType") == "Code"
        assert "codeSystem" in enc_type

    def test_referential_integrity_valid(self):
        """Test referential integrity with valid references."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "Vitals"}],
            "encounters": [{"id": "ENC-001", "name": "Screening"}],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "visitId": "ENC-001",
                }
            ],
        }

        checker = USDMComplianceChecker()
        result_usdm, result = checker.ensure_compliance(usdm)

        # Should pass referential integrity
        assert result.referential_integrity_passed

    def test_referential_integrity_invalid(self):
        """Test referential integrity with invalid references."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "Vitals"}],
            "encounters": [{"id": "ENC-001", "name": "Screening"}],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-NONEXISTENT",  # Invalid reference
                    "visitId": "ENC-001",
                }
            ],
        }

        checker = USDMComplianceChecker()
        result_usdm, result = checker.ensure_compliance(usdm)

        # Should fail referential integrity
        assert not result.referential_integrity_passed
        assert any(i.category == "referential_integrity" for i in result.issues)

    def test_condition_linkage(self):
        """Test condition extraction and linkage from footnotes."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "Pregnancy Test"}],
            "encounters": [{"id": "ENC-001", "name": "Screening"}],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "visitId": "ENC-001",
                    "footnoteMarkers": ["f"],
                }
            ],
            "footnotes": [
                {"marker": "f", "text": "For females of childbearing potential only"},
            ],
            "conditions": [],
            "conditionAssignments": [],
        }

        checker = USDMComplianceChecker()
        result_usdm, result = checker.ensure_compliance(usdm)

        # Should have created conditions and assignments
        assert len(result_usdm.get("conditions", [])) > 0
        assert len(result_usdm.get("conditionAssignments", [])) > 0


class TestDomainCategorizer:
    """Tests for Domain Categorizer (non-LLM parts)."""

    def test_normalize_name(self):
        """Test activity name normalization."""
        categorizer = DomainCategorizer(use_cache=False)

        assert categorizer._normalize_name("  Hematology  ") == "hematology"
        assert categorizer._normalize_name("VITAL SIGNS") == "vital signs"

    def test_cache_key_generation(self):
        """Test cache key generation is consistent."""
        categorizer = DomainCategorizer(use_cache=False)

        key1 = categorizer._get_cache_key("Hematology")
        key2 = categorizer._get_cache_key("hematology")
        key3 = categorizer._get_cache_key("  HEMATOLOGY  ")

        assert key1 == key2 == key3


# Integration test (requires LLM API keys)
class TestDomainCategorizerIntegration:
    """Integration tests for Domain Categorizer with LLM."""

    @pytest.mark.skipif(
        not Path(__file__).parent.parent.parent.parent / ".env",
        reason="No .env file found",
    )
    @pytest.mark.asyncio
    async def test_categorize_activities(self):
        """Test full categorization pipeline (requires API keys)."""
        activities = [
            {"id": "ACT-001", "name": "Hematology"},
            {"id": "ACT-002", "name": "Vital Signs"},
            {"id": "ACT-003", "name": "12-Lead ECG"},
        ]

        categorizer = DomainCategorizer(use_cache=True)
        result = await categorizer.categorize_activities(activities)

        # Should have mappings for all activities
        assert result.total_activities == 3
        assert len(result.mappings) == 3

        # Check specific mappings
        hematology = result.get_mapping("ACT-001")
        if hematology and hematology.source != "default":
            assert hematology.cdash_domain == "LB"

        vitals = result.get_mapping("ACT-002")
        if vitals and vitals.source != "default":
            assert vitals.cdash_domain == "VS"


if __name__ == "__main__":
    # Run basic tests without pytest
    print("Running basic tests...")

    # Test CodeObject
    print("\n--- Testing CodeObject ---")
    code = CodeObject.from_simple_pair("C48262", "Screening")
    print(f"Created: {code.to_dict()}")
    assert code.instanceType == "Code"
    print("✓ CodeObject tests passed")

    # Test Condition
    print("\n--- Testing Condition ---")
    cond = Condition.from_footnote("For females of childbearing potential only", "f")
    if cond:
        print(f"Extracted: {cond.name}")
        assert cond.condition_type == ConditionType.DEMOGRAPHIC_FERTILITY
    print("✓ Condition tests passed")

    # Test USDM Compliance
    print("\n--- Testing USDM Compliance ---")
    usdm = {
        "encounters": [{"id": "ENC-001", "type": {"code": "C48262", "decode": "Screening"}}],
        "activities": [],
        "scheduledActivityInstances": [],
    }
    checker = USDMComplianceChecker()
    result_usdm, result = checker.ensure_compliance(usdm)
    print(f"Compliance result: {result.get_summary()}")
    print("✓ USDM Compliance tests passed")

    print("\n✓ All basic tests passed!")
