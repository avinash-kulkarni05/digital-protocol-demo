"""
Concept Expansion Cache

Persistent cache for LLM concept expansions with TTL-based expiration.
Stores term-level expansions for reuse across protocols.
"""

import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_DIR = Path(__file__).parent.parent / ".cache" / "concept_expansions"
CACHE_FILE = CACHE_DIR / "concept_expansion_cache.json"
METADATA_FILE = CACHE_DIR / "cache_metadata.json"
DEFAULT_TTL_DAYS = 30
PROMPT_VERSION = "1.0"  # Increment when prompt changes significantly


@dataclass
class ConceptExpansion:
    """Result of LLM concept expansion for a single term."""
    original_term: str
    abbreviation_expansion: Optional[str] = None
    synonyms: List[str] = field(default_factory=list)
    omop_domain_hint: Optional[str] = None
    vocabulary_hints: List[str] = field(default_factory=list)
    confidence: float = 0.0
    source: str = "llm"  # "cache", "llm", "fallback"
    cached_at: Optional[str] = None
    prompt_version: str = PROMPT_VERSION

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConceptExpansion":
        """Create from dictionary."""
        return cls(**data)


class ConceptExpansionCache:
    """
    Persistent cache for LLM concept expansions.

    Features:
    - Term-level caching (not protocol-level)
    - TTL-based expiration (default 30 days)
    - Prompt version tracking for cache invalidation
    - Batch get/set operations for efficiency
    """

    def __init__(self, ttl_days: int = DEFAULT_TTL_DAYS):
        """
        Initialize the cache.

        Args:
            ttl_days: Time-to-live in days for cache entries
        """
        self.ttl_days = ttl_days
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._dirty = False
        self._ensure_cache_dir()
        self._load_cache()

    def _ensure_cache_dir(self) -> None:
        """Ensure cache directory exists."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _normalize_key(self, term: str) -> str:
        """Normalize term for cache lookup."""
        return term.lower().strip()

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """Check if cache entry is expired."""
        cached_at = entry.get("cached_at")
        if not cached_at:
            return True

        try:
            cached_time = datetime.fromisoformat(cached_at)
            expiry_time = cached_time + timedelta(days=self.ttl_days)
            return datetime.now() > expiry_time
        except (ValueError, TypeError):
            return True

    def _is_version_mismatch(self, entry: Dict[str, Any]) -> bool:
        """Check if cache entry was created with different prompt version."""
        return entry.get("prompt_version") != PROMPT_VERSION

    def _load_cache(self) -> None:
        """Load cache from disk."""
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
                logger.info(f"Loaded {len(self._cache)} cached concept expansions")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load cache: {e}. Starting fresh.")
                self._cache = {}
        else:
            self._cache = {}

    def _save_cache(self) -> None:
        """Save cache to disk."""
        if not self._dirty:
            return

        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
            self._dirty = False
            logger.debug(f"Saved {len(self._cache)} cached concept expansions")
        except IOError as e:
            logger.error(f"Failed to save cache: {e}")

    def get(self, term: str) -> Optional[ConceptExpansion]:
        """
        Get cached expansion for a term.

        Args:
            term: Clinical term to look up

        Returns:
            ConceptExpansion if found and valid, None otherwise
        """
        key = self._normalize_key(term)
        entry = self._cache.get(key)

        if entry is None:
            return None

        # Check expiration
        if self._is_expired(entry):
            logger.debug(f"Cache entry expired for term: {term}")
            del self._cache[key]
            self._dirty = True
            return None

        # Check prompt version
        if self._is_version_mismatch(entry):
            logger.debug(f"Cache entry version mismatch for term: {term}")
            del self._cache[key]
            self._dirty = True
            return None

        # Return cached expansion with source set to "cache"
        expansion = ConceptExpansion.from_dict(entry)
        expansion.source = "cache"
        return expansion

    def set(self, term: str, expansion: ConceptExpansion) -> None:
        """
        Store expansion in cache.

        Args:
            term: Clinical term
            expansion: Expansion result to cache
        """
        key = self._normalize_key(term)

        # Add metadata
        expansion.cached_at = datetime.now().isoformat()
        expansion.prompt_version = PROMPT_VERSION

        self._cache[key] = expansion.to_dict()
        self._dirty = True

    def get_batch(self, terms: List[str]) -> Tuple[Dict[str, ConceptExpansion], List[str]]:
        """
        Get cached expansions for multiple terms.

        Args:
            terms: List of clinical terms

        Returns:
            Tuple of (cached expansions dict, list of uncached terms)
        """
        cached: Dict[str, ConceptExpansion] = {}
        uncached: List[str] = []

        for term in terms:
            expansion = self.get(term)
            if expansion:
                cached[term] = expansion
            else:
                uncached.append(term)

        logger.info(f"Cache batch lookup: {len(cached)} hits, {len(uncached)} misses")
        return cached, uncached

    def set_batch(self, expansions: Dict[str, ConceptExpansion]) -> None:
        """
        Store multiple expansions in cache.

        Args:
            expansions: Dict mapping terms to expansions
        """
        for term, expansion in expansions.items():
            self.set(term, expansion)

        # Save after batch update
        self._save_cache()
        logger.info(f"Cached {len(expansions)} new concept expansions")

    def invalidate(self, term: str) -> bool:
        """
        Invalidate a specific term.

        Args:
            term: Term to invalidate

        Returns:
            True if term was in cache
        """
        key = self._normalize_key(term)
        if key in self._cache:
            del self._cache[key]
            self._dirty = True
            return True
        return False

    def invalidate_all(self) -> int:
        """
        Invalidate all cache entries.

        Returns:
            Number of entries invalidated
        """
        count = len(self._cache)
        self._cache = {}
        self._dirty = True
        self._save_cache()
        logger.info(f"Invalidated {count} cache entries")
        return count

    def cleanup_expired(self) -> int:
        """
        Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        expired_keys = [
            key for key, entry in self._cache.items()
            if self._is_expired(entry) or self._is_version_mismatch(entry)
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            self._dirty = True
            self._save_cache()
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache statistics
        """
        total = len(self._cache)
        expired = sum(1 for entry in self._cache.values() if self._is_expired(entry))
        version_mismatch = sum(1 for entry in self._cache.values() if self._is_version_mismatch(entry))

        return {
            "total_entries": total,
            "valid_entries": total - expired - version_mismatch,
            "expired_entries": expired,
            "version_mismatch_entries": version_mismatch,
            "cache_file": str(CACHE_FILE),
            "prompt_version": PROMPT_VERSION,
            "ttl_days": self.ttl_days,
        }

    def flush(self) -> None:
        """Force save cache to disk."""
        self._dirty = True
        self._save_cache()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure cache is saved."""
        self._save_cache()
        return False


# Singleton instance
_cache_instance: Optional[ConceptExpansionCache] = None


def get_concept_expansion_cache() -> ConceptExpansionCache:
    """Get or create singleton cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = ConceptExpansionCache()
    return _cache_instance


def reset_cache() -> None:
    """Reset singleton cache instance (for testing)."""
    global _cache_instance
    _cache_instance = None
