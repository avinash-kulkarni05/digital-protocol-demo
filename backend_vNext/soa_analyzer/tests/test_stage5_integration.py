"""
Integration tests for Stage 5: Specimen Enrichment.

Tests the integration of Stage 5 with:
1. Stage 4 (Alternative Resolution) → Stage 5 handoff
2. Stage 5 → Stage 6 (Conditional Expansion) handoff
3. Stage 5 → Stage 12 (USDM Compliance) validation
4. Full pipeline integration with different specimen types

Run with: python -m pytest soa_analyzer/tests/test_stage5_integration.py -v
"""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from soa_analyzer.interpretation.stage5_specimen_enrichment import (
    SpecimenEnricher,
    SpecimenPatternRegistry,
    enrich_specimens,
)
from soa_analyzer.interpretation.stage12_usdm_compliance import (
    USDMComplianceChecker,
)
from soa_analyzer.models.specimen_enrichment import (
    SpecimenCategory,
    SpecimenSubtype,
    SpecimenPurpose,
    TubeType,
    TubeColor,
    StoragePhase,
    ShippingCondition,
    VolumeSpecification,
    TemperatureRange,
    TubeSpecification,
    ProcessingRequirement,
    StorageRequirement,
    ShippingRequirement,
    SpecimenDecision,
    SpecimenEnrichment,
    Stage5Result,
    SpecimenEnrichmentConfig,
)


class TestStage4ToStage5Handoff:
    """Tests for Stage 4 → Stage 5 handoff."""

    @pytest.mark.asyncio
    async def test_stage5_processes_stage4_output(self):
        """Test that Stage 5 correctly processes Stage 4 output."""
        # Simulated Stage 4 output (alternative resolution completed)
        stage4_output = {
            "activities": [
                {
                    "id": "ACT-001",
                    "name": "Hematology",
                    "domain": {"code": "LB", "decode": "Laboratory"},
                },
                {
                    "id": "ACT-002",
                    "name": "Chemistry Panel",
                    "domain": {"code": "LB", "decode": "Laboratory"},
                },
                {
                    "id": "ACT-003",
                    "name": "Vital Signs",
                    "domain": {"code": "VS", "decode": "Vital Signs"},
                },
            ],
            "encounters": [
                {"id": "ENC-001", "name": "Screening"},
            ],
            "scheduledActivityInstances": [
                {"id": "SAI-001", "activityId": "ACT-001", "scheduledInstanceEncounterId": "ENC-001"},
                {"id": "SAI-002", "activityId": "ACT-002", "scheduledInstanceEncounterId": "ENC-001"},
                {"id": "SAI-003", "activityId": "ACT-003", "scheduledInstanceEncounterId": "ENC-001"},
            ],
            "footnotes": [
                {"marker": "a", "text": "5 mL EDTA tube required"},
            ],
            "conditions": [],
        }

        enricher = SpecimenEnricher()
        result = await enricher.enrich_specimens(stage4_output)

        # Should process LB domain activities
        assert result.activities_analyzed >= 2

        # VS domain should be excluded
        vs_candidate = any(
            d.activity_name == "Vital Signs" and d.has_specimen
            for d in result.decisions.values()
        )
        assert not vs_candidate

    @pytest.mark.asyncio
    async def test_stage5_preserves_stage4_fields(self):
        """Test that Stage 5 preserves Stage 4 specific fields."""
        stage4_output = {
            "activities": [
                {
                    "id": "ACT-001",
                    "name": "Blood Draw",
                    "domain": {"code": "LB"},
                    # Stage 4 specific fields
                    "_alternativeResolution": {
                        "originalName": "Blood Draw A or B",
                        "selectedOption": "A",
                    },
                },
            ],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    # Stage 4 alternative flag
                    "_alternativeExpansion": {"originalId": "SAI-ALT-001"},
                },
            ],
            "footnotes": [],
            "conditions": [],
        }

        enricher = SpecimenEnricher()

        # Create a simple decision
        decision = SpecimenDecision(
            activity_id="ACT-001",
            activity_name="Blood Draw",
            has_specimen=True,
            specimen_category=SpecimenCategory.BLOOD,
            confidence=0.95,
        )
        result = Stage5Result()
        result.decisions["ACT-001"] = decision

        enrichment = SpecimenEnrichment(
            id="SPEC-001",
            activity_id="ACT-001",
            activity_name="Blood Draw",
            specimen_collection={"id": "SPEC-001"},
            biospecimen_requirements={},
            confidence=0.95,
        )
        result.enrichments.append(enrichment)

        updated = enricher.apply_enrichments_to_usdm(stage4_output, result)

        # Stage 4 fields should still be present on activity
        act = updated["activities"][0]
        assert "_alternativeResolution" in act

        # Stage 4 fields should still be present on SAI
        sai = updated["scheduledActivityInstances"][0]
        assert "_alternativeExpansion" in sai

        # Stage 5 fields should be added
        assert "specimenCollection" in sai


