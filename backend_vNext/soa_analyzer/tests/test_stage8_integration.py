"""
Integration tests for Stage 8 Cycle Expansion.

Tests the integration of Stage 8 with:
1. Stage 7 (Timing Distribution) → Stage 8 (Cycle Expansion)
2. Stage 8 (Cycle Expansion) → Stage 12 (USDM Compliance)
3. Full pipeline: Stage 7 → Stage 8 → Stage 12

Key validations:
1. Expanded encounters have proper USDM Code objects for cycleNumber
2. Referential integrity is maintained across expansion
3. SAIs are correctly duplicated for expanded encounters
4. Provenance metadata is preserved
5. All encounter fields are preserved during expansion

Run with: python -m pytest soa_analyzer/tests/test_stage8_integration.py -v
"""

import asyncio
import pytest
from typing import Dict, Any, List

# Import Stage 7
from soa_analyzer.interpretation.stage7_timing_distribution import (
    TimingDistributor,
    TimingDistributionConfig,
    distribute_timing,
)

# Import Stage 8
from soa_analyzer.interpretation.stage8_cycle_expansion import (
    CycleExpander,
    CycleExpansionConfig,
    expand_cycles,
)

# Import Stage 12
from soa_analyzer.interpretation.stage12_usdm_compliance import (
    USDMComplianceChecker,
    ComplianceResult,
    ensure_usdm_compliance,
)

# Import models
from soa_analyzer.models.cycle_expansion import (
    Stage8Result,
    CyclePatternType,
    is_already_expanded,
)
from soa_analyzer.models.code_object import is_usdm_compliant_code


def create_oncology_usdm() -> Dict[str, Any]:
    """Create a test USDM structure for oncology protocol with cycle patterns."""
    return {
        "activities": [
            {"id": "ACT-001", "name": "PK Blood Sample"},
            {"id": "ACT-002", "name": "Vital Signs"},
            {"id": "ACT-003", "name": "Physical Examination"},
            {"id": "ACT-004", "name": "ECG"},
        ],
        "encounters": [
            {
                "id": "ENC-001",
                "name": "Screening",
                "type": "Screening",
            },
            {
                "id": "ENC-002",
                "name": "Day 1 of Each Cycle",
                "type": "Treatment",
                "recurrence": {
                    "type": "PER_CYCLE",
                    "cycleDay": 1,
                    "maxCycles": 6,
                },
            },
            {
                "id": "ENC-003",
                "name": "Day 8 of Cycle 1 only",
                "type": "Treatment",
                # No recurrence - single cycle
            },
            {
                "id": "ENC-004",
                "name": "End of Treatment",
                "type": "EOT",
            },
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
                "scheduledInstanceEncounterId": "ENC-002",
                "isRequired": True,
            },
            {
                "id": "SAI-003",
                "activityId": "ACT-003",
                "scheduledInstanceEncounterId": "ENC-001",
                "isRequired": True,
            },
            {
                "id": "SAI-004",
                "activityId": "ACT-004",
                "scheduledInstanceEncounterId": "ENC-004",
                "isRequired": True,
            },
        ],
        "footnotes": [],
        "conditions": [],
        "conditionAssignments": [],
    }


def create_fixed_interval_usdm() -> Dict[str, Any]:
    """Create a test USDM structure with fixed interval recurrence."""
    return {
        "activities": [
            {"id": "ACT-001", "name": "Infusion"},
            {"id": "ACT-002", "name": "Labs"},
        ],
        "encounters": [
            {
                "id": "ENC-001",
                "name": "Baseline",
                "type": "Baseline",
            },
            {
                "id": "ENC-002",
                "name": "Every 3 weeks for 6 doses",
                "type": "Treatment",
                "recurrence": {
                    "type": "FIXED_INTERVAL",
                    "intervalValue": 3,
                    "intervalUnit": "weeks",
                    "maxOccurrences": 6,
                },
            },
            {
                "id": "ENC-003",
                "name": "Follow-up",
                "type": "Follow-up",
            },
        ],
        "scheduledActivityInstances": [
            {
                "id": "SAI-001",
                "activityId": "ACT-001",
                "scheduledInstanceEncounterId": "ENC-002",
                "isRequired": True,
            },
            {
                "id": "SAI-002",
                "activityId": "ACT-002",
                "scheduledInstanceEncounterId": "ENC-002",
                "isRequired": True,
            },
        ],
        "footnotes": [],
        "conditions": [],
    }


