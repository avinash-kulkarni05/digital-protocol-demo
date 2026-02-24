"""
Integration tests for Stage 4: Alternative Resolution.

Tests Stage 4's integration with:
- Stage 6: Conditional Expansion (footnote-linked alternatives)
- Stage 12: USDM Compliance (Code object validation)
- Full pipeline: Stage 4 → Stage 6 → Stage 12
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from soa_analyzer.models.alternative_expansion import (
    AlternativeType,
    ResolutionAction,
    AlternativeOption,
    AlternativeDecision,
    Stage4Result,
    AlternativeResolutionConfig,
)

from soa_analyzer.interpretation.stage4_alternative_resolution import (
    AlternativeResolver,
    AlternativePatternRegistry,
)


# ============================================================================
# Stage 4 → Stage 12 Integration Tests
# ============================================================================

class TestStage4To12Integration:
    """Tests for Stage 4 output passing Stage 12 USDM compliance checks."""

    @pytest.mark.asyncio
    async def test_expanded_activities_have_valid_structure(self):
        """Test that Stage 4 expanded activities have valid USDM structure."""
        resolver = AlternativeResolver(AlternativeResolutionConfig(use_cache=False))

        # Create a decision with alternatives
        decision = AlternativeDecision(
            activity_id="ACT-001",
            activity_name="CT or MRI",
            is_alternative=True,
            alternative_type=AlternativeType.MUTUALLY_EXCLUSIVE,
            alternatives=[
                AlternativeOption(name="CT scan", order=1, confidence=0.95),
                AlternativeOption(name="MRI", order=2, confidence=0.95),
            ],
            recommended_action=ResolutionAction.EXPAND,
            confidence=0.95,
            rationale="Test expansion",
        )

        # Generate expansion
        original_activity = {"id": "ACT-001", "name": "CT or MRI", "cdiscDomain": "MI"}
        sais = [{"id": "SAI-001", "activityId": "ACT-001", "visitId": "ENC-001"}]
        usdm = {"activities": [original_activity], "scheduledActivityInstances": sais}

        expansion = resolver._generate_expansion(original_activity, decision, sais, usdm)

        # Validate expanded activities structure
        assert len(expansion.expanded_activities) == 2

        for activity in expansion.expanded_activities:
            # Must have required USDM fields
            assert "id" in activity
            assert "name" in activity
            assert "instanceType" in activity
            assert activity["instanceType"] == "Activity"
            # Must have provenance
            assert "_alternativeResolution" in activity
            assert "originalActivityId" in activity["_alternativeResolution"]
            assert "stage" in activity["_alternativeResolution"]
            assert activity["_alternativeResolution"]["stage"] == "Stage4AlternativeResolution"

    @pytest.mark.asyncio
    async def test_conditions_have_6_field_code_objects(self):
        """Test that Stage 4 conditions have USDM 4.0 compliant Code objects."""
        resolver = AlternativeResolver(AlternativeResolutionConfig(use_cache=False))

        decision = AlternativeDecision(
            activity_id="ACT-001",
            activity_name="CT or MRI",
            is_alternative=True,
            alternative_type=AlternativeType.MUTUALLY_EXCLUSIVE,
            alternatives=[
                AlternativeOption(name="CT scan", order=1, confidence=0.95),
                AlternativeOption(name="MRI", order=2, confidence=0.95),
            ],
            recommended_action=ResolutionAction.EXPAND,
            confidence=0.95,
        )

        original_activity = {"id": "ACT-001", "name": "CT or MRI"}
        sais = [{"id": "SAI-001", "activityId": "ACT-001", "visitId": "ENC-001"}]
        usdm = {"activities": [original_activity], "scheduledActivityInstances": sais}

        expansion = resolver._generate_expansion(original_activity, decision, sais, usdm)

        # Validate conditions
        assert len(expansion.conditions_created) == 2

        for condition in expansion.conditions_created:
            assert "id" in condition
            assert "instanceType" in condition
            assert condition["instanceType"] == "Condition"
            assert "conditionType" in condition

            # conditionType should be a 6-field Code object
            cond_type = condition["conditionType"]
            assert "id" in cond_type
            assert "code" in cond_type
            assert "decode" in cond_type
            assert "codeSystem" in cond_type
            assert "codeSystemVersion" in cond_type
            assert "instanceType" in cond_type
            assert cond_type["instanceType"] == "Code"

    @pytest.mark.asyncio
    async def test_sais_have_valid_references(self):
        """Test that expanded SAIs have valid activity and condition references."""
        resolver = AlternativeResolver(AlternativeResolutionConfig(use_cache=False))

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
        )

        original_activity = {"id": "ACT-001", "name": "CT or MRI"}
        sais = [{"id": "SAI-001", "activityId": "ACT-001", "visitId": "ENC-001"}]
        usdm = {"activities": [original_activity], "scheduledActivityInstances": sais}

        expansion = resolver._generate_expansion(original_activity, decision, sais, usdm)

        # Build ID sets for validation
        expanded_activity_ids = {a["id"] for a in expansion.expanded_activities}
        condition_ids = {c["id"] for c in expansion.conditions_created}

        # Validate SAI references
        for sai in expansion.expanded_sais:
            assert sai["activityId"] in expanded_activity_ids, f"SAI {sai['id']} references non-existent activity"
            assert sai.get("defaultConditionId") in condition_ids, f"SAI {sai['id']} references non-existent condition"


# ============================================================================
# Stage 4 + Stage 6 Integration Tests
# ============================================================================

class TestStage4WithFootnotes:
    """Tests for Stage 4 handling activities with footnote-linked conditions."""

    @pytest.mark.asyncio
    async def test_preserves_footnote_markers_on_expansion(self):
        """Stage 4 preserves footnote markers for Stage 6 processing."""
        resolver = AlternativeResolver(AlternativeResolutionConfig(use_cache=False))

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
        )

        original_activity = {"id": "ACT-001", "name": "CT or MRI"}
        sais = [{
            "id": "SAI-001",
            "activityId": "ACT-001",
            "visitId": "ENC-001",
            "footnoteMarkers": ["a", "c"],  # Footnotes for Stage 6
        }]
        usdm = {"activities": [original_activity], "scheduledActivityInstances": sais}

        expansion = resolver._generate_expansion(original_activity, decision, sais, usdm)

        # Check footnote markers are preserved on expanded SAIs
        for sai in expansion.expanded_sais:
            assert "footnoteMarkers" in sai
            assert sai["footnoteMarkers"] == ["a", "c"]

    @pytest.mark.asyncio
    async def test_preserves_timing_modifier_on_expansion(self):
        """Stage 4 preserves timing modifiers for Stage 7 processing."""
        resolver = AlternativeResolver(AlternativeResolutionConfig(use_cache=False))

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
        )

        original_activity = {"id": "ACT-001", "name": "CT or MRI"}
        timing_modifier = {
            "id": "CODE-TIM-001",
            "code": "C71148",
            "decode": "Before Infusion",
            "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
            "codeSystemVersion": "24.12",
            "instanceType": "Code",
        }
        sais = [{
            "id": "SAI-001",
            "activityId": "ACT-001",
            "visitId": "ENC-001",
            "timingModifier": timing_modifier,
        }]
        usdm = {"activities": [original_activity], "scheduledActivityInstances": sais}

        expansion = resolver._generate_expansion(original_activity, decision, sais, usdm)

        # Check timing modifier is preserved on expanded SAIs
        for sai in expansion.expanded_sais:
            assert "timingModifier" in sai
            assert sai["timingModifier"]["code"] == "C71148"


# ============================================================================
# M:N Expansion Tests
# ============================================================================

class TestManyToManyExpansion:
    """Tests for M:N activity→SAI expansion scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_sais_expanded_for_one_activity(self):
        """Multiple SAIs referencing same activity all get expanded."""
        resolver = AlternativeResolver(AlternativeResolutionConfig(use_cache=False))

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
        )

        original_activity = {"id": "ACT-001", "name": "CT or MRI"}
        # 3 SAIs reference the same activity at different visits
        sais = [
            {"id": "SAI-001", "activityId": "ACT-001", "visitId": "ENC-001"},
            {"id": "SAI-002", "activityId": "ACT-001", "visitId": "ENC-002"},
            {"id": "SAI-003", "activityId": "ACT-001", "visitId": "ENC-003"},
        ]
        usdm = {"activities": [original_activity], "scheduledActivityInstances": sais}

        expansion = resolver._generate_expansion(original_activity, decision, sais, usdm)

        # 2 alternatives x 3 visits = 6 expanded SAIs
        assert len(expansion.expanded_sais) == 6

        # Verify each visit has 2 SAI variants
        visit_sai_counts = {}
        for sai in expansion.expanded_sais:
            visit_id = sai["scheduledInstanceEncounterId"]
            visit_sai_counts[visit_id] = visit_sai_counts.get(visit_id, 0) + 1

        assert visit_sai_counts == {"ENC-001": 2, "ENC-002": 2, "ENC-003": 2}

    @pytest.mark.asyncio
    async def test_deterministic_id_generation(self):
        """Expanded IDs are deterministic and consistent."""
        resolver = AlternativeResolver(AlternativeResolutionConfig(use_cache=False))

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
        )

        original_activity = {"id": "ACT-001", "name": "CT or MRI"}
        sais = [{"id": "SAI-001", "activityId": "ACT-001", "visitId": "ENC-001"}]
        usdm = {"activities": [original_activity], "scheduledActivityInstances": sais}

        # Run twice
        expansion1 = resolver._generate_expansion(original_activity, decision, sais, usdm)
        expansion2 = resolver._generate_expansion(original_activity, decision, sais, usdm)

        # IDs should be the same
        ids1 = {a["id"] for a in expansion1.expanded_activities}
        ids2 = {a["id"] for a in expansion2.expanded_activities}
        assert ids1 == ids2

        # Verify ID format
        assert "ACT-001-A" in ids1
        assert "ACT-001-B" in ids1


