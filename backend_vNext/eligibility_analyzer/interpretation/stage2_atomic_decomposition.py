"""
Stage 2: Atomic Decomposition (CRITICAL)

Breaks compound eligibility criteria into SQL-queryable atomic pieces while
preserving AND/OR/AND_NOT logic structure.

This is a CRITICAL stage - the quality of downstream SQL generation and
OMOP mapping depends entirely on correct atomic decomposition.

Key Features:
- AND/OR/AND_NOT logic detection
- Nested logic support (subOptions for OR within AND)
- Structured data extraction (timeFrameStructured, numericConstraintStructured)
- OMOP table pre-assignment
- IF-THEN dependency detection
- Exception clause (EXCEPT, UNLESS) handling
- Gemini 2.5 Pro as primary LLM with Azure OpenAI (gpt-5-mini) fallback

Usage:
    from eligibility_analyzer.interpretation.stage2_atomic_decomposition import (
        AtomicDecomposer,
        decompose_criteria,
    )

    decomposer = AtomicDecomposer()
    result = await decomposer.decompose(criteria_list)
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from openai import AzureOpenAI
from dotenv import load_dotenv
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

load_dotenv()

logger = logging.getLogger(__name__)

# LLM API Configuration
LLM_TIMEOUT_SECONDS = 120  # 2 minute timeout per request
LLM_MAX_RETRIES = 3


# =============================================================================
# CONFIGURATION
# =============================================================================

# Maximum criteria to process in a single batch
BATCH_SIZE = 5

# Load prompt from file - Use expression tree prompt for nested AND/OR/NOT/EXCEPT logic
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "stage2_expression_tree.txt"


def _load_prompt() -> str:
    """Load atomic decomposition prompt from file."""
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding='utf-8')
    else:
        logger.warning(f"Prompt file not found: {PROMPT_PATH}")
        return ""


def _infer_omop_table_from_text(atomic_text: str) -> str:
    """
    Infer OMOP table from atomic text when LLM doesn't specify.

    Uses keyword patterns to make an educated guess, with logging.
    This is a fallback - the LLM prompt should specify omopTable.
    """
    text_lower = atomic_text.lower()

    # Measurement indicators (lab values, vital signs)
    if any(kw in text_lower for kw in [
        "level", "count", "g/dl", "mg/dl", "u/l", "ng/ml", "mmol",
        "hemoglobin", "platelet", "neutrophil", "creatinine", "bilirubin",
        "albumin", "ast", "alt", "inr", "egfr", "anc", "wbc", "hgb",
    ]):
        logger.debug(f"Inferred 'measurement' table for: {atomic_text[:50]}...")
        return "measurement"

    # Drug indicators
    if any(kw in text_lower for kw in [
        "drug", "medication", "therapy", "treatment with", "receiving",
        "chemotherapy", "immunotherapy", "targeted therapy",
    ]):
        logger.debug(f"Inferred 'drug_exposure' table for: {atomic_text[:50]}...")
        return "drug_exposure"

    # Procedure indicators
    if any(kw in text_lower for kw in [
        "surgery", "procedure", "biopsy", "resection", "transplant",
        "radiation", "mastectomy", "colectomy",
    ]):
        logger.debug(f"Inferred 'procedure_occurrence' table for: {atomic_text[:50]}...")
        return "procedure_occurrence"

    # Observation indicators (demographics, functional status)
    if any(kw in text_lower for kw in [
        "age", "ecog", "karnofsky", "kps", "performance status",
        "pregnant", "breastfeeding", "smoking",
    ]):
        logger.debug(f"Inferred 'observation' table for: {atomic_text[:50]}...")
        return "observation"

    # Default to condition_occurrence for diseases
    if any(kw in text_lower for kw in [
        "cancer", "carcinoma", "tumor", "malignant", "metastatic",
        "disease", "disorder", "syndrome", "diagnosis",
    ]):
        logger.debug(f"Inferred 'condition_occurrence' table for: {atomic_text[:50]}...")
        return "condition_occurrence"

    # Final fallback with warning
    logger.warning(
        f"Could not infer OMOP table for '{atomic_text[:50]}...' - "
        f"defaulting to 'observation'. LLM should specify omopTable."
    )
    return "observation"


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class TimeFrameStructured:
    """Structured time constraint."""
    value: float
    unit: str  # days, weeks, months, years
    operator: str  # within, before, after, during
    relative_event: str  # randomization, screening, etc.

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "unit": self.unit,
            "operator": self.operator,
            "relativeEvent": self.relative_event,
        }


@dataclass
class NumericConstraintStructured:
    """Structured numeric constraint (single value with operator)."""
    value: float
    operator: str  # >, <, >=, <=, =
    unit: str
    parameter: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "operator": self.operator,
            "unit": self.unit,
            "parameter": self.parameter,
        }


@dataclass
class NumericRangeStructured:
    """Structured numeric range (min-max)."""
    min_value: float
    max_value: float
    unit: str
    parameter: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min": self.min_value,
            "max": self.max_value,
            "unit": self.unit,
            "parameter": self.parameter,
        }


# =============================================================================
# EXPRESSION TREE DATA CLASSES (Phase 1: AND/OR/NOT + Phase 2: Temporal)
# =============================================================================


@dataclass
class TemporalConstraint:
    """
    Temporal relationship between conditions or relative to an event.

    Supports:
    - WITHIN: condition must occur within X time of anchor (e.g., "within 28 days of screening")
    - BEFORE: condition must occur before anchor (e.g., "before first dose")
    - AFTER: condition must occur after anchor (e.g., "after prior therapy")
    - BETWEEN: condition must occur between two anchors
    """
    operator: str  # WITHIN, BEFORE, AFTER, BETWEEN
    value: Optional[float] = None  # Time value (e.g., 28)
    unit: Optional[str] = None  # days, weeks, months, years
    anchor: str = "reference_date"  # Event anchor (screening, first_dose, randomization, etc.)
    anchor_end: Optional[str] = None  # For BETWEEN: end anchor

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "operator": self.operator,
            "anchor": self.anchor,
        }
        if self.value is not None:
            result["value"] = self.value
        if self.unit:
            result["unit"] = self.unit
        if self.anchor_end:
            result["anchorEnd"] = self.anchor_end
        return result


@dataclass
class ExpressionNode:
    """
    Recursive expression tree node for representing complex boolean logic.

    Node Types:
    - atomic: Leaf node with a single SQL-queryable condition
    - operator: Internal node with AND, OR, NOT, EXCEPT operators
    - temporal: Temporal relationship node (WITHIN, BEFORE, AFTER)

    This design supports arbitrary nesting like:
    - A AND (B OR C) AND NOT D
    - (A WITHIN 7 days of screening) AND (B OR C)
    - A EXCEPT (B AND C)
    """
    node_id: str
    node_type: str  # "atomic", "operator", "temporal"

    # For atomic nodes (leaf)
    atomic_text: Optional[str] = None
    omop_table: Optional[str] = None
    value_constraint: Optional[str] = None
    time_constraint: Optional[str] = None
    time_frame_structured: Optional[TimeFrameStructured] = None
    numeric_constraint_structured: Optional[NumericConstraintStructured] = None
    numeric_range_structured: Optional[NumericRangeStructured] = None
    concept_ids: List[int] = field(default_factory=list)  # Populated by Stage 5
    strategy: str = ""

    # Provenance tracking (for traceability to source document)
    provenance: Optional[Dict[str, Any]] = None  # {page_number: int, text_snippet: str}

    # Clinical metadata (additive layer for UI/feasibility - does not affect downstream processing)
    # Categories: disease_indication, biomarker, prior_therapy, performance_status,
    #            organ_function, safety_exclusion, demographics, diagnostic_confirmation
    clinical_category: Optional[str] = None
    # Status: fully_queryable, partially_queryable, screening_only, requires_manual
    queryable_status: Optional[str] = None
    # Groups related atomics (e.g., "egfr_activating_mutation" for EGFR ex19 + L858R)
    clinical_concept_group: Optional[str] = None

    # For operator nodes (internal)
    operator: Optional[str] = None  # AND, OR, NOT, EXCEPT, IMPLICATION
    operands: List["ExpressionNode"] = field(default_factory=list)

    # For IMPLICATION operator (IF condition THEN requirement)
    # Semantics: NOT(condition) OR (condition AND requirement)
    condition: Optional["ExpressionNode"] = None
    requirement: Optional["ExpressionNode"] = None

    # For temporal nodes
    temporal_constraint: Optional[TemporalConstraint] = None
    temporal_operand: Optional["ExpressionNode"] = None  # The condition with temporal constraint

    def to_dict(self) -> Dict[str, Any]:
        """Convert node to dictionary for JSON serialization."""
        result = {
            "nodeId": self.node_id,
            "nodeType": self.node_type,
        }

        if self.node_type == "atomic":
            result["atomicText"] = self.atomic_text
            result["omopTable"] = self.omop_table
            if self.value_constraint:
                result["valueConstraint"] = self.value_constraint
            if self.time_constraint:
                result["timeConstraint"] = self.time_constraint
            if self.time_frame_structured:
                result["timeFrameStructured"] = self.time_frame_structured.to_dict()
            if self.numeric_constraint_structured:
                result["numericConstraintStructured"] = self.numeric_constraint_structured.to_dict()
            if self.numeric_range_structured:
                result["numericRangeStructured"] = self.numeric_range_structured.to_dict()
            if self.concept_ids:
                result["conceptIds"] = self.concept_ids
            if self.strategy:
                result["strategy"] = self.strategy
            if self.provenance:
                result["provenance"] = self.provenance
            # Clinical metadata (additive layer)
            if self.clinical_category:
                result["clinicalCategory"] = self.clinical_category
            if self.queryable_status:
                result["queryableStatus"] = self.queryable_status
            if self.clinical_concept_group:
                result["clinicalConceptGroup"] = self.clinical_concept_group

        elif self.node_type == "operator":
            result["operator"] = self.operator
            # Handle IMPLICATION operator specially with condition/requirement structure
            if self.operator == "IMPLICATION":
                if self.condition:
                    result["condition"] = self.condition.to_dict()
                if self.requirement:
                    result["requirement"] = self.requirement.to_dict()
            else:
                result["operands"] = [op.to_dict() for op in self.operands]

        elif self.node_type == "temporal":
            if self.temporal_constraint:
                result["temporalConstraint"] = self.temporal_constraint.to_dict()
            if self.temporal_operand:
                result["operand"] = self.temporal_operand.to_dict()

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExpressionNode":
        """Parse expression node from dictionary."""
        node_type = data.get("nodeType", "atomic")
        node_id = data.get("nodeId", "")

        if node_type == "atomic":
            # Parse structured constraints
            time_frame = None
            if data.get("timeFrameStructured"):
                tf = data["timeFrameStructured"]
                time_frame = TimeFrameStructured(
                    value=tf.get("value", 0),
                    unit=tf.get("unit", ""),
                    operator=tf.get("operator", ""),
                    relative_event=tf.get("relativeEvent", ""),
                )

            numeric_constraint = None
            if data.get("numericConstraintStructured"):
                nc = data["numericConstraintStructured"]
                numeric_constraint = NumericConstraintStructured(
                    value=nc.get("value", 0),
                    operator=nc.get("operator", ""),
                    unit=nc.get("unit", ""),
                    parameter=nc.get("parameter", ""),
                )

            numeric_range = None
            if data.get("numericRangeStructured"):
                nr = data["numericRangeStructured"]
                numeric_range = NumericRangeStructured(
                    min_value=nr.get("min", 0),
                    max_value=nr.get("max", 0),
                    unit=nr.get("unit", ""),
                    parameter=nr.get("parameter", ""),
                )

            atomic_text = data.get("atomicText", "")
            omop_table = data.get("omopTable")
            if not omop_table:
                omop_table = _infer_omop_table_from_text(atomic_text)

            return cls(
                node_id=node_id,
                node_type="atomic",
                atomic_text=atomic_text,
                omop_table=omop_table,
                value_constraint=data.get("valueConstraint"),
                time_constraint=data.get("timeConstraint"),
                time_frame_structured=time_frame,
                numeric_constraint_structured=numeric_constraint,
                numeric_range_structured=numeric_range,
                concept_ids=data.get("conceptIds", []),
                strategy=data.get("strategy", ""),
                provenance=data.get("provenance"),
                # Clinical metadata (additive layer)
                clinical_category=data.get("clinicalCategory"),
                queryable_status=data.get("queryableStatus"),
                clinical_concept_group=data.get("clinicalConceptGroup"),
            )

        elif node_type == "operator":
            operator = data.get("operator", "AND")

            # Handle IMPLICATION operator specially with condition/requirement structure
            if operator == "IMPLICATION":
                condition = None
                requirement = None
                if data.get("condition"):
                    condition = cls.from_dict(data["condition"])
                if data.get("requirement"):
                    requirement = cls.from_dict(data["requirement"])
                return cls(
                    node_id=node_id,
                    node_type="operator",
                    operator="IMPLICATION",
                    condition=condition,
                    requirement=requirement,
                )
            else:
                operands = [cls.from_dict(op) for op in data.get("operands", [])]
                return cls(
                    node_id=node_id,
                    node_type="operator",
                    operator=operator,
                    operands=operands,
                )

        elif node_type == "temporal":
            temporal_constraint = None
            if data.get("temporalConstraint"):
                tc = data["temporalConstraint"]
                temporal_constraint = TemporalConstraint(
                    operator=tc.get("operator", "WITHIN"),
                    value=tc.get("value"),
                    unit=tc.get("unit"),
                    anchor=tc.get("anchor", "reference_date"),
                    anchor_end=tc.get("anchorEnd"),
                )

            temporal_operand = None
            if data.get("operand"):
                temporal_operand = cls.from_dict(data["operand"])

            return cls(
                node_id=node_id,
                node_type="temporal",
                temporal_constraint=temporal_constraint,
                temporal_operand=temporal_operand,
            )

        # Default to atomic
        return cls(node_id=node_id, node_type="atomic")

    def get_all_atomics(self) -> List["ExpressionNode"]:
        """Recursively collect all atomic nodes from the expression tree."""
        atomics = []

        if self.node_type == "atomic":
            atomics.append(self)
        elif self.node_type == "operator":
            # Handle IMPLICATION operator with condition/requirement structure
            if self.operator == "IMPLICATION":
                if self.condition:
                    atomics.extend(self.condition.get_all_atomics())
                if self.requirement:
                    atomics.extend(self.requirement.get_all_atomics())
            else:
                for operand in self.operands:
                    atomics.extend(operand.get_all_atomics())
        elif self.node_type == "temporal":
            if self.temporal_operand:
                atomics.extend(self.temporal_operand.get_all_atomics())

        return atomics

    def count_nodes(self) -> int:
        """Count total nodes in the expression tree."""
        count = 1
        if self.node_type == "operator":
            # Handle IMPLICATION operator with condition/requirement structure
            if self.operator == "IMPLICATION":
                if self.condition:
                    count += self.condition.count_nodes()
                if self.requirement:
                    count += self.requirement.count_nodes()
            else:
                for operand in self.operands:
                    count += operand.count_nodes()
        elif self.node_type == "temporal" and self.temporal_operand:
            count += self.temporal_operand.count_nodes()
        return count

    def _normalize_text(self, text: str) -> str:
        """Normalize atomic text for comparison (lowercase, strip, collapse whitespace)."""
        import re
        if not text:
            return ""
        return re.sub(r'\s+', ' ', text.lower().strip())

    def _get_atomic_signature(self) -> str:
        """
        Get a signature for this atomic node for deduplication.
        Combines normalized text + value constraint + time constraint.
        """
        if self.node_type != "atomic":
            return ""
        parts = [self._normalize_text(self.atomic_text or "")]
        if self.value_constraint:
            parts.append(f"val:{self.value_constraint}")
        if self.time_constraint:
            parts.append(f"time:{self.time_constraint}")
        return "|".join(parts)

    def _is_equivalent_atomic(self, other: "ExpressionNode") -> bool:
        """Check if two atomic nodes are semantically equivalent."""
        if self.node_type != "atomic" or other.node_type != "atomic":
            return False
        return self._get_atomic_signature() == other._get_atomic_signature()

    def simplify(self, id_prefix: str = "S") -> "ExpressionNode":
        """
        Simplify the expression tree by:
        1. Removing duplicate atomics within OR/AND branches
        2. Simplifying (A AND B) OR (A AND NOT B) → A
        3. Factorizing common terms: (A AND B) OR (A AND C) → A AND (B OR C)
        4. Flattening nested operators of the same type

        Returns:
            Simplified expression tree (may be a new node or self)
        """
        return self._simplify_recursive(id_prefix, counter=[0])

    def _simplify_recursive(self, id_prefix: str, counter: list) -> "ExpressionNode":
        """Internal recursive simplification."""
        if self.node_type == "atomic":
            return self

        if self.node_type == "temporal":
            if self.temporal_operand:
                self.temporal_operand = self.temporal_operand._simplify_recursive(id_prefix, counter)
            return self

        if self.node_type != "operator":
            return self

        # Handle IMPLICATION operator specially - recursively simplify condition and requirement
        if self.operator == "IMPLICATION":
            if self.condition:
                self.condition = self.condition._simplify_recursive(id_prefix, counter)
            if self.requirement:
                self.requirement = self.requirement._simplify_recursive(id_prefix, counter)
            # IMPLICATION nodes are preserved as-is (don't collapse)
            return self

        # First, recursively simplify all operands (for AND/OR/NOT/EXCEPT)
        simplified_operands = []
        for op in self.operands:
            simplified_operands.append(op._simplify_recursive(id_prefix, counter))
        self.operands = simplified_operands

        # Flatten nested operators of the same type: (A AND (B AND C)) → (A AND B AND C)
        self._flatten_nested_operators()

        # Remove duplicate atomics within this operator
        self._deduplicate_atomics()

        # Try boolean simplifications
        simplified = self._apply_boolean_simplifications(id_prefix, counter)

        # If only one operand remains, return it directly
        # BUT preserve NOT operators (they have semantic meaning with 1 operand)
        # Also preserve EXCEPT as it has specific two-operand semantics
        if len(simplified.operands) == 1 and simplified.operator not in ("NOT", "EXCEPT"):
            return simplified.operands[0]

        return simplified

    def _flatten_nested_operators(self) -> None:
        """Flatten nested operators of the same type. E.g., (A AND (B AND C)) → (A AND B AND C)."""
        if self.node_type != "operator" or not self.operator:
            return

        flattened = []
        for operand in self.operands:
            if (operand.node_type == "operator" and
                operand.operator == self.operator and
                self.operator in ("AND", "OR")):
                # Absorb children of same-type nested operator
                flattened.extend(operand.operands)
            else:
                flattened.append(operand)
        self.operands = flattened

    def _deduplicate_atomics(self) -> None:
        """Remove duplicate atomic nodes within an operator's operands."""
        if self.node_type != "operator":
            return

        seen_signatures = set()
        unique_operands = []

        for operand in self.operands:
            if operand.node_type == "atomic":
                sig = operand._get_atomic_signature()
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    unique_operands.append(operand)
                else:
                    logger.debug(f"Removing duplicate atomic: {operand.atomic_text[:50]}...")
            else:
                unique_operands.append(operand)

        if len(unique_operands) < len(self.operands):
            logger.info(f"Deduplicated {len(self.operands) - len(unique_operands)} atomic(s) from {self.operator} operator")
            self.operands = unique_operands

    def _apply_boolean_simplifications(self, id_prefix: str, counter: list) -> "ExpressionNode":
        """
        Apply boolean algebra simplifications:
        1. (A AND B) OR (A AND C) → A AND (B OR C)  [Factorization - preserves structure]
        2. A OR A → A  [Idempotence - handled by dedup]
        3. A AND A → A  [Idempotence - handled by dedup]

        NOTE: Complementary elimination (A AND B) OR (A AND NOT B) → A is DISABLED.
        While mathematically correct, it removes semantic information about negation
        that is important for eligibility criteria audit/provenance. The original
        criterion structure (e.g., current vs former smoker distinction) should be
        preserved even if logically equivalent to a simpler form.
        """
        if self.node_type != "operator" or self.operator != "OR":
            return self

        # Only attempt simplification on OR nodes with AND children
        and_children = [op for op in self.operands if op.node_type == "operator" and op.operator == "AND"]
        other_children = [op for op in self.operands if op not in and_children]

        if len(and_children) < 2:
            return self

        # NOTE: Complementary elimination is DISABLED to preserve semantic structure.
        # The original criterion's NOT operators should be maintained for audit trail.
        # Uncomment if full boolean simplification is desired:
        # simplified = self._try_complementary_elimination(and_children, other_children, id_prefix, counter)
        # if simplified:
        #     return simplified

        # Check for factorization: (A AND B) OR (A AND C) → A AND (B OR C)
        simplified = self._try_factorization(and_children, other_children, id_prefix, counter)
        if simplified:
            return simplified

        return self

    def _try_complementary_elimination(
        self,
        and_children: List["ExpressionNode"],
        other_children: List["ExpressionNode"],
        id_prefix: str,
        counter: list
    ) -> Optional["ExpressionNode"]:
        """
        Try to simplify (A AND B) OR (A AND NOT B) → A

        This pattern occurs when the same condition appears in both branches of an OR,
        combined with complementary conditions (B and NOT B).
        """
        if len(and_children) != 2:
            return None

        branch1, branch2 = and_children

        # Get atomic signatures from each branch
        atomics1 = {op._get_atomic_signature(): op for op in branch1.operands if op.node_type == "atomic"}
        atomics2 = {op._get_atomic_signature(): op for op in branch2.operands if op.node_type == "atomic"}

        # Find common atomics
        common_sigs = set(atomics1.keys()) & set(atomics2.keys())

        if not common_sigs:
            return None

        # Check if the non-common parts are complements (B vs NOT B)
        unique1 = [op for op in branch1.operands if op.node_type != "atomic" or op._get_atomic_signature() not in common_sigs]
        unique2 = [op for op in branch2.operands if op.node_type != "atomic" or op._get_atomic_signature() not in common_sigs]

        # Simple case: exact complement check
        # If one branch has B and other has NOT(B), they're complements
        # For now, check if they're atomics with same text but one is negated structurally
        is_complement = self._check_complement_pair(unique1, unique2)

        if is_complement and len(common_sigs) > 0:
            # Complementary elimination: keep only the common part
            common_atomics = [atomics1[sig] for sig in common_sigs]

            logger.info(
                f"Simplified (A AND B) OR (A AND NOT B) → A: "
                f"eliminated complementary conditions, keeping {len(common_atomics)} common atomic(s)"
            )

            if len(common_atomics) == 1:
                return common_atomics[0]
            else:
                counter[0] += 1
                return ExpressionNode(
                    node_id=f"{id_prefix}_simp_{counter[0]}",
                    node_type="operator",
                    operator="AND",
                    operands=common_atomics
                )

        return None

    def _check_complement_pair(
        self,
        operands1: List["ExpressionNode"],
        operands2: List["ExpressionNode"]
    ) -> bool:
        """
        Check if two sets of operands represent complementary conditions.

        E.g., [B] and [NOT B], or [smoked recently] and [NOT smoked recently]
        """
        # Simple case: one operand in each set
        if len(operands1) == 1 and len(operands2) == 1:
            op1, op2 = operands1[0], operands2[0]

            # Check for NOT operator wrapping same atomic
            if op1.node_type == "operator" and op1.operator == "NOT" and len(op1.operands) == 1:
                if op1.operands[0]._is_equivalent_atomic(op2):
                    return True

            if op2.node_type == "operator" and op2.operator == "NOT" and len(op2.operands) == 1:
                if op2.operands[0]._is_equivalent_atomic(op1):
                    return True

            # Check for semantic complements (e.g., "smoked within past year" vs "not smoked within past year")
            if op1.node_type == "atomic" and op2.node_type == "atomic":
                text1 = self._normalize_text(op1.atomic_text or "")
                text2 = self._normalize_text(op2.atomic_text or "")

                # Check common complement patterns
                if self._are_semantic_complements(text1, text2):
                    return True

        return False

    def _are_semantic_complements(self, text1: str, text2: str) -> bool:
        """
        Check if two atomic texts are semantic complements.

        E.g., "smoking event occurred" vs "no smoking event occurred"
        Or: "smoked within past year" vs "not smoked within past year"
        """
        # Normalize both texts
        t1, t2 = text1.lower().strip(), text2.lower().strip()

        # Check for explicit NOT patterns
        negation_patterns = [
            ("not ", ""),
            ("no ", ""),
            ("without ", "with "),
            ("absence of ", "presence of "),
            ("never ", ""),
        ]

        for neg, pos in negation_patterns:
            # Check if one is negation of other
            if t1.startswith(neg) and t1[len(neg):] == t2:
                return True
            if t2.startswith(neg) and t2[len(neg):] == t1:
                return True
            if t1.replace(neg, pos) == t2 or t2.replace(neg, pos) == t1:
                return True

        return False

    def _try_factorization(
        self,
        and_children: List["ExpressionNode"],
        other_children: List["ExpressionNode"],
        id_prefix: str,
        counter: list
    ) -> Optional["ExpressionNode"]:
        """
        Try to factorize: (A AND B) OR (A AND C) → A AND (B OR C)

        This reduces redundancy when the same condition appears in multiple OR branches.
        """
        if len(and_children) < 2:
            return None

        # Collect atomic signatures from all AND branches
        branch_atomics = []
        for branch in and_children:
            atomics = {}
            for op in branch.operands:
                if op.node_type == "atomic":
                    atomics[op._get_atomic_signature()] = op
            branch_atomics.append(atomics)

        # Find atomics common to ALL branches
        common_sigs = set(branch_atomics[0].keys())
        for atomics in branch_atomics[1:]:
            common_sigs &= set(atomics.keys())

        if not common_sigs:
            return None

        # Extract common factors
        common_factors = [branch_atomics[0][sig] for sig in common_sigs]

        # Build remaining terms for each branch (what's left after factoring out common)
        remaining_branches = []
        for i, branch in enumerate(and_children):
            remaining = [op for op in branch.operands
                        if op.node_type != "atomic" or op._get_atomic_signature() not in common_sigs]
            if remaining:
                if len(remaining) == 1:
                    remaining_branches.append(remaining[0])
                else:
                    counter[0] += 1
                    remaining_branches.append(ExpressionNode(
                        node_id=f"{id_prefix}_rem_{counter[0]}",
                        node_type="operator",
                        operator="AND",
                        operands=remaining
                    ))

        # If factorization produces simpler result
        # Case 1: common factors AND remaining branches (normal factorization)
        # Case 2: common factors only, no remaining (branches were identical - idempotence)
        if len(common_factors) > 0 and len(remaining_branches) == 0:
            # All atomics were common - branches were identical
            # (A AND B) OR (A AND B) = A AND B
            logger.info(
                f"Deduplicated identical OR branches: extracted {len(common_factors)} common factor(s), "
                f"eliminated {len(and_children) - 1} redundant branch(es)"
            )

            if len(common_factors) == 1:
                return common_factors[0]

            counter[0] += 1
            return ExpressionNode(
                node_id=f"{id_prefix}_and_{counter[0]}",
                node_type="operator",
                operator="AND",
                operands=common_factors
            )

        if len(common_factors) > 0 and len(remaining_branches) > 0:
            logger.info(
                f"Factorized expression: extracted {len(common_factors)} common factor(s) "
                f"from {len(and_children)} AND branches"
            )

            # Build: common_factors AND (remaining_branches OR other_children)
            counter[0] += 1
            or_node = ExpressionNode(
                node_id=f"{id_prefix}_or_{counter[0]}",
                node_type="operator",
                operator="OR",
                operands=remaining_branches + other_children
            )

            # If remaining OR is trivial (one element), skip it
            if len(or_node.operands) == 1:
                final_operands = common_factors + [or_node.operands[0]]
            elif len(or_node.operands) == 0:
                final_operands = common_factors
            else:
                final_operands = common_factors + [or_node]

            if len(final_operands) == 1:
                return final_operands[0]

            counter[0] += 1
            return ExpressionNode(
                node_id=f"{id_prefix}_and_{counter[0]}",
                node_type="operator",
                operator="AND",
                operands=final_operands
            )

        return None


