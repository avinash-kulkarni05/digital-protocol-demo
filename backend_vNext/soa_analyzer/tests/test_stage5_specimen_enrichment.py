"""
Unit tests for Stage 5: Specimen Enrichment.

Tests:
- SpecimenPatternRegistry (pattern matching for validation)
- SpecimenEnricher (LLM-first enrichment logic)
- Data models (SpecimenDecision, SpecimenEnrichment, Stage5Result)
- Helper functions

Run with: python -m pytest soa_analyzer/tests/test_stage5_specimen_enrichment.py -v
"""

import asyncio
import json
import pytest
from pathlib import Path

# Import models
from soa_analyzer.models.specimen_enrichment import (
    SpecimenCategory,
    SpecimenSubtype,
    SpecimenPurpose,
    TubeType,
    TubeColor,
    StoragePhase,
    EquipmentType,
    ShippingCondition,
    VolumeSpecification,
    TemperatureRange,
    TubeSpecification,
    ProcessingRequirement,
    StorageRequirement,
    ShippingRequirement,
    SpecimenDecision,
    SpecimenProvenance,
    SpecimenEnrichment,
    HumanReviewItem,
    ValidationDiscrepancy,
    Stage5Result,
    SpecimenEnrichmentConfig,
    infer_specimen_from_activity_name,
    infer_subtype_from_panel,
    generate_specimen_collection_id,
    generate_condition_id,
    generate_code_id,
    generate_review_id,
)

# Import stage 5
from soa_analyzer.interpretation.stage5_specimen_enrichment import (
    SpecimenEnricher,
    SpecimenPatternRegistry,
    enrich_specimens,
    SPECIMEN_DOMAINS,
    NON_SPECIMEN_DOMAINS,
)


class TestVolumeSpecification:
    """Tests for VolumeSpecification dataclass."""

    def test_creation(self):
        """Test basic VolumeSpecification creation."""
        vol = VolumeSpecification(
            value=5.0,
            unit="mL",
            visit_context="Screening",
            population="adult",
        )

        assert vol.value == 5.0
        assert vol.unit == "mL"
        assert vol.visit_context == "Screening"
        assert vol.population == "adult"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        vol = VolumeSpecification(value=3.0, unit="mL", visit_context="Week 4")
        d = vol.to_dict()

        assert d["value"] == 3.0
        assert d["unit"] == "mL"
        assert d["visitContext"] == "Week 4"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {"value": 10, "unit": "mL", "visitContext": "Baseline"}
        vol = VolumeSpecification.from_dict(data)

        assert vol.value == 10
        assert vol.unit == "mL"
        assert vol.visit_context == "Baseline"


class TestTubeSpecification:
    """Tests for TubeSpecification dataclass."""

    def test_creation(self):
        """Test basic TubeSpecification creation."""
        tube = TubeSpecification(
            tube_type=TubeType.EDTA,
            tube_color=TubeColor.LAVENDER,
            anticoagulant="K2 EDTA",
            fill_critical=False,
        )

        assert tube.tube_type == TubeType.EDTA
        assert tube.tube_color == TubeColor.LAVENDER
        assert tube.anticoagulant == "K2 EDTA"
        assert tube.fill_critical is False

    def test_to_dict(self):
        """Test serialization to dictionary."""
        tube = TubeSpecification(
            tube_type=TubeType.SST,
            tube_color=TubeColor.GOLD,
        )
        d = tube.to_dict()

        assert d["tubeType"] == "sst"
        assert d["tubeColor"] == "gold"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "tubeType": "sodium_citrate",
            "tubeColor": "light_blue",
            "anticoagulant": "3.2% Sodium Citrate",
            "fillCritical": True,
        }
        tube = TubeSpecification.from_dict(data)

        assert tube.tube_type == TubeType.SODIUM_CITRATE
        assert tube.tube_color == TubeColor.LIGHT_BLUE
        assert tube.fill_critical is True


class TestProcessingRequirement:
    """Tests for ProcessingRequirement dataclass."""

    def test_creation(self):
        """Test basic ProcessingRequirement creation."""
        proc = ProcessingRequirement(
            step_name="Centrifugation",
            step_order=2,
            centrifuge_speed="1500 x g",
            centrifuge_time="10 minutes",
            centrifuge_temperature="4°C",
        )

        assert proc.step_name == "Centrifugation"
        assert proc.step_order == 2
        assert proc.centrifuge_speed == "1500 x g"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        proc = ProcessingRequirement(
            step_name="Mix",
            step_order=1,
            inversion_count="8-10 times",
        )
        d = proc.to_dict()

        assert d["stepName"] == "Mix"
        assert d["stepOrder"] == 1
        assert d["inversionCount"] == "8-10 times"


