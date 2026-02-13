"""
SOA Database Service - Save per-table results to PostgreSQL.

This module provides functions to persist SOA extraction results
to the database, enabling:
- Per-table USDM storage for granular review
- Quality tracking at table level
- Integration with main pipeline
- Human-in-the-loop workflows

Usage:
    from soa_db_service import save_soa_results_to_db

    # After running SOA extraction
    result = await run_soa_extraction(pdf_path)

    # Save to database
    soa_job_id = await save_soa_results_to_db(
        protocol_id=protocol_uuid,
        extraction_result=result,
    )
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from pathlib import Path
import sys

# Fix Python path
_this_dir = Path(__file__).parent.resolve()
_parent_dir = _this_dir.parent
if str(_parent_dir) not in sys.path:
    sys.path.insert(0, str(_parent_dir))

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


def save_soa_results_to_db(
    db: Session,
    protocol_id: str,
    protocol_name: Optional[str],
    extraction_result: Any,  # ExtractionResult from soa_extraction_pipeline
    detected_pages: Optional[Dict] = None,
) -> str:
    """
    Save SOA extraction results to database.

    Creates:
    - 1 SOAJob record (parent)
    - N SOATableResult records (one per table)

    Args:
        db: SQLAlchemy session
        protocol_id: UUID of the protocol
        protocol_name: Human-readable protocol name
        extraction_result: ExtractionResult from SOA pipeline
        detected_pages: Optional page detection data

    Returns:
        soa_job_id: UUID of created SOA job
    """
    from app.db import SOAJob, SOATableResult, SCHEMA_NAME

    # Create SOA job
    soa_job = SOAJob(
        id=uuid.uuid4(),
        protocol_id=uuid.UUID(protocol_id) if isinstance(protocol_id, str) else protocol_id,
        protocol_name=protocol_name or extraction_result.protocol_id,
        status="completed" if extraction_result.success else "failed",
        detected_pages=detected_pages,
        current_phase="completed" if extraction_result.success else "failed",
        phase_progress={
            "phases": [p.to_dict() for p in extraction_result.phases],
            "total_duration": extraction_result.total_duration,
        },
        usdm_data=extraction_result.usdm_data,  # Merged USDM if available
        error_message="; ".join(extraction_result.errors) if extraction_result.errors else None,
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow() if extraction_result.success else None,
    )

    db.add(soa_job)
    db.flush()  # Get the ID

    logger.info(f"Created SOAJob: {soa_job.id}")

    # Create per-table results
    for ptr in extraction_result.per_table_results:
        table_result = SOATableResult(
            id=uuid.uuid4(),
            soa_job_id=soa_job.id,
            protocol_id=soa_job.protocol_id,
            protocol_name=protocol_name,
            table_id=ptr.table_id,
            table_category=ptr.category,
            page_start=ptr.usdm.get("_tableMetadata", {}).get("pageStart", 0) if ptr.usdm else 0,
            page_end=ptr.usdm.get("_tableMetadata", {}).get("pageEnd", 0) if ptr.usdm else 0,
            status="success" if ptr.success else "failed",
            error_message=ptr.error,
            usdm_data=ptr.usdm,
            visits_count=ptr.counts.get("visits", 0),
            activities_count=ptr.counts.get("activities", 0),
            sais_count=ptr.counts.get("sais", 0),
            footnotes_count=ptr.counts.get("footnotes", 0),
        )

        db.add(table_result)
        logger.info(f"  Added SOATableResult: {ptr.table_id} ({ptr.category})")

    db.commit()

    logger.info(f"Saved {len(extraction_result.per_table_results)} table results to database")

    return str(soa_job.id)


def get_soa_job_with_tables(
    db: Session,
    soa_job_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Get SOA job with all table results.

    Args:
        db: SQLAlchemy session
        soa_job_id: UUID of the SOA job

    Returns:
        Dict with job and table_results, or None if not found
    """
    from app.db import SOAJob, SOATableResult

    job = db.query(SOAJob).filter(SOAJob.id == uuid.UUID(soa_job_id)).first()
    if not job:
        return None

    table_results = db.query(SOATableResult).filter(
        SOATableResult.soa_job_id == job.id
    ).order_by(SOATableResult.table_id).all()

    return {
        "job": {
            "id": str(job.id),
            "protocol_id": str(job.protocol_id),
            "protocol_name": job.protocol_name,
            "status": job.status,
            "current_phase": job.current_phase,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        },
        "table_results": [
            {
                "id": str(tr.id),
                "table_id": tr.table_id,
                "table_category": tr.table_category,
                "page_start": tr.page_start,
                "page_end": tr.page_end,
                "status": tr.status,
                "visits_count": tr.visits_count,
                "activities_count": tr.activities_count,
                "sais_count": tr.sais_count,
                "footnotes_count": tr.footnotes_count,
                "error_message": tr.error_message,
            }
            for tr in table_results
        ],
        "totals": {
            "tables": len(table_results),
            "successful": sum(1 for tr in table_results if tr.status == "success"),
            "visits": sum(tr.visits_count or 0 for tr in table_results),
            "activities": sum(tr.activities_count or 0 for tr in table_results),
            "sais": sum(tr.sais_count or 0 for tr in table_results),
            "footnotes": sum(tr.footnotes_count or 0 for tr in table_results),
        },
    }