@dataclass
class AtomicCriterion:
    """Single atomic criterion (SQL-queryable piece)."""
    atomic_id: str
    atomic_text: str
    omop_table: str
    value_constraint: Optional[str] = None
    time_constraint: Optional[str] = None
    time_frame_structured: Optional[TimeFrameStructured] = None
    numeric_constraint_structured: Optional[NumericConstraintStructured] = None
    numeric_range_structured: Optional[NumericRangeStructured] = None
    and_not: Optional[str] = None  # Exception clause
    depends_on: Optional[str] = None  # IF-THEN dependency
    condition_type: Optional[str] = None  # if_then
    has_sub_options: bool = False
    sub_options: List["AtomicCriterion"] = field(default_factory=list)
    strategy: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "atomicId": self.atomic_id,
            "atomicText": self.atomic_text,
            "omopTable": self.omop_table,
            "valueConstraint": self.value_constraint,
            "timeConstraint": self.time_constraint,
            "timeFrameStructured": self.time_frame_structured.to_dict() if self.time_frame_structured else None,
            "numericConstraintStructured": self.numeric_constraint_structured.to_dict() if self.numeric_constraint_structured else None,
            "numericRangeStructured": self.numeric_range_structured.to_dict() if self.numeric_range_structured else None,
            "strategy": self.strategy,
        }

        # Only include optional fields if present
        if self.and_not:
            result["AND_NOT"] = self.and_not
        if self.depends_on:
            result["dependsOn"] = self.depends_on
            result["conditionType"] = self.condition_type
        if self.has_sub_options:
            result["hasSubOptions"] = True
            result["subOptions"] = [so.to_dict() for so in self.sub_options]

        return result