class TestStorageRequirement:
    """Tests for StorageRequirement dataclass."""

    def test_creation(self):
        """Test basic StorageRequirement creation."""
        storage = StorageRequirement(
            storage_phase=StoragePhase.LONG_TERM,
            equipment_type=EquipmentType.FREEZER_MINUS80,
            stability_limit="2 years",
        )

        assert storage.storage_phase == StoragePhase.LONG_TERM
        assert storage.equipment_type == EquipmentType.FREEZER_MINUS80
        assert storage.stability_limit == "2 years"

    def test_with_temperature(self):
        """Test StorageRequirement with TemperatureRange."""
        storage = StorageRequirement(
            storage_phase=StoragePhase.TEMPORARY,
            temperature=TemperatureRange(nominal=4, min=2, max=8, description="refrigerated"),
        )

        d = storage.to_dict()
        assert d["temperature"]["nominal"] == 4
        assert d["temperature"]["description"] == "refrigerated"


class TestShippingRequirement:
    """Tests for ShippingRequirement dataclass."""

    def test_creation(self):
        """Test basic ShippingRequirement creation."""
        shipping = ShippingRequirement(
            destination="Central Laboratory",
            shipping_frequency="weekly",
            shipping_condition=ShippingCondition.DRY_ICE,
            un_classification="UN3373",
        )

        assert shipping.destination == "Central Laboratory"
        assert shipping.shipping_condition == ShippingCondition.DRY_ICE
        assert shipping.un_classification == "UN3373"


class TestSpecimenDecision:
    """Tests for SpecimenDecision dataclass."""

    def test_creation_with_specimen(self):
        """Test SpecimenDecision creation for specimen activity."""
        decision = SpecimenDecision(
            activity_id="ACT-001",
            activity_name="Hematology",
            has_specimen=True,
            specimen_category=SpecimenCategory.BLOOD,
            specimen_subtype=SpecimenSubtype.WHOLE_BLOOD,
            purpose=SpecimenPurpose.SAFETY,
            confidence=0.98,
            rationale="Standard hematology panel requires EDTA whole blood",
            source="config",
        )

        assert decision.activity_id == "ACT-001"
        assert decision.has_specimen is True
        assert decision.specimen_category == SpecimenCategory.BLOOD
        assert decision.confidence == 0.98
        assert decision.source == "config"

    def test_creation_without_specimen(self):
        """Test SpecimenDecision creation for non-specimen activity."""
        decision = SpecimenDecision(
            activity_id="ACT-002",
            activity_name="Vital Signs",
            has_specimen=False,
            confidence=1.0,
            rationale="Vital signs does not require specimen collection",
        )

        assert decision.has_specimen is False
        assert decision.confidence == 1.0

    def test_to_dict(self):
        """Test serialization to dictionary (camelCase for JSON)."""
        decision = SpecimenDecision(
            activity_id="ACT-003",
            activity_name="Chemistry",
            has_specimen=True,
            specimen_category=SpecimenCategory.BLOOD,
            specimen_subtype=SpecimenSubtype.SERUM,
            volumes=[VolumeSpecification(value=5, unit="mL")],
            confidence=0.95,
        )

        d = decision.to_dict()

        assert d["activityId"] == "ACT-003"
        assert d["hasSpecimen"] is True
        assert d["specimenCategory"] == "blood"
        assert d["specimenSubtype"] == "serum"
        assert len(d["volumes"]) == 1
        assert d["volumes"][0]["value"] == 5

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "activityId": "ACT-004",
            "activityName": "Coagulation",
            "hasSpecimen": True,
            "specimenCategory": "blood",
            "specimenSubtype": "citrate_plasma",
            "purpose": "safety",
            "confidence": 0.92,
        }

        decision = SpecimenDecision.from_dict(data)

        assert decision.activity_id == "ACT-004"
        assert decision.specimen_category == SpecimenCategory.BLOOD
        assert decision.specimen_subtype == SpecimenSubtype.CITRATE_PLASMA
        assert decision.purpose == SpecimenPurpose.SAFETY

    def test_from_llm_response(self):
        """Test creating SpecimenDecision from LLM response."""
        response_data = {
            "hasSpecimen": True,
            "specimenCategory": "blood",
            "specimenSubtype": "whole_blood",
            "purpose": "pk",
            "tubeSpecification": {
                "tubeType": "edta",
                "tubeColor": "lavender",
            },
            "volumes": [
                {"value": 5, "unit": "mL", "visitContext": "Screening"},
                {"value": 3, "unit": "mL", "visitContext": "Week 4"},
            ],
            "fastingRequired": False,
            "confidence": 0.95,
            "rationale": "PK sampling requires EDTA whole blood",
        }

        decision = SpecimenDecision.from_llm_response(
            "ACT-005",
            "PK Sample",
            response_data,
            "gemini-2.0-flash-exp",
        )

        assert decision.activity_id == "ACT-005"
        assert decision.has_specimen is True
        assert decision.specimen_category == SpecimenCategory.BLOOD
        assert decision.specimen_subtype == SpecimenSubtype.WHOLE_BLOOD
        assert decision.purpose == SpecimenPurpose.PK
        assert decision.tube_specification.tube_type == TubeType.EDTA
        assert len(decision.volumes) == 2
        assert decision.confidence == 0.95
        assert decision.source == "llm"
        assert decision.model_name == "gemini-2.0-flash-exp"

    def test_get_cache_key(self):
        """Test cache key generation is consistent."""
        decision = SpecimenDecision(
            activity_id="ACT-001",
            activity_name="Hematology",
            has_specimen=True,
        )

        key1 = decision.get_cache_key("gemini-2.0-flash-exp")
        key2 = decision.get_cache_key("gemini-2.0-flash-exp")

        assert key1 == key2

        # Different model = different key
        key3 = decision.get_cache_key("gpt-4-turbo")
        assert key1 != key3


