"""
Extraction Cache Utility

Database-backed caching for two-phase extraction results with file-based fallback.
Cache invalidates automatically when any component changes:
- PDF content (hash of file)
- Module name
- Prompt templates (hash of pass1 + pass2 prompts)
- JSON Schema (hash of schema file)
- Model name

Primary storage: PostgreSQL database (public.extraction_cache table)
Fallback: File-based cache in backend_vNext/.cache/ (if DB unavailable)
"""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional, Dict, Union
from datetime import datetime
import uuid
from uuid import UUID

logger = logging.getLogger(__name__)

# Cache directory relative to backend_vNext (fallback)
CACHE_DIR = Path(__file__).parent.parent.parent / ".cache"


def _compute_file_hash(file_path: str, max_bytes: int = 1024 * 1024) -> str:
    """Compute SHA256 hash of a file (first max_bytes for large files)."""
    hasher = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            # For PDFs, read first 1MB to speed up hashing
            data = f.read(max_bytes)
            hasher.update(data)
            # Also include file size for uniqueness
            f.seek(0, 2)  # Seek to end
            hasher.update(str(f.tell()).encode())
    except Exception as e:
        logger.warning(f"Could not hash file {file_path}: {e}")
        return "unknown"
    return hasher.hexdigest()[:16]