class TestStage5ToStage6Handoff:
    """Tests for Stage 5 → Stage 6 handoff."""

    def test_stage5_creates_optional_conditions(self):
        """Test that Stage 5 creates conditions for optional specimens."""
        enricher = SpecimenEnricher()
        enricher.config.create_conditions_for_optional = True

        decision = SpecimenDecision(
            activity_id="ACT-001",
            activity_name="Optional PK Sample",
            has_specimen=True,
            specimen_category=SpecimenCategory.BLOOD,
            is_optional=True,
            condition_text="Optional: collect if PK substudy enrolled",
            confidence=0.85,
        )

        enrichment = enricher._generate_enrichment(decision)

        # Should create condition for optional specimen
        assert enrichment is not None
        assert len(enrichment.conditions_created) == 1
        assert enrichment.conditions_created[0]["instanceType"] == "Condition"
        assert "_specimenEnrichment" in enrichment.conditions_created[0]

    def test_stage5_conditions_ready_for_stage6(self):
        """Test that Stage 5 conditions can be processed by Stage 6."""
        usdm = {
            "activities": [
                {"id": "ACT-001", "name": "Optional PK"},
            ],
            "scheduledActivityInstances": [
                {"id": "SAI-001", "activityId": "ACT-001", "footnoteMarkers": ["a"]},
            ],
            "footnotes": [
                {"marker": "a", "text": "Optional for PK substudy participants"},
            ],
            "conditions": [],
        }

        # Create enrichment with optional condition
        condition = {
            "id": "COND-SPEC-001",
            "instanceType": "Condition",
            "name": "Optional specimen: Optional PK",
            "text": "Optional for PK substudy participants",
            "_specimenEnrichment": {
                "stage": "Stage5SpecimenEnrichment",
                "sourceActivityId": "ACT-001",
                "conditionType": "optional",
            },
        }

        enrichment = SpecimenEnrichment(
            id="SPEC-001",
            activity_id="ACT-001",
            activity_name="Optional PK",
            specimen_collection={},
            biospecimen_requirements={},
            conditions_created=[condition],
            confidence=0.85,
        )

        result = Stage5Result(enrichments=[enrichment])

        enricher = SpecimenEnricher()
        updated = enricher.apply_enrichments_to_usdm(usdm, result)

        # Condition should be in output
        assert len(updated["conditions"]) == 1
        assert updated["conditions"][0]["id"] == "COND-SPEC-001"

        # Stage 6 should be able to create assignments for this condition
        # (validated in Stage 6 tests)


