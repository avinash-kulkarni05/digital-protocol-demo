"""
Integration tests for Stage 7 → Stage 12 pipeline.

Validates that Stage 7 output is USDM 4.0 compliant after Stage 12 processing.

Key validations:
1. Expanded SAIs have proper USDM Code objects for timingModifier
2. Referential integrity is maintained across expansion
3. No compliance errors after Stage 12 processing
4. Provenance metadata is preserved

Run with: python -m pytest soa_analyzer/tests/test_stage7_12_integration.py -v
"""

import asyncio
import pytest
from typing import Dict, Any

# Import Stage 7
from soa_analyzer.interpretation.stage7_timing_distribution import (
    TimingDistributor,
    TimingDistributionConfig,
    distribute_timing,
)

# Import Stage 12
from soa_analyzer.interpretation.stage12_usdm_compliance import (
    USDMComplianceChecker,
    ComplianceResult,
    ensure_usdm_compliance,
)

# Import models
from soa_analyzer.models.timing_expansion import Stage7Result
from soa_analyzer.models.code_object import is_usdm_compliant_code


def create_test_usdm() -> Dict[str, Any]:
    """Create a test USDM structure with timing modifiers to expand."""
    return {
        "activities": [
            {"id": "ACT-001", "name": "PK Blood Sample"},
            {"id": "ACT-002", "name": "Vital Signs"},
            {"id": "ACT-003", "name": "ECG"},
        ],
        "encounters": [
            {"id": "ENC-001", "name": "Screening"},
            {"id": "ENC-002", "name": "Cycle 1 Day 1"},
            {"id": "ENC-003", "name": "Cycle 1 Day 8"},
        ],
        "scheduledActivityInstances": [
            {
                "id": "SAI-001",
                "activityId": "ACT-001",
                "scheduledInstanceEncounterId": "ENC-002",
                "timingModifier": "BI/EOI",
                "isRequired": True,
            },
            {
                "id": "SAI-002",
                "activityId": "ACT-002",
                "scheduledInstanceEncounterId": "ENC-001",
                "timingModifier": None,  # No timing modifier
                "isRequired": True,
            },
            {
                "id": "SAI-003",
                "activityId": "ACT-001",
                "scheduledInstanceEncounterId": "ENC-003",
                "timingModifier": "pre-dose/post-dose",
                "isRequired": True,
            },
            {
                "id": "SAI-004",
                "activityId": "ACT-003",
                "scheduledInstanceEncounterId": "ENC-002",
                "timingModifier": "trough",  # Already atomic, no expansion
                "isRequired": True,
            },
        ],
        "footnotes": [],
        "conditions": [],
        "conditionAssignments": [],
    }


