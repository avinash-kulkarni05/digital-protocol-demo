"""
QEB Validation Service

Business logic for Human-in-the-Loop QEB validation sessions.
Handles session management, classification overrides, OMOP corrections,
and funnel execution readiness checks.
"""

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from .qeb_validation_models import (
    AtomicWithClassification,
    ClassificationOverride,
    OMOPCorrection,
    QEBClassificationSummary,
    ClassificationSummary,
    ValidationSession,
    FunnelStageConfig,
)

logger = logging.getLogger(__name__)


class QEBValidationService:
    """Service for loading, validating, and saving QEB validation sessions."""

    # Default funnel stage names (8 stages)
    DEFAULT_FUNNEL_STAGES = [
        (1, "Disease Indication"),
        (2, "Demographics"),
        (3, "Organ Function"),
        (4, "Treatment History"),
        (5, "Comorbidities"),
        (6, "Lab Values"),
        (7, "Concomitant Medications"),
        (8, "Other Requirements"),
    ]

    def __init__(self, athena_db_path: Optional[str] = None):
        """
        Initialize validation service.

        Args:
            athena_db_path: Path to ATHENA SQLite database for concept search.
                          If None, uses ATHENA_DB_PATH environment variable.
        """
        self.athena_db_path = athena_db_path or os.environ.get("ATHENA_DB_PATH")
        self._qeb_cache: Dict[str, Dict[str, Any]] = {}  # session_id -> QEB data

    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================

    def create_session(
        self,
        protocol_id: str,
        protocol_name: str,
        qeb_output_path: str,
    ) -> ValidationSession:
        """
        Create new validation session from QEB output.

        Args:
            protocol_id: Protocol identifier (e.g., NCT number).
            protocol_name: Human-readable protocol name.
            qeb_output_path: Path to eligibility_funnel_v2.json file.

        Returns:
            New ValidationSession instance.
        """
        session_id = str(uuid.uuid4())

        # Load QEB data to initialize funnel stages
        qeb_data = self._load_qeb_data(qeb_output_path)
        funnel_stages = self._initialize_funnel_stages(qeb_data)

        session = ValidationSession(
            session_id=session_id,
            protocol_id=protocol_id,
            protocol_name=protocol_name,
            qeb_output_path=qeb_output_path,
            llm_recommendation_accepted=False,
            classification_overrides=[],
            omop_corrections=[],
            funnel_stages=funnel_stages,
            execution_result=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            completed_at=None,
        )

        # Cache the QEB data
        self._qeb_cache[session_id] = qeb_data

        logger.info(f"Created validation session {session_id} for protocol {protocol_id}")
        return session

    def load_session(self, session_path: str) -> ValidationSession:
        """
        Load existing session from JSON file.

        Args:
            session_path: Path to validation session JSON file.

        Returns:
            Loaded ValidationSession instance.
        """
        with open(session_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        session = ValidationSession.from_dict(data)

        # Load QEB data into cache
        if session.qeb_output_path and Path(session.qeb_output_path).exists():
            self._qeb_cache[session.session_id] = self._load_qeb_data(session.qeb_output_path)

        logger.info(f"Loaded validation session {session.session_id}")
        return session

    def save_session(self, session: ValidationSession, output_dir: Optional[Path] = None) -> Path:
        """
        Save session state to JSON file.

        Args:
            session: ValidationSession to save.
            output_dir: Directory to save to. If None, uses parent of qeb_output_path.

        Returns:
            Path to saved session file.
        """
        session.updated_at = datetime.utcnow()

        if output_dir is None:
            output_dir = Path(session.qeb_output_path).parent / "validation"
        output_dir.mkdir(parents=True, exist_ok=True)

        session_path = output_dir / f"validation_session_{session.session_id}.json"
        with open(session_path, "w", encoding="utf-8") as f:
            f.write(session.to_json())

        logger.info(f"Saved validation session to {session_path}")
        return session_path

    def _load_qeb_data(self, qeb_output_path: str) -> Dict[str, Any]:
        """Load QEB data from eligibility_funnel_v2.json file."""
        with open(qeb_output_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _initialize_funnel_stages(self, qeb_data: Dict[str, Any]) -> List[FunnelStageConfig]:
        """Initialize funnel stages from QEB data or use defaults."""
        # Try to get stages from QEB data
        logical_groups = qeb_data.get("logicalGroups", [])

        if logical_groups:
            # Group QEBs by their funnel stage (if available)
            stage_qebs: Dict[int, Tuple[List[str], List[str]]] = {}
            for group in logical_groups:
                stage_num = group.get("funnelStage", 1)
                qeb_id = group.get("qebId", "")
                criterion_type = group.get("criterionType", "inclusion")

                if stage_num not in stage_qebs:
                    stage_qebs[stage_num] = ([], [])

                if criterion_type == "inclusion":
                    stage_qebs[stage_num][0].append(qeb_id)
                else:
                    stage_qebs[stage_num][1].append(qeb_id)

            # Build stage configs
            stages = []
            for stage_num, stage_name in self.DEFAULT_FUNNEL_STAGES:
                inclusion_ids, exclusion_ids = stage_qebs.get(stage_num, ([], []))
                stages.append(FunnelStageConfig(
                    stage_number=stage_num,
                    stage_name=stage_name,
                    inclusion_qeb_ids=inclusion_ids,
                    exclusion_qeb_ids=exclusion_ids,
                ))
            return stages

        # Return default empty stages
        return [
            FunnelStageConfig(stage_number=num, stage_name=name)
            for num, name in self.DEFAULT_FUNNEL_STAGES
        ]

    # =========================================================================
    # CLASSIFICATION SUMMARY (What user sees first)
    # =========================================================================

    def get_classification_summary(self, session: ValidationSession) -> ClassificationSummary:
        """
        Get protocol-wide classification counts.

        Args:
            session: ValidationSession to analyze.

        Returns:
            ClassificationSummary with aggregate counts.
        """
        qeb_data = self._get_qeb_data(session)
        atomics = qeb_data.get("atomicCriteria", [])

        queryable = 0
        screening_only = 0
        not_applicable = 0
        unmapped = 0
        killer_count = 0

        for atomic in atomics:
            # Apply any user overrides
            effective_category = self._get_effective_classification(
                atomic, session.classification_overrides
            )

            if effective_category == "QUERYABLE":
                queryable += 1
            elif effective_category == "SCREENING_ONLY":
                screening_only += 1
            else:
                not_applicable += 1

            # Check if unmapped (no OMOP concept and no user correction)
            if self._is_unmapped(atomic, session.omop_corrections):
                unmapped += 1

        # Count killer criteria
        logical_groups = qeb_data.get("logicalGroups", [])
        for group in logical_groups:
            if group.get("isKiller", False):
                killer_count += 1

        return ClassificationSummary(
            total_atomics=len(atomics),
            queryable_atomics=queryable,
            screening_only_atomics=screening_only,
            not_applicable_atomics=not_applicable,
            unmapped_atomics=unmapped,
            killer_criteria_count=killer_count,
        )

    def get_qeb_summaries(self, session: ValidationSession) -> List[QEBClassificationSummary]:
        """
        Get classification summary for each QEB.

        Args:
            session: ValidationSession to analyze.

        Returns:
            List of QEBClassificationSummary for each QEB.
        """
        qeb_data = self._get_qeb_data(session)
        logical_groups = qeb_data.get("logicalGroups", [])
        atomic_criteria = qeb_data.get("atomicCriteria", [])

        # Build atomic lookup by ID
        atomic_lookup = {a.get("atomicId"): a for a in atomic_criteria}

        summaries = []
        for group in logical_groups:
            qeb_id = group.get("qebId", "")
            atomic_ids = group.get("atomicIds", [])

            queryable = 0
            screening_only = 0
            not_applicable = 0
            unmapped = 0

            for atomic_id in atomic_ids:
                atomic = atomic_lookup.get(atomic_id, {})
                effective_category = self._get_effective_classification(
                    atomic, session.classification_overrides
                )

                if effective_category == "QUERYABLE":
                    queryable += 1
                elif effective_category == "SCREENING_ONLY":
                    screening_only += 1
                else:
                    not_applicable += 1

                if self._is_unmapped(atomic, session.omop_corrections):
                    unmapped += 1

            summaries.append(QEBClassificationSummary(
                qeb_id=qeb_id,
                criterion_type=group.get("criterionType", "inclusion"),
                criterion_text=group.get("criterionText", ""),
                total_atomics=len(atomic_ids),
                queryable_count=queryable,
                screening_only_count=screening_only,
                not_applicable_count=not_applicable,
                unmapped_count=unmapped,
                is_queryable=queryable > 0,
                is_killer=group.get("isKiller", False),
                funnel_stage=group.get("funnelStage", 1),
                elimination_estimate=group.get("eliminationEstimate"),
            ))

        return summaries

    # =========================================================================
    # ATOMIC-LEVEL OPERATIONS
    # =========================================================================

    def get_atomics_by_category(
        self,
        session: ValidationSession,
        category: str,
    ) -> List[AtomicWithClassification]:
        """
        Get all atomics in a category (QUERYABLE, SCREENING_ONLY, NOT_APPLICABLE).

        Args:
            session: ValidationSession to analyze.
            category: Classification category to filter by.

        Returns:
            List of AtomicWithClassification matching the category.
        """
        qeb_data = self._get_qeb_data(session)
        atomics = qeb_data.get("atomicCriteria", [])

        result = []
        for atomic in atomics:
            effective_category = self._get_effective_classification(
                atomic, session.classification_overrides
            )
            if effective_category == category:
                result.append(self._convert_to_atomic_with_classification(
                    atomic, session.omop_corrections
                ))

        return result

    def get_unmapped_atomics(self, session: ValidationSession) -> List[AtomicWithClassification]:
        """
        Get all atomics with no OMOP mapping.

        Args:
            session: ValidationSession to analyze.

        Returns:
            List of AtomicWithClassification that are unmapped.
        """
        qeb_data = self._get_qeb_data(session)
        atomics = qeb_data.get("atomicCriteria", [])

        result = []
        for atomic in atomics:
            if self._is_unmapped(atomic, session.omop_corrections):
                result.append(self._convert_to_atomic_with_classification(
                    atomic, session.omop_corrections
                ))

        return result

    def override_classification(
        self,
        session: ValidationSession,
        override: ClassificationOverride,
    ) -> None:
        """
        Apply user override to atomic classification.

        Args:
            session: ValidationSession to modify.
            override: Classification override to apply.
        """
        # Remove any existing override for this atomic
        session.classification_overrides = [
            o for o in session.classification_overrides
            if o.atomic_id != override.atomic_id
        ]

        # Add new override
        session.classification_overrides.append(override)
        session.updated_at = datetime.utcnow()

        logger.info(
            f"Applied classification override for atomic {override.atomic_id}: "
            f"{override.original_category} -> {override.new_category}"
        )

    def apply_omop_correction(
        self,
        session: ValidationSession,
        correction: OMOPCorrection,
    ) -> None:
        """
        Apply user-provided OMOP mapping for unmapped term.

        Args:
            session: ValidationSession to modify.
            correction: OMOP correction to apply.
        """
        # Remove any existing correction for this atomic
        session.omop_corrections = [
            c for c in session.omop_corrections
            if c.atomic_id != correction.atomic_id
        ]

        # Add new correction
        session.omop_corrections.append(correction)
        session.updated_at = datetime.utcnow()

        logger.info(
            f"Applied OMOP correction for atomic {correction.atomic_id}: "
            f"'{correction.original_term}' -> {correction.selected_concept_id} ({correction.selected_concept_name})"
        )

    # =========================================================================
    # OMOP CONCEPT SEARCH
    # =========================================================================

    def search_omop_concepts(
        self,
        term: str,
        domain: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Search ATHENA for OMOP concepts.

        Args:
            term: Search term.
            domain: Optional domain filter (Condition, Drug, Measurement, Procedure).
            limit: Maximum results to return.

        Returns:
            List of matching concept dictionaries.
        """
        if not self.athena_db_path or not Path(self.athena_db_path).exists():
            logger.warning("ATHENA database not available for concept search")
            return []

        try:
            conn = sqlite3.connect(self.athena_db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Build search query
            search_pattern = f"%{term}%"

            if domain:
                query = """
                    SELECT concept_id, concept_name, domain_id, vocabulary_id,
                           concept_class_id, standard_concept
                    FROM concept
                    WHERE concept_name LIKE ?
                      AND domain_id = ?
                      AND standard_concept = 'S'
                    ORDER BY
                        CASE WHEN concept_name LIKE ? THEN 0 ELSE 1 END,
                        LENGTH(concept_name)
                    LIMIT ?
                """
                cursor.execute(query, (search_pattern, domain, f"{term}%", limit))
            else:
                query = """
                    SELECT concept_id, concept_name, domain_id, vocabulary_id,
                           concept_class_id, standard_concept
                    FROM concept
                    WHERE concept_name LIKE ?
                      AND standard_concept = 'S'
                    ORDER BY
                        CASE WHEN concept_name LIKE ? THEN 0 ELSE 1 END,
                        LENGTH(concept_name)
                    LIMIT ?
                """
                cursor.execute(query, (search_pattern, f"{term}%", limit))

            results = []
            for row in cursor.fetchall():
                results.append({
                    "conceptId": row["concept_id"],
                    "conceptName": row["concept_name"],
                    "domain": row["domain_id"],
                    "vocabulary": row["vocabulary_id"],
                    "conceptClass": row["concept_class_id"],
                    "isStandard": row["standard_concept"] == "S",
                })

            conn.close()
            return results

        except Exception as e:
            logger.error(f"OMOP concept search failed: {e}")
            return []

    # =========================================================================
    # FUNNEL MANAGEMENT
    # =========================================================================

    def get_funnel_stages(self, session: ValidationSession) -> List[FunnelStageConfig]:
        """Get funnel stage configuration."""
        return session.funnel_stages

    def is_ready_for_execution(
        self,
        session: ValidationSession,
    ) -> Tuple[bool, List[str]]:
        """
        Check if session is ready for funnel execution.

        Args:
            session: ValidationSession to check.

        Returns:
            Tuple of (ready, blocking_reasons).
        """
        blocking_reasons = []

        # Check if LLM recommendation was accepted or classifications reviewed
        if not session.llm_recommendation_accepted and not session.classification_overrides:
            blocking_reasons.append("LLM recommendation not reviewed")

        # Check for unmapped concepts
        unmapped = self.get_unmapped_atomics(session)
        if unmapped:
            blocking_reasons.append(
                f"{len(unmapped)} atomics have UNMAPPED OMOP concepts"
            )

        # Check if funnel stages are configured
        total_qebs = sum(
            len(s.inclusion_qeb_ids) + len(s.exclusion_qeb_ids)
            for s in session.funnel_stages
        )
        if total_qebs == 0:
            blocking_reasons.append("No QEBs assigned to funnel stages")

        ready = len(blocking_reasons) == 0
        return ready, blocking_reasons

    # =========================================================================
    # LLM RECOMMENDATION WORKFLOW
    # =========================================================================

    def accept_recommendation(self, session: ValidationSession) -> None:
        """
        Accept LLM's classification recommendation (Workflow A fast path).

        Args:
            session: ValidationSession to update.
        """
        session.llm_recommendation_accepted = True
        session.updated_at = datetime.utcnow()
        logger.info(f"Accepted LLM recommendation for session {session.session_id}")

    # =========================================================================
    # HELPER METHODS (used by FunnelExecutor)
    # =========================================================================

    def get_effective_queryable_count(
        self,
        qeb_id: str,
        qeb_data: Dict[str, Any],
        session: ValidationSession,
    ) -> int:
        """
        Get count of QUERYABLE atomics after applying user overrides.
        Used by FunnelExecutor to determine if QEB should be skipped.

        Args:
            qeb_id: QEB identifier.
            qeb_data: QEB data dictionary (from logicalGroups).
            session: ValidationSession with user overrides.

        Returns:
            Count of QUERYABLE atomics.
        """
        # Get atomic IDs from QEB, then look up atomics from session cache
        atomic_ids = qeb_data.get("atomicIds", [])
        full_qeb_data = self._get_qeb_data(session)
        atomic_criteria = full_qeb_data.get("atomicCriteria", [])
        atomic_lookup = {a.get("atomicId"): a for a in atomic_criteria}

        count = 0
        for atomic_id in atomic_ids:
            atomic = atomic_lookup.get(atomic_id, {})
            effective_category = self._get_effective_classification(
                atomic, session.classification_overrides
            )
            if effective_category == "QUERYABLE":
                count += 1

        return count

    def extract_concept_ids_from_qeb(
        self,
        qeb_data: Dict[str, Any],
        session: ValidationSession,
    ) -> List[int]:
        """
        Extract OMOP concept IDs from QEB atomics, including user corrections.
        Used by FunnelExecutor for mock database filtering.

        Args:
            qeb_data: QEB data dictionary (from logicalGroups).
            session: ValidationSession with user corrections.

        Returns:
            List of OMOP concept IDs.
        """
        # Get atomic IDs from QEB, then look up atomics from session cache
        atomic_ids = qeb_data.get("atomicIds", [])
        full_qeb_data = self._get_qeb_data(session)
        atomic_criteria = full_qeb_data.get("atomicCriteria", [])
        atomic_lookup = {a.get("atomicId"): a for a in atomic_criteria}

        concept_ids = []
        for atomic_id in atomic_ids:
            atomic = atomic_lookup.get(atomic_id, {})

            # Check if user corrected this atomic's OMOP mapping
            correction = next(
                (c for c in session.omop_corrections if c.atomic_id == atomic_id),
                None
            )

            if correction:
                concept_ids.append(correction.selected_concept_id)
            else:
                # Extract from omopQuery.conceptIds structure
                omop_query = atomic.get("omopQuery") or {}
                cids = omop_query.get("conceptIds", [])
                for cid in cids:
                    if cid and cid not in concept_ids:
                        concept_ids.append(cid)

        return concept_ids

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _get_qeb_data(self, session: ValidationSession) -> Dict[str, Any]:
        """Get QEB data from cache or load from file."""
        if session.session_id in self._qeb_cache:
            return self._qeb_cache[session.session_id]

        qeb_data = self._load_qeb_data(session.qeb_output_path)
        self._qeb_cache[session.session_id] = qeb_data
        return qeb_data

    def _get_effective_classification(
        self,
        atomic: Dict[str, Any],
        overrides: List[ClassificationOverride],
    ) -> str:
        """Get effective classification after applying user overrides."""
        atomic_id = atomic.get("atomicId", "")

        # Check for user override
        override = next(
            (o for o in overrides if o.atomic_id == atomic_id),
            None
        )

        if override:
            return override.new_category

        # Return LLM classification
        classification = atomic.get("queryabilityClassification", {})
        return classification.get("category", "SCREENING_ONLY")

    def _is_unmapped(
        self,
        atomic: Dict[str, Any],
        corrections: List[OMOPCorrection],
    ) -> bool:
        """Check if atomic is unmapped (no OMOP concept and no user correction)."""
        atomic_id = atomic.get("atomicId", "")

        # Check if user provided a correction
        has_correction = any(c.atomic_id == atomic_id for c in corrections)
        if has_correction:
            return False

        # Check if LLM found an OMOP concept (under omopQuery.conceptIds)
        omop_query = atomic.get("omopQuery") or {}
        concept_ids = omop_query.get("conceptIds", [])

        # Has mapping if there's at least one non-zero concept ID
        has_mapping = bool(concept_ids and any(cid for cid in concept_ids if cid))
        return not has_mapping

    def _convert_to_atomic_with_classification(
        self,
        atomic: Dict[str, Any],
        corrections: List[OMOPCorrection],
    ) -> AtomicWithClassification:
        """Convert raw atomic data to AtomicWithClassification."""
        atomic_id = atomic.get("atomicId", "")

        # Check for user correction
        correction = next(
            (c for c in corrections if c.atomic_id == atomic_id),
            None
        )

        if correction:
            omop_id = correction.selected_concept_id
            omop_name = correction.selected_concept_name
            is_unmapped = False
        else:
            # Extract from omopQuery.conceptIds structure
            omop_query = atomic.get("omopQuery") or {}
            concept_ids = omop_query.get("conceptIds", [])
            concept_names = omop_query.get("conceptNames", [])
            omop_id = concept_ids[0] if concept_ids else None
            omop_name = concept_names[0] if concept_names else None
            is_unmapped = not bool(concept_ids and any(cid for cid in concept_ids if cid))

        classification = atomic.get("queryabilityClassification", {})

        return AtomicWithClassification(
            atomic_id=atomic_id,
            text=atomic.get("text", ""),
            omop_concept_id=omop_id,
            omop_concept_name=omop_name,
            classification=classification.get("category", "SCREENING_ONLY"),
            classification_confidence=classification.get("confidence", 0.0),
            classification_reasoning=classification.get("reasoning", ""),
            is_unmapped=is_unmapped,
            qeb_id=atomic.get("qebId"),
        )
