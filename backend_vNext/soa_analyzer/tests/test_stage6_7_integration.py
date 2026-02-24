"""
Integration tests for Stage 6 → Stage 7 → Stage 12 pipeline.

Validates that:
1. Stage 7 flags SAIs with footnotes correctly
2. Stage 6 processes those flags and creates Conditions
3. Stage 12 passes compliance on the final output
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
    Stage6Result,
)
from soa_analyzer.interpretation.stage7_timing_distribution import (
    TimingDistributor,
    TimingDistributionConfig,
)
from soa_analyzer.interpretation.stage12_usdm_compliance import (
    USDMComplianceChecker,
)
from soa_analyzer.models.condition import Condition, ConditionAssignment


class TestStage7FootnoteFlags:
    """Tests for Stage 7's footnote flagging feature."""

    def test_stage7_preserves_footnote_markers(self):
        """Test that Stage 7 preserves footnote markers on expanded SAIs."""
        # Simulated Stage 7 output (after timing expansion)
        stage7_output = {
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001-BI",
                    "activityId": "ACT-001",
                    "timingModifier": {"code": "C71148", "decode": "Before Infusion"},
                    "footnoteMarkers": ["a", "c"],
                    "_hasFootnoteCondition": True,
                    "_footnoteMarkersPreserved": ["a", "c"],
                },
                {
                    "id": "SAI-001-EOI",
                    "activityId": "ACT-001",
                    "timingModifier": {"code": "C71149", "decode": "End of Infusion"},
                    "footnoteMarkers": ["a", "c"],
                    "_hasFootnoteCondition": True,
                    "_footnoteMarkersPreserved": ["a", "c"],
                },
            ],
            "footnotes": [
                {"marker": "a", "text": "For female subjects of childbearing potential only"},
                {"marker": "c", "text": "If clinically indicated"},
            ],
        }

        # Verify Stage 7 flags are present
        for sai in stage7_output["scheduledActivityInstances"]:
            assert "_hasFootnoteCondition" in sai
            assert sai["_hasFootnoteCondition"] is True
            assert "footnoteMarkers" in sai
            assert len(sai["footnoteMarkers"]) > 0


class TestStage6ProcessesStage7Flags:
    """Tests for Stage 6 processing Stage 7 footnote flags."""

    @pytest.mark.asyncio
    async def test_stage6_creates_conditions_from_footnotes(self):
        """Test that Stage 6 creates Conditions from footnotes."""
        # Simulated Stage 7 output
        usdm = {
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001-BI",
                    "activityId": "ACT-001",
                    "footnoteMarkers": ["a"],
                    "_hasFootnoteCondition": True,
                },
            ],
            "footnotes": [
                {"marker": "a", "text": "For female subjects of childbearing potential only"},
            ],
            "conditions": [],
            "conditionAssignments": [],
        }

        # Mock LLM response
        mock_response = json.dumps({
            "conditions": [
                {
                    "footnote_marker": "a",
                    "has_condition": True,
                    "condition_type": "DEMOGRAPHIC_FERTILITY",
                    "condition_name": "Female of Childbearing Potential",
                    "condition_text": "For female subjects of childbearing potential only",
                    "criterion": {"sex": "F", "fertilityStatus": "fertile"},
                    "confidence": 0.95,
                    "rationale": "Explicitly identifies WOCBP population",
                }
            ]
        })

        config = ConditionalExpansionConfig(use_cache=False)
        expander = ConditionalExpander(config)

        # Mock the LLM call
        with patch.object(expander, '_call_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response

            result = await expander.expand_conditions(usdm)
            updated = expander.apply_conditions_to_usdm(usdm, result)

        # Verify conditions created
        assert result.conditions_created >= 1
        assert len(updated["conditions"]) >= 1

        # Verify condition has correct type
        condition = updated["conditions"][0]
        assert condition["name"] == "Female of Childbearing Potential"

    @pytest.mark.asyncio
    async def test_stage6_removes_stage7_flags(self):
        """Test that Stage 6 removes Stage 7 processing flags."""
        usdm = {
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "footnoteMarkers": ["a"],
                    "_hasFootnoteCondition": True,
                    "_footnoteMarkersPreserved": ["a"],
                },
            ],
            "footnotes": [
                {"marker": "a", "text": "For female subjects only"},
            ],
            "conditions": [],
            "conditionAssignments": [],
        }

        # Create a condition for the test
        result = Stage6Result()
        condition = Condition(
            name="Female Only",
            text="For female subjects only",
        )
        result.conditions.append(condition)
        result.marker_to_condition["a"] = condition.id

        expander = ConditionalExpander()
        updated = expander.apply_conditions_to_usdm(usdm, result)

        # Stage 7 flags should be removed
        sai = updated["scheduledActivityInstances"][0]
        assert "_hasFootnoteCondition" not in sai
        assert "_footnoteMarkersPreserved" not in sai

        # But footnoteMarkers should remain
        assert "footnoteMarkers" in sai


