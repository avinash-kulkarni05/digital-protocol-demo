"""
Jobs router for status tracking and SSE streaming.

Endpoints:
- GET /{job_id} - Get job status
- GET /{job_id}/results - Get all module results
- GET /{job_id}/events - SSE stream of job events
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.db import get_db, Job, ModuleResult, JobEvent
from app.services.checkpoint_service import CheckpointService

logger = logging.getLogger(__name__)

router = APIRouter()


class ModuleStatus(BaseModel):
    """Status for a single extraction module."""
    module_id: str
    display_name: str
    status: str  # pending, running, completed, failed
    quality_score: Optional[float] = None
    wave: int = 0


class JobStatusResponse(BaseModel):
    """Response model for job status."""
    job_id: str
    protocol_id: str
    status: str
    current_module: Optional[str]
    completed_modules: list
    failed_modules: list
    total_modules: int
    modules: list[ModuleStatus]
    progress: dict
    started_at: Optional[str]
    completed_at: Optional[str]
    error_message: Optional[str]


class ModuleResultResponse(BaseModel):
    """Response model for module result."""
    module_id: str
    status: str
    provenance_coverage: Optional[float]
    pass1_duration_seconds: Optional[float]
    pass2_duration_seconds: Optional[float]
    retry_count: int


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: UUID,
    db: Session = Depends(get_db),
):
    """Get detailed job status with module-level progress."""
    from app.module_registry import get_enabled_modules

    checkpoint_service = CheckpointService(db)

    try:
        status = checkpoint_service.get_job_status(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get module results for quality scores
    module_results = db.query(ModuleResult).filter(
        ModuleResult.job_id == job_id
    ).all()
    result_map = {r.module_id: r for r in module_results}

    # Build modules array from registry
    completed_set = set(status.get("completed_modules", []))
    failed_set = set(status.get("failed_modules", []))
    current = status.get("current_module")

    modules = []
    for module in get_enabled_modules():
        if module.module_id in completed_set:
            mod_status = "completed"
        elif module.module_id in failed_set:
            mod_status = "failed"
        elif module.module_id == current:
            mod_status = "running"
        else:
            mod_status = "pending"

        quality_score = None
        if module.module_id in result_map:
            result = result_map[module.module_id]
            if result.provenance_coverage is not None:
                quality_score = result.provenance_coverage

        modules.append(ModuleStatus(
            module_id=module.module_id,
            display_name=module.display_name,
            status=mod_status,
            quality_score=quality_score,
            wave=module.wave,
        ))

    return JobStatusResponse(
        job_id=status["job_id"],
        protocol_id=status["protocol_id"],
        status=status["status"],
        current_module=status["current_module"],
        completed_modules=status["completed_modules"],
        failed_modules=status["failed_modules"],
        total_modules=status["progress"]["total"],
        modules=modules,
        progress=status["progress"],
        started_at=status["started_at"],
        completed_at=status["completed_at"],
        error_message=status["error_message"],
    )


@router.get("/{job_id}/results")
async def get_job_results(
    job_id: UUID,
    db: Session = Depends(get_db),
):
    """Get all module results for a job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    results = db.query(ModuleResult).filter(
        ModuleResult.job_id == job_id
    ).order_by(ModuleResult.created_at).all()

    return [
        {
            "module_id": r.module_id,
            "status": r.status,
            "provenance_coverage": r.provenance_coverage,
            "compliance_score": r.compliance_score,
            "pass1_duration_seconds": r.pass1_duration_seconds,
            "pass2_duration_seconds": r.pass2_duration_seconds,
            "retry_count": r.retry_count,
            "has_data": r.extracted_data is not None,
            "created_at": r.created_at.isoformat(),
        }
        for r in results
    ]


@router.get("/{job_id}/results/{module_id}")
async def get_module_result(
    job_id: UUID,
    module_id: str,
    db: Session = Depends(get_db),
):
    """Get extracted data for a specific module."""
    result = db.query(ModuleResult).filter(
        ModuleResult.job_id == job_id,
        ModuleResult.module_id == module_id,
    ).first()

    if not result:
        raise HTTPException(status_code=404, detail="Module result not found")

    return {
        "module_id": result.module_id,
        "status": result.status,
        "provenance_coverage": result.provenance_coverage,
        "extracted_data": result.extracted_data,
        "error_details": result.error_details,
        "created_at": result.created_at.isoformat(),
    }