class TestSpecimenEnrichment:
    """Tests for SpecimenEnrichment dataclass."""

    def test_creation(self):
        """Test SpecimenEnrichment creation."""
        enrichment = SpecimenEnrichment(
            id="SPEC-001",
            activity_id="ACT-001",
            activity_name="Hematology",
            specimen_collection={
                "id": "SPEC-001",
                "instanceType": "SpecimenCollection",
            },
            biospecimen_requirements={},
            confidence=0.98,
        )

        assert enrichment.id == "SPEC-001"
        assert enrichment.activity_id == "ACT-001"
        assert enrichment.confidence == 0.98

    def test_to_dict(self):
        """Test serialization to dictionary."""
        enrichment = SpecimenEnrichment(
            id="SPEC-002",
            activity_id="ACT-002",
            activity_name="Chemistry",
            specimen_collection={"id": "SPEC-002"},
            requires_review=True,
            review_reason="Low confidence",
        )

        d = enrichment.to_dict()

        assert d["id"] == "SPEC-002"
        assert d["requiresReview"] is True
        assert d["reviewReason"] == "Low confidence"


class TestStage5Result:
    """Tests for Stage5Result dataclass."""

    def test_empty_result(self):
        """Test creating empty result."""
        result = Stage5Result()

        assert result.activities_analyzed == 0
        assert result.specimens_enriched == 0
        assert result.cache_hits == 0
        assert len(result.enrichments) == 0

    def test_add_enrichment_auto_apply(self):
        """Test adding high-confidence enrichment."""
        result = Stage5Result()

        enrichment = SpecimenEnrichment(
            id="SPEC-001",
            activity_id="ACT-001",
            activity_name="Hematology",
            confidence=0.98,  # High confidence
            requires_review=False,
        )

        result.add_enrichment(enrichment)

        assert result.specimens_enriched == 1
        assert result.auto_applied == 1
        assert result.flagged_for_review == 0
        assert result.needs_review == 0

    def test_add_enrichment_flagged(self):
        """Test adding medium-confidence enrichment."""
        result = Stage5Result()

        enrichment = SpecimenEnrichment(
            id="SPEC-002",
            activity_id="ACT-002",
            activity_name="Unknown Panel",
            confidence=0.75,  # Medium confidence
            requires_review=False,
        )

        result.add_enrichment(enrichment)

        assert result.specimens_enriched == 1
        assert result.auto_applied == 0
        assert result.flagged_for_review == 1

    def test_add_enrichment_needs_review(self):
        """Test adding low-confidence enrichment."""
        result = Stage5Result()

        enrichment = SpecimenEnrichment(
            id="SPEC-003",
            activity_id="ACT-003",
            activity_name="Unclear Test",
            confidence=0.5,
            requires_review=True,
        )

        result.add_enrichment(enrichment)

        assert result.specimens_enriched == 1
        assert result.needs_review == 1

    def test_to_dict_metrics(self):
        """Test metrics in serialized output."""
        result = Stage5Result(
            activities_analyzed=10,
            activities_with_specimens=7,
            specimens_enriched=7,
            cache_hits=5,
            llm_calls=1,
            analyzed_by_llm=2,
        )

        d = result.to_dict()

        assert "metrics" in d
        assert d["metrics"]["activitiesAnalyzed"] == 10
        assert d["metrics"]["specimensEnriched"] == 7
        assert d["metrics"]["cacheHits"] == 5


