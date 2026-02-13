"""
Gemini File API service for PDF upload and caching.

Handles:
- PDF upload to Gemini File API
- 48-hour file caching
- File reference management
- Retry logic with exponential backoff for transient errors
"""

import asyncio
import hashlib
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, Union
import time
import tempfile
import os
from uuid import UUID

import google.generativeai as genai
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Protocol

logger = logging.getLogger(__name__)


# Error patterns that indicate transient/retryable errors
RETRYABLE_ERROR_PATTERNS = (
    "503",
    "ServiceUnavailable",
    "service unavailable",
    "Connection reset",
    "connection reset",
    "recvmsg",
    "429",
    "ResourceExhausted",
    "resource exhausted",
    "rate limit",
    "quota",
    "504",
    "DeadlineExceeded",
    "deadline exceeded",
    "timeout",
    "Timeout",
    "Connection refused",
    "connection refused",
    "temporarily unavailable",
    "UNAVAILABLE",
    "overloaded",
)

# Error patterns that indicate non-retryable errors (fail fast)
NON_RETRYABLE_ERROR_PATTERNS = (
    "401",
    "Unauthorized",
    "unauthorized",
    "403",
    "Forbidden",
    "forbidden",
    "400",
    "Bad Request",
    "bad request",
    "InvalidArgument",
    "invalid argument",
    "PermissionDenied",
    "permission denied",
)


def _is_retryable_error(error: Exception) -> bool:
    """
    Check if an error is retryable (transient) or should fail fast.

    Args:
        error: The exception to check

    Returns:
        True if the error is retryable, False otherwise
    """
    error_str = str(error)

    # Check for non-retryable patterns first (fail fast)
    for pattern in NON_RETRYABLE_ERROR_PATTERNS:
        if pattern in error_str:
            return False

    # Check for retryable patterns
    for pattern in RETRYABLE_ERROR_PATTERNS:
        if pattern in error_str:
            return True

    # Default: treat unknown errors as non-retryable to avoid masking bugs
    return False


def _calculate_backoff_delay(attempt: int) -> float:
    """
    Calculate exponential backoff delay with jitter.

    Args:
        attempt: Current attempt number (0-indexed)

    Returns:
        Delay in seconds
    """
    base_delay = settings.api_retry_base_delay
    max_delay = settings.api_retry_max_delay
    exponential_base = settings.api_retry_exponential_base

    # Exponential backoff: base_delay * (exponential_base ^ attempt)
    delay = base_delay * (exponential_base ** attempt)

    # Cap at max delay
    delay = min(delay, max_delay)

    # Add jitter (0-1 second) to prevent thundering herd
    jitter = random.uniform(0, 1)

    return delay + jitter


