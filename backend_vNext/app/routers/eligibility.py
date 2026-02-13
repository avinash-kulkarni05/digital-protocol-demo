"""
Eligibility Analysis router for human-in-the-loop eligibility extraction.

Endpoints:
- POST /protocols/{protocol_id}/eligibility/start - Start eligibility section detection
- GET /eligibility/jobs/{job_id} - Get eligibility job status & detected sections
- POST /eligibility/jobs/{job_id}/confirm-sections - Confirm or correct detected sections
- GET /eligibility/jobs/{job_id}/results - Get final eligibility extraction results
- GET /protocols/{protocol_id}/eligibility/latest - Get latest eligibility job for protocol
"""

import asyncio
import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db, Protocol, EligibilityJob
from app.services.eligibility_worker import (
    spawn_section_detection_process,
    spawn_full_extraction_process,
    register_eligibility_process,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class EligibilityStartRequest(BaseModel):
    """Optional configuration for eligibility extraction."""
    skip_feasibility: bool = False  # Skip Stage 11 feasibility analysis
    use_cache: bool = True  # Use caching for expensive stages


class EligibilityStartResponse(BaseModel):
    """Response when starting eligibility extraction."""
    job_id: str
    protocol_id: str
    status: str
    message: str


class EligibilitySectionInfo(BaseModel):
    """Information about detected eligibility section."""
    id: str
    type: str  # inclusion or exclusion
    pageStart: int
    pageEnd: int
    pages: List[int]
    title: str
    confidence: float


class EligibilityJobStatusResponse(BaseModel):
    """Response for eligibility job status."""
    job_id: str
    protocol_id: str
    status: str
    current_phase: Optional[str] = None
    current_stage: Optional[int] = None
    phase_progress: Optional[Dict[str, Any]] = None
    detected_sections: Optional[Dict[str, Any]] = None
    confirmed_sections: Optional[Dict[str, Any]] = None
    counts: Optional[Dict[str, int]] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class ConfirmSectionsRequest(BaseModel):
    """Request to confirm or correct detected sections."""
    confirmed: bool = True  # Use detected sections as-is
    sections: Optional[List[Dict[str, Any]]] = None  # User-corrected sections (required if confirmed=False)
    skip_feasibility: bool = False  # Skip Stage 11 feasibility analysis
    use_cache: bool = False  # Disabled - always start fresh


class EligibilityResultsResponse(BaseModel):
    """Response with eligibility extraction results."""
    job_id: str
    status: str
    usdm_data: Optional[Dict[str, Any]] = None
    quality_report: Optional[Dict[str, Any]] = None
    interpretation_result: Optional[Dict[str, Any]] = None
    feasibility_result: Optional[Dict[str, Any]] = None
    qeb_result: Optional[Dict[str, Any]] = None
    counts: Optional[Dict[str, int]] = None


# =============================================================================
# Helper Functions
# =============================================================================

def get_pdf_path_for_protocol(protocol: Protocol, db: Session) -> str:
    """
    Get or create a temporary file path for the protocol PDF.

    If the protocol has file_data (stored in DB), write it to a temp file.
    Otherwise, use the file_path if available.
    """
    if protocol.file_data:
        # Write binary data to temp file
        temp_dir = Path(tempfile.gettempdir()) / "eligibility_extraction"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{protocol.id}_{protocol.filename}"

        if not temp_path.exists():
            with open(temp_path, 'wb') as f:
                f.write(protocol.file_data)
            logger.info(f"Created temp PDF file: {temp_path}")

        return str(temp_path)
    elif protocol.file_path:
        return protocol.file_path
    else:
        raise ValueError(f"Protocol {protocol.id} has no PDF data or file path")


def get_protocol_by_study_id(study_id: str, db: Session) -> Optional[Protocol]:
    """
    Find a protocol by study_id (filename without .pdf extension).
    """
    # First try exact match on filename
    protocol = db.query(Protocol).filter(
        Protocol.filename == f"{study_id}.pdf"
    ).first()

    if protocol:
        return protocol

    # Try to find by partial match
    protocol = db.query(Protocol).filter(
        Protocol.filename.ilike(f"%{study_id}%")
    ).first()

    return protocol


def _merge_interpretation_into_criteria(
    raw_criteria: List[Dict[str, Any]],
    interpretation_result: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Merge interpretation stage results into the raw criteria.

    Fallback helper function for the API endpoint when usdm_data is not populated.
    Mirrors the logic in eligibility_extraction_pipeline.py.
    """
    if not interpretation_result or not raw_criteria:
        return raw_criteria or []

    merged = []

    # Get stage results
    stage_results = interpretation_result.get("stage_results", {})
    stage2_result = stage_results.get("2", {}) or stage_results.get(2, {})
    stage5_result = stage_results.get("5", {}) or stage_results.get(5, {})
    stage6_result = stage_results.get("6", {}) or stage_results.get(6, {})
    stage8_result = stage_results.get("8", {}) or stage_results.get(8, {})

    # Build lookup maps using composite keys (criterionId, type)
    decomposed_map = {}
    if stage2_result and isinstance(stage2_result, dict):
        for dc in stage2_result.get("decomposedCriteria", []):
            crit_id = dc.get("criterionId")
            if crit_id:
                key = (crit_id, dc.get("type", "Inclusion"))
                decomposed_map[key] = dc

    omop_map = {}
    if stage5_result and isinstance(stage5_result, dict):
        for mapping in stage5_result.get("mappings", []):
            key = (
                mapping.get("criterionId"),
                mapping.get("type", "Inclusion"),
                mapping.get("atomicId")
            )
            if key not in omop_map:
                omop_map[key] = []
            omop_map[key].append(mapping)

    sql_map = {}
    if stage6_result and isinstance(stage6_result, dict):
        for template in stage6_result.get("templates", []):
            key = (template.get("criterionId"), template.get("type", "Inclusion"))
            sql_map[key] = template

    tier_map = {"tier1": [], "tier2": [], "tier3": []}
    if stage8_result and isinstance(stage8_result, dict):
        tier_map = stage8_result

    # Merge each criterion
    for criterion in raw_criteria:
        criterion_id = criterion.get("criterionId")
        criterion_type = criterion.get("type", "Inclusion")
        composite_key = (criterion_id, criterion_type)
        merged_criterion = criterion.copy()

        # Merge Stage 2: Atomic decomposition
        if composite_key in decomposed_map:
            dc = decomposed_map[composite_key]
            merged_criterion["atomicCriteria"] = dc.get("atomicCriteria", [])
            merged_criterion["options"] = dc.get("options", [])
            merged_criterion["logicOperator"] = dc.get("logicOperator")

            # Merge OMOP concepts into atomic criteria
            for ac in merged_criterion.get("atomicCriteria", []):
                atomic_id = ac.get("atomicId")
                omop_key = (criterion_id, criterion_type, atomic_id)
                if omop_key in omop_map:
                    ac["omopConcepts"] = omop_map[omop_key]

        # Merge Stage 6: SQL templates
        if composite_key in sql_map:
            merged_criterion["sqlTemplate"] = sql_map[composite_key]

        # Determine tier assignment
        tier_assignment = None
        for tier_name in ["tier1", "tier2", "tier3"]:
            tier_criteria = tier_map.get(tier_name, [])
            for tc in tier_criteria:
                if tc.get("criterionId") == criterion_id and tc.get("type", "Inclusion") == criterion_type:
                    tier_assignment = tier_name
                    break
            if tier_assignment:
                break
        if tier_assignment:
            merged_criterion["tier"] = tier_assignment

        merged.append(merged_criterion)

    return merged


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/protocols/{protocol_id}/eligibility/start", response_model=EligibilityStartResponse)
async def start_eligibility_extraction(
    protocol_id: str,
    request: Optional[EligibilityStartRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Start eligibility section detection for a protocol.

    This initiates Stage 1 of the human-in-the-loop pipeline.
    After section detection completes, the job status will be 'awaiting_section_confirmation'.

    The protocol_id can be either:
    - A UUID (protocol.id)
    - A study_id (filename without .pdf extension)
    """
    # Try to find protocol by UUID or study_id
    protocol = None
    try:
        protocol_uuid = UUID(protocol_id)
        protocol = db.query(Protocol).filter(Protocol.id == protocol_uuid).first()
    except ValueError:
        # Not a UUID, try as study_id
        protocol = get_protocol_by_study_id(protocol_id, db)

    if not protocol:
        raise HTTPException(status_code=404, detail=f"Protocol not found: {protocol_id}")

    # Check for completed job - only return if fully completed
    completed_job = db.query(EligibilityJob).filter(
        EligibilityJob.protocol_id == protocol.id,
        EligibilityJob.status == "completed"
    ).order_by(EligibilityJob.completed_at.desc()).first()

    if completed_job:
        # Return completed job
        return EligibilityStartResponse(
            job_id=str(completed_job.id),
            protocol_id=str(protocol.id),
            status="completed",
            message="Eligibility extraction already completed. Use the results endpoint to get data."
        )

    # Check for failed job with detected sections - allow retry from section confirmation
    failed_job = db.query(EligibilityJob).filter(
        EligibilityJob.protocol_id == protocol.id,
        EligibilityJob.status == "failed"
    ).order_by(EligibilityJob.updated_at.desc()).first()

    if failed_job and failed_job.detected_sections:
        # Reset to section confirmation stage instead of restarting completely
        failed_job.status = "awaiting_section_confirmation"
        failed_job.error_message = None
        failed_job.updated_at = datetime.utcnow()
        db.commit()
        logger.info(f"Reset failed eligibility job {failed_job.id} to awaiting_section_confirmation for retry")
        return EligibilityStartResponse(
            job_id=str(failed_job.id),
            protocol_id=str(protocol.id),
            status="awaiting_section_confirmation",
            message="Previous extraction failed. Please re-confirm sections to retry."
        )

    # Cancel any existing incomplete jobs
    incomplete_jobs = db.query(EligibilityJob).filter(
        EligibilityJob.protocol_id == protocol.id,
        EligibilityJob.status.notin_(["completed", "failed", "cancelled"])
    ).all()

    for job in incomplete_jobs:
        job.status = "cancelled"
        job.error_message = "Cancelled - new extraction started"
        job.updated_at = datetime.utcnow()
        logger.info(f"Cancelled incomplete eligibility job {job.id}")

    if incomplete_jobs:
        db.commit()
        logger.info(f"Cancelled {len(incomplete_jobs)} incomplete eligibility job(s) for protocol {protocol.id}")

    # Create new eligibility job
    eligibility_job = EligibilityJob(
        protocol_id=protocol.id,
        protocol_name=protocol.protocol_name or protocol.filename.replace('.pdf', ''),
        status="detecting_sections",
    )
    db.add(eligibility_job)
    db.commit()
    db.refresh(eligibility_job)

    logger.info(f"Created eligibility job {eligibility_job.id} for protocol {protocol.id}")

    # Get PDF path
    try:
        pdf_path = get_pdf_path_for_protocol(protocol, db)
    except ValueError as e:
        eligibility_job.status = "failed"
        eligibility_job.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))

    # Spawn section detection process
    process = spawn_section_detection_process(
        job_id=eligibility_job.id,
        protocol_id=protocol.id,
        pdf_path=pdf_path,
    )
    register_eligibility_process(str(eligibility_job.id), process)

    return EligibilityStartResponse(
        job_id=str(eligibility_job.id),
        protocol_id=str(protocol.id),
        status="detecting_sections",
        message="Eligibility section detection started"
    )