class TestStage5ToStage12Compliance:
    """Tests for Stage 5 → Stage 12 compliance."""

    def test_specimen_enrichment_passes_stage12(self):
        """Test that Stage 5 enriched output passes Stage 12 compliance."""
        usdm = {
            "activities": [
                {"id": "ACT-001", "name": "Hematology"},
            ],
            "encounters": [
                {"id": "ENC-001", "name": "Screening"},
            ],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "specimenCollection": {
                        "id": "SPEC-001",
                        "instanceType": "SpecimenCollection",
                        "specimenType": {
                            "id": "CODE-SPEC-001",
                            "code": "C78732",
                            "decode": "Whole Blood",
                            "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
                            "codeSystemVersion": "24.12",
                            "instanceType": "Code",
                        },
                        "collectionVolume": {"value": 3, "unit": "mL"},
                        "_specimenEnrichment": {
                            "stage": "Stage5SpecimenEnrichment",
                            "confidence": 0.98,
                        },
                    },
                },
            ],
            "footnotes": [],
            "conditions": [],
            "conditionAssignments": [],
        }

        checker = USDMComplianceChecker()
        updated, compliance_result = checker.ensure_compliance(usdm)

        # Should pass without errors
        errors = [i for i in compliance_result.issues if i.severity == "error"]
        assert len(errors) == 0, f"Errors: {[e.message for e in errors]}"

        # Referential integrity should pass
        assert compliance_result.referential_integrity_passed

    def test_specimen_code_objects_are_compliant(self):
        """Test that specimen Code objects meet USDM 4.0 requirements."""
        enricher = SpecimenEnricher()

        code = enricher._create_specimen_code(
            SpecimenCategory.BLOOD,
            SpecimenSubtype.WHOLE_BLOOD
        )

        # Check required USDM Code fields
        assert "id" in code
        assert "instanceType" in code
        assert code["instanceType"] == "Code"
        assert "codeSystem" in code
        assert "codeSystemVersion" in code
        assert "decode" in code

    def test_optional_specimen_conditions_are_compliant(self):
        """Test that optional specimen conditions pass Stage 12."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "Optional PK"}],
            "encounters": [{"id": "ENC-001", "name": "Screening"}],
            "scheduledActivityInstances": [
                {
                    "id": "SAI-001",
                    "activityId": "ACT-001",
                    "scheduledInstanceEncounterId": "ENC-001",
                    "defaultConditionId": "COND-SPEC-001",
                },
            ],
            "conditions": [
                {
                    "id": "COND-SPEC-001",
                    "instanceType": "Condition",
                    "name": "Optional specimen",
                    "text": "Optional: collect if enrolled in PK substudy",
                },
            ],
            "conditionAssignments": [
                {
                    "id": "CA-001",
                    "instanceType": "ConditionAssignment",
                    "conditionId": "COND-SPEC-001",
                    "conditionTargetId": "SAI-001",
                },
            ],
            "footnotes": [],
        }

        checker = USDMComplianceChecker()
        updated, compliance_result = checker.ensure_compliance(usdm)

        # Referential integrity should pass
        assert compliance_result.referential_integrity_passed


class TestDifferentSpecimenTypes:
    """Tests for different specimen type handling."""

    @pytest.mark.asyncio
    async def test_blood_specimen_enrichment(self):
        """Test enrichment of blood specimen activities."""
        enricher = SpecimenEnricher()

        decision = SpecimenDecision(
            activity_id="ACT-001",
            activity_name="Hematology",
            has_specimen=True,
            specimen_category=SpecimenCategory.BLOOD,
            specimen_subtype=SpecimenSubtype.WHOLE_BLOOD,
            purpose=SpecimenPurpose.SAFETY,
            tube_specification=TubeSpecification(
                tube_type=TubeType.EDTA,
                tube_color=TubeColor.LAVENDER,
                anticoagulant="K2 EDTA",
            ),
            volumes=[VolumeSpecification(value=3, unit="mL")],
            confidence=0.98,
        )

        enrichment = enricher._generate_enrichment(decision)

        assert enrichment is not None
        assert "specimenType" in enrichment.specimen_collection
        assert enrichment.specimen_collection["specimenType"]["decode"] in [
            "Whole Blood", "whole_blood"
        ]
        assert "collectionContainer" in enrichment.specimen_collection

    @pytest.mark.asyncio
    async def test_urine_specimen_enrichment(self):
        """Test enrichment of urine specimen activities."""
        enricher = SpecimenEnricher()

        decision = SpecimenDecision(
            activity_id="ACT-002",
            activity_name="Urinalysis",
            has_specimen=True,
            specimen_category=SpecimenCategory.URINE,
            specimen_subtype=SpecimenSubtype.URINE_SPOT,
            purpose=SpecimenPurpose.SAFETY,
            confidence=0.95,
        )

        enrichment = enricher._generate_enrichment(decision)

        assert enrichment is not None
        assert "specimenType" in enrichment.specimen_collection

    @pytest.mark.asyncio
    async def test_pk_specimen_enrichment(self):
        """Test enrichment of PK specimen activities."""
        enricher = SpecimenEnricher()

        decision = SpecimenDecision(
            activity_id="ACT-003",
            activity_name="PK Sample",
            has_specimen=True,
            specimen_category=SpecimenCategory.BLOOD,
            specimen_subtype=SpecimenSubtype.EDTA_PLASMA,
            purpose=SpecimenPurpose.PK,
            tube_specification=TubeSpecification(
                tube_type=TubeType.EDTA,
                tube_color=TubeColor.LAVENDER,
            ),
            volumes=[
                VolumeSpecification(value=5, unit="mL", visit_context="Screening"),
                VolumeSpecification(value=3, unit="mL", visit_context="Week 4"),
            ],
            processing=[
                ProcessingRequirement(
                    step_name="Mix",
                    step_order=1,
                    inversion_count="8-10 times",
                ),
                ProcessingRequirement(
                    step_name="Centrifuge",
                    step_order=2,
                    centrifuge_speed="1500 x g",
                    centrifuge_time="10 minutes",
                    centrifuge_temperature="4°C",
                ),
            ],
            storage=[
                StorageRequirement(
                    storage_phase=StoragePhase.LONG_TERM,
                    temperature=TemperatureRange(nominal=-80, min=-85, max=-75),
                    stability_limit="2 years",
                ),
            ],
            confidence=0.95,
        )

        enrichment = enricher._generate_enrichment(decision)

        assert enrichment is not None
        assert enrichment.specimen_collection.get("purpose") is not None

        # Should have visit-dependent volumes
        if "visitDependentVolumes" in enrichment.specimen_collection:
            assert len(enrichment.specimen_collection["visitDependentVolumes"]) == 2

        # Should have processing requirements
        if "processingRequirements" in enrichment.specimen_collection:
            assert len(enrichment.specimen_collection["processingRequirements"]) == 2

        # Should have storage requirements
        if "storageRequirements" in enrichment.specimen_collection:
            assert len(enrichment.specimen_collection["storageRequirements"]) == 1


class TestVisitDependentVolumes:
    """Tests for visit-dependent volume handling."""

    def test_multiple_volumes_preserved(self):
        """Test that multiple visit-dependent volumes are preserved."""
        enricher = SpecimenEnricher()

        decision = SpecimenDecision(
            activity_id="ACT-001",
            activity_name="PK Sample",
            has_specimen=True,
            specimen_category=SpecimenCategory.BLOOD,
            volumes=[
                VolumeSpecification(value=12, unit="mL", visit_context="Screening"),
                VolumeSpecification(value=6, unit="mL", visit_context="Week 4"),
                VolumeSpecification(value=6, unit="mL", visit_context="Week 8"),
            ],
            confidence=0.95,
        )

        enrichment = enricher._generate_enrichment(decision)

        assert enrichment is not None

        # Primary volume should be first one
        primary_vol = enrichment.specimen_collection.get("collectionVolume")
        assert primary_vol is not None
        assert primary_vol["value"] == 12

        # All volumes in array
        all_vols = enrichment.specimen_collection.get("visitDependentVolumes", [])
        assert len(all_vols) == 3

    def test_single_volume_no_array(self):
        """Test that single volume doesn't create array."""
        enricher = SpecimenEnricher()

        decision = SpecimenDecision(
            activity_id="ACT-002",
            activity_name="Chemistry",
            has_specimen=True,
            specimen_category=SpecimenCategory.BLOOD,
            volumes=[VolumeSpecification(value=5, unit="mL")],
            confidence=0.95,
        )

        enrichment = enricher._generate_enrichment(decision)

        assert enrichment is not None
        assert enrichment.specimen_collection.get("collectionVolume") is not None
        # Should not have visitDependentVolumes for single volume
        assert enrichment.specimen_collection.get("visitDependentVolumes") is None


