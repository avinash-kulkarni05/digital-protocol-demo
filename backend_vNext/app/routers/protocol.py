"""
Protocol router for PDF upload and extraction triggers.

Endpoints:
- POST /upload - Upload protocol PDF
- POST /{protocol_id}/extract - Start extraction job
- GET /{protocol_id} - Get protocol details
"""

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db, Protocol, Job
from app.services.checkpoint_service import CheckpointService

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Helper Functions
# =============================================================================

def get_protocol_by_id_or_study_id(protocol_id: str, db: Session) -> Optional[Protocol]:
    """
    Find protocol by UUID or studyId (filename without .pdf extension).

    Args:
        protocol_id: Either a UUID string or a studyId
        db: Database session

    Returns:
        Protocol if found, None otherwise
    """
    # Try to parse as UUID first
    try:
        protocol_uuid = UUID(protocol_id)
        return db.query(Protocol).filter(Protocol.id == protocol_uuid).first()
    except ValueError:
        # Not a UUID, try as studyId (filename match)
        protocol = db.query(Protocol).filter(
            Protocol.filename == f"{protocol_id}.pdf"
        ).first()
        if not protocol:
            # Try partial match
            protocol = db.query(Protocol).filter(
                Protocol.filename.ilike(f"%{protocol_id}%")
            ).first()
        return protocol


# =============================================================================
# Response Models
# =============================================================================

class ProtocolListResponse(BaseModel):
    """Response model for protocol list."""
    id: str
    filename: str
    file_hash: str
    file_size: Optional[int] = None
    studyId: Optional[str] = None
    studyTitle: Optional[str] = None
    usdmData: Optional[dict] = None
    extractionStatus: Optional[str] = None  # pending, processing, completed, failed
    created_at: str


class ProtocolResponse(BaseModel):
    """Response model for protocol details."""
    id: str
    filename: str
    file_hash: str
    file_size: Optional[int] = None
    gemini_file_uri: Optional[str] = None
    created_at: str


class ExtractionRequest(BaseModel):
    """Request model for starting extraction."""
    resume: bool = True
    modules: Optional[list] = None  # Specific modules to extract (default: all)


class ExtractionResponse(BaseModel):
    """Response model for extraction job."""
    job_id: str
    protocol_id: str
    status: str
    message: str


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_hash_from_bytes(file_data: bytes) -> str:
    """Compute SHA-256 hash from binary data."""
    return hashlib.sha256(file_data).hexdigest()


@router.get("", response_model=list[ProtocolListResponse])
async def list_protocols(
    db: Session = Depends(get_db),
):
    """
    List all uploaded protocols.

    Returns protocols from the protocols table for display on landing page.
    Includes extracted USDM data for rich metadata display.
    """
    protocols = db.query(Protocol).order_by(Protocol.created_at.desc()).all()

    return [
        ProtocolListResponse(
            id=str(protocol.id),
            filename=protocol.filename,
            file_hash=protocol.file_hash,
            file_size=protocol.file_size,
            studyId=protocol.filename.replace(".pdf", ""),
            studyTitle=protocol.filename.replace(".pdf", "").replace("_", " "),
            usdmData=protocol.usdm_json,  # Extracted USDM 4.0 data
            extractionStatus=protocol.extraction_status,  # extraction status
            created_at=protocol.created_at.isoformat(),
        )
        for protocol in protocols
    ]