def _compute_text_hash(text: str) -> str:
    """Compute SHA256 hash of text content."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _load_prompt(prompt_path: str) -> str:
    """Load prompt text from file."""
    try:
        with open(prompt_path, 'r') as f:
            return f.read()
    except Exception:
        return ""


def _load_schema(schema_path: str) -> str:
    """Load schema JSON as string."""
    try:
        with open(schema_path, 'r') as f:
            return f.read()
    except Exception:
        return ""


class ExtractionCache:
    """
    Database-backed extraction result cache with file fallback.

    Cache key components:
    - PDF hash (first 1MB + file size, SHA256)
    - Module name
    - Pass 1 prompt hash
    - Pass 2 prompt hash
    - Schema hash
    - Model name

    Usage:
        cache = ExtractionCache()

        # Check for cached result
        result = cache.get(pdf_path, module_name, pass1_prompt, pass2_prompt, schema_path, model)
        if result:
            return result  # Cache hit!

        # Run extraction...
        result = extractor.extract(...)

        # Store in cache
        cache.set(pdf_path, module_name, pass1_prompt, pass2_prompt, schema_path, model, result)
    """

    def __init__(self, cache_dir: Optional[Path] = None, use_database: bool = True):
        """Initialize cache with optional custom directory."""
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_database = use_database
        self._db_available = None  # Lazy check
        logger.info(f"Extraction cache initialized (DB: {use_database}, fallback dir: {self.cache_dir})")

    def _is_db_available(self) -> bool:
        """Check if database is available (cached result)."""
        if self._db_available is not None:
            return self._db_available

        if not self.use_database:
            self._db_available = False
            return False

        try:
            from sqlalchemy import text
            from app.db import get_engine
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            self._db_available = True
            logger.info("Database cache enabled")
        except Exception as e:
            logger.warning(f"Database unavailable, using file fallback: {e}")
            self._db_available = False

        return self._db_available

    def _build_cache_key(
        self,
        pdf_path: str,
        module_name: str,
        pass1_prompt_path: str,
        pass2_prompt_path: str,
        schema_path: str,
        model_name: str
    ) -> Dict[str, str]:
        """Build cache key components from all inputs."""
        pdf_hash = _compute_file_hash(pdf_path)
        pass1_hash = _compute_text_hash(_load_prompt(pass1_prompt_path))
        pass2_hash = _compute_text_hash(_load_prompt(pass2_prompt_path))
        schema_hash = _compute_text_hash(_load_schema(schema_path))
        model_hash = _compute_text_hash(model_name)[:8]

        # Combined prompt hash for DB storage
        prompt_hash = _compute_text_hash(f"{pass1_hash}_{pass2_hash}_{schema_hash}")

        return {
            "pdf_hash": pdf_hash,
            "module_id": module_name,
            "model_name": model_name,
            "prompt_hash": prompt_hash,
            "file_key": f"{module_name}_{pdf_hash}_{prompt_hash[:8]}_{model_hash}"
        }

    def _get_cache_path(self, file_key: str) -> Path:
        """Get the file path for a cache key."""
        return self.cache_dir / f"{file_key}.json"

    def _get_from_db(self, key: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Get cached result from database."""
        try:
            from sqlalchemy import text
            from app.db import get_engine

            engine = get_engine()
            with engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT extracted_data, quality_score, pdf_path, cache_hits, created_at, protocol_id
                        FROM public.extraction_cache
                        WHERE pdf_hash = :pdf_hash
                          AND module_id = :module_id
                          AND model_name = :model_name
                          AND prompt_hash = :prompt_hash
                    """),
                    {
                        "pdf_hash": key["pdf_hash"],
                        "module_id": key["module_id"],
                        "model_name": key["model_name"],
                        "prompt_hash": key["prompt_hash"]
                    }
                ).fetchone()

                if result:
                    # Update accessed_at and cache_hits
                    conn.execute(
                        text("""
                            UPDATE public.extraction_cache
                            SET accessed_at = NOW(), cache_hits = cache_hits + 1
                            WHERE pdf_hash = :pdf_hash
                              AND module_id = :module_id
                              AND model_name = :model_name
                              AND prompt_hash = :prompt_hash
                        """),
                        {
                            "pdf_hash": key["pdf_hash"],
                            "module_id": key["module_id"],
                            "model_name": key["model_name"],
                            "prompt_hash": key["prompt_hash"]
                        }
                    )
                    conn.commit()

                    return {
                        "data": result[0],  # extracted_data (JSONB)
                        "metadata": {
                            "module_name": key["module_id"],
                            "model_name": key["model_name"],
                            "pdf_path": result[2],
                            "cached_at": result[4].isoformat() if result[4] else None,
                            "quality_score": result[1],
                            "cache_hits": result[3] + 1,
                            "protocol_id": str(result[5]) if result[5] else None,
                            "source": "database"
                        }
                    }
                return None
        except Exception as e:
            logger.warning(f"Database cache read error: {e}")
            return None

    def _set_to_db(
        self,
        key: Dict[str, str],
        pdf_path: str,
        result: Dict[str, Any],
        quality_score: Optional[Dict[str, Any]] = None,
        protocol_id: Optional[Union[str, UUID]] = None
    ) -> bool:
        """Store result in database cache."""
        try:
            from sqlalchemy import text
            from app.db import get_engine

            engine = get_engine()
            with engine.connect() as conn:
                # Use upsert (INSERT ... ON CONFLICT UPDATE)
                conn.execute(
                    text("""
                        INSERT INTO public.extraction_cache
                            (id, module_id, model_name, pdf_hash, prompt_hash, extracted_data, quality_score, pdf_path, protocol_id)
                        VALUES
                            (:id, :module_id, :model_name, :pdf_hash, :prompt_hash, :extracted_data, :quality_score, :pdf_path, :protocol_id)
                        ON CONFLICT (pdf_hash, module_id, model_name, prompt_hash)
                        DO UPDATE SET
                            extracted_data = EXCLUDED.extracted_data,
                            quality_score = EXCLUDED.quality_score,
                            pdf_path = EXCLUDED.pdf_path,
                            protocol_id = EXCLUDED.protocol_id,
                            accessed_at = NOW()
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "module_id": key["module_id"],
                        "model_name": key["model_name"],
                        "pdf_hash": key["pdf_hash"],
                        "prompt_hash": key["prompt_hash"],
                        "extracted_data": json.dumps(result),
                        "quality_score": json.dumps(quality_score) if quality_score else None,
                        "pdf_path": pdf_path,
                        "protocol_id": str(protocol_id) if protocol_id else None  # Convert UUID to string for DB
                    }
                )
                conn.commit()
                logger.debug(f"Successfully wrote to DB cache: module_id={key['module_id']}, protocol_id={protocol_id}")
                return True
        except Exception as e:
            logger.error(f"Database cache write error for module {key['module_id']}: {type(e).__name__}: {e}", exc_info=True)
            return False

    def _get_from_file(self, file_key: str) -> Optional[Dict[str, Any]]:
        """Get cached result from file."""
        cache_path = self._get_cache_path(file_key)
        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    cached = json.load(f)
                    if "metadata" not in cached:
                        cached["metadata"] = {}
                    cached["metadata"]["source"] = "file"
                    return cached
            except Exception as e:
                logger.warning(f"File cache read error for {file_key}: {e}")
        return None

    def _set_to_file(
        self,
        file_key: str,
        pdf_path: str,
        module_name: str,
        model_name: str,
        result: Dict[str, Any],
        quality_score: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Store result in file cache."""
        cache_path = self._get_cache_path(file_key)
        cache_entry = {
            "data": result,
            "metadata": {
                "module_name": module_name,
                "model_name": model_name,
                "pdf_path": pdf_path,
                "cached_at": datetime.now().isoformat(),
                "quality_score": quality_score,
                "source": "file"
            }
        }
        try:
            with open(cache_path, 'w') as f:
                json.dump(cache_entry, f, indent=2, default=str)
            return True
        except Exception as e:
            logger.warning(f"File cache write error for {file_key}: {e}")
            return False

    def get(
        self,
        pdf_path: str,
        module_name: str,
        pass1_prompt_path: str,
        pass2_prompt_path: str,
        schema_path: str,
        model_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached extraction result if available.

        Returns:
            Cached result dict with 'data' and 'metadata' keys, or None if cache miss.
        """
        key = self._build_cache_key(
            pdf_path, module_name, pass1_prompt_path, pass2_prompt_path, schema_path, model_name
        )

        # Try database only (filesystem cache disabled)
        if self._is_db_available():
            result = self._get_from_db(key)
            if result:
                logger.info(f"Cache HIT (DB) for {module_name} (pdf_hash: {key['pdf_hash']})")
                return result

        # Filesystem cache disabled - database only
        # (Removed file cache fallback to ensure fresh extractions use DB cache)

        logger.info(f"Cache MISS for {module_name} (pdf_hash: {key['pdf_hash']})")
        return None

    def set(
        self,
        pdf_path: str,
        module_name: str,
        pass1_prompt_path: str,
        pass2_prompt_path: str,
        schema_path: str,
        model_name: str,
        result: Dict[str, Any],
        quality_score: Optional[Dict[str, Any]] = None,
        protocol_id: Optional[Union[str, UUID]] = None
    ) -> str:
        """
        Store extraction result in cache.

        Args:
            result: The extraction result data
            quality_score: Optional quality score metadata
            protocol_id: Optional protocol UUID for linking cache to protocol

        Returns:
            The cache key used
        """
        key = self._build_cache_key(
            pdf_path, module_name, pass1_prompt_path, pass2_prompt_path, schema_path, model_name
        )

        # Try database only (filesystem cache disabled)
        db_success = False
        if self._is_db_available():
            db_success = self._set_to_db(key, pdf_path, result, quality_score, protocol_id)
            if db_success:
                logger.info(f"Cached (DB) {module_name} result (pdf_hash: {key['pdf_hash']}, protocol_id: {protocol_id})")

        # Filesystem cache disabled - database only
        # (Removed file cache write to use DB as single source of truth)
        if not db_success:
            logger.warning(f"Failed to cache {module_name} result - database unavailable")

        return key["file_key"]

    def invalidate(self, module_name: Optional[str] = None, pdf_hash: Optional[str] = None) -> int:
        """
        Invalidate cached entries.

        Args:
            module_name: If provided, only invalidate entries for this module.
            pdf_hash: If provided, only invalidate entries for this PDF.
                      If both None, invalidate all entries.

        Returns:
            Number of entries invalidated.
        """
        count = 0

        # Invalidate from database
        if self._is_db_available():
            try:
                from sqlalchemy import text
                from app.db import get_engine

                engine = get_engine()
                with engine.connect() as conn:
                    if module_name and pdf_hash:
                        result = conn.execute(
                            text("""
                                DELETE FROM public.extraction_cache
                                WHERE module_id = :module_id AND pdf_hash = :pdf_hash
                            """),
                            {"module_id": module_name, "pdf_hash": pdf_hash}
                        )
                    elif module_name:
                        result = conn.execute(
                            text("""
                                DELETE FROM public.extraction_cache
                                WHERE module_id = :module_id
                            """),
                            {"module_id": module_name}
                        )
                    elif pdf_hash:
                        result = conn.execute(
                            text("""
                                DELETE FROM public.extraction_cache
                                WHERE pdf_hash = :pdf_hash
                            """),
                            {"pdf_hash": pdf_hash}
                        )
                    else:
                        result = conn.execute(
                            text("DELETE FROM public.extraction_cache")
                        )
                    conn.commit()
                    count += result.rowcount
            except Exception as e:
                logger.warning(f"Database cache invalidation error: {e}")

        # Filesystem cache disabled - database only
        # (Removed file cache invalidation)

        if count > 0:
            msg = f"Invalidated {count} cache entries"
            if module_name:
                msg += f" for module {module_name}"
            if pdf_hash:
                msg += f" for pdf_hash {pdf_hash}"
            logger.info(msg)
        return count

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics from both database and file system."""
        stats = {
            "database": {"available": False, "entries": 0, "total_hits": 0},
            "file": {"entries": 0, "total_size_mb": 0.0},
            "entries_by_module": {}
        }

        # Database stats
        if self._is_db_available():
            try:
                from sqlalchemy import text
                from app.db import get_engine

                engine = get_engine()
                with engine.connect() as conn:
                    # Total entries and hits
                    result = conn.execute(
                        text("""
                            SELECT COUNT(*), COALESCE(SUM(cache_hits), 0)
                            FROM public.extraction_cache
                        """)
                    ).fetchone()
                    stats["database"]["available"] = True
                    stats["database"]["entries"] = result[0]
                    stats["database"]["total_hits"] = result[1]

                    # By module
                    modules = conn.execute(
                        text("""
                            SELECT module_id, COUNT(*), SUM(cache_hits)
                            FROM public.extraction_cache
                            GROUP BY module_id
                        """)
                    ).fetchall()
                    for row in modules:
                        stats["entries_by_module"][row[0]] = {
                            "db_entries": row[1],
                            "db_hits": row[2] or 0
                        }
            except Exception as e:
                logger.warning(f"Database stats error: {e}")

        # File stats
        file_entries = list(self.cache_dir.glob("*.json"))
        stats["file"]["entries"] = len(file_entries)
        stats["file"]["total_size_mb"] = round(
            sum(f.stat().st_size for f in file_entries) / (1024 * 1024), 2
        )
        stats["file"]["cache_dir"] = str(self.cache_dir)

        # Group file entries by module
        for f in file_entries:
            module = f.name.split("_")[0]
            if module not in stats["entries_by_module"]:
                stats["entries_by_module"][module] = {}
            stats["entries_by_module"][module]["file_entries"] = \
                stats["entries_by_module"].get(module, {}).get("file_entries", 0) + 1

        return stats


# Singleton instance for convenience
_cache_instance: Optional[ExtractionCache] = None


def get_cache() -> ExtractionCache:
    """Get the singleton cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = ExtractionCache()
    return _cache_instance
