"""
V2 Patient Funnel Builder.

Creates queryable funnel output by integrating:
- Stage 2: Atomic decomposition with expression trees
- Stage 5: OMOP concept mappings
- Stage 6: SQL templates
- OMOP→FHIR bridge for FHIR query generation

The output enables external UX to:
1. Import JSON with atomic criteria
2. Connect to OMOP CDM or FHIR server
3. Drag-and-drop criteria execution
4. Build patient funnel incrementally with correct boolean logic
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple
from enum import Enum

from .omop_fhir_bridge import OmopFhirBridge, FhirQuerySpec, FhirCode
from .llm_atomic_matcher import LLMAtomicMatcher
from ..services.llm_reflection import LLMReflectionService, TABLES_WITH_VALUE_COLUMN
from ..config import load_config

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class GroupLogic(str, Enum):
    """Logic within a group of criteria."""
    AND = "AND"
    OR = "OR"


class CombineLogic(str, Enum):
    """How to combine with previous results."""
    AND = "AND"  # INTERSECT
    OR = "OR"    # UNION
    NOT = "NOT"  # EXCEPT/subtract


class QueryableStatus(str, Enum):
    """Whether criterion is queryable against data."""
    FULLY_QUERYABLE = "fully_queryable"
    PARTIALLY_QUERYABLE = "partially_queryable"
    REQUIRES_MANUAL = "requires_manual"


# ============================================================================
# V2 Data Classes
# ============================================================================

@dataclass
class OmopQuerySpec:
    """OMOP CDM SQL query specification."""
    table_name: str
    concept_ids: List[int]
    concept_names: List[str]
    vocabulary_ids: List[str]
    concept_codes: List[str]  # SNOMED/ICD/LOINC codes for each concept
    sql_template: str
    sql_executable: bool = True
    value_constraint: Optional[str] = None  # e.g., "value_as_number >= 1500"

    # Mapping of OMOP table names to their concept_id column names
    TABLE_CONCEPT_COLUMNS = {
        "condition_occurrence": "condition_concept_id",
        "drug_exposure": "drug_concept_id",
        "measurement": "measurement_concept_id",
        "observation": "observation_concept_id",
        "procedure_occurrence": "procedure_concept_id",
        "device_exposure": "device_concept_id",
        "visit_occurrence": "visit_concept_id",
        "specimen": "specimen_concept_id",
    }

    def regenerate_sql_template(self) -> str:
        """
        Regenerate SQL template from current concept_ids and table_name.

        Bug #2 fix: When LLM validation updates concept_ids, the sql_template
        must also be updated to match. This prevents stale SQL that references
        old concept IDs from the initial keyword-based matching.

        Also appends value_constraint (e.g., "value_as_number >= 1500") to SQL
        when present, enabling proper filtering for lab criteria.

        Returns:
            Updated SQL template string
        """
        if not self.concept_ids:
            self.sql_template = f"-- No concept IDs for {self.table_name}"
            return self.sql_template

        # Get the concept column for this table
        concept_column = self.TABLE_CONCEPT_COLUMNS.get(
            self.table_name,
            f"{self.table_name.replace('_occurrence', '').replace('_exposure', '')}_concept_id"
        )

        # Build the concept ID list
        concept_list = ", ".join(str(cid) for cid in self.concept_ids)

        # Generate the SQL template
        sql = f"SELECT DISTINCT person_id FROM {self.table_name} WHERE {concept_column} IN ({concept_list})"

        # Append value constraint ONLY for tables that support value_as_number
        # This prevents invalid SQL like "condition_occurrence ... AND value_as_number >= X"
        if self.value_constraint:
            if self.table_name in TABLES_WITH_VALUE_COLUMN:
                sql += f" AND {self.value_constraint}"
            else:
                # Table doesn't support value constraints - log warning
                # The constraint is preserved in self.value_constraint for reference
                logger.warning(
                    f"Value constraint '{self.value_constraint}' not appended to SQL - "
                    f"table '{self.table_name}' does not support value_as_number column"
                )

        self.sql_template = sql
        return self.sql_template

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "tableName": self.table_name,
            "conceptIds": self.concept_ids,
            "conceptNames": self.concept_names,
            "vocabularyIds": self.vocabulary_ids,
            "conceptCodes": self.concept_codes,
            "sqlTemplate": self.sql_template,
            "sqlExecutable": self.sql_executable,
        }
        if self.value_constraint:
            result["valueConstraint"] = self.value_constraint
        return result


@dataclass
class FunnelImpact:
    """Impact metrics for a criterion."""
    elimination_rate: float = 0.0
    impact_score: float = 0.0
    is_killer_criterion: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eliminationRate": self.elimination_rate,
            "impactScore": self.impact_score,
            "isKillerCriterion": self.is_killer_criterion,
        }


@dataclass
class AtomicProvenance:
    """Source provenance for an atomic criterion."""
    page_number: Optional[int] = None
    text_snippet: Optional[str] = None
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pageNumber": self.page_number,
            "textSnippet": self.text_snippet,
            "confidence": self.confidence,
        }


@dataclass
class ExecutionContext:
    """Tells UX how to execute and combine this criterion."""
    logical_group: str
    group_logic: str  # AND/OR within group
    combine_with_previous: str  # AND/OR/NOT with prior results
    is_exclusion: bool
    sequence_hint: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "logicalGroup": self.logical_group,
            "groupLogic": self.group_logic,
            "combineWithPrevious": self.combine_with_previous,
            "isExclusion": self.is_exclusion,
            "sequenceHint": self.sequence_hint,
        }


@dataclass
class AtomicCriterion:
    """A single, atomically queryable eligibility criterion."""
    atomic_id: str
    original_criterion_id: str
    criterion_type: str  # "inclusion" or "exclusion"
    atomic_text: str
    normalized_text: str
    category: str
    funnel_impact: FunnelImpact
    omop_query: Optional[OmopQuerySpec] = None
    fhir_query: Optional[Dict[str, Any]] = None  # FhirQuerySpec as dict
    execution_context: Optional[ExecutionContext] = None
    provenance: Optional[AtomicProvenance] = None
    queryable_status: str = "requires_manual"  # fully_queryable, partially_queryable, requires_manual, screening_only
    non_queryable_reason: Optional[str] = None
    # Stage 2 clinical metadata - preserved for downstream validation and UI
    stage2_clinical_category: Optional[str] = None  # Original clinical category from Stage 2
    stage2_queryable_status: Optional[str] = None  # Original queryable status from Stage 2
    clinical_concept_group: Optional[str] = None  # Grouping ID for related atomics (e.g., "egfr_activating_mutation")
    expression_node_id: Optional[str] = None  # Original node ID from Stage 2 expression tree

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "atomicId": self.atomic_id,
            "originalCriterionId": self.original_criterion_id,
            "criterionType": self.criterion_type,
            "atomicText": self.atomic_text,
            "normalizedText": self.normalized_text,
            "category": self.category,
            "funnelImpact": self.funnel_impact.to_dict(),
            "omopQuery": self.omop_query.to_dict() if self.omop_query else None,
            "fhirQuery": self.fhir_query,
            "executionContext": self.execution_context.to_dict() if self.execution_context else None,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "queryableStatus": self.queryable_status,
            "nonQueryableReason": self.non_queryable_reason,
        }
        # Include Stage 2 metadata if present (for validation and UI)
        if self.stage2_clinical_category:
            result["stage2ClinicalCategory"] = self.stage2_clinical_category
        if self.stage2_queryable_status:
            result["stage2QueryableStatus"] = self.stage2_queryable_status
        if self.clinical_concept_group:
            result["clinicalConceptGroup"] = self.clinical_concept_group
        if self.expression_node_id:
            result["expressionNodeId"] = self.expression_node_id
        return result


@dataclass
class LogicalGroup:
    """Group of atoms with defined boolean logic."""
    group_id: str
    group_label: str
    internal_logic: str  # AND/OR within group
    combine_with_others: str  # AND/OR/NOT with other groups
    is_exclusion: bool
    atomic_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "groupId": self.group_id,
            "groupLabel": self.group_label,
            "internalLogic": self.internal_logic,
            "combineWithOthers": self.combine_with_others,
            "isExclusion": self.is_exclusion,
            "atomicIds": self.atomic_ids,
        }


@dataclass
class QueryableFunnelStage:
    """A stage in the patient funnel with query references."""
    stage_id: str
    stage_name: str
    stage_order: int
    stage_logic: str  # AND/OR
    criteria_ids: List[str]
    estimated_elimination_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stageId": self.stage_id,
            "stageName": self.stage_name,
            "stageOrder": self.stage_order,
            "stageLogic": self.stage_logic,
            "criteriaIds": self.criteria_ids,
            "estimatedEliminationRate": self.estimated_elimination_rate,
        }


@dataclass
class QueryableFunnelResult:
    """V2 output format with atomic criteria and execution context."""
    protocol_id: str
    version: str = "2.0"
    generated_at: str = ""
    atomic_criteria: List[AtomicCriterion] = field(default_factory=list)
    logical_groups: List[LogicalGroup] = field(default_factory=list)
    expression_tree: Optional[Dict[str, Any]] = None
    funnel_stages: List[QueryableFunnelStage] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocolId": self.protocol_id,
            "version": self.version,
            "generatedAt": self.generated_at,
            "atomicCriteria": [ac.to_dict() for ac in self.atomic_criteria],
            "logicalGroups": [lg.to_dict() for lg in self.logical_groups],
            "expressionTree": self.expression_tree,
            "funnelStages": [fs.to_dict() for fs in self.funnel_stages],
            "metadata": self.metadata,
        }


# ============================================================================
# Eligibility Funnel Builder
# ============================================================================

class EligibilityFunnelBuilder:
    """
    Builds queryable eligibility funnel by integrating Stage 2/5/6 outputs.

    Workflow:
    1. Load Stage 2 decomposed criteria with expression trees
    2. Load Stage 5 OMOP concept mappings
    3. Load Stage 6 SQL templates
    4. Generate FHIR queries using OMOP→FHIR bridge
    5. Build logical groups from expression trees
    6. Assign execution context to each atomic
    7. Output QueryableFunnelResult
    """

    # Default category mappings for funnel stages (used if config not available)
    # Prefer using config.get_stage_for_category() which loads from YAML
    _DEFAULT_CATEGORY_TO_STAGE = {
        "disease_indication": ("S1", "Disease Indication", 1),
        "demographics": ("S2", "Demographics", 2),
        "biomarker": ("S3", "Biomarker Requirements", 3),
        "treatment_history": ("S4", "Treatment History", 4),
        "functional_status": ("S5", "Performance Status", 5),
        "lab_criteria": ("S6", "Lab Criteria", 6),
        "safety_exclusion": ("S7", "Safety Exclusions", 7),
        "other": ("S8", "Other Criteria", 8),
    }

    def __init__(self, athena_db_path: Optional[str] = None, use_llm: bool = True):
        """
        Initialize the builder.

        Args:
            athena_db_path: Path to ATHENA database for FHIR translation.
            use_llm: Whether to use LLM for semantic matching (default True).
                     Set to False for faster testing with keyword-based fallback.
        """
        self.fhir_bridge = OmopFhirBridge(athena_db_path)
        self._atomic_counter = 0
        self.use_llm = use_llm

        # Initialize LLM matcher (lazy initialization if needed)
        self._llm_matcher: Optional[LLMAtomicMatcher] = None
        if use_llm:
            try:
                self._llm_matcher = LLMAtomicMatcher()
            except Exception as e:
                logger.warning(f"Failed to initialize LLM matcher, falling back to keyword matching: {e}")
                self.use_llm = False

        # Initialize LLM reflection service for schema validation and error correction
        self._reflection_service: Optional[LLMReflectionService] = None
        if use_llm:
            try:
                self._reflection_service = LLMReflectionService()
            except Exception as e:
                logger.warning(f"Failed to initialize reflection service: {e}")

        # Load configuration from YAML files
        self._config = load_config()

        # Load curated lab concept mappings for common clinical values
        self._curated_mappings = self._load_curated_mappings()

    def _get_category_to_stage(self) -> Dict[str, Tuple[str, str, int]]:
        """
        Get category to funnel stage mapping from config or use default.

        Returns:
            Dict mapping category name to (stage_id, display_name, order) tuple
        """
        result = {}
        for category in self._DEFAULT_CATEGORY_TO_STAGE.keys():
            stage_info = self._config.get_stage_for_category(category)
            if stage_info:
                result[category] = stage_info
            else:
                result[category] = self._DEFAULT_CATEGORY_TO_STAGE[category]
        return result

    async def build_from_stage_outputs(
        self,
        protocol_id: str,
        stage2_result: Dict[str, Any],
        stage5_result: Dict[str, Any],
        stage6_result: Dict[str, Any],
        key_criteria: Optional[List[Dict[str, Any]]] = None,
    ) -> QueryableFunnelResult:
        """
        Build V2 funnel from interpretation stage outputs.

        Uses LLM-based semantic matching for:
        - OMOP mapping selection (replaces Jaccard similarity)
        - Category classification (replaces keyword matching)
        - Key criteria matching (replaces text matching)

        Args:
            protocol_id: Protocol identifier
            stage2_result: Stage 2 atomic decomposition result
            stage5_result: Stage 5 OMOP mapping result
            stage6_result: Stage 6 SQL template result
            key_criteria: Optional pre-selected key criteria from Stage 11

        Returns:
            QueryableFunnelResult with atomic criteria and execution context
        """
        logger.info(f"Building V2 funnel for protocol: {protocol_id} (LLM mode: {self.use_llm})")

        # Index Stage 5 mappings by (criterionId, atomicId)
        omop_index = self._index_omop_mappings(stage5_result)
        logger.info(f"Indexed {len(omop_index)} OMOP mappings")

        # Index Stage 6 SQL templates by criterionId
        sql_index = self._index_sql_templates(stage6_result)
        logger.info(f"Indexed {len(sql_index)} SQL templates")

        # Process each decomposed criterion
        decomposed_criteria = stage2_result.get("decomposedCriteria", [])
        all_atomics: List[AtomicCriterion] = []
        all_groups: List[LogicalGroup] = []
        expression_trees: Dict[str, Any] = {}

        for criterion in decomposed_criteria:
            criterion_id = str(criterion.get("criterionId", ""))
            criterion_type = criterion.get("type", "Inclusion").lower()
            is_exclusion = criterion_type == "exclusion"

            # Get expression tree
            expression = criterion.get("expression", {})
            if not expression:
                continue

            # Process expression tree to extract atomics and groups
            atomics, groups = self._process_expression_tree(
                expression=expression,
                criterion_id=criterion_id,
                criterion_type=criterion_type,
                original_text=criterion.get("originalText", ""),
                provenance=criterion.get("provenance"),
                omop_index=omop_index,
                sql_index=sql_index,
                is_exclusion=is_exclusion,
            )

            all_atomics.extend(atomics)
            all_groups.extend(groups)

            # Store expression tree
            expression_trees[criterion_id] = {
                "criterionId": criterion_id,
                "type": criterion_type,
                "tree": expression,
            }

        # LLM-first approach: Assign categories and validate OMOP mappings
        await self._assign_categories_llm(all_atomics, key_criteria, omop_index)
        await self._validate_and_update_omop_mappings_llm(all_atomics, omop_index)
        funnel_stages = self._build_funnel_stages(all_atomics)

        # Build result
        result = QueryableFunnelResult(
            protocol_id=protocol_id,
            atomic_criteria=all_atomics,
            logical_groups=all_groups,
            expression_tree={"criteria": expression_trees},
            funnel_stages=funnel_stages,
            metadata={
                "totalAtomics": len(all_atomics),
                "totalGroups": len(all_groups),
                "totalStages": len(funnel_stages),
                "stagesWithQueries": sum(
                    1 for ac in all_atomics
                    if ac.omop_query and ac.omop_query.sql_executable
                ),
                "stagesWithFhir": sum(
                    1 for ac in all_atomics
                    if ac.fhir_query and ac.fhir_query.get("queryExecutable", False)
                ),
            },
        )

        logger.info(
            f"Built V2 funnel: {len(all_atomics)} atomics, "
            f"{len(all_groups)} groups, {len(funnel_stages)} stages"
        )

        return result

    def _index_omop_mappings(
        self,
        stage5_result: Dict[str, Any]
    ) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
        """Index OMOP mappings by (criterionId, atomicId), storing lists for duplicates."""
        index: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        mappings = stage5_result.get("mappings", [])

        for mapping in mappings:
            criterion_id = str(mapping.get("criterionId", ""))
            atomic_id = str(mapping.get("atomicId", ""))
            key = (criterion_id, atomic_id)
            if key not in index:
                index[key] = []
            index[key].append(mapping)

        return index

    def _calculate_jaccard_similarity(
        self,
        text1: str,
        text2: str,
    ) -> float:
        """
        Calculate Jaccard similarity between two text strings.

        Returns a value between 0 and 1, where 1 means identical word sets.
        """
        # Normalize and tokenize
        stop_words = {
            "the", "a", "an", "is", "are", "be", "to", "of", "and", "or", "in",
            "for", "with", "on", "at", "by", "from", "that", "this", "which",
            "has", "have", "had", "been", "must", "should", "will", "can",
            "may", "subject", "patient", "subjects", "patients"
        }

        words1 = set(text1.lower().split()) - stop_words
        words2 = set(text2.lower().split()) - stop_words

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _validate_concept_domain_fallback(
        self,
        atomic_text: str,
        mapping: Dict[str, Any],
    ) -> bool:
        """
        FALLBACK: Validate concept domain.

        Fallback chain:
        1. Try reflection service (LLM-based) - if available
        2. Fall back to keyword patterns - if LLM unavailable

        Catches semantic mismatches like "Age >= 18" mapped to drug concepts.
        """
        # Get domain and concept_name from mapping
        concepts = mapping.get("concepts", [])
        if not concepts:
            return True  # Can't validate, allow it

        first_concept = concepts[0]
        domain = first_concept.get("domain_id", "")
        concept_name = first_concept.get("concept_name", "")

        # Try reflection service first (LLM-based)
        try:
            import asyncio
            reflection_service = LLMReflectionService()
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                is_valid, reason = loop.run_until_complete(
                    reflection_service.validate_domain_semantic(
                        atomic_text=atomic_text,
                        concept_name=concept_name,
                        domain=domain,
                    )
                )
                if reason:
                    logger.debug(f"Reflection domain validation for '{atomic_text[:30]}...': {is_valid} ({reason})")
                return is_valid
        except Exception as e:
            logger.debug(f"Reflection service unavailable for domain validation: {e}")

        # Fall back to keyword patterns
        logger.debug(f"Using keyword fallback for domain validation: '{atomic_text[:50]}...'")
        text_lower = atomic_text.lower()

        # Get all domains from mapping concepts
        domains = set()
        for concept in concepts:
            d = concept.get("domain_id", "").lower()
            if d:
                domains.add(d)

        if not domains:
            return True  # Can't validate, allow it

        # Define expected domains for text patterns (keyword fallback)
        domain_patterns = {
            # Age/demographics should map to Observation or Measurement, not Drug/Condition
            "age": {"observation", "measurement", "person"},
            "year": {"observation", "measurement", "person"},
            "≥ 18": {"observation", "measurement", "person"},
            ">= 18": {"observation", "measurement", "person"},
            "adult": {"observation", "measurement", "person"},

            # Disease indications should map to Condition
            "cancer": {"condition"},
            "carcinoma": {"condition"},
            "nsclc": {"condition"},
            "tumor": {"condition"},
            "disease": {"condition"},
            "diagnosis": {"condition"},
            "metastasis": {"condition"},
            "metastases": {"condition"},

            # Lab values should map to Measurement
            "hemoglobin": {"measurement"},
            "platelet": {"measurement"},
            "creatinine": {"measurement"},
            "bilirubin": {"measurement"},
            "anc": {"measurement"},
            "wbc": {"measurement"},
            "neutrophil": {"measurement"},

            # Treatments should map to Drug or Procedure
            "chemotherapy": {"drug", "procedure"},
            "radiation": {"procedure"},
            "surgery": {"procedure"},
            "therapy": {"drug", "procedure"},

            # Imaging procedures - NEVER Drug domain
            "ct scan": {"procedure"},
            "computed tomography": {"procedure"},
            "cat scan": {"procedure"},
            "mri": {"procedure"},
            "magnetic resonance": {"procedure"},
            "pet scan": {"procedure"},
            "positron emission": {"procedure"},
            "x-ray": {"procedure"},
            "xray": {"procedure"},
            "ultrasound": {"procedure"},
            "sonography": {"procedure"},
            "radiograph": {"procedure"},
            "imaging": {"procedure"},
            "scan": {"procedure"},

            # Allergies and hypersensitivity
            "hypersensitivity": {"condition", "observation"},
            "allergy": {"condition", "observation"},
        }

        # Check if any text pattern has a domain constraint
        for pattern, expected_domains in domain_patterns.items():
            if pattern in text_lower:
                # Check if any domain in mapping is in expected domains
                if domains.isdisjoint(expected_domains):
                    # Semantic mismatch! E.g., "age" text with "drug" domain
                    return False
                break

        return True

    def _find_best_omop_mapping_fallback(
        self,
        mappings: List[Dict[str, Any]],
        atomic_text: str,
    ) -> Optional[Dict[str, Any]]:
        """
        FALLBACK: Find the best OMOP mapping using Jaccard similarity.

        Used when LLM matching is unavailable. Uses Jaccard similarity with
        minimum 0.3 threshold and keyword-based domain validation.
        """
        if not mappings:
            return None
        if len(mappings) == 1:
            # Even with single mapping, validate domain
            if self._validate_concept_domain_fallback(atomic_text, mappings[0]):
                return mappings[0]
            else:
                logger.warning(
                    f"Single mapping rejected due to domain mismatch: "
                    f"'{atomic_text}' -> concepts: {[c.get('concept_name') for c in mappings[0].get('concepts', [])]}"
                )
                return None

        # Score all mappings
        scored_mappings: List[Tuple[float, Dict[str, Any]]] = []

        for mapping in mappings:
            # Skip if domain validation fails
            if not self._validate_concept_domain_fallback(atomic_text, mapping):
                continue

            term = mapping.get("term", "")
            similarity = self._calculate_jaccard_similarity(atomic_text, term)
            scored_mappings.append((similarity, mapping))

        if not scored_mappings:
            logger.warning(
                f"All mappings rejected for '{atomic_text}' due to domain validation failures"
            )
            return None

        # Sort by similarity (descending)
        scored_mappings.sort(key=lambda x: x[0], reverse=True)

        # Require minimum 0.3 Jaccard similarity (about 30% word overlap)
        best_score, best_mapping = scored_mappings[0]

        if best_score >= 0.3:
            return best_mapping

        # If best score is too low but we have candidates, log warning
        if scored_mappings:
            logger.debug(
                f"Best mapping for '{atomic_text}' has low similarity ({best_score:.2f}), "
                f"falling back to best available: '{best_mapping.get('term', '')}'"
            )
            # Still return best available rather than nothing
            return best_mapping

        return None

    def _find_best_omop_mapping(
        self,
        mappings: List[Dict[str, Any]],
        atomic_text: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Find the best OMOP mapping using keyword-based fallback.

        Note: LLM-based OMOP matching is done in batch via
        _validate_and_update_omop_mappings_llm() after atomic creation.
        """
        return self._find_best_omop_mapping_fallback(mappings, atomic_text)

    def _load_curated_mappings(self) -> Dict[str, Any]:
        """
        Load curated reference mappings for common clinical values.

        These mappings bypass the database pattern matching for well-known
        clinical concepts (labs, biomarkers, conditions, treatments, medications)
        to prevent semantic mismatches like 'ANC' matching 'Grade Cancer'.
        """
        mappings_path = Path(__file__).parent / "reference_data" / "curated_concept_mappings.json"
        if mappings_path.exists():
            try:
                with open(mappings_path, "r", encoding="utf-8") as f:
                    mappings = json.load(f)
                    total = sum(len(v) for k, v in mappings.items() if k.endswith('_mappings'))
                    logger.info(f"Loaded {total} curated concept mappings")
                    return mappings
            except Exception as e:
                logger.warning(f"Failed to load curated mappings: {e}")
        else:
            logger.warning(f"Curated mappings not found: {mappings_path}")
        return {}

    def _find_curated_mapping(self, atomic_text: str) -> Optional[Dict[str, Any]]:
        """
        Check if atomic text matches any curated mapping patterns.

        Returns curated OMOP concept and FHIR codes if found, None otherwise.
        This bypasses the database lookup for well-known clinical values.

        Uses word-boundary matching to avoid false positives (e.g., "anc" matching "cancer").
        """
        import re

        if not self._curated_mappings:
            return None

        text_lower = atomic_text.lower()

        # Helper to build curated result with FHIR codes
        def build_result(mapping_info: Dict, term: str) -> Dict[str, Any]:
            concept = mapping_info.get("omop_concept", {})
            return {
                "source": "curated",
                "term": term,
                "concepts": [concept],
                "sql_template": mapping_info.get("sql_template", ""),
                "fhir_codes": mapping_info.get("fhir_codes", []),
                "fhir_resource_type": mapping_info.get("fhir_resource_type", ""),
            }

        def pattern_matches(pattern: str, text: str) -> bool:
            """Check if pattern matches text using word boundaries for short patterns."""
            pattern_lower = pattern.lower()
            # For short patterns (<=4 chars), use word boundary matching to avoid false positives
            if len(pattern_lower) <= 4:
                # Match only as a whole word or at word boundaries
                word_pattern = r'\b' + re.escape(pattern_lower) + r'\b'
                return bool(re.search(word_pattern, text))
            else:
                # Longer patterns are less likely to cause false positives
                return pattern_lower in text

        # Check lab mappings
        for lab_key, lab_info in self._curated_mappings.get("lab_mappings", {}).items():
            patterns = lab_info.get("patterns", [])
            if any(pattern_matches(p, text_lower) for p in patterns):
                return build_result(lab_info, lab_key)

        # Check biomarker mappings
        for bio_key, bio_info in self._curated_mappings.get("biomarker_mappings", {}).items():
            patterns = bio_info.get("patterns", [])
            if any(pattern_matches(p, text_lower) for p in patterns):
                return build_result(bio_info, bio_key)

        # Check functional status mappings
        for func_key, func_info in self._curated_mappings.get("functional_status_mappings", {}).items():
            patterns = func_info.get("patterns", [])
            if any(pattern_matches(p, text_lower) for p in patterns):
                return build_result(func_info, func_key)

        # Check condition mappings
        for cond_key, cond_info in self._curated_mappings.get("condition_mappings", {}).items():
            patterns = cond_info.get("patterns", [])
            if any(pattern_matches(p, text_lower) for p in patterns):
                return build_result(cond_info, cond_key)

        # Check demographic mappings
        for demo_key, demo_info in self._curated_mappings.get("demographic_mappings", {}).items():
            patterns = demo_info.get("patterns", [])
            if any(pattern_matches(p, text_lower) for p in patterns):
                return build_result(demo_info, demo_key)

        # Check organ function mappings
        for organ_key, organ_info in self._curated_mappings.get("organ_function_mappings", {}).items():
            patterns = organ_info.get("patterns", [])
            if any(pattern_matches(p, text_lower) for p in patterns):
                return build_result(organ_info, organ_key)

        # Check comorbidity mappings
        for comorb_key, comorb_info in self._curated_mappings.get("comorbidity_mappings", {}).items():
            patterns = comorb_info.get("patterns", [])
            if any(pattern_matches(p, text_lower) for p in patterns):
                return build_result(comorb_info, comorb_key)

        # Check prior treatment mappings
        for treat_key, treat_info in self._curated_mappings.get("prior_treatment_mappings", {}).items():
            patterns = treat_info.get("patterns", [])
            if any(pattern_matches(p, text_lower) for p in patterns):
                return build_result(treat_info, treat_key)

        # Check medication mappings
        for med_key, med_info in self._curated_mappings.get("medication_mappings", {}).items():
            patterns = med_info.get("patterns", [])
            if any(pattern_matches(p, text_lower) for p in patterns):
                return build_result(med_info, med_key)

        # Check clinical findings mappings
        for finding_key, finding_info in self._curated_mappings.get("clinical_findings_mappings", {}).items():
            patterns = finding_info.get("patterns", [])
            if any(pattern_matches(p, text_lower) for p in patterns):
                return build_result(finding_info, finding_key)

        # Check procedure mappings (imaging, etc.)
        for proc_key, proc_info in self._curated_mappings.get("procedure_mappings", {}).items():
            patterns = proc_info.get("patterns", [])
            if any(pattern_matches(p, text_lower) for p in patterns):
                return build_result(proc_info, proc_key)

        # Check allergy/hypersensitivity mappings
        for allergy_key, allergy_info in self._curated_mappings.get("allergy_hypersensitivity_mappings", {}).items():
            patterns = allergy_info.get("patterns", [])
            if any(pattern_matches(p, text_lower) for p in patterns):
                return build_result(allergy_info, allergy_key)

        return None

    def _apply_curated_mapping(self, atomic: AtomicCriterion, curated: Dict[str, Any]) -> None:
        """Apply a curated mapping to an atomic criterion (both OMOP and FHIR)."""
        concepts = curated.get("concepts", [])
        if concepts and atomic.omop_query:
            concept = concepts[0]
            atomic.omop_query.concept_ids = [concept.get("concept_id")]
            atomic.omop_query.concept_names = [concept.get("concept_name", "")]
            atomic.omop_query.vocabulary_ids = [concept.get("vocabulary_id", "")]
            atomic.omop_query.concept_codes = [concept.get("concept_code", "")]

            # Set table based on domain
            domain = concept.get("domain_id", "")
            if domain == "Measurement":
                atomic.omop_query.table_name = "measurement"
            elif domain == "Condition":
                atomic.omop_query.table_name = "condition_occurrence"
            elif domain == "Drug":
                atomic.omop_query.table_name = "drug_exposure"
            elif domain == "Procedure":
                atomic.omop_query.table_name = "procedure_occurrence"
            else:
                atomic.omop_query.table_name = "observation"

            # Use curated SQL if available, otherwise regenerate
            sql_template = curated.get("sql_template", "")
            if sql_template:
                atomic.omop_query.sql_template = sql_template
                # Append value constraint to curated SQL if:
                # 1. Value constraint exists
                # 2. Not already in the SQL
                # 3. Table supports value_as_number column
                # 4. SQL doesn't already have age calculation (EXTRACT)
                if atomic.omop_query.value_constraint and "value_as_number" not in sql_template:
                    if atomic.omop_query.table_name in TABLES_WITH_VALUE_COLUMN:
                        # Don't append to age SQL that uses EXTRACT - it already handles the constraint
                        if "EXTRACT" not in sql_template.upper():
                            atomic.omop_query.sql_template += f" AND {atomic.omop_query.value_constraint}"
            else:
                atomic.omop_query.regenerate_sql_template()

            atomic.omop_query.sql_executable = True
            logger.debug(f"Applied curated OMOP mapping for {atomic.atomic_id}: {concept.get('concept_name')}")

        # Apply curated FHIR codes if available (bypass database lookup)
        fhir_codes_data = curated.get("fhir_codes", [])
        fhir_resource_type = curated.get("fhir_resource_type", "")
        if fhir_codes_data and fhir_resource_type:
            # Build FhirCode objects from curated data
            fhir_codes = [
                FhirCode(
                    system=fc.get("system", ""),
                    code=fc.get("code", ""),
                    display=fc.get("display", "")
                )
                for fc in fhir_codes_data
            ]

            # Build search params from codes
            code_system = fhir_codes[0].system if fhir_codes else ""
            code_values = ",".join(fc.code for fc in fhir_codes)
            search_params = f"code={code_system}|{code_values}" if code_system and code_values else ""

            # Create FHIR query spec
            fhir_spec = FhirQuerySpec(
                resource_type=fhir_resource_type,
                codes=fhir_codes,
                search_params=search_params,
                query_executable=True,
            )
            atomic.fhir_query = fhir_spec.to_dict()
            logger.debug(f"Applied curated FHIR mapping for {atomic.atomic_id}: {fhir_resource_type} ({len(fhir_codes)} codes)")

    def _apply_validated_mapping(self, atomic: AtomicCriterion, concept: Dict[str, Any]) -> None:
        """Apply a validated OMOP concept to an atomic criterion."""
        if atomic.omop_query:
            atomic.omop_query.concept_ids = [concept.get("concept_id")]
            atomic.omop_query.concept_names = [concept.get("concept_name", "")]
            atomic.omop_query.vocabulary_ids = [concept.get("vocabulary_id", "")]
            atomic.omop_query.concept_codes = [concept.get("concept_code", "")]

            # Set table based on domain
            domain = concept.get("domain_id", "")
            if domain == "Measurement":
                atomic.omop_query.table_name = "measurement"
            elif domain == "Condition":
                atomic.omop_query.table_name = "condition_occurrence"
            elif domain == "Drug":
                atomic.omop_query.table_name = "drug_exposure"
            elif domain == "Procedure":
                atomic.omop_query.table_name = "procedure_occurrence"
            else:
                atomic.omop_query.table_name = "observation"

            atomic.omop_query.regenerate_sql_template()
            atomic.omop_query.sql_executable = True

    async def _search_omop_for_recovery(self, term: str) -> List[Dict[str, Any]]:
        """
        Search OMOP/ATHENA database for concepts matching a term.

        Used by UNMAPPED recovery to find alternative concepts.

        Args:
            term: Search term (e.g., "lung carcinoma", "EGFR mutation")

        Returns:
            List of concept dicts with concept_id, concept_name, domain_id, vocabulary_id
        """
        if not self.fhir_bridge or not self.fhir_bridge.db_path:
            logger.debug("No ATHENA database available for OMOP search")
            return []

        try:
            conn = self.fhir_bridge._get_connection()
            if not conn:
                return []

            cursor = conn.cursor()
            # Search for standard concepts matching the term
            search_term = f"%{term}%"
            cursor.execute("""
                SELECT concept_id, concept_name, domain_id, vocabulary_id,
                       concept_class_id, standard_concept
                FROM concept
                WHERE concept_name LIKE ?
                  AND standard_concept = 'S'
                  AND invalid_reason IS NULL
                ORDER BY
                    CASE WHEN LOWER(concept_name) = LOWER(?) THEN 0 ELSE 1 END,
                    LENGTH(concept_name)
                LIMIT 10
            """, (search_term, term))

            results = []
            for row in cursor.fetchall():
                results.append({
                    "concept_id": row["concept_id"],
                    "concept_name": row["concept_name"],
                    "domain_id": row["domain_id"],
                    "vocabulary_id": row["vocabulary_id"],
                    "concept_class_id": row["concept_class_id"],
                })

            logger.debug(f"OMOP search for '{term}': {len(results)} results")
            return results

        except Exception as e:
            logger.warning(f"OMOP search failed for '{term}': {e}")
            return []

    async def _validate_and_update_omop_mappings_llm(
        self,
        atomics: List[AtomicCriterion],
        omop_index: Dict[Tuple[str, str], List[Dict[str, Any]]],
    ) -> None:
        """
        Use LLM to validate and update OMOP mappings for atomics.

        Enhanced flow:
        1. Check curated mappings first (bypass database lookup for well-known values)
        2. For database-derived mappings, run LLM SEMANTIC validation
        3. Reject semantically wrong concepts (e.g., 'Grade Cancer' for 'ANC')
        4. Update SQL templates to match validated concepts
        """
        curated_count = 0
        validation_count = 0

        # Step 1: Apply curated mappings first
        atomics_needing_validation = []

        for atomic in atomics:
            # Check curated mappings first
            curated = self._find_curated_mapping(atomic.atomic_text)
            if curated:
                # Use curated mapping, skip database validation
                self._apply_curated_mapping(atomic, curated)
                curated_count += 1
                continue

            # Collect database-derived mappings for semantic validation
            criterion_id = atomic.original_criterion_id
            atomic_id = atomic.atomic_id

            candidate_mappings = []
            for key in [(criterion_id, atomic_id), (criterion_id, criterion_id), (criterion_id, "root")]:
                mappings = omop_index.get(key, [])
                for m in mappings:
                    if m not in candidate_mappings:
                        candidate_mappings.append(m)

            if not candidate_mappings:
                continue

            # Extract all concepts for semantic validation
            all_concepts = []
            for m in candidate_mappings:
                for c in m.get("concepts", []):
                    if c not in all_concepts:
                        all_concepts.append(c)

            if all_concepts:
                atomics_needing_validation.append({
                    "atomic_id": atomic_id,
                    "atomic_text": atomic.atomic_text,
                    "concepts": all_concepts,
                    "_atomic_ref": atomic,
                    "_mappings": candidate_mappings,
                })

        logger.info(f"Applied {curated_count} curated mappings, {len(atomics_needing_validation)} need LLM validation")

        if not atomics_needing_validation:
            return

        # Step 2: Run LLM semantic validation for database-derived mappings
        if not self.use_llm or not self._llm_matcher:
            logger.debug("LLM matcher not available, using domain validation fallback")
            # Fall back to domain validation only
            await self._validate_domains_fallback(atomics_needing_validation)
            return

        try:
            # Run LLM semantic validation (validates concept NAMES match atomic MEANING)
            validations = await self._llm_matcher.validate_concept_semantics_batch(
                atomics_needing_validation
            )

            # Step 3: Apply validation results
            for item in atomics_needing_validation:
                atomic_id = item["atomic_id"]
                atomic = item["_atomic_ref"]
                all_concepts = item["concepts"]

                validation_result = validations.get(atomic_id, {})
                best_mapping_id = validation_result.get("best_valid_mapping_id")

                if best_mapping_id:
                    # Find the valid concept and use it
                    mapping_idx = int(best_mapping_id.replace("M", ""))
                    if 0 <= mapping_idx < len(all_concepts):
                        valid_concept = all_concepts[mapping_idx]
                        self._apply_validated_mapping(atomic, valid_concept)
                        validation_count += 1
                        logger.debug(f"Applied validated mapping for {atomic_id}: {valid_concept.get('concept_name')}")
                else:
                    # No valid mapping - try UNMAPPED recovery before giving up
                    recovered = False
                    if atomic.omop_query:
                        try:
                            reflection_service = LLMReflectionService()
                            recovery_result = await reflection_service.recover_unmapped_criterion(
                                atomic_text=atomic.atomic_text,
                                failed_concepts=all_concepts,
                                search_function=self._search_omop_for_recovery,
                            )
                            if recovery_result:
                                # Apply recovered mapping
                                self._apply_validated_mapping(atomic, recovery_result)
                                validation_count += 1
                                recovered = True
                                logger.info(
                                    f"Recovered UNMAPPED {atomic_id} via '{recovery_result.get('recovery_term')}' -> "
                                    f"{recovery_result.get('concept_name')}"
                                )
                        except Exception as e:
                            logger.debug(f"UNMAPPED recovery failed for {atomic_id}: {e}")

                    if not recovered:
                        # Mark as unmapped with reason
                        if atomic.omop_query:
                            atomic.omop_query.concept_ids = []
                            atomic.omop_query.concept_names = []
                            atomic.omop_query.sql_template = f"-- UNMAPPED: No semantically valid concepts for '{atomic.atomic_text[:50]}...'"
                            atomic.omop_query.sql_executable = False
                        logger.warning(f"No valid semantic mapping for {atomic_id}: {atomic.atomic_text[:50]}...")

            logger.info(
                f"LLM semantic validation completed: {curated_count} curated, "
                f"{validation_count} validated, {len(atomics_needing_validation) - validation_count} unmapped"
            )

        except Exception as e:
            logger.warning(f"LLM semantic validation failed: {e}")
            # Fall back to domain validation
            await self._validate_domains_fallback(atomics_needing_validation)

    async def _validate_domains_fallback(
        self,
        atomics_with_concepts: List[Dict[str, Any]],
    ) -> None:
        """Fall back to domain validation when semantic validation fails."""
        if not self._llm_matcher:
            return

        try:
            # Convert to format expected by domain validation
            domain_input = [
                {
                    "atomic_id": item["atomic_id"],
                    "atomic_text": item["atomic_text"],
                    "mappings": item["_mappings"],
                }
                for item in atomics_with_concepts
            ]

            validations = await self._llm_matcher.validate_concept_domains_batch(domain_input)

            for item in atomics_with_concepts:
                atomic_id = item["atomic_id"]
                atomic = item["_atomic_ref"]
                mappings = item["_mappings"]
                all_concepts = item["concepts"]

                validation_results = validations.get(atomic_id, {})

                # Find first valid mapping according to domain validation
                best_concept = None
                for i, concept in enumerate(all_concepts[:10]):
                    mapping_id = f"M{i}"
                    if validation_results.get(mapping_id, True):
                        best_concept = concept
                        break

                if best_concept:
                    self._apply_validated_mapping(atomic, best_concept)

            logger.info(f"Domain validation fallback completed for {len(atomics_with_concepts)} atomics")

        except Exception as e:
            logger.warning(f"LLM domain validation fallback failed: {e}, trying reflection service")
            # Use reflection service as second-tier fallback
            try:
                reflection_service = LLMReflectionService()
                for item in atomics_with_concepts:
                    atomic = item["_atomic_ref"]
                    concepts = item["concepts"]

                    # Try to validate each concept with reflection service
                    for concept in concepts[:5]:  # Limit to top 5
                        is_valid, _ = await reflection_service.validate_domain_semantic(
                            atomic_text=atomic.atomic_text,
                            concept_name=concept.get("concept_name", ""),
                            domain=concept.get("domain_id", "Unknown"),
                        )
                        if is_valid:
                            self._apply_validated_mapping(atomic, concept)
                            break

                logger.info(f"Reflection domain validation completed for {len(atomics_with_concepts)} atomics")

            except Exception as e2:
                logger.warning(f"Reflection service domain validation also failed: {e2}")

    def _index_sql_templates(
        self,
        stage6_result: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Index SQL templates by criterionId, with components by atomicId."""
        index = {}
        templates = stage6_result.get("templates", [])

        for template in templates:
            criterion_id = str(template.get("criterionId", ""))
            index[criterion_id] = template

        return index

    def _process_expression_tree(
        self,
        expression: Dict[str, Any],
        criterion_id: str,
        criterion_type: str,
        original_text: str,
        provenance: Optional[Dict[str, Any]],
        omop_index: Dict[Tuple[str, str], Dict[str, Any]],
        sql_index: Dict[str, Dict[str, Any]],
        is_exclusion: bool,
        parent_logic: str = "AND",
        depth: int = 0,
    ) -> Tuple[List[AtomicCriterion], List[LogicalGroup]]:
        """
        Recursively process expression tree to extract atomics and groups.

        Args:
            expression: Expression tree node
            criterion_id: Parent criterion ID
            criterion_type: "inclusion" or "exclusion"
            original_text: Original criterion text
            provenance: Provenance info
            omop_index: Indexed OMOP mappings
            sql_index: Indexed SQL templates
            is_exclusion: Whether this is an exclusion criterion
            parent_logic: Logic operator from parent node
            depth: Recursion depth

        Returns:
            Tuple of (atomics list, groups list)
        """
        atomics: List[AtomicCriterion] = []
        groups: List[LogicalGroup] = []

        node_type = expression.get("nodeType", "atomic")
        node_id = expression.get("nodeId", "root")

        if node_type == "atomic":
            # This is a leaf node - create atomic criterion
            atomic = self._create_atomic_from_node(
                node=expression,
                criterion_id=criterion_id,
                node_id=node_id,
                criterion_type=criterion_type,
                provenance=provenance,
                omop_index=omop_index,
                sql_index=sql_index,
                is_exclusion=is_exclusion,
                parent_logic=parent_logic,
            )
            if atomic:
                atomics.append(atomic)

        elif node_type == "operator":
            # This is an operator node - recurse into operands
            operator = expression.get("operator", "AND")

            # Create a logical group for this operator
            group_id = f"G_{criterion_id}_{node_id}"
            group_atomics: List[str] = []

            # CRITICAL: Handle IMPLICATION operator separately
            # IMPLICATION has "condition" and "requirement" instead of "operands"
            # Semantic: IF condition THEN requirement (P → Q)
            # SQL equivalent: (NOT P) UNION (P AND Q)
            if operator == "IMPLICATION":
                condition = expression.get("condition", {})
                requirement = expression.get("requirement", {})

                # Process condition branch
                if condition:
                    child_atomics, child_groups = self._process_expression_tree(
                        expression=condition,
                        criterion_id=criterion_id,
                        criterion_type=criterion_type,
                        original_text=original_text,
                        provenance=provenance,
                        omop_index=omop_index,
                        sql_index=sql_index,
                        is_exclusion=is_exclusion,
                        parent_logic="IMPLICATION_CONDITION",
                        depth=depth + 1,
                    )
                    atomics.extend(child_atomics)
                    groups.extend(child_groups)
                    group_atomics.extend([a.atomic_id for a in child_atomics])

                # Process requirement branch
                if requirement:
                    child_atomics, child_groups = self._process_expression_tree(
                        expression=requirement,
                        criterion_id=criterion_id,
                        criterion_type=criterion_type,
                        original_text=original_text,
                        provenance=provenance,
                        omop_index=omop_index,
                        sql_index=sql_index,
                        is_exclusion=is_exclusion,
                        parent_logic="IMPLICATION_REQUIREMENT",
                        depth=depth + 1,
                    )
                    atomics.extend(child_atomics)
                    groups.extend(child_groups)
                    group_atomics.extend([a.atomic_id for a in child_atomics])

                # Log for debugging
                if not condition and not requirement:
                    logger.warning(
                        f"IMPLICATION operator at node {node_id} has no condition or requirement - "
                        f"criterion {criterion_id}"
                    )

            else:
                # Standard operators (AND, OR, NOT, EXCEPT) use operands array
                operands = expression.get("operands", [])

                for operand in operands:
                    child_atomics, child_groups = self._process_expression_tree(
                        expression=operand,
                        criterion_id=criterion_id,
                        criterion_type=criterion_type,
                        original_text=original_text,
                        provenance=provenance,
                        omop_index=omop_index,
                        sql_index=sql_index,
                        is_exclusion=is_exclusion,
                        parent_logic=operator,
                        depth=depth + 1,
                    )
                    atomics.extend(child_atomics)
                    groups.extend(child_groups)
                    group_atomics.extend([a.atomic_id for a in child_atomics])

            # Create group if it has atomics
            if group_atomics:
                group = LogicalGroup(
                    group_id=group_id,
                    group_label=f"Criterion {criterion_id} - {operator}",
                    internal_logic=operator,
                    combine_with_others="NOT" if is_exclusion else "AND",
                    is_exclusion=is_exclusion,
                    atomic_ids=group_atomics,
                )
                groups.append(group)

        elif node_type == "temporal":
            # Temporal node - extract the nested operand and process it
            # Temporal nodes have "operand" (singular), not "operands" (plural)
            operand = expression.get("operand", {})
            if operand:
                child_atomics, child_groups = self._process_expression_tree(
                    expression=operand,
                    criterion_id=criterion_id,
                    criterion_type=criterion_type,
                    original_text=original_text,
                    provenance=provenance,
                    omop_index=omop_index,
                    sql_index=sql_index,
                    is_exclusion=is_exclusion,
                    parent_logic=parent_logic,
                    depth=depth + 1,
                )
                atomics.extend(child_atomics)
                groups.extend(child_groups)

        return atomics, groups

    def _create_atomic_from_node(
        self,
        node: Dict[str, Any],
        criterion_id: str,
        node_id: str,
        criterion_type: str,
        provenance: Optional[Dict[str, Any]],
        omop_index: Dict[Tuple[str, str], Dict[str, Any]],
        sql_index: Dict[str, Dict[str, Any]],
        is_exclusion: bool,
        parent_logic: str,
    ) -> Optional[AtomicCriterion]:
        """Create an AtomicCriterion from an expression tree node."""
        self._atomic_counter += 1
        atomic_id = f"A{self._atomic_counter:04d}"

        atomic_text = node.get("atomicText", "")
        if not atomic_text:
            return None

        # Get OMOP mapping
        # Try (criterion_id, node_id) first
        omop_key = (criterion_id, node_id)
        omop_mappings = omop_index.get(omop_key, [])
        omop_mapping = self._find_best_omop_mapping(omop_mappings, atomic_text)

        # Fallback: for simple criteria where Stage 2 uses "root" as nodeId,
        # Stage 5 often uses criterion_id as the atomicId
        if not omop_mapping and node_id == "root":
            omop_key = (criterion_id, criterion_id)
            omop_mappings = omop_index.get(omop_key, [])
            omop_mapping = self._find_best_omop_mapping(omop_mappings, atomic_text)

        # Second fallback: for nodes with numeric IDs, collect all mappings for criterion
        if not omop_mapping and node_id not in ["root", criterion_id]:
            all_mappings = []
            for key, mapping_list in omop_index.items():
                if key[0] == criterion_id:
                    all_mappings.extend(mapping_list)
            if all_mappings:
                omop_mapping = self._find_best_omop_mapping(all_mappings, atomic_text)

        # Get SQL template
        sql_template_data = sql_index.get(criterion_id, {})
        sql_template = None
        component_sql = None

        # Look for component-level SQL
        components = sql_template_data.get("components", [])
        for comp in components:
            if comp.get("atomicId") == node_id:
                component_sql = comp.get("sql")
                break

        # Fall back to criterion-level SQL
        if not component_sql:
            component_sql = sql_template_data.get("sqlTemplate")

        # Check if SQL contains UNMAPPED marker or manual review requirement
        sql_has_unmapped = False
        if component_sql:
            sql_lower = component_sql.lower()
            if "unmapped" in sql_lower or "manual" in sql_lower or "requires" in sql_lower:
                sql_has_unmapped = True

        # Build OMOP query spec
        omop_query = None
        concept_ids = []
        concept_names = []
        vocabulary_ids = []
        concept_codes = []

        if omop_mapping:
            concepts = omop_mapping.get("concepts", [])
            for concept in concepts:
                cid = concept.get("concept_id")
                if cid:
                    concept_ids.append(cid)
                    concept_names.append(concept.get("concept_name", ""))
                    concept_codes.append(concept.get("concept_code", ""))
                    vocab = concept.get("vocabulary_id", "")
                    if vocab and vocab not in vocabulary_ids:
                        vocabulary_ids.append(vocab)

        omop_table = node.get("omopTable", "observation")

        # Extract value constraint from Stage 2 atomic decomposition output
        # Stage 2 produces numericConstraintStructured or numericRangeStructured,
        # which we convert to SQL-compatible value_constraint strings
        value_constraint = node.get("valueConstraint")  # Direct field if present

        if not value_constraint:
            # Convert numericConstraintStructured: {value, operator, unit, parameter}
            numeric_constraint = node.get("numericConstraintStructured")
            if numeric_constraint:
                op = numeric_constraint.get("operator", "")
                val = numeric_constraint.get("value")
                if op and val is not None:
                    value_constraint = f"value_as_number {op} {val}"

        if not value_constraint:
            # Convert numericRangeStructured: {min, max, unit, parameter}
            numeric_range = node.get("numericRangeStructured")
            if numeric_range:
                min_val = numeric_range.get("min")
                max_val = numeric_range.get("max")
                if min_val is not None and max_val is not None:
                    value_constraint = f"value_as_number >= {min_val} AND value_as_number <= {max_val}"
                elif min_val is not None:
                    value_constraint = f"value_as_number >= {min_val}"
                elif max_val is not None:
                    value_constraint = f"value_as_number <= {max_val}"

        # Determine SQL executability - must have concepts and NOT have UNMAPPED marker
        sql_executable = bool(component_sql and concept_ids and not sql_has_unmapped)

        if component_sql or concept_ids:
            omop_query = OmopQuerySpec(
                table_name=omop_table,
                concept_ids=concept_ids,
                concept_names=concept_names,
                vocabulary_ids=vocabulary_ids,
                concept_codes=concept_codes,
                sql_template=component_sql or "",
                sql_executable=sql_executable,
                value_constraint=value_constraint,
            )
            # Regenerate SQL template when:
            # 1. We have value constraints that need to be incorporated, OR
            # 2. We have concept IDs but SQL still has UNMAPPED marker (from fallback mapping)
            if concept_ids and (value_constraint or sql_has_unmapped):
                omop_query.regenerate_sql_template()

        # Generate FHIR query using bridge
        fhir_query_dict = None
        fhir_executable = False
        if concept_ids:
            fhir_spec = self.fhir_bridge.map_omop_to_fhir(
                concept_ids=concept_ids,
                omop_table=omop_table,
            )
            if fhir_spec:
                fhir_query_dict = fhir_spec.to_dict()
                fhir_executable = fhir_spec.query_executable

        # Build provenance
        atomic_provenance = None
        if provenance:
            atomic_provenance = AtomicProvenance(
                page_number=provenance.get("pageNumber"),
                text_snippet=provenance.get("textSnippet"),
                confidence=provenance.get("confidence", 1.0),
            )

        # Build execution context
        execution_context = ExecutionContext(
            logical_group=f"G_{criterion_id}_{node_id}",
            group_logic=parent_logic,
            combine_with_previous="NOT" if is_exclusion else "AND",
            is_exclusion=is_exclusion,
            sequence_hint=self._atomic_counter,
        )

        # =====================================================================
        # STAGE 2 METADATA EXTRACTION (P1 Fix: Preserve clinical metadata)
        # =====================================================================
        # Extract clinical metadata from Stage 2 expression tree node
        # These values are set during atomic decomposition and represent
        # clinical domain knowledge that should be preserved through the pipeline
        stage2_clinical_category = node.get("clinicalCategory")
        stage2_queryable_status = node.get("queryableStatus")
        clinical_concept_group = node.get("clinicalConceptGroup")

        # =====================================================================
        # QUERYABLE STATUS DETERMINATION (with Stage 2 override)
        # =====================================================================
        # Compute status based on OMOP/SQL/FHIR mapping success
        computed_queryable_status = QueryableStatus.FULLY_QUERYABLE.value
        non_queryable_reason = None

        if not concept_ids:
            computed_queryable_status = QueryableStatus.REQUIRES_MANUAL.value
            non_queryable_reason = "No OMOP concepts mapped"
        elif sql_has_unmapped:
            computed_queryable_status = QueryableStatus.REQUIRES_MANUAL.value
            non_queryable_reason = "SQL template requires manual concept selection"
        elif not sql_executable:
            computed_queryable_status = QueryableStatus.PARTIALLY_QUERYABLE.value
            non_queryable_reason = "OMOP concepts mapped but SQL not fully executable"
        elif not fhir_executable:
            # Has SQL but no FHIR - still partially queryable
            if fhir_query_dict is None:
                computed_queryable_status = QueryableStatus.PARTIALLY_QUERYABLE.value
                non_queryable_reason = "OMOP concepts not translatable to FHIR"

        # CRITICAL: Stage 2 can OVERRIDE computed status with more restrictive values
        # Priority order (most restrictive wins):
        #   screening_only > requires_manual > partially_queryable > fully_queryable
        #
        # This ensures that clinical domain knowledge from Stage 2 (e.g., "pathologist
        # report available" being a documentation requirement, not a patient filter)
        # is preserved even if OMOP mapping succeeds.
        queryable_status = computed_queryable_status

        if stage2_queryable_status:
            # Define restrictiveness order
            restrictiveness = {
                "screening_only": 4,
                "requires_manual": 3,
                "partially_queryable": 2,
                "fully_queryable": 1,
            }

            stage2_level = restrictiveness.get(stage2_queryable_status, 0)
            computed_level = restrictiveness.get(computed_queryable_status, 0)

            # Use Stage 2 status if it's more restrictive
            if stage2_level > computed_level:
                queryable_status = stage2_queryable_status
                # Update reason if Stage 2 is screening_only
                if stage2_queryable_status == "screening_only":
                    non_queryable_reason = (
                        "Stage 2 classified as screening_only: site/documentation "
                        "requirement, not a patient filter"
                    )
                elif stage2_queryable_status == "requires_manual" and not non_queryable_reason:
                    non_queryable_reason = "Stage 2 classified as requires_manual review"

                logger.debug(
                    f"Atomic {atomic_id} ({atomic_text[:50]}...): Stage 2 override - "
                    f"computed={computed_queryable_status}, stage2={stage2_queryable_status}, "
                    f"final={queryable_status}"
                )

        # =====================================================================
        # CLINICAL CATEGORY ASSIGNMENT (from Stage 2 if available)
        # =====================================================================
        # Use Stage 2's clinical category if present, otherwise default to "other"
        # for later LLM-based classification
        initial_category = stage2_clinical_category if stage2_clinical_category else "other"

        # Create atomic criterion with full Stage 2 metadata preservation
        return AtomicCriterion(
            atomic_id=atomic_id,
            original_criterion_id=criterion_id,
            criterion_type=criterion_type,
            atomic_text=atomic_text,
            normalized_text=atomic_text,  # Could be enhanced with normalization
            category=initial_category,  # Use Stage 2 category if available
            funnel_impact=FunnelImpact(
                elimination_rate=0.0,  # Will be populated from key_criteria
                impact_score=0.0,
                is_killer_criterion=False,
            ),
            omop_query=omop_query,
            fhir_query=fhir_query_dict,
            execution_context=execution_context,
            provenance=atomic_provenance,
            queryable_status=queryable_status,
            non_queryable_reason=non_queryable_reason,
            # Stage 2 metadata preservation (P1 fix)
            stage2_clinical_category=stage2_clinical_category,
            stage2_queryable_status=stage2_queryable_status,
            clinical_concept_group=clinical_concept_group,
            expression_node_id=node_id,
        )

    # =========================================================================
    # LLM-First Category Assignment
    # =========================================================================

    async def _assign_categories_llm(
        self,
        atomics: List[AtomicCriterion],
        key_criteria: Optional[List[Dict[str, Any]]],
        omop_index: Dict[Tuple[str, str], List[Dict[str, Any]]],
    ) -> None:
        """
        Assign categories and funnel impact using LLM semantic reasoning.

        This replaces keyword-based matching with LLM-powered clinical reasoning
        for better generalization across all protocol types.

        Args:
            atomics: List of atomic criteria to categorize
            key_criteria: Optional key criteria with elimination rates
            omop_index: OMOP mappings for semantic matching
        """
        if not self.use_llm or not self._llm_matcher:
            # Fall back to keyword-based matching
            logger.info("LLM matcher not available, using keyword-based fallback")
            self._assign_categories(atomics, key_criteria)
            return

        logger.info(f"LLM-based category assignment for {len(atomics)} atomics")

        # Prepare atomic data for LLM
        atomic_data = [
            {
                "atomic_id": a.atomic_id,
                "atomic_text": a.atomic_text,
                "criterion_id": a.original_criterion_id,
                "criterion_type": a.criterion_type,
            }
            for a in atomics
        ]

        # Step 1: Match atomics to key criteria for elimination rates (if available)
        if key_criteria:
            try:
                kc_matches = await self._llm_matcher.match_atomics_to_key_criteria(
                    atomics=atomic_data,
                    key_criteria=key_criteria,
                )

                # Apply matched key criteria
                for atomic in atomics:
                    match_info = kc_matches.get(atomic.atomic_id, {})
                    matched_key_id = match_info.get("matched_key_id")

                    if matched_key_id:
                        # Find the matching key criterion
                        matched_kc = next(
                            (kc for kc in key_criteria if kc.get("key_id") == matched_key_id),
                            None
                        )
                        if matched_kc:
                            self._apply_key_criterion(atomic, matched_kc)

                matched_count = sum(
                    1 for a in atomics if a.funnel_impact.elimination_rate > 0
                )
                logger.info(f"LLM key criteria matching: {matched_count}/{len(atomics)} matched")

            except Exception as e:
                logger.warning(f"LLM key criteria matching failed, skipping: {e}")

        # Step 2: Classify any atomics still in "other" category
        unclassified = [a for a in atomics if a.category == "other"]
        if unclassified:
            try:
                unclassified_data = [
                    {
                        "atomic_id": a.atomic_id,
                        "atomic_text": a.atomic_text,
                        "criterion_type": a.criterion_type,
                    }
                    for a in unclassified
                ]

                classifications = await self._llm_matcher.classify_atomics_batch(
                    atomics=unclassified_data,
                )

                # Apply classifications
                for atomic in unclassified:
                    class_info = classifications.get(atomic.atomic_id, {})
                    atomic.category = class_info.get("category", "other")

                classified_count = sum(
                    1 for a in unclassified if a.category != "other"
                )
                logger.info(
                    f"LLM classification: {classified_count}/{len(unclassified)} "
                    f"classified (remaining {len(unclassified) - classified_count} as 'other')"
                )

            except Exception as e:
                logger.warning(f"LLM matcher classification failed: {e}, trying reflection service")
                # Try reflection service as second-tier fallback
                try:
                    reflection_service = LLMReflectionService()
                    for atomic in unclassified:
                        category, confidence = await reflection_service.classify_criterion_category(
                            atomic.atomic_text
                        )
                        atomic.category = category
                        if confidence < 0.6:
                            logger.debug(
                                f"Low confidence ({confidence:.2f}) for '{atomic.atomic_text[:40]}...'"
                            )
                except Exception as e2:
                    logger.warning(f"Reflection service also failed: {e2}, using keyword fallback")
                    for atomic in unclassified:
                        atomic.category = self._infer_category_fallback(atomic.atomic_text)

        # Log category distribution
        from collections import Counter
        cat_counts = Counter(a.category for a in atomics)
        logger.info(f"Category distribution: {dict(cat_counts)}")

    def _assign_categories(
        self,
        atomics: List[AtomicCriterion],
        key_criteria: Optional[List[Dict[str, Any]]],
    ) -> None:
        """
        Assign categories and funnel impact from key criteria.

        Uses three-tier matching strategy:
        1. Exact text match
        2. Substring match (key in atomic or atomic in key)
        3. Fuzzy match with 50%+ Jaccard similarity
        """
        if not key_criteria:
            # Auto-categorize based on atomic text
            for atomic in atomics:
                atomic.category = self._infer_category_fallback(atomic.atomic_text)
            return

        # Build index of key criteria by normalized text (lowercase, stripped)
        key_index = {}
        for kc in key_criteria:
            text = kc.get("text", kc.get("normalizedText", "")).lower().strip()
            key_index[text] = kc

        matched_count = 0

        # Match atomics to key criteria
        for atomic in atomics:
            atomic_lower = atomic.atomic_text.lower().strip()
            matched = False

            # Tier 1: Try exact match first
            if atomic_lower in key_index:
                kc = key_index[atomic_lower]
                self._apply_key_criterion(atomic, kc)
                matched = True
                matched_count += 1

            # Tier 2: Try substring match
            if not matched:
                for key_text, kc in key_index.items():
                    if atomic_lower in key_text or key_text in atomic_lower:
                        self._apply_key_criterion(atomic, kc)
                        matched = True
                        matched_count += 1
                        break

            # Tier 3: Try fuzzy match with 50%+ Jaccard similarity
            if not matched:
                best_similarity = 0.0
                best_kc = None

                for key_text, kc in key_index.items():
                    similarity = self._calculate_jaccard_similarity(atomic_lower, key_text)
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_kc = kc

                if best_similarity >= 0.5 and best_kc:
                    self._apply_key_criterion(atomic, best_kc)
                    matched = True
                    matched_count += 1

            # No match found - infer category from text
            if not matched:
                atomic.category = self._infer_category_fallback(atomic.atomic_text)

        logger.info(
            f"Assigned categories to {len(atomics)} atomics: "
            f"{matched_count} matched to key_criteria, "
            f"{len(atomics) - matched_count} inferred from text"
        )

    def _apply_key_criterion(
        self,
        atomic: AtomicCriterion,
        kc: Dict[str, Any],
    ) -> None:
        """Apply key criterion data to an atomic criterion."""
        atomic.category = kc.get("category", "other")
        atomic.funnel_impact.elimination_rate = kc.get("elimination_rate", 0.0)
        atomic.funnel_impact.is_killer_criterion = kc.get("is_killer", False)

        # Calculate impact score based on elimination rate and killer status
        elimination = atomic.funnel_impact.elimination_rate
        atomic.funnel_impact.impact_score = min(elimination / 100.0, 1.0)
        if atomic.funnel_impact.is_killer_criterion:
            atomic.funnel_impact.impact_score = max(atomic.funnel_impact.impact_score, 0.8)

    def _infer_category_fallback(self, text: str) -> str:
        """
        FALLBACK: Infer category from atomic text.

        Fallback chain:
        1. Try reflection service (LLM-based) - if available
        2. Fall back to keyword patterns - if LLM unavailable

        Categories:
        - demographics, disease_indication, biomarker, treatment_history,
        - functional_status, lab_criteria, safety_exclusion, other
        """
        # Try reflection service first (LLM-based)
        try:
            import asyncio
            reflection_service = LLMReflectionService()
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                category, confidence = loop.run_until_complete(
                    reflection_service.classify_criterion_category(text)
                )
                if confidence >= 0.6:
                    logger.debug(f"Reflection classified '{text[:30]}...' as '{category}' (conf: {confidence})")
                    return category
        except Exception as e:
            logger.debug(f"Reflection service unavailable for category inference: {e}")

        # Fall back to keyword patterns
        logger.warning(f"Using keyword fallback for category: '{text[:50]}...'")
        text_lower = text.lower()

        # Demographics - Age, sex, geographic criteria
        demographics_patterns = [
            "age", "year old", "years old", "≥ 18", ">= 18", "≥18", ">=18",
            "adult", "pediatric", "child", "elderly", "geriatric",
            "male", "female", "sex", "gender",
            "ethnic", "race", "nationality"
        ]
        if any(w in text_lower for w in demographics_patterns):
            return "demographics"

        # Functional status - Performance scores
        functional_patterns = [
            "ecog", "karnofsky", "performance status", "performance score",
            "ambulatory", "self-care", "capable of", "ability to",
            "functional", "mobile", "activities of daily living",
            "life expectancy", "prognosis"
        ]
        if any(w in text_lower for w in functional_patterns):
            return "functional_status"

        # Biomarker - Molecular markers and genetic testing
        biomarker_patterns = [
            "egfr", "alk", "ros1", "braf", "kras", "her2", "pd-l1", "pdl1",
            "mutation", "biomarker", "expression", "receptor", "amplification",
            "translocation", "fusion", "wild-type", "wildtype", "positive", "negative",
            "immunohistochemistry", "ihc", "fish", "ngs", "next-generation sequencing",
            "molecular", "genetic", "genomic", "marker", "testing", "ctdna"
        ]
        if any(w in text_lower for w in biomarker_patterns):
            return "biomarker"

        # Lab criteria - Laboratory measurements and values
        lab_patterns = [
            "anc", "wbc", "platelet", "hemoglobin", "hematocrit",
            "creatinine", "bilirubin", "ast", "alt", "ggt", "alkaline phosphatase",
            "inr", "ptt", "aptt", "albumin", "glucose", "potassium", "sodium",
            "neutrophil", "lymphocyte", "leukocyte", "white blood cell",
            "liver function", "renal function", "kidney function",
            "clearance", "gfr", "egfr clearance", "cockcroft", "mdrd",
            "uln", "lln", "normal limit", "laboratory", "lab value",
            "hba1c", "thyroid", "tsh", "electrolyte", "serum", "plasma",
            "urine", "urinalysis", "blood count", "cbc"
        ]
        if any(w in text_lower for w in lab_patterns):
            return "lab_criteria"

        # Safety exclusion - Contraindications and safety concerns
        safety_patterns = [
            "pregnant", "pregnancy", "nursing", "lactating", "breastfeeding",
            "allergy", "allergic", "hypersensitivity", "contraindication", "contraindicated",
            "brain metastasis", "brain metastases", "cns metastasis", "cns metastases",
            "leptomeningeal", "carcinomatous meningitis",
            "seizure", "epilepsy", "convulsion",
            "cardiac", "cardiovascular", "heart failure", "arrhythmia", "qt prolongation",
            "hepatic", "liver disease", "cirrhosis", "hepatitis",
            "renal impairment", "dialysis", "kidney disease",
            "active infection", "hiv", "hepatitis b", "hepatitis c",
            "autoimmune", "immunodeficiency",
            "psychiatric", "mental illness", "suicidal",
            "substance abuse", "alcohol", "drug abuse",
            "interstitial lung disease", "pneumonitis", "fibrosis",
            "uncontrolled", "unstable", "severe", "significant",
            "exclude", "exclusion", "not eligible", "ineligible"
        ]
        if any(w in text_lower for w in safety_patterns):
            return "safety_exclusion"

        # Treatment history - Prior therapies and interventions
        treatment_patterns = [
            "chemotherapy", "radiation", "radiotherapy", "surgery", "resection",
            "treatment", "therapy", "regimen", "prior", "previous", "received",
            "underwent", "exposed", "treated with",
            "systemic", "targeted", "immunotherapy", "checkpoint inhibitor",
            "anti-pd-1", "anti-pd-l1", "anti-ctla-4",
            "investigational", "experimental", "clinical trial", "study drug",
            "washout", "discontinue", "last dose", "days since",
            "lines of therapy", "first-line", "second-line", "third-line",
            "adjuvant", "neoadjuvant", "maintenance", "consolidation"
        ]
        if any(w in text_lower for w in treatment_patterns):
            return "treatment_history"

        # Disease indication - Primary diagnosis and staging
        disease_patterns = [
            "cancer", "tumor", "tumour", "carcinoma", "adenocarcinoma",
            "nsclc", "sclc", "lung cancer", "breast cancer", "colorectal",
            "disease", "diagnosis", "diagnosed", "confirmed", "histology",
            "histological", "pathological", "cytological", "biopsy",
            "stage", "staging", "tnm", "metastatic", "advanced", "locally advanced",
            "recurrent", "relapsed", "refractory", "progressive",
            "measurable disease", "evaluable disease", "target lesion",
            "squamous", "non-squamous", "adenosquamous",
            "differentiated", "undifferentiated", "grade"
        ]
        if any(w in text_lower for w in disease_patterns):
            return "disease_indication"

        # Administrative criteria (subset of "other")
        administrative_patterns = [
            "consent", "informed consent", "willing", "agree", "compliance",
            "follow-up", "protocol", "study visit", "participate",
            "able to", "capable of", "understanding", "language",
            "geographic", "travel", "access", "availability"
        ]
        if any(w in text_lower for w in administrative_patterns):
            # Keep as "other" but could be "administrative" in future
            return "other"

        return "other"

    def _build_funnel_stages(
        self,
        atomics: List[AtomicCriterion],
    ) -> List[QueryableFunnelStage]:
        """Build funnel stages from categorized atomics."""
        # Group atomics by category
        category_atomics: Dict[str, List[str]] = {}
        for atomic in atomics:
            cat = atomic.category
            if cat not in category_atomics:
                category_atomics[cat] = []
            category_atomics[cat].append(atomic.atomic_id)

        # Build stages in order
        stages: List[QueryableFunnelStage] = []

        for category, (stage_id, stage_name, order) in self._get_category_to_stage().items():
            atomic_ids = category_atomics.get(category, [])
            if not atomic_ids:
                continue

            # Calculate average elimination rate
            avg_elimination = 0.0
            for atomic in atomics:
                if atomic.atomic_id in atomic_ids:
                    avg_elimination += atomic.funnel_impact.elimination_rate
            if atomic_ids:
                avg_elimination /= len(atomic_ids)

            stage = QueryableFunnelStage(
                stage_id=stage_id,
                stage_name=stage_name,
                stage_order=order,
                stage_logic="AND",  # Stages are ANDed by default
                criteria_ids=atomic_ids,
                estimated_elimination_rate=avg_elimination,
            )
            stages.append(stage)

        # Sort by order
        stages.sort(key=lambda s: s.stage_order)
        return stages

    def close(self):
        """Clean up resources."""
        if self.fhir_bridge:
            self.fhir_bridge.close()


# ============================================================================
# Utility Functions
# ============================================================================

async def build_eligibility_funnel_from_files(
    protocol_id: str,
    stage2_path: Path,
    stage5_path: Path,
    stage6_path: Path,
    key_criteria_path: Optional[Path] = None,
    athena_db_path: Optional[str] = None,
    use_llm: bool = True,
) -> QueryableFunnelResult:
    """
    Build eligibility funnel from stage output files (async, LLM-powered).

    Args:
        protocol_id: Protocol identifier
        stage2_path: Path to stage02_result.json
        stage5_path: Path to stage05_result.json
        stage6_path: Path to stage06_result.json
        key_criteria_path: Optional path to key_criteria.json
        athena_db_path: Optional path to ATHENA database
        use_llm: Whether to use LLM for semantic matching (default True)

    Returns:
        QueryableFunnelResult
    """
    # Load stage outputs
    with open(stage2_path, "r", encoding="utf-8") as f:
        stage2_result = json.load(f)

    with open(stage5_path, "r", encoding="utf-8") as f:
        stage5_result = json.load(f)

    with open(stage6_path, "r", encoding="utf-8") as f:
        stage6_result = json.load(f)

    key_criteria = None
    if key_criteria_path and key_criteria_path.exists():
        with open(key_criteria_path, "r", encoding="utf-8") as f:
            kc_data = json.load(f)
            key_criteria = kc_data.get("key_criteria", [])

    # Build funnel using async LLM-based matching
    builder = EligibilityFunnelBuilder(athena_db_path, use_llm=use_llm)
    try:
        return await builder.build_from_stage_outputs(
            protocol_id=protocol_id,
            stage2_result=stage2_result,
            stage5_result=stage5_result,
            stage6_result=stage6_result,
            key_criteria=key_criteria,
        )
    finally:
        builder.close()


def build_eligibility_funnel_from_files_sync(
    protocol_id: str,
    stage2_path: Path,
    stage5_path: Path,
    stage6_path: Path,
    key_criteria_path: Optional[Path] = None,
    athena_db_path: Optional[str] = None,
    use_llm: bool = True,
) -> QueryableFunnelResult:
    """
    Synchronous wrapper for build_eligibility_funnel_from_files.

    Args:
        protocol_id: Protocol identifier
        stage2_path: Path to stage02_result.json
        stage5_path: Path to stage05_result.json
        stage6_path: Path to stage06_result.json
        key_criteria_path: Optional path to key_criteria.json
        athena_db_path: Optional path to ATHENA database
        use_llm: Whether to use LLM for semantic matching (default True)

    Returns:
        QueryableFunnelResult
    """
    return asyncio.run(
        build_eligibility_funnel_from_files(
            protocol_id=protocol_id,
            stage2_path=stage2_path,
            stage5_path=stage5_path,
            stage6_path=stage6_path,
            key_criteria_path=key_criteria_path,
            athena_db_path=athena_db_path,
            use_llm=use_llm,
        )
    )


def save_eligibility_funnel(
    result: QueryableFunnelResult,
    output_dir: Path,
    protocol_id: str,
) -> Path:
    """
    Save eligibility funnel result to JSON file.

    Args:
        result: QueryableFunnelResult to save
        output_dir: Output directory
        protocol_id: Protocol identifier

    Returns:
        Path to saved file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{protocol_id}_eligibility_funnel.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2)

    logger.info(f"Saved eligibility funnel to: {output_path}")
    return output_path


# Backward compatibility aliases
FunnelV2Builder = EligibilityFunnelBuilder
build_v2_funnel_from_files = build_eligibility_funnel_from_files
build_v2_funnel_from_files_sync = build_eligibility_funnel_from_files_sync
save_v2_funnel = save_eligibility_funnel