class TestStage7To8Integration:
    """Integration tests for Stage 7 → Stage 8 pipeline."""

    @pytest.mark.asyncio
    async def test_timing_then_cycle_expansion(self):
        """Test that Stage 7 output can be processed by Stage 8."""
        usdm = create_oncology_usdm()

        # Run Stage 7 (timing distribution)
        stage7_output, stage7_result = await distribute_timing(usdm)

        # Run Stage 8 (cycle expansion)
        expander = CycleExpander()
        stage8_result = await expander.expand_cycles(stage7_output)
        stage8_output = expander.apply_expansions_to_usdm(stage7_output, stage8_result)

        # Verify Stage 8 processed encounters
        assert stage8_result.encounters_processed > 0

        # Verify encounters are expanded
        encounters = stage8_output.get("encounters", [])
        encounter_ids = [e["id"] for e in encounters]

        # Should have expanded cycles (ENC-002-C1, ENC-002-C2, etc.)
        cycle_encounters = [eid for eid in encounter_ids if "-C" in eid]
        assert len(cycle_encounters) > 0, "Should have expanded cycle encounters"

    @pytest.mark.asyncio
    async def test_timing_expansion_preserved_after_cycle_expansion(self):
        """Test that Stage 7 timing expansion metadata is preserved after Stage 8."""
        usdm = create_oncology_usdm()

        # Run Stage 7
        stage7_output, _ = await distribute_timing(usdm)

        # Check if any SAIs were expanded in Stage 7
        stage7_expanded_sais = [
            sai for sai in stage7_output.get("scheduledActivityInstances", [])
            if "_timingExpansion" in sai
        ]

        # Run Stage 8
        expander = CycleExpander()
        stage8_result = await expander.expand_cycles(stage7_output)
        stage8_output = expander.apply_expansions_to_usdm(stage7_output, stage8_result)

        # Verify Stage 7 metadata is preserved
        for sai in stage8_output.get("scheduledActivityInstances", []):
            if "_timingExpansion" in sai:
                timing_meta = sai["_timingExpansion"]
                assert "originalId" in timing_meta
                assert "stage" in timing_meta
                assert timing_meta["stage"] == "Stage7TimingDistribution"

    @pytest.mark.asyncio
    async def test_sais_duplicated_for_expanded_encounters(self):
        """Test that SAIs referencing expanded encounters are duplicated."""
        usdm = create_oncology_usdm()

        # Run Stage 8
        expander = CycleExpander()
        stage8_result = await expander.expand_cycles(usdm)
        stage8_output = expander.apply_expansions_to_usdm(usdm, stage8_result)

        # Find SAIs that reference expanded encounters
        sais = stage8_output.get("scheduledActivityInstances", [])
        cycle_sais = [sai for sai in sais if "-C" in sai.get("id", "")]

        # Should have duplicated SAIs for each cycle
        if stage8_result.encounters_expanded > 0:
            assert len(cycle_sais) > 0, "Should have cycle-specific SAIs"

            # Verify SAI IDs follow pattern: SAI-XXX-CY
            for sai in cycle_sais:
                assert "_cycleExpansion" in sai
                assert "originalSaiId" in sai["_cycleExpansion"]