@router.post("/upload", response_model=ProtocolResponse)
async def upload_protocol(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload a protocol PDF file.

    The file binary data is stored in the database (file_data column).
    Duplicate files (same hash) return the existing record.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Read file data into memory
    try:
        file_data = await file.read()
        file_size = len(file_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")

    # Compute file hash from binary data
    file_hash = compute_hash_from_bytes(file_data)

    # Check for existing protocol with same hash
    existing = db.query(Protocol).filter(Protocol.file_hash == file_hash).first()
    if existing:
        logger.info(f"Protocol already exists: {existing.id} ({existing.filename})")
        # Update file data if it wasn't stored yet (migration scenario)
        needs_update = False
        if existing.file_data is None:
            existing.file_data = file_data
            existing.file_size = file_size
            existing.content_type = "application/pdf"
            existing.filename = file.filename
            needs_update = True
        # Set protocol_name if not already set
        if existing.protocol_name is None:
            existing.protocol_name = existing.filename.rsplit('.', 1)[0] if '.' in existing.filename else existing.filename
            needs_update = True
        if needs_update:
            db.commit()
            logger.info(f"Updated protocol {existing.id}")
        return ProtocolResponse(
            id=str(existing.id),
            filename=existing.filename,
            file_hash=existing.file_hash,
            file_size=existing.file_size,
            gemini_file_uri=existing.gemini_file_uri,
            created_at=existing.created_at.isoformat(),
        )

    # Derive protocol_name from filename (remove .pdf extension)
    protocol_name = file.filename.rsplit('.', 1)[0] if '.' in file.filename else file.filename

    # Create new protocol record with binary data
    protocol = Protocol(
        filename=file.filename,
        protocol_name=protocol_name,
        file_hash=file_hash,
        file_data=file_data,
        file_size=file_size,
        content_type="application/pdf",
    )
    db.add(protocol)
    db.commit()
    db.refresh(protocol)

    logger.info(f"Uploaded protocol: {protocol.id} ({file.filename}, {file_size} bytes)")

    return ProtocolResponse(
        id=str(protocol.id),
        filename=protocol.filename,
        file_hash=protocol.file_hash,
        file_size=protocol.file_size,
        gemini_file_uri=protocol.gemini_file_uri,
        created_at=protocol.created_at.isoformat(),
    )


@router.get("/{protocol_id}", response_model=ProtocolResponse)
async def get_protocol(
    protocol_id: UUID,
    db: Session = Depends(get_db),
):
    """Get protocol details by ID."""
    protocol = db.query(Protocol).filter(Protocol.id == protocol_id).first()
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")

    return ProtocolResponse(
        id=str(protocol.id),
        filename=protocol.filename,
        file_hash=protocol.file_hash,
        file_size=protocol.file_size,
        gemini_file_uri=protocol.gemini_file_uri,
        created_at=protocol.created_at.isoformat(),
    )


@router.get("/{protocol_id}/pdf")
async def get_protocol_pdf(
    protocol_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve the PDF binary data for a protocol.

    Accepts either UUID or studyId (filename without .pdf extension).
    Returns the PDF file as binary data with appropriate content-type header.
    Frontend can use this endpoint to display or download the PDF.
    """
    protocol = get_protocol_by_id_or_study_id(protocol_id, db)
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")

    if not protocol.file_data:
        raise HTTPException(status_code=404, detail="PDF data not found in database")

    return Response(
        content=protocol.file_data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{protocol.filename}"',
            "Content-Length": str(protocol.file_size or len(protocol.file_data)),
        }
    )


@router.get("/{protocol_id}/pdf/annotated")
async def get_annotated_pdf(
    protocol_id: str,
    job_id: Optional[UUID] = Query(None, description="Specific job ID (default: latest)"),
    db: Session = Depends(get_db),
):
    """
    Retrieve annotated PDF for a protocol.

    Accepts either UUID or studyId (filename without .pdf extension).
    Falls back to original PDF if no annotated version exists.
    """
    from app.db import ExtractionOutput

    protocol = get_protocol_by_id_or_study_id(protocol_id, db)
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")

    # Find annotated PDF
    query = db.query(ExtractionOutput).filter(
        ExtractionOutput.protocol_id == protocol.id,
        ExtractionOutput.file_type == "annotated_pdf"
    )

    if job_id:
        query = query.filter(ExtractionOutput.job_id == job_id)
    else:
        query = query.order_by(ExtractionOutput.created_at.desc())

    annotated_output = query.first()

    if annotated_output and annotated_output.file_data:
        return Response(
            content=annotated_output.file_data,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{annotated_output.file_name}"',
                "Content-Length": str(annotated_output.file_size)
            }
        )

    # Fallback to original PDF
    logger.info(f"No annotated PDF for protocol {protocol_id}, serving original")
    if not protocol.file_data:
        raise HTTPException(status_code=404, detail="No PDF available")

    return Response(
        content=protocol.file_data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{protocol.filename}"',
            "Content-Length": str(protocol.file_size)
        }
    )


@router.post("/{protocol_id}/extract", response_model=ExtractionResponse)
async def start_extraction(
    protocol_id: UUID,
    request: ExtractionRequest,
    db: Session = Depends(get_db),
):
    """
    Start extraction job for a protocol.

    Extraction runs in a **separate OS process** to ensure the API
    remains responsive. This is a fire-and-forget operation - poll
    GET /jobs/{job_id} for status updates.

    The extraction process:
    1. Creates a new job record (status: "pending")
    2. Spawns a separate Python process
    3. Returns immediately with job_id
    4. Extraction runs independently (30+ minutes)
    5. Process updates database directly as modules complete
    """
    # Get protocol
    protocol = db.query(Protocol).filter(Protocol.id == protocol_id).first()
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")

    # Check if PDF data is available (either in database or on filesystem)
    has_db_data = protocol.file_data is not None
    has_file_path = protocol.file_path and Path(protocol.file_path).exists()

    if not has_db_data and not has_file_path:
        raise HTTPException(status_code=400, detail="Protocol PDF data not found")

    # If we have database data but no file path, create a temp file for extraction
    # (extraction pipeline will be updated to read from DB directly later)
    pdf_path = protocol.file_path
    temp_file_path = None
    if has_db_data and not has_file_path:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(protocol.file_data)
            temp_file_path = tmp.name
        pdf_path = temp_file_path
        logger.info(f"Created temp file for protocol {protocol_id}: {temp_file_path}")

    # Update protocol status to processing
    protocol.extraction_status = "processing"
    db.commit()

    # Create job record
    checkpoint_service = CheckpointService(db)
    job = checkpoint_service.create_job(protocol_id=protocol_id)

    # Spawn extraction in a separate OS process
    # This returns IMMEDIATELY - extraction runs independently
    from app.services.extraction_worker import (
        spawn_extraction_process,
        register_extraction_process,
    )

    process = spawn_extraction_process(
        job_id=job.id,
        protocol_id=protocol_id,
        pdf_path=pdf_path,  # Use pdf_path (includes temp file path if needed)
        resume=request.resume,
    )

    # Register for monitoring (optional)
    register_extraction_process(str(job.id), process)

    logger.info(
        f"Started extraction job {job.id} in process {process.pid} "
        f"for protocol {protocol_id}"
    )

    return ExtractionResponse(
        job_id=str(job.id),
        protocol_id=str(protocol_id),
        status="running",
        message=f"Extraction started in background process (PID: {process.pid})",
    )


@router.get("/{protocol_id}/jobs")
async def list_protocol_jobs(
    protocol_id: UUID,
    db: Session = Depends(get_db),
):
    """List all extraction jobs for a protocol."""
    protocol = db.query(Protocol).filter(Protocol.id == protocol_id).first()
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")

    jobs = db.query(Job).filter(Job.protocol_id == protocol_id).order_by(
        Job.created_at.desc()
    ).all()

    return [
        {
            "job_id": str(job.id),
            "status": job.status,
            "current_module": job.current_module,
            "completed_modules": len(job.completed_modules or []),
            "total_modules": job.total_modules,
            "created_at": job.created_at.isoformat(),
        }
        for job in jobs
    ]


@router.get("/extractions/active")
async def get_active_extractions():
    """
    Get list of currently running extraction processes.

    This endpoint is useful for monitoring and debugging.
    """
    from app.services.extraction_worker import get_active_extractions

    return {
        "active_extractions": get_active_extractions(),
    }


@router.get("/{protocol_id}/eligibility")
async def get_eligibility_data(
    protocol_id: str,
    db: Session = Depends(get_db),
):
    """
    Get eligibility analysis results for a protocol.

    Looks for eligibility output in:
    - protocols/{protocol_name}/eligibility_output/{latest_timestamp}/

    Returns the eligibility_criteria.json data if available.
    """
    import json
    import glob

    # Find protocol by UUID or study ID
    protocol = get_protocol_by_id_or_study_id(protocol_id, db)
    if not protocol:
        raise HTTPException(status_code=404, detail=f"Protocol not found: {protocol_id}")

    # Get protocol name from filename (without .pdf extension)
    protocol_name = protocol.filename.replace('.pdf', '') if protocol.filename else None
    if not protocol_name:
        raise HTTPException(status_code=400, detail="Protocol has no filename")

    # Look for eligibility output directory
    project_root = Path(__file__).parent.parent.parent

    # Extract potential folder names from protocol name
    # e.g., "Prot_000 ACP-044-004" -> ["Prot_000 ACP-044-004", "ACP-044-004"]
    protocol_variants = [protocol_name]
    if '_' in protocol_name:
        # Add the part after the last underscore-number pattern
        parts = protocol_name.split(' ')
        for part in parts:
            if part != protocol_name:
                protocol_variants.append(part)
        # Also try the last part after splitting by space
        if len(parts) > 1:
            protocol_variants.append(parts[-1])

    # Try multiple possible locations for the protocol folder
    possible_paths = []
    protocols_dir = project_root / "protocols"

    for variant in protocol_variants:
        # Direct path: protocols/{variant}/eligibility_output
        possible_paths.append(protocols_dir / variant / "eligibility_output")

    # Also search for any folder containing the protocol name variants
    if protocols_dir.exists():
        for subdir in protocols_dir.iterdir():
            if subdir.is_dir():
                for variant in protocol_variants:
                    # Check direct: protocols/subdir/{variant}/eligibility_output
                    eligibility_dir = subdir / variant / "eligibility_output"
                    if eligibility_dir.exists():
                        possible_paths.insert(0, eligibility_dir)

                # Also check nested folders that contain any variant
                for nested in subdir.iterdir():
                    if nested.is_dir():
                        nested_name = nested.name
                        # Check if any variant matches or is contained in folder name
                        for variant in protocol_variants:
                            if variant in nested_name or nested_name in variant:
                                eligibility_dir = nested / "eligibility_output"
                                if eligibility_dir.exists():
                                    possible_paths.insert(0, eligibility_dir)
                                break

    eligibility_dir = None
    for path in possible_paths:
        if path and path.exists():
            eligibility_dir = path
            break

    if not eligibility_dir or not eligibility_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Eligibility output not found for protocol: {protocol_name}"
        )

    # Find the latest timestamp directory
    timestamp_dirs = sorted(
        [d for d in eligibility_dir.iterdir() if d.is_dir()],
        key=lambda x: x.name,
        reverse=True
    )

    if not timestamp_dirs:
        raise HTTPException(
            status_code=404,
            detail=f"No eligibility analysis results found for protocol: {protocol_name}"
        )

    latest_dir = timestamp_dirs[0]

    # First, try to find QEB output file (processed data for wizard view)
    qeb_files = list(latest_dir.glob("*qeb_output.json"))
    if qeb_files:
        try:
            with open(qeb_files[0], 'r', encoding='utf-8') as f:
                qeb_data = json.load(f)
            # Return QEB data directly - it has the full structure needed by frontend
            return qeb_data
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse QEB output: {e}, falling back to criteria file")

    # Fallback: Look for eligibility_criteria.json file
    criteria_files = list(latest_dir.glob("*eligibility_criteria.json"))
    if not criteria_files:
        raise HTTPException(
            status_code=404,
            detail=f"No eligibility data found in {latest_dir}"
        )

    criteria_file = criteria_files[0]

    try:
        with open(criteria_file, 'r', encoding='utf-8') as f:
            eligibility_data = json.load(f)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse eligibility data: {e}")

    # Also try to load funnel data if available
    funnel_data = None
    funnel_files = list(latest_dir.glob("*eligibility_funnel.json"))
    if funnel_files:
        try:
            with open(funnel_files[0], 'r', encoding='utf-8') as f:
                funnel_data = json.load(f)
        except:
            pass

    return {
        "protocolId": protocol_name,
        "criteria": eligibility_data.get("criteria", []),
        "funnel": funnel_data,
        "outputDir": str(latest_dir),
        "generatedAt": latest_dir.name,
    }