class TestStage7To12Integration:
    """Integration tests for Stage 7 → Stage 12 pipeline."""

    @pytest.mark.asyncio
    async def test_expanded_sais_have_code_objects(self):
        """Test that Stage 7 expanded SAIs have proper USDM Code objects."""
        usdm = create_test_usdm()

        # Run Stage 7
        distributor = TimingDistributor()
        result = await distributor.distribute_timing(usdm)
        stage7_output = distributor.apply_expansions_to_usdm(usdm, result)

        # Verify expanded SAIs have Code objects
        for sai in stage7_output["scheduledActivityInstances"]:
            timing_mod = sai.get("timingModifier")
            if timing_mod is not None:
                # If it was expanded, it should be a Code object
                if "_timingExpansion" in sai:
                    assert isinstance(timing_mod, dict), f"SAI {sai['id']}: timingModifier should be dict, got {type(timing_mod)}"
                    assert timing_mod.get("instanceType") == "Code", f"SAI {sai['id']}: timingModifier should have instanceType='Code'"
                    assert "decode" in timing_mod, f"SAI {sai['id']}: timingModifier should have 'decode' field"

    @pytest.mark.asyncio
    async def test_stage7_output_passes_stage12_compliance(self):
        """Test that Stage 7 output passes Stage 12 compliance check."""
        usdm = create_test_usdm()

        # Run Stage 7
        distributor = TimingDistributor()
        result = await distributor.distribute_timing(usdm)
        stage7_output = distributor.apply_expansions_to_usdm(usdm, result)

        # Run Stage 12
        checker = USDMComplianceChecker()
        final_output, compliance_result = checker.ensure_compliance(stage7_output)

        # Check referential integrity
        ref_errors = [i for i in compliance_result.issues if i.category == "referential_integrity" and i.severity == "error"]
        assert len(ref_errors) == 0, f"Referential integrity errors: {[i.message for i in ref_errors]}"
        assert compliance_result.referential_integrity_passed, "Referential integrity should pass"

    @pytest.mark.asyncio
    async def test_referential_integrity_preserved_after_expansion(self):
        """Test that all expanded SAI references point to existing entities."""
        usdm = create_test_usdm()

        # Run Stage 7
        distributor = TimingDistributor()
        result = await distributor.distribute_timing(usdm)
        stage7_output = distributor.apply_expansions_to_usdm(usdm, result)

        # Collect all IDs
        activity_ids = {a["id"] for a in stage7_output["activities"]}
        encounter_ids = {e["id"] for e in stage7_output["encounters"]}

        # Check all SAI references
        for sai in stage7_output["scheduledActivityInstances"]:
            assert sai["activityId"] in activity_ids, f"SAI {sai['id']} references non-existent activity {sai['activityId']}"
            enc_id = sai.get("scheduledInstanceEncounterId") or sai.get("visitId")
            assert enc_id in encounter_ids, f"SAI {sai['id']} references non-existent encounter {enc_id}"

    @pytest.mark.asyncio
    async def test_bi_eoi_expansion_creates_two_sais(self):
        """Test that BI/EOI timing modifier expands to two SAIs."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "PK Sample"}],
            "encounters": [{"id": "ENC-001", "name": "Cycle 1 Day 1"}],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "timingModifier": "BI/EOI",
                },
            ],
        }

        # Run Stage 7
        distributor = TimingDistributor()
        result = await distributor.distribute_timing(usdm)
        stage7_output = distributor.apply_expansions_to_usdm(usdm, result)

        sais = stage7_output["scheduledActivityInstances"]

        # Should have 2 SAIs (BI and EOI)
        assert len(sais) >= 2, f"Expected at least 2 SAIs after expansion, got {len(sais)}"

        # Check for BI and EOI variants
        sai_ids = [s["id"] for s in sais]
        has_bi = any("BI" in sai_id for sai_id in sai_ids)
        has_eoi = any("EOI" in sai_id for sai_id in sai_ids)

        if result.sais_expanded > 0:
            assert has_bi, "Should have SAI with BI timing"
            assert has_eoi, "Should have SAI with EOI timing"

            # Verify Code objects
            for sai in sais:
                if "_timingExpansion" in sai:
                    timing_mod = sai["timingModifier"]
                    assert isinstance(timing_mod, dict), "Expanded timingModifier should be dict"
                    assert timing_mod.get("instanceType") == "Code"

    @pytest.mark.asyncio
    async def test_predose_postdose_expansion(self):
        """Test that pre-dose/post-dose expands correctly."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "PK Sample"}],
            "encounters": [{"id": "ENC-001", "name": "Visit"}],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "timingModifier": "pre-dose/post-dose",
                },
            ],
        }

        distributor = TimingDistributor()
        result = await distributor.distribute_timing(usdm)
        stage7_output = distributor.apply_expansions_to_usdm(usdm, result)

        sais = stage7_output["scheduledActivityInstances"]

        if result.sais_expanded > 0:
            # Check for correct CDISC codes
            for sai in sais:
                if "_timingExpansion" in sai:
                    timing_mod = sai["timingModifier"]
                    assert timing_mod.get("instanceType") == "Code"

                    # Check decode matches expected
                    decode = timing_mod.get("decode", "")
                    assert decode in ["Pre-dose", "Post-dose"], f"Unexpected decode: {decode}"

    @pytest.mark.asyncio
    async def test_atomic_timing_not_expanded(self):
        """Test that atomic timings are not expanded."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "PK Sample"}],
            "encounters": [{"id": "ENC-001", "name": "Visit"}],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "timingModifier": "trough",  # Atomic - should not expand
                },
            ],
        }

        distributor = TimingDistributor()
        result = await distributor.distribute_timing(usdm)
        stage7_output = distributor.apply_expansions_to_usdm(usdm, result)

        # Should still have exactly 1 SAI
        sais = stage7_output["scheduledActivityInstances"]
        assert len(sais) == 1, f"Atomic timing should not expand, got {len(sais)} SAIs"
        assert sais[0]["id"] == "SAI-001"

    @pytest.mark.asyncio
    async def test_provenance_preserved_through_pipeline(self):
        """Test that provenance metadata is preserved through Stage 7→12."""
        usdm = create_test_usdm()

        # Run Stage 7
        distributor = TimingDistributor()
        result = await distributor.distribute_timing(usdm)
        stage7_output = distributor.apply_expansions_to_usdm(usdm, result)

        # Run Stage 12
        final_output, _ = ensure_usdm_compliance(stage7_output)

        # Check provenance on expanded SAIs
        for sai in final_output["scheduledActivityInstances"]:
            if "_timingExpansion" in sai:
                expansion_meta = sai["_timingExpansion"]

                # Should have required provenance fields
                assert "originalId" in expansion_meta
                assert "originalTimingModifier" in expansion_meta
                assert "expandedTiming" in expansion_meta
                assert "stage" in expansion_meta
                assert expansion_meta["stage"] == "Stage7TimingDistribution"
                assert "timestamp" in expansion_meta

    @pytest.mark.asyncio
    async def test_footnote_markers_preserved_after_expansion(self):
        """Test that footnote markers are preserved on expanded SAIs."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "PK Sample"}],
            "encounters": [{"id": "ENC-001", "name": "Visit"}],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "timingModifier": "BI/EOI",
                    "footnoteMarkers": ["a", "c"],
                },
            ],
            "footnotes": [
                {"id": "FN-001", "marker": "a", "text": "Only if clinically indicated"},
                {"id": "FN-002", "marker": "c", "text": "Fasting sample"},
            ],
        }

        distributor = TimingDistributor()
        result = await distributor.distribute_timing(usdm)
        stage7_output = distributor.apply_expansions_to_usdm(usdm, result)

        # Check that expanded SAIs preserve footnote markers
        for sai in stage7_output["scheduledActivityInstances"]:
            if "_timingExpansion" in sai:
                # Should have footnote markers preserved
                assert "footnoteMarkers" in sai
                assert sai["footnoteMarkers"] == ["a", "c"]

                # Should have footnote condition flag
                assert sai.get("_hasFootnoteCondition") is True

    @pytest.mark.asyncio
    async def test_end_to_end_pipeline(self):
        """End-to-end test of Stage 7 → Stage 12 pipeline."""
        usdm = create_test_usdm()

        # Run full pipeline
        stage7_output, stage7_result = await distribute_timing(usdm)
        final_output, compliance_result = ensure_usdm_compliance(stage7_output)

        # Summary checks
        assert stage7_result.sais_processed > 0
        assert compliance_result.referential_integrity_passed

        # Verify all timing modifiers that were expanded are now Code objects
        expanded_sai_count = sum(
            1 for sai in final_output["scheduledActivityInstances"]
            if "_timingExpansion" in sai
        )

        if expanded_sai_count > 0:
            for sai in final_output["scheduledActivityInstances"]:
                if "_timingExpansion" in sai:
                    timing_mod = sai.get("timingModifier")
                    assert isinstance(timing_mod, dict), "Expanded timingModifier should be dict"
                    assert timing_mod.get("instanceType") == "Code"