class TestStage6To12Compliance:
    """Tests for Stage 6 → Stage 12 compliance."""

    @pytest.mark.asyncio
    async def test_stage6_conditions_pass_stage12(self):
        """Test that Stage 6 conditions pass Stage 12 compliance."""
        # Create USDM with Stage 6 processed conditions
        usdm = {
            "activities": [{"id": "ACT-001", "name": "Pregnancy Test"}],
            "encounters": [{"id": "ENC-001", "name": "Screening"}],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "footnoteMarkers": ["a"],
                    "defaultConditionId": "COND-001",
                },
            ],
            "conditions": [
                {
                    "id": "COND-001",
                    "instanceType": "Condition",
                    "name": "Female of Childbearing Potential",
                    "text": "For female subjects of childbearing potential only",
                },
            ],
            "conditionAssignments": [
                {
                    "id": "CA-001",
                    "instanceType": "ConditionAssignment",
                    "conditionId": "COND-001",
                    "conditionTargetId": "SAI-001",
                },
            ],
            "footnotes": [
                {"id": "FN-001", "marker": "a", "text": "For WOCBP only"},
            ],
        }

        # Run Stage 12 compliance check
        checker = USDMComplianceChecker()
        updated, compliance_result = checker.ensure_compliance(usdm)

        # Should pass referential integrity
        assert compliance_result.referential_integrity_passed

        # No errors should be present
        errors = [i for i in compliance_result.issues if i.severity == "error"]
        assert len(errors) == 0, f"Errors: {[e.message for e in errors]}"

    def test_stage12_validates_condition_references(self):
        """Test that Stage 12 catches invalid condition references."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "Test"}],
            "encounters": [{"id": "ENC-001", "name": "Visit"}],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "defaultConditionId": "COND-INVALID",  # Non-existent!
                },
            ],
            "conditions": [],  # Empty - no conditions defined
            "conditionAssignments": [],
            "footnotes": [],
        }

        checker = USDMComplianceChecker()
        _, compliance_result = checker.ensure_compliance(usdm)

        # Should have referential integrity warning
        warnings = [i for i in compliance_result.issues if i.severity == "warning"]
        condition_warnings = [w for w in warnings if "condition" in w.message.lower()]
        assert len(condition_warnings) > 0


class TestFullPipelineIntegration:
    """Tests for the full Stage 7 → Stage 6 → Stage 12 pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_timing_and_conditions(self):
        """Test complete pipeline with both timing expansion and conditions."""
        # Initial USDM input
        usdm = {
            "activities": [
                {"id": "ACT-001", "name": "PK Sample"},
                {"id": "ACT-002", "name": "Pregnancy Test"},
            ],
            "encounters": [{"id": "ENC-001", "name": "Cycle 1 Day 1"}],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "timingModifier": "BI/EOI",
                    "footnoteMarkers": ["c"],
                },
                {
                    "id": "SAI-002",
                    "activityId": "ACT-002",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "footnoteMarkers": ["a"],
                },
            ],
            "footnotes": [
                {"marker": "a", "text": "For female subjects of childbearing potential only"},
                {"marker": "c", "text": "PK samples taken pre and post dose"},
            ],
            "conditions": [],
            "conditionAssignments": [],
        }

        # Simulate Stage 7 output (timing expanded, footnotes flagged)
        stage7_output = {
            **usdm,
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001-BI",
                    "activityId": "ACT-001",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "timingModifier": {"code": "C71148", "decode": "Before Infusion"},
                    "footnoteMarkers": ["c"],
                    "_hasFootnoteCondition": True,
                },
                {
                    "id": "SAI-001-EOI",
                    "activityId": "ACT-001",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "timingModifier": {"code": "C71149", "decode": "End of Infusion"},
                    "footnoteMarkers": ["c"],
                    "_hasFootnoteCondition": True,
                },
                {
                    "id": "SAI-002",
                    "activityId": "ACT-002",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "footnoteMarkers": ["a"],
                    "_hasFootnoteCondition": True,
                },
            ],
        }

        # Stage 6: Create conditions for WOCBP footnote
        result = Stage6Result()
        condition = Condition(
            name="Female of Childbearing Potential",
            text="For female subjects of childbearing potential only",
            source_footnote_marker="a",
        )
        result.conditions.append(condition)
        result.marker_to_condition["a"] = condition.id

        expander = ConditionalExpander()
        stage6_output = expander.apply_conditions_to_usdm(stage7_output, result)

        # Stage 12: Compliance check
        checker = USDMComplianceChecker()
        final_output, compliance_result = checker.ensure_compliance(stage6_output)

        # Verify pipeline results
        # 1. Conditions created
        assert len(final_output["conditions"]) >= 1

        # 2. Assignments created for WOCBP SAI
        assignments = final_output["conditionAssignments"]
        wocbp_assignments = [a for a in assignments if a["conditionTargetId"] == "SAI-002"]
        assert len(wocbp_assignments) >= 1

        # 3. SAI has defaultConditionId
        pregnancy_sai = next(
            s for s in final_output["scheduledActivityInstances"]
            if s["id"] == "SAI-002"
        )
        assert pregnancy_sai.get("defaultConditionId") == condition.id

        # 4. Stage 7 flags removed
        for sai in final_output["scheduledActivityInstances"]:
            assert "_hasFootnoteCondition" not in sai

        # 5. Compliance passed
        assert compliance_result.referential_integrity_passed


