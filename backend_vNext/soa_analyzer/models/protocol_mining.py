"""
Stage 9: Protocol Mining - Data Models

Cross-reference non-SOA protocol sections (18 extraction modules) to enrich SOA activities
with laboratory specifications, PK/PD parameters, safety requirements, biospecimen details,
endpoint linkages, oncology imaging/tumor assessments, and dose modification rules.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import json


class EnrichmentType(str, Enum):
    """Types of enrichment from protocol mining"""
    LAB_MANUAL = "lab_manual"
    PK_PD = "pk_pd"
    SAFETY = "safety"
    BIOSPECIMEN = "biospecimen"
    ENDPOINT = "endpoint"
    IMAGING = "imaging"           # ONCOLOGY: RECIST, tumor assessments, BICR
    DOSE_MODIFICATION = "dose_modification"  # ONCOLOGY: DLT, dose adjustments


class SourceModule(str, Enum):
    """18 extraction modules available for mining (including oncology-specific)"""
    # Core modules
    LABORATORY_SPECIFICATIONS = "laboratory_specifications"
    PKPD_SAMPLING = "pkpd_sampling"
    BIOSPECIMEN_HANDLING = "biospecimen_handling"
    ADVERSE_EVENTS = "adverse_events"
    SAE_REPORTING = "sae_reporting"
    ENDPOINTS_ESTIMANDS = "endpoints_estimands"
    SAFETY_MONITORING = "safety_monitoring"
    CONCOMITANT_MEDICATIONS = "concomitant_medications"
    INVESTIGATIONAL_PRODUCT = "investigational_product"
    STUDY_METADATA = "study_metadata"
    ARMS_DESIGN = "arms_design"
    ELIGIBILITY_CRITERIA = "eligibility_criteria"
    VISIT_SCHEDULE = "visit_schedule"
    DATA_MANAGEMENT = "data_management"
    SITE_OPERATIONS = "site_operations"
    # Oncology-specific modules
    IMAGING_CENTRAL_READING = "imaging_central_reading"  # RECIST, tumor assessments, BICR
    DOSE_MODIFICATIONS = "dose_modifications"            # DLT, dose adjustments
    PRO_SPECIFICATIONS = "pro_specifications"            # Patient-reported outcomes (QoL)


class MatchConfidence(str, Enum):
    """Confidence levels for activity-module matching"""
    HIGH = "high"      # ≥0.90 - Auto-apply
    MEDIUM = "medium"  # 0.70-0.89 - Apply + flag
    LOW = "low"        # <0.70 - Requires review


@dataclass
class MiningProvenance:
    """Tracks source of each enrichment"""
    source_module: str  # Module name as string for JSON serialization
    field_path: str  # e.g., "labTests[0].specimenType"
    page_numbers: List[int] = field(default_factory=list)
    text_snippets: List[str] = field(default_factory=list)
    extraction_timestamp: str = ""
    model_used: str = ""

    def __post_init__(self):
        if not self.extraction_timestamp:
            self.extraction_timestamp = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sourceModule": self.source_module,
            "fieldPath": self.field_path,
            "pageNumbers": self.page_numbers,
            "textSnippets": self.text_snippets,
            "extractionTimestamp": self.extraction_timestamp,
            "modelUsed": self.model_used
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MiningProvenance":
        return cls(
            source_module=data.get("sourceModule", ""),
            field_path=data.get("fieldPath", ""),
            page_numbers=data.get("pageNumbers", []),
            text_snippets=data.get("textSnippets", []),
            extraction_timestamp=data.get("extractionTimestamp", ""),
            model_used=data.get("modelUsed", "")
        )


@dataclass
class MiningDecision:
    """Cached LLM decision for activity matching"""
    activity_id: str
    activity_name: str
    domain: Optional[str] = None
    matched_modules: List[str] = field(default_factory=list)
    match_rationale: Dict[str, str] = field(default_factory=dict)  # module -> why matched
    confidence: float = 0.0
    source: str = "llm"  # "llm", "cache", "config"
    requires_human_review: bool = False
    cache_key: str = ""
    model_used: str = ""
    timestamp: str = ""
    pdf_validation: Optional[Dict[str, Any]] = None  # PDF validation results from Phase 2.5

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"
        if not self.cache_key:
            self.cache_key = self.generate_cache_key()

    def generate_cache_key(self) -> str:
        """Generate MD5 cache key from activity_id + activity_name + model"""
        key_str = f"{self.activity_id}:{self.activity_name}:{self.model_used}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get_confidence_level(self) -> MatchConfidence:
        """Get confidence level enum from numeric confidence"""
        if self.confidence >= 0.90:
            return MatchConfidence.HIGH
        elif self.confidence >= 0.70:
            return MatchConfidence.MEDIUM
        return MatchConfidence.LOW

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "activityId": self.activity_id,
            "activityName": self.activity_name,
            "domain": self.domain,
            "matchedModules": self.matched_modules,
            "matchRationale": self.match_rationale,
            "confidence": self.confidence,
            "source": self.source,
            "requiresHumanReview": self.requires_human_review,
            "cacheKey": self.cache_key,
            "modelUsed": self.model_used,
            "timestamp": self.timestamp
        }
        if self.pdf_validation:
            result["pdfValidation"] = self.pdf_validation
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MiningDecision":
        return cls(
            activity_id=data.get("activityId", ""),
            activity_name=data.get("activityName", ""),
            domain=data.get("domain"),
            matched_modules=data.get("matchedModules", []),
            match_rationale=data.get("matchRationale", {}),
            confidence=data.get("confidence", 0.0),
            source=data.get("source", "llm"),
            requires_human_review=data.get("requiresHumanReview", False),
            cache_key=data.get("cacheKey", ""),
            model_used=data.get("modelUsed", ""),
            timestamp=data.get("timestamp", ""),
            pdf_validation=data.get("pdfValidation"),
        )

    @classmethod
    def from_llm_response(
        cls,
        response_data: Dict[str, Any],
        activity: Dict[str, Any],
        model_used: str
    ) -> "MiningDecision":
        """Create MiningDecision from LLM response"""
        matched_modules = []
        match_rationale = {}
        max_confidence = 0.0

        for match in response_data.get("matched_modules", []):
            module = match.get("module", "")
            confidence = match.get("confidence", 0.0)
            rationale = match.get("rationale", "")

            if module:
                matched_modules.append(module)
                match_rationale[module] = rationale
                max_confidence = max(max_confidence, confidence)

        # Use average confidence if multiple matches
        if len(response_data.get("matched_modules", [])) > 1:
            total_confidence = sum(m.get("confidence", 0.0) for m in response_data.get("matched_modules", []))
            avg_confidence = total_confidence / len(response_data.get("matched_modules", []))
            max_confidence = avg_confidence

        decision = cls(
            activity_id=activity.get("id", ""),
            activity_name=activity.get("activityName", activity.get("name", "")),
            domain=activity.get("domain"),
            matched_modules=matched_modules,
            match_rationale=match_rationale,
            confidence=max_confidence,
            source="llm",
            requires_human_review=max_confidence < 0.70,
            model_used=model_used
        )

        return decision


# ============ CORE ENRICHMENT DATACLASSES ============

@dataclass
class LabManualEnrichment:
    """Enrichment from laboratory_specifications module"""
    lab_test_name: Optional[str] = None
    test_code: Optional[str] = None
    loinc_code: Optional[str] = None
    specimen_type: Optional[str] = None
    collection_requirements: Optional[str] = None
    processing_instructions: Optional[str] = None
    stability_requirements: Optional[str] = None
    tube_type: Optional[str] = None
    sample_volume: Optional[str] = None
    fasting_required: Optional[bool] = None
    reference_ranges: Optional[Dict[str, Any]] = None
    central_lab_name: Optional[str] = None
    provenance: List[MiningProvenance] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "labTestName": self.lab_test_name,
            "testCode": self.test_code,
            "loincCode": self.loinc_code,
            "specimenType": self.specimen_type,
            "collectionRequirements": self.collection_requirements,
            "processingInstructions": self.processing_instructions,
            "stabilityRequirements": self.stability_requirements,
            "tubeType": self.tube_type,
            "sampleVolume": self.sample_volume,
            "fastingRequired": self.fasting_required,
            "referenceRanges": self.reference_ranges,
            "centralLabName": self.central_lab_name,
            "provenance": [p.to_dict() for p in self.provenance]
        }


@dataclass
class PKPDEnrichment:
    """Enrichment from pkpd_sampling module"""
    analyte_name: Optional[str] = None
    analyte_type: Optional[str] = None
    sampling_timepoints: List[str] = field(default_factory=list)
    sampling_windows: Optional[str] = None
    sample_volume_ml: Optional[float] = None
    sample_matrix: Optional[str] = None
    processing_requirements: Optional[str] = None
    storage_conditions: Optional[str] = None
    bioanalytical_method: Optional[str] = None
    pk_parameters: List[str] = field(default_factory=list)  # e.g., ["Cmax", "AUC", "Tmax"]
    pd_markers: List[str] = field(default_factory=list)
    immunogenicity_sampling: Optional[bool] = None
    provenance: List[MiningProvenance] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analyteName": self.analyte_name,
            "analyteType": self.analyte_type,
            "samplingTimepoints": self.sampling_timepoints,
            "samplingWindows": self.sampling_windows,
            "sampleVolumeMl": self.sample_volume_ml,
            "sampleMatrix": self.sample_matrix,
            "processingRequirements": self.processing_requirements,
            "storageConditions": self.storage_conditions,
            "bioanalyticalMethod": self.bioanalytical_method,
            "pkParameters": self.pk_parameters,
            "pdMarkers": self.pd_markers,
            "immunogenicitySampling": self.immunogenicity_sampling,
            "provenance": [p.to_dict() for p in self.provenance]
        }


@dataclass
class SafetyEnrichment:
    """Enrichment from adverse_events/sae_reporting modules"""
    safety_assessment_type: Optional[str] = None  # e.g., "CTCAE v5.0"
    grading_system_version: Optional[str] = None
    reporting_period: Optional[str] = None
    related_aes: List[str] = field(default_factory=list)  # AE terms linked to this activity
    aesi_terms: List[str] = field(default_factory=list)  # AEs of special interest
    monitoring_requirements: Optional[str] = None
    dose_modification_triggers: List[str] = field(default_factory=list)
    causality_categories: List[str] = field(default_factory=list)
    provenance: List[MiningProvenance] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "safetyAssessmentType": self.safety_assessment_type,
            "gradingSystemVersion": self.grading_system_version,
            "reportingPeriod": self.reporting_period,
            "relatedAEs": self.related_aes,
            "aesiTerms": self.aesi_terms,
            "monitoringRequirements": self.monitoring_requirements,
            "doseModificationTriggers": self.dose_modification_triggers,
            "causalityCategories": self.causality_categories,
            "provenance": [p.to_dict() for p in self.provenance]
        }


@dataclass
class BiospecimenEnrichment:
    """Enrichment from biospecimen_handling module"""
    biobank_consent_required: Optional[bool] = None
    consent_type: Optional[str] = None
    short_term_storage: Optional[str] = None
    long_term_storage_conditions: Optional[str] = None
    future_research_uses: List[str] = field(default_factory=list)
    genetic_testing_included: Optional[bool] = None
    genetic_consent_required: Optional[bool] = None
    retention_period: Optional[str] = None
    destruction_policy: Optional[str] = None
    shipping_requirements: Optional[str] = None
    provenance: List[MiningProvenance] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "biobankConsentRequired": self.biobank_consent_required,
            "consentType": self.consent_type,
            "shortTermStorage": self.short_term_storage,
            "longTermStorageConditions": self.long_term_storage_conditions,
            "futureResearchUses": self.future_research_uses,
            "geneticTestingIncluded": self.genetic_testing_included,
            "geneticConsentRequired": self.genetic_consent_required,
            "retentionPeriod": self.retention_period,
            "destructionPolicy": self.destruction_policy,
            "shippingRequirements": self.shipping_requirements,
            "provenance": [p.to_dict() for p in self.provenance]
        }


@dataclass
class EndpointEnrichment:
    """Enrichment from endpoints_estimands module"""
    related_endpoints: List[str] = field(default_factory=list)
    endpoint_type: Optional[str] = None  # "primary", "secondary", "exploratory"
    linked_objective: Optional[str] = None
    measurement_method: Optional[str] = None
    estimand_strategy: Optional[str] = None
    intercurrent_events: List[str] = field(default_factory=list)
    analysis_population: Optional[str] = None
    assessment_timing: Optional[str] = None
    provenance: List[MiningProvenance] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relatedEndpoints": self.related_endpoints,
            "endpointType": self.endpoint_type,
            "linkedObjective": self.linked_objective,
            "measurementMethod": self.measurement_method,
            "estimandStrategy": self.estimand_strategy,
            "intercurrentEvents": self.intercurrent_events,
            "analysisPopulation": self.analysis_population,
            "assessmentTiming": self.assessment_timing,
            "provenance": [p.to_dict() for p in self.provenance]
        }


# ============ ONCOLOGY-SPECIFIC ENRICHMENTS ============

@dataclass
class ImagingEnrichment:
    """Enrichment from imaging_central_reading module (ONCOLOGY)"""
    # Response criteria (RECIST 1.1, iRECIST, mRECIST, Lugano, RANO)
    response_criteria: Optional[str] = None  # e.g., "RECIST 1.1"
    criteria_version: Optional[str] = None   # e.g., "1.1"
    secondary_criteria: List[str] = field(default_factory=list)
    criteria_modifications: Optional[str] = None
    immune_related_criteria: Optional[bool] = None  # iRECIST used
    # Imaging modalities
    imaging_modality: Optional[str] = None   # CT, MRI, PET, PET-CT
    body_regions: List[str] = field(default_factory=list)  # chest, abdomen, brain, whole body
    contrast_required: Optional[bool] = None
    contrast_type: Optional[str] = None
    slice_thickness: Optional[str] = None
    technical_requirements: Optional[str] = None
    # Assessment schedule
    baseline_window: Optional[str] = None    # e.g., "within 28 days prior to first dose"
    assessment_frequency: Optional[str] = None  # e.g., "every 6 weeks"
    first_assessment_timing: Optional[str] = None
    post_treatment_schedule: Optional[str] = None
    confirmatory_scan_required: Optional[bool] = None
    confirmatory_scan_window: Optional[str] = None
    # Lesion criteria
    measurable_disease_definition: Optional[str] = None
    target_lesion_criteria: Optional[str] = None  # e.g., "≥10mm longest diameter"
    lymph_node_criteria: Optional[str] = None
    max_target_lesions: Optional[int] = None      # typically 5
    max_target_lesions_per_organ: Optional[int] = None
    non_target_lesion_definition: Optional[str] = None
    # Central reading (BICR)
    bicr_required: Optional[bool] = None
    bicr_purpose: Optional[str] = None
    bicr_vendor: Optional[str] = None
    reading_methodology: Optional[str] = None  # single reader, dual reader with adjudication
    reader_qualifications: Optional[str] = None
    blinding_requirements: Optional[str] = None
    adjudication_process: Optional[str] = None
    turnaround_time: Optional[str] = None
    # Response categories
    response_categories: List[str] = field(default_factory=list)  # ["CR", "PR", "SD", "PD", "NE"]
    # Immune-related
    pseudoprogression_handling: Optional[str] = None
    treatment_beyond_progression: Optional[str] = None
    provenance: List[MiningProvenance] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "responseCriteria": self.response_criteria,
            "criteriaVersion": self.criteria_version,
            "secondaryCriteria": self.secondary_criteria,
            "criteriaModifications": self.criteria_modifications,
            "immuneRelatedCriteria": self.immune_related_criteria,
            "imagingModality": self.imaging_modality,
            "bodyRegions": self.body_regions,
            "contrastRequired": self.contrast_required,
            "contrastType": self.contrast_type,
            "sliceThickness": self.slice_thickness,
            "technicalRequirements": self.technical_requirements,
            "baselineWindow": self.baseline_window,
            "assessmentFrequency": self.assessment_frequency,
            "firstAssessmentTiming": self.first_assessment_timing,
            "postTreatmentSchedule": self.post_treatment_schedule,
            "confirmatoryRequired": self.confirmatory_scan_required,
            "confirmatoryWindow": self.confirmatory_scan_window,
            "measurableDiseaseDefinition": self.measurable_disease_definition,
            "targetLesionCriteria": self.target_lesion_criteria,
            "lymphNodeCriteria": self.lymph_node_criteria,
            "maxTargetLesions": self.max_target_lesions,
            "maxTargetLesionsPerOrgan": self.max_target_lesions_per_organ,
            "nonTargetLesionDefinition": self.non_target_lesion_definition,
            "bicrRequired": self.bicr_required,
            "bicrPurpose": self.bicr_purpose,
            "bicrVendor": self.bicr_vendor,
            "readingMethodology": self.reading_methodology,
            "readerQualifications": self.reader_qualifications,
            "blindingRequirements": self.blinding_requirements,
            "adjudicationProcess": self.adjudication_process,
            "turnaroundTime": self.turnaround_time,
            "responseCategories": self.response_categories,
            "pseudoprogressionHandling": self.pseudoprogression_handling,
            "treatmentBeyondProgression": self.treatment_beyond_progression,
            "provenance": [p.to_dict() for p in self.provenance]
        }


@dataclass
class DoseModificationEnrichment:
    """Enrichment from dose_modifications module (ONCOLOGY)"""
    # DLT criteria (Dose Limiting Toxicity)
    dlt_definition: Optional[str] = None
    dlt_evaluation_period: Optional[str] = None  # e.g., "Cycle 1 (28 days)"
    dlt_criteria: List[str] = field(default_factory=list)  # List of DLT-qualifying events
    non_dlt_exceptions: List[str] = field(default_factory=list)
    # Dose reduction rules
    starting_dose: Optional[str] = None
    dose_reduction_levels: List[Dict[str, str]] = field(default_factory=list)  # e.g., [{"level": "-1", "dose": "80mg"}]
    dose_reduction_triggers: List[str] = field(default_factory=list)  # AE grades/types triggering reduction
    max_dose_reductions: Optional[int] = None
    # Dose delay rules
    dose_delay_criteria: Optional[str] = None
    max_delay_duration: Optional[str] = None
    recovery_requirements: Optional[str] = None
    # Treatment discontinuation
    discontinuation_criteria: List[str] = field(default_factory=list)
    permanent_discontinuation_criteria: List[str] = field(default_factory=list)
    # Dose re-escalation
    re_escalation_allowed: Optional[bool] = None
    re_escalation_criteria: Optional[str] = None
    re_escalation_conditions: Optional[str] = None
    # Supportive care
    gcsf_allowed: Optional[bool] = None
    supportive_care_notes: Optional[str] = None
    provenance: List[MiningProvenance] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dltDefinition": self.dlt_definition,
            "dltEvaluationPeriod": self.dlt_evaluation_period,
            "dltCriteria": self.dlt_criteria,
            "nonDltExceptions": self.non_dlt_exceptions,
            "startingDose": self.starting_dose,
            "doseReductionLevels": self.dose_reduction_levels,
            "doseReductionTriggers": self.dose_reduction_triggers,
            "maxDoseReductions": self.max_dose_reductions,
            "doseDelayCriteria": self.dose_delay_criteria,
            "maxDelayDuration": self.max_delay_duration,
            "recoveryRequirements": self.recovery_requirements,
            "discontinuationCriteria": self.discontinuation_criteria,
            "permanentDiscontinuationCriteria": self.permanent_discontinuation_criteria,
            "reEscalationAllowed": self.re_escalation_allowed,
            "reEscalationCriteria": self.re_escalation_criteria,
            "reEscalationConditions": self.re_escalation_conditions,
            "gcsfAllowed": self.gcsf_allowed,
            "supportiveCareNotes": self.supportive_care_notes,
            "provenance": [p.to_dict() for p in self.provenance]
        }


# ============ COMPOSITE ENRICHMENT ============

@dataclass
class MiningEnrichment:
    """Complete enrichment for one activity"""
    id: str
    activity_id: str
    activity_name: str
    # Core enrichments
    lab_manual_enrichment: Optional[LabManualEnrichment] = None
    pkpd_enrichment: Optional[PKPDEnrichment] = None
    safety_enrichment: Optional[SafetyEnrichment] = None
    biospecimen_enrichment: Optional[BiospecimenEnrichment] = None
    endpoint_enrichment: Optional[EndpointEnrichment] = None
    # Oncology-specific enrichments
    imaging_enrichment: Optional[ImagingEnrichment] = None
    dose_modification_enrichment: Optional[DoseModificationEnrichment] = None
    # Metadata
    overall_confidence: float = 0.0
    sources_used: List[str] = field(default_factory=list)
    requires_human_review: bool = False
    _mining_metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self._mining_metadata:
            self._mining_metadata = {
                "stage": "Stage9ProtocolMining",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

    def get_enrichment_types(self) -> List[EnrichmentType]:
        """Get list of enrichment types present"""
        types = []
        if self.lab_manual_enrichment:
            types.append(EnrichmentType.LAB_MANUAL)
        if self.pkpd_enrichment:
            types.append(EnrichmentType.PK_PD)
        if self.safety_enrichment:
            types.append(EnrichmentType.SAFETY)
        if self.biospecimen_enrichment:
            types.append(EnrichmentType.BIOSPECIMEN)
        if self.endpoint_enrichment:
            types.append(EnrichmentType.ENDPOINT)
        if self.imaging_enrichment:
            types.append(EnrichmentType.IMAGING)
        if self.dose_modification_enrichment:
            types.append(EnrichmentType.DOSE_MODIFICATION)
        return types

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "activityId": self.activity_id,
            "activityName": self.activity_name,
            "stage": self._mining_metadata.get("stage", "Stage9ProtocolMining"),
            "timestamp": self._mining_metadata.get("timestamp", ""),
            "overallConfidence": self.overall_confidence,
            "sourcesUsed": self.sources_used,
            "requiresHumanReview": self.requires_human_review
        }

        if self.lab_manual_enrichment:
            result["labManualEnrichment"] = self.lab_manual_enrichment.to_dict()
        if self.pkpd_enrichment:
            result["pkpdEnrichment"] = self.pkpd_enrichment.to_dict()
        if self.safety_enrichment:
            result["safetyEnrichment"] = self.safety_enrichment.to_dict()
        if self.biospecimen_enrichment:
            result["biospecimenEnrichment"] = self.biospecimen_enrichment.to_dict()
        if self.endpoint_enrichment:
            result["endpointEnrichment"] = self.endpoint_enrichment.to_dict()
        if self.imaging_enrichment:
            result["imagingEnrichment"] = self.imaging_enrichment.to_dict()
        if self.dose_modification_enrichment:
            result["doseModificationEnrichment"] = self.dose_modification_enrichment.to_dict()

        return result


# ============ PIPELINE RESULT ============

@dataclass
class Stage9Result:
    """Pipeline result from protocol mining"""
    enrichments: List[MiningEnrichment] = field(default_factory=list)
    decisions: Dict[str, MiningDecision] = field(default_factory=dict)  # activity_id -> decision
    review_items: List[Dict[str, Any]] = field(default_factory=list)
    # Metrics
    total_activities_processed: int = 0
    activities_enriched: int = 0
    activities_no_match: int = 0
    modules_used: Dict[str, int] = field(default_factory=dict)  # module -> count
    cache_hits: int = 0
    llm_calls: int = 0
    pdf_validations: int = 0  # Count of PDF validations performed (Phase 2.5)
    avg_confidence: float = 0.0
    processing_time_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics"""
        return {
            "totalActivitiesProcessed": self.total_activities_processed,
            "activitiesEnriched": self.activities_enriched,
            "activitiesNoMatch": self.activities_no_match,
            "modulesUsed": self.modules_used,
            "cacheHits": self.cache_hits,
            "llmCalls": self.llm_calls,
            "pdfValidations": self.pdf_validations,
            "avgConfidence": round(self.avg_confidence, 3),
            "processingTimeSeconds": round(self.processing_time_seconds, 2),
            "errorCount": len(self.errors),
            "reviewItemCount": len(self.review_items)
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": 9,
            "stageName": "Protocol Mining",
            "success": len(self.errors) == 0,
            "enrichments": [e.to_dict() for e in self.enrichments],
            "decisions": {k: v.to_dict() for k, v in self.decisions.items()},
            "reviewItems": self.review_items,
            "metrics": self.get_summary(),
            "errors": self.errors,
        }


