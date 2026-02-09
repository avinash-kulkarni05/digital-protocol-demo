"""
SOA Analysis router for human-in-the-loop SOA extraction.

Endpoints:
- POST /protocols/{protocol_id}/soa/start - Start SOA page detection
- GET /soa/jobs/{job_id}/status - Get SOA job status & detected pages
- POST /soa/jobs/{job_id}/confirm-pages - Confirm or correct detected pages
- GET /soa/jobs/{job_id}/results - Get final SOA extraction results
- GET /soa/jobs/{job_id}/events - SSE stream for progress updates
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
from sqlalchemy.orm.attributes import flag_modified

from app.db import get_db, Protocol, SOAJob, SOAEditAudit, SOATableResult
from app.services.soa_worker import (
    spawn_page_detection_process,
    spawn_full_extraction_process,
    register_soa_process,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class SOAStartResponse(BaseModel):
    """Response when starting SOA extraction."""
    job_id: str
    protocol_id: str
    status: str
    message: str


class SOAPageInfo(BaseModel):
    """Information about detected SOA pages."""
    id: str
    pageStart: int
    pageEnd: int
    category: str
    pages: List[int]


class SOAJobStatusResponse(BaseModel):
    """Response for SOA job status."""
    job_id: str
    protocol_id: str
    status: str
    current_phase: Optional[str] = None
    phase_progress: Optional[Dict[str, Any]] = None
    detected_pages: Optional[Dict[str, Any]] = None
    merge_plan: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class ConfirmPagesRequest(BaseModel):
    """Request to confirm or correct detected pages."""
    confirmed: bool
    pages: Optional[List[Dict[str, Any]]] = None  # Required if confirmed=False


class SOAResultsResponse(BaseModel):
    """Response with SOA extraction results."""
    job_id: str
    status: str
    usdm_data: Optional[Dict[str, Any]] = None
    quality_report: Optional[Dict[str, Any]] = None
    extraction_review: Optional[Dict[str, Any]] = None
    interpretation_review: Optional[Dict[str, Any]] = None


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
        temp_dir = Path(tempfile.gettempdir()) / "soa_extraction"
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


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/protocols/{protocol_id}/soa/start", response_model=SOAStartResponse)
async def start_soa_extraction(
    protocol_id: str,
    db: Session = Depends(get_db),
):
    """
    Start SOA page detection for a protocol.

    This initiates Stage 1 of the human-in-the-loop pipeline.
    After page detection completes, the job status will be 'awaiting_page_confirmation'.

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
    completed_job = db.query(SOAJob).filter(
        SOAJob.protocol_id == protocol.id,
        SOAJob.status == "completed"
    ).order_by(SOAJob.completed_at.desc()).first()

    if completed_job:
        # Return completed job
        return SOAStartResponse(
            job_id=str(completed_job.id),
            protocol_id=str(protocol.id),
            status="completed",
            message="SOA extraction already completed. Use the results endpoint to get data."
        )

    # Check for job awaiting user confirmation (page or merge)
    # These should NOT be cancelled - user needs to confirm
    awaiting_job = db.query(SOAJob).filter(
        SOAJob.protocol_id == protocol.id,
        SOAJob.status.in_(["awaiting_page_confirmation", "awaiting_merge_confirmation"])
    ).order_by(SOAJob.created_at.desc()).first()

    if awaiting_job:
        # Return the job that's awaiting confirmation
        return SOAStartResponse(
            job_id=str(awaiting_job.id),
            protocol_id=str(protocol.id),
            status=awaiting_job.status,
            message=f"SOA job awaiting confirmation. Status: {awaiting_job.status}"
        )

    # Cancel any existing incomplete jobs (not completed/failed/cancelled/awaiting confirmation)
    # This ensures we always start fresh if previous extraction was interrupted
    incomplete_jobs = db.query(SOAJob).filter(
        SOAJob.protocol_id == protocol.id,
        SOAJob.status.notin_(["completed", "failed", "cancelled", "awaiting_page_confirmation", "awaiting_merge_confirmation"])
    ).all()

    for job in incomplete_jobs:
        job.status = "cancelled"
        job.error_message = "Cancelled - new extraction started"
        job.updated_at = datetime.utcnow()
        logger.info(f"Cancelled incomplete SOA job {job.id}")

    if incomplete_jobs:
        db.commit()
        logger.info(f"Cancelled {len(incomplete_jobs)} incomplete SOA job(s) for protocol {protocol.id}")

    # Create new SOA job with protocol_name from protocol
    soa_job = SOAJob(
        protocol_id=protocol.id,
        protocol_name=protocol.protocol_name,
        status="detecting_pages",
    )
    db.add(soa_job)
    db.commit()
    db.refresh(soa_job)

    logger.info(f"Created SOA job {soa_job.id} for protocol {protocol.id}")

    # Get PDF path
    try:
        pdf_path = get_pdf_path_for_protocol(protocol, db)
    except ValueError as e:
        soa_job.status = "failed"
        soa_job.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))

    # Spawn page detection process
    process = spawn_page_detection_process(
        soa_job_id=soa_job.id,
        protocol_id=protocol.id,
        pdf_path=pdf_path,
    )
    register_soa_process(str(soa_job.id), process)

    return SOAStartResponse(
        job_id=str(soa_job.id),
        protocol_id=str(protocol.id),
        status="detecting_pages",
        message="SOA page detection started"
    )