# ============================================================================
# Multi-Way Alternative Tests
# ============================================================================

class TestMultiWayAlternatives:
    """Tests for 3+ option alternatives."""

    @pytest.mark.asyncio
    async def test_three_way_alternative_expansion(self):
        """Three-way alternatives (CT, MRI, PET) expand correctly."""
        resolver = AlternativeResolver(AlternativeResolutionConfig(use_cache=False))

        decision = AlternativeDecision(
            activity_id="ACT-001",
            activity_name="CT, MRI, or PET scan",
            is_alternative=True,
            alternative_type=AlternativeType.MUTUALLY_EXCLUSIVE,
            alternatives=[
                AlternativeOption(name="CT scan", order=1),
                AlternativeOption(name="MRI", order=2),
                AlternativeOption(name="PET scan", order=3),
            ],
            recommended_action=ResolutionAction.EXPAND,
            confidence=0.95,
        )

        original_activity = {"id": "ACT-001", "name": "CT, MRI, or PET scan"}
        sais = [{"id": "SAI-001", "activityId": "ACT-001", "visitId": "ENC-001"}]
        usdm = {"activities": [original_activity], "scheduledActivityInstances": sais}

        expansion = resolver._generate_expansion(original_activity, decision, sais, usdm)

        # 3 activities, 3 SAIs, 3 conditions
        assert len(expansion.expanded_activities) == 3
        assert len(expansion.expanded_sais) == 3
        assert len(expansion.conditions_created) == 3

        # Verify activity names
        names = {a["name"] for a in expansion.expanded_activities}
        assert names == {"CT scan", "MRI", "PET scan"}