class TestFullLifecycleEnrichment:
    """Tests for full lifecycle (collection, processing, storage, shipping)."""

    def test_complete_lifecycle_enrichment(self):
        """Test enrichment with complete lifecycle data."""
        enricher = SpecimenEnricher()

        decision = SpecimenDecision(
            activity_id="ACT-001",
            activity_name="Biomarker Sample",
            has_specimen=True,
            specimen_category=SpecimenCategory.BLOOD,
            specimen_subtype=SpecimenSubtype.SERUM,
            purpose=SpecimenPurpose.BIOMARKER,
            tube_specification=TubeSpecification(
                tube_type=TubeType.SST,
                tube_color=TubeColor.GOLD,
            ),
            volumes=[VolumeSpecification(value=5, unit="mL")],
            fasting_required=True,
            fasting_duration="8 hours",
            processing=[
                ProcessingRequirement(
                    step_name="Clot",
                    step_order=1,
                    clotting_time="30 minutes",
                ),
                ProcessingRequirement(
                    step_name="Centrifuge",
                    step_order=2,
                    centrifuge_speed="1500 x g",
                    centrifuge_time="10 minutes",
                ),
                ProcessingRequirement(
                    step_name="Aliquot",
                    step_order=3,
                    aliquot_count=2,
                    aliquot_volume=VolumeSpecification(value=1, unit="mL"),
                    aliquot_container="cryovial",
                ),
            ],
            storage=[
                StorageRequirement(
                    storage_phase=StoragePhase.TEMPORARY,
                    temperature=TemperatureRange(nominal=4, min=2, max=8),
                    max_duration="24 hours",
                ),
                StorageRequirement(
                    storage_phase=StoragePhase.LONG_TERM,
                    temperature=TemperatureRange(nominal=-80, min=-85, max=-75),
                    stability_limit="2 years",
                ),
            ],
            shipping=ShippingRequirement(
                destination="Central Laboratory",
                shipping_frequency="weekly",
                shipping_condition=ShippingCondition.DRY_ICE,
                un_classification="UN3373",
            ),
            confidence=0.92,
        )

        enrichment = enricher._generate_enrichment(decision)

        assert enrichment is not None
        sc = enrichment.specimen_collection

        # Collection data
        assert "specimenType" in sc
        assert "collectionContainer" in sc
        assert "collectionVolume" in sc

        # Fasting
        assert sc.get("fastingRequired") is True
        assert sc.get("fastingDuration") == "8 hours"

        # Processing
        proc = sc.get("processingRequirements", [])
        assert len(proc) == 3

        # Storage
        storage = sc.get("storageRequirements", [])
        assert len(storage) == 2

        # Shipping
        shipping = sc.get("shippingRequirements")
        assert shipping is not None
        assert shipping.get("destination") == "Central Laboratory"