@router.get("/soa/jobs/{job_id}/status", response_model=SOAJobStatusResponse)
async def get_soa_job_status(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    Get current status of an SOA extraction job.

    When status is 'awaiting_page_confirmation', the response includes
    detected_pages which the frontend should display for user verification.

    When status is 'awaiting_merge_confirmation', the response includes
    merge_plan which the frontend should display for user review.
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    soa_job = db.query(SOAJob).filter(SOAJob.id == job_uuid).first()
    if not soa_job:
        raise HTTPException(status_code=404, detail=f"SOA job not found: {job_id}")

    # Get merge plan from soa_job.merge_analysis if status is awaiting_merge_confirmation
    merge_plan_data = None
    if soa_job.status == "awaiting_merge_confirmation" and soa_job.merge_analysis:
        merge_plan_data = soa_job.merge_analysis

    return SOAJobStatusResponse(
        job_id=str(soa_job.id),
        protocol_id=str(soa_job.protocol_id),
        status=soa_job.status,
        current_phase=soa_job.current_phase,
        phase_progress=soa_job.phase_progress,
        detected_pages=soa_job.detected_pages,
        merge_plan=merge_plan_data,
        error_message=soa_job.error_message,
        created_at=soa_job.created_at.isoformat() if soa_job.created_at else "",
        updated_at=soa_job.updated_at.isoformat() if soa_job.updated_at else "",
    )


@router.post("/soa/jobs/{job_id}/confirm-pages")
async def confirm_soa_pages(
    job_id: str,
    request: ConfirmPagesRequest,
    db: Session = Depends(get_db),
):
    """
    Confirm or correct detected SOA pages.

    If confirmed=True, uses the detected pages.
    If confirmed=False, uses the pages provided in the request.

    This triggers Stage 2 of the pipeline (full extraction).
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    soa_job = db.query(SOAJob).filter(SOAJob.id == job_uuid).first()
    if not soa_job:
        raise HTTPException(status_code=404, detail=f"SOA job not found: {job_id}")

    if soa_job.status != "awaiting_page_confirmation":
        raise HTTPException(
            status_code=400,
            detail=f"Job is not awaiting page confirmation (current status: {soa_job.status})"
        )

    # Get protocol
    protocol = db.query(Protocol).filter(Protocol.id == soa_job.protocol_id).first()
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")

    # Determine which pages to use
    if request.confirmed:
        # Use detected pages
        confirmed_pages = soa_job.detected_pages
        logger.info(f"User confirmed detected pages for job {job_id}")
    else:
        # Use corrected pages
        if not request.pages:
            raise HTTPException(
                status_code=400,
                detail="pages field is required when confirmed=False"
            )
        confirmed_pages = {
            "tables": request.pages,
            "user_corrected": True,
        }
        logger.info(f"User provided corrected pages for job {job_id}: {request.pages}")

    # Update job status
    soa_job.status = "extracting"
    soa_job.confirmed_pages = confirmed_pages
    db.commit()

    # Get PDF path
    try:
        pdf_path = get_pdf_path_for_protocol(protocol, db)
    except ValueError as e:
        soa_job.status = "failed"
        soa_job.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))

    # Spawn full extraction process
    process = spawn_full_extraction_process(
        soa_job_id=soa_job.id,
        protocol_id=protocol.id,
        pdf_path=pdf_path,
        confirmed_pages=confirmed_pages,
    )
    register_soa_process(str(soa_job.id), process)

    return {
        "job_id": str(soa_job.id),
        "status": "extracting",
        "message": "Full SOA extraction started"
    }


@router.get("/soa/jobs/{job_id}/results", response_model=SOAResultsResponse)
async def get_soa_results(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    Get final SOA extraction results.

    Only available when job status is 'completed'.
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    soa_job = db.query(SOAJob).filter(SOAJob.id == job_uuid).first()
    if not soa_job:
        raise HTTPException(status_code=404, detail=f"SOA job not found: {job_id}")

    if soa_job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Results not available (job status: {soa_job.status})"
        )

    return SOAResultsResponse(
        job_id=str(soa_job.id),
        status=soa_job.status,
        usdm_data=soa_job.usdm_data,
        quality_report=soa_job.quality_report,
        extraction_review=soa_job.extraction_review,
        interpretation_review=soa_job.interpretation_review,
    )


class SOATableResultResponse(BaseModel):
    """Response for a single table result."""
    id: str
    table_id: str
    table_category: str
    page_start: int
    page_end: int
    status: str
    error_message: Optional[str] = None
    visits_count: int
    activities_count: int
    sais_count: int
    footnotes_count: int
    usdm_data: Optional[Dict[str, Any]] = None


class SOAPerTableResultsResponse(BaseModel):
    """Response with per-table SOA extraction results."""
    job_id: str
    status: str
    total_tables: int
    successful_tables: int
    tables: List[SOATableResultResponse]


@router.get("/soa/jobs/{job_id}/tables", response_model=SOAPerTableResultsResponse)
async def get_soa_per_table_results(
    job_id: str,
    include_usdm: bool = Query(default=True, description="Include full USDM data for each table"),
    db: Session = Depends(get_db),
):
    """
    Get per-table SOA extraction results.

    Returns individual table results with their USDM data for granular review.
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    soa_job = db.query(SOAJob).filter(SOAJob.id == job_uuid).first()
    if not soa_job:
        raise HTTPException(status_code=404, detail=f"SOA job not found: {job_id}")

    if soa_job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Results not available (job status: {soa_job.status})"
        )

    # Get per-table results
    table_results = db.query(SOATableResult).filter(
        SOATableResult.soa_job_id == job_uuid
    ).order_by(SOATableResult.table_id).all()

    tables = []
    for tr in table_results:
        table_response = SOATableResultResponse(
            id=str(tr.id),
            table_id=tr.table_id,
            table_category=tr.table_category,
            page_start=tr.page_start or 0,
            page_end=tr.page_end or 0,
            status=tr.status,
            error_message=tr.error_message,
            visits_count=tr.visits_count or 0,
            activities_count=tr.activities_count or 0,
            sais_count=tr.sais_count or 0,
            footnotes_count=tr.footnotes_count or 0,
            usdm_data=tr.usdm_data if include_usdm else None,
        )
        tables.append(table_response)

    return SOAPerTableResultsResponse(
        job_id=str(soa_job.id),
        status=soa_job.status,
        total_tables=len(table_results),
        successful_tables=sum(1 for tr in table_results if tr.status == "success"),
        tables=tables,
    )