# ============================================================================
# Apply Resolutions Tests
# ============================================================================

class TestApplyResolutions:
    """Tests for apply_resolutions_to_usdm method."""

    @pytest.mark.asyncio
    async def test_apply_adds_expanded_entities(self):
        """apply_resolutions_to_usdm adds expanded activities, SAIs, conditions."""
        resolver = AlternativeResolver(AlternativeResolutionConfig(use_cache=False))

        # Create a result with one expansion with PROPER references
        result = Stage4Result()

        from soa_analyzer.models.alternative_expansion import AlternativeExpansion
        exp = AlternativeExpansion(
            id="EXP-ACT-001",
            original_activity_id="ACT-001",
            original_activity_name="CT or MRI",
            expanded_activities=[
                {"id": "ACT-001-A", "name": "CT scan", "instanceType": "Activity"},
                {"id": "ACT-001-B", "name": "MRI", "instanceType": "Activity"},
            ],
            expanded_sais=[
                {
                    "id": "SAI-001-A",
                    "activityId": "ACT-001-A",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "defaultConditionId": "COND-001-A",
                    "_alternativeResolution": {"originalSaiId": "SAI-001"},  # Required for removal
                },
                {
                    "id": "SAI-001-B",
                    "activityId": "ACT-001-B",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "defaultConditionId": "COND-001-B",
                    "_alternativeResolution": {"originalSaiId": "SAI-001"},  # Required for removal
                },
            ],
            conditions_created=[
                {"id": "COND-001-A", "instanceType": "Condition", "name": "CT scan selected"},
                {"id": "COND-001-B", "instanceType": "Condition", "name": "MRI selected"},
            ],
            assignments_created=[
                {"id": "CA-001-A", "instanceType": "ConditionAssignment", "conditionId": "COND-001-A", "conditionTargetId": "SAI-001-A"},
                {"id": "CA-001-B", "instanceType": "ConditionAssignment", "conditionId": "COND-001-B", "conditionTargetId": "SAI-001-B"},
            ],
        )
        result.add_expansion(exp)

        # Original USDM
        usdm = {
            "activities": [{"id": "ACT-001", "name": "CT or MRI"}, {"id": "ACT-002", "name": "Lab test"}],
            "scheduledActivityInstances": [
                {"id": "SAI-001", "activityId": "ACT-001", "scheduledInstanceEncounterId": "ENC-001"},
                {"id": "SAI-002", "activityId": "ACT-002", "scheduledInstanceEncounterId": "ENC-001"},
            ],
            "conditions": [],
            "conditionAssignments": [],
            "encounters": [{"id": "ENC-001", "name": "Screening"}],
        }

        # Apply resolutions
        updated = resolver.apply_resolutions_to_usdm(usdm, result)

        # Original activity removed, expanded added
        activity_ids = {a["id"] for a in updated["activities"]}
        assert "ACT-001" not in activity_ids  # Original removed
        assert "ACT-001-A" in activity_ids  # Expanded A added
        assert "ACT-001-B" in activity_ids  # Expanded B added
        assert "ACT-002" in activity_ids  # Unaffected remains

        # Original SAI removed, expanded added
        sai_ids = {s["id"] for s in updated["scheduledActivityInstances"]}
        assert "SAI-001" not in sai_ids  # Original removed
        assert "SAI-001-A" in sai_ids  # Expanded A added
        assert "SAI-001-B" in sai_ids  # Expanded B added
        assert "SAI-002" in sai_ids  # Unaffected remains

        # Conditions and assignments added
        assert len(updated["conditions"]) == 2
        assert len(updated["conditionAssignments"]) == 2