class GeminiFileService:
    """Service for managing PDF files with Gemini File API."""

    # File cache duration (48 hours per Gemini API)
    CACHE_DURATION_HOURS = 48

    def __init__(self):
        """Initialize Gemini API client."""
        genai.configure(api_key=settings.gemini_api_key)
        self._model = None

    @property
    def model(self):
        """Get or create Gemini model instance."""
        if self._model is None:
            self._model = genai.GenerativeModel(settings.gemini_model)
        return self._model

    def compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA-256 hash of file for deduplication."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def compute_hash_from_bytes(self, file_data: bytes) -> str:
        """Compute SHA-256 hash from binary data."""
        return hashlib.sha256(file_data).hexdigest()

    async def get_or_upload_file_from_protocol(
        self,
        protocol_id: UUID,
        db: Session
    ) -> Tuple[str, Protocol]:
        """
        Get cached Gemini file URI or upload from protocol stored in database.

        This method retrieves the PDF binary data from the database and uploads
        it to Gemini File API if not already cached.

        Args:
            protocol_id: UUID of the protocol
            db: Database session

        Returns:
            Tuple of (gemini_file_uri, protocol_record)
        """
        # Get protocol from database
        protocol = db.query(Protocol).filter(Protocol.id == protocol_id).first()
        if not protocol:
            raise ValueError(f"Protocol {protocol_id} not found in database")

        # Check if Gemini cache is still valid
        if protocol.gemini_file_uri and self._is_cache_valid(protocol):
            logger.info(f"Using cached Gemini file: {protocol.gemini_file_uri}")
            return protocol.gemini_file_uri, protocol

        # Get PDF data (prefer database, fallback to filesystem)
        pdf_data = None
        temp_file_path = None

        if protocol.file_data:
            # Have binary data in database
            pdf_data = protocol.file_data
            logger.info(f"Using PDF data from database ({len(pdf_data)} bytes)")
        elif protocol.file_path and Path(protocol.file_path).exists():
            # Fallback to filesystem
            with open(protocol.file_path, 'rb') as f:
                pdf_data = f.read()
            logger.info(f"Using PDF data from filesystem ({len(pdf_data)} bytes)")
        else:
            raise ValueError(f"No PDF data found for protocol {protocol_id}")

        # Create temporary file for Gemini upload (Gemini API requires file path)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_data)
            temp_file_path = tmp.name

        try:
            # Upload to Gemini
            logger.info(f"Uploading PDF to Gemini File API: {protocol.filename}")
            gemini_file = await self._upload_to_gemini(Path(temp_file_path))

            # Update protocol with Gemini URI
            expires_at = datetime.utcnow() + timedelta(hours=self.CACHE_DURATION_HOURS)
            protocol.gemini_file_uri = gemini_file.uri
            protocol.gemini_file_expires_at = expires_at
            db.commit()
            db.refresh(protocol)

            logger.info(f"Uploaded file with URI: {gemini_file.uri}")
            return gemini_file.uri, protocol

        finally:
            # Clean up temp file
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                logger.debug(f"Deleted temp file: {temp_file_path}")

    async def get_or_upload_file(
        self,
        file_path: Path,
        db: Session
    ) -> Tuple[str, Protocol]:
        """
        Get cached Gemini file URI or upload new file.

        Returns:
            Tuple of (gemini_file_uri, protocol_record)
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        # Compute file hash
        file_hash = self.compute_file_hash(file_path)
        logger.info(f"File hash: {file_hash}")

        # Check if file already cached in database
        protocol = db.query(Protocol).filter(Protocol.file_hash == file_hash).first()

        if protocol and self._is_cache_valid(protocol):
            logger.info(f"Using cached Gemini file: {protocol.gemini_file_uri}")
            return protocol.gemini_file_uri, protocol

        # Upload to Gemini File API
        logger.info(f"Uploading PDF to Gemini File API: {file_path.name}")
        gemini_file = await self._upload_to_gemini(file_path)

        # Calculate expiry time
        expires_at = datetime.utcnow() + timedelta(hours=self.CACHE_DURATION_HOURS)

        if protocol:
            # Update existing record
            protocol.gemini_file_uri = gemini_file.uri
            protocol.gemini_file_expires_at = expires_at
            protocol.file_path = str(file_path)
        else:
            # Create new record
            protocol = Protocol(
                filename=file_path.name,
                file_hash=file_hash,
                file_path=str(file_path),
                gemini_file_uri=gemini_file.uri,
                gemini_file_expires_at=expires_at,
            )
            db.add(protocol)

        db.commit()
        db.refresh(protocol)

        logger.info(f"Uploaded file with URI: {gemini_file.uri}")
        return gemini_file.uri, protocol

    def _is_cache_valid(self, protocol: Protocol) -> bool:
        """Check if cached Gemini file URI is still valid."""
        if not protocol.gemini_file_uri or not protocol.gemini_file_expires_at:
            return False

        # Add 1 hour buffer before expiry
        buffer = timedelta(hours=1)
        return datetime.utcnow() < (protocol.gemini_file_expires_at - buffer)

    async def _upload_to_gemini(self, file_path: Path):
        """Upload file to Gemini File API."""
        # Gemini upload_file is synchronous
        gemini_file = genai.upload_file(
            path=str(file_path),
            display_name=file_path.name,
        )

        # Wait for file to be processed
        while gemini_file.state.name == "PROCESSING":
            logger.info("Waiting for Gemini to process file...")
            time.sleep(2)
            gemini_file = genai.get_file(gemini_file.name)

        if gemini_file.state.name == "FAILED":
            raise RuntimeError(f"Gemini file processing failed: {gemini_file.name}")

        return gemini_file

    async def generate_content(
        self,
        gemini_file_uri: str,
        prompt: str,
        max_output_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate content using Gemini with uploaded file.

        Includes retry logic with exponential backoff for transient errors
        (503, 429, connection resets, timeouts).

        Args:
            gemini_file_uri: URI of uploaded file
            prompt: Prompt to send with file
            max_output_tokens: Maximum output tokens (default from settings)

        Returns:
            Generated text content

        Raises:
            RuntimeError: If no content generated after all retries
            Exception: If a non-retryable error occurs
        """
        max_attempts = settings.api_retry_max_attempts
        last_error: Optional[Exception] = None

        for attempt in range(max_attempts):
            try:
                # Get file reference
                gemini_file = genai.get_file(gemini_file_uri.split("/")[-1])

                # Configure generation
                generation_config = genai.GenerationConfig(
                    max_output_tokens=max_output_tokens or settings.gemini_max_output_tokens,
                    temperature=0.1,  # Low temperature for consistent extraction
                )

                # Generate content
                response = self.model.generate_content(
                    [gemini_file, prompt],
                    generation_config=generation_config,
                )

                # Extract text from response
                if response.candidates and response.candidates[0].content.parts:
                    if attempt > 0:
                        logger.info(f"API call succeeded on attempt {attempt + 1}")
                    return response.candidates[0].content.parts[0].text

                # Empty response - treat as retryable
                raise RuntimeError("No content generated by Gemini")

            except Exception as e:
                last_error = e

                # Check if error is retryable
                if not _is_retryable_error(e):
                    logger.error(f"Non-retryable error (failing fast): {e}")
                    raise

                # Check if we have more attempts
                if attempt >= max_attempts - 1:
                    logger.error(
                        f"Max retries ({max_attempts}) exhausted. Last error: {e}"
                    )
                    raise

                # Calculate backoff delay
                delay = _calculate_backoff_delay(attempt)
                logger.warning(
                    f"Retryable error on attempt {attempt + 1}/{max_attempts}: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )

                # Wait before retry
                await asyncio.sleep(delay)

        # Should not reach here, but just in case
        if last_error:
            raise last_error
        raise RuntimeError("Unexpected state: no response and no error")

    def delete_file(self, gemini_file_uri: str) -> bool:
        """
        Delete file from Gemini File API.

        Args:
            gemini_file_uri: URI of file to delete

        Returns:
            True if deleted successfully
        """
        try:
            file_name = gemini_file_uri.split("/")[-1]
            genai.delete_file(file_name)
            logger.info(f"Deleted Gemini file: {file_name}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete Gemini file: {e}")
            return False