@router.get("/soa/jobs/{job_id}/tables/{table_id}")
async def get_soa_table_usdm(
    job_id: str,
    table_id: str,
    db: Session = Depends(get_db),
):
    """
    Get USDM data for a specific table.

    Useful for viewing a single table's extraction results.
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    table_result = db.query(SOATableResult).filter(
        SOATableResult.soa_job_id == job_uuid,
        SOATableResult.table_id == table_id,
    ).first()

    if not table_result:
        raise HTTPException(
            status_code=404,
            detail=f"Table result not found: {table_id} in job {job_id}"
        )

    return {
        "id": str(table_result.id),
        "table_id": table_result.table_id,
        "table_category": table_result.table_category,
        "page_start": table_result.page_start,
        "page_end": table_result.page_end,
        "status": table_result.status,
        "error_message": table_result.error_message,
        "counts": {
            "visits": table_result.visits_count or 0,
            "activities": table_result.activities_count or 0,
            "sais": table_result.sais_count or 0,
            "footnotes": table_result.footnotes_count or 0,
        },
        "usdm_data": table_result.usdm_data,
    }


class SOAFieldUpdateRequest(BaseModel):
    """Request to update a specific SOA field."""
    path: str  # Dot-notation path e.g., "visits.0.name" or "activities.1.category"
    value: Any  # New value for the field
    updated_by: Optional[str] = None  # User who made the change


class SOAFieldUpdateResponse(BaseModel):
    """Response after updating SOA field."""
    success: bool
    job_id: str
    path: str
    old_value: Any
    new_value: Any
    message: str


def set_nested_value(data: Dict, path: str, value: Any) -> Any:
    """
    Set a value in a nested dictionary using dot notation path.
    Returns the old value.

    Example: set_nested_value(data, "visits.0.name", "New Name")
    """
    keys = path.split(".")
    old_value = None

    # Navigate to parent
    current = data
    for key in keys[:-1]:
        if key.isdigit():
            key = int(key)
        if isinstance(current, list):
            current = current[key]
        else:
            current = current[key]

    # Get old value and set new value
    final_key = keys[-1]
    if final_key.isdigit():
        final_key = int(final_key)

    if isinstance(current, list):
        old_value = current[final_key] if final_key < len(current) else None
        current[final_key] = value
    else:
        old_value = current.get(final_key) if isinstance(current, dict) else None
        current[final_key] = value

    return old_value


def get_nested_value(data: Dict, path: str) -> Any:
    """
    Get a value from a nested dictionary using dot notation path.
    """
    keys = path.split(".")
    current = data

    for key in keys:
        if key.isdigit():
            key = int(key)
        if isinstance(current, list):
            current = current[key]
        elif isinstance(current, dict):
            current = current.get(key)
        else:
            return None

    return current


@router.patch("/soa/jobs/{job_id}/field", response_model=SOAFieldUpdateResponse)
async def update_soa_field(
    job_id: str,
    request: SOAFieldUpdateRequest,
    db: Session = Depends(get_db),
):
    """
    Update a specific field in SOA data.

    Updates the field in both usdm_data and extraction_review columns.

    Path examples:
    - "visits.0.name" - Update first visit's name
    - "activities.2.category" - Update third activity's category
    - "scheduledActivityInstances.5.visitId" - Update SAI's visitId
    - "footnotes.1.text" - Update footnote text
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    soa_job = db.query(SOAJob).filter(SOAJob.id == job_uuid).first()
    if not soa_job:
        raise HTTPException(status_code=404, detail=f"SOA job not found: {job_id}")

    if soa_job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit SOA data (job status: {soa_job.status}). Only completed jobs can be edited."
        )

    path = request.path
    value = request.value
    old_value = None

    # Transform path from frontend format (tables.0.X) to usdm_data format (X)
    # Frontend sends: tables.0.visits.1.timing.value
    # usdm_data expects: visits.1.timing.value
    def transform_path_for_usdm(frontend_path: str) -> str:
        """Strip 'tables.N.' prefix if present, since usdm_data doesn't have tables wrapper."""
        import re
        match = re.match(r'^tables\.\d+\.(.+)$', frontend_path)
        if match:
            return match.group(1)
        return frontend_path

    # Transform path for extraction_review nested structure
    # Frontend sends: tables.0.visits.0.timing.value
    # extraction_review expects: tables.0.visits.items.0.timing.value
    def transform_path_for_extraction_review(frontend_path: str) -> str:
        """Add 'items' after visits/activities/footnotes since they have {items: []} structure."""
        import re
        # Pattern: tables.N.{visits|activities|footnotes}.M.rest
        # Transform to: tables.N.{visits|activities|footnotes}.items.M.rest
        pattern = r'^(tables\.\d+\.(visits|activities|footnotes))\.(\d+)(.*)$'
        match = re.match(pattern, frontend_path)
        if match:
            prefix = match.group(1)  # tables.0.visits
            idx = match.group(3)     # 0
            rest = match.group(4)    # .timing.value
            return f"{prefix}.items.{idx}{rest}"
        return frontend_path

    try:
        # Prioritize extraction_review as primary data source
        if soa_job.extraction_review:
            # Update extraction_review first (primary source)
            extraction_review = dict(soa_job.extraction_review)  # Make a copy
            extraction_path = transform_path_for_extraction_review(path)
            try:
                old_value = get_nested_value(extraction_review, extraction_path)
                set_nested_value(extraction_review, extraction_path, value)
                soa_job.extraction_review = extraction_review
                flag_modified(soa_job, "extraction_review")  # Tell SQLAlchemy the JSONB was modified
                logger.info(f"Updated extraction_review.{extraction_path} from {old_value} to {value}")
            except (KeyError, IndexError, TypeError) as e:
                logger.warning(f"Path {extraction_path} not found in extraction_review: {e}")
        elif soa_job.usdm_data:
            # Fallback to usdm_data if extraction_review doesn't exist
            usdm_data = dict(soa_job.usdm_data)  # Make a copy
            usdm_path = transform_path_for_usdm(path)
            try:
                old_value = get_nested_value(usdm_data, usdm_path)
                set_nested_value(usdm_data, usdm_path, value)
                soa_job.usdm_data = usdm_data
                flag_modified(soa_job, "usdm_data")  # Tell SQLAlchemy the JSONB was modified
                logger.info(f"Updated usdm_data.{usdm_path} from {old_value} to {value}")
            except (KeyError, IndexError, TypeError) as e:
                logger.warning(f"Path {usdm_path} not found in usdm_data: {e}")

        # Create audit log entry
        audit_entry = SOAEditAudit(
            soa_job_id=soa_job.id,
            protocol_id=soa_job.protocol_id,
            protocol_name=soa_job.protocol_name,
            field_path=path,
            original_value=old_value,
            new_value=value,
            edit_type='update',
            updated_by=request.updated_by or 'user',
            updated_at=datetime.utcnow()
        )
        db.add(audit_entry)

        # Update timestamp
        soa_job.updated_at = datetime.utcnow()

        # Commit changes
        db.commit()
        db.refresh(soa_job)

        return SOAFieldUpdateResponse(
            success=True,
            job_id=str(soa_job.id),
            path=path,
            old_value=old_value,
            new_value=value,
            message=f"Successfully updated {path}"
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update SOA field: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update field: {str(e)}"
        )