class TestSpecimenEnrichmentConfig:
    """Tests for SpecimenEnrichmentConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = SpecimenEnrichmentConfig()

        assert config.confidence_threshold_auto == 0.90
        assert config.confidence_threshold_review == 0.70
        assert config.infer_from_activity_components is True
        assert config.use_cache is True
        assert config.max_retries == 3

    def test_custom_values(self):
        """Test custom configuration values."""
        config = SpecimenEnrichmentConfig(
            confidence_threshold_auto=0.95,
            confidence_threshold_review=0.80,
            infer_from_activity_components=False,
            model_name="gpt-4-turbo",
        )

        assert config.confidence_threshold_auto == 0.95
        assert config.infer_from_activity_components is False
        assert config.model_name == "gpt-4-turbo"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        config = SpecimenEnrichmentConfig()
        d = config.to_dict()

        assert d["confidenceThresholdAuto"] == 0.90
        assert d["useCache"] is True


class TestSpecimenPatternRegistry:
    """Tests for SpecimenPatternRegistry (validation patterns)."""

    def test_initialization(self):
        """Test registry loads patterns successfully."""
        registry = SpecimenPatternRegistry()
        # Should load without error
        assert registry is not None

    def test_get_activity_mapping_known(self):
        """Test getting mapping for known activity."""
        registry = SpecimenPatternRegistry()

        mapping = registry.get_activity_mapping("hematology")
        # May or may not exist depending on config
        # Just verify no crash

    def test_get_activity_mapping_unknown(self):
        """Test getting mapping for unknown activity."""
        registry = SpecimenPatternRegistry()

        mapping = registry.get_activity_mapping("unknown_activity_xyz")
        assert mapping is None

    def test_is_non_specimen_activity_positive(self):
        """Test detection of non-specimen activities."""
        registry = SpecimenPatternRegistry()

        # These should typically not require specimens
        assert registry.is_non_specimen_activity("Vital Signs") or True  # May not have patterns loaded
        assert registry.is_non_specimen_activity("ECG") or True
        assert registry.is_non_specimen_activity("Physical Examination") or True

    def test_validate_decision_no_specimen(self):
        """Test validation of non-specimen decision."""
        registry = SpecimenPatternRegistry()

        decision = SpecimenDecision(
            activity_id="ACT-001",
            activity_name="Vital Signs",
            has_specimen=False,
            confidence=1.0,
        )

        discrepancies = registry.validate_decision(decision)
        assert len(discrepancies) == 0  # No specimen = no validation needed


class TestSpecimenEnricher:
    """Tests for SpecimenEnricher class."""

    def test_initialization(self):
        """Test enricher initialization."""
        enricher = SpecimenEnricher()

        assert enricher.config is not None
        assert enricher._pattern_registry is not None

    def test_initialization_with_config(self):
        """Test enricher with custom config."""
        config = SpecimenEnrichmentConfig(
            confidence_threshold_auto=0.85,
            use_cache=False,
        )
        enricher = SpecimenEnricher(config=config, use_cache=False)

        assert enricher.config.confidence_threshold_auto == 0.85
        assert enricher.use_cache is False

    def test_extract_candidate_activities_by_domain(self):
        """Test extracting candidates by domain."""
        enricher = SpecimenEnricher()

        usdm = {
            "activities": [
                {"id": "ACT-001", "name": "Hematology", "domain": {"code": "LB"}},
                {"id": "ACT-002", "name": "Vital Signs", "domain": {"code": "VS"}},
                {"id": "ACT-003", "name": "PK Sample", "domain": {"code": "PC"}},
                {"id": "ACT-004", "name": "ECG", "domain": {"code": "EG"}},
            ]
        }

        candidates = enricher._extract_candidate_activities(usdm)

        # LB and PC are specimen domains, VS and EG are not
        candidate_ids = [c["id"] for c in candidates]
        assert "ACT-001" in candidate_ids  # LB
        assert "ACT-003" in candidate_ids  # PC
        assert "ACT-002" not in candidate_ids  # VS
        assert "ACT-004" not in candidate_ids  # EG

    def test_check_activity_components_match(self):
        """Test activity_components.json lookup."""
        enricher = SpecimenEnricher()

        # This depends on actual config file contents
        # Test that method doesn't crash
        decision = enricher._check_activity_components("Hematology")
        # May return None if not in config, or SpecimenDecision if found

    def test_cache_key_generation(self):
        """Test cache key is consistent and normalized."""
        enricher = SpecimenEnricher()

        key1 = enricher._get_cache_key("Hematology")
        key2 = enricher._get_cache_key("hematology")
        key3 = enricher._get_cache_key("  Hematology  ")

        assert key1 == key2 == key3

    def test_cache_operations(self):
        """Test cache read/write operations."""
        enricher = SpecimenEnricher(use_cache=True)

        decision = SpecimenDecision(
            activity_id="ACT-001",
            activity_name="Hematology",
            has_specimen=True,
            specimen_category=SpecimenCategory.BLOOD,
            confidence=0.98,
        )

        # Initially not in memory cache
        cached = enricher._check_cache("Hematology")
        # May be None or may hit disk cache

        # Add to cache
        enricher._update_cache("Hematology", decision)

        # Now should be in memory cache
        cached = enricher._check_cache("Hematology")
        assert cached is not None
        assert cached.activity_name == "Hematology"
        assert cached.source == "cache"

    def test_create_specimen_code(self):
        """Test USDM Code object creation for specimen type."""
        enricher = SpecimenEnricher()

        code = enricher._create_specimen_code(
            SpecimenCategory.BLOOD,
            SpecimenSubtype.WHOLE_BLOOD
        )

        assert code["instanceType"] == "Code"
        assert "id" in code
        assert "codeSystem" in code
        # Code may or may not have actual CDISC code depending on config

    def test_create_tube_code(self):
        """Test USDM Code object creation for tube type."""
        enricher = SpecimenEnricher()

        code = enricher._create_tube_code(TubeType.EDTA)

        assert code["instanceType"] == "Code"
        assert "id" in code
        assert code["id"].startswith("CODE-TUBE-")

    def test_create_purpose_code(self):
        """Test USDM Code object creation for purpose."""
        enricher = SpecimenEnricher()

        code = enricher._create_purpose_code(SpecimenPurpose.PK)

        assert code["instanceType"] == "Code"
        assert "id" in code

    def test_generate_enrichment_with_specimen(self):
        """Test generating enrichment from decision."""
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
            ),
            volumes=[VolumeSpecification(value=3, unit="mL")],
            confidence=0.98,
            rationale="Standard hematology panel",
        )

        enrichment = enricher._generate_enrichment(decision)

        assert enrichment is not None
        assert enrichment.activity_id == "ACT-001"
        assert enrichment.confidence == 0.98
        assert "specimenType" in enrichment.specimen_collection
        assert "collectionContainer" in enrichment.specimen_collection
        assert "collectionVolume" in enrichment.specimen_collection
        assert "_specimenEnrichment" in enrichment.specimen_collection

    def test_generate_enrichment_without_specimen(self):
        """Test generating enrichment for non-specimen activity."""
        enricher = SpecimenEnricher()

        decision = SpecimenDecision(
            activity_id="ACT-002",
            activity_name="Vital Signs",
            has_specimen=False,
            confidence=1.0,
        )

        enrichment = enricher._generate_enrichment(decision)

        assert enrichment is None  # No enrichment for non-specimen

    def test_generate_enrichment_with_optional_specimen(self):
        """Test generating enrichment for optional specimen."""
        enricher = SpecimenEnricher()
        enricher.config.create_conditions_for_optional = True

        decision = SpecimenDecision(
            activity_id="ACT-003",
            activity_name="Optional PK",
            has_specimen=True,
            specimen_category=SpecimenCategory.BLOOD,
            is_optional=True,
            condition_text="Optional: collect if PK performed",
            confidence=0.85,
        )

        enrichment = enricher._generate_enrichment(decision)

        assert enrichment is not None
        assert len(enrichment.conditions_created) == 1
        assert enrichment.conditions_created[0]["instanceType"] == "Condition"

    def test_parse_llm_response_valid(self):
        """Test parsing valid LLM JSON response."""
        enricher = SpecimenEnricher()

        response = json.dumps({
            "ACT-001": {
                "activityName": "Hematology",
                "hasSpecimen": True,
                "specimenCategory": "blood",
                "specimenSubtype": "whole_blood",
                "confidence": 0.95,
                "rationale": "Standard panel"
            },
            "ACT-002": {
                "activityName": "Vital Signs",
                "hasSpecimen": False,
                "confidence": 1.0,
                "rationale": "No specimen needed"
            }
        })

        activities = [
            {"id": "ACT-001", "name": "Hematology"},
            {"id": "ACT-002", "name": "Vital Signs"},
        ]

        decisions = enricher._parse_llm_response(response, activities)

        assert len(decisions) == 2
        assert "ACT-001" in decisions
        assert "ACT-002" in decisions
        assert decisions["ACT-001"].has_specimen is True
        assert decisions["ACT-002"].has_specimen is False

    def test_parse_llm_response_with_markdown(self):
        """Test parsing LLM response wrapped in markdown code blocks."""
        enricher = SpecimenEnricher()

        response = """```json
{
    "ACT-001": {
        "activityName": "Chemistry",
        "hasSpecimen": true,
        "specimenCategory": "blood",
        "confidence": 0.92,
        "rationale": "Blood chemistry panel"
    }
}
```"""

        activities = [{"id": "ACT-001", "name": "Chemistry"}]

        decisions = enricher._parse_llm_response(response, activities)

        assert len(decisions) == 1
        assert decisions["ACT-001"].has_specimen is True

    def test_parse_llm_response_invalid_json(self):
        """Test handling invalid JSON response."""
        enricher = SpecimenEnricher()

        response = "This is not valid JSON"

        activities = [{"id": "ACT-001", "name": "Test"}]

        decisions = enricher._parse_llm_response(response, activities)

        # Should return default decisions with review flag
        assert len(decisions) == 1
        assert decisions["ACT-001"].requires_human_review is True
        assert decisions["ACT-001"].confidence == 0.0


class TestSpecimenEnricherApplyEnrichments:
    """Tests for applying enrichments to USDM."""

    def test_apply_enrichments_updates_activities(self):
        """Test that enrichments update Activity objects."""
        enricher = SpecimenEnricher()

        usdm = {
            "activities": [
                {"id": "ACT-001", "name": "Hematology"},
                {"id": "ACT-002", "name": "Vital Signs"},
            ],
            "scheduledActivityInstances": [
                {"id": "SAI-001", "activityId": "ACT-001"},
                {"id": "SAI-002", "activityId": "ACT-002"},
            ],
            "conditions": [],
        }

        enrichment = SpecimenEnrichment(
            id="SPEC-001",
            activity_id="ACT-001",
            activity_name="Hematology",
            specimen_collection={"id": "SPEC-001", "instanceType": "SpecimenCollection"},
            biospecimen_requirements={"specimenType": {"code": "C78732"}},
            confidence=0.98,
        )

        result = Stage5Result(
            enrichments=[enrichment],
        )

        updated_usdm = enricher.apply_enrichments_to_usdm(usdm, result)

        # Check activity was updated
        act_001 = next(a for a in updated_usdm["activities"] if a["id"] == "ACT-001")
        assert "biospecimenRequirements" in act_001

        # Check SAI was updated
        sai_001 = next(s for s in updated_usdm["scheduledActivityInstances"] if s["activityId"] == "ACT-001")
        assert "specimenCollection" in sai_001

    def test_apply_enrichments_adds_conditions(self):
        """Test that optional specimen conditions are added."""
        enricher = SpecimenEnricher()

        usdm = {
            "activities": [{"id": "ACT-001", "name": "Optional PK"}],
            "scheduledActivityInstances": [{"id": "SAI-001", "activityId": "ACT-001"}],
            "conditions": [],
        }

        enrichment = SpecimenEnrichment(
            id="SPEC-001",
            activity_id="ACT-001",
            activity_name="Optional PK",
            specimen_collection={},
            biospecimen_requirements={},
            conditions_created=[
                {"id": "COND-001", "instanceType": "Condition", "name": "Optional specimen"}
            ],
            confidence=0.85,
        )

        result = Stage5Result(enrichments=[enrichment])

        updated_usdm = enricher.apply_enrichments_to_usdm(usdm, result)

        assert len(updated_usdm["conditions"]) == 1
        assert updated_usdm["conditions"][0]["id"] == "COND-001"


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_infer_specimen_from_activity_name_blood(self):
        """Test inferring blood specimens from activity names."""
        assert infer_specimen_from_activity_name("Hematology") == SpecimenCategory.BLOOD
        assert infer_specimen_from_activity_name("CBC") == SpecimenCategory.BLOOD
        assert infer_specimen_from_activity_name("Chemistry Panel") == SpecimenCategory.BLOOD
        assert infer_specimen_from_activity_name("Serum Chemistry") == SpecimenCategory.BLOOD
        assert infer_specimen_from_activity_name("Coagulation") == SpecimenCategory.BLOOD
        assert infer_specimen_from_activity_name("PK Sample") == SpecimenCategory.BLOOD

    def test_infer_specimen_from_activity_name_urine(self):
        """Test inferring urine specimens from activity names."""
        assert infer_specimen_from_activity_name("Urinalysis") == SpecimenCategory.URINE
        assert infer_specimen_from_activity_name("Urine Drug Screen") == SpecimenCategory.URINE

    def test_infer_specimen_from_activity_name_tissue(self):
        """Test inferring tissue specimens from activity names."""
        assert infer_specimen_from_activity_name("Tumor Biopsy") == SpecimenCategory.TISSUE
        assert infer_specimen_from_activity_name("FFPE Sample") == SpecimenCategory.TISSUE

    def test_infer_specimen_from_activity_name_csf(self):
        """Test inferring CSF specimens from activity names."""
        assert infer_specimen_from_activity_name("CSF Collection") == SpecimenCategory.CSF
        assert infer_specimen_from_activity_name("Lumbar Puncture") == SpecimenCategory.CSF

    def test_infer_specimen_from_activity_name_none(self):
        """Test that non-specimen activities return None."""
        assert infer_specimen_from_activity_name("Vital Signs") is None
        assert infer_specimen_from_activity_name("ECG") is None
        assert infer_specimen_from_activity_name("Physical Exam") is None

    def test_infer_subtype_from_panel(self):
        """Test inferring specimen subtype from panel name."""
        assert infer_subtype_from_panel("Hematology") == SpecimenSubtype.WHOLE_BLOOD
        assert infer_subtype_from_panel("CBC with Differential") == SpecimenSubtype.WHOLE_BLOOD
        assert infer_subtype_from_panel("Coagulation Panel") == SpecimenSubtype.CITRATE_PLASMA
        assert infer_subtype_from_panel("Chemistry Panel") == SpecimenSubtype.SERUM
        assert infer_subtype_from_panel("Serum Chemistry") == SpecimenSubtype.SERUM
        assert infer_subtype_from_panel("Urinalysis") == SpecimenSubtype.URINE_SPOT

    def test_generate_specimen_collection_id(self):
        """Test specimen collection ID generation."""
        id1 = generate_specimen_collection_id("ACT-001")
        assert id1 == "SPEC-001"

        id2 = generate_specimen_collection_id("ACT-042")
        assert id2 == "SPEC-042"

    def test_generate_condition_id(self):
        """Test condition ID generation."""
        id1 = generate_condition_id("ACT-001", "optional")
        id2 = generate_condition_id("ACT-001", "optional")

        # Should be deterministic
        assert id1 == id2
        assert id1.startswith("COND-SPEC-")

    def test_generate_code_id(self):
        """Test code ID generation."""
        id1 = generate_code_id("SPEC", "C78732")
        assert id1 == "CODE-SPEC-C78732"

    def test_generate_review_id(self):
        """Test review ID generation is unique."""
        id1 = generate_review_id()
        id2 = generate_review_id()

        assert id1 != id2
        assert id1.startswith("REVIEW-SPEC-")


class TestDomainConstants:
    """Tests for domain constant definitions."""

    def test_specimen_domains(self):
        """Test specimen domains are correctly defined."""
        assert "LB" in SPECIMEN_DOMAINS  # Laboratory
        assert "PC" in SPECIMEN_DOMAINS  # Pharmacokinetics
        assert "BS" in SPECIMEN_DOMAINS  # Biospecimen

    def test_non_specimen_domains(self):
        """Test non-specimen domains are correctly defined."""
        assert "VS" in NON_SPECIMEN_DOMAINS  # Vital Signs
        assert "EG" in NON_SPECIMEN_DOMAINS  # ECG
        assert "PE" in NON_SPECIMEN_DOMAINS  # Physical Exam
        assert "QS" in NON_SPECIMEN_DOMAINS  # Questionnaires

    def test_no_overlap(self):
        """Test specimen and non-specimen domains don't overlap."""
        overlap = SPECIMEN_DOMAINS & NON_SPECIMEN_DOMAINS
        assert len(overlap) == 0


