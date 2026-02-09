"""
SOA Pipeline Cache

Version-aware caching for SOA extraction pipeline stages.
Cache invalidates automatically when any component changes:
- PDF content (hash of file)
- Stage name
- Config settings
- Prompt templates (when applicable)
- Model name

Cache location: soa_analyzer/.cache/soa/

Usage:
    from soa_analyzer.soa_cache import SOACache, get_soa_cache

    cache = get_soa_cache()

    # Check cache
    result = cache.get(pdf_path, "detection", model="gemini-2.5-pro")
    if result:
        return result["data"]  # Cache hit!

    # Store result
    cache.set(pdf_path, "detection", data, model="gemini-2.5-pro")
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cache directory relative to soa_analyzer
CACHE_DIR = Path(__file__).parent / ".cache" / "soa"

# Default TTL in days
DEFAULT_TTL_DAYS = 30


@dataclass
class CacheEntry:
    """Represents a cached result with metadata."""
    data: Any
    stage: str
    pdf_path: str
    pdf_hash: str
    model: Optional[str]
    config_hash: Optional[str]
    prompt_hash: Optional[str]
    created_at: datetime
    ttl_days: int

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        expiry = self.created_at + timedelta(days=self.ttl_days)
        return datetime.now() > expiry

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "data": self.data,
            "metadata": {
                "stage": self.stage,
                "pdf_path": self.pdf_path,
                "pdf_hash": self.pdf_hash,
                "model": self.model,
                "config_hash": self.config_hash,
                "prompt_hash": self.prompt_hash,
                "created_at": self.created_at.isoformat(),
                "ttl_days": self.ttl_days,
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheEntry":
        """Create from dictionary."""
        metadata = data["metadata"]
        return cls(
            data=data["data"],
            stage=metadata["stage"],
            pdf_path=metadata["pdf_path"],
            pdf_hash=metadata["pdf_hash"],
            model=metadata.get("model"),
            config_hash=metadata.get("config_hash"),
            prompt_hash=metadata.get("prompt_hash"),
            created_at=datetime.fromisoformat(metadata["created_at"]),
            ttl_days=metadata.get("ttl_days", DEFAULT_TTL_DAYS),
        )


def compute_file_hash(file_path: str, max_bytes: int = 2 * 1024 * 1024) -> str:
    """
    Compute SHA256 hash of a file (first max_bytes for large files).

    Uses SHA256 for better collision resistance than MD5.
    Includes file size for additional uniqueness.
    """
    hasher = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            # Read first 2MB to speed up hashing
            data = f.read(max_bytes)
            hasher.update(data)
            # Include file size
            f.seek(0, 2)
            hasher.update(str(f.tell()).encode())
    except Exception as e:
        logger.warning(f"Could not hash file {file_path}: {e}")
        return "unknown"
    return hasher.hexdigest()[:16]


def compute_text_hash(text: str) -> str:
    """Compute SHA256 hash of text content."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def compute_config_hash(config: Dict[str, Any]) -> str:
    """Compute hash of configuration dictionary."""
    config_str = json.dumps(config, sort_keys=True)
    return compute_text_hash(config_str)