class TestStage8To12Integration:
    """Integration tests for Stage 8 → Stage 12 pipeline."""

    @pytest.mark.asyncio
    async def test_expanded_encounters_pass_compliance(self):
        """Test that Stage 8 expanded encounters pass Stage 12 compliance."""
        usdm = create_oncology_usdm()

        # Run Stage 8
        expander = CycleExpander()
        stage8_result = await expander.expand_cycles(usdm)
        stage8_output = expander.apply_expansions_to_usdm(usdm, stage8_result)

        # Run Stage 12
        checker = USDMComplianceChecker()
        final_output, compliance_result = checker.ensure_compliance(stage8_output)

        # Check referential integrity
        assert compliance_result.referential_integrity_passed, \
            f"Referential integrity failed: {[i.message for i in compliance_result.issues if i.category == 'referential_integrity']}"

    @pytest.mark.asyncio
    async def test_cycle_number_code_objects_valid(self):
        """Test that cycleNumber fields have valid USDM Code objects."""
        usdm = create_oncology_usdm()

        # Run Stage 8
        expander = CycleExpander()
        stage8_result = await expander.expand_cycles(usdm)
        stage8_output = expander.apply_expansions_to_usdm(usdm, stage8_result)

        # Run Stage 12
        checker = USDMComplianceChecker()
        final_output, compliance_result = checker.ensure_compliance(stage8_output)

        # Check cycleNumber Code objects
        for encounter in final_output.get("encounters", []):
            if "_cycleExpansion" in encounter:
                cycle_num = encounter.get("cycleNumber")
                assert cycle_num is not None, f"Encounter {encounter['id']} missing cycleNumber"
                assert isinstance(cycle_num, dict), f"cycleNumber should be dict, got {type(cycle_num)}"
                assert cycle_num.get("instanceType") == "Code", "cycleNumber should be Code object"
                assert "decode" in cycle_num, "cycleNumber should have decode"

    @pytest.mark.asyncio
    async def test_referential_integrity_after_expansion(self):
        """Test that all SAI references point to valid expanded encounters."""
        usdm = create_oncology_usdm()

        # Run Stage 8
        expander = CycleExpander()
        stage8_result = await expander.expand_cycles(usdm)
        stage8_output = expander.apply_expansions_to_usdm(usdm, stage8_result)

        # Collect all IDs
        activity_ids = {a["id"] for a in stage8_output.get("activities", [])}
        encounter_ids = {e["id"] for e in stage8_output.get("encounters", [])}

        # Check all SAI references
        for sai in stage8_output.get("scheduledActivityInstances", []):
            assert sai["activityId"] in activity_ids, \
                f"SAI {sai['id']} references non-existent activity {sai['activityId']}"

            enc_id = sai.get("scheduledInstanceEncounterId") or sai.get("visitId")
            assert enc_id in encounter_ids, \
                f"SAI {sai['id']} references non-existent encounter {enc_id}"