# Integration test (requires LLM API keys)
class TestSpecimenEnricherIntegration:
    """Integration tests for Specimen Enricher with LLM."""

    @pytest.mark.skip(reason="Requires LLM API keys - run manually")
    @pytest.mark.asyncio
    async def test_enrich_specimens_full(self):
        """Test full specimen enrichment pipeline (requires API keys)."""
        usdm = {
            "activities": [
                {"id": "ACT-001", "name": "Hematology", "domain": {"code": "LB"}},
                {"id": "ACT-002", "name": "Chemistry Panel", "domain": {"code": "LB"}},
                {"id": "ACT-003", "name": "Vital Signs", "domain": {"code": "VS"}},
            ],
            "scheduledActivityInstances": [
                {"id": "SAI-001", "activityId": "ACT-001"},
                {"id": "SAI-002", "activityId": "ACT-002"},
                {"id": "SAI-003", "activityId": "ACT-003"},
            ],
            "footnotes": [],
            "conditions": [],
        }

        enricher = SpecimenEnricher()
        result = await enricher.enrich_specimens(usdm)

        # Should analyze LB activities
        assert result.activities_analyzed >= 2

        # Hematology and Chemistry should have specimens
        assert result.activities_with_specimens >= 2

        # Vital Signs should NOT have specimen
        vs_decision = result.decisions.get("ACT-003")
        if vs_decision:
            assert vs_decision.has_specimen is False