# ============================================================================
# Filtering Tests
# ============================================================================

class TestPatternFiltering:
    """Tests for timing and unit pattern filtering."""

    def test_timing_patterns_filtered_from_candidates(self):
        """Timing patterns like BI/EOI are filtered from analysis."""
        resolver = AlternativeResolver(AlternativeResolutionConfig(use_cache=False))

        activities = [
            {"id": "ACT-001", "name": "BI/EOI"},  # Timing - filtered
            {"id": "ACT-002", "name": "pre-dose/post-dose"},  # Timing - filtered
            {"id": "ACT-003", "name": "CT or MRI"},  # Should be analyzed
        ]
        result = Stage4Result()
        candidates = resolver._extract_candidate_activities(activities, result)

        assert len(candidates) == 1
        assert candidates[0]["id"] == "ACT-003"
        assert result.timing_patterns_filtered == 2

    def test_unit_patterns_filtered_from_candidates(self):
        """Unit patterns like mg/kg are filtered from analysis."""
        resolver = AlternativeResolver(AlternativeResolutionConfig(use_cache=False))

        activities = [
            {"id": "ACT-001", "name": "5 mg/kg"},  # Unit - filtered
            {"id": "ACT-002", "name": "100 mg/m2"},  # Unit - filtered
            {"id": "ACT-003", "name": "Blood / urine sample"},  # Should be analyzed
        ]
        result = Stage4Result()
        candidates = resolver._extract_candidate_activities(activities, result)

        assert len(candidates) == 1
        assert candidates[0]["id"] == "ACT-003"
        assert result.unit_patterns_filtered == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
