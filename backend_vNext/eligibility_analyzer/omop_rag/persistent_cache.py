"""
Persistent Disk Cache for OMOP RAG Mapping Results.

SQLite-backed cache that persists OMOP concept mapping results across pipeline runs.
Terms that map to the same concept don't need re-embedding or re-searching.

Cache location: .cache/eligibility/omop_mapping_cache.db
"""

import hashlib
import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / ".cache" / "eligibility"
CACHE_DB_PATH = CACHE_DIR / "omop_mapping_cache.db"
DEFAULT_TTL_DAYS = 30
VECTOR_STORE_VERSION = "1.0"


class OMOPMappingDiskCache:
    """
    SQLite-backed persistent cache for OMOP mapping results.

    - Term-level caching shared across protocols
    - TTL-based expiration (default 30 days)
    - Vector store version tracking for invalidation
    - Batch get/set for efficiency
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        ttl_days: int = DEFAULT_TTL_DAYS,
        vector_store_version: str = VECTOR_STORE_VERSION,
    ):
        self.db_path = db_path or CACHE_DB_PATH
        self.ttl_days = ttl_days
        self.vector_store_version = vector_store_version
        self._ensure_dir()
        self._init_db()

    def _ensure_dir(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mapping_cache (
                cache_key TEXT PRIMARY KEY,
                term TEXT NOT NULL,
                domain_hint TEXT,
                result_json TEXT NOT NULL,
                concept_id INTEGER,
                concept_name TEXT,
                confidence REAL,
                source TEXT,
                vector_store_version TEXT,
                created_at TEXT NOT NULL,
                ttl_days INTEGER NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cache_term ON mapping_cache(term)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cache_created ON mapping_cache(created_at)"
        )
        conn.commit()
        conn.close()

    @staticmethod
    def _make_key(term: str, domain_hint: Optional[str] = None) -> str:
        normalized = term.lower().strip()
        combined = f"{normalized}|{(domain_hint or '').lower()}"
        return hashlib.sha256(combined.encode()).hexdigest()[:32]

    def _result_to_dict(self, result) -> Dict[str, Any]:
        """Serialize MappingResult to a storable dict."""
        # Strip disk_cache() wrapper from source if re-saving
        source = result.source
        if source.startswith("disk_cache("):
            source = source[len("disk_cache("):-1]

        return {
            "term": result.term,
            "concept_id": result.concept_id,
            "concept_name": result.concept_name,
            "concept_code": result.concept_code,
            "vocabulary_id": result.vocabulary_id,
            "domain_id": result.domain_id,
            "standard_concept": result.standard_concept,
            "confidence": result.confidence,
            "source": source,
            "match_type": result.match_type,
            "is_mapped": result.is_mapped,
            "candidates": result.candidates[:3] if result.candidates else [],
            "validation_reason": result.validation_reason,
            "processing_time_ms": 0.0,
        }

    def get(self, term: str, domain_hint: Optional[str] = None):
        """Get cached mapping result. Returns None if not cached, expired, or version mismatch."""
        from .rag_mapper import MappingResult

        key = self._make_key(term, domain_hint)
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM mapping_cache WHERE cache_key = ?", (key,)
            ).fetchone()
            conn.close()

            if not row:
                return None

            created = datetime.fromisoformat(row["created_at"])
            if datetime.now() > created + timedelta(days=row["ttl_days"]):
                self._delete_key(key)
                return None

            if row["vector_store_version"] != self.vector_store_version:
                self._delete_key(key)
                return None

            d = json.loads(row["result_json"])
            return MappingResult(
                term=d["term"],
                concept_id=d.get("concept_id"),
                concept_name=d.get("concept_name"),
                concept_code=d.get("concept_code"),
                vocabulary_id=d.get("vocabulary_id"),
                domain_id=d.get("domain_id"),
                standard_concept=d.get("standard_concept"),
                confidence=d.get("confidence", 0.0),
                source=d.get("source", "unmapped"),
                match_type=d.get("match_type", "none"),
                is_mapped=d.get("is_mapped", False),
                candidates=d.get("candidates", []),
                validation_reason=d.get("validation_reason"),
                processing_time_ms=0.0,
            )

        except Exception as e:
            logger.warning(f"Disk cache get error for '{term}': {e}")
            return None

    def set(self, term: str, domain_hint: Optional[str], result) -> None:
        """Store mapping result in cache."""
        key = self._make_key(term, domain_hint)
        try:
            result_dict = self._result_to_dict(result)
            conn = sqlite3.connect(str(self.db_path))
            conn.execute(
                """INSERT OR REPLACE INTO mapping_cache
                   (cache_key, term, domain_hint, result_json,
                    concept_id, concept_name, confidence, source,
                    vector_store_version, created_at, ttl_days)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    key,
                    term.lower().strip(),
                    domain_hint,
                    json.dumps(result_dict),
                    result.concept_id,
                    result.concept_name,
                    result.confidence,
                    result_dict["source"],
                    self.vector_store_version,
                    datetime.now().isoformat(),
                    self.ttl_days,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Disk cache set error for '{term}': {e}")

    def set_batch(self, entries: list) -> None:
        """Batch store: list of (term, domain_hint, MappingResult) tuples."""
        if not entries:
            return
        try:
            conn = sqlite3.connect(str(self.db_path))
            now = datetime.now().isoformat()
            for term, dh, result in entries:
                key = self._make_key(term, dh)
                result_dict = self._result_to_dict(result)
                conn.execute(
                    """INSERT OR REPLACE INTO mapping_cache
                       (cache_key, term, domain_hint, result_json,
                        concept_id, concept_name, confidence, source,
                        vector_store_version, created_at, ttl_days)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        key,
                        term.lower().strip(),
                        dh,
                        json.dumps(result_dict),
                        result.concept_id,
                        result.concept_name,
                        result.confidence,
                        result_dict["source"],
                        self.vector_store_version,
                        now,
                        self.ttl_days,
                    ),
                )
            conn.commit()
            conn.close()
            logger.info(f"Disk cache: stored {len(entries)} mapping results")
        except Exception as e:
            logger.error(f"Disk cache batch set error: {e}")

    def _delete_key(self, key: str) -> None:
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("DELETE FROM mapping_cache WHERE cache_key = ?", (key,))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def invalidate_all(self) -> int:
        try:
            conn = sqlite3.connect(str(self.db_path))
            count = conn.execute("SELECT COUNT(*) FROM mapping_cache").fetchone()[0]
            conn.execute("DELETE FROM mapping_cache")
            conn.commit()
            conn.close()
            logger.info(f"Invalidated {count} disk cache entries")
            return count
        except Exception as e:
            logger.error(f"Invalidate all failed: {e}")
            return 0

    def cleanup_expired(self) -> int:
        try:
            conn = sqlite3.connect(str(self.db_path))
            cur = conn.execute(
                "DELETE FROM mapping_cache "
                "WHERE datetime(created_at, '+' || ttl_days || ' days') < datetime('now')"
            )
            count = cur.rowcount
            conn.commit()
            conn.close()
            if count:
                logger.info(f"Cleaned up {count} expired disk cache entries")
            return count
        except Exception:
            return 0

    def stats(self) -> Dict[str, Any]:
        try:
            conn = sqlite3.connect(str(self.db_path))
            total = conn.execute("SELECT COUNT(*) FROM mapping_cache").fetchone()[0]
            by_source = dict(
                conn.execute(
                    "SELECT source, COUNT(*) FROM mapping_cache GROUP BY source"
                ).fetchall()
            )
            avg_conf = (
                conn.execute(
                    "SELECT AVG(confidence) FROM mapping_cache WHERE confidence > 0"
                ).fetchone()[0]
                or 0.0
            )
            conn.close()
            return {
                "total_entries": total,
                "by_source": by_source,
                "avg_confidence": round(avg_conf, 3),
                "db_path": str(self.db_path),
                "ttl_days": self.ttl_days,
                "vector_store_version": self.vector_store_version,
            }
        except Exception:
            return {"total_entries": 0, "error": "Failed to read stats"}


_disk_cache_instance: Optional[OMOPMappingDiskCache] = None


def get_omop_disk_cache(**kwargs) -> OMOPMappingDiskCache:
    """Get or create the singleton disk cache."""
    global _disk_cache_instance
    if _disk_cache_instance is None:
        _disk_cache_instance = OMOPMappingDiskCache(**kwargs)
    return _disk_cache_instance
