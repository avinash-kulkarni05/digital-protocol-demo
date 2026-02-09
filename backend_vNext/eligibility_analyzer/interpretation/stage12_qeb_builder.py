"""
Stage 12: Queryable Eligibility Block (QEB) Builder.

Transforms atomic criteria into queryable blocks for the feasibility application.
Each QEB maps 1:1 to an original protocol criterion with combined SQL,
LLM-generated clinical names, and proper deduplication.

Key features:
- LLM-first design: All categorization, staging, and naming done by LLM
- No hardcoded mappings or predefined funnel stages
- Combined SQL implementing full AND/OR/NOT logic
- Deduplication of OMOP concepts within each QEB
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Set

import google.generativeai as genai
from dotenv import load_dotenv

from ..feasibility.qeb_models import (
    QueryableEligibilityBlock,
    QEBFunnelStage,
    QEBOutput,
    QEBSummary,
    QEBExecutionGuide,
    OMOPConceptRef,
    FHIRResourceRef,
    CDISCBiomedicalConcept,
    QEBProvenance,
    ClinicalSummary,
    ClinicalConceptGroup,
    ScreeningOnlyRequirement,
    save_qeb_output,
    # Data source-aware classification models
    QueryableStatus,
    DataSourceType,
    DataSourceClassification,
    NlpQuerySpec,
)

load_dotenv()

logger = logging.getLogger(__name__)


class Stage12QEBBuilder:
    """
    Stage 12: Queryable Eligibility Block Builder.

    Builds QEBs from atomic criteria, where each QEB maps 1:1 to an original
    protocol criterion with combined SQL and LLM-generated clinical context.
    """

    STAGE_NUMBER = 12
    STAGE_NAME = "QEB Builder"
    GEMINI_MODEL = "gemini-2.5-pro"  # For clinical naming and assessment
    MAX_OUTPUT_TOKENS = 65536  # Maximum output tokens for Gemini 2.5 Pro
    LLM_RETRY_ATTEMPTS = 3  # Number of retry attempts for LLM calls
    LLM_RETRY_DELAY = 2  # Seconds between retries

    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize Stage 12 QEB Builder.

        Args:
            output_dir: Directory for output files.
        """
        self.output_dir = output_dir
        self._gemini_client = None
        self._prompts_dir = Path(__file__).parent.parent / "prompts"
        self._llm_warnings: List[str] = []  # Track LLM failures for output

        logger.info(f"Stage {self.STAGE_NUMBER} ({self.STAGE_NAME}) initialized")

    @property
    def gemini_client(self):
        """Lazy initialization of Gemini client."""
        if self._gemini_client is None:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not set in environment")
            genai.configure(api_key=api_key)
            self._gemini_client = genai.GenerativeModel(self.GEMINI_MODEL)
        return self._gemini_client

    def _load_prompt(self, prompt_name: str) -> str:
        """Load a prompt template from file."""
        prompt_path = self._prompts_dir / prompt_name
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    async def _call_llm_with_retry(
        self,
        prompt: str,
        operation_name: str,
        temperature: float = 0.3,
    ) -> Optional[str]:
        """
        Call LLM with retry logic and error tracking.

        Args:
            prompt: The prompt to send to the LLM.
            operation_name: Name of the operation for logging.
            temperature: LLM temperature setting.

        Returns:
            Response text if successful, None if all retries failed.
        """
        import asyncio as aio

        last_error = None
        for attempt in range(self.LLM_RETRY_ATTEMPTS):
            try:
                response = await self.gemini_client.generate_content_async(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=temperature,
                        max_output_tokens=self.MAX_OUTPUT_TOKENS,
                    ),
                )
                return response.text.strip()
            except Exception as e:
                last_error = e
                if attempt < self.LLM_RETRY_ATTEMPTS - 1:
                    logger.warning(
                        f"LLM {operation_name} attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {self.LLM_RETRY_DELAY}s..."
                    )
                    await aio.sleep(self.LLM_RETRY_DELAY)
                else:
                    warning_msg = f"LLM {operation_name} failed after {self.LLM_RETRY_ATTEMPTS} attempts: {last_error}"
                    logger.warning(warning_msg)
                    self._llm_warnings.append(warning_msg)

        return None

    def _parse_llm_json_response(self, result_text: str) -> Optional[Any]:
        """
        Parse JSON from LLM response, handling markdown code blocks.

        Args:
            result_text: Raw LLM response text.

        Returns:
            Parsed JSON object or None if parsing fails.
        """
        if not result_text:
            return None

        # Remove markdown code blocks if present
        text = result_text.strip()
        if text.startswith("```"):
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}")
            self._llm_warnings.append(f"JSON parse error: {e}")
            return None

    async def run(
        self,
        eligibility_funnel: Dict[str, Any],
        stage2_result: Dict[str, Any],
        raw_criteria: List[Dict[str, Any]],
        protocol_id: str,
        therapeutic_area: Optional[str] = None,
        eligibility_page_start: Optional[int] = None,
        eligibility_page_end: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Build QEBs from atomic criteria.

        Args:
            eligibility_funnel: Output from Stage 11 eligibility funnel builder.
            stage2_result: Output from Stage 2 atomic decomposition.
            raw_criteria: Original extracted criteria.
            protocol_id: Protocol identifier.
            therapeutic_area: Optional therapeutic area for context.
            eligibility_page_start: First page of eligibility section in PDF.
            eligibility_page_end: Last page of eligibility section in PDF.

        Returns:
            Stage result dictionary containing QEB output.
        """
        # Store page range for use in summary
        self._eligibility_page_start = eligibility_page_start
        self._eligibility_page_end = eligibility_page_end
        start_time = time.time()
        logger.info(f"Starting Stage {self.STAGE_NUMBER}: {self.STAGE_NAME}")

        # Reset LLM warnings for this run
        self._llm_warnings = []

        try:
            # Extract data from inputs
            atomics = eligibility_funnel.get("atomicCriteria", [])
            logical_groups = eligibility_funnel.get("logicalGroups", [])
            decomposed_criteria = stage2_result.get("decomposedCriteria", [])

            if not atomics:
                return self._error_result("No atomic criteria found in eligibility funnel", start_time)

            logger.info(f"Processing {len(atomics)} atomics from eligibility funnel")

            # Step 0a: Classify data sources for each atomic (NEW: data source-aware)
            data_source_classifications = await self._classify_data_sources_batch(
                atomics, therapeutic_area
            )
            logger.info(f"Classified data sources for {len(data_source_classifications)} atomics")

            # Step 0b: Add atomic-level queryability classification using data sources
            atomics = await self._classify_atomic_queryability_batch(
                atomics, therapeutic_area, data_source_classifications
            )
            logger.info("Classified queryability for all atomics")

            # Step 1: Group atomics by original criterion ID
            grouped_atomics = self._group_atomics_by_criterion(atomics)
            logger.info(f"Grouped into {len(grouped_atomics)} criteria with atomics")

            # Step 1b: ATOMIC COUNT RECONCILIATION VALIDATION (P2 Fix)
            # This validates that all atomics from Stage 2 expression trees
            # made it through the eligibility funnel processing
            atomic_validation = self._validate_atomic_counts(
                grouped_atomics=grouped_atomics,
                decomposed_criteria=decomposed_criteria,
            )
            if not atomic_validation["is_valid"]:
                # Add validation warnings to LLM warnings for visibility
                self._llm_warnings.extend(atomic_validation["warnings"])

            # Step 2: Build expression tree lookup
            expression_lookup = self._build_expression_lookup(decomposed_criteria)

            # Step 3: Build SQL lookup from atomics
            sql_lookup = self._build_sql_lookup(atomics)

            # Step 4: Create raw QEBs with combined SQL for criteria with atomics
            raw_qebs = []
            for criterion_id, criterion_atomics in grouped_atomics.items():
                qeb = self._build_raw_qeb(
                    criterion_id=criterion_id,
                    atomics=criterion_atomics,
                    expression_lookup=expression_lookup,
                    sql_lookup=sql_lookup,
                    raw_criteria=raw_criteria,
                )
                raw_qebs.append(qeb)

            # Step 4b: Add QEBs for criteria WITHOUT atomics (mark as requires_manual)
            missing_qebs = self._create_qebs_for_missing_criteria(
                raw_criteria=raw_criteria,
                existing_criterion_ids=set(grouped_atomics.keys()),
                expression_lookup=expression_lookup,
            )
            if missing_qebs:
                logger.info(f"Added {len(missing_qebs)} QEBs for criteria without atomics")
                raw_qebs.extend(missing_qebs)

            logger.info(f"Built {len(raw_qebs)} raw QEBs total")

            # Step 5: LLM-powered clinical naming (batch)
            qebs_with_names = await self._generate_clinical_names_batch(
                raw_qebs, therapeutic_area
            )
            logger.info("Generated clinical names for all QEBs")

            # Step 6: LLM-powered queryable status assessment
            qebs_assessed = await self._assess_queryable_status_batch(
                qebs_with_names, therapeutic_area
            )
            logger.info("Assessed queryable status for all QEBs")

            # Step 7: LLM-powered funnel stage clustering
            qebs_with_stages, funnel_stages = await self._cluster_into_funnel_stages(
                qebs_assessed, therapeutic_area, protocol_id
            )
            logger.info(f"Clustered into {len(funnel_stages)} funnel stages")

            # Step 8: LLM-powered killer criteria identification
            killer_ids = await self._identify_killer_criteria(
                qebs_with_stages, therapeutic_area
            )
            logger.info(f"Identified {len(killer_ids)} killer criteria")

            # Update killer status on QEBs (set True if in killer_ids, False otherwise)
            killer_ids_set = set(killer_ids)
            for qeb in qebs_with_stages:
                qeb.is_killer_criterion = qeb.qeb_id in killer_ids_set

            # Step 9: Build logical groups for validation UI
            logical_groups = self._build_logical_groups(qebs_with_stages, atomics)
            logger.info(f"Built {len(logical_groups)} logical groups for validation UI")

            # Step 10: Build final QEB output
            duration = time.time() - start_time
            qeb_output = self._build_qeb_output(
                qebs=qebs_with_stages,
                funnel_stages=funnel_stages,
                protocol_id=protocol_id,
                therapeutic_area=therapeutic_area,
                atomics=atomics,
                logical_groups=logical_groups,
                llm_warnings=self._llm_warnings,
                processing_time=duration,
            )

            # Step 10: Save output (after setting processing time)
            if self.output_dir:
                output_path = save_qeb_output(qeb_output, self.output_dir, protocol_id)
                logger.info(f"Saved QEB output to: {output_path}")

            logger.info(
                f"Stage {self.STAGE_NUMBER} complete in {duration:.2f}s: "
                f"{len(qebs_with_stages)} QEBs, {len(funnel_stages)} stages"
            )

            return {
                "success": True,
                "stage": self.STAGE_NUMBER,
                "stage_name": self.STAGE_NAME,
                "duration_seconds": duration,
                "qeb_output": qeb_output.to_dict(),
                "summary": qeb_output.summary.to_dict(),
                "llm_warnings": self._llm_warnings,
                # Atomic count validation results (P2 Fix)
                "atomic_validation": atomic_validation,
                "atomic_validation_passed": atomic_validation["is_valid"],
            }

        except Exception as e:
            logger.error(f"Stage {self.STAGE_NUMBER} failed: {e}", exc_info=True)
            return self._error_result(str(e), start_time)

    def _error_result(self, error_msg: str, start_time: float) -> Dict[str, Any]:
        """Create an error result dictionary."""
        return {
            "success": False,
            "stage": self.STAGE_NUMBER,
            "stage_name": self.STAGE_NAME,
            "error": error_msg,
            "duration_seconds": time.time() - start_time,
        }

    # =========================================================================
    # ATOMIC COUNT RECONCILIATION VALIDATION (P2 Fix)
    # =========================================================================

    def _validate_atomic_counts(
        self,
        grouped_atomics: Dict[str, List[Dict[str, Any]]],
        decomposed_criteria: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Validate that atomic counts match between Stage 2 and eligibility funnel.

        This is a critical validation to catch bugs in expression tree processing,
        especially for complex operators like IMPLICATION, EXCEPT, and nested structures.

        Args:
            grouped_atomics: Atomics from eligibility funnel, grouped by criterion ID.
            decomposed_criteria: Stage 2 decomposition output with expression trees.

        Returns:
            Dictionary containing validation results:
            - is_valid: True if all counts match
            - mismatches: List of criteria with count mismatches
            - warnings: List of warning messages
            - total_stage2_atomics: Total atomics expected from Stage 2
            - total_funnel_atomics: Total atomics received in funnel
        """
        mismatches = []
        warnings = []
        total_stage2_atomics = 0
        total_funnel_atomics = 0

        # Build lookup from Stage 2 data
        for criterion in decomposed_criteria:
            criterion_id = criterion.get("criterionId")
            if not criterion_id:
                continue

            expression_tree = criterion.get("expression")
            if not expression_tree:
                continue

            # Count leaf (atomic) nodes in Stage 2 expression tree
            stage2_leaf_count = len(self._collect_leaf_nodes(expression_tree))
            total_stage2_atomics += stage2_leaf_count

            # Count atomics that arrived in funnel for this criterion
            funnel_atomics = grouped_atomics.get(criterion_id, [])
            funnel_count = len(funnel_atomics)
            total_funnel_atomics += funnel_count

            # Check for mismatch
            if stage2_leaf_count != funnel_count:
                mismatch_info = {
                    "criterionId": criterion_id,
                    "stage2_count": stage2_leaf_count,
                    "funnel_count": funnel_count,
                    "difference": stage2_leaf_count - funnel_count,
                    "expression_operators": self._get_expression_operators(expression_tree),
                }
                mismatches.append(mismatch_info)

                # Log detailed warning
                warning_msg = (
                    f"ATOMIC COUNT MISMATCH: {criterion_id} - "
                    f"Stage 2 has {stage2_leaf_count} atomics, funnel has {funnel_count} "
                    f"(missing {stage2_leaf_count - funnel_count}). "
                    f"Operators in tree: {mismatch_info['expression_operators']}"
                )
                warnings.append(warning_msg)
                logger.warning(warning_msg)

        # Check for criteria in funnel but not in Stage 2 (orphan atomics)
        stage2_criterion_ids = {c.get("criterionId") for c in decomposed_criteria if c.get("criterionId")}
        for criterion_id in grouped_atomics:
            if criterion_id not in stage2_criterion_ids:
                warning_msg = (
                    f"ORPHAN ATOMICS: {criterion_id} has {len(grouped_atomics[criterion_id])} "
                    f"atomics in funnel but no Stage 2 expression tree"
                )
                warnings.append(warning_msg)
                logger.warning(warning_msg)

        is_valid = len(mismatches) == 0 and len(warnings) == len([w for w in warnings if "ORPHAN" in w])

        validation_result = {
            "is_valid": is_valid,
            "mismatches": mismatches,
            "warnings": warnings,
            "total_stage2_atomics": total_stage2_atomics,
            "total_funnel_atomics": total_funnel_atomics,
            "criteria_with_mismatches": len(mismatches),
            "validation_timestamp": datetime.now().isoformat(),
        }

        if is_valid:
            logger.info(
                f"Atomic count validation PASSED: {total_stage2_atomics} Stage 2 atomics "
                f"matched {total_funnel_atomics} funnel atomics across {len(decomposed_criteria)} criteria"
            )
        else:
            logger.error(
                f"Atomic count validation FAILED: {len(mismatches)} criteria have count mismatches. "
                f"Stage 2: {total_stage2_atomics}, Funnel: {total_funnel_atomics}"
            )

        return validation_result

    def _get_expression_operators(self, expression_tree: Dict[str, Any]) -> List[str]:
        """
        Extract all operators from an expression tree for debugging.

        Args:
            expression_tree: Expression tree from Stage 2.

        Returns:
            List of operator names found in the tree.
        """
        operators = []
        self._collect_operators_recursive(expression_tree, operators)
        return list(set(operators))  # Unique operators

    def _collect_operators_recursive(
        self,
        node: Dict[str, Any],
        operators: List[str],
    ) -> None:
        """Recursively collect all operators from expression tree."""
        if not node:
            return

        node_type = node.get("nodeType", "")

        if node_type == "operator":
            operator = node.get("operator", "")
            if operator:
                operators.append(operator)

            # Handle IMPLICATION which has condition/requirement
            if operator == "IMPLICATION":
                condition = node.get("condition", {})
                requirement = node.get("requirement", {})
                if condition:
                    self._collect_operators_recursive(condition, operators)
                if requirement:
                    self._collect_operators_recursive(requirement, operators)
            else:
                # Standard operators use operands
                for operand in node.get("operands", []):
                    self._collect_operators_recursive(operand, operators)

        elif node_type == "temporal":
            operators.append("TEMPORAL")
            operand = node.get("operand", {})
            if operand:
                self._collect_operators_recursive(operand, operators)

    def _group_atomics_by_criterion(
        self,
        atomics: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group atomics by their originalCriterionId.

        Args:
            atomics: List of atomic criteria from eligibility funnel.

        Returns:
            Dictionary mapping criterion_id to list of atomics.
        """
        grouped = {}
        for atomic in atomics:
            criterion_id = atomic.get("originalCriterionId", "UNKNOWN")
            if criterion_id not in grouped:
                grouped[criterion_id] = []
            grouped[criterion_id].append(atomic)
        return grouped

    def _build_expression_lookup(
        self,
        decomposed_criteria: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Build a lookup from criterion ID to expression tree.

        Args:
            decomposed_criteria: Stage 2 decomposition output.

        Returns:
            Dictionary mapping criterion_id to expression tree.
        """
        lookup = {}
        for criterion in decomposed_criteria:
            criterion_id = criterion.get("criterionId")
            if criterion_id and criterion.get("expression"):
                lookup[criterion_id] = criterion
        return lookup

    def _build_sql_lookup(
        self,
        atomics: List[Dict[str, Any]],
    ) -> Dict[str, str]:
        """
        Build a lookup from atomic ID to SQL template.

        Args:
            atomics: List of atomic criteria.

        Returns:
            Dictionary mapping atomicId to sqlTemplate.
        """
        lookup = {}
        for atomic in atomics:
            atomic_id = atomic.get("atomicId")
            sql_template = (atomic.get("omopQuery") or {}).get("sqlTemplate", "")
            if atomic_id and sql_template:
                lookup[atomic_id] = sql_template
        return lookup

    def _build_raw_qeb(
        self,
        criterion_id: str,
        atomics: List[Dict[str, Any]],
        expression_lookup: Dict[str, Dict[str, Any]],
        sql_lookup: Dict[str, str],
        raw_criteria: List[Dict[str, Any]],
    ) -> QueryableEligibilityBlock:
        """
        Build a raw QEB from grouped atomics with combined SQL.

        Args:
            criterion_id: The original criterion ID (INC_1, EXC_5, etc.)
            atomics: List of atomics belonging to this criterion.
            expression_lookup: Lookup for expression trees.
            sql_lookup: Lookup for SQL templates.
            raw_criteria: Original extracted criteria for provenance.

        Returns:
            QueryableEligibilityBlock with combined SQL.
        """
        # Determine criterion type from first atomic
        first_atomic = atomics[0] if atomics else {}
        criterion_type = first_atomic.get("criterionType", "inclusion")

        # Get expression tree from Stage 2
        criterion_data = expression_lookup.get(criterion_id, {})
        expression_tree = criterion_data.get("expression")
        original_text = criterion_data.get("originalText", "")

        # Build atomic ID to node ID mapping
        node_to_atomic = self._map_nodes_to_atomics(atomics, expression_tree)

        # Build combined SQL from expression tree
        combined_sql, logic_explanation = self._build_combined_sql(
            expression_tree=expression_tree,
            sql_lookup=sql_lookup,
            node_to_atomic=node_to_atomic,
        )

        # Determine internal logic complexity
        internal_logic = self._determine_internal_logic(expression_tree)

        # Collect and deduplicate OMOP concepts
        omop_concepts = self._deduplicate_omop_concepts(atomics)

        # Collect FHIR resources
        fhir_resources = self._collect_fhir_resources(atomics)

        # Enrich with CDISC Biomedical Concepts (cross-pipeline consistency)
        biomedical_concepts = self._enrich_with_biomedical_concepts(omop_concepts, atomics)

        # Get provenance
        provenance = self._get_provenance(criterion_id, raw_criteria, criterion_data)

        # Determine initial queryable status from atomics
        queryable_status = self._aggregate_queryable_status(atomics)

        # Calculate atomic IDs
        atomic_ids = [a.get("atomicId", "") for a in atomics]

        # Build clinical summary (additive layer for UI/feasibility)
        # Uses expression tree to extract clinical metadata (clinicalCategory, queryableStatus, clinicalConceptGroup)
        clinical_summary = self._build_clinical_summary(
            atomics, original_text, expression_tree, node_to_atomic,
            criterion_type=criterion_type, internal_logic=internal_logic
        )

        return QueryableEligibilityBlock(
            qeb_id=f"QEB_{criterion_id}",
            original_criterion_id=criterion_id,
            criterion_type=criterion_type,
            clinical_name="",  # To be filled by LLM
            clinical_description="",  # To be filled by LLM
            clinical_category="",  # To be filled by LLM
            funnel_stage="",  # To be filled by LLM
            funnel_stage_order=0,  # To be filled by LLM
            combined_sql=combined_sql,
            sql_logic_explanation=logic_explanation,
            queryable_status=queryable_status,
            non_queryable_reason=None,
            estimated_elimination_rate=0.0,  # To be filled by LLM
            is_killer_criterion=False,  # To be filled by LLM
            atomic_ids=atomic_ids,
            atomic_count=len(atomics),
            internal_logic=internal_logic,
            omop_concepts=omop_concepts,
            fhir_resources=fhir_resources,
            biomedical_concepts=biomedical_concepts,
            protocol_text=original_text,
            provenance=provenance,
            clinical_summary=clinical_summary,
        )

    def _map_nodes_to_atomics(
        self,
        atomics: List[Dict[str, Any]],
        expression_tree: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        """
        Map expression tree node IDs to atomic IDs using multiple strategies.

        Strategies (in order of preference):
        1. LogicalGroup pattern matching (e.g., "G_INC_3_1a1" -> node "1a1")
        2. AtomicId suffix matching (e.g., atomic "A0003" -> node containing "3")
        3. Position-based matching for simple trees
        """
        mapping = {}
        if not expression_tree:
            return mapping

        # Collect leaf nodes from expression tree
        leaf_nodes = self._collect_leaf_nodes(expression_tree)
        if not leaf_nodes:
            return mapping

        # Strategy 1: LogicalGroup pattern matching
        for atomic in atomics:
            atomic_id = atomic.get("atomicId", "")
            logical_group = atomic.get("executionContext", {}).get("logicalGroup", "")

            if logical_group:
                # Extract node ID from logical group (e.g., "G_INC_3_1a1" -> "1a1")
                parts = logical_group.split("_")
                if len(parts) >= 4:
                    node_id = "_".join(parts[3:])
                    mapping[node_id] = atomic_id
                elif len(parts) >= 3:
                    node_id = parts[-1]
                    mapping[node_id] = atomic_id

        # Strategy 2: Try to match remaining unmapped atomics by ID patterns
        mapped_atomic_ids = set(mapping.values())
        unmapped_atomics = [a for a in atomics if a.get("atomicId", "") not in mapped_atomic_ids]

        if unmapped_atomics:
            unmapped_nodes = [n.get("nodeId", "") for n in leaf_nodes if n.get("nodeId", "") not in mapping]

            # Try matching by atomic ID number suffix to node ID
            for atomic in unmapped_atomics:
                atomic_id = atomic.get("atomicId", "")
                # Extract number from atomic ID (e.g., "A0003" -> "3" or "0003")
                atomic_num = atomic_id.lstrip("A0") if atomic_id.startswith("A") else ""

                for node_id in unmapped_nodes:
                    if node_id not in mapping:
                        # Check if node ID contains the atomic number
                        if atomic_num and atomic_num in node_id:
                            mapping[node_id] = atomic_id
                            break

        # Strategy 3: Position-based fallback for simple 1:1 cases
        if len(unmapped_atomics) == len([n for n in leaf_nodes if n.get("nodeId", "") not in mapping]):
            # Same count of unmapped items - try position matching
            still_unmapped_nodes = [n.get("nodeId", "") for n in leaf_nodes if n.get("nodeId", "") not in mapping]
            still_unmapped_atomics = [a for a in atomics if a.get("atomicId", "") not in set(mapping.values())]

            for node_id, atomic in zip(still_unmapped_nodes, still_unmapped_atomics):
                if node_id and node_id not in mapping:
                    mapping[node_id] = atomic.get("atomicId", "")

        return mapping

    def _collect_leaf_nodes(
        self,
        node: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Recursively collect all atomic (leaf) nodes from expression tree."""
        leaves = []
        node_type = node.get("nodeType", "")

        if node_type == "atomic":
            leaves.append(node)
        elif node_type == "operator":
            operator = node.get("operator", "")

            # Handle IMPLICATION operator which has condition/requirement instead of operands
            if operator == "IMPLICATION":
                condition = node.get("condition", {})
                requirement = node.get("requirement", {})
                if condition:
                    leaves.extend(self._collect_leaf_nodes(condition))
                if requirement:
                    leaves.extend(self._collect_leaf_nodes(requirement))
            else:
                # Standard operators (AND, OR, NOT, EXCEPT) use operands
                for operand in node.get("operands", []):
                    leaves.extend(self._collect_leaf_nodes(operand))
        elif node_type == "temporal":
            # Temporal nodes have "operand" (singular) containing nested expression
            operand = node.get("operand", {})
            if operand:
                leaves.extend(self._collect_leaf_nodes(operand))

        return leaves

    def _extract_leaf_metadata(
        self,
        expression_tree: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Extract clinical metadata from expression tree leaf nodes.

        Creates a mapping from node ID to clinical metadata for use in
        building clinical summaries.

        Args:
            expression_tree: The expression tree from Stage 2.

        Returns:
            Dictionary mapping nodeId to {clinicalCategory, queryableStatus, clinicalConceptGroup, atomicText}.
        """
        metadata = {}
        leaf_nodes = self._collect_leaf_nodes(expression_tree)

        for node in leaf_nodes:
            node_id = node.get("nodeId", "")
            if node_id:
                metadata[node_id] = {
                    "clinicalCategory": node.get("clinicalCategory", "other"),
                    "queryableStatus": node.get("queryableStatus", "fully_queryable"),
                    "clinicalConceptGroup": node.get("clinicalConceptGroup"),
                    "atomicText": node.get("atomicText", ""),
                    "strategy": node.get("strategy", ""),
                }

        return metadata

    def _build_combined_sql(
        self,
        expression_tree: Optional[Dict[str, Any]],
        sql_lookup: Dict[str, str],
        node_to_atomic: Dict[str, str],
    ) -> Tuple[str, str]:
        """
        Build combined SQL from expression tree using INTERSECT/UNION/EXCEPT.

        Args:
            expression_tree: The expression tree from Stage 2.
            sql_lookup: Mapping from atomic ID to SQL template.
            node_to_atomic: Mapping from node ID to atomic ID.

        Returns:
            Tuple of (combined_sql, logic_explanation).
        """
        if not expression_tree:
            # No expression tree - just combine all available SQLs with INTERSECT
            sqls = list(sql_lookup.values())
            if not sqls:
                return "-- NO SQL AVAILABLE", "No SQL templates found"
            if len(sqls) == 1:
                return sqls[0], "Single atomic criterion"
            combined = " INTERSECT ".join(f"({sql})" for sql in sqls)
            return combined, "AND of all atomics (no expression tree)"

        # Recursively build SQL from expression tree
        sql, logic = self._build_sql_from_node(
            expression_tree, sql_lookup, node_to_atomic
        )
        return sql, logic

    def _build_sql_from_node(
        self,
        node: Dict[str, Any],
        sql_lookup: Dict[str, str],
        node_to_atomic: Dict[str, str],
    ) -> Tuple[str, str]:
        """
        Recursively build SQL from an expression tree node.

        Args:
            node: Current node in expression tree.
            sql_lookup: Mapping from atomic ID to SQL template.
            node_to_atomic: Mapping from node ID to atomic ID.

        Returns:
            Tuple of (sql, logic_explanation).
        """
        node_type = node.get("nodeType", "")
        node_id = node.get("nodeId", "")

        if node_type == "atomic":
            # Leaf node - find corresponding SQL
            atomic_id = node_to_atomic.get(node_id, "")
            if atomic_id:
                sql = sql_lookup.get(atomic_id, "-- MISSING SQL")
                return sql, atomic_id
            # Try direct lookup if no mapping
            for aid, asql in sql_lookup.items():
                if node_id in aid or aid.endswith(node_id):
                    return asql, aid
            return "-- MISSING SQL", f"node_{node_id}"

        elif node_type == "operator":
            operator = node.get("operator", "AND")

            # Handle IMPLICATION operator (P → Q)
            # Semantics: "IF condition THEN requirement"
            # SQL equivalent: (NOT condition) UNION (condition AND requirement)
            # Patients who are eligible: those who don't have condition OR those who have it AND meet requirement
            if operator == "IMPLICATION":
                condition = node.get("condition", {})
                requirement = node.get("requirement", {})

                if not condition or not requirement:
                    return "-- IMPLICATION REQUIRES CONDITION AND REQUIREMENT", ""

                # Recursively process condition and requirement
                condition_sql, condition_logic = self._build_sql_from_node(
                    condition, sql_lookup, node_to_atomic
                )
                requirement_sql, requirement_logic = self._build_sql_from_node(
                    requirement, sql_lookup, node_to_atomic
                )

                # Build IMPLICATION SQL: (NOT condition) UNION (condition AND requirement)
                base_pop = "SELECT DISTINCT person_id FROM person"
                not_condition_sql = f"({base_pop}) EXCEPT ({condition_sql})"
                condition_and_requirement_sql = f"({condition_sql}) INTERSECT ({requirement_sql})"
                sql = f"({not_condition_sql}) UNION ({condition_and_requirement_sql})"
                logic = f"IF ({condition_logic}) THEN ({requirement_logic})"

                return sql, logic

            operands = node.get("operands", [])

            if not operands:
                return "-- NO OPERANDS", ""

            # Recursively process operands
            operand_results = [
                self._build_sql_from_node(op, sql_lookup, node_to_atomic)
                for op in operands
            ]
            operand_sqls = [r[0] for r in operand_results]
            operand_logics = [r[1] for r in operand_results]

            # Handle NOT operator (unary - applies to single operand)
            if operator == "NOT":
                if len(operand_sqls) >= 1:
                    # NOT is unary - use EXCEPT from a base population
                    # In OMOP CDM context, we negate from the full person table
                    # This returns patients who do NOT match the operand condition
                    base_pop = "SELECT DISTINCT person_id FROM person"
                    sql = f"({base_pop}) EXCEPT ({operand_sqls[0]})"
                    logic = f"NOT ({operand_logics[0]})"
                    return sql, logic
                return "-- NOT REQUIRES OPERAND", "NOT ?"

            # Handle single operand for non-NOT operators
            if len(operand_sqls) == 1:
                return operand_sqls[0], operand_logics[0]

            # Multi-operand logic
            if operator == "AND":
                sql = " INTERSECT ".join(f"({s})" for s in operand_sqls)
                logic = " AND ".join(operand_logics)
            elif operator == "OR":
                sql = " UNION ".join(f"({s})" for s in operand_sqls)
                logic = f"({' OR '.join(operand_logics)})"
            else:
                # Default to AND for unknown operators
                logger.warning(f"Unknown operator '{operator}', defaulting to AND")
                sql = " INTERSECT ".join(f"({s})" for s in operand_sqls)
                logic = " AND ".join(operand_logics)

            return sql, logic

        elif node_type == "temporal":
            # Temporal node - has "operand" (singular) with nested expression
            # and optional temporal constraints (referencePoint, direction, etc.)
            operand = node.get("operand", {})
            temporal_constraint = node.get("temporalConstraint", {})

            if not operand:
                return "-- TEMPORAL NODE WITHOUT OPERAND", ""

            # Recursively process the nested operand
            operand_sql, operand_logic = self._build_sql_from_node(
                operand, sql_lookup, node_to_atomic
            )

            # Extract temporal parameters for SQL enhancement
            reference_point = temporal_constraint.get("referencePoint", "")
            direction = temporal_constraint.get("direction", "")
            duration_value = temporal_constraint.get("durationValue")
            duration_unit = temporal_constraint.get("durationUnit", "")

            # If we have temporal constraints, wrap the SQL with a date filter
            if duration_value is not None and duration_unit:
                # Map duration units to PostgreSQL interval format
                unit_map = {
                    "days": "DAY",
                    "day": "DAY",
                    "weeks": "WEEK",
                    "week": "WEEK",
                    "months": "MONTH",
                    "month": "MONTH",
                    "years": "YEAR",
                    "year": "YEAR",
                }
                pg_unit = unit_map.get(duration_unit.lower(), "DAY")

                # Build temporal SQL with date constraint
                # This wraps the operand SQL to filter by date range
                # For "before" direction: events in the past X days/weeks/months
                # For "after" direction: events after a reference point
                if "before" in direction.lower() or "within" in direction.lower():
                    # Events within the past X time units from a reference date
                    # We add a date constraint as a comment that downstream systems can parse
                    # The operand SQL needs to be modified to include the date filter
                    temporal_sql = f"""-- TEMPORAL CONSTRAINT: Events {direction} {duration_value} {duration_unit}
-- Apply date filter: event_date >= CURRENT_DATE - INTERVAL '{duration_value} {pg_unit}'
SELECT person_id FROM (
{operand_sql}
) AS temporal_filter
-- Note: Add the following WHERE clause to the underlying table query:
-- WHERE [date_column] >= CURRENT_DATE - INTERVAL '{duration_value} {pg_unit}'"""
                    logic = f"TEMPORAL({operand_logic}, {direction} {duration_value} {duration_unit})"
                else:
                    # Default: just return the operand SQL with a comment
                    temporal_sql = f"-- Temporal: {direction} {duration_value} {duration_unit}\n{operand_sql}"
                    logic = f"TEMPORAL({operand_logic})"

                return temporal_sql, logic

            # No specific temporal constraint - just return the operand SQL
            return operand_sql, operand_logic

        return "-- UNKNOWN NODE", ""

    def _determine_internal_logic(
        self,
        expression_tree: Optional[Dict[str, Any]],
    ) -> str:
        """Determine the internal logic complexity of the criterion."""
        if not expression_tree:
            return "SIMPLE"

        operators = set()
        self._collect_operators(expression_tree, operators)

        if len(operators) == 0:
            return "SIMPLE"
        elif len(operators) == 1:
            return list(operators)[0]
        else:
            return "COMPLEX"

    def _collect_operators(
        self,
        node: Dict[str, Any],
        operators: Set[str],
    ) -> None:
        """Recursively collect operators from expression tree."""
        if node.get("nodeType") == "operator":
            op = node.get("operator", "AND")
            operators.add(op)

            # Handle IMPLICATION operator which has condition/requirement instead of operands
            if op == "IMPLICATION":
                condition = node.get("condition", {})
                requirement = node.get("requirement", {})
                if condition:
                    self._collect_operators(condition, operators)
                if requirement:
                    self._collect_operators(requirement, operators)
            else:
                for operand in node.get("operands", []):
                    self._collect_operators(operand, operators)

    def _deduplicate_omop_concepts(
        self,
        atomics: List[Dict[str, Any]],
    ) -> List[OMOPConceptRef]:
        """
        Collect and deduplicate OMOP concepts from atomics.

        Args:
            atomics: List of atomic criteria.

        Returns:
            Deduplicated list of OMOPConceptRef.
        """
        seen_concepts = set()
        concepts = []

        for atomic in atomics:
            omop_query = atomic.get("omopQuery") or {}
            concept_ids = omop_query.get("conceptIds", [])
            concept_names = omop_query.get("conceptNames", [])
            vocabulary_ids = omop_query.get("vocabularyIds", [])
            concept_codes = omop_query.get("conceptCodes", [])
            table_name = omop_query.get("tableName", "")

            # Map table name to domain
            domain_map = {
                "condition_occurrence": "Condition",
                "drug_exposure": "Drug",
                "procedure_occurrence": "Procedure",
                "measurement": "Measurement",
                "observation": "Observation",
                "person": "Person",
                "visit_occurrence": "Visit",
            }
            domain = domain_map.get(table_name, "Unknown")

            for i, cid in enumerate(concept_ids):
                if cid and cid not in seen_concepts:
                    seen_concepts.add(cid)
                    concepts.append(OMOPConceptRef(
                        concept_id=cid,
                        concept_name=concept_names[i] if i < len(concept_names) else "",
                        domain_id=domain,
                        vocabulary_id=vocabulary_ids[i] if i < len(vocabulary_ids) else None,
                        concept_code=concept_codes[i] if i < len(concept_codes) else None,
                    ))

        return concepts

    def _collect_fhir_resources(
        self,
        atomics: List[Dict[str, Any]],
    ) -> List[FHIRResourceRef]:
        """Collect FHIR resources from atomics."""
        seen_resources = set()
        resources = []

        for atomic in atomics:
            fhir_query = atomic.get("fhirQuery") or {}
            resource_type = fhir_query.get("resourceType", "")
            search_params = fhir_query.get("searchParams", "")

            if resource_type and (resource_type, search_params) not in seen_resources:
                seen_resources.add((resource_type, search_params))
                resources.append(FHIRResourceRef(
                    resource_type=resource_type,
                    search_params={"query": search_params},
                    description=None,
                ))

        return resources

    # OMOP domain to CDISC domain mapping
    OMOP_TO_CDISC_DOMAIN = {
        "Condition": "MH",       # Medical History
        "Drug": "CM",            # Concomitant Medications
        "Measurement": "LB",     # Laboratory
        "Procedure": "PR",       # Procedures
        "Observation": "VS",     # Vital Signs (or LB for labs)
        "Device": "DA",          # Device Accountability
        "Person": "DM",          # Demographics
        "Visit": "SV",           # Subject Visits
        "Unknown": "OTHER",      # Fallback
    }

    def _enrich_with_biomedical_concepts(
        self,
        omop_concepts: List[OMOPConceptRef],
        atomics: List[Dict[str, Any]],
    ) -> List[CDISCBiomedicalConcept]:
        """
        Convert OMOP concepts to CDISC Biomedical Concepts.

        Maps OMOP domain_id to CDISC domain and creates BC objects for
        cross-pipeline consistency with Main Pipeline and SOA Pipeline.

        Args:
            omop_concepts: Deduplicated OMOP concepts from the QEB.
            atomics: Atomic criteria for additional context.

        Returns:
            List of CDISCBiomedicalConcept objects.
        """
        biomedical_concepts = []
        seen_concepts = set()

        for omop in omop_concepts:
            # Skip duplicates
            if omop.concept_id in seen_concepts:
                continue
            seen_concepts.add(omop.concept_id)

            # Map OMOP domain to CDISC domain
            cdisc_domain = self.OMOP_TO_CDISC_DOMAIN.get(
                omop.domain_id, "OTHER"
            )

            # Determine confidence based on mapping quality
            # Higher confidence for exact vocabulary matches
            confidence = 0.85 if omop.vocabulary_id in ["SNOMED", "LOINC", "RxNorm"] else 0.7

            # Build rationale
            vocab_info = f"{omop.vocabulary_id}:{omop.concept_code}" if omop.vocabulary_id else f"OMOP:{omop.concept_id}"
            rationale = f"Mapped from OMOP {vocab_info} (domain: {omop.domain_id})"

            bc = CDISCBiomedicalConcept(
                concept_name=omop.concept_name[:150] if omop.concept_name else f"Concept {omop.concept_id}",
                cdisc_code="CUSTOM",  # OMOP concepts don't have direct NCI EVS codes
                domain=cdisc_domain,
                confidence=confidence,
                rationale=rationale[:200],
                source_omop_concept_id=omop.concept_id,
            )
            biomedical_concepts.append(bc)

        return biomedical_concepts

    def _get_provenance(
        self,
        criterion_id: str,
        raw_criteria: List[Dict[str, Any]],
        criterion_data: Dict[str, Any],
    ) -> Optional[QEBProvenance]:
        """Get provenance information for the criterion."""
        # Try from Stage 2 data first
        prov = criterion_data.get("provenance", {})
        if prov:
            return QEBProvenance(
                page_number=prov.get("pageNumber"),
                section_id=prov.get("sectionId"),
                text_snippet=prov.get("textSnippet"),
            )

        # Fall back to raw criteria
        for criterion in raw_criteria:
            if criterion.get("id") == criterion_id or criterion.get("criterionId") == criterion_id:
                prov = criterion.get("provenance", {})
                return QEBProvenance(
                    page_number=prov.get("pageNumber"),
                    section_id=prov.get("sectionId"),
                    text_snippet=prov.get("textSnippet"),
                )

        return None

    def _aggregate_queryable_status(
        self,
        atomics: List[Dict[str, Any]],
    ) -> str:
        """
        Aggregate queryable status from multiple atomics.

        Priority order (most restrictive to least):
        1. requires_manual - always requires chart review
        2. screening_only - requires real-time assessment
        3. llm_extractable - can be extracted from notes
        4. hybrid_queryable - SQL + LLM
        5. partially_queryable - some aspects queryable
        6. fully_queryable - fully queryable via SQL
        7. not_applicable - consent/compliance (doesn't affect queryability)

        Returns the most restrictive status.
        """
        statuses = [a.get("queryableStatus", "fully_queryable") for a in atomics]

        # Priority order from most to least restrictive
        priority_order = [
            "requires_manual",
            "screening_only",
            "llm_extractable",
            "hybrid_queryable",
            "partially_queryable",
            "fully_queryable",
            "not_applicable",
        ]

        for status in priority_order:
            if status in statuses:
                return status

        return "fully_queryable"

    def _build_clinical_summary(
        self,
        atomics: List[Dict[str, Any]],
        protocol_text: str,
        expression_tree: Optional[Dict[str, Any]] = None,
        node_to_atomic: Optional[Dict[str, str]] = None,
        criterion_type: str = "inclusion",
        internal_logic: str = "AND",
    ) -> ClinicalSummary:
        """
        Build clinical summary from atomics and expression tree.

        Groups related atomics by clinicalConceptGroup, identifies screening-only
        requirements, and generates a plain English summary.

        Clinical metadata (clinicalCategory, queryableStatus, clinicalConceptGroup)
        is extracted from the expression tree leaf nodes from Stage 2.

        Args:
            atomics: List of atomic criteria from eligibility funnel.
            protocol_text: Original protocol text for context.
            expression_tree: Stage 2 expression tree with clinical metadata in leaf nodes.
            node_to_atomic: Mapping from node ID to atomic ID for resolving metadata.

        Returns:
            ClinicalSummary with concept groups and screening requirements.
        """
        # Extract clinical metadata from expression tree leaf nodes (keyed by nodeId)
        node_metadata = self._extract_leaf_metadata(expression_tree) if expression_tree else {}

        # Build reverse mapping: atomicId -> nodeId
        atomic_to_node = {}
        if node_to_atomic:
            atomic_to_node = {atomic_id: node_id for node_id, atomic_id in node_to_atomic.items()}

        # Group atomics by clinicalConceptGroup
        groups_by_id: Dict[str, List[Dict[str, Any]]] = {}
        ungrouped: List[Dict[str, Any]] = []
        screening_only: List[Dict[str, Any]] = []

        for atomic in atomics:
            atomic_id = atomic.get("atomicId", "")

            # Find the corresponding node ID and get its metadata
            node_id = atomic_to_node.get(atomic_id, "")
            leaf_data = node_metadata.get(node_id, {}) if node_id else {}

            # Enrich atomic with clinical metadata from expression tree
            clinical_category = leaf_data.get("clinicalCategory", atomic.get("clinicalCategory", "other"))
            queryable_status = leaf_data.get("queryableStatus", atomic.get("queryableStatus", "fully_queryable"))
            concept_group = leaf_data.get("clinicalConceptGroup", atomic.get("clinicalConceptGroup"))
            atomic_text = leaf_data.get("atomicText", atomic.get("text", atomic.get("atomicText", "")))

            # Enrich the atomic dict with metadata for downstream processing
            enriched_atomic = {
                **atomic,
                "clinicalCategory": clinical_category,
                "queryableStatus": queryable_status,
                "clinicalConceptGroup": concept_group,
                "atomicText": atomic_text,
            }

            # Check if screening_only
            if queryable_status == "screening_only":
                screening_only.append(enriched_atomic)
                continue

            # Check for clinical concept group
            if concept_group:
                if concept_group not in groups_by_id:
                    groups_by_id[concept_group] = []
                groups_by_id[concept_group].append(enriched_atomic)
            else:
                ungrouped.append(enriched_atomic)

        # Build ClinicalConceptGroup objects for grouped atomics
        concept_groups: List[ClinicalConceptGroup] = []

        for group_id, group_atomics in groups_by_id.items():
            # Use the first atomic's category and build group name
            first_atomic = group_atomics[0]
            clinical_category = first_atomic.get("clinicalCategory", "other")

            # Generate readable group name from group_id
            # e.g., "egfr_activating_mutation" → "EGFR Activating Mutation"
            group_name = group_id.replace("_", " ").title()

            # Collect atomic IDs and aggregate queryable status
            atomic_ids = [a.get("atomicId", "") for a in group_atomics]
            statuses = [a.get("queryableStatus", "fully_queryable") for a in group_atomics]

            if "requires_manual" in statuses:
                agg_status = "requires_manual"
            elif "partially_queryable" in statuses:
                agg_status = "partially_queryable"
            else:
                agg_status = "fully_queryable"

            # Generate plain English from atomic texts
            atomic_texts = [a.get("text", a.get("atomicText", ""))[:100] for a in group_atomics]
            plain_english = " OR ".join(atomic_texts) if len(atomic_texts) <= 3 else f"{atomic_texts[0]} OR ... ({len(atomic_texts)} variants)"

            concept_groups.append(ClinicalConceptGroup(
                group_name=group_name,
                clinical_category=clinical_category,
                atomic_ids=atomic_ids,
                queryable_status=agg_status,
                treatment_implication=None,  # Could be enriched by LLM
                plain_english=plain_english,
            ))

        # Create individual groups for ungrouped atomics (each is its own concept)
        for atomic in ungrouped:
            atomic_id = atomic.get("atomicId", "")
            atomic_text = atomic.get("text", atomic.get("atomicText", ""))
            clinical_category = atomic.get("clinicalCategory", "other")
            queryable_status = atomic.get("queryableStatus", "fully_queryable")

            # Use atomic text as group name (shortened)
            group_name = atomic_text[:50] + "..." if len(atomic_text) > 50 else atomic_text

            concept_groups.append(ClinicalConceptGroup(
                group_name=group_name,
                clinical_category=clinical_category,
                atomic_ids=[atomic_id],
                queryable_status=queryable_status,
                plain_english=atomic_text,
            ))

        # Build ScreeningOnlyRequirement objects
        screening_reqs: List[ScreeningOnlyRequirement] = []
        for atomic in screening_only:
            atomic_id = atomic.get("atomicId", "")
            description = atomic.get("text", atomic.get("atomicText", ""))

            screening_reqs.append(ScreeningOnlyRequirement(
                atomic_id=atomic_id,
                description=description,
                note="Site/documentation requirement, not patient filter",
            ))

        # Generate clinical logic summary with proper negation handling for exclusion criteria
        # and correct logical operators based on internal_logic
        if len(concept_groups) == 0:
            logic_summary = "No queryable clinical concepts identified."
        else:
            # Determine the prefix based on criterion type
            if criterion_type == "exclusion":
                prefix = "Patient must NOT have"
            else:
                prefix = "Patient must meet"

            # Determine the logical connector based on internal_logic
            if internal_logic == "OR":
                connector = " OR "
            elif internal_logic == "COMPLEX":
                # For complex logic, use "and/or" to indicate mixed logic
                connector = ", "
            else:  # AND or SIMPLE
                connector = " AND "

            if len(concept_groups) == 1:
                logic_summary = f"{prefix}: {concept_groups[0].group_name}"
            else:
                group_names = [g.group_name for g in concept_groups[:3]]
                if len(concept_groups) > 3:
                    logic_summary = f"{prefix}: {', '.join(group_names)}, and {len(concept_groups) - 3} more requirements"
                else:
                    logic_summary = f"{prefix}: {connector.join(group_names)}"

        return ClinicalSummary(
            concept_groups=concept_groups,
            screening_only_requirements=screening_reqs,
            clinical_logic_summary=logic_summary,
        )

    def _create_qebs_for_missing_criteria(
        self,
        raw_criteria: List[Dict[str, Any]],
        existing_criterion_ids: Set[str],
        expression_lookup: Dict[str, Dict[str, Any]],
    ) -> List[QueryableEligibilityBlock]:
        """
        Create QEBs for criteria that have no atomics (requires manual review).

        Some criteria may not have been decomposed into atomics (e.g., subjective
        criteria like "investigator judgment"). This ensures they still appear
        in the QEB output marked as requires_manual.

        Args:
            raw_criteria: Original extracted criteria list.
            existing_criterion_ids: Set of criterion IDs that already have QEBs.
            expression_lookup: Lookup for expression trees from Stage 2.

        Returns:
            List of QEBs for missing criteria.
        """
        missing_qebs = []

        for criterion in raw_criteria:
            # Try multiple ID field names
            criterion_id = (
                criterion.get("criterionId")
                or criterion.get("id")
                or criterion.get("criterion_id")
            )

            if not criterion_id:
                continue

            # Skip if already has atomics
            if criterion_id in existing_criterion_ids:
                continue

            # Determine criterion type
            criterion_type = criterion.get("type", "").lower()
            if not criterion_type:
                if criterion_id.startswith("INC"):
                    criterion_type = "inclusion"
                elif criterion_id.startswith("EXC"):
                    criterion_type = "exclusion"
                else:
                    criterion_type = "inclusion"

            # Get original text
            original_text = (
                criterion.get("text")
                or criterion.get("originalText")
                or criterion.get("criterionText")
                or ""
            )

            # Get expression tree if available
            criterion_data = expression_lookup.get(criterion_id, {})

            # Get provenance
            provenance = self._get_provenance(criterion_id, raw_criteria, criterion_data)

            # Create QEB marked as requires_manual
            qeb = QueryableEligibilityBlock(
                qeb_id=f"QEB_{criterion_id}",
                original_criterion_id=criterion_id,
                criterion_type=criterion_type,
                clinical_name="",  # To be filled by LLM
                clinical_description="",  # To be filled by LLM
                clinical_category="",  # To be filled by LLM
                funnel_stage="",  # To be filled by LLM
                funnel_stage_order=0,  # To be filled by LLM
                combined_sql="-- NO ATOMICS: Manual review required",
                sql_logic_explanation="No atomic decomposition available",
                queryable_status="requires_manual",
                non_queryable_reason="Criterion could not be decomposed into queryable atomic components",
                estimated_elimination_rate=0.0,  # To be filled by LLM
                is_killer_criterion=False,  # To be filled by LLM
                atomic_ids=[],
                atomic_count=0,
                internal_logic="MANUAL",
                omop_concepts=[],
                fhir_resources=[],
                biomedical_concepts=[],  # No BC for manual review criteria
                protocol_text=original_text,
                provenance=provenance,
            )
            missing_qebs.append(qeb)

            logger.info(
                f"Created manual-review QEB for {criterion_id} (no atomics found)"
            )

        return missing_qebs

    # Maximum atomics per LLM batch to avoid token limits
    QUERYABILITY_BATCH_SIZE = 50
    DATA_SOURCE_BATCH_SIZE = 30  # Smaller batch for data source classification

    # =========================================================================
    # DATA SOURCE CLASSIFICATION (New: Data source-aware queryability)
    # =========================================================================

    async def _classify_data_sources_batch(
        self,
        atomics: List[Dict[str, Any]],
        therapeutic_area: Optional[str],
    ) -> Dict[str, DataSourceClassification]:
        """
        Use LLM to classify the primary data source for each atomic criterion.

        This classification determines WHERE clinical data for each criterion
        would typically be found in a patient's medical record:
        - ehr_structured: Diagnosis codes, lab results, medications (SQL queryable)
        - pathology_report: Histology, biomarkers, mutations (LLM extractable)
        - radiology_report: Imaging findings, metastases (LLM extractable)
        - clinical_notes: Prior treatments, history (LLM extractable)
        - real_time_assessment: Requires new assessment at enrollment (screening only)
        - clinical_judgment: Subjective investigator evaluation (screening only)
        - calculated_value: Formula calculation at enrollment (screening only)
        - patient_decision: Consent, compliance (not applicable)

        Args:
            atomics: List of atomic criteria from eligibility funnel.
            therapeutic_area: Therapeutic area for context.

        Returns:
            Dictionary mapping atomic_id to DataSourceClassification.
        """
        if not atomics:
            return {}

        all_classifications = {}

        # Process in batches to avoid token limits
        for batch_start in range(0, len(atomics), self.DATA_SOURCE_BATCH_SIZE):
            batch_end = min(batch_start + self.DATA_SOURCE_BATCH_SIZE, len(atomics))
            batch_atomics = atomics[batch_start:batch_end]

            batch_results = await self._classify_data_sources_single_batch(
                batch_atomics, therapeutic_area
            )
            all_classifications.update(batch_results)

            if batch_end < len(atomics):
                logger.debug(
                    f"Processed data source batch {batch_start}-{batch_end} of {len(atomics)}"
                )

        # Log data source distribution
        source_counts = {}
        for classification in all_classifications.values():
            source = classification.primary_data_source
            source_counts[source] = source_counts.get(source, 0) + 1

        logger.info(
            f"Data source classification complete: {len(all_classifications)} atomics. "
            f"Distribution: {source_counts}"
        )

        return all_classifications

    async def _classify_data_sources_single_batch(
        self,
        batch_atomics: List[Dict[str, Any]],
        therapeutic_area: Optional[str],
    ) -> Dict[str, DataSourceClassification]:
        """
        Classify data sources for a single batch of atomics.

        Returns:
            Dictionary mapping atomic_id to DataSourceClassification.
        """
        # Prepare atomics data for prompt
        atomics_for_prompt = []
        for atomic in batch_atomics:
            atomics_for_prompt.append({
                "atomicId": atomic.get("atomicId", ""),
                "text": atomic.get("text", atomic.get("atomicText", ""))[:400],
                "criterionType": atomic.get("criterionType", ""),
                "clinicalCategory": atomic.get("clinicalCategory", ""),
                "originalCriterionId": atomic.get("originalCriterionId", ""),
            })

        # Load and format prompt
        prompt_template = self._load_prompt("stage12_data_source_classification.txt")
        prompt = prompt_template.format(
            atomics_json=json.dumps(atomics_for_prompt, indent=2),
        )

        # Call LLM with retry logic
        result_text = await self._call_llm_with_retry(prompt, "data_source_classification")
        classification_results = self._parse_llm_json_response(result_text)

        results = {}
        if classification_results and isinstance(classification_results, list):
            for item in classification_results:
                atomic_id = item.get("atomicId", "")
                if atomic_id:
                    results[atomic_id] = DataSourceClassification(
                        atomic_id=atomic_id,
                        primary_data_source=item.get("primaryDataSource", "ehr_structured"),
                        secondary_data_source=item.get("secondaryDataSource"),
                        note_types=item.get("noteTypes", []),
                        confidence=item.get("confidence", 0.8),
                        reasoning=item.get("reasoning"),
                    )
        else:
            # Fallback when LLM fails - use heuristics
            warning = "Data source classification LLM failed - using heuristic fallback"
            logger.warning(warning)
            self._llm_warnings.append(warning)

            for atomic in batch_atomics:
                atomic_id = atomic.get("atomicId", "")
                atomic_text = atomic.get("text", atomic.get("atomicText", "")).lower()

                # Heuristic data source classification
                data_source, note_types, reasoning = self._heuristic_data_source(atomic_text)

                results[atomic_id] = DataSourceClassification(
                    atomic_id=atomic_id,
                    primary_data_source=data_source,
                    secondary_data_source=None,
                    note_types=note_types,
                    confidence=0.6,  # Lower confidence for heuristic
                    reasoning=reasoning,
                )

        return results

    def _heuristic_data_source(self, text: str) -> Tuple[str, List[str], str]:
        """
        Heuristic data source classification when LLM fails.

        Returns:
            Tuple of (data_source, note_types, reasoning).
        """
        text_lower = text.lower()

        # Patient decision / consent
        consent_keywords = [
            "informed consent", "willing to", "agrees to", "able to comply",
            "signed consent", "understand the study", "capable of understanding",
            "consent to provide", "must consent", "agrees to provide",
            "willing to use contraception", "agree to use contraception",
            "willing to abstain", "agrees to abstain", "provide written consent",
            "give written consent", "must agree to", "willing to participate",
        ]
        if any(kw in text_lower for kw in consent_keywords):
            return DataSourceType.PATIENT_DECISION.value, [], "Consent/compliance requirement"

        # Clinical judgment
        judgment_keywords = [
            "life expectancy", "investigator judgment", "investigator's opinion",
            "in the opinion of", "adequate organ function", "medically fit",
            "per investigator", "discretion of",
        ]
        if any(kw in text_lower for kw in judgment_keywords):
            return DataSourceType.CLINICAL_JUDGMENT.value, [], "Clinical judgment required"

        # Calculated values
        calculated_keywords = [
            "creatinine clearance", "cockcroft-gault", "body surface area", "bsa",
            "calculated gfr", "estimated gfr", "egfr >", "egfr <", "egfr ≥", "egfr ≤",
            "qtcf", "qtcb", "corrected qt", "meld score", "child-pugh",
        ]
        if any(kw in text_lower for kw in calculated_keywords):
            return DataSourceType.CALCULATED_VALUE.value, [], "Calculated value at enrollment"

        # Real-time assessment
        realtime_keywords = [
            "measurable disease", "recist", "at baseline", "at screening",
            "accessible for biopsy", "currently pregnant", "currently breastfeeding",
            "physical examination", "demonstrated by mri", "demonstrated by ct",
        ]
        if any(kw in text_lower for kw in realtime_keywords):
            return DataSourceType.REAL_TIME_ASSESSMENT.value, [], "Real-time assessment required"

        # Pathology report indicators
        pathology_keywords = [
            "histology", "histologic", "adenocarcinoma", "squamous", "cytology",
            "egfr mutation", "alk rearrangement", "alk fusion", "ros1", "braf",
            "kras", "pd-l1", "her2", "er positive", "pr positive", "ki-67",
            "tumor grade", "gleason", "differentiation", "molecular",
        ]
        if any(kw in text_lower for kw in pathology_keywords):
            return (
                DataSourceType.PATHOLOGY_REPORT.value,
                ["Pathology", "Molecular Diagnostics"],
                "Pathology/molecular finding"
            )

        # Radiology report indicators
        radiology_keywords = [
            "brain metastases", "cns metastases", "bone metastases", "liver metastases",
            "lung metastases", "imaging", "mri", "ct scan", "pet scan", "tumor size",
            "stage iv", "stage iii", "metastatic", "locally advanced",
        ]
        if any(kw in text_lower for kw in radiology_keywords):
            return (
                DataSourceType.RADIOLOGY_REPORT.value,
                ["Radiology"],
                "Imaging/radiology finding"
            )

        # Clinical notes indicators (prior treatments, history)
        clinical_notes_keywords = [
            "prior treatment", "prior therapy", "previously treated", "previous treatment",
            "history of", "prior chemotherapy", "prior radiation", "failed",
            "progressed on", "relapsed",
        ]
        if any(kw in text_lower for kw in clinical_notes_keywords):
            return (
                DataSourceType.CLINICAL_NOTES.value,
                ["Progress Note", "H&P"],
                "Clinical history in notes"
            )

        # Default to EHR structured (labs, meds, diagnoses)
        return DataSourceType.EHR_STRUCTURED.value, [], "Structured EHR data (default)"

    def _determine_queryable_status_from_data_source(
        self,
        data_source: str,
        has_omop_mapping: bool,
        secondary_source: Optional[str] = None,
    ) -> str:
        """
        Determine queryable status based on data source classification.

        This is the core logic that replaces the old "unmapped → screening_only" default.

        Args:
            data_source: Primary data source type.
            has_omop_mapping: Whether OMOP concept mapping exists.
            secondary_source: Optional secondary data source.

        Returns:
            QueryableStatus value as string.
        """
        # Patient decisions are always NOT_APPLICABLE
        if data_source == DataSourceType.PATIENT_DECISION.value:
            return QueryableStatus.NOT_APPLICABLE.value

        # True screening requirements (cannot be pre-queried)
        screening_sources = [
            DataSourceType.REAL_TIME_ASSESSMENT.value,
            DataSourceType.CLINICAL_JUDGMENT.value,
            DataSourceType.CALCULATED_VALUE.value,
        ]
        if data_source in screening_sources:
            return QueryableStatus.SCREENING_ONLY.value

        # Unstructured data sources (pathology, radiology, clinical notes)
        unstructured_sources = [
            DataSourceType.PATHOLOGY_REPORT.value,
            DataSourceType.RADIOLOGY_REPORT.value,
            DataSourceType.CLINICAL_NOTES.value,
        ]
        if data_source in unstructured_sources:
            if has_omop_mapping:
                # Has both structured mapping AND unstructured source
                return QueryableStatus.HYBRID_QUERYABLE.value
            else:
                # No structured mapping, but LLM can extract from notes
                return QueryableStatus.LLM_EXTRACTABLE.value

        # Structured data (EHR)
        if data_source == DataSourceType.EHR_STRUCTURED.value:
            if has_omop_mapping:
                return QueryableStatus.FULLY_QUERYABLE.value
            else:
                # Structured data without mapping - might be in notes
                # Check if there's a secondary unstructured source
                if secondary_source in unstructured_sources:
                    return QueryableStatus.LLM_EXTRACTABLE.value
                # Default: might still be extractable from notes
                return QueryableStatus.LLM_EXTRACTABLE.value

        # Fallback
        return QueryableStatus.REQUIRES_MANUAL.value

    async def _classify_atomic_queryability_batch(
        self,
        atomics: List[Dict[str, Any]],
        therapeutic_area: Optional[str],
        data_source_classifications: Optional[Dict[str, DataSourceClassification]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Classify each atomic's queryability using data source-aware logic.

        New classification approach:
        - Uses data source classification to determine WHERE data lives
        - Maps data source to appropriate query method (SQL, LLM, hybrid, screening)
        - Unmapped atomics are NO LONGER automatically SCREENING_ONLY
        - Instead, checks if data exists in unstructured notes (pathology, radiology)

        Args:
            atomics: List of atomic criteria from eligibility funnel.
            therapeutic_area: Therapeutic area for context.
            data_source_classifications: Pre-computed data source classifications.

        Returns:
            Atomics list with queryabilityClassification and optional nlpQuerySpec.
        """
        if not atomics:
            return atomics

        # Use provided classifications or empty dict
        ds_classifications = data_source_classifications or {}

        # Apply data source-aware classifications to atomics
        for atomic in atomics:
            atomic_id = atomic.get("atomicId", "")

            # Get OMOP mapping status
            omop_query = atomic.get("omopQuery") or {}
            concept_ids = omop_query.get("conceptIds", [])
            has_mapping = bool(concept_ids and any(cid for cid in concept_ids if cid))

            # Get data source classification
            ds_class = ds_classifications.get(atomic_id)

            if ds_class:
                # Determine queryable status from data source
                queryable_status = self._determine_queryable_status_from_data_source(
                    data_source=ds_class.primary_data_source,
                    has_omop_mapping=has_mapping,
                    secondary_source=ds_class.secondary_data_source,
                )

                # Map new status values to category
                status_to_category = {
                    QueryableStatus.FULLY_QUERYABLE.value: "QUERYABLE",
                    QueryableStatus.LLM_EXTRACTABLE.value: "LLM_EXTRACTABLE",
                    QueryableStatus.HYBRID_QUERYABLE.value: "HYBRID_QUERYABLE",
                    QueryableStatus.SCREENING_ONLY.value: "SCREENING_ONLY",
                    QueryableStatus.NOT_APPLICABLE.value: "NOT_APPLICABLE",
                    QueryableStatus.PARTIALLY_QUERYABLE.value: "PARTIALLY_QUERYABLE",
                    QueryableStatus.REQUIRES_MANUAL.value: "REQUIRES_MANUAL",
                }
                category = status_to_category.get(queryable_status, "REQUIRES_MANUAL")

                # Build reasoning
                reasoning_parts = [ds_class.reasoning or ""]
                if has_mapping:
                    reasoning_parts.append("Has OMOP mapping.")
                else:
                    reasoning_parts.append("No OMOP mapping.")
                if ds_class.note_types:
                    reasoning_parts.append(f"Data in: {', '.join(ds_class.note_types)}")

                reasoning = " ".join(filter(None, reasoning_parts))
                confidence = ds_class.confidence

                # Build classification structure
                classification = {
                    "category": category,
                    "queryableStatus": queryable_status,
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "overridable": True,
                    "dataSource": ds_class.to_dict(),
                }

                # Add NlpQuerySpec for LLM_EXTRACTABLE or HYBRID_QUERYABLE
                if queryable_status in [
                    QueryableStatus.LLM_EXTRACTABLE.value,
                    QueryableStatus.HYBRID_QUERYABLE.value,
                ]:
                    atomic_text = atomic.get("text", atomic.get("atomicText", ""))
                    nlp_spec = NlpQuerySpec(
                        note_types=ds_class.note_types or ["Progress Note"],
                        extraction_prompt=f"Extract: {atomic_text[:200]}",
                        value_type=self._infer_value_type(atomic_text),
                        temporal_constraint="most_recent",
                        confidence_threshold=0.70,
                    )
                    classification["nlpQuerySpec"] = nlp_spec.to_dict()

                atomic["queryabilityClassification"] = classification
                # Also set top-level queryableStatus for aggregation
                atomic["queryableStatus"] = queryable_status

            else:
                # No data source classification - use fallback heuristics
                atomic_text = atomic.get("text", atomic.get("atomicText", "")).lower()

                if self._is_consent_compliance_text(atomic_text):
                    category = "NOT_APPLICABLE"
                    queryable_status = QueryableStatus.NOT_APPLICABLE.value
                    reasoning = "Consent/compliance requirement"
                elif self._is_screening_only_text(atomic_text):
                    category = "SCREENING_ONLY"
                    queryable_status = QueryableStatus.SCREENING_ONLY.value
                    reasoning = "Requires real-time assessment or clinical judgment"
                elif has_mapping:
                    category = "QUERYABLE"
                    queryable_status = QueryableStatus.FULLY_QUERYABLE.value
                    reasoning = "Has OMOP mapping"
                else:
                    # NEW: Default to LLM_EXTRACTABLE instead of SCREENING_ONLY
                    # Most unmapped criteria CAN be found in clinical notes
                    category = "LLM_EXTRACTABLE"
                    queryable_status = QueryableStatus.LLM_EXTRACTABLE.value
                    reasoning = "No OMOP mapping but may be extractable from clinical notes"

                atomic["queryabilityClassification"] = {
                    "category": category,
                    "queryableStatus": queryable_status,
                    "confidence": 0.6,
                    "reasoning": reasoning,
                    "overridable": True,
                }
                # Also set top-level queryableStatus for aggregation
                atomic["queryableStatus"] = queryable_status

        # Log classification distribution
        categories = [a.get("queryabilityClassification", {}).get("category", "") for a in atomics]
        logger.info(
            f"Classified {len(atomics)} atomics: "
            f"QUERYABLE={categories.count('QUERYABLE')}, "
            f"LLM_EXTRACTABLE={categories.count('LLM_EXTRACTABLE')}, "
            f"HYBRID_QUERYABLE={categories.count('HYBRID_QUERYABLE')}, "
            f"SCREENING_ONLY={categories.count('SCREENING_ONLY')}, "
            f"NOT_APPLICABLE={categories.count('NOT_APPLICABLE')}"
        )

        return atomics

    def _infer_value_type(self, text: str) -> str:
        """Infer the expected value type for LLM extraction."""
        text_lower = text.lower()

        # Numeric indicators
        numeric_patterns = [
            ">=", "<=", ">", "<", "≥", "≤",
            "mg/dl", "g/dl", "ml/min", "mm", "cm",
            "weeks", "months", "years", "days",
            "score", "level", "count", "percentage", "%",
        ]
        if any(p in text_lower for p in numeric_patterns):
            return "numeric"

        # Boolean indicators
        boolean_patterns = [
            "presence of", "absence of", "with ", "without ",
            "positive", "negative", "confirmed", "documented",
            "history of", "no history", "no known",
        ]
        if any(p in text_lower for p in boolean_patterns):
            return "boolean"

        # Date indicators
        date_patterns = [
            "within", "prior to", "after", "before",
            "date of", "at the time of",
        ]
        if any(p in text_lower for p in date_patterns):
            return "date"

        # Default to categorical
        return "categorical"

    async def _classify_queryability_single_batch(
        self,
        batch_atomics: List[Dict[str, Any]],
        therapeutic_area: Optional[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Classify a single batch of atomics.

        Returns:
            Dictionary mapping atomic_id to classification dict.
        """
        # Prepare atomics data for prompt
        atomics_for_prompt = []
        for atomic in batch_atomics:
            omop_query = atomic.get("omopQuery") or {}
            concept_ids = omop_query.get("conceptIds", [])
            concept_names = omop_query.get("conceptNames", [])

            # Determine if OMOP mapping exists
            has_mapping = bool(concept_ids and any(cid for cid in concept_ids if cid))
            is_unmapped = not has_mapping

            atomics_for_prompt.append({
                "atomicId": atomic.get("atomicId", ""),
                "text": atomic.get("text", "")[:500],
                "criterionType": atomic.get("criterionType", ""),
                "clinicalCategory": atomic.get("clinicalCategory", ""),
                "omopConceptId": concept_ids[0] if concept_ids else None,
                "omopConceptName": concept_names[0] if concept_names else None,
                "isUnmapped": is_unmapped,
            })

        # Load and format prompt with therapeutic area context
        prompt_template = self._load_prompt("stage12_queryability_classification.txt")
        prompt = prompt_template.format(
            atomics_json=json.dumps(atomics_for_prompt, indent=2),
            therapeutic_area=therapeutic_area or "General",
        )

        # Call LLM with retry logic
        result_text = await self._call_llm_with_retry(prompt, "queryability_classification")
        classification_results = self._parse_llm_json_response(result_text)

        if classification_results and isinstance(classification_results, list):
            # Return lookup from atomic ID to classification
            return {r.get("atomicId"): r for r in classification_results}
        else:
            # Fallback when LLM fails - use heuristics
            warning = "Queryability classification LLM failed - using heuristic fallback"
            logger.warning(warning)
            self._llm_warnings.append(warning)

            result = {}
            for atomic in batch_atomics:
                atomic_id = atomic.get("atomicId", "")
                atomic_text = atomic.get("text", "").lower()
                omop_query = atomic.get("omopQuery") or {}
                concept_ids = omop_query.get("conceptIds", [])
                has_mapping = bool(concept_ids and any(cid for cid in concept_ids if cid))

                # Heuristic classification
                if self._is_consent_compliance_text(atomic_text):
                    category = "NOT_APPLICABLE"
                    reasoning = "Heuristic: Consent/compliance requirement detected"
                elif self._is_screening_only_text(atomic_text):
                    category = "SCREENING_ONLY"
                    reasoning = "Heuristic: Screening-only criterion detected"
                elif has_mapping:
                    category = "QUERYABLE"
                    reasoning = "Heuristic: Has OMOP mapping and no screening-only keywords"
                else:
                    category = "SCREENING_ONLY"
                    reasoning = "Heuristic: No OMOP mapping found"

                result[atomic_id] = {
                    "atomicId": atomic_id,
                    "category": category,
                    "confidence": 0.6,  # Lower confidence for heuristic
                    "reasoning": reasoning,
                }

            return result

    def _is_consent_compliance_text(self, text: str) -> bool:
        """Check if text indicates consent/compliance (NOT_APPLICABLE)."""
        text_lower = text.lower()
        consent_keywords = [
            "informed consent",
            "willing to provide",
            "consent to provide",  # "Subject must consent to provide archived tissue"
            "must consent",
            "agrees to use",
            "agrees to provide",
            "able to comply",
            "signed consent",
            "understand the study",
            "capable of understanding",
            "willing to comply",
            "agrees to participate",
            "documentation of consent",
            "willing to use contraception",
            "agree to use contraception",
            "agrees to use contraception",
            "willing to abstain",
            "agrees to abstain",
            "provide written consent",
            "give written consent",
        ]
        return any(kw in text_lower for kw in consent_keywords)

    def _is_screening_only_text(self, text: str) -> bool:
        """
        Check if text indicates screening-only criterion.

        Note: These heuristics are fallbacks when LLM fails. They intentionally
        avoid ambiguous terms to prevent misclassification.
        """
        # Exact phrases that indicate clinician judgment or calculated values
        screening_phrases = [
            "life expectancy",
            "in the opinion of",
            "investigator judgment",
            "investigator's opinion",
            "creatinine clearance",
            "cockcroft-gault",
            "body surface area",
            "adequate organ function",
            "medically fit",
            "capable of understanding",
            "physical examination",
            "currently pregnant",
            "currently breastfeeding",
        ]

        # Calculated lab values (not the raw labs which ARE queryable)
        calculated_values = [
            "calculated gfr",
            "estimated gfr",
            "egfr (",  # eGFR with units/values, not EGFR gene
            "egfr >",
            "egfr <",
            "egfr ≥",
            "egfr ≤",
            "qtcf",
            "qtcb",
            "corrected qt",
            "meld score",
        ]

        # Real-time imaging/assessment requirements (not history)
        realtime_assessments = [
            "measurable disease",
            "recist",
            "accessible for biopsy",
            "tumor accessible",
            "no evidence of.*on mri",  # Real-time imaging requirement
            "no evidence of.*on ct",
            "demonstrated by mri",
            "demonstrated by ct",
            "confirmed by imaging",
        ]

        # Check exact phrases
        if any(phrase in text for phrase in screening_phrases):
            return True

        if any(calc in text for calc in calculated_values):
            return True

        # Check regex patterns for real-time imaging
        import re
        for pattern in realtime_assessments:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    async def _generate_clinical_names_batch(
        self,
        qebs: List[QueryableEligibilityBlock],
        therapeutic_area: Optional[str],
    ) -> List[QueryableEligibilityBlock]:
        """
        Use LLM to generate clinical names and descriptions for all QEBs.

        Args:
            qebs: List of raw QEBs.
            therapeutic_area: Therapeutic area for context.

        Returns:
            QEBs with clinical names populated.
        """
        if not qebs:
            return qebs

        # Prepare criteria data for prompt
        criteria_for_prompt = []
        for qeb in qebs:
            criteria_for_prompt.append({
                "criterion_id": qeb.original_criterion_id,
                "criterion_type": qeb.criterion_type,
                "protocol_text": qeb.protocol_text[:500] if qeb.protocol_text else "",
                "atomic_count": qeb.atomic_count,
                "omop_concepts": [c.concept_name for c in qeb.omop_concepts[:5]],
            })

        # Load and format prompt
        prompt_template = self._load_prompt("stage12_clinical_naming.txt")
        prompt = prompt_template.format(
            therapeutic_area=therapeutic_area or "General",
            criteria_json=json.dumps(criteria_for_prompt, indent=2),
        )

        # Call LLM with retry logic
        result_text = await self._call_llm_with_retry(prompt, "clinical_naming")
        naming_results = self._parse_llm_json_response(result_text)

        if naming_results and isinstance(naming_results, list):
            # Apply names to QEBs
            name_lookup = {r.get("criterion_id"): r for r in naming_results}
            for qeb in qebs:
                naming = name_lookup.get(qeb.original_criterion_id, {})
                qeb.clinical_name = naming.get("clinical_name", f"Criterion {qeb.original_criterion_id}")
                qeb.clinical_description = naming.get("clinical_description", qeb.protocol_text[:200])
                qeb.clinical_category = naming.get("clinical_category", "other")
        else:
            # Fallback when LLM fails - use criterion ID as name
            warning = "Clinical naming LLM failed - using fallback names"
            logger.warning(warning)
            self._llm_warnings.append(warning)
            for qeb in qebs:
                qeb.clinical_name = f"Criterion {qeb.original_criterion_id}"
                qeb.clinical_description = qeb.protocol_text[:200] if qeb.protocol_text else ""
                qeb.clinical_category = "other"

        return qebs

    async def _assess_queryable_status_batch(
        self,
        qebs: List[QueryableEligibilityBlock],
        therapeutic_area: Optional[str],
    ) -> List[QueryableEligibilityBlock]:
        """
        Use LLM to assess elimination rates and killer criteria for all QEBs.

        IMPORTANT: This method now PRESERVES the data source-based queryable status
        set by _classify_atomic_queryability_batch. The LLM is only used for:
        - Assessing elimination rates
        - Identifying killer criteria
        - Providing non-queryable reasons for screening_only criteria

        The queryable status is NOT overwritten except in specific cases:
        - If LLM returns "screening_only" for something marked as queryable
          AND provides a valid reason (e.g., clinical judgment required)

        Args:
            qebs: List of QEBs with clinical names.
            therapeutic_area: Therapeutic area for context.

        Returns:
            QEBs with elimination rates and killer criteria updated.
        """
        if not qebs:
            return qebs

        # Prepare criteria data for prompt
        criteria_for_prompt = []
        for qeb in qebs:
            criteria_for_prompt.append({
                "criterion_id": qeb.original_criterion_id,
                "clinical_name": qeb.clinical_name,
                "clinical_category": qeb.clinical_category,
                "criterion_type": qeb.criterion_type,
                "protocol_text": qeb.protocol_text[:500] if qeb.protocol_text else "",
                "has_sql": bool(qeb.combined_sql and "MISSING" not in qeb.combined_sql),
                "omop_concepts": [c.concept_name for c in qeb.omop_concepts[:5]],
                "current_status": qeb.queryable_status,
            })

        # Load and format prompt
        prompt_template = self._load_prompt("stage12_queryable_assessment.txt")
        prompt = prompt_template.format(
            therapeutic_area=therapeutic_area or "General",
            criteria_json=json.dumps(criteria_for_prompt, indent=2),
        )

        # Call LLM with retry logic
        result_text = await self._call_llm_with_retry(prompt, "queryable_assessment")
        assessment_results = self._parse_llm_json_response(result_text)

        if assessment_results and isinstance(assessment_results, list):
            # Apply assessments to QEBs - PRESERVE data source-based status
            assessment_lookup = {r.get("criterion_id"): r for r in assessment_results}
            for qeb in qebs:
                assessment = assessment_lookup.get(qeb.original_criterion_id, {})

                # PRESERVE the data source-based queryable status
                # Only update if the current status is not one of the data source types
                # OR if the LLM downgrades to screening_only with a reason
                llm_status = assessment.get("queryable_status", qeb.queryable_status)
                data_source_statuses = [
                    QueryableStatus.LLM_EXTRACTABLE.value,
                    QueryableStatus.HYBRID_QUERYABLE.value,
                    QueryableStatus.FULLY_QUERYABLE.value,
                ]

                # Only accept LLM downgrade to screening_only if it has a valid reason
                if qeb.queryable_status in data_source_statuses:
                    if llm_status == "screening_only" and assessment.get("non_queryable_reason"):
                        # LLM says this is truly screening-only with a reason
                        qeb.queryable_status = llm_status
                    # Otherwise, PRESERVE the data source-based status
                else:
                    # For non-data-source statuses, accept LLM assessment
                    qeb.queryable_status = llm_status

                # Only set non_queryable_reason if status is NOT fully_queryable
                # This prevents contradictions like "fully_queryable" with a non_queryable_reason
                if qeb.queryable_status != QueryableStatus.FULLY_QUERYABLE.value:
                    qeb.non_queryable_reason = assessment.get("non_queryable_reason")
                else:
                    qeb.non_queryable_reason = None
                # Elimination rate is only set if epidemiological evidence exists
                qeb.estimated_elimination_rate = assessment.get("estimated_elimination_rate")
                qeb.epidemiological_evidence = assessment.get("epidemiological_evidence")
                # Killer criterion requires epidemiological evidence
                is_killer = assessment.get("is_killer_criterion", False)
                has_evidence = bool(assessment.get("epidemiological_evidence"))
                qeb.is_killer_criterion = is_killer and has_evidence
        else:
            # Keep existing values when LLM fails
            warning = "Queryable assessment LLM failed - using existing status values"
            logger.warning(warning)
            self._llm_warnings.append(warning)

        return qebs

    async def _cluster_into_funnel_stages(
        self,
        qebs: List[QueryableEligibilityBlock],
        therapeutic_area: Optional[str],
        protocol_id: str,
    ) -> Tuple[List[QueryableEligibilityBlock], List[QEBFunnelStage]]:
        """
        Use LLM to cluster QEBs into funnel stages.

        Args:
            qebs: List of QEBs with clinical names and assessments.
            therapeutic_area: Therapeutic area for context.
            protocol_id: Protocol identifier.

        Returns:
            Tuple of (updated QEBs, funnel stages).
        """
        if not qebs:
            return qebs, []

        # Prepare criteria data for prompt
        criteria_for_prompt = []
        for qeb in qebs:
            criteria_for_prompt.append({
                "qeb_id": qeb.qeb_id,
                "criterion_id": qeb.original_criterion_id,
                "clinical_name": qeb.clinical_name,
                "clinical_category": qeb.clinical_category,
                "criterion_type": qeb.criterion_type,
                "estimated_elimination_rate": qeb.estimated_elimination_rate,
                "protocol_text": qeb.protocol_text[:300] if qeb.protocol_text else "",
            })

        # Load and format prompt
        prompt_template = self._load_prompt("stage12_funnel_clustering.txt")
        prompt = prompt_template.format(
            therapeutic_area=therapeutic_area or "General",
            protocol_context=f"Protocol: {protocol_id}",
            criteria_json=json.dumps(criteria_for_prompt, indent=2),
        )

        # Call LLM with retry logic
        result_text = await self._call_llm_with_retry(prompt, "funnel_clustering")
        clustering_result = self._parse_llm_json_response(result_text)

        funnel_stages = []
        if clustering_result and isinstance(clustering_result, dict):
            # Build funnel stages and update QEBs
            stages_data = clustering_result.get("funnel_stages", [])
            qeb_lookup = {q.qeb_id: q for q in qebs}

            for stage_data in stages_data:
                stage = QEBFunnelStage(
                    stage_id=f"FS_{stage_data.get('stage_order', 0)}",
                    stage_name=stage_data.get("stage_name", "Unknown Stage"),
                    stage_order=stage_data.get("stage_order", 0),
                    qeb_ids=stage_data.get("qeb_ids", []),
                    combined_elimination_rate=stage_data.get("estimated_elimination_rate", 0.0),
                    stage_description=stage_data.get("stage_description"),
                )
                funnel_stages.append(stage)

                # Update QEBs with stage info
                for qeb_id in stage.qeb_ids:
                    if qeb_id in qeb_lookup:
                        qeb_lookup[qeb_id].funnel_stage = stage.stage_name
                        qeb_lookup[qeb_id].funnel_stage_order = stage.stage_order
        else:
            # Create a default stage with all QEBs when LLM fails
            warning = "Funnel clustering LLM failed - using single default stage"
            logger.warning(warning)
            self._llm_warnings.append(warning)

            default_stage = QEBFunnelStage(
                stage_id="FS_1",
                stage_name="All Criteria",
                stage_order=1,
                qeb_ids=[q.qeb_id for q in qebs],
                combined_elimination_rate=0.0,
            )
            funnel_stages.append(default_stage)
            for qeb in qebs:
                qeb.funnel_stage = "All Criteria"
                qeb.funnel_stage_order = 1

        return qebs, funnel_stages

    async def _identify_killer_criteria(
        self,
        qebs: List[QueryableEligibilityBlock],
        therapeutic_area: Optional[str],
    ) -> List[str]:
        """
        Collect killer criteria from LLM assessment results.

        The actual killer identification is done by the LLM in the queryable
        assessment step. This method collects those IDs.

        IMPORTANT: Killer criteria MUST have epidemiological evidence backing.
        We do not mark criteria as killers based on speculation.

        Args:
            qebs: List of QEBs (with is_killer_criterion already set by assessment).
            therapeutic_area: Therapeutic area for context.

        Returns:
            List of QEB IDs that are killer criteria.
        """
        killer_ids = []

        for qeb in qebs:
            # Only include as killer if:
            # 1. LLM marked it as killer AND
            # 2. Epidemiological evidence exists
            if qeb.is_killer_criterion and qeb.epidemiological_evidence:
                killer_ids.append(qeb.qeb_id)
                evidence_preview = qeb.epidemiological_evidence[:80] + "..." if len(qeb.epidemiological_evidence) > 80 else qeb.epidemiological_evidence
                logger.info(
                    f"Killer criterion: {qeb.qeb_id} - {qeb.clinical_name} "
                    f"(elimination: {qeb.estimated_elimination_rate}%, "
                    f"evidence: {evidence_preview})"
                )
            elif qeb.is_killer_criterion and not qeb.epidemiological_evidence:
                # LLM marked as killer but no evidence - downgrade
                logger.warning(
                    f"Downgrading {qeb.qeb_id} from killer - no epidemiological evidence provided"
                )
                qeb.is_killer_criterion = False

        return killer_ids

    def _build_logical_groups(
        self,
        qebs: List[QueryableEligibilityBlock],
        atomics: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Build logical groups mapping QEBs to their atomics for validation UI.

        Each logical group represents a QEB with its associated atomic IDs,
        allowing the validation UI to display and manage atomics within their
        QEB context.

        Args:
            qebs: List of QEBs (with funnel stage and killer status set).
            atomics: List of atomic criteria with queryabilityClassification.

        Returns:
            List of logical group dictionaries for validation UI.
        """
        logical_groups = []

        # Build atomic lookup by original criterion ID
        atomics_by_criterion: Dict[str, List[str]] = {}
        for atomic in atomics:
            criterion_id = atomic.get("originalCriterionId", "")
            atomic_id = atomic.get("atomicId", "")
            if criterion_id and atomic_id:
                if criterion_id not in atomics_by_criterion:
                    atomics_by_criterion[criterion_id] = []
                atomics_by_criterion[criterion_id].append(atomic_id)

        for qeb in qebs:
            criterion_id = qeb.original_criterion_id

            # Get atomic IDs either from QEB directly or from lookup
            atomic_ids = qeb.atomic_ids if qeb.atomic_ids else atomics_by_criterion.get(criterion_id, [])

            logical_group = {
                "qebId": qeb.qeb_id,
                "criterionType": qeb.criterion_type,
                "criterionText": qeb.protocol_text[:500] if qeb.protocol_text else qeb.clinical_name,
                "clinicalName": qeb.clinical_name,
                "atomicIds": atomic_ids,
                "funnelStage": qeb.funnel_stage_order,
                "funnelStageName": qeb.funnel_stage,
                "isKiller": qeb.is_killer_criterion,
                "queryableStatus": qeb.queryable_status,
            }
            logical_groups.append(logical_group)

        logger.debug(f"Built {len(logical_groups)} logical groups from {len(qebs)} QEBs")
        return logical_groups

    def _build_qeb_output(
        self,
        qebs: List[QueryableEligibilityBlock],
        funnel_stages: List[QEBFunnelStage],
        protocol_id: str,
        therapeutic_area: Optional[str],
        atomics: List[Dict[str, Any]],
        logical_groups: List[Dict[str, Any]],
        llm_warnings: Optional[List[str]] = None,
        processing_time: Optional[float] = None,
    ) -> QEBOutput:
        """Build the final QEB output structure."""
        total_atomics = len(atomics)

        # Calculate summary statistics
        inclusion_count = sum(1 for q in qebs if q.criterion_type == "inclusion")
        exclusion_count = sum(1 for q in qebs if q.criterion_type == "exclusion")
        killer_count = sum(1 for q in qebs if q.is_killer_criterion)

        # Data source-aware queryability counts
        fully_queryable = sum(1 for q in qebs if q.queryable_status == "fully_queryable")
        llm_extractable = sum(1 for q in qebs if q.queryable_status == "llm_extractable")
        hybrid_queryable = sum(1 for q in qebs if q.queryable_status == "hybrid_queryable")
        screening_only = sum(1 for q in qebs if q.queryable_status == "screening_only")
        not_applicable = sum(1 for q in qebs if q.queryable_status == "not_applicable")

        # Legacy counts for backward compatibility
        partially_queryable = sum(1 for q in qebs if q.queryable_status == "partially_queryable")
        requires_manual = sum(1 for q in qebs if q.queryable_status == "requires_manual")

        # Calculate unique OMOP concepts across all atomics (before QEB consolidation)
        all_concepts = set()
        for qeb in qebs:
            for c in qeb.omop_concepts:
                all_concepts.add(c.concept_id)

        # Deduplication rate: How much consolidation happened from atomics to QEBs
        if total_atomics > 0 and len(all_concepts) > 0:
            dedup_rate = 1.0 - (len(all_concepts) / total_atomics)
            dedup_rate = max(0.0, dedup_rate)
        else:
            dedup_rate = 0.0

        summary = QEBSummary(
            total_qebs=len(qebs),
            inclusion_qebs=inclusion_count,
            exclusion_qebs=exclusion_count,
            # Data source-aware queryability
            fully_queryable=fully_queryable,
            llm_extractable=llm_extractable,
            hybrid_queryable=hybrid_queryable,
            screening_only=screening_only,
            not_applicable=not_applicable,
            # Legacy (backward compatibility)
            partially_queryable=partially_queryable,
            requires_manual_review=requires_manual,
            total_atomics_consolidated=total_atomics,
            unique_omop_concepts=len(all_concepts),
            deduplication_rate=dedup_rate,
            killer_criteria_count=killer_count,
            funnel_stages_count=len(funnel_stages),
            eligibility_page_start=getattr(self, '_eligibility_page_start', None),
            eligibility_page_end=getattr(self, '_eligibility_page_end', None),
        )

        # Build execution guide
        # Recommended order: by funnel stage order, then by elimination rate (highest first)
        # Handle None elimination rates by treating them as 0
        sorted_qebs = sorted(
            qebs,
            key=lambda q: (q.funnel_stage_order, -(q.estimated_elimination_rate or 0)),
        )
        recommended_order = [q.qeb_id for q in sorted_qebs]

        killer_criteria = [q.qeb_id for q in qebs if q.is_killer_criterion]
        manual_review = [q.qeb_id for q in qebs if q.queryable_status == "requires_manual"]

        execution_guide = QEBExecutionGuide(
            recommended_order=recommended_order,
            killer_criteria=killer_criteria,
            manual_review_required=manual_review,
            execution_notes="Execute criteria in recommended order for optimal patient elimination. "
                          "Killer criteria should be prioritized as they eliminate the most patients.",
        )

        return QEBOutput(
            protocol_id=protocol_id,
            therapeutic_area=therapeutic_area,
            summary=summary,
            funnel_stages=funnel_stages,
            queryable_blocks=qebs,
            execution_guide=execution_guide,
            atomic_criteria=atomics,
            logical_groups=logical_groups,
            processing_time_seconds=processing_time or 0.0,
            llm_model_used=self.GEMINI_MODEL,
            stage_inputs_used=["stage2", "stage11_eligibility_funnel"],
            llm_warnings=llm_warnings or [],
        )


def run_stage12(
    eligibility_funnel: Dict[str, Any],
    stage2_result: Dict[str, Any],
    raw_criteria: List[Dict[str, Any]],
    protocol_id: str,
    output_dir: Optional[Path] = None,
    therapeutic_area: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to run Stage 12 QEB Builder synchronously.

    Args:
        eligibility_funnel: Output from Stage 11 eligibility funnel builder.
        stage2_result: Output from Stage 2 atomic decomposition.
        raw_criteria: Original extracted criteria.
        protocol_id: Protocol identifier.
        output_dir: Directory for output files.
        therapeutic_area: Optional therapeutic area for context.

    Returns:
        Stage result dictionary containing QEB output.
    """
    import asyncio

    builder = Stage12QEBBuilder(output_dir=output_dir)
    return asyncio.run(
        builder.run(
            eligibility_funnel=eligibility_funnel,
            stage2_result=stage2_result,
            raw_criteria=raw_criteria,
            protocol_id=protocol_id,
            therapeutic_area=therapeutic_area,
        )
    )