class SOACache:
    """
    Version-aware cache for SOA pipeline stages.

    Features:
    - Stage-specific caching (detection, extraction, transformation, etc.)
    - TTL-based expiration
    - Automatic invalidation on PDF/config/prompt changes
    - Protocol-level cache isolation

    Cache key components:
    - PDF hash (first 2MB + file size)
    - Stage name
    - Model name (when applicable)
    - Config hash (stage-specific settings)
    - Prompt hash (when applicable)
    """

    def __init__(self, cache_dir: Optional[Path] = None, ttl_days: int = DEFAULT_TTL_DAYS):
        """
        Initialize cache.

        Args:
            cache_dir: Custom cache directory (default: .cache/soa/)
            ttl_days: Time-to-live for cache entries (default: 30 days)
        """
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_days = ttl_days
        logger.info(f"SOA cache initialized at: {self.cache_dir}")

    def _build_cache_key(
        self,
        pdf_path: str,
        stage: str,
        model: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        prompt_path: Optional[str] = None,
    ) -> str:
        """Build a unique cache key from all components."""
        # Hash PDF
        pdf_hash = compute_file_hash(pdf_path)

        # Hash config if provided
        config_hash = compute_config_hash(config) if config else "noconfig"

        # Hash prompt if provided
        prompt_hash = "noprompt"
        if prompt_path and os.path.exists(prompt_path):
            with open(prompt_path, 'r') as f:
                prompt_hash = compute_text_hash(f.read())

        # Model hash
        model_hash = compute_text_hash(model or "nomodel")[:8]

        # Combine components
        combined = f"{pdf_hash}_{stage}_{config_hash}_{prompt_hash}_{model_hash}"
        key_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]

        # Protocol name for readable filename
        protocol_name = Path(pdf_path).stem[:30]

        return f"{stage}_{protocol_name}_{key_hash}"

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get file path for a cache key."""
        return self.cache_dir / f"{cache_key}.json"

    def get(
        self,
        pdf_path: str,
        stage: str,
        model: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        prompt_path: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached result if available and not expired.

        Args:
            pdf_path: Path to protocol PDF
            stage: Pipeline stage name (detection, extraction, etc.)
            model: Model name used for this stage
            config: Stage-specific configuration
            prompt_path: Path to prompt template (for LLM stages)

        Returns:
            Cached result dict with 'data' and 'metadata', or None if cache miss.
        """
        cache_key = self._build_cache_key(pdf_path, stage, model, config, prompt_path)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            logger.debug(f"Cache MISS for {stage} (key: {cache_key})")
            return None

        try:
            with open(cache_path, 'r') as f:
                cached = json.load(f)

            # Check expiration
            entry = CacheEntry.from_dict(cached)
            if entry.is_expired():
                logger.info(f"Cache EXPIRED for {stage} (key: {cache_key})")
                cache_path.unlink()
                return None

            logger.info(f"Cache HIT for {stage} (key: {cache_key})")
            return cached

        except Exception as e:
            logger.warning(f"Cache read error for {cache_key}: {e}")
            return None

    def set(
        self,
        pdf_path: str,
        stage: str,
        data: Any,
        model: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        prompt_path: Optional[str] = None,
        quality_score: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Store result in cache.

        Args:
            pdf_path: Path to protocol PDF
            stage: Pipeline stage name
            data: The result data to cache
            model: Model name used
            config: Stage-specific configuration
            prompt_path: Path to prompt template
            quality_score: Optional quality metrics

        Returns:
            The cache key used.
        """
        cache_key = self._build_cache_key(pdf_path, stage, model, config, prompt_path)
        cache_path = self._get_cache_path(cache_key)

        # Hash values for metadata
        pdf_hash = compute_file_hash(pdf_path)
        config_hash = compute_config_hash(config) if config else None
        prompt_hash = None
        if prompt_path and os.path.exists(prompt_path):
            with open(prompt_path, 'r') as f:
                prompt_hash = compute_text_hash(f.read())

        # Create cache entry
        entry = CacheEntry(
            data=data,
            stage=stage,
            pdf_path=pdf_path,
            pdf_hash=pdf_hash,
            model=model,
            config_hash=config_hash,
            prompt_hash=prompt_hash,
            created_at=datetime.now(),
            ttl_days=self.ttl_days,
        )

        # Add quality score if provided
        entry_dict = entry.to_dict()
        if quality_score:
            entry_dict["metadata"]["quality_score"] = quality_score

        try:
            with open(cache_path, 'w') as f:
                json.dump(entry_dict, f, indent=2, default=str)
            logger.info(f"Cached {stage} result (key: {cache_key})")
            return cache_key
        except Exception as e:
            logger.warning(f"Cache write error for {cache_key}: {e}")
            return cache_key

    def invalidate_protocol(self, pdf_path: str) -> int:
        """
        Invalidate all cache entries for a specific protocol.

        Args:
            pdf_path: Path to protocol PDF

        Returns:
            Number of entries invalidated.
        """
        pdf_hash = compute_file_hash(pdf_path)
        count = 0

        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r') as f:
                    cached = json.load(f)
                if cached.get("metadata", {}).get("pdf_hash") == pdf_hash:
                    cache_file.unlink()
                    count += 1
            except Exception:
                pass

        if count > 0:
            logger.info(f"Invalidated {count} cache entries for {Path(pdf_path).name}")
        return count

    def invalidate_stage(self, stage: str) -> int:
        """
        Invalidate all cache entries for a specific stage.

        Args:
            stage: Stage name (detection, extraction, etc.)

        Returns:
            Number of entries invalidated.
        """
        count = 0
        for cache_file in self.cache_dir.glob(f"{stage}_*.json"):
            cache_file.unlink()
            count += 1

        if count > 0:
            logger.info(f"Invalidated {count} cache entries for stage: {stage}")
        return count

    def invalidate_all(self) -> int:
        """
        Invalidate all cache entries.

        Returns:
            Number of entries invalidated.
        """
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
            count += 1

        if count > 0:
            logger.info(f"Invalidated all {count} cache entries")
        return count

    def cleanup_expired(self) -> int:
        """
        Remove all expired cache entries.

        Returns:
            Number of entries removed.
        """
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r') as f:
                    cached = json.load(f)
                entry = CacheEntry.from_dict(cached)
                if entry.is_expired():
                    cache_file.unlink()
                    count += 1
            except Exception:
                # Remove corrupted entries
                cache_file.unlink()
                count += 1

        if count > 0:
            logger.info(f"Cleaned up {count} expired cache entries")
        return count

    def stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats.
        """
        entries = list(self.cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in entries)

        # Group by stage
        stages = {}
        expired_count = 0

        for f in entries:
            stage = f.name.split("_")[0]
            stages[stage] = stages.get(stage, 0) + 1

            try:
                with open(f, 'r') as file:
                    cached = json.load(file)
                entry = CacheEntry.from_dict(cached)
                if entry.is_expired():
                    expired_count += 1
            except Exception:
                pass

        return {
            "total_entries": len(entries),
            "expired_entries": expired_count,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cache_dir": str(self.cache_dir),
            "ttl_days": self.ttl_days,
            "entries_by_stage": stages,
        }

    def get_protocol_cache_status(self, pdf_path: str) -> Dict[str, bool]:
        """
        Get cache status for each stage of a protocol.

        Args:
            pdf_path: Path to protocol PDF

        Returns:
            Dictionary mapping stage names to cache hit status.
        """
        pdf_hash = compute_file_hash(pdf_path)
        stages = ["detection", "classification", "evidence", "extraction",
                  "transformation", "enrichment", "validation"]

        status = {}
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r') as f:
                    cached = json.load(f)
                metadata = cached.get("metadata", {})
                if metadata.get("pdf_hash") == pdf_hash:
                    stage = metadata.get("stage", "unknown")
                    entry = CacheEntry.from_dict(cached)
                    status[stage] = not entry.is_expired()
            except Exception:
                pass

        # Fill in missing stages
        for stage in stages:
            if stage not in status:
                status[stage] = False

        return status


# Singleton instance
_cache_instance: Optional[SOACache] = None


def get_soa_cache(ttl_days: int = DEFAULT_TTL_DAYS) -> SOACache:
    """
    Get the singleton cache instance.

    Args:
        ttl_days: Time-to-live for cache entries (only used on first call)

    Returns:
        SOACache instance.
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SOACache(ttl_days=ttl_days)
    return _cache_instance


def reset_cache_instance():
    """Reset the singleton cache instance (useful for testing)."""
    global _cache_instance
    _cache_instance = None


# CLI support for cache management
if __name__ == "__main__":
    import sys

    def print_usage():
        print("Usage: python soa_cache.py [command]")
        print("\nCommands:")
        print("  stats           Show cache statistics")
        print("  cleanup         Remove expired entries")
        print("  clear           Clear all cache entries")
        print("  clear-stage X   Clear entries for stage X")
        sys.exit(1)

    if len(sys.argv) < 2:
        print_usage()

    cache = get_soa_cache()
    command = sys.argv[1].lower()

    if command == "stats":
        stats = cache.stats()
        print(f"\nSOA Cache Statistics")
        print("=" * 40)
        print(f"Total entries: {stats['total_entries']}")
        print(f"Expired entries: {stats['expired_entries']}")
        print(f"Total size: {stats['total_size_mb']} MB")
        print(f"TTL: {stats['ttl_days']} days")
        print(f"Location: {stats['cache_dir']}")
        print(f"\nEntries by stage:")
        for stage, count in stats['entries_by_stage'].items():
            print(f"  {stage}: {count}")

    elif command == "cleanup":
        count = cache.cleanup_expired()
        print(f"Cleaned up {count} expired entries")

    elif command == "clear":
        count = cache.invalidate_all()
        print(f"Cleared {count} cache entries")

    elif command == "clear-stage":
        if len(sys.argv) < 3:
            print("Error: Stage name required")
            sys.exit(1)
        stage = sys.argv[2]
        count = cache.invalidate_stage(stage)
        print(f"Cleared {count} cache entries for stage: {stage}")

    else:
        print(f"Unknown command: {command}")
        print_usage()