@dataclass
class CriterionOption:
    """Option for OR-logic criteria."""
    option_id: str
    description: str  # includePatientIf or excludePatientIf
    is_inclusion: bool
    and_not: Optional[str] = None
    strategy: str = ""
    conditions: List[AtomicCriterion] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "optionId": self.option_id,
            "strategy": self.strategy,
            "conditions": [c.to_dict() for c in self.conditions],
        }

        if self.is_inclusion:
            result["includePatientIf"] = self.description
        else:
            result["excludePatientIf"] = self.description

        if self.and_not:
            result["AND_NOT"] = self.and_not

        return result


@dataclass
class DecomposedCriterion:
    """Decomposed criterion with atomic pieces and logic structure."""
    criterion_id: str
    original_text: str
    criterion_type: str  # Inclusion or Exclusion
    logic_operator: str  # AND or OR
    has_nested_logic: bool = False
    decomposition_strategy: str = ""
    atomic_criteria: List[AtomicCriterion] = field(default_factory=list)
    options: List[CriterionOption] = field(default_factory=list)
    provenance: Optional[Dict[str, Any]] = None

    # NEW: Expression tree for complex nested logic (Phase 1 & 2)
    expression: Optional[ExpressionNode] = None
    use_expression_tree: bool = False  # Flag to indicate expression tree is available

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "criterionId": self.criterion_id,
            "originalText": self.original_text,
            "type": self.criterion_type,
            "logicOperator": self.logic_operator,
            "decompositionStrategy": self.decomposition_strategy,
        }

        if self.has_nested_logic:
            result["hasNestedLogic"] = True

        # Include expression tree if available (new format)
        if self.use_expression_tree and self.expression:
            result["expression"] = self.expression.to_dict()
            result["useExpressionTree"] = True
        else:
            # Backward compatible: use flat format
            if self.logic_operator == "AND":
                result["atomicCriteria"] = [ac.to_dict() for ac in self.atomic_criteria]
            else:
                result["options"] = [opt.to_dict() for opt in self.options]

        if self.provenance:
            result["provenance"] = self.provenance

        return result

    def get_all_atomic_texts(self) -> List[str]:
        """Get all atomic texts from either expression tree or flat format."""
        if self.use_expression_tree and self.expression:
            return [node.atomic_text for node in self.expression.get_all_atomics() if node.atomic_text]
        elif self.logic_operator == "AND":
            return [ac.atomic_text for ac in self.atomic_criteria]
        else:
            texts = []
            for opt in self.options:
                texts.extend([c.atomic_text for c in opt.conditions])
            return texts


