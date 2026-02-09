"""
Data models for Stage 5: Specimen Enrichment.

Extracts and enriches specimen/biospecimen data from SOA tables and footnotes.
Handles collection, processing, storage, and shipping requirements.

Design principles:
- USDM 4.0 compliant (6-field Code objects, specimenCollection on SAI)
- Full provenance tracking on all generated entities
- Support for visit-dependent volumes and conditional collection
- Integration with activity_components.json for specimen type inference
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
import hashlib
import uuid


# =============================================================================
# ENUMERATIONS
# =============================================================================

class SpecimenCategory(str, Enum):
    """High-level specimen categories."""
    BLOOD = "blood"
    URINE = "urine"
    TISSUE = "tissue"
    CSF = "csf"
    SALIVA = "saliva"
    STOOL = "stool"
    SWAB = "swab"
    BONE_MARROW = "bone_marrow"
    BREATH = "breath"
    SPUTUM = "sputum"
    HAIR = "hair"
    NAIL = "nail"
    OTHER = "other"


class SpecimenSubtype(str, Enum):
    """Subtypes within categories (primarily blood)."""
    # Blood subtypes
    WHOLE_BLOOD = "whole_blood"
    SERUM = "serum"
    PLASMA = "plasma"
    EDTA_PLASMA = "edta_plasma"
    CITRATE_PLASMA = "citrate_plasma"
    LITHIUM_HEPARIN_PLASMA = "lithium_heparin_plasma"
    DRIED_BLOOD_SPOT = "dried_blood_spot"  # DBS for remote monitoring/pediatric
    BUFFY_COAT = "buffy_coat"
    PERIPHERAL_BLOOD_MONONUCLEAR = "pbmc"  # PBMCs for immunology
    # Urine subtypes
    URINE_SPOT = "urine_spot"
    URINE_24H = "urine_24h"
    URINE_FIRST_MORNING = "urine_first_morning"
    URINE_TIMED = "urine_timed"  # Timed collection (e.g., 2-hour, 4-hour)
    # Tissue subtypes
    FRESH_TISSUE = "fresh_tissue"
    FFPE = "ffpe"
    FROZEN_TISSUE = "frozen_tissue"
    CORE_BIOPSY = "core_biopsy"
    FINE_NEEDLE_ASPIRATE = "fine_needle_aspirate"
    # Bone marrow subtypes
    BONE_MARROW_ASPIRATE = "bone_marrow_aspirate"
    BONE_MARROW_BIOPSY = "bone_marrow_biopsy"
    # Swab subtypes
    NASOPHARYNGEAL_SWAB = "nasopharyngeal_swab"
    OROPHARYNGEAL_SWAB = "oropharyngeal_swab"
    BUCCAL_SWAB = "buccal_swab"
    THROAT_SWAB = "throat_swab"
    RECTAL_SWAB = "rectal_swab"
    SKIN_SWAB = "skin_swab"
    WOUND_SWAB = "wound_swab"
    # Respiratory subtypes
    INDUCED_SPUTUM = "induced_sputum"
    BRONCHOALVEOLAR_LAVAGE = "bronchoalveolar_lavage"
    EXHALED_BREATH_CONDENSATE = "exhaled_breath_condensate"


class SpecimenPurpose(str, Enum):
    """Purpose of specimen collection."""
    PK = "pk"
    PD = "pd"
    BIOMARKER = "biomarker"
    SAFETY = "safety"
    EFFICACY = "efficacy"
    EXPLORATORY = "exploratory"
    GENETIC = "genetic"
    IMMUNOGENICITY = "immunogenicity"


class TubeType(str, Enum):
    """Blood collection tube types."""
    EDTA = "edta"
    SST = "sst"
    LITHIUM_HEPARIN = "lithium_heparin"
    SODIUM_HEPARIN = "sodium_heparin"
    SODIUM_CITRATE = "sodium_citrate"
    ACD = "acd"
    CPT = "cpt"
    PAXGENE = "paxgene"
    PLAIN = "plain"
    FLUORIDE_OXALATE = "fluoride_oxalate"


class TubeColor(str, Enum):
    """Tube cap colors."""
    LAVENDER = "lavender"
    PURPLE = "purple"
    RED = "red"
    GOLD = "gold"
    GREEN = "green"
    LIGHT_GREEN = "light_green"
    LIGHT_BLUE = "light_blue"
    GRAY = "gray"
    YELLOW = "yellow"
    TAN = "tan"


class StoragePhase(str, Enum):
    """Storage phase categories."""
    TEMPORARY = "temporary"
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    ARCHIVE = "archive"


class EquipmentType(str, Enum):
    """Storage equipment types."""
    REFRIGERATOR = "refrigerator"
    FREEZER_MINUS20 = "freezer_minus20"
    FREEZER_MINUS80 = "freezer_minus80"
    LIQUID_NITROGEN_VAPOR = "ln2_vapor"
    LIQUID_NITROGEN_LIQUID = "ln2_liquid"


class ShippingCondition(str, Enum):
    """Shipping temperature conditions."""
    DRY_ICE = "dry_ice"
    FROZEN_GEL_PACKS = "frozen_gel_packs"
    COLD_GEL_PACKS = "cold_gel_packs"
    REFRIGERATED = "refrigerated"
    AMBIENT_CONTROLLED = "ambient_controlled"


# =============================================================================
# VOLUME AND MEASUREMENT DATACLASSES
# =============================================================================

@dataclass
class VolumeSpecification:
    """Volume with units and context."""
    value: Optional[float] = None
    unit: str = "mL"
    visit_context: Optional[str] = None  # "Screening", "Week 4", etc.
    population: Optional[str] = None     # "adult", "pediatric"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "unit": self.unit,
            "visitContext": self.visit_context,
            "population": self.population,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VolumeSpecification":
        return cls(
            value=data.get("value"),
            unit=data.get("unit", "mL"),
            visit_context=data.get("visitContext"),
            population=data.get("population"),
        )


@dataclass
class TemperatureRange:
    """Temperature specification with nominal, min, max values."""
    nominal: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    description: Optional[str] = None  # "frozen at -80°C"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nominal": self.nominal,
            "min": self.min,
            "max": self.max,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TemperatureRange":
        return cls(
            nominal=data.get("nominal"),
            min=data.get("min"),
            max=data.get("max"),
            description=data.get("description"),
        )


# =============================================================================
# TUBE AND COLLECTION DATACLASSES
# =============================================================================

@dataclass
class TubeSpecification:
    """Blood collection tube specification."""
    tube_type: Optional[TubeType] = None
    tube_color: Optional[TubeColor] = None
    anticoagulant: Optional[str] = None
    preservative: Optional[str] = None
    volume_capacity: Optional[VolumeSpecification] = None
    fill_volume: Optional[VolumeSpecification] = None
    fill_critical: bool = False  # True for citrate tubes
    special_instructions: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "tubeType": self.tube_type.value if self.tube_type else None,
            "tubeColor": self.tube_color.value if self.tube_color else None,
            "anticoagulant": self.anticoagulant,
            "preservative": self.preservative,
            "fillCritical": self.fill_critical,
            "specialInstructions": self.special_instructions,
        }
        if self.volume_capacity:
            result["volumeCapacity"] = self.volume_capacity.to_dict()
        if self.fill_volume:
            result["fillVolume"] = self.fill_volume.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TubeSpecification":
        tube_type = None
        if data.get("tubeType"):
            try:
                tube_type = TubeType(data["tubeType"].lower())
            except ValueError:
                pass

        tube_color = None
        if data.get("tubeColor"):
            try:
                tube_color = TubeColor(data["tubeColor"].lower())
            except ValueError:
                pass

        return cls(
            tube_type=tube_type,
            tube_color=tube_color,
            anticoagulant=data.get("anticoagulant"),
            preservative=data.get("preservative"),
            volume_capacity=VolumeSpecification.from_dict(data["volumeCapacity"]) if data.get("volumeCapacity") else None,
            fill_volume=VolumeSpecification.from_dict(data["fillVolume"]) if data.get("fillVolume") else None,
            fill_critical=data.get("fillCritical", False),
            special_instructions=data.get("specialInstructions"),
        )


# =============================================================================
# PROCESSING, STORAGE, SHIPPING DATACLASSES
# =============================================================================

@dataclass
class ProcessingRequirement:
    """Specimen processing requirement (single step)."""
    step_name: str = ""
    step_order: int = 0
    description: Optional[str] = None
    centrifuge_speed: Optional[str] = None       # "3000 x g" or "1500 rpm"
    centrifuge_time: Optional[str] = None        # "10 minutes"
    centrifuge_temperature: Optional[str] = None  # "4°C" or "room temperature"
    time_constraint: Optional[str] = None         # "within 30 minutes of collection"
    inversion_count: Optional[str] = None         # "8-10 times"
    clotting_time: Optional[str] = None           # "30 minutes"
    aliquot_count: Optional[int] = None
    aliquot_volume: Optional[VolumeSpecification] = None
    aliquot_container: Optional[str] = None       # "cryovial", "microtube"
    special_instructions: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "stepName": self.step_name,
            "stepOrder": self.step_order,
            "description": self.description,
            "centrifugeSpeed": self.centrifuge_speed,
            "centrifugeTime": self.centrifuge_time,
            "centrifugeTemperature": self.centrifuge_temperature,
            "timeConstraint": self.time_constraint,
            "inversionCount": self.inversion_count,
            "clottingTime": self.clotting_time,
            "aliquotCount": self.aliquot_count,
            "aliquotContainer": self.aliquot_container,
            "specialInstructions": self.special_instructions,
        }
        if self.aliquot_volume:
            result["aliquotVolume"] = self.aliquot_volume.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProcessingRequirement":
        return cls(
            step_name=data.get("stepName", ""),
            step_order=data.get("stepOrder", 0),
            description=data.get("description"),
            centrifuge_speed=data.get("centrifugeSpeed"),
            centrifuge_time=data.get("centrifugeTime"),
            centrifuge_temperature=data.get("centrifugeTemperature"),
            time_constraint=data.get("timeConstraint"),
            inversion_count=data.get("inversionCount"),
            clotting_time=data.get("clottingTime"),
            aliquot_count=data.get("aliquotCount"),
            aliquot_volume=VolumeSpecification.from_dict(data["aliquotVolume"]) if data.get("aliquotVolume") else None,
            aliquot_container=data.get("aliquotContainer"),
            special_instructions=data.get("specialInstructions"),
        )


@dataclass
class StorageRequirement:
    """Specimen storage requirement."""
    storage_phase: Optional[StoragePhase] = None
    temperature: Optional[TemperatureRange] = None
    equipment_type: Optional[EquipmentType] = None
    max_duration: Optional[str] = None           # "48 hours", "1 month"
    stability_limit: Optional[str] = None        # "2 years at -80°C"
    monitoring_requirements: Optional[str] = None
    excursion_limits: Optional[str] = None       # "≤1 hour above -70°C"
    special_instructions: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "storagePhase": self.storage_phase.value if self.storage_phase else None,
            "temperature": self.temperature.to_dict() if self.temperature else None,
            "equipmentType": self.equipment_type.value if self.equipment_type else None,
            "maxDuration": self.max_duration,
            "stabilityLimit": self.stability_limit,
            "monitoringRequirements": self.monitoring_requirements,
            "excursionLimits": self.excursion_limits,
            "specialInstructions": self.special_instructions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StorageRequirement":
        storage_phase = None
        if data.get("storagePhase"):
            try:
                storage_phase = StoragePhase(data["storagePhase"].lower())
            except ValueError:
                pass

        equipment_type = None
        if data.get("equipmentType"):
            try:
                equipment_type = EquipmentType(data["equipmentType"].lower())
            except ValueError:
                pass

        return cls(
            storage_phase=storage_phase,
            temperature=TemperatureRange.from_dict(data["temperature"]) if data.get("temperature") else None,
            equipment_type=equipment_type,
            max_duration=data.get("maxDuration"),
            stability_limit=data.get("stabilityLimit"),
            monitoring_requirements=data.get("monitoringRequirements"),
            excursion_limits=data.get("excursionLimits"),
            special_instructions=data.get("specialInstructions"),
        )


@dataclass
class ShippingRequirement:
    """Specimen shipping requirement."""
    destination: Optional[str] = None             # "Central Lab, Boston MA"
    shipping_frequency: Optional[str] = None      # "weekly on Fridays"
    shipping_condition: Optional[ShippingCondition] = None
    temperature: Optional[TemperatureRange] = None
    packaging_requirements: Optional[str] = None  # "Insulated shipper with dry ice"
    un_classification: Optional[str] = None       # "UN3373"
    courier_requirements: Optional[str] = None
    manifest_requirements: Optional[str] = None
    contingency_procedures: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "destination": self.destination,
            "shippingFrequency": self.shipping_frequency,
            "shippingCondition": self.shipping_condition.value if self.shipping_condition else None,
            "temperature": self.temperature.to_dict() if self.temperature else None,
            "packagingRequirements": self.packaging_requirements,
            "unClassification": self.un_classification,
            "courierRequirements": self.courier_requirements,
            "manifestRequirements": self.manifest_requirements,
            "contingencyProcedures": self.contingency_procedures,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ShippingRequirement":
        shipping_condition = None
        if data.get("shippingCondition"):
            try:
                shipping_condition = ShippingCondition(data["shippingCondition"].lower())
            except ValueError:
                pass

        return cls(
            destination=data.get("destination"),
            shipping_frequency=data.get("shippingFrequency"),
            shipping_condition=shipping_condition,
            temperature=TemperatureRange.from_dict(data["temperature"]) if data.get("temperature") else None,
            packaging_requirements=data.get("packagingRequirements"),
            un_classification=data.get("unClassification"),
            courier_requirements=data.get("courierRequirements"),
            manifest_requirements=data.get("manifestRequirements"),
            contingency_procedures=data.get("contingencyProcedures"),
        )


# =============================================================================
# DECISION AND PROVENANCE DATACLASSES
# =============================================================================

@dataclass
class SpecimenDecision:
    """
    LLM decision for specimen enrichment on an activity.
    This is the object that gets cached.
    """
    activity_id: str = ""
    activity_name: str = ""
    has_specimen: bool = False

    # Specimen identification
    specimen_category: Optional[SpecimenCategory] = None
    specimen_subtype: Optional[SpecimenSubtype] = None
    purpose: Optional[SpecimenPurpose] = None

    # Collection details
    tube_specification: Optional[TubeSpecification] = None
    volumes: List[VolumeSpecification] = field(default_factory=list)
    fasting_required: Optional[bool] = None
    fasting_duration: Optional[str] = None

    # Processing, storage, shipping
    processing: List[ProcessingRequirement] = field(default_factory=list)
    storage: List[StorageRequirement] = field(default_factory=list)
    shipping: Optional[ShippingRequirement] = None

    # Conditional/optional
    is_optional: bool = False
    condition_text: Optional[str] = None  # "Optional: if PK performed"

    # Metadata
    confidence: float = 1.0
    rationale: Optional[str] = None
    source: str = "llm"  # "llm", "cache", "config", "inferred"
    requires_human_review: bool = False
    review_reason: Optional[str] = None
    cached_at: Optional[str] = None
    model_name: Optional[str] = None

    # Provenance
    footnote_markers: List[str] = field(default_factory=list)
    page_numbers: List[int] = field(default_factory=list)
    text_snippets: List[str] = field(default_factory=list)
    section_reference: Optional[str] = None  # Protocol section (e.g., "8.5.1")

    def get_cache_key(self, model_name: str) -> str:
        """Generate cache key including model version for invalidation."""
        normalized = f"{self.activity_name.lower().strip()}:{model_name}"
        return hashlib.md5(normalized.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "activityId": self.activity_id,
            "activityName": self.activity_name,
            "hasSpecimen": self.has_specimen,
            "specimenCategory": self.specimen_category.value if self.specimen_category else None,
            "specimenSubtype": self.specimen_subtype.value if self.specimen_subtype else None,
            "purpose": self.purpose.value if self.purpose else None,
            "tubeSpecification": self.tube_specification.to_dict() if self.tube_specification else None,
            "volumes": [v.to_dict() for v in self.volumes],
            "fastingRequired": self.fasting_required,
            "fastingDuration": self.fasting_duration,
            "processing": [p.to_dict() for p in self.processing],
            "storage": [s.to_dict() for s in self.storage],
            "shipping": self.shipping.to_dict() if self.shipping else None,
            "isOptional": self.is_optional,
            "conditionText": self.condition_text,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "source": self.source,
            "requiresHumanReview": self.requires_human_review,
            "reviewReason": self.review_reason,
            "cachedAt": self.cached_at,
            "modelName": self.model_name,
            "footnoteMarkers": self.footnote_markers,
            "pageNumbers": self.page_numbers,
            "textSnippets": self.text_snippets,
            "sectionReference": self.section_reference,
        }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpecimenDecision":
        """Create from cached dict."""
        # Parse enums safely
        category = None
        if data.get("specimenCategory"):
            try:
                category = SpecimenCategory(data["specimenCategory"].lower())
            except ValueError:
                pass

        subtype = None
        if data.get("specimenSubtype"):
            try:
                subtype = SpecimenSubtype(data["specimenSubtype"].lower())
            except ValueError:
                pass

        purpose = None
        if data.get("purpose"):
            try:
                purpose = SpecimenPurpose(data["purpose"].lower())
            except ValueError:
                pass

        # Parse volumes
        volumes = []
        for v in data.get("volumes", []):
            volumes.append(VolumeSpecification.from_dict(v))

        # Parse processing
        processing = []
        for p in data.get("processing", []):
            processing.append(ProcessingRequirement.from_dict(p))

        # Parse storage
        storage = []
        for s in data.get("storage", []):
            storage.append(StorageRequirement.from_dict(s))

        return cls(
            activity_id=data.get("activityId", ""),
            activity_name=data.get("activityName", ""),
            has_specimen=data.get("hasSpecimen", False),
            specimen_category=category,
            specimen_subtype=subtype,
            purpose=purpose,
            tube_specification=TubeSpecification.from_dict(data["tubeSpecification"]) if data.get("tubeSpecification") else None,
            volumes=volumes,
            fasting_required=data.get("fastingRequired"),
            fasting_duration=data.get("fastingDuration"),
            processing=processing,
            storage=storage,
            shipping=ShippingRequirement.from_dict(data["shipping"]) if data.get("shipping") else None,
            is_optional=data.get("isOptional", False),
            condition_text=data.get("conditionText"),
            confidence=data.get("confidence", 1.0),
            rationale=data.get("rationale"),
            source=data.get("source", "cache"),
            requires_human_review=data.get("requiresHumanReview", False),
            review_reason=data.get("reviewReason"),
            cached_at=data.get("cachedAt"),
            model_name=data.get("modelName"),
            footnote_markers=data.get("footnoteMarkers", []),
            page_numbers=data.get("pageNumbers", []),
            text_snippets=data.get("textSnippets", []),
            section_reference=data.get("sectionReference"),
        )

    @classmethod
    def from_llm_response(
        cls,
        activity_id: str,
        activity_name: str,
        response_data: Dict[str, Any],
        model_name: str
    ) -> "SpecimenDecision":
        """Create from LLM JSON response."""
        # Parse enums safely
        category = None
        if response_data.get("specimenCategory"):
            try:
                category = SpecimenCategory(response_data["specimenCategory"].lower())
            except ValueError:
                pass

        subtype = None
        if response_data.get("specimenSubtype"):
            try:
                subtype = SpecimenSubtype(response_data["specimenSubtype"].lower().replace(" ", "_"))
            except ValueError:
                pass

        purpose = None
        if response_data.get("purpose"):
            try:
                purpose = SpecimenPurpose(response_data["purpose"].lower())
            except ValueError:
                pass

        # Parse volumes
        volumes = []
        for v in response_data.get("volumes", []):
            volumes.append(VolumeSpecification.from_dict(v))

        # Parse tube specification
        tube_spec = None
        if response_data.get("tubeSpecification"):
            tube_spec = TubeSpecification.from_dict(response_data["tubeSpecification"])

        # Parse processing
        processing = []
        for p in response_data.get("processing", []):
            processing.append(ProcessingRequirement.from_dict(p))

        # Parse storage
        storage = []
        for s in response_data.get("storage", []):
            storage.append(StorageRequirement.from_dict(s))

        # Parse shipping
        shipping = None
        if response_data.get("shipping"):
            shipping = ShippingRequirement.from_dict(response_data["shipping"])

        confidence = response_data.get("confidence", 0.8)

        # Extract provenance fields from LLM response
        footnote_markers = response_data.get("footnoteMarkers", [])
        page_numbers = response_data.get("pageNumbers", [])
        text_snippets = response_data.get("textSnippets", [])
        section_reference = response_data.get("sectionReference")

        # Normalize page numbers to integers
        if page_numbers:
            page_numbers = [int(p) if isinstance(p, (int, float, str)) and str(p).isdigit() else p for p in page_numbers]
            page_numbers = [p for p in page_numbers if isinstance(p, int)]

        return cls(
            activity_id=activity_id,
            activity_name=activity_name,
            has_specimen=response_data.get("hasSpecimen", False),
            specimen_category=category,
            specimen_subtype=subtype,
            purpose=purpose,
            tube_specification=tube_spec,
            volumes=volumes,
            fasting_required=response_data.get("fastingRequired"),
            fasting_duration=response_data.get("fastingDuration"),
            processing=processing,
            storage=storage,
            shipping=shipping,
            is_optional=response_data.get("isOptional", False),
            condition_text=response_data.get("conditionText"),
            confidence=confidence,
            rationale=response_data.get("rationale"),
            source="llm",
            requires_human_review=confidence < 0.70,
            review_reason=response_data.get("reviewReason"),
            model_name=model_name,
            cached_at=datetime.utcnow().isoformat() + "Z",
            footnote_markers=footnote_markers,
            page_numbers=page_numbers,
            text_snippets=text_snippets,
            section_reference=section_reference,
        )


@dataclass
class SpecimenProvenance:
    """Full provenance metadata for specimen enrichment."""
    activity_id: str = ""
    activity_name: str = ""
    specimen_category: Optional[str] = None
    stage: str = "Stage5SpecimenEnrichment"
    model: Optional[str] = None
    timestamp: Optional[str] = None
    source: str = "llm"  # "llm", "cache", "config", "inferred"
    cache_hit: bool = False
    cache_key: Optional[str] = None
    confidence: float = 1.0
    rationale: Optional[str] = None
    footnote_markers: List[str] = field(default_factory=list)
    page_numbers: List[int] = field(default_factory=list)
    # New provenance fields for PDF validation
    text_snippets: List[str] = field(default_factory=list)  # Verbatim quotes from PDF
    section_reference: Optional[str] = None  # Protocol section (e.g., "8.5.1")
    pdf_validated: bool = False  # True if PDF was used for validation
    biospecimen_source: bool = False  # True if biospecimen_handling data was used

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activityId": self.activity_id,
            "activityName": self.activity_name,
            "specimenCategory": self.specimen_category,
            "stage": self.stage,
            "model": self.model,
            "timestamp": self.timestamp,
            "source": self.source,
            "cacheHit": self.cache_hit,
            "cacheKey": self.cache_key,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "footnoteMarkers": self.footnote_markers,
            "pageNumbers": self.page_numbers,
            "textSnippets": self.text_snippets,
            "sectionReference": self.section_reference,
            "pdfValidated": self.pdf_validated,
            "biospecimenSource": self.biospecimen_source,
        }


# =============================================================================
# ENRICHMENT OUTPUT DATACLASSES
# =============================================================================

@dataclass
class SpecimenEnrichment:
    """
    Result of enriching an activity with specimen data.
    Contains the specimenCollection object to add to SAI and
    biospecimenRequirements to add to Activity.
    """
    id: str = ""
    activity_id: str = ""
    activity_name: str = ""

    # USDM objects
    specimen_collection: Dict[str, Any] = field(default_factory=dict)
    biospecimen_requirements: Dict[str, Any] = field(default_factory=dict)
    conditions_created: List[Dict[str, Any]] = field(default_factory=list)

    # Source decision
    decision: Optional[SpecimenDecision] = None

    # Metrics
    confidence: float = 1.0
    requires_review: bool = False
    review_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "activityId": self.activity_id,
            "activityName": self.activity_name,
            "specimenCollection": self.specimen_collection,
            "biospecimenRequirements": self.biospecimen_requirements,
            "conditionsCreated": self.conditions_created,
            "confidence": self.confidence,
            "requiresReview": self.requires_review,
            "reviewReason": self.review_reason,
        }


@dataclass
class HumanReviewItem:
    """Item flagged for human review."""
    id: str = ""
    item_type: str = "specimen"
    activity_id: str = ""
    activity_name: str = ""
    title: str = ""
    description: str = ""
    reason: str = ""
    priority: str = "medium"  # "low", "medium", "high"
    confidence: float = 0.0
    proposed_resolution: Optional[Dict[str, Any]] = None
    specimen_options: List[str] = field(default_factory=list)
    context: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "itemType": self.item_type,
            "activityId": self.activity_id,
            "activityName": self.activity_name,
            "title": self.title,
            "description": self.description,
            "reason": self.reason,
            "priority": self.priority,
            "confidence": self.confidence,
            "proposedResolution": self.proposed_resolution,
            "specimenOptions": self.specimen_options,
            "context": self.context,
        }


@dataclass
class ValidationDiscrepancy:
    """Discrepancy found during pattern validation."""
    activity_id: str = ""
    activity_name: str = ""
    field: str = ""
    llm_value: Any = None
    expected_value: Any = None
    severity: str = "warning"  # "info", "warning", "error"
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activityId": self.activity_id,
            "activityName": self.activity_name,
            "field": self.field,
            "llmValue": self.llm_value,
            "expectedValue": self.expected_value,
            "severity": self.severity,
            "message": self.message,
        }


# =============================================================================
# RESULT AND CONFIG DATACLASSES
# =============================================================================

@dataclass
class Stage5Result:
    """Result of Stage 5: Specimen Enrichment."""
    enrichments: List[SpecimenEnrichment] = field(default_factory=list)
    decisions: Dict[str, SpecimenDecision] = field(default_factory=dict)
    review_items: List[HumanReviewItem] = field(default_factory=list)
    discrepancies: List[ValidationDiscrepancy] = field(default_factory=list)

    # Metrics
    activities_analyzed: int = 0
    activities_with_specimens: int = 0
    specimens_enriched: int = 0
    sais_updated: int = 0
    conditions_created: int = 0

    # Source breakdown
    inferred_from_config: int = 0   # From activity_components.json
    inferred_from_loinc: int = 0    # From LOINC display names
    analyzed_by_llm: int = 0        # Required LLM analysis

    # Confidence breakdown
    auto_applied: int = 0           # >= 0.90 confidence
    flagged_for_review: int = 0     # 0.70-0.89 confidence
    needs_review: int = 0           # < 0.70 confidence

    # Complexity metrics
    visit_dependent_volumes: int = 0
    conditional_specimens: int = 0
    with_processing: int = 0
    with_storage: int = 0
    with_shipping: int = 0

    # Cache metrics
    cache_hits: int = 0
    cache_misses: int = 0
    llm_calls: int = 0

    # Validation
    validation_discrepancies: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": 5,
            "stageName": "Specimen Enrichment",
            "success": True,
            "enrichments": [e.to_dict() for e in self.enrichments],
            "decisions": {k: v.to_dict() for k, v in self.decisions.items()},
            "reviewItems": [item.to_dict() for item in self.review_items],
            "discrepancies": [d.to_dict() for d in self.discrepancies],
            "metrics": {
                "activitiesAnalyzed": self.activities_analyzed,
                "activitiesWithSpecimens": self.activities_with_specimens,
                "specimensEnriched": self.specimens_enriched,
                "saisUpdated": self.sais_updated,
                "conditionsCreated": self.conditions_created,
                "inferredFromConfig": self.inferred_from_config,
                "inferredFromLoinc": self.inferred_from_loinc,
                "analyzedByLlm": self.analyzed_by_llm,
                "autoApplied": self.auto_applied,
                "flaggedForReview": self.flagged_for_review,
                "needsReview": self.needs_review,
                "visitDependentVolumes": self.visit_dependent_volumes,
                "conditionalSpecimens": self.conditional_specimens,
                "withProcessing": self.with_processing,
                "withStorage": self.with_storage,
                "withShipping": self.with_shipping,
                "cacheHits": self.cache_hits,
                "cacheMisses": self.cache_misses,
                "llmCalls": self.llm_calls,
                "validationDiscrepancies": self.validation_discrepancies,
            },
        }

    def add_enrichment(self, enrichment: SpecimenEnrichment) -> None:
        """Add enrichment and update metrics."""
        self.enrichments.append(enrichment)
        self.specimens_enriched += 1
        self.conditions_created += len(enrichment.conditions_created)

        if enrichment.requires_review:
            self.needs_review += 1
        elif enrichment.confidence >= 0.90:
            self.auto_applied += 1
        else:
            self.flagged_for_review += 1


@dataclass
class SpecimenEnrichmentConfig:
    """Configuration for Stage 5: Specimen Enrichment."""
    # Confidence thresholds
    confidence_threshold_auto: float = 0.90
    confidence_threshold_review: float = 0.70

    # Feature flags
    infer_from_activity_components: bool = True
    infer_from_loinc: bool = True
    extract_tube_specifications: bool = True
    extract_processing_requirements: bool = True
    extract_storage_requirements: bool = True
    extract_shipping_requirements: bool = True
    create_conditions_for_optional: bool = True
    handle_visit_dependent_volumes: bool = True
    validate_against_patterns: bool = True

    # LLM settings
    model_name: str = "gemini-2.5-pro"
    azure_model_name: str = "gpt-5-mini"
    timeout_seconds: int = 120
    max_retries: int = 3
    max_output_tokens: int = 8192
    temperature: float = 0.1

    # Batch settings
    max_batch_size: int = 25

    # Cache settings
    use_cache: bool = True
    cache_ttl_hours: int = 168  # 1 week

    def to_dict(self) -> Dict[str, Any]:
        return {
            "confidenceThresholdAuto": self.confidence_threshold_auto,
            "confidenceThresholdReview": self.confidence_threshold_review,
            "inferFromActivityComponents": self.infer_from_activity_components,
            "inferFromLoinc": self.infer_from_loinc,
            "extractTubeSpecifications": self.extract_tube_specifications,
            "extractProcessingRequirements": self.extract_processing_requirements,
            "extractStorageRequirements": self.extract_storage_requirements,
            "extractShippingRequirements": self.extract_shipping_requirements,
            "createConditionsForOptional": self.create_conditions_for_optional,
            "handleVisitDependentVolumes": self.handle_visit_dependent_volumes,
            "validateAgainstPatterns": self.validate_against_patterns,
            "modelName": self.model_name,
            "azureModelName": self.azure_model_name,
            "timeoutSeconds": self.timeout_seconds,
            "maxRetries": self.max_retries,
            "maxOutputTokens": self.max_output_tokens,
            "temperature": self.temperature,
            "maxBatchSize": self.max_batch_size,
            "useCache": self.use_cache,
            "cacheTtlHours": self.cache_ttl_hours,
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def infer_specimen_from_activity_name(activity_name: str) -> Optional[SpecimenCategory]:
    """Infer specimen category from activity name using keywords."""
    name_lower = activity_name.lower()

    # Blood specimens - expanded to capture common clinical tests
    blood_keywords = [
        # Core lab terms
        "hematology", "cbc", "blood count", "chemistry", "serum",
        "plasma", "coagulation", "lipid", "liver function", "lft",
        "electrolytes", "hemoglobin", "hba1c", "glucose", "creatinine",
        # PK/PD/Biomarker
        "pk sample", "pd sample", "pk sampling", "pharmacokinetic",
        "pharmacodynamic", "biomarker",
        # Immunogenicity/ADA
        "immunogenicity", "ada sample", "ada ", "anti-drug antibody",
        # Infectious disease screening
        "hiv", "hepatitis", "hbv", "hcv", "covid",
        # Pregnancy
        "pregnancy test", "hcg", "bhcg", "beta-hcg",
        # Genetic/Genomic
        "pharmacogenomic", "pharmacogenomics", "pgx", "genotyping",
        "cfdna", "cf-dna", "cfdna", "ctdna", "wes", "wgs",
        "whole exome", "whole genome", "dna sample", "rna sample",
        # General blood indicators
        "blood sample", "blood draw", "venipuncture",
    ]
    if any(kw in name_lower for kw in blood_keywords):
        return SpecimenCategory.BLOOD

    # Urine specimens
    urine_keywords = ["urinalysis", "urine", "ua ", "urine culture", "urine sample"]
    if any(kw in name_lower for kw in urine_keywords):
        return SpecimenCategory.URINE

    # Swab specimens (nasal, nasopharyngeal, etc.)
    swab_keywords = ["swab", "nasal", "nasopharyngeal", "oropharyngeal", "throat swab"]
    if any(kw in name_lower for kw in swab_keywords):
        return SpecimenCategory.OTHER

    # Tissue specimens
    tissue_keywords = ["biopsy", "tissue", "tumor sample", "ffpe", "core biopsy", "needle biopsy"]
    if any(kw in name_lower for kw in tissue_keywords):
        return SpecimenCategory.TISSUE

    # CSF specimens
    csf_keywords = ["csf", "cerebrospinal fluid", "lumbar puncture", "spinal tap"]
    if any(kw in name_lower for kw in csf_keywords):
        return SpecimenCategory.CSF

    # Stool/feces specimens
    stool_keywords = ["stool", "feces", "fecal"]
    if any(kw in name_lower for kw in stool_keywords):
        return SpecimenCategory.OTHER

    return None


def infer_subtype_from_panel(panel_name: str) -> Optional[SpecimenSubtype]:
    """Infer specimen subtype from laboratory panel name."""
    panel_lower = panel_name.lower()

    if "hematology" in panel_lower or "cbc" in panel_lower or "differential" in panel_lower:
        return SpecimenSubtype.WHOLE_BLOOD
    elif "coagulation" in panel_lower or "coag" in panel_lower or "pt/inr" in panel_lower:
        return SpecimenSubtype.CITRATE_PLASMA
    elif "chemistry" in panel_lower or "serum" in panel_lower or "liver" in panel_lower or "renal" in panel_lower:
        return SpecimenSubtype.SERUM
    elif "plasma" in panel_lower and "pk" in panel_lower:
        return SpecimenSubtype.EDTA_PLASMA
    elif "plasma" in panel_lower:
        return SpecimenSubtype.PLASMA
    elif "urine" in panel_lower or "urinalysis" in panel_lower:
        return SpecimenSubtype.URINE_SPOT

    return None


def generate_specimen_collection_id(activity_id: str) -> str:
    """Generate deterministic specimen collection ID."""
    return f"SPEC-{activity_id.replace('ACT-', '')}"


def generate_condition_id(activity_id: str, condition_type: str) -> str:
    """Generate deterministic Condition ID for optional specimen."""
    suffix = hashlib.md5(f"{activity_id}:{condition_type}".encode()).hexdigest()[:6].upper()
    return f"COND-SPEC-{suffix}"


def generate_code_id(prefix: str, code: str) -> str:
    """Generate deterministic Code ID."""
    return f"CODE-{prefix}-{code}"


def generate_review_id() -> str:
    """Generate unique review item ID."""
    return f"REVIEW-SPEC-{uuid.uuid4().hex[:8].upper()}"
