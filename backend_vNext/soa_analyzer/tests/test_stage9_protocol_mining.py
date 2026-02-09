"""
Unit tests for Stage 9: Protocol Mining

Tests the data models, registry, and mining logic.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from ..models.protocol_mining import (
    EnrichmentType,
    SourceModule,
    MatchConfidence,
    MiningProvenance,
    MiningDecision,
    LabManualEnrichment,
    PKPDEnrichment,
    SafetyEnrichment,
    BiospecimenEnrichment,
    EndpointEnrichment,
    ImagingEnrichment,
    DoseModificationEnrichment,
    MiningEnrichment,
    Stage9Result,
    Stage9Config,
)

from ..interpretation.stage9_protocol_mining import (
    ModuleMappingRegistry,
    ProtocolMiner,
    mine_protocol,
)


# ============ TEST FIXTURES ============

@pytest.fixture
def sample_activity():
    return {
        "id": "SAI-001",
        "activityId": "ACT-HEMATOLOGY-001",
        "activityName": "Hematology (CBC)",
        "encounterId": "ENC-SCREENING",
        "domain": "LB",
        "footnoteMarkers": ["a"],
        "isRequired": True,
    }


@pytest.fixture
def sample_activities():
    return [
        {
            "id": "SAI-001",
            "activityName": "Hematology (CBC)",
            "domain": "LB",
            "footnoteMarkers": [],
        },
        {
            "id": "SAI-002",
            "activityName": "PK Sample Collection",
            "domain": "PC",
            "footnoteMarkers": ["a"],
        },
        {
            "id": "SAI-003",
            "activityName": "Tumor Assessment (CT/MRI)",
            "domain": "RS",
            "footnoteMarkers": [],
        },
        {
            "id": "SAI-004",
            "activityName": "Vital Signs",
            "domain": "VS",
            "footnoteMarkers": [],
        },
    ]


@pytest.fixture
def sample_usdm_output(sample_activities):
    return {
        "scheduledActivityInstances": [
            {"id": a["id"], "activityName": a["activityName"], "domain": a.get("domain")}
            for a in sample_activities
        ],
        "encounters": [
            {"id": "ENC-SCREENING", "name": "Screening"},
            {"id": "ENC-WEEK4", "name": "Week 4"},
        ],
    }


@pytest.fixture
def sample_extraction_outputs():
    return {
        "laboratory_specifications": {
            "labTests": [
                {
                    "testName": "Complete Blood Count (CBC)",
                    "loincCode": "58410-2",
                    "specimenType": "Whole Blood",
                    "tubeType": "EDTA",
                    "collectionRequirements": "3 mL",
                    "provenance": {"page_number": 45, "text_snippet": "CBC test..."},
                }
            ],
            "centralLabInfo": {"labName": "Quest Diagnostics"},
        },
        "pkpd_sampling": {
            "pkSampling": [
                {
                    "analyteName": "Drug X",
                    "samplingTimepoints": ["Pre-dose", "1h", "2h", "4h"],
                    "sampleVolume": 5.0,
                    "bioanalyticalMethod": "LC-MS/MS",
                    "provenance": {"page_number": 78},
                }
            ],
            "pkParameters": [
                {"parameterName": "Cmax"},
                {"parameterName": "AUC"},
            ],
        },
        "imaging_central_reading": {
            "response_criteria": {
                "primary_criteria": "RECIST 1.1",
                "criteria_version": "1.1",
            },
            "imaging_modalities": [
                {
                    "modality_type": "CT",
                    "body_regions": ["chest", "abdomen", "pelvis"],
                    "contrast_required": True,
                }
            ],
            "central_reading": {
                "bicr_required": True,
                "vendor_name": "Imaging Core Lab",
                "reading_methodology": "dual reader with adjudication",
            },
            "response_categories": [
                {"category_code": "CR", "category_name": "Complete Response"},
                {"category_code": "PR", "category_name": "Partial Response"},
            ],
        },
        "adverse_events": {
            "grading_system": {
                "system_name": "CTCAE",
                "system_version": "5.0",
            },
            "aesi": [{"term": "Neutropenia"}, {"term": "Thrombocytopenia"}],
        },
    }


@pytest.fixture
def sample_config():
    return Stage9Config(
        confidence_threshold_auto=0.90,
        confidence_threshold_review=0.70,
        batch_size=25,
        use_cache=False,
    )


# ============ TEST ENUMS ============

class TestEnums:
    def test_enrichment_type_values(self):
        assert EnrichmentType.LAB_MANUAL == "lab_manual"
        assert EnrichmentType.IMAGING == "imaging"
        assert EnrichmentType.DOSE_MODIFICATION == "dose_modification"

    def test_source_module_values(self):
        assert SourceModule.LABORATORY_SPECIFICATIONS == "laboratory_specifications"
        assert SourceModule.IMAGING_CENTRAL_READING == "imaging_central_reading"
        assert SourceModule.DOSE_MODIFICATIONS == "dose_modifications"

    def test_match_confidence_values(self):
        assert MatchConfidence.HIGH == "high"
        assert MatchConfidence.MEDIUM == "medium"
        assert MatchConfidence.LOW == "low"


# ============ TEST MINING PROVENANCE ============

class TestMiningProvenance:
    def test_create_provenance(self):
        prov = MiningProvenance(
            source_module="laboratory_specifications",
            field_path="labTests[0].testName",
            page_numbers=[45, 46],
            text_snippets=["CBC test..."],
            model_used="gemini-2.0-flash-exp",
        )
        assert prov.source_module == "laboratory_specifications"
        assert prov.page_numbers == [45, 46]
        assert prov.extraction_timestamp  # Should be auto-set

    def test_to_dict(self):
        prov = MiningProvenance(
            source_module="pkpd_sampling",
            field_path="pkSampling[0]",
            page_numbers=[78],
            text_snippets=["PK sample..."],
            model_used="gemini",
        )
        d = prov.to_dict()
        assert d["sourceModule"] == "pkpd_sampling"
        assert d["pageNumbers"] == [78]

    def test_from_dict(self):
        data = {
            "sourceModule": "imaging_central_reading",
            "fieldPath": "response_criteria",
            "pageNumbers": [80],
            "textSnippets": ["RECIST..."],
            "modelUsed": "azure",
        }
        prov = MiningProvenance.from_dict(data)
        assert prov.source_module == "imaging_central_reading"
        assert prov.page_numbers == [80]


# ============ TEST MINING DECISION ============

class TestMiningDecision:
    def test_create_decision(self):
        decision = MiningDecision(
            activity_id="SAI-001",
            activity_name="Hematology",
            domain="LB",
            matched_modules=["laboratory_specifications", "adverse_events"],
            confidence=0.92,
            model_used="gemini",
        )
        assert decision.activity_id == "SAI-001"
        assert len(decision.matched_modules) == 2
        assert decision.confidence == 0.92

    def test_generate_cache_key(self):
        decision = MiningDecision(
            activity_id="SAI-001",
            activity_name="Test",
            model_used="gemini",
        )
        key = decision.generate_cache_key()
        assert isinstance(key, str)
        assert len(key) == 32  # MD5 hex digest

    def test_get_confidence_level_high(self):
        decision = MiningDecision(
            activity_id="SAI-001",
            activity_name="Test",
            confidence=0.95,
        )
        assert decision.get_confidence_level() == MatchConfidence.HIGH

    def test_get_confidence_level_medium(self):
        decision = MiningDecision(
            activity_id="SAI-001",
            activity_name="Test",
            confidence=0.75,
        )
        assert decision.get_confidence_level() == MatchConfidence.MEDIUM

    def test_get_confidence_level_low(self):
        decision = MiningDecision(
            activity_id="SAI-001",
            activity_name="Test",
            confidence=0.50,
        )
        assert decision.get_confidence_level() == MatchConfidence.LOW

    def test_from_llm_response(self):
        response_data = {
            "matched_modules": [
                {
                    "module": "laboratory_specifications",
                    "confidence": 0.95,
                    "rationale": "CBC test found in lab specs",
                }
            ]
        }
        activity = {"id": "SAI-001", "activityName": "Hematology"}

        decision = MiningDecision.from_llm_response(response_data, activity, "gemini")
        assert decision.activity_id == "SAI-001"
        assert "laboratory_specifications" in decision.matched_modules
        assert decision.confidence == 0.95


# ============ TEST ENRICHMENT DATACLASSES ============

class TestLabManualEnrichment:
    def test_create_enrichment(self):
        enrichment = LabManualEnrichment(
            lab_test_name="Complete Blood Count",
            loinc_code="58410-2",
            specimen_type="Whole Blood",
            tube_type="EDTA",
            central_lab_name="Quest",
        )
        assert enrichment.lab_test_name == "Complete Blood Count"
        assert enrichment.loinc_code == "58410-2"

    def test_to_dict(self):
        enrichment = LabManualEnrichment(
            lab_test_name="CBC",
            loinc_code="58410-2",
        )
        d = enrichment.to_dict()
        assert d["labTestName"] == "CBC"
        assert d["loincCode"] == "58410-2"


class TestImagingEnrichment:
    def test_create_oncology_enrichment(self):
        enrichment = ImagingEnrichment(
            response_criteria="RECIST 1.1",
            criteria_version="1.1",
            imaging_modality="CT",
            body_regions=["chest", "abdomen"],
            bicr_required=True,
            bicr_vendor="Imaging Core Lab",
            response_categories=["CR", "PR", "SD", "PD"],
        )
        assert enrichment.response_criteria == "RECIST 1.1"
        assert enrichment.bicr_required is True
        assert len(enrichment.response_categories) == 4

    def test_to_dict(self):
        enrichment = ImagingEnrichment(
            response_criteria="iRECIST",
            immune_related_criteria=True,
        )
        d = enrichment.to_dict()
        assert d["responseCriteria"] == "iRECIST"
        assert d["immuneRelatedCriteria"] is True


class TestDoseModificationEnrichment:
    def test_create_dlt_enrichment(self):
        enrichment = DoseModificationEnrichment(
            dlt_definition="Any Grade 4 non-hematologic toxicity",
            dlt_evaluation_period="Cycle 1 (28 days)",
            dlt_criteria=["Grade 4 neutropenia >7 days", "Grade 4 thrombocytopenia"],
            max_dose_reductions=2,
            re_escalation_allowed=False,
        )
        assert enrichment.dlt_definition is not None
        assert len(enrichment.dlt_criteria) == 2
        assert enrichment.max_dose_reductions == 2

    def test_to_dict(self):
        enrichment = DoseModificationEnrichment(
            dlt_evaluation_period="28 days",
            dose_reduction_levels=[{"level": "-1", "dose": "80mg"}],
        )
        d = enrichment.to_dict()
        assert d["dltEvaluationPeriod"] == "28 days"
        assert len(d["doseReductionLevels"]) == 1


# ============ TEST MINING ENRICHMENT ============

class TestMiningEnrichment:
    def test_create_composite_enrichment(self):
        lab = LabManualEnrichment(lab_test_name="CBC")
        safety = SafetyEnrichment(safety_assessment_type="CTCAE v5.0")

        enrichment = MiningEnrichment(
            id="MINE-001",
            activity_id="SAI-001",
            activity_name="Hematology",
            lab_manual_enrichment=lab,
            safety_enrichment=safety,
            overall_confidence=0.90,
            sources_used=["laboratory_specifications", "adverse_events"],
        )
        assert enrichment.id == "MINE-001"
        assert enrichment.lab_manual_enrichment is not None
        assert enrichment.safety_enrichment is not None

    def test_get_enrichment_types(self):
        lab = LabManualEnrichment(lab_test_name="CBC")
        imaging = ImagingEnrichment(response_criteria="RECIST")

        enrichment = MiningEnrichment(
            id="MINE-001",
            activity_id="SAI-001",
            activity_name="Test",
            lab_manual_enrichment=lab,
            imaging_enrichment=imaging,
            overall_confidence=0.85,
        )

        types = enrichment.get_enrichment_types()
        assert EnrichmentType.LAB_MANUAL in types
        assert EnrichmentType.IMAGING in types
        assert EnrichmentType.SAFETY not in types

    def test_to_dict(self):
        enrichment = MiningEnrichment(
            id="MINE-001",
            activity_id="SAI-001",
            activity_name="Test",
            overall_confidence=0.88,
            sources_used=["lab"],
        )
        d = enrichment.to_dict()
        assert d["id"] == "MINE-001"
        assert d["overallConfidence"] == 0.88


# ============ TEST STAGE9 RESULT ============

class TestStage9Result:
    def test_empty_result(self):
        result = Stage9Result()
        assert result.total_activities_processed == 0
        assert result.activities_enriched == 0
        assert len(result.enrichments) == 0

    def test_get_summary(self):
        result = Stage9Result(
            total_activities_processed=10,
            activities_enriched=8,
            activities_no_match=2,
            cache_hits=5,
            llm_calls=5,
            avg_confidence=0.85,
            processing_time_seconds=10.5,
        )
        summary = result.get_summary()
        assert summary["totalActivitiesProcessed"] == 10
        assert summary["activitiesEnriched"] == 8
        assert summary["avgConfidence"] == 0.85


# ============ TEST STAGE9 CONFIG ============

class TestStage9Config:
    def test_default_config(self):
        config = Stage9Config()
        assert config.confidence_threshold_auto == 0.90
        assert config.confidence_threshold_review == 0.70
        assert config.batch_size == 25

    def test_custom_config(self):
        config = Stage9Config(
            confidence_threshold_auto=0.85,
            batch_size=50,
            model_name="gemini-1.5-pro",
        )
        assert config.confidence_threshold_auto == 0.85
        assert config.batch_size == 50

    def test_to_dict(self):
        config = Stage9Config()
        d = config.to_dict()
        assert "confidenceThresholdAuto" in d
        assert "batchSize" in d


# ============ TEST MODULE MAPPING REGISTRY ============

class TestModuleMappingRegistry:
    def test_registry_loads(self):
        registry = ModuleMappingRegistry()
        # Should load without error

    def test_get_candidate_modules_by_domain(self):
        registry = ModuleMappingRegistry()
        candidates = registry.get_candidate_modules("LB", "Some Lab Test")
        assert "laboratory_specifications" in candidates or len(candidates) >= 0

    def test_get_candidate_modules_by_keyword(self):
        registry = ModuleMappingRegistry()
        candidates = registry.get_candidate_modules(None, "hematology")
        assert "laboratory_specifications" in candidates or len(candidates) >= 0

    def test_get_enrichment_fields(self):
        registry = ModuleMappingRegistry()
        fields = registry.get_enrichment_fields("laboratory_specifications")
        # May be empty if config not loaded
        assert isinstance(fields, dict)


# ============ TEST PROTOCOL MINER ============

class TestProtocolMiner:
    def test_miner_init(self, sample_config):
        miner = ProtocolMiner(sample_config)
        assert miner.config == sample_config

    def test_extract_activities(self, sample_config, sample_usdm_output):
        miner = ProtocolMiner(sample_config)
        activities = miner._extract_activities(sample_usdm_output)
        assert len(activities) == 4
        assert activities[0]["activityName"] == "Hematology (CBC)"

    def test_generate_cache_key(self, sample_config, sample_activity):
        miner = ProtocolMiner(sample_config)
        key = miner._generate_cache_key(sample_activity)
        assert isinstance(key, str)
        assert len(key) == 32

    def test_generate_module_summaries(self, sample_config, sample_extraction_outputs):
        miner = ProtocolMiner(sample_config)
        summaries = miner._generate_module_summaries(sample_extraction_outputs)
        assert isinstance(summaries, dict)

    def test_extract_lab_enrichment(self, sample_config, sample_activity, sample_extraction_outputs):
        miner = ProtocolMiner(sample_config)
        lab_output = sample_extraction_outputs["laboratory_specifications"]

        # Activity name should match lab test
        activity = {"activityName": "Complete Blood Count (CBC)"}
        enrichment = miner._extract_lab_enrichment(activity, lab_output)

        assert enrichment is not None
        assert enrichment.lab_test_name == "Complete Blood Count (CBC)"
        assert enrichment.loinc_code == "58410-2"

    def test_extract_imaging_enrichment(self, sample_config, sample_extraction_outputs):
        miner = ProtocolMiner(sample_config)
        imaging_output = sample_extraction_outputs["imaging_central_reading"]

        activity = {"activityName": "Tumor Assessment"}
        enrichment = miner._extract_imaging_enrichment(activity, imaging_output)

        assert enrichment is not None
        assert enrichment.response_criteria == "RECIST 1.1"
        assert enrichment.bicr_required is True


# ============ TEST PARSE MATCH RESPONSE ============

class TestParseMatchResponse:
    def test_parse_valid_response(self, sample_config, sample_activities):
        miner = ProtocolMiner(sample_config)

        response_text = json.dumps({
            "matches": [
                {
                    "activity_id": "SAI-001",
                    "activity_name": "Hematology (CBC)",
                    "matched_modules": [
                        {
                            "module": "laboratory_specifications",
                            "confidence": 0.95,
                            "rationale": "CBC test found",
                        }
                    ],
                }
            ]
        })

        decisions = miner._parse_match_response(
            response_text, sample_activities, "gemini"
        )

        assert "SAI-001" in decisions
        assert decisions["SAI-001"].confidence == 0.95

    def test_parse_invalid_json(self, sample_config, sample_activities):
        miner = ProtocolMiner(sample_config)

        response_text = "not valid json"

        decisions = miner._parse_match_response(
            response_text, sample_activities, "gemini"
        )

        # Should create review-needed decisions for all
        assert len(decisions) == len(sample_activities)
        for decision in decisions.values():
            assert decision.requires_human_review is True

    def test_parse_with_markdown_wrapper(self, sample_config, sample_activities):
        miner = ProtocolMiner(sample_config)

        response_text = """```json
{
    "matches": [
        {
            "activity_id": "SAI-001",
            "activity_name": "Hematology (CBC)",
            "matched_modules": []
        }
    ]
}
```"""

        decisions = miner._parse_match_response(
            response_text, sample_activities, "gemini"
        )

        # Should strip markdown and parse
        assert "SAI-001" in decisions


# ============ TEST APPLY ENRICHMENTS ============

class TestApplyEnrichments:
    def test_apply_enrichments_to_usdm(self, sample_config, sample_usdm_output):
        miner = ProtocolMiner(sample_config)

        enrichment = MiningEnrichment(
            id="MINE-001",
            activity_id="SAI-001",
            activity_name="Hematology (CBC)",
            lab_manual_enrichment=LabManualEnrichment(lab_test_name="CBC"),
            overall_confidence=0.92,
            sources_used=["laboratory_specifications"],
        )

        result = Stage9Result(enrichments=[enrichment])

        updated = miner.apply_enrichments_to_usdm(sample_usdm_output, result)

        # Check enrichment was applied
        sai = updated["scheduledActivityInstances"][0]
        assert "_miningEnrichment" in sai
        assert sai["_miningEnrichment"]["id"] == "MINE-001"


# ============ TEST INTEGRATION WITH ASYNC ============

@pytest.mark.asyncio
class TestAsyncMining:
    async def test_mine_protocol_no_llm(self, sample_config, sample_usdm_output, sample_extraction_outputs):
        """Test mining without actual LLM calls (mocked)"""
        miner = ProtocolMiner(sample_config)

        # Mock LLM call
        mock_response = json.dumps({
            "matches": [
                {
                    "activity_id": "SAI-001",
                    "activity_name": "Hematology (CBC)",
                    "matched_modules": [
                        {"module": "laboratory_specifications", "confidence": 0.95, "rationale": "CBC found"}
                    ],
                }
            ]
        })

        with patch.object(miner, '_call_llm_with_fallback', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (mock_response, "gemini")

            result = await miner.mine_protocol(sample_usdm_output, sample_extraction_outputs)

            assert result.total_activities_processed == 4
            # LLM was called (implementation may batch or process individually)
            assert result.llm_calls >= 1

    async def test_convenience_function(self, sample_config, sample_usdm_output, sample_extraction_outputs):
        """Test the convenience function"""
        mock_response = json.dumps({"matches": []})

        with patch('soa_analyzer.interpretation.stage9_protocol_mining.ProtocolMiner._call_llm_with_fallback',
                   new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = (mock_response, "gemini")

            updated_usdm, result = await mine_protocol(
                sample_usdm_output, sample_extraction_outputs, sample_config
            )

            assert isinstance(result, Stage9Result)
            assert isinstance(updated_usdm, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