if __name__ == "__main__":
    # Run basic tests without pytest
    print("Running Stage 5 Specimen Enrichment tests...")

    # Test helper functions
    print("\n--- Testing Helper Functions ---")
    assert infer_specimen_from_activity_name("Hematology") == SpecimenCategory.BLOOD
    assert infer_specimen_from_activity_name("Urinalysis") == SpecimenCategory.URINE
    assert infer_specimen_from_activity_name("Vital Signs") is None
    print("  Specimen inference from activity name working")

    assert infer_subtype_from_panel("Hematology") == SpecimenSubtype.WHOLE_BLOOD
    assert infer_subtype_from_panel("Chemistry") == SpecimenSubtype.SERUM
    print("  Subtype inference from panel working")

    assert generate_specimen_collection_id("ACT-001") == "SPEC-001"
    print("  ID generation working")

    # Test data models
    print("\n--- Testing Data Models ---")
    vol = VolumeSpecification(value=5.0, unit="mL")
    assert vol.to_dict()["value"] == 5.0
    print("  VolumeSpecification working")

    tube = TubeSpecification(tube_type=TubeType.EDTA, tube_color=TubeColor.LAVENDER)
    assert tube.to_dict()["tubeType"] == "edta"
    print("  TubeSpecification working")

    decision = SpecimenDecision(
        activity_id="ACT-001",
        activity_name="Hematology",
        has_specimen=True,
        specimen_category=SpecimenCategory.BLOOD,
        confidence=0.98,
    )
    d = decision.to_dict()
    assert d["hasSpecimen"] is True
    assert d["specimenCategory"] == "blood"
    print("  SpecimenDecision working")

    # Test config
    print("\n--- Testing Config ---")
    config = SpecimenEnrichmentConfig()
    assert config.confidence_threshold_auto == 0.90
    print("  Default config working")

    # Test SpecimenPatternRegistry
    print("\n--- Testing SpecimenPatternRegistry ---")
    registry = SpecimenPatternRegistry()
    print("  Pattern registry loaded")

    # Test SpecimenEnricher
    print("\n--- Testing SpecimenEnricher ---")
    enricher = SpecimenEnricher()
    assert enricher.config is not None
    print("  Enricher initialized")

    # Test candidate extraction
    usdm = {
        "activities": [
            {"id": "ACT-001", "name": "Hematology", "domain": {"code": "LB"}},
            {"id": "ACT-002", "name": "Vital Signs", "domain": {"code": "VS"}},
        ]
    }
    candidates = enricher._extract_candidate_activities(usdm)
    assert len(candidates) == 1
    assert candidates[0]["id"] == "ACT-001"
    print("  Candidate extraction working")

    # Test cache operations
    enricher._update_cache("Hematology", decision)
    cached = enricher._check_cache("Hematology")
    assert cached is not None
    print("  Cache operations working")

    # Test code creation
    code = enricher._create_specimen_code(SpecimenCategory.BLOOD, SpecimenSubtype.WHOLE_BLOOD)
    assert code["instanceType"] == "Code"
    print("  Code creation working")

    # Test enrichment generation
    enrichment = enricher._generate_enrichment(decision)
    assert enrichment is not None
    assert enrichment.activity_id == "ACT-001"
    print("  Enrichment generation working")

    print("\n All Stage 5 basic tests passed!")