@dataclass
class AtomicDecompositionResult:
    """Result from Stage 2."""
    success: bool
    decomposed_criteria: List[DecomposedCriterion] = field(default_factory=list)
    total_atomics: int = 0
    total_options: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "decomposedCriteria": [dc.to_dict() for dc in self.decomposed_criteria],
            "counts": {
                "criteria": len(self.decomposed_criteria),
                "atomics": self.total_atomics,
                "options": self.total_options,
            },
            "errors": self.errors,
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _clean_json(text: str) -> str:
    """
    Extract JSON from LLM response.

    Handles:
    - Markdown code fences (```json ... ```)
    - JSON embedded in text (finds first { to last })
    - Plain JSON
    """
    import re
    text = text.strip()

    # Try to extract JSON from markdown code block
    if "```json" in text:
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return match.group(1).strip()

    if "```" in text:
        match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return match.group(1).strip()

    # Try to find JSON object in the text
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace:last_brace + 1]

    # Return as-is if nothing found
    return text


def _parse_atomic_criterion(data: Dict[str, Any]) -> AtomicCriterion:
    """Parse atomic criterion from LLM response."""
    # Parse structured time frame
    time_frame = None
    if data.get("timeFrameStructured"):
        tf = data["timeFrameStructured"]
        time_frame = TimeFrameStructured(
            value=tf.get("value", 0),
            unit=tf.get("unit", ""),
            operator=tf.get("operator", ""),
            relative_event=tf.get("relativeEvent", ""),
        )

    # Parse structured numeric constraint
    numeric_constraint = None
    if data.get("numericConstraintStructured"):
        nc = data["numericConstraintStructured"]
        numeric_constraint = NumericConstraintStructured(
            value=nc.get("value", 0),
            operator=nc.get("operator", ""),
            unit=nc.get("unit", ""),
            parameter=nc.get("parameter", ""),
        )

    # Parse structured numeric range
    numeric_range = None
    if data.get("numericRangeStructured"):
        nr = data["numericRangeStructured"]
        numeric_range = NumericRangeStructured(
            min_value=nr.get("min", 0),
            max_value=nr.get("max", 0),
            unit=nr.get("unit", ""),
            parameter=nr.get("parameter", ""),
        )

    # Parse sub-options
    sub_options = []
    if data.get("hasSubOptions") and data.get("subOptions"):
        for so in data["subOptions"]:
            sub_options.append(_parse_atomic_criterion(so))

    # Infer OMOP table if not specified by LLM
    atomic_text = data.get("atomicText", "")
    omop_table = data.get("omopTable")
    if not omop_table:
        omop_table = _infer_omop_table_from_text(atomic_text)

    return AtomicCriterion(
        atomic_id=str(data.get("atomicId", "")),
        atomic_text=atomic_text,
        omop_table=omop_table,
        value_constraint=data.get("valueConstraint"),
        time_constraint=data.get("timeConstraint"),
        time_frame_structured=time_frame,
        numeric_constraint_structured=numeric_constraint,
        numeric_range_structured=numeric_range,
        and_not=data.get("AND_NOT"),
        depends_on=data.get("dependsOn"),
        condition_type=data.get("conditionType"),
        has_sub_options=data.get("hasSubOptions", False),
        sub_options=sub_options,
        strategy=data.get("strategy", ""),
    )


