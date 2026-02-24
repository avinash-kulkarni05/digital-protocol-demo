"""
Funnel Executor for QEB Validation

Executes validated QEBs through sequential funnel stages to produce
patient cohort filtering results. Supports both mock and real database
adapters for development, testing, and production use cases.

Key Design Principles:
- RECALL over PRECISION at feasibility stage
- Sequential stage execution (killer criteria first)
- INTERSECTION for inclusion criteria
- EXCEPT (set difference) for exclusion criteria
- Skips non-queryable QEBs (SCREENING_ONLY, NOT_APPLICABLE)
"""

import logging
from datetime import datetime
from typing import Dict, List, Set, Any, TYPE_CHECKING

from ..review.qeb_validation_models import (
    ValidationSession,
    FunnelStageConfig,
    FunnelStageResult,
    QEBExecutionResult,
    FunnelExecutionResult,
)
from .database_adapters import DatabaseAdapter

if TYPE_CHECKING:
    from ..review.qeb_validation_service import QEBValidationService

logger = logging.getLogger(__name__)


class FunnelExecutor:
    """
    Execute validated QEBs through funnel stages.

    The executor processes QEBs in stage order:
    1. For each stage, process inclusion QEBs (INTERSECT all)
    2. Then process exclusion QEBs (EXCEPT all)
    3. Pass remaining cohort to next stage

    QEBs with no QUERYABLE atomics are skipped and marked as such.
    """

    def __init__(
        self,
        database_adapter: DatabaseAdapter,
        validation_service: "QEBValidationService",
    ):
        """
        Initialize funnel executor.

        Args:
            database_adapter: Database adapter for patient filtering.
            validation_service: Validation service for checking overrides/corrections.
        """
        self.db = database_adapter
        self.validation_service = validation_service

    def execute_funnel(
        self,
        session: ValidationSession,
        qeb_lookup: Dict[str, Dict[str, Any]],
    ) -> FunnelExecutionResult:
        """
        Execute all funnel stages sequentially.

        Args:
            session: ValidationSession with configuration and overrides.
            qeb_lookup: Dictionary mapping qeb_id -> QEB data.

        Returns:
            FunnelExecutionResult with all stage results.
        """
        logger.info(f"Starting funnel execution for session {session.session_id}")

        current_cohort = self.db.get_base_population()
        base_population = len(current_cohort)
        stage_results: List[FunnelStageResult] = []

        for stage_config in session.funnel_stages:
            # Skip empty stages
            if not stage_config.inclusion_qeb_ids and not stage_config.exclusion_qeb_ids:
                logger.debug(f"Skipping empty stage {stage_config.stage_number}")
                continue

            stage_result = self._execute_stage(
                stage_config=stage_config,
                cohort=current_cohort,
                qeb_lookup=qeb_lookup,
                session=session,
            )
            stage_results.append(stage_result)
            current_cohort = stage_result.remaining_patient_ids

            logger.info(
                f"Stage {stage_config.stage_number} ({stage_config.stage_name}): "
                f"{stage_result.patients_entering:,} -> {stage_result.patients_exiting:,} "
                f"({stage_result.elimination_rate:.1%} eliminated)"
            )

        final_population = len(current_cohort)
        overall_elimination = 1 - (final_population / base_population) if base_population > 0 else 0

        result = FunnelExecutionResult(
            session_id=session.session_id,
            executed_at=datetime.utcnow(),
            database_name=self.db.name,
            base_population=base_population,
            final_population=final_population,
            overall_elimination_rate=overall_elimination,
            stage_results=stage_results,
        )

        logger.info(
            f"Funnel execution complete: {base_population:,} -> {final_population:,} "
            f"({overall_elimination:.2%} overall elimination)"
        )

        return result

    def _execute_stage(
        self,
        stage_config: FunnelStageConfig,
        cohort: Set[int],
        qeb_lookup: Dict[str, Dict[str, Any]],
        session: ValidationSession,
    ) -> FunnelStageResult:
        """
        Execute single stage: inclusion (INTERSECT) then exclusion (EXCEPT).

        Args:
            stage_config: Stage configuration.
            cohort: Current patient cohort.
            qeb_lookup: Dictionary mapping qeb_id -> QEB data.
            session: ValidationSession with overrides.

        Returns:
            FunnelStageResult with QEB results.
        """
        before_count = len(cohort)
        qeb_results: List[QEBExecutionResult] = []

        # Process inclusion QEBs: INTERSECT all (patients must match ALL)
        for qeb_id in stage_config.inclusion_qeb_ids:
            qeb_data = qeb_lookup.get(qeb_id)
            if not qeb_data:
                logger.warning(f"QEB {qeb_id} not found in lookup, skipping")
                continue

            result = self._execute_qeb(
                qeb_id=qeb_id,
                qeb_data=qeb_data,
                cohort=cohort,
                session=session,
                is_inclusion=True,
            )
            qeb_results.append(result)

            if not result.was_skipped:
                # INTERSECT: keep only patients matching this inclusion criterion
                cohort = cohort.intersection(result.matching_patient_ids)
                logger.debug(
                    f"  INC {qeb_id}: {result.patients_before:,} -> {len(cohort):,}"
                )

        # Process exclusion QEBs: EXCEPT all (remove patients matching ANY)
        for qeb_id in stage_config.exclusion_qeb_ids:
            qeb_data = qeb_lookup.get(qeb_id)
            if not qeb_data:
                logger.warning(f"QEB {qeb_id} not found in lookup, skipping")
                continue

            result = self._execute_qeb(
                qeb_id=qeb_id,
                qeb_data=qeb_data,
                cohort=cohort,
                session=session,
                is_inclusion=False,
            )
            qeb_results.append(result)

            if not result.was_skipped:
                # EXCEPT: remove patients matching this exclusion criterion
                cohort = cohort - result.matching_patient_ids
                logger.debug(
                    f"  EXC {qeb_id}: {result.patients_before:,} -> {len(cohort):,}"
                )

        after_count = len(cohort)
        elimination_rate = 1 - (after_count / before_count) if before_count > 0 else 0

        return FunnelStageResult(
            stage_number=stage_config.stage_number,
            stage_name=stage_config.stage_name,
            patients_entering=before_count,
            patients_exiting=after_count,
            elimination_rate=elimination_rate,
            qeb_results=qeb_results,
            remaining_patient_ids=cohort,
        )

    def _execute_qeb(
        self,
        qeb_id: str,
        qeb_data: Dict[str, Any],
        cohort: Set[int],
        session: ValidationSession,
        is_inclusion: bool,
    ) -> QEBExecutionResult:
        """
        Execute single QEB against cohort.

        Args:
            qeb_id: QEB identifier.
            qeb_data: QEB data dictionary.
            cohort: Current patient cohort.
            session: ValidationSession with overrides.
            is_inclusion: True for inclusion criteria, False for exclusion.

        Returns:
            QEBExecutionResult with matching patients.
        """
        criterion_text = qeb_data.get("criterionText", "")

        # Check if all queryable atomics after overrides
        # Uses validation_service for user overrides
        effective_queryable = self.validation_service.get_effective_queryable_count(
            qeb_id=qeb_id,
            qeb_data=qeb_data,
            session=session,
        )

        if effective_queryable == 0:
            # All atomics are SCREENING_ONLY or NOT_APPLICABLE - skip
            logger.debug(f"  {qeb_id}: SKIPPED (no queryable atomics)")
            return QEBExecutionResult(
                qeb_id=qeb_id,
                criterion_text=criterion_text,
                patients_before=len(cohort),
                patients_after=len(cohort),
                sql_executed="-- SKIPPED (no queryable atomics)",
                was_skipped=True,
                # For skipped inclusion: return empty (would filter everyone out)
                # For skipped exclusion: return empty (no one to exclude)
                matching_patient_ids=set(),
            )

        # Execute against database (mock or real)
        sql = qeb_data.get("sqlQuery", "")
        omop_concepts = self.validation_service.extract_concept_ids_from_qeb(
            qeb_data=qeb_data,
            session=session,
        )

        # Use database adapter to filter cohort
        matching = self.db.filter_cohort_by_concepts(
            cohort=cohort,
            concept_ids=omop_concepts,
            is_inclusion=is_inclusion,
        )

        # Calculate patients_after based on operation type
        if is_inclusion:
            patients_after = len(cohort.intersection(matching))
        else:
            patients_after = len(cohort - matching)

        return QEBExecutionResult(
            qeb_id=qeb_id,
            criterion_text=criterion_text,
            patients_before=len(cohort),
            patients_after=patients_after,
            sql_executed=sql,
            was_skipped=False,
            matching_patient_ids=matching,
        )

    def execute_single_qeb(
        self,
        qeb_id: str,
        qeb_data: Dict[str, Any],
        session: ValidationSession,
        is_inclusion: bool = True,
    ) -> QEBExecutionResult:
        """
        Execute a single QEB against full base population.

        Useful for testing individual criteria.

        Args:
            qeb_id: QEB identifier.
            qeb_data: QEB data dictionary.
            session: ValidationSession with overrides.
            is_inclusion: True for inclusion criteria, False for exclusion.

        Returns:
            QEBExecutionResult with matching patients.
        """
        cohort = self.db.get_base_population()
        return self._execute_qeb(
            qeb_id=qeb_id,
            qeb_data=qeb_data,
            cohort=cohort,
            session=session,
            is_inclusion=is_inclusion,
        )


def execute_validation_funnel(
    session: ValidationSession,
    qeb_output_path: str,
    database_adapter: DatabaseAdapter,
    validation_service: "QEBValidationService",
) -> FunnelExecutionResult:
    """
    Convenience function to execute funnel from validation session.

    Args:
        session: ValidationSession with configuration.
        qeb_output_path: Path to eligibility_funnel_v2.json.
        database_adapter: Database adapter for patient filtering.
        validation_service: Validation service instance.

    Returns:
        FunnelExecutionResult with all stage results.
    """
    import json

    # Load QEB data
    with open(qeb_output_path, "r", encoding="utf-8") as f:
        qeb_data = json.load(f)

    # Build QEB lookup from logical groups
    qeb_lookup: Dict[str, Dict[str, Any]] = {}
    for group in qeb_data.get("logicalGroups", []):
        qeb_id = group.get("qebId", "")
        if qeb_id:
            qeb_lookup[qeb_id] = group

    # Execute funnel
    executor = FunnelExecutor(
        database_adapter=database_adapter,
        validation_service=validation_service,
    )

    return executor.execute_funnel(
        session=session,
        qeb_lookup=qeb_lookup,
    )