@router.get("/eligibility/jobs/{job_id}", response_model=EligibilityJobStatusResponse)
async def get_eligibility_job_status(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    Get current status of an eligibility extraction job.

    When status is 'awaiting_section_confirmation', the response includes
    detected_sections which the frontend should display for user verification.
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    job = db.query(EligibilityJob).filter(EligibilityJob.id == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Eligibility job not found: {job_id}")

    counts = None
    if job.inclusion_count is not None or job.exclusion_count is not None:
        counts = {
            "inclusion": job.inclusion_count or 0,
            "exclusion": job.exclusion_count or 0,
            "atomic": job.atomic_count or 0,
            "total": (job.inclusion_count or 0) + (job.exclusion_count or 0),
        }

    return EligibilityJobStatusResponse(
        job_id=str(job.id),
        protocol_id=str(job.protocol_id),
        status=job.status,
        current_phase=job.current_phase,
        current_stage=(job.phase_progress or {}).get("stage"),  # Get from phase_progress JSONB
        phase_progress=job.phase_progress,
        detected_sections=job.detected_sections,
        confirmed_sections=job.confirmed_sections,
        counts=counts,
        error_message=job.error_message,
        created_at=job.created_at.isoformat() if job.created_at else "",
        updated_at=job.updated_at.isoformat() if job.updated_at else "",
    )


@router.post("/eligibility/jobs/{job_id}/confirm-sections")
async def confirm_eligibility_sections(
    job_id: str,
    request: ConfirmSectionsRequest,
    db: Session = Depends(get_db),
):
    """
    Confirm or correct detected eligibility sections.

    If confirmed=True, uses the detected sections.
    If confirmed=False, uses the sections provided in the request.

    This triggers Stage 2 of the pipeline (full extraction).
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    job = db.query(EligibilityJob).filter(EligibilityJob.id == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Eligibility job not found: {job_id}")

    if job.status != "awaiting_section_confirmation":
        raise HTTPException(
            status_code=400,
            detail=f"Job is not awaiting section confirmation (current status: {job.status})"
        )

    # Get protocol
    protocol = db.query(Protocol).filter(Protocol.id == job.protocol_id).first()
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")

    # Determine which sections to use
    if request.confirmed:
        # Use detected sections
        confirmed_sections = job.detected_sections
        logger.info(f"User confirmed detected sections for job {job_id}")
    else:
        # Use corrected sections
        if not request.sections:
            raise HTTPException(
                status_code=400,
                detail="sections field is required when confirmed=False"
            )
        confirmed_sections = {
            "sections": request.sections,
            "user_corrected": True,
        }
        logger.info(f"User provided corrected sections for job {job_id}: {request.sections}")

    # Update job status
    job.status = "extracting"
    job.confirmed_sections = confirmed_sections
    db.commit()

    # Get PDF path
    try:
        pdf_path = get_pdf_path_for_protocol(protocol, db)
    except ValueError as e:
        job.status = "failed"
        job.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))

    # Spawn full extraction process
    process = spawn_full_extraction_process(
        job_id=job.id,
        protocol_id=protocol.id,
        pdf_path=pdf_path,
        confirmed_sections=confirmed_sections,
        skip_feasibility=request.skip_feasibility,
        use_cache=request.use_cache,
    )
    register_eligibility_process(str(job.id), process)

    return {
        "job_id": str(job.id),
        "status": "extracting",
        "message": "Full eligibility extraction started"
    }


@router.get("/eligibility/jobs/{job_id}/results", response_model=EligibilityResultsResponse)
async def get_eligibility_results(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    Get final eligibility extraction results.

    Only available when job status is 'completed'.
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    job = db.query(EligibilityJob).filter(EligibilityJob.id == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Eligibility job not found: {job_id}")

    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Results not available (job status: {job.status})"
        )

    counts = {
        "inclusion": job.inclusion_count or 0,
        "exclusion": job.exclusion_count or 0,
        "atomic": job.atomic_count or 0,
        "total": (job.inclusion_count or 0) + (job.exclusion_count or 0),
    }

    # Fallback: construct usdm_data from raw_criteria if not populated
    # This handles jobs completed before the usdm_data fix was applied
    usdm_data = job.usdm_data
    if not usdm_data and job.raw_criteria:
        logger.info(f"Constructing usdm_data fallback from raw_criteria for job {job_id}")
        # Merge interpretation results into raw_criteria for the fallback
        merged_criteria = _merge_interpretation_into_criteria(
            job.raw_criteria,
            job.interpretation_result
        )
        usdm_data = {"criteria": merged_criteria}

    return EligibilityResultsResponse(
        job_id=str(job.id),
        status=job.status,
        usdm_data=usdm_data,
        quality_report=job.quality_report,
        interpretation_result=job.interpretation_result,
        feasibility_result=job.feasibility_result,
        qeb_result=job.qeb_result,
        counts=counts,
    )


@router.get("/protocols/{protocol_id}/eligibility/latest")
async def get_latest_eligibility_job(
    protocol_id: str,
    db: Session = Depends(get_db),
):
    """
    Get the latest eligibility job for a protocol.

    Useful for checking if extraction has already been done.
    """
    # Try to find protocol by UUID or study_id
    protocol = None
    try:
        protocol_uuid = UUID(protocol_id)
        protocol = db.query(Protocol).filter(Protocol.id == protocol_uuid).first()
    except ValueError:
        protocol = get_protocol_by_study_id(protocol_id, db)

    if not protocol:
        raise HTTPException(status_code=404, detail=f"Protocol not found: {protocol_id}")

    # Get latest job
    job = db.query(EligibilityJob).filter(
        EligibilityJob.protocol_id == protocol.id
    ).order_by(EligibilityJob.created_at.desc()).first()

    if not job:
        return {
            "protocol_id": str(protocol.id),
            "has_job": False,
            "message": "No eligibility extraction job found for this protocol"
        }

    counts = None
    if job.inclusion_count is not None or job.exclusion_count is not None:
        counts = {
            "inclusion": job.inclusion_count or 0,
            "exclusion": job.exclusion_count or 0,
            "atomic": job.atomic_count or 0,
            "total": (job.inclusion_count or 0) + (job.exclusion_count or 0),
        }

    return {
        "protocol_id": str(protocol.id),
        "has_job": True,
        "job_id": str(job.id),
        "status": job.status,
        "current_phase": job.current_phase,
        "counts": counts,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/eligibility/jobs/{job_id}/events")
async def get_eligibility_events(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    SSE stream for real-time eligibility extraction progress.

    Events are sent when:
    - Phase changes (detection → awaiting_confirmation → extraction → interpretation → etc.)
    - Progress updates within a phase
    - Job completes or fails
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    job = db.query(EligibilityJob).filter(EligibilityJob.id == job_uuid).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Eligibility job not found: {job_id}")

    async def event_generator():
        """Generate SSE events for eligibility job progress."""
        last_status = None
        last_phase = None
        last_stage = None

        while True:
            # Get fresh job state
            from app.db import get_session_factory
            SessionLocal = get_session_factory()
            fresh_db = SessionLocal()
            try:
                fresh_job = fresh_db.query(EligibilityJob).filter(
                    EligibilityJob.id == job_uuid
                ).first()

                if not fresh_job:
                    yield f"event: error\ndata: {json.dumps({'message': 'Job not found'})}\n\n"
                    break

                # Check for changes (get current_stage from phase_progress JSONB)
                current_stage_value = (fresh_job.phase_progress or {}).get("stage")
                if (fresh_job.status != last_status or
                    fresh_job.current_phase != last_phase or
                    current_stage_value != last_stage):

                    event_data = {
                        "status": fresh_job.status,
                        "current_phase": fresh_job.current_phase,
                        "current_stage": current_stage_value,
                        "phase_progress": fresh_job.phase_progress,
                        "detected_sections": fresh_job.detected_sections if fresh_job.status == "awaiting_section_confirmation" else None,
                    }

                    yield f"event: progress\ndata: {json.dumps(event_data)}\n\n"

                    last_status = fresh_job.status
                    last_phase = fresh_job.current_phase
                    last_stage = current_stage_value

                # Check if job is terminal
                if fresh_job.status in ("completed", "failed", "cancelled"):
                    final_data = {
                        "status": fresh_job.status,
                        "error_message": fresh_job.error_message,
                    }
                    if fresh_job.status == "completed":
                        final_data["counts"] = {
                            "inclusion": fresh_job.inclusion_count or 0,
                            "exclusion": fresh_job.exclusion_count or 0,
                            "atomic": fresh_job.atomic_count or 0,
                        }
                    yield f"event: complete\ndata: {json.dumps(final_data)}\n\n"
                    break

            finally:
                fresh_db.close()

            await asyncio.sleep(2)  # Poll every 2 seconds

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