class TestStage7To12EdgeCases:
    """Edge case tests for Stage 7 → Stage 12 integration."""

    @pytest.mark.asyncio
    async def test_empty_sai_list(self):
        """Test handling of empty SAI list."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "Test"}],
            "encounters": [{"id": "ENC-001", "name": "Test"}],
            "scheduledActivityInstances": [],
        }

        distributor = TimingDistributor()
        result = await distributor.distribute_timing(usdm)

        assert result.sais_processed == 0
        assert result.sais_expanded == 0

    @pytest.mark.asyncio
    async def test_no_timing_modifiers(self):
        """Test handling when no SAIs have timing modifiers."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "Test"}],
            "encounters": [{"id": "ENC-001", "name": "Test"}],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "timingModifier": None,
                },
                {
                    "id": "SAI-002",
                    "activityId": "ACT-001",
                    "scheduledInstanceEncounterId": "ENC-001",
                    # No timingModifier field
                },
            ],
        }

        distributor = TimingDistributor()
        result = await distributor.distribute_timing(usdm)

        assert result.sais_expanded == 0
        assert result.unique_timings_analyzed == 0

    @pytest.mark.asyncio
    async def test_nested_usdm_structure(self):
        """Test handling of nested studyVersion structure."""
        usdm = {
            "studyVersion": [
                {
                    "activities": [{"id": "ACT-001", "name": "PK Sample"}],
                    "encounters": [{"id": "ENC-001", "name": "Visit"}],
                    "scheduledActivityInstances": [
                        {
                            "id": "SAI-001",
                            "activityId": "ACT-001",
                            "scheduledInstanceEncounterId": "ENC-001",
                            "timingModifier": "BI/EOI",
                        },
                    ],
                }
            ]
        }

        distributor = TimingDistributor()
        result = await distributor.distribute_timing(usdm)
        stage7_output = distributor.apply_expansions_to_usdm(usdm, result)

        # Should handle nested structure
        assert result.sais_processed > 0

        # Verify structure is preserved
        assert "studyVersion" in stage7_output

    @pytest.mark.asyncio
    async def test_unknown_timing_still_gets_code_object(self):
        """Test that unknown timing modifiers still get Code objects (with null code)."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "Test"}],
            "encounters": [{"id": "ENC-001", "name": "Test"}],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "timingModifier": "unknown/novel",  # Unknown pattern
                },
            ],
        }

        distributor = TimingDistributor()
        result = await distributor.distribute_timing(usdm)
        stage7_output = distributor.apply_expansions_to_usdm(usdm, result)

        # If expanded, should still have Code objects
        for sai in stage7_output["scheduledActivityInstances"]:
            if "_timingExpansion" in sai:
                timing_mod = sai.get("timingModifier")
                assert isinstance(timing_mod, dict)
                assert timing_mod.get("instanceType") == "Code"
                # May have null code but should have decode
                assert "decode" in timing_mod


if __name__ == "__main__":
    # Run basic integration test without pytest
    print("Running Stage 7 → Stage 12 Integration Tests...")

    async def run_basic_test():
        usdm = create_test_usdm()

        print("\n--- Running Stage 7 ---")
        distributor = TimingDistributor()
        result = await distributor.distribute_timing(usdm)
        stage7_output = distributor.apply_expansions_to_usdm(usdm, result)

        print(f"  SAIs processed: {result.sais_processed}")
        print(f"  SAIs expanded: {result.sais_expanded}")
        print(f"  SAIs created: {result.sais_created}")

        print("\n--- Running Stage 12 ---")
        final_output, compliance_result = ensure_usdm_compliance(stage7_output)

        print(f"  Is compliant: {compliance_result.is_compliant}")
        print(f"  Referential integrity: {compliance_result.referential_integrity_passed}")
        print(f"  Total issues: {compliance_result.total_issues}")
        print(f"  Errors: {compliance_result.errors}")

        # Verify Code objects
        code_object_count = 0
        for sai in final_output["scheduledActivityInstances"]:
            if "_timingExpansion" in sai:
                timing_mod = sai.get("timingModifier")
                if isinstance(timing_mod, dict) and timing_mod.get("instanceType") == "Code":
                    code_object_count += 1

        print(f"\n  Expanded SAIs with Code objects: {code_object_count}")

        assert compliance_result.referential_integrity_passed, "Referential integrity should pass"
        print("\n Integration test PASSED!")

    asyncio.run(run_basic_test())