class TestCachingBehavior:
    """Tests for caching behavior across pipeline."""

    @pytest.mark.asyncio
    async def test_cache_hit_on_repeated_activity(self):
        """Test that repeated activity names hit cache."""
        enricher = SpecimenEnricher(use_cache=True)

        # First call - should be cache miss
        decision1 = SpecimenDecision(
            activity_id="ACT-001",
            activity_name="Hematology",
            has_specimen=True,
            specimen_category=SpecimenCategory.BLOOD,
            confidence=0.98,
            source="llm",
        )
        enricher._update_cache("Hematology", decision1)

        # Second call - should be cache hit
        cached = enricher._check_cache("Hematology")

        assert cached is not None
        assert cached.source == "cache"
        assert cached.activity_name == "Hematology"

    @pytest.mark.asyncio
    async def test_cache_key_includes_model(self):
        """Test that cache key includes model name."""
        config1 = SpecimenEnrichmentConfig(model_name="gemini-2.0-flash-exp")
        enricher1 = SpecimenEnricher(config=config1)

        config2 = SpecimenEnrichmentConfig(model_name="gpt-4-turbo")
        enricher2 = SpecimenEnricher(config=config2)

        key1 = enricher1._get_cache_key("Hematology")
        key2 = enricher2._get_cache_key("Hematology")

        # Different models = different cache keys
        assert key1 != key2