@router.get("/{job_id}/events")
async def stream_job_events(
    job_id: UUID,
    last_event_id: Optional[int] = Query(None, description="Last received event ID"),
    db: Session = Depends(get_db),
):
    """
    SSE stream of job events for real-time progress tracking.

    Events are streamed as they occur. Use last_event_id to resume from
    a specific point after reconnection.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        """Generate SSE events."""
        current_id = last_event_id or 0

        while True:
            # Query new events
            events = db.query(JobEvent).filter(
                JobEvent.job_id == job_id,
                JobEvent.id > current_id,
            ).order_by(JobEvent.id).all()

            for event in events:
                current_id = event.id
                data = {
                    "event_type": event.event_type,
                    "module_id": event.module_id,
                    "payload": event.payload,
                    "timestamp": event.created_at.isoformat(),
                }
                yield {
                    "event": event.event_type,
                    "id": str(event.id),
                    "data": json.dumps(data),
                }

            # Check if job is complete
            job_check = db.query(Job).filter(Job.id == job_id).first()
            if job_check and job_check.status in ("completed", "failed", "completed_with_errors"):
                # Send final status
                yield {
                    "event": "job_finished",
                    "data": json.dumps({
                        "status": job_check.status,
                        "completed_modules": job_check.completed_modules,
                        "failed_modules": job_check.failed_modules,
                    }),
                }
                break

            # Poll interval
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@router.delete("/{job_id}")
async def cancel_job(
    job_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Cancel a running job.

    Note: This marks the job as cancelled but may not stop
    in-progress module extractions immediately.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="Job already finished")

    job.status = "cancelled"
    job.completed_at = datetime.utcnow()
    job.error_message = "Cancelled by user"
    db.commit()

    logger.info(f"Job {job_id} cancelled")

    return {"status": "cancelled", "job_id": str(job_id)}


@router.get("/protocol/{protocol_id}/latest")
async def get_latest_job_for_protocol(
    protocol_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get the latest job for a protocol.

    Useful for resuming progress tracking after page refresh.
    """
    job = db.query(Job).filter(
        Job.protocol_id == protocol_id
    ).order_by(Job.created_at.desc()).first()

    if not job:
        return {"job_id": None, "status": "no_job", "message": "No job found for this protocol"}

    return {
        "job_id": str(job.id),
        "protocol_id": str(job.protocol_id),
        "status": job.status,
        "completed_modules": job.completed_modules or [],
        "failed_modules": job.failed_modules or [],
        "total_modules": job.total_modules,
        "progress": {
            "completed": len(job.completed_modules or []),
            "failed": len(job.failed_modules or []),
            "total": job.total_modules,
        },
    }


@router.get("/{job_id}/summary")
async def get_job_summary(
    job_id: UUID,
    db: Session = Depends(get_db),
):
    """Get extraction summary with statistics."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    results = db.query(ModuleResult).filter(ModuleResult.job_id == job_id).all()

    total_pass1_time = sum(r.pass1_duration_seconds or 0 for r in results)
    total_pass2_time = sum(r.pass2_duration_seconds or 0 for r in results)
    coverages = [r.provenance_coverage for r in results if r.provenance_coverage is not None]
    avg_coverage = sum(coverages) / len(coverages) if coverages else 0

    return {
        "job_id": str(job_id),
        "status": job.status,
        "modules_completed": len(job.completed_modules or []),
        "modules_failed": len(job.failed_modules or []),
        "modules_total": job.total_modules,
        "average_provenance_coverage": round(avg_coverage, 3),
        "total_pass1_duration_seconds": round(total_pass1_time, 2),
        "total_pass2_duration_seconds": round(total_pass2_time, 2),
        "total_duration_seconds": round(total_pass1_time + total_pass2_time, 2),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/{job_id}/outputs/{file_type}")
async def get_job_output_file(
    job_id: UUID,
    file_type: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve output file from database.

    File types: usdm_json, extraction_results, quality_report, annotated_pdf, annotation_report
    """
    from app.db import ExtractionOutput
    from fastapi.responses import Response
    import json

    output = db.query(ExtractionOutput).filter(
        ExtractionOutput.job_id == job_id,
        ExtractionOutput.file_type == file_type
    ).first()

    if not output:
        raise HTTPException(status_code=404, detail=f"File '{file_type}' not found")

    # Serve JSON
    if output.content_type == "application/json":
        if not output.json_data:
            raise HTTPException(status_code=404, detail="JSON data not available")
        return Response(
            content=json.dumps(output.json_data, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{output.file_name}"'}
        )

    # Serve PDF
    elif output.content_type == "application/pdf":
        if not output.file_data:
            raise HTTPException(status_code=404, detail="PDF data not available")
        return Response(
            content=output.file_data,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{output.file_name}"',
                "Content-Length": str(output.file_size or len(output.file_data))
            }
        )

    raise HTTPException(status_code=500, detail="Unknown content type")


@router.get("/{job_id}/outputs")
async def list_job_outputs(
    job_id: UUID,
    db: Session = Depends(get_db),
):
    """List all output files for a job."""
    from app.db import ExtractionOutput

    outputs = db.query(ExtractionOutput).filter(
        ExtractionOutput.job_id == job_id
    ).all()

    return [
        {
            "file_type": o.file_type,
            "file_name": o.file_name,
            "file_size": o.file_size,
            "content_type": o.content_type,
            "created_at": o.created_at.isoformat(),
            "download_url": f"/api/v1/jobs/{job_id}/outputs/{o.file_type}",
        }
        for o in outputs
    ]