def _parse_option(data: Dict[str, Any], is_inclusion: bool) -> CriterionOption:
    """Parse criterion option from LLM response."""
    conditions = []
    for cond in data.get("conditions", []):
        conditions.append(_parse_atomic_criterion(cond))

    description = data.get("includePatientIf") if is_inclusion else data.get("excludePatientIf")
    if not description:
        description = data.get("includePatientIf") or data.get("excludePatientIf") or ""

    return CriterionOption(
        option_id=data.get("optionId", ""),
        description=description,
        is_inclusion=is_inclusion,
        and_not=data.get("AND_NOT"),
        strategy=data.get("strategy", ""),
        conditions=conditions,
    )


# =============================================================================
# MAIN DECOMPOSER CLASS
# =============================================================================


class AtomicDecomposer:
    """
    Stage 2: Atomic Decomposition.

    Breaks compound eligibility criteria into SQL-queryable atomic pieces
    while preserving logic structure.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-pro",
        timeout_seconds: int = LLM_TIMEOUT_SECONDS
    ):
        """
        Initialize the decomposer.

        Args:
            api_key: Gemini API key (falls back to env var)
            model: Gemini model to use
            timeout_seconds: Timeout for LLM API calls
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")

        self.model = model
        self.timeout_seconds = timeout_seconds

        # Initialize Gemini client
        genai.configure(api_key=self.api_key)
        self.gemini_model = genai.GenerativeModel(model)
        self.prompt_template = _load_prompt()

        # Initialize Azure OpenAI fallback client
        self._azure_client: Optional[AzureOpenAI] = None
        self._azure_deployment: Optional[str] = None
        self._init_azure_fallback()

        logger.info(f"AtomicDecomposer initialized with model: {model}, timeout: {timeout_seconds}s")

    def _init_azure_fallback(self) -> None:
        """Initialize Azure OpenAI client for fallback."""
        azure_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
        azure_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-01-preview")

        if azure_key and azure_endpoint:
            try:
                self._azure_client = AzureOpenAI(
                    api_key=azure_key,
                    api_version=azure_version,
                    azure_endpoint=azure_endpoint,
                    timeout=float(self.timeout_seconds)
                )
                self._azure_deployment = azure_deployment
                logger.info(f"Azure OpenAI fallback initialized: {azure_deployment}")
            except Exception as e:
                logger.warning(f"Failed to initialize Azure OpenAI fallback: {e}")
        else:
            logger.info("Azure OpenAI credentials not found - fallback disabled")

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if error is retryable (transient failures)."""
        error_str = str(error).lower()
        retryable_patterns = [
            "503", "504", "429", "rate limit", "deadline",
            "timeout", "resource exhausted", "connection", "overloaded"
        ]
        return any(p in error_str for p in retryable_patterns)

    def _should_fallback(self, error: Exception) -> bool:
        """Check if error warrants fallback to Azure OpenAI."""
        error_str = str(error).lower()
        fallback_patterns = [
            "quota", "billing", "payment", "subscription",
            "api key", "authentication", "permission", "blocked",
            "safety", "content filtered"
        ]
        return any(p in error_str for p in fallback_patterns)

    async def _call_azure_openai_fallback(self, prompt: str) -> Optional[str]:
        """
        Call Azure OpenAI as fallback when Gemini fails.

        Args:
            prompt: The prompt to send

        Returns:
            Response text or None if failed
        """
        if not self._azure_client or not self._azure_deployment:
            logger.warning("Azure OpenAI fallback not available")
            return None

        try:
            logger.info(f"Calling Azure OpenAI fallback ({self._azure_deployment})...")
            response = await asyncio.to_thread(
                self._azure_client.chat.completions.create,
                model=self._azure_deployment,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a clinical protocol analyst specializing in eligibility criteria decomposition. Return only valid JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=8192,
                response_format={"type": "json_object"}
            )

            if response and response.choices:
                content = response.choices[0].message.content
                if content and len(content.strip()) >= 10:
                    logger.info("Azure OpenAI fallback succeeded")
                    return content

        except Exception as e:
            logger.error(f"Azure OpenAI fallback failed: {e}")

        return None

    async def _repair_malformed_json(
        self,
        malformed_json: str,
        parse_error: str,
        criterion_id: str,
        max_retries: int = 2
    ) -> Optional[str]:
        """
        Use LLM to repair malformed JSON response.

        This implements the reflection loop pattern: when JSON parsing fails,
        we send the malformed JSON back to the LLM with the error message
        and ask it to fix the issue.

        Args:
            malformed_json: The malformed JSON string
            parse_error: The JSON parse error message
            criterion_id: For logging
            max_retries: Maximum repair attempts

        Returns:
            Repaired JSON string or None if repair failed
        """
        repair_prompt = f"""The following JSON response has a syntax error and cannot be parsed.