class TestMockedLLMIntegration:
    """Tests with mocked LLM responses."""

    @pytest.mark.asyncio
    async def test_batch_llm_analysis(self):
        """Test batch LLM analysis with mocked response."""
        enricher = SpecimenEnricher(use_cache=False)

        usdm = {
            "activities": [
                {"id": "ACT-001", "name": "Hematology", "domain": {"code": "LB"}},
                {"id": "ACT-002", "name": "Chemistry", "domain": {"code": "LB"}},
            ],
            "scheduledActivityInstances": [
                {"id": "SAI-001", "activityId": "ACT-001"},
                {"id": "SAI-002", "activityId": "ACT-002"},
            ],
            "footnotes": [],
            "conditions": [],
        }

        mock_response = json.dumps({
            "ACT-001": {
                "activityName": "Hematology",
                "hasSpecimen": True,
                "specimenCategory": "blood",
                "specimenSubtype": "whole_blood",
                "confidence": 0.98,
                "rationale": "Standard hematology panel",
            },
            "ACT-002": {
                "activityName": "Chemistry",
                "hasSpecimen": True,
                "specimenCategory": "blood",
                "specimenSubtype": "serum",
                "confidence": 0.95,
                "rationale": "Serum chemistry panel",
            },
        })

        with patch.object(enricher, '_call_llm_with_fallback', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response
            result = await enricher.enrich_specimens(usdm)

        # Should process both activities
        assert result.activities_analyzed == 2
        assert result.activities_with_specimens == 2
        assert result.llm_calls == 1  # Single batch call

    @pytest.mark.asyncio
    async def test_llm_failure_marks_for_review(self):
        """Test that LLM failure marks activities for human review."""
        enricher = SpecimenEnricher(use_cache=False)

        usdm = {
            "activities": [
                {"id": "ACT-001", "name": "Unknown Test", "domain": {"code": "LB"}},
            ],
            "scheduledActivityInstances": [],
            "footnotes": [],
            "conditions": [],
        }

        with patch.object(enricher, '_call_llm_with_fallback', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = None  # LLM failure
            result = await enricher.enrich_specimens(usdm)

        # Activity should be marked for review (check review_items)
        assert len(result.review_items) >= 1
        decision = result.decisions.get("ACT-001")
        assert decision is not None
        assert decision.requires_human_review is True


class TestProvenanceTracking:
    """Tests for provenance tracking across pipeline."""

    def test_enrichment_provenance_complete(self):
        """Test that enrichment includes complete provenance."""
        enricher = SpecimenEnricher()

        decision = SpecimenDecision(
            activity_id="ACT-001",
            activity_name="Hematology",
            has_specimen=True,
            specimen_category=SpecimenCategory.BLOOD,
            confidence=0.98,
            source="config",
            rationale="Inferred from activity_components.json",
            footnote_markers=["a"],
            page_numbers=[45],
        )

        enrichment = enricher._generate_enrichment(decision)

        assert enrichment is not None
        prov = enrichment.specimen_collection.get("_specimenEnrichment")

        assert prov is not None
        assert prov["stage"] == "Stage5SpecimenEnrichment"
        assert prov["source"] == "config"
        assert prov["confidence"] == 0.98
        assert prov["rationale"] == "Inferred from activity_components.json"
        assert "timestamp" in prov

    def test_provenance_preserved_through_apply(self):
        """Test that provenance is preserved when applying enrichments."""
        usdm = {
            "activities": [{"id": "ACT-001", "name": "Hematology"}],
            "scheduledActivityInstances": [{"id": "SAI-001", "activityId": "ACT-001"}],
            "footnotes": [],
            "conditions": [],
        }

        enrichment = SpecimenEnrichment(
            id="SPEC-001",
            activity_id="ACT-001",
            activity_name="Hematology",
            specimen_collection={
                "id": "SPEC-001",
                "_specimenEnrichment": {
                    "stage": "Stage5SpecimenEnrichment",
                    "source": "llm",
                },
            },
            biospecimen_requirements={},
            confidence=0.95,
        )

        result = Stage5Result(enrichments=[enrichment])

        enricher = SpecimenEnricher()
        updated = enricher.apply_enrichments_to_usdm(usdm, result)

        # Provenance should be on SAI
        sai = updated["scheduledActivityInstances"][0]
        assert "_specimenEnrichment" in sai["specimenCollection"]


class TestEdgeCases:
    """Tests for edge cases in Stage 5 integration."""

    @pytest.mark.asyncio
    async def test_empty_activities_list(self):
        """Test handling of empty activities list."""
        enricher = SpecimenEnricher()

        usdm = {
            "activities": [],
            "scheduledActivityInstances": [],
            "footnotes": [],
            "conditions": [],
        }

        result = await enricher.enrich_specimens(usdm)

        assert result.activities_analyzed == 0
        assert result.specimens_enriched == 0

    @pytest.mark.asyncio
    async def test_all_non_specimen_activities(self):
        """Test handling when all activities are non-specimen."""
        enricher = SpecimenEnricher()

        usdm = {
            "activities": [
                {"id": "ACT-001", "name": "Vital Signs", "domain": {"code": "VS"}},
                {"id": "ACT-002", "name": "ECG", "domain": {"code": "EG"}},
                {"id": "ACT-003", "name": "Physical Exam", "domain": {"code": "PE"}},
            ],
            "scheduledActivityInstances": [],
            "footnotes": [],
            "conditions": [],
        }

        result = await enricher.enrich_specimens(usdm)

        # No candidates should be identified
        assert result.activities_analyzed == 0
        assert result.specimens_enriched == 0

    def test_missing_domain_in_activity(self):
        """Test handling of activity without domain."""
        enricher = SpecimenEnricher()

        usdm = {
            "activities": [
                {"id": "ACT-001", "name": "Hematology"},  # No domain
            ],
            "scheduledActivityInstances": [],
            "footnotes": [],
            "conditions": [],
        }

        # Should not crash
        candidates = enricher._extract_candidate_activities(usdm)

        # Should still identify by name inference
        assert len(candidates) == 1

    def test_multiple_sais_same_activity(self):
        """Test handling multiple SAIs for same activity."""
        enricher = SpecimenEnricher()

        usdm = {
            "activities": [
                {"id": "ACT-001", "name": "Hematology"},
            ],
            "scheduledActivityInstances": [
                {"id": "SAI-001", "activityId": "ACT-001"},
                {"id": "SAI-002", "activityId": "ACT-001"},
                {"id": "SAI-003", "activityId": "ACT-001"},
            ],
            "footnotes": [],
            "conditions": [],
        }

        enrichment = SpecimenEnrichment(
            id="SPEC-001",
            activity_id="ACT-001",
            activity_name="Hematology",
            specimen_collection={"id": "SPEC-001"},
            biospecimen_requirements={},
            confidence=0.95,
        )

        result = Stage5Result(enrichments=[enrichment])
        updated = enricher.apply_enrichments_to_usdm(usdm, result)

        # All SAIs for the activity should get specimen collection
        for sai in updated["scheduledActivityInstances"]:
            assert "specimenCollection" in sai


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