@router.get("/soa/jobs/{job_id}/events")
async def get_soa_events(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    SSE stream for real-time SOA extraction progress.

    Events are sent when:
    - Phase changes (detection → awaiting_confirmation → extraction → interpretation → etc.)
    - Progress updates within a phase
    - Job completes or fails
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    soa_job = db.query(SOAJob).filter(SOAJob.id == job_uuid).first()
    if not soa_job:
        raise HTTPException(status_code=404, detail=f"SOA job not found: {job_id}")

    async def event_generator():
        """Generate SSE events for job progress."""
        last_status = None
        last_phase = None
        last_progress = None
        poll_count = 0
        max_polls = 600  # 10 minutes at 1s intervals

        while poll_count < max_polls:
            # Refresh job from database
            db.refresh(soa_job)

            current_status = soa_job.status
            current_phase = soa_job.current_phase
            current_progress = soa_job.phase_progress

            # Send event if something changed
            if (current_status != last_status or
                current_phase != last_phase or
                current_progress != last_progress):

                event_data = {
                    "status": current_status,
                    "phase": current_phase,
                    "progress": current_progress,
                    "detected_pages": soa_job.detected_pages if current_status == "awaiting_page_confirmation" else None,
                    "error": soa_job.error_message if current_status == "failed" else None,
                }

                # Include merge_plan from soa_job.merge_analysis when awaiting merge confirmation
                if current_status == "awaiting_merge_confirmation" and soa_job.merge_analysis:
                    event_data["merge_plan"] = soa_job.merge_analysis

                yield f"data: {json.dumps(event_data)}\n\n"

                last_status = current_status
                last_phase = current_phase
                last_progress = current_progress

                # Stop if job is complete or failed or awaiting merge confirmation
                if current_status in ["completed", "failed", "awaiting_merge_confirmation"]:
                    break

            await asyncio.sleep(1)
            poll_count += 1

        # Send final event
        yield f"data: {json.dumps({'status': 'stream_ended'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/protocols/{protocol_id}/soa/latest")