# ============ CONFIGURATION ============

@dataclass
class Stage9Config:
    """Configuration for protocol mining"""
    confidence_threshold_auto: float = 0.90
    confidence_threshold_review: float = 0.70
    batch_size: int = 25
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    model_name: str = "gemini-2.5-pro"
    fallback_model: str = "gpt-5-mini"
    use_cache: bool = True
    cache_file: str = "protocol_mining_cache.json"
    max_output_tokens: int = 65536
    temperature: float = 0.1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "confidenceThresholdAuto": self.confidence_threshold_auto,
            "confidenceThresholdReview": self.confidence_threshold_review,
            "batchSize": self.batch_size,
            "maxRetries": self.max_retries,
            "retryDelaySeconds": self.retry_delay_seconds,
            "modelName": self.model_name,
            "fallbackModel": self.fallback_model,
            "useCache": self.use_cache,
            "cacheFile": self.cache_file,
            "maxOutputTokens": self.max_output_tokens,
            "temperature": self.temperature
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Stage9Config":
        return cls(
            confidence_threshold_auto=data.get("confidenceThresholdAuto", 0.90),
            confidence_threshold_review=data.get("confidenceThresholdReview", 0.70),
            batch_size=data.get("batchSize", 25),
            max_retries=data.get("maxRetries", 3),
            retry_delay_seconds=data.get("retryDelaySeconds", 1.0),
            model_name=data.get("modelName", "gemini-2.5-pro"),
            fallback_model=data.get("fallbackModel", "gpt-5-mini"),
            use_cache=data.get("useCache", True),
            cache_file=data.get("cacheFile", "protocol_mining_cache.json"),
            max_output_tokens=data.get("maxOutputTokens", 65536),
            temperature=data.get("temperature", 0.1)
        )