class TestEdgeCases:
    """Tests for edge cases in Stage 6+7 integration."""

    def test_multiple_conditions_same_sai(self):
        """Test SAI with multiple condition footnotes."""
        usdm = {
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "footnoteMarkers": ["a", "b"],  # Two conditions
                },
            ],
            "footnotes": [
                {"marker": "a", "text": "Female subjects only"},
                {"marker": "b", "text": "If clinically indicated"},
            ],
            "conditions": [],
            "conditionAssignments": [],
        }

        # Create two conditions
        result = Stage6Result()
        cond_a = Condition(name="Female Only", text="Female subjects only")
        cond_b = Condition(name="Clinically Indicated", text="If clinically indicated")
        result.conditions.extend([cond_a, cond_b])
        result.marker_to_condition["a"] = cond_a.id
        result.marker_to_condition["b"] = cond_b.id

        expander = ConditionalExpander()
        updated = expander.apply_conditions_to_usdm(usdm, result)

        # Should have 2 conditions
        assert len(updated["conditions"]) == 2

        # Should have 2 assignments for the SAI
        assert len(updated["conditionAssignments"]) == 2

        # First condition should be the defaultConditionId
        sai = updated["scheduledActivityInstances"][0]
        assert sai["defaultConditionId"] in [cond_a.id, cond_b.id]

    def test_shared_condition_across_sais(self):
        """Test same condition applied to multiple SAIs."""
        usdm = {
            "scheduledActivityInstances": [
                {"id": "SAI-001", "footnoteMarkers": ["a"]},
                {"id": "SAI-002", "footnoteMarkers": ["a"]},  # Same footnote
                {"id": "SAI-003", "footnoteMarkers": ["a"]},  # Same footnote
            ],
            "footnotes": [
                {"marker": "a", "text": "Female subjects only"},
            ],
            "conditions": [],
            "conditionAssignments": [],
        }

        # Single condition shared across SAIs
        result = Stage6Result()
        condition = Condition(name="Female Only", text="Female subjects only")
        result.conditions.append(condition)
        result.marker_to_condition["a"] = condition.id

        expander = ConditionalExpander()
        updated = expander.apply_conditions_to_usdm(usdm, result)

        # Only 1 condition
        assert len(updated["conditions"]) == 1

        # But 3 assignments
        assert len(updated["conditionAssignments"]) == 3

        # All SAIs point to same condition
        for sai in updated["scheduledActivityInstances"]:
            assert sai["defaultConditionId"] == condition.id

    def test_footnote_without_condition(self):
        """Test footnote that doesn't describe a condition."""
        usdm = {
            "scheduledActivityInstances": [
                {"id": "SAI-001", "footnoteMarkers": ["a"]},
            ],
            "footnotes": [
                {"marker": "a", "text": "See Appendix B for collection instructions"},
            ],
            "conditions": [],
            "conditionAssignments": [],
        }

        # No conditions extracted (footnote is informational)
        result = Stage6Result()
        # marker_to_condition is empty - no condition for marker "a"

        expander = ConditionalExpander()
        updated = expander.apply_conditions_to_usdm(usdm, result)

        # No conditions or assignments
        assert len(updated["conditions"]) == 0
        assert len(updated["conditionAssignments"]) == 0

        # SAI should not have defaultConditionId
        assert "defaultConditionId" not in updated["scheduledActivityInstances"][0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