async def get_latest_soa_job(
    protocol_id: str,
    db: Session = Depends(get_db),
):
    """
    Get the latest SOA job for a protocol.

    Useful for checking if SOA extraction has already been done.
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

    # Get latest SOA job
    soa_job = db.query(SOAJob).filter(
        SOAJob.protocol_id == protocol.id
    ).order_by(SOAJob.created_at.desc()).first()

    if not soa_job:
        return {"job_id": None, "status": "not_started", "message": "No SOA extraction has been started"}

    response = {
        "job_id": str(soa_job.id),
        "status": soa_job.status,
        "detected_pages": soa_job.detected_pages if soa_job.status == "awaiting_page_confirmation" else None,
        "has_results": soa_job.status == "completed",
    }

    # Include merge_plan from soa_job.merge_analysis if awaiting merge confirmation
    if soa_job.status == "awaiting_merge_confirmation" and soa_job.merge_analysis:
        response["merge_plan"] = soa_job.merge_analysis

    return response


# =============================================================================
# MERGE PLAN ENDPOINTS
# =============================================================================


@router.post("/soa/jobs/{job_id}/analyze-merges")
async def trigger_merge_analysis(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    Trigger Phase 3.5: Merge Analysis.

    This endpoint runs the table merge analyzer on per-table USDM results
    and saves the merge plan to soa_job.merge_analysis.

    Call this after per-table extraction is complete (status: 'completed')
    to generate merge suggestions for human review.
    """
    from app.services.soa_worker import spawn_merge_analysis_process, register_soa_process

    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    soa_job = db.query(SOAJob).filter(SOAJob.id == job_uuid).first()
    if not soa_job:
        raise HTTPException(status_code=404, detail=f"SOA job not found: {job_id}")

    # Check if job has per-table results
    if soa_job.status not in ["completed", "extracting"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot run merge analysis - job status is '{soa_job.status}'. Expected 'completed'."
        )

    # Check if there are per-table results
    table_results = db.query(SOATableResult).filter(
        SOATableResult.soa_job_id == job_uuid
    ).all()

    if not table_results:
        raise HTTPException(
            status_code=400,
            detail="No per-table results found. Per-table extraction must complete first."
        )

    # Check if merge plan already exists in soa_job.merge_analysis
    if soa_job.merge_analysis:
        # Return existing plan
        return {
            "job_id": str(soa_job.id),
            "status": "awaiting_merge_confirmation",
            "message": "Merge plan already exists. Use GET /merge-plan to retrieve it."
        }

    # Get protocol for PDF path
    protocol = db.query(Protocol).filter(Protocol.id == soa_job.protocol_id).first()
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")

    try:
        pdf_path = get_pdf_path_for_protocol(protocol, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Update job status
    soa_job.status = "analyzing_merges"
    soa_job.current_phase = "merge_analysis"
    soa_job.phase_progress = {"phase": "merge_analysis", "progress": 0}
    soa_job.updated_at = datetime.utcnow()
    db.commit()

    # Spawn merge analysis process
    process = spawn_merge_analysis_process(
        soa_job_id=soa_job.id,
        protocol_id=protocol.id,
        pdf_path=pdf_path,
    )
    register_soa_process(str(soa_job.id), process)

    logger.info(f"Started merge analysis for job {job_id}")

    return {
        "job_id": str(soa_job.id),
        "status": "analyzing_merges",
        "message": "Merge analysis started. Poll status or use SSE for updates."
    }


class MergeGroupInfo(BaseModel):
    """Information about a merge group."""
    id: str
    table_ids: List[str]
    merge_type: str
    decision_level: int
    confidence: float
    reasoning: str
    confirmed: Optional[bool] = None
    user_override: Optional[Dict[str, Any]] = None


class MergePlanResponse(BaseModel):
    """Response with merge plan for human review."""
    soa_job_id: str
    protocol_id: str
    status: str
    total_tables_input: int
    suggested_merge_groups: int
    merge_groups: List[MergeGroupInfo]
    analysis_details: Optional[Dict[str, Any]] = None
    created_at: str


class MergePlanConfirmationRequest(BaseModel):
    """Request to confirm or modify merge plan."""
    confirmed_groups: List[Dict[str, Any]]  # List of {id, confirmed, user_override?}
    confirmed_by: Optional[str] = None


class MergePlanConfirmationResponse(BaseModel):
    """Response after confirming merge plan."""
    soa_job_id: str
    status: str
    confirmed_groups: int
    modified_groups: int
    message: str


@router.get("/soa/jobs/{job_id}/merge-plan", response_model=MergePlanResponse)
async def get_merge_plan(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    Get the merge plan for an SOA job.

    Returns the suggested merge groups for human review.
    Only available after Phase 3 completes and before interpretation.
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    # Check job exists
    soa_job = db.query(SOAJob).filter(SOAJob.id == job_uuid).first()
    if not soa_job:
        raise HTTPException(status_code=404, detail=f"SOA job not found: {job_id}")

    # Get merge plan from soa_job.merge_analysis
    if not soa_job.merge_analysis:
        raise HTTPException(
            status_code=404,
            detail=f"Merge plan not found for job {job_id}. Merge analysis may not have run yet."
        )

    plan_data = soa_job.merge_analysis
    merge_groups = []

    for mg in plan_data.get("mergeGroups", []):
        merge_groups.append(MergeGroupInfo(
            id=mg.get("id", ""),
            table_ids=mg.get("tableIds", []),
            merge_type=mg.get("mergeType", "unknown"),
            decision_level=mg.get("decisionLevel", 0),
            confidence=mg.get("confidence", 0.0),
            reasoning=mg.get("reasoning", ""),
            confirmed=mg.get("confirmed"),
            user_override=mg.get("userOverride"),
        ))

    return MergePlanResponse(
        soa_job_id=str(soa_job.id),
        protocol_id=str(soa_job.protocol_id),
        status=plan_data.get("status", "pending_confirmation"),
        total_tables_input=plan_data.get("totalTablesInput", 0),
        suggested_merge_groups=plan_data.get("suggestedMergeGroups", 0),
        merge_groups=merge_groups,
        analysis_details=plan_data.get("analysisDetails"),
        created_at=plan_data.get("analysisTimestamp", soa_job.created_at.isoformat() if soa_job.created_at else ""),
    )


@router.post("/soa/jobs/{job_id}/merge-plan/confirm", response_model=MergePlanConfirmationResponse)
async def confirm_merge_plan(
    job_id: str,
    request: MergePlanConfirmationRequest,
    db: Session = Depends(get_db),
):
    """
    Confirm or modify the merge plan.

    After confirmation, the pipeline will run 12-stage interpretation
    on each confirmed merge group.

    Request body example:
    ```json
    {
        "confirmed_groups": [
            {"id": "MG-001", "confirmed": true},
            {"id": "MG-002", "confirmed": true},
            {"id": "MG-003", "confirmed": false, "user_override": {
                "action": "split",
                "new_groups": [
                    {"table_ids": ["SOA-4", "SOA-5"]},
                    {"table_ids": ["SOA-6"]}
                ],
                "reason": "SOA-6 is safety monitoring, should be separate"
            }}
        ]
    }
    ```
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    # Check job exists
    soa_job = db.query(SOAJob).filter(SOAJob.id == job_uuid).first()
    if not soa_job:
        raise HTTPException(status_code=404, detail=f"SOA job not found: {job_id}")

    # Get merge plan from soa_job.merge_analysis
    if not soa_job.merge_analysis:
        raise HTTPException(
            status_code=404,
            detail=f"Merge plan not found for job {job_id}"
        )

    merge_plan_data = soa_job.merge_analysis

    if merge_plan_data.get("status") == "confirmed":
        raise HTTPException(
            status_code=400,
            detail="Merge plan already confirmed"
        )

    # Build confirmed plan
    confirmed_count = 0
    modified_count = 0
    confirmed_groups_list = []

    for group_conf in request.confirmed_groups:
        group_id = group_conf.get("id")
        is_confirmed = group_conf.get("confirmed", True)
        user_override = group_conf.get("user_override")

        if is_confirmed:
            confirmed_count += 1
        elif user_override:
            modified_count += 1

        confirmed_groups_list.append({
            "id": group_id,
            "confirmed": is_confirmed,
            "userOverride": user_override,
        })

    # Update merge_analysis in soa_job with confirmation details
    merge_plan_data["status"] = "confirmed"
    merge_plan_data["confirmedAt"] = datetime.utcnow().isoformat()
    merge_plan_data["confirmedBy"] = request.confirmed_by or "user"
    merge_plan_data["confirmedGroups"] = confirmed_groups_list

    # Update SOA job
    soa_job.merge_analysis = merge_plan_data
    flag_modified(soa_job, "merge_analysis")  # Tell SQLAlchemy the JSONB was modified
    soa_job.status = "interpreting"
    soa_job.current_phase = "interpretation"
    soa_job.phase_progress = {"phase": "interpretation", "progress": 0}
    soa_job.updated_at = datetime.utcnow()

    db.commit()

    logger.info(f"Confirmed merge plan for job {job_id}: {confirmed_count} confirmed, {modified_count} modified")

    # Auto-start interpretation process
    try:
        from app.services.soa_worker import spawn_merge_interpretation_process, register_soa_process

        # Get protocol for PDF path
        protocol = db.query(Protocol).filter(Protocol.id == soa_job.protocol_id).first()
        if protocol:
            pdf_path = get_pdf_path_for_protocol(protocol, db)

            # Spawn interpretation process
            process = spawn_merge_interpretation_process(
                soa_job_id=soa_job.id,
                protocol_id=protocol.id,
                pdf_path=pdf_path,
                confirmed_plan=merge_plan_data,
            )
            register_soa_process(str(soa_job.id), process)
            logger.info(f"Auto-started interpretation for job {job_id}")
    except Exception as e:
        logger.error(f"Failed to auto-start interpretation: {e}")
        # Don't fail the confirmation, user can manually resume

    return MergePlanConfirmationResponse(
        soa_job_id=str(soa_job.id),
        status="confirmed",
        confirmed_groups=confirmed_count,
        modified_groups=modified_count,
        message="Merge plan confirmed. Interpretation started automatically."
    )


@router.post("/soa/jobs/{job_id}/resume")
async def resume_soa_pipeline(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    Resume SOA pipeline after merge plan confirmation.

    This triggers 12-stage interpretation on each confirmed merge group.
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    # Check job exists
    soa_job = db.query(SOAJob).filter(SOAJob.id == job_uuid).first()
    if not soa_job:
        raise HTTPException(status_code=404, detail=f"SOA job not found: {job_id}")

    if soa_job.status != "awaiting_interpretation":
        raise HTTPException(
            status_code=400,
            detail=f"Job is not ready for interpretation (current status: {soa_job.status})"
        )

    # Get confirmed merge plan from soa_job.merge_analysis
    if not soa_job.merge_analysis:
        raise HTTPException(
            status_code=400,
            detail="No merge plan found"
        )

    merge_plan_data = soa_job.merge_analysis
    if merge_plan_data.get("status") != "confirmed":
        raise HTTPException(
            status_code=400,
            detail="Merge plan not confirmed"
        )

    # Get protocol
    protocol = db.query(Protocol).filter(Protocol.id == soa_job.protocol_id).first()
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")

    # Update status
    soa_job.status = "interpreting"
    soa_job.current_phase = "interpretation"
    soa_job.updated_at = datetime.utcnow()
    db.commit()

    # Get PDF path
    try:
        pdf_path = get_pdf_path_for_protocol(protocol, db)
    except ValueError as e:
        soa_job.status = "failed"
        soa_job.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))

    # Spawn interpretation process for confirmed groups
    from app.services.soa_worker import (
        spawn_merge_interpretation_process,
        register_soa_process,
    )

    process = spawn_merge_interpretation_process(
        soa_job_id=soa_job.id,
        protocol_id=protocol.id,
        pdf_path=pdf_path,
        confirmed_plan=merge_plan_data,
    )
    register_soa_process(str(soa_job.id), process)

    return {
        "job_id": str(soa_job.id),
        "status": "interpreting",
        "message": "Interpretation started for confirmed merge groups"
    }


@router.get("/soa/jobs/{job_id}/merge-results")
async def get_merge_group_results(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    Get interpretation results for all merge groups.

    Returns the status and results of 12-stage interpretation
    for each confirmed merge group from soa_job.merge_analysis.
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    # Check job exists
    soa_job = db.query(SOAJob).filter(SOAJob.id == job_uuid).first()
    if not soa_job:
        raise HTTPException(status_code=404, detail=f"SOA job not found: {job_id}")

    # Get merge plan from soa_job.merge_analysis
    if not soa_job.merge_analysis:
        raise HTTPException(
            status_code=404,
            detail=f"Merge plan not found for job {job_id}"
        )

    merge_plan_data = soa_job.merge_analysis

    # Get group results from merge_analysis.groupResults
    group_results = merge_plan_data.get("groupResults", [])

    results = []
    for gr in group_results:
        results.append({
            "id": gr.get("id", ""),
            "merge_group_id": gr.get("mergeGroupId", gr.get("id", "")),
            "source_table_ids": gr.get("sourceTableIds", gr.get("tableIds", [])),
            "merge_type": gr.get("mergeType", ""),
            "status": gr.get("status", "pending"),
            "error_message": gr.get("errorMessage"),
            "counts": gr.get("counts", {
                "visits": 0,
                "activities": 0,
                "sais": 0,
                "footnotes": 0,
            }),
            "quality_score": gr.get("qualityScore"),
            "created_at": gr.get("createdAt"),
            "completed_at": gr.get("completedAt"),
        })

    completed_count = sum(1 for gr in group_results if gr.get("status") == "completed")
    failed_count = sum(1 for gr in group_results if gr.get("status") == "failed")

    return {
        "job_id": str(soa_job.id),
        "status": soa_job.status,
        "total_groups": len(group_results),
        "completed_groups": completed_count,
        "failed_groups": failed_count,
        "group_results": results,
    }


@router.get("/soa/jobs/{job_id}/merge-results/{group_id}")
async def get_merge_group_usdm(
    job_id: str,
    group_id: str,
    db: Session = Depends(get_db),
):
    """
    Get the final USDM for a specific merge group.

    Returns the full USDM output after 12-stage interpretation
    from soa_job.merge_analysis.groupResults.
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    # Check job exists
    soa_job = db.query(SOAJob).filter(SOAJob.id == job_uuid).first()
    if not soa_job:
        raise HTTPException(status_code=404, detail=f"SOA job not found: {job_id}")

    # Get merge plan from soa_job.merge_analysis
    if not soa_job.merge_analysis:
        raise HTTPException(
            status_code=404,
            detail=f"Merge plan not found for job {job_id}"
        )

    merge_plan_data = soa_job.merge_analysis

    # Find the group result by group_id
    group_results = merge_plan_data.get("groupResults", [])
    group_result = None
    for gr in group_results:
        if gr.get("id") == group_id or gr.get("mergeGroupId") == group_id:
            group_result = gr
            break

    if not group_result:
        raise HTTPException(
            status_code=404,
            detail=f"Merge group result not found: {group_id}"
        )

    return {
        "id": group_result.get("id", ""),
        "merge_group_id": group_result.get("mergeGroupId", group_result.get("id", "")),
        "source_table_ids": group_result.get("sourceTableIds", group_result.get("tableIds", [])),
        "merge_type": group_result.get("mergeType", ""),
        "status": group_result.get("status", "pending"),
        "merged_usdm": group_result.get("mergedUsdm"),
        "final_usdm": group_result.get("finalUsdm"),
        "interpretation_result": group_result.get("interpretationResult"),
        "quality_score": group_result.get("qualityScore"),
    }


@router.get("/soa/jobs/{job_id}/interpretation-stages")
async def get_interpretation_stages(
    job_id: str,
    group_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Get 12-stage interpretation results for a SOA job.

    Returns detailed stage-by-stage results from the interpretation pipeline.
    Each stage includes:
    - Stage 1: Domain Categorization
    - Stage 2: Activity Expansion
    - Stage 3: Hierarchy Builder
    - Stage 4: Alternative Resolution
    - Stage 5: Specimen Enrichment
    - Stage 6: Conditional Expansion
    - Stage 7: Timing Distribution
    - Stage 8: Cycle Expansion
    - Stage 9: Protocol Mining
    - Stage 10: Human Review
    - Stage 11: Schedule Generation
    - Stage 12: USDM Compliance

    Args:
        job_id: The SOA job ID
        group_id: Optional merge group ID to filter results

    Returns:
        Dictionary with stage results for all or specific merge groups
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")

    # Check job exists
    soa_job = db.query(SOAJob).filter(SOAJob.id == job_uuid).first()
    if not soa_job:
        raise HTTPException(status_code=404, detail=f"SOA job not found: {job_id}")

    # Get merge plan from soa_job.merge_analysis
    if not soa_job.merge_analysis:
        raise HTTPException(
            status_code=404,
            detail=f"No interpretation results found for job {job_id}. Run merge confirmation first."
        )

    merge_plan_data = soa_job.merge_analysis

    # Get group results from merge_analysis.groupResults
    group_results = merge_plan_data.get("groupResults", [])

    if not group_results:
        raise HTTPException(
            status_code=404,
            detail=f"No interpretation results found. Run merge confirmation and interpretation first."
        )

    # Stage metadata for UI display
    stage_metadata = {
        1: {"name": "Domain Categorization", "description": "Maps activities to CDISC SDTM domains"},
        2: {"name": "Activity Expansion", "description": "Decomposes parent activities into components"},
        3: {"name": "Hierarchy Builder", "description": "Builds activity hierarchy structure"},
        4: {"name": "Alternative Resolution", "description": "Resolves X or Y choice points"},
        5: {"name": "Specimen Enrichment", "description": "Enriches specimen collection requirements"},
        6: {"name": "Conditional Expansion", "description": "Interprets conditional footnotes"},
        7: {"name": "Timing Distribution", "description": "Expands BI/EOI timing modifiers"},
        8: {"name": "Cycle Expansion", "description": "Handles cycle patterns and expansions"},
        9: {"name": "Protocol Mining", "description": "Discovers cross-references to other sections"},
        10: {"name": "Human Review", "description": "Assembles human review package"},
        11: {"name": "Schedule Generation", "description": "Generates draft visit schedule"},
        12: {"name": "USDM Compliance", "description": "Ensures USDM 4.0 compliance"},
    }

    # If group_id is specified, filter to that group
    if group_id:
        group_result = None
        for gr in group_results:
            if gr.get("id") == group_id or gr.get("mergeGroupId") == group_id:
                group_result = gr
                break

        if not group_result:
            raise HTTPException(
                status_code=404,
                detail=f"Merge group not found: {group_id}"
            )

        stage_results = group_result.get("stageResults", {})
        interpretation_summary = group_result.get("interpretationResult", {})

        return {
            "job_id": str(soa_job.id),
            "merge_group_id": group_id,
            "status": group_result.get("status", "pending"),
            "stage_metadata": stage_metadata,
            "stage_results": stage_results,
            "interpretation_summary": {
                "success": interpretation_summary.get("success", False),
                "stages_completed": interpretation_summary.get("stagesCompleted", 0),
                "stages_failed": interpretation_summary.get("stagesFailed", 0),
                "stages_skipped": interpretation_summary.get("stagesSkipped", 0),
                "total_duration_seconds": interpretation_summary.get("totalDurationSeconds", 0),
                "stage_durations": interpretation_summary.get("stageDurations", {}),
                "stage_statuses": interpretation_summary.get("stageStatuses", {}),
            },
        }

    # Return stage results for all groups
    all_group_stages = []
    for gr in group_results:
        stage_results = gr.get("stageResults", {})
        interpretation_summary = gr.get("interpretationResult", {})

        all_group_stages.append({
            "merge_group_id": gr.get("id", gr.get("mergeGroupId", "")),
            "source_table_ids": gr.get("sourceTableIds", gr.get("tableIds", [])),
            "status": gr.get("status", "pending"),
            "stage_results": stage_results,
            "interpretation_summary": {
                "success": interpretation_summary.get("success", False),
                "stages_completed": interpretation_summary.get("stagesCompleted", 0),
                "stages_failed": interpretation_summary.get("stagesFailed", 0),
                "stages_skipped": interpretation_summary.get("stagesSkipped", 0),
                "total_duration_seconds": interpretation_summary.get("totalDurationSeconds", 0),
                "stage_durations": interpretation_summary.get("stageDurations", {}),
                "stage_statuses": interpretation_summary.get("stageStatuses", {}),
            },
            "counts": gr.get("counts", {}),
        })

    return {
        "job_id": str(soa_job.id),
        "status": soa_job.status,
        "total_groups": len(group_results),
        "stage_metadata": stage_metadata,
        "groups": all_group_stages,
    }