ERROR: {parse_error}

MALFORMED JSON:
```json
{malformed_json[:4000]}
```

Please fix the JSON syntax error and return ONLY the corrected JSON.
Do not include any explanation or markdown code fences - return raw JSON only.
Ensure all strings are properly quoted, all brackets are balanced, and there are no trailing commas."""

        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting JSON repair for {criterion_id} (attempt {attempt + 1}/{max_retries})")

                # Try Gemini first with timeout
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.gemini_model.generate_content,
                            repair_prompt,
                            generation_config={"max_output_tokens": 8192}
                        ),
                        timeout=60  # Shorter timeout for repair
                    )
                    if response and response.text:
                        repaired = _clean_json(response.text)
                        # Validate the repair worked
                        json.loads(repaired)
                        logger.info(f"JSON repair succeeded for {criterion_id} on attempt {attempt + 1}")
                        return repaired
                except json.JSONDecodeError:
                    logger.debug(f"Gemini repair attempt {attempt + 1} still produced invalid JSON")
                except asyncio.TimeoutError:
                    logger.warning(f"Gemini JSON repair timed out for {criterion_id}, trying Azure...")
                except Exception as e:
                    logger.debug(f"Gemini repair failed: {e}")

                # Try Azure fallback for repair with timeout
                if self._azure_client and self._azure_deployment:
                    try:
                        response = await asyncio.wait_for(
                            asyncio.to_thread(
                                self._azure_client.chat.completions.create,
                                model=self._azure_deployment,
                                messages=[
                                    {"role": "system", "content": "You are a JSON repair assistant. Fix the JSON syntax error and return only valid JSON."},
                                    {"role": "user", "content": repair_prompt}
                                ],
                                max_completion_tokens=8192,
                                response_format={"type": "json_object"}
                            ),
                            timeout=60  # Shorter timeout for repair
                        )
                        if response and response.choices:
                            repaired = response.choices[0].message.content
                            if repaired:
                                # Validate
                                json.loads(repaired)
                                logger.info(f"Azure JSON repair succeeded for {criterion_id}")
                                return repaired
                    except json.JSONDecodeError:
                        logger.debug(f"Azure repair attempt still produced invalid JSON")
                    except asyncio.TimeoutError:
                        logger.warning(f"Azure JSON repair timed out for {criterion_id}")
                    except Exception as e:
                        logger.debug(f"Azure repair failed: {e}")

            except Exception as e:
                logger.warning(f"JSON repair attempt {attempt + 1} failed: {e}")

        logger.error(f"JSON repair failed after {max_retries} attempts for {criterion_id}")
        return None

    async def decompose(
        self,
        criteria: List[Dict[str, Any]],
        resolved_references: Optional[Dict[str, str]] = None
    ) -> AtomicDecompositionResult:
        """
        Decompose all criteria into atomic pieces.

        Args:
            criteria: List of raw criteria from Phase 2
            resolved_references: Optional resolved cross-references

        Returns:
            AtomicDecompositionResult with all decomposed criteria
        """
        if not self.prompt_template:
            return AtomicDecompositionResult(
                success=False,
                errors=["Prompt template not loaded"]
            )

        decomposed = []
        errors = []
        total_atomics = 0
        total_options = 0

        # Process in batches with PARALLEL LLM calls within each batch
        for i in range(0, len(criteria), BATCH_SIZE):
            batch = criteria[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            logger.info(f"Processing batch {batch_num} ({len(batch)} criteria) in parallel")

            # Create tasks for parallel processing
            tasks = [
                self._decompose_single(criterion, resolved_references)
                for criterion in batch
            ]

            # Execute all tasks in parallel with timeout and handle exceptions individually
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=300  # 5 minutes per batch of criteria
                )
            except asyncio.TimeoutError:
                logger.error(f"Batch {batch_num} timed out after 300s - marking all as failed")
                results = [TimeoutError(f"Batch {batch_num} timed out")] * len(tasks)

            # Process results, handling any exceptions
            for criterion, result in zip(batch, results):
                criterion_id = criterion.get('criterionId', '?')

                if isinstance(result, Exception):
                    logger.error(f"Failed to decompose criterion {criterion_id}: {result}")
                    errors.append(f"Criterion {criterion_id}: {str(result)}")
                    continue

                decomposed.append(result)

                # Count atomics and options
                if result.use_expression_tree and result.expression:
                    # Expression tree: count atomics recursively
                    total_atomics += len(result.expression.get_all_atomics())
                elif result.logic_operator == "AND":
                    total_atomics += len(result.atomic_criteria)
                    # Count sub-options too
                    for ac in result.atomic_criteria:
                        if ac.has_sub_options:
                            total_atomics += len(ac.sub_options)
                else:
                    total_options += len(result.options)
                    for opt in result.options:
                        total_atomics += len(opt.conditions)

        logger.info(f"Stage 2 complete: {len(decomposed)} criteria, {total_atomics} atomics, {total_options} options")

        return AtomicDecompositionResult(
            success=len(errors) == 0,
            decomposed_criteria=decomposed,
            total_atomics=total_atomics,
            total_options=total_options,
            errors=errors,
        )

    @retry(
        stop=stop_after_attempt(LLM_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=lambda retry_state: (
            retry_state.outcome.exception() is not None and
            any(p in str(retry_state.outcome.exception()).lower()
                for p in ["503", "504", "429", "rate limit", "overloaded", "resource exhausted"])
        ),
        before_sleep=lambda retry_state: logger.warning(
            f"Retrying LLM call (attempt {retry_state.attempt_number}/{LLM_MAX_RETRIES}): {retry_state.outcome.exception()}"
        )
    )
    async def _call_llm_with_retry(self, prompt: str) -> str:
        """
        Call Gemini API with retry logic for transient failures.

        Args:
            prompt: The prompt to send to Gemini

        Returns:
            Response text from Gemini
        """
        # Run Gemini call in thread pool with timeout to avoid blocking/hanging
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.gemini_model.generate_content,
                    prompt,
                    generation_config={"max_output_tokens": 8192}
                ),
                timeout=self.timeout_seconds  # Default 120 seconds
            )
        except asyncio.TimeoutError:
            raise RuntimeError(f"Gemini API call timed out after {self.timeout_seconds}s")

        # Validate response
        if not response or not response.text:
            raise ValueError("Empty response from Gemini API")

        response_text = response.text
        if not response_text or len(response_text.strip()) < 10:
            raise ValueError(f"Invalid response from Gemini API: response too short ({len(response_text)} chars)")

        return response_text

    async def _decompose_single(
        self,
        criterion: Dict[str, Any],
        resolved_references: Optional[Dict[str, str]] = None
    ) -> DecomposedCriterion:
        """
        Decompose a single criterion.

        Args:
            criterion: Raw criterion dict
            resolved_references: Optional resolved cross-references

        Returns:
            DecomposedCriterion with atomic pieces
        """
        criterion_id = criterion.get("criterionId", "")
        original_text = criterion.get("originalText", "")
        criterion_type = criterion.get("type", "Inclusion")
        provenance = criterion.get("provenance")

        # Build note about cross-references if any
        note_text = ""
        cross_refs = criterion.get("crossReferences", [])
        if cross_refs and resolved_references:
            note_parts = ["REFERENCED CONTENT:"]
            for xref in cross_refs:
                target = xref.get("targetSection", "")
                if target in resolved_references:
                    note_parts.append(f"\n{target}:\n{resolved_references[target]}")
            if len(note_parts) > 1:
                note_text = "\n".join(note_parts)

        # Build prompt
        prompt = self.prompt_template.format(
            criterion_text=original_text,
            note_text=note_text if note_text else ""
        )

        # Call Gemini with retry logic, with Azure fallback
        response_text = None
        try:
            response_text = await self._call_llm_with_retry(prompt)
        except Exception as gemini_error:
            # Check if this is an error that warrants fallback
            if self._should_fallback(gemini_error) or self._is_retryable_error(gemini_error):
                logger.warning(f"Gemini API error for criterion {criterion_id}: {gemini_error}")
                logger.info("Attempting Azure OpenAI fallback...")
                response_text = await self._call_azure_openai_fallback(prompt)
                if not response_text:
                    raise ValueError(f"Both Gemini and Azure fallback failed for criterion {criterion_id}")
            else:
                raise

        # Parse response - validate JSON structure with reflection-based repair
        cleaned_json = _clean_json(response_text)
        data = None
        try:
            data = json.loads(cleaned_json)
        except json.JSONDecodeError as e:
            logger.warning(f"Initial JSON parse failed for {criterion_id}: {e}")
            logger.debug(f"Raw response: {response_text[:500]}...")

            # Attempt JSON repair using reflection loop
            repaired_json = await self._repair_malformed_json(
                malformed_json=cleaned_json,
                parse_error=str(e),
                criterion_id=criterion_id
            )

            if repaired_json:
                try:
                    data = json.loads(repaired_json)
                    logger.info(f"Successfully parsed repaired JSON for {criterion_id}")
                except json.JSONDecodeError as repair_error:
                    logger.error(f"Repaired JSON still invalid for {criterion_id}: {repair_error}")
                    raise ValueError(f"JSON repair failed - still invalid: {repair_error}")
            else:
                raise ValueError(f"Invalid JSON response from LLM and repair failed: {e}")

        # Validate required fields
        if not isinstance(data, dict):
            raise ValueError(f"Expected dict response, got {type(data).__name__}")

        # Build result
        strategy = data.get("decompositionStrategy", "")
        use_expression_tree = data.get("useExpressionTree", False)

        # Only warn about missing logicOperator when NOT using expression tree
        # (expression tree uses operator field in the tree itself, not logicOperator)
        if "logicOperator" not in data:
            if not use_expression_tree:
                logger.warning(f"Response missing logicOperator for {criterion_id}, defaulting to AND")
            data["logicOperator"] = "AND"  # Silent default for expression trees

        is_inclusion = criterion_type == "Inclusion"

        # Initialize result values
        expression = None
        atomic_criteria = []
        options = []
        logic_operator = "AND"  # Default
        has_nested = False

        if use_expression_tree and data.get("expression"):
            # NEW: Parse expression tree response
            expression = ExpressionNode.from_dict(data["expression"])
            has_nested = True  # Expression trees inherently support nested logic

            # Count atomics before simplification
            atomics_before = len(expression.get_all_atomics())

            # Debug: Log raw expression tree structure before simplification
            logger.debug(f"Raw expression tree for {criterion_id} (before simplification): {expression.to_dict()}")

            # Apply simplification pass: deduplicate atomics, apply boolean algebra
            # This handles cases like (A AND B) OR (A AND NOT B) → A
            expression = expression.simplify(id_prefix=f"{criterion_id}_S")
            atomics_after = len(expression.get_all_atomics())

            if atomics_before != atomics_after:
                logger.info(f"Simplification for {criterion_id}: {atomics_before} → {atomics_after} atomics (eliminated {atomics_before - atomics_after})")
            else:
                logger.debug(f"No simplification possible for {criterion_id} ({atomics_after} atomics)")

            # Determine logic operator from root node
            if expression.node_type == "operator":
                logic_operator = expression.operator or "AND"

            logger.debug(f"Parsed expression tree for {criterion_id} with {atomics_after} atomic nodes (after simplification)")
        else:
            # Backward compatible: parse flat format
            logic_operator = data.get("logicOperator", "AND")
            has_nested = data.get("hasNestedLogic", False)

            # Parse atomic criteria (for AND logic)
            if logic_operator == "AND":
                for ac_data in data.get("atomicCriteria", []):
                    atomic_criteria.append(_parse_atomic_criterion(ac_data))

            # Parse options (for OR logic)
            if logic_operator == "OR":
                for opt_data in data.get("options", []):
                    options.append(_parse_option(opt_data, is_inclusion))

        return DecomposedCriterion(
            criterion_id=criterion_id,
            original_text=original_text,
            criterion_type=criterion_type,
            logic_operator=logic_operator,
            has_nested_logic=has_nested,
            decomposition_strategy=strategy,
            atomic_criteria=atomic_criteria,
            options=options,
            provenance=provenance,
            expression=expression,
            use_expression_tree=use_expression_tree,
        )


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================


async def decompose_criteria(
    criteria: List[Dict[str, Any]],
    resolved_references: Optional[Dict[str, str]] = None
) -> AtomicDecompositionResult:
    """
    Convenience function to decompose criteria.

    Args:
        criteria: List of raw criteria from Phase 2
        resolved_references: Optional resolved cross-references

    Returns:
        AtomicDecompositionResult
    """
    decomposer = AtomicDecomposer()
    return await decomposer.decompose(criteria, resolved_references)


# =============================================================================
# CLI SUPPORT
# =============================================================================


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # Test with sample criteria
    sample_criteria = [
        {
            "criterionId": "INC_001",
            "originalText": "Age >= 18 years AND (ECOG performance status 0 OR 1) AND measurable disease per RECIST v1.1",
            "type": "Inclusion",
        },
        {
            "criterionId": "EXC_001",
            "originalText": "History of any of the following within 6 months: a) Myocardial infarction b) Unstable angina c) Deep vein thrombosis (EXCEPT if associated with central venous access complication)",
            "type": "Exclusion",
        },
    ]

    async def main():
        decomposer = AtomicDecomposer()
        result = await decomposer.decompose(sample_criteria)

        print(f"\n{'='*60}")
        print("ATOMIC DECOMPOSITION RESULTS")
        print(f"{'='*60}")

        if result.success:
            print(f"Success: {result.success}")
            print(f"Criteria: {len(result.decomposed_criteria)}")
            print(f"Total Atomics: {result.total_atomics}")
            print(f"Total Options: {result.total_options}")

            for dc in result.decomposed_criteria:
                print(f"\n{dc.criterion_id} [{dc.logic_operator}]:")
                print(f"  Strategy: {dc.decomposition_strategy[:100]}...")

                if dc.logic_operator == "AND":
                    for ac in dc.atomic_criteria:
                        print(f"    - {ac.atomic_id}: {ac.atomic_text[:50]}...")
                else:
                    for opt in dc.options:
                        print(f"    - Option {opt.option_id}: {opt.description[:50]}...")
        else:
            print(f"Failed with errors: {result.errors}")

    asyncio.run(main())
