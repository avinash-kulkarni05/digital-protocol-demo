"""
Transform flat USDM structure to domain-sections structure for frontend.

The backend stores all data in a flat structure under 'study', but the frontend
expects a structured format with 'domainSections' for module-specific data.
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class UsdmTransformer:
    """Transform USDM data from flat structure to frontend domain sections structure."""

    @staticmethod
    def transform_for_frontend(usdm_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform flat USDM JSON to frontend-expected structure.

        Input structure:
        {
            "study": {
                "protocol_endpoints": {...},
                "laboratory_tests": [...],
                ... (all fields flat)
            }
        }

        Output structure:
        {
            "study": {...core study fields only...},
            "domainSections": {
                "endpointsEstimandsSAP": {"data": {...}},
                "laboratorySpecifications": {"data": {...}},
                ...
            },
            "agentDocumentation": {...},
            "extractionMetadata": {...}
        }
        """
        if not usdm_json or "study" not in usdm_json:
            logger.warning("Invalid USDM JSON structure, missing 'study' key")
            return usdm_json

        study = usdm_json["study"]

        # Extract domain-specific data from study object
        domain_sections = {
            "endpointsEstimandsSAP": {
                "data": study.get("protocol_endpoints", {})
            },
            "adverseEvents": {
                "data": {
                    "aesi_list": study.get("aesi_list", []),
                    "ae_definitions": study.get("ae_definitions", {}),
                    "sae_criteria": study.get("sae_criteria", {}),
                    "dlt_criteria": study.get("dlt_criteria", {}),
                    "grading_system": study.get("grading_system", {}),
                    "causality_assessment": study.get("causality_assessment", {}),
                    "abnormal_result_grading": study.get("abnormal_result_grading", {}),
                    "immune_related_criteria": study.get("immune_related_criteria", {}),
                    "critical_value_reporting": study.get("critical_value_reporting", {}),
                }
            },
            "safetyDecisionPoints": {
                "data": {
                    "decision_points": study.get("decision_points", []),
                    "dose_modification_levels": study.get("dose_modification_levels", {}),
                    "organ_specific_adjustments": study.get("organ_specific_adjustments", []),
                    "lab_based_dose_modifications": study.get("lab_based_dose_modifications", []),
                    "stopping_rules_summary": study.get("stopping_rules_summary", {}),
                }
            },
            "concomitantMedications": {
                "data": {
                    "allowed_medications": study.get("allowed_medications", []),
                    "required_medications": study.get("required_medications", []),
                    "prohibited_medications": study.get("prohibited_medications", []),
                    "restricted_medications": study.get("restricted_medications", []),
                    "rescue_medications": study.get("rescue_medications", []),
                    "drug_interactions": study.get("drug_interactions", []),
                    "washout_requirements": study.get("washout_requirements", []),
                    "herbal_supplements_policy": study.get("herbal_supplements_policy", {}),
                }
            },
            "biospecimenHandling": {
                "data": {
                    "biomarker_samples": study.get("biomarker_samples", {}),
                    "sample_handling": study.get("sample_handling", {}),
                    "pharmacokinetic_samples": study.get("pharmacokinetic_samples", {}),
                    "collection_schedule": study.get("collection_schedule", []),
                    "storage_requirements": study.get("storage_requirements", []),
                    "shipping_requirements": study.get("shipping_requirements", []),
                    "processing_requirements": study.get("processing_requirements", []),
                    "collection_containers": study.get("collection_containers", []),
                    "discovered_specimen_types": study.get("discovered_specimen_types", []),
                    "sample_collection_requirements": study.get("sample_collection_requirements", {}),
                }
            },
            "laboratorySpecifications": {
                "data": {
                    "laboratory_tests": study.get("laboratory_tests", []),
                    "central_laboratory": study.get("central_laboratory", {}),
                    "local_lab_requirements": study.get("local_lab_requirements", {}),
                    "testing_schedule": study.get("testing_schedule", []),
                    "discovered_panels": study.get("discovered_panels", []),
                    "eligibility_lab_criteria": study.get("eligibility_lab_criteria", []),
                }
            },
            "informedConsent": {
                "data": {
                    "confidentiality": study.get("confidentiality", {}),
                    "voluntary_participation": study.get("voluntary_participation", {}),
                    "special_consents": study.get("special_consents", {}),
                    "consent_withdrawal": study.get("consent_withdrawal", {}),
                    "compensation_costs": study.get("compensation_costs", {}),
                }
            },
            "proSpecifications": {
                "data": {
                    "pro_instruments": study.get("pro_instruments", []),
                    "obsro_instruments": study.get("obsro_instruments", []),
                    "perfo_instruments": study.get("perfo_instruments", []),
                    "clinro_instruments": study.get("clinro_instruments", []),
                }
            },
            "dataManagement": {
                "data": {
                    "data_quality": study.get("data_quality", {}),
                    "data_standards": study.get("data_standards", {}),
                    "data_retention": study.get("data_retention", {}),
                    "data_archival": study.get("data_archival", {}),
                    "data_transfers": study.get("data_transfers", {}),
                    "database_management": study.get("database_management", {}),
                    "edc_specifications": study.get("edc_specifications", {}),
                    "coding_dictionary": study.get("coding_dictionary", {}),
                }
            },
            "siteOperationsLogistics": {
                "data": {
                    "site_selection": study.get("site_selection", {}),
                    "site_personnel": study.get("site_personnel", {}),
                    "site_activation_timeline": study.get("site_activation_timeline", {}),
                    "equipment_facilities": study.get("equipment_facilities", {}),
                    "training_requirements": study.get("training_requirements", {}),
                    "technology_systems": study.get("technology_systems", {}),
                    "vendor_coordination": study.get("vendor_coordination", []),
                    "drug_supply_logistics": study.get("drug_supply_logistics", {}),
                }
            },
            "qualityManagement": {
                "data": {
                    "monitoring": study.get("monitoring", {}),
                    "monitoring_plan": study.get("monitoring_plan", {}),
                    "rbqm": study.get("rbqm", {}),
                    "regulatory_ethics": study.get("regulatory_ethics", {}),
                    "safety_committees": study.get("safety_committees", []),
                }
            },
            "withdrawalProcedures": {
                "data": {
                    "discontinuation_types": study.get("discontinuation_types", []),
                    "discontinuation_visit": study.get("discontinuation_visit", {}),
                    "administrative_withdrawal": study.get("administrative_withdrawal", {}),
                    "post_discontinuation_followup": study.get("post_discontinuation_followup", {}),
                    "lost_to_followup": study.get("lost_to_followup", {}),
                    "replacement_strategy": study.get("replacement_strategy", {}),
                    "retention_strategies": study.get("retention_strategies", {}),
                }
            },
            "imagingCentralReading": {
                "data": {
                    "imaging_modalities": study.get("imaging_modalities", []),
                    "central_reading": study.get("central_reading", {}),
                    "image_submission": study.get("image_submission", {}),
                    "response_criteria": study.get("response_criteria", {}),
                    "response_categories": study.get("response_categories", []),
                    "lesion_requirements": study.get("lesion_requirements", {}),
                }
            },
            "pkpdSampling": {
                "data": {
                    "pk_sampling": study.get("pk_sampling", {}),
                    "pk_parameters": study.get("pk_parameters", {}),
                    "population_pk": study.get("population_pk", {}),
                    "pd_assessments": study.get("pd_assessments", {}),
                    "immunogenicity": study.get("immunogenicity", {}),
                }
            },
            "studyDesign": {
                "data": {
                    "studyArms": study.get("studyArms", []),
                    "studyEpochs": study.get("studyEpochs", []),
                    "studyCells": study.get("studyCells", []),
                }
            },
        }

        # Create core study object with only basic metadata (no domain-specific fields)
        core_study_fields = [
            "id", "name", "version", "description", "officialTitle", "documentType",
            "instanceType", "schemaVersion", "ich_m11_section", "isPivotal",
            "studyType", "studyPhase", "indication", "therapeuticArea", "sponsorName",
            "studyIdentifiers", "studyProtocolVersions", "studyDesignInfo", "studyPopulation",
            "studyMilestones", "designMetadata", "extensionAttributes", "study_overview",
            "extraction_statistics", "provenance", "contacts", "risks", "benefits", "alternatives",
        ]

        core_study = {key: study.get(key) for key in core_study_fields if key in study}

        # Build final structure
        transformed = {
            "study": core_study,
            "domainSections": domain_sections,
            "agentDocumentation": study.get("agentDocumentation", {}),
            "extractionMetadata": study.get("extractionMetadata", {}),
        }

        logger.info("Successfully transformed USDM data for frontend")
        return transformed