def get_table_usdm(
    db: Session,
    soa_job_id: str,
    table_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Get USDM data for a specific table.

    Args:
        db: SQLAlchemy session
        soa_job_id: UUID of the SOA job
        table_id: Table identifier (SOA-1, SOA-2, etc.)

    Returns:
        USDM JSON for the table, or None if not found
    """
    from app.db import SOATableResult

    result = db.query(SOATableResult).filter(
        SOATableResult.soa_job_id == uuid.UUID(soa_job_id),
        SOATableResult.table_id == table_id,
    ).first()

    return result.usdm_data if result else None


def get_tables_by_category(
    db: Session,
    protocol_id: str,
    category: str,
) -> List[Dict[str, Any]]:
    """
    Get all table results for a protocol by category.

    Useful for getting all PK_SOA tables across jobs, for example.

    Args:
        db: SQLAlchemy session
        protocol_id: UUID of the protocol
        category: Table category (MAIN_SOA, PK_SOA, etc.)

    Returns:
        List of table results with metadata
    """
    from app.db import SOATableResult

    results = db.query(SOATableResult).filter(
        SOATableResult.protocol_id == uuid.UUID(protocol_id),
        SOATableResult.table_category == category,
    ).order_by(SOATableResult.created_at.desc()).all()

    return [
        {
            "id": str(tr.id),
            "soa_job_id": str(tr.soa_job_id),
            "table_id": tr.table_id,
            "table_category": tr.table_category,
            "status": tr.status,
            "visits_count": tr.visits_count,
            "activities_count": tr.activities_count,
            "sais_count": tr.sais_count,
            "created_at": tr.created_at.isoformat() if tr.created_at else None,
        }
        for tr in results
    ]


def update_table_usdm(
    db: Session,
    table_result_id: str,
    usdm_data: Dict[str, Any],
    update_counts: bool = True,
) -> bool:
    """
    Update USDM data for a specific table result.

    Useful for applying human edits or re-processing.

    Args:
        db: SQLAlchemy session
        table_result_id: UUID of the table result
        usdm_data: New USDM data
        update_counts: Whether to recalculate counts

    Returns:
        True if updated, False if not found
    """
    from app.db import SOATableResult

    result = db.query(SOATableResult).filter(
        SOATableResult.id == uuid.UUID(table_result_id)
    ).first()

    if not result:
        return False

    result.usdm_data = usdm_data
    result.updated_at = datetime.utcnow()

    if update_counts:
        result.visits_count = len(usdm_data.get("visits", []))
        result.activities_count = len(usdm_data.get("activities", []))
        result.sais_count = len(usdm_data.get("scheduledActivityInstances", []))
        result.footnotes_count = len(usdm_data.get("footnotes", []))

    db.commit()
    return True


# =============================================================================
# MERGE PLAN PERSISTENCE
# =============================================================================


def save_merge_plan(
    db: Session,
    soa_job_id: str,
    protocol_id: str,
    protocol_name: Optional[str],
    merge_plan: Any,  # MergePlan from table_merge_analyzer
) -> str:
    """
    Save a merge plan for human review.

    Args:
        db: SQLAlchemy session
        soa_job_id: UUID of the SOA job
        protocol_id: UUID of the protocol
        protocol_name: Human-readable protocol name
        merge_plan: MergePlan object from table_merge_analyzer

    Returns:
        merge_plan_id: UUID of created merge plan
    """
    from app.db import SOAMergePlan

    plan = SOAMergePlan(
        id=uuid.uuid4(),
        soa_job_id=uuid.UUID(soa_job_id) if isinstance(soa_job_id, str) else soa_job_id,
        protocol_id=uuid.UUID(protocol_id) if isinstance(protocol_id, str) else protocol_id,
        protocol_name=protocol_name,
        status="pending_confirmation",
        merge_plan=merge_plan.to_dict() if hasattr(merge_plan, 'to_dict') else merge_plan,
        total_tables_input=merge_plan.total_tables if hasattr(merge_plan, 'total_tables') else None,
        merge_groups_output=len(merge_plan.merge_groups) if hasattr(merge_plan, 'merge_groups') else None,
    )

    db.add(plan)
    db.commit()

    logger.info(f"Created SOAMergePlan: {plan.id}")
    return str(plan.id)


def get_merge_plan(
    db: Session,
    merge_plan_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Get a merge plan by ID.

    Args:
        db: SQLAlchemy session
        merge_plan_id: UUID of the merge plan

    Returns:
        Merge plan data or None if not found
    """
    from app.db import SOAMergePlan

    plan = db.query(SOAMergePlan).filter(
        SOAMergePlan.id == uuid.UUID(merge_plan_id)
    ).first()

    if not plan:
        return None

    return {
        "id": str(plan.id),
        "soa_job_id": str(plan.soa_job_id),
        "protocol_id": str(plan.protocol_id),
        "protocol_name": plan.protocol_name,
        "status": plan.status,
        "merge_plan": plan.merge_plan,
        "total_tables_input": plan.total_tables_input,
        "merge_groups_output": plan.merge_groups_output,
        "confirmed_at": plan.confirmed_at.isoformat() if plan.confirmed_at else None,
        "confirmed_by": plan.confirmed_by,
        "confirmed_plan": plan.confirmed_plan,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }


def get_merge_plan_by_job(
    db: Session,
    soa_job_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Get the merge plan for an SOA job.

    Args:
        db: SQLAlchemy session
        soa_job_id: UUID of the SOA job

    Returns:
        Merge plan data or None if not found
    """
    from app.db import SOAMergePlan

    plan = db.query(SOAMergePlan).filter(
        SOAMergePlan.soa_job_id == uuid.UUID(soa_job_id)
    ).order_by(SOAMergePlan.created_at.desc()).first()

    if not plan:
        return None

    return get_merge_plan(db, str(plan.id))


def confirm_merge_plan(
    db: Session,
    merge_plan_id: str,
    confirmed_plan: Dict[str, Any],
    confirmed_by: str = "user",
) -> bool:
    """
    Confirm a merge plan after human review.

    Args:
        db: SQLAlchemy session
        merge_plan_id: UUID of the merge plan
        confirmed_plan: The confirmed/modified plan
        confirmed_by: User who confirmed

    Returns:
        True if confirmed, False if not found
    """
    from app.db import SOAMergePlan

    plan = db.query(SOAMergePlan).filter(
        SOAMergePlan.id == uuid.UUID(merge_plan_id)
    ).first()

    if not plan:
        return False

    plan.status = "confirmed"
    plan.confirmed_plan = confirmed_plan
    plan.confirmed_by = confirmed_by
    plan.confirmed_at = datetime.utcnow()
    plan.updated_at = datetime.utcnow()

    db.commit()
    logger.info(f"Confirmed SOAMergePlan: {plan.id}")
    return True


def save_merge_group_result(
    db: Session,
    soa_job_id: str,
    merge_plan_id: str,
    protocol_id: str,
    protocol_name: Optional[str],
    merge_group_id: str,
    source_table_ids: List[str],
    merge_type: str,
    merged_usdm: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create a merge group result record.

    Args:
        db: SQLAlchemy session
        soa_job_id: UUID of the SOA job
        merge_plan_id: UUID of the merge plan
        protocol_id: UUID of the protocol
        protocol_name: Human-readable protocol name
        merge_group_id: Group ID (MG-001, etc.)
        source_table_ids: List of source table IDs
        merge_type: Type of merge (physical_continuation, etc.)
        merged_usdm: Combined USDM before interpretation

    Returns:
        group_result_id: UUID of created result
    """
    from app.db import SOAMergeGroupResult

    result = SOAMergeGroupResult(
        id=uuid.uuid4(),
        soa_job_id=uuid.UUID(soa_job_id) if isinstance(soa_job_id, str) else soa_job_id,
        merge_plan_id=uuid.UUID(merge_plan_id) if isinstance(merge_plan_id, str) else merge_plan_id,
        protocol_id=uuid.UUID(protocol_id) if isinstance(protocol_id, str) else protocol_id,
        protocol_name=protocol_name,
        merge_group_id=merge_group_id,
        source_table_ids=source_table_ids,
        merge_type=merge_type,
        status="pending",
        merged_usdm=merged_usdm,
    )

    db.add(result)
    db.commit()

    logger.info(f"Created SOAMergeGroupResult: {result.id} ({merge_group_id})")
    return str(result.id)


def update_merge_group_result(
    db: Session,
    group_result_id: str,
    status: str,
    interpretation_result: Optional[Dict[str, Any]] = None,
    final_usdm: Optional[Dict[str, Any]] = None,
    quality_score: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> bool:
    """
    Update a merge group result after interpretation.

    Args:
        db: SQLAlchemy session
        group_result_id: UUID of the group result
        status: New status (interpreting, completed, failed)
        interpretation_result: Full interpretation pipeline result
        final_usdm: Final USDM after interpretation
        quality_score: Quality metrics
        error_message: Error message if failed

    Returns:
        True if updated, False if not found
    """
    from app.db import SOAMergeGroupResult

    result = db.query(SOAMergeGroupResult).filter(
        SOAMergeGroupResult.id == uuid.UUID(group_result_id)
    ).first()

    if not result:
        return False

    result.status = status
    result.updated_at = datetime.utcnow()

    if status == "interpreting":
        result.started_at = datetime.utcnow()
    elif status in ["completed", "failed"]:
        result.completed_at = datetime.utcnow()

    if interpretation_result is not None:
        result.interpretation_result = interpretation_result

    if final_usdm is not None:
        result.final_usdm = final_usdm
        result.visits_count = len(final_usdm.get("visits", []))
        result.activities_count = len(final_usdm.get("activities", []))
        result.sais_count = len(final_usdm.get("scheduledActivityInstances", []))
        result.footnotes_count = len(final_usdm.get("footnotes", []))

    if quality_score is not None:
        result.quality_score = quality_score

    if error_message is not None:
        result.error_message = error_message

    db.commit()
    return True


def get_merge_group_results(
    db: Session,
    merge_plan_id: str,
) -> List[Dict[str, Any]]:
    """
    Get all merge group results for a merge plan.

    Args:
        db: SQLAlchemy session
        merge_plan_id: UUID of the merge plan

    Returns:
        List of merge group results
    """
    from app.db import SOAMergeGroupResult

    results = db.query(SOAMergeGroupResult).filter(
        SOAMergeGroupResult.merge_plan_id == uuid.UUID(merge_plan_id)
    ).order_by(SOAMergeGroupResult.merge_group_id).all()

    return [
        {
            "id": str(r.id),
            "merge_group_id": r.merge_group_id,
            "source_table_ids": r.source_table_ids,
            "merge_type": r.merge_type,
            "status": r.status,
            "error_message": r.error_message,
            "visits_count": r.visits_count,
            "activities_count": r.activities_count,
            "sais_count": r.sais_count,
            "footnotes_count": r.footnotes_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in results
    ]