class TestFullPipelineIntegration:
    """Full pipeline integration tests: Stage 7 → Stage 8 → Stage 12."""

    @pytest.mark.asyncio
    async def test_oncology_protocol_full_pipeline(self):
        """Test full pipeline with oncology protocol."""
        usdm = create_oncology_usdm()

        # Run Stage 7
        stage7_output, stage7_result = await distribute_timing(usdm)

        # Run Stage 8
        stage8_output, stage8_result = await expand_cycles(stage7_output)

        # Run Stage 12
        final_output, compliance_result = ensure_usdm_compliance(stage8_output)

        # Summary checks
        assert stage7_result.sais_processed > 0
        assert stage8_result.encounters_processed > 0
        assert compliance_result.referential_integrity_passed

        # Verify expanded encounters
        expanded_encounters = [
            e for e in final_output.get("encounters", [])
            if "_cycleExpansion" in e
        ]

        if stage8_result.encounters_expanded > 0:
            assert len(expanded_encounters) > 0

            # Each should have cycleNumber Code object
            for enc in expanded_encounters:
                cycle_num = enc.get("cycleNumber")
                assert isinstance(cycle_num, dict)
                assert cycle_num.get("instanceType") == "Code"

    @pytest.mark.asyncio
    async def test_fixed_interval_protocol_full_pipeline(self):
        """Test full pipeline with fixed interval recurrence."""
        usdm = create_fixed_interval_usdm()

        # Run Stage 8 (skip Stage 7 - no timing modifiers)
        stage8_output, stage8_result = await expand_cycles(usdm)

        # Run Stage 12
        final_output, compliance_result = ensure_usdm_compliance(stage8_output)

        # Should pass compliance
        assert compliance_result.referential_integrity_passed

    @pytest.mark.asyncio
    async def test_provenance_chain_through_pipeline(self):
        """Test that provenance is maintained through all stages."""
        usdm = create_oncology_usdm()

        # Run full pipeline
        stage7_output, _ = await distribute_timing(usdm)
        stage8_output, _ = await expand_cycles(stage7_output)
        final_output, _ = ensure_usdm_compliance(stage8_output)

        # Check SAI provenance
        for sai in final_output.get("scheduledActivityInstances", []):
            # Timing expansion metadata (from Stage 7)
            if "_timingExpansion" in sai:
                timing_meta = sai["_timingExpansion"]
                assert "stage" in timing_meta
                assert timing_meta["stage"] == "Stage7TimingDistribution"

            # Cycle expansion metadata (from Stage 8)
            if "_cycleExpansion" in sai:
                cycle_meta = sai["_cycleExpansion"]
                assert "stage" in cycle_meta
                assert cycle_meta["stage"] == "Stage8CycleExpansion"
                assert "originalSaiId" in cycle_meta

        # Check encounter provenance
        for enc in final_output.get("encounters", []):
            if "_cycleExpansion" in enc:
                cycle_meta = enc["_cycleExpansion"]
                assert "originalId" in cycle_meta
                assert "cycleNumber" in cycle_meta
                assert "stage" in cycle_meta
                assert "timestamp" in cycle_meta

    @pytest.mark.asyncio
    async def test_non_expandable_encounters_preserved(self):
        """Test that Screening, EOT, etc. are not expanded."""
        usdm = create_oncology_usdm()

        # Run Stage 8
        stage8_output, stage8_result = await expand_cycles(usdm)

        # Find non-expandable encounters
        encounters = stage8_output.get("encounters", [])
        screening = [e for e in encounters if e.get("name") == "Screening"]
        eot = [e for e in encounters if e.get("name") == "End of Treatment"]
        cycle1_only = [e for e in encounters if "Cycle 1 only" in e.get("name", "")]

        # Should still have exactly one of each
        assert len(screening) == 1, "Screening should not be expanded"
        assert len(eot) == 1, "EOT should not be expanded"
        assert len(cycle1_only) == 1, "Cycle 1 only should not be expanded"

        # None should have _cycleExpansion
        for enc in screening + eot + cycle1_only:
            assert "_cycleExpansion" not in enc

    @pytest.mark.asyncio
    async def test_encounter_fields_preserved(self):
        """Test that all original encounter fields are preserved during expansion."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "Test"}],
            "encounters": [
                {
                    "id": "ENC-001",
                    "name": "Cycle Day 1",
                    "type": "Treatment",
                    "footnoteMarkers": ["a", "b"],
                    "window": {
                        "description": "±3 days",
                        "lower": -3,
                        "upper": 3,
                    },
                    "recurrence": {
                        "type": "PER_CYCLE",
                        "cycleDay": 1,
                        "maxCycles": 3,
                    },
                },
            ],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "scheduledInstanceEncounterId": "ENC-001",
                },
            ],
        }

        stage8_output, stage8_result = await expand_cycles(usdm)

        # Check expanded encounters preserve fields
        for enc in stage8_output.get("encounters", []):
            if "_cycleExpansion" in enc:
                # Should preserve type
                assert enc.get("type") == "Treatment"

                # Should preserve footnoteMarkers
                assert enc.get("footnoteMarkers") == ["a", "b"]

                # Should preserve window
                window = enc.get("window")
                assert window is not None
                assert window.get("description") == "±3 days"


class TestStage8EdgeCases:
    """Edge case tests for Stage 8 integration."""

    @pytest.mark.asyncio
    async def test_already_expanded_not_reexpanded(self):
        """Test that already expanded encounters are not re-expanded."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "Test"}],
            "encounters": [
                {
                    "id": "ENC-001-C1",  # Already expanded ID
                    "name": "Cycle 1 Day 1",
                    "_cycleExpansion": {"originalId": "ENC-001", "cycleNumber": 1},
                },
                {
                    "id": "ENC-001-C2",
                    "name": "Cycle 2 Day 1",
                    "_cycleExpansion": {"originalId": "ENC-001", "cycleNumber": 2},
                },
            ],
            "scheduledActivityInstances": [],
        }

        stage8_output, stage8_result = await expand_cycles(usdm)

        # Should not expand further
        assert stage8_result.encounters_expanded == 0

        # Should still have exactly 2 encounters
        assert len(stage8_output.get("encounters", [])) == 2

    @pytest.mark.asyncio
    async def test_event_driven_flagged_for_review(self):
        """Test that event-driven recurrence is flagged for human review."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "Test"}],
            "encounters": [
                {
                    "id": "ENC-001",
                    "name": "Treatment until progression",
                    "recurrence": {
                        "type": "AT_EVENT",
                        "triggerEvent": "progression",
                    },
                },
            ],
            "scheduledActivityInstances": [],
        }

        stage8_output, stage8_result = await expand_cycles(usdm)

        # Should flag for review
        assert stage8_result.needs_review > 0

        # Should not expand
        assert stage8_result.encounters_expanded == 0

        # Should have review items
        assert len(stage8_result.review_items) > 0

        review_reasons = [item.reason for item in stage8_result.review_items]
        assert any("progression" in r.lower() or "event" in r.lower() for r in review_reasons)

    @pytest.mark.asyncio
    async def test_empty_encounters_list(self):
        """Test handling of empty encounters list."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "Test"}],
            "encounters": [],
            "scheduledActivityInstances": [],
        }

        expander = CycleExpander()
        stage8_result = await expander.expand_cycles(usdm)

        assert stage8_result.encounters_processed == 0
        assert stage8_result.encounters_expanded == 0

    @pytest.mark.asyncio
    async def test_mixed_recurrence_types(self):
        """Test handling of mixed recurrence types in same protocol."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "Test"}],
            "encounters": [
                {
                    "id": "ENC-001",
                    "name": "Day 1 of Each Cycle",
                    "recurrence": {"type": "PER_CYCLE", "cycleDay": 1, "maxCycles": 4},
                },
                {
                    "id": "ENC-002",
                    "name": "Every 2 weeks",
                    "recurrence": {"type": "FIXED_INTERVAL", "intervalValue": 2, "intervalUnit": "weeks", "maxOccurrences": 6},
                },
                {
                    "id": "ENC-003",
                    "name": "Screening",
                    # No recurrence
                },
            ],
            "scheduledActivityInstances": [],
        }

        stage8_output, stage8_result = await expand_cycles(usdm)

        # Should have processed all encounters
        assert stage8_result.encounters_processed == 3

        # Screening should not be expanded
        screening = [e for e in stage8_output.get("encounters", []) if e.get("name") == "Screening"]
        assert len(screening) == 1
        assert "_cycleExpansion" not in screening[0]


if __name__ == "__main__":
    # Run basic integration test without pytest
    print("Running Stage 8 Integration Tests...")

    async def run_basic_test():
        usdm = create_oncology_usdm()

        print("\n--- Running Stage 7 ---")
        stage7_output, stage7_result = await distribute_timing(usdm)
        print(f"  SAIs processed: {stage7_result.sais_processed}")
        print(f"  SAIs expanded: {stage7_result.sais_expanded}")

        print("\n--- Running Stage 8 ---")
        stage8_output, stage8_result = await expand_cycles(stage7_output)
        print(f"  Encounters processed: {stage8_result.encounters_processed}")
        print(f"  Encounters expanded: {stage8_result.encounters_expanded}")
        print(f"  SAIs duplicated: {stage8_result.sais_duplicated}")

        print("\n--- Running Stage 12 ---")
        final_output, compliance_result = ensure_usdm_compliance(stage8_output)
        print(f"  Is compliant: {compliance_result.is_compliant}")
        print(f"  Referential integrity: {compliance_result.referential_integrity_passed}")
        print(f"  Total issues: {compliance_result.total_issues}")

        # Summary
        expanded_encounters = [
            e for e in final_output.get("encounters", [])
            if "_cycleExpansion" in e
        ]
        print(f"\n  Expanded encounters: {len(expanded_encounters)}")

        cycle_sais = [
            sai for sai in final_output.get("scheduledActivityInstances", [])
            if "_cycleExpansion" in sai
        ]
        print(f"  Cycle-specific SAIs: {len(cycle_sais)}")

        assert compliance_result.referential_integrity_passed, "Referential integrity should pass"
        print("\n✓ Integration test PASSED!")

    asyncio.run(run_basic_test())
