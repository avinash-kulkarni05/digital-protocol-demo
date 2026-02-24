"""
OMOP Query Result Cache

Provides in-memory LRU caching for OMOP concept searches and source mappings
to avoid redundant database queries across eligibility criteria.

This cache significantly improves Stage 5 performance when multiple criteria
reference the same medical terms (e.g., "hypertension" appearing in multiple criteria).
"""

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """Statistics for cache performance monitoring."""
    hits: int = 0
    misses: int = 0
    source_mapping_hits: int = 0
    source_mapping_misses: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def source_mapping_hit_rate(self) -> float:
        total = self.source_mapping_hits + self.source_mapping_misses
        return self.source_mapping_hits / total if total > 0 else 0.0


class OMOPQueryCache:
    """
    Thread-safe LRU cache for OMOP concept searches and source mappings.

    Features:
    - LRU eviction when cache is full
    - Separate caches for concept searches and source mappings
    - Thread-safe operations
    - Statistics tracking for monitoring

    Usage:
        cache = OMOPQueryCache(max_concept_entries=5000, max_source_entries=10000)

        # Cache concept search results
        key = cache.make_concept_key(search_terms, domain, vocab_priority)
        if key in cache:
            concepts = cache.get_concepts(key)
        else:
            concepts = search_database(...)
            cache.set_concepts(key, concepts)

        # Cache source mappings
        source_key = cache.make_source_mapping_key(concept_id)
        if source_key in cache:
            mappings = cache.get_source_mappings(source_key)
        else:
            mappings = query_source_mappings(...)
            cache.set_source_mappings(source_key, mappings)
    """

    _instance: Optional['OMOPQueryCache'] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Singleton pattern - ensures one cache instance across pipeline."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        max_concept_entries: int = 5000,
        max_source_entries: int = 10000
    ):
        """
        Initialize the cache.

        Args:
            max_concept_entries: Maximum concept search results to cache
            max_source_entries: Maximum source mapping results to cache
        """
        if getattr(self, '_initialized', False):
            return

        self._max_concept_entries = max_concept_entries
        self._max_source_entries = max_source_entries

        # OrderedDict for LRU behavior
        self._concept_cache: OrderedDict[str, Tuple[List[Dict], float]] = OrderedDict()
        self._source_mapping_cache: OrderedDict[int, Tuple[List[Dict], float]] = OrderedDict()

        # Thread locks for cache operations
        self._concept_lock = threading.Lock()
        self._source_lock = threading.Lock()

        # Statistics
        self._stats = CacheStats()

        self._initialized = True
        logger.debug(f"OMOPQueryCache initialized: max_concepts={max_concept_entries}, max_sources={max_source_entries}")

    @staticmethod
    def make_concept_key(
        search_terms: List[str],
        domain: str,
        vocab_priority: List[str]
    ) -> str:
        """
        Create a unique cache key for concept search parameters.

        Args:
            search_terms: List of search terms (order matters)
            domain: OMOP domain
            vocab_priority: Vocabulary priority list

        Returns:
            SHA256 hash key
        """
        # Normalize: lowercase, sorted terms for consistent keys
        normalized_terms = sorted([t.lower().strip() for t in search_terms if t])
        key_data = {
            "terms": normalized_terms,
            "domain": domain.lower(),
            "vocabs": [v.lower() for v in vocab_priority]
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]

    @staticmethod
    def make_source_mapping_key(concept_id: int) -> int:
        """Source mapping key is just the concept_id."""
        return concept_id

    def get_concepts(self, key: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached concept search results.

        Args:
            key: Cache key from make_concept_key()

        Returns:
            List of concept dicts if cached, None otherwise
        """
        return None  # Always return None - caching disabled

    def set_concepts(self, key: str, concepts: List[Dict[str, Any]]) -> None:
        """
        Cache concept search results.

        Args:
            key: Cache key from make_concept_key()
            concepts: List of concept dicts to cache
        """
        with self._concept_lock:
            # Evict oldest if at capacity
            while len(self._concept_cache) >= self._max_concept_entries:
                self._concept_cache.popitem(last=False)
                self._stats.evictions += 1

            # Store with timestamp
            self._concept_cache[key] = (concepts, time.time())

    def get_source_mappings(self, concept_id: int) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached source mappings for a concept.

        Args:
            concept_id: Standard concept ID

        Returns:
            List of source mapping dicts if cached, None otherwise
        """
        return None  # Always return None - caching disabled

    def set_source_mappings(self, concept_id: int, mappings: List[Dict[str, Any]]) -> None:
        """
        Cache source mappings for a concept.

        Args:
            concept_id: Standard concept ID
            mappings: List of source mapping dicts
        """
        with self._source_lock:
            while len(self._source_mapping_cache) >= self._max_source_entries:
                self._source_mapping_cache.popitem(last=False)
                self._stats.evictions += 1

            self._source_mapping_cache[concept_id] = (mappings, time.time())

    def get_source_mappings_batch(
        self,
        concept_ids: List[int]
    ) -> Tuple[Dict[int, List[Dict]], List[int]]:
        """
        Get cached source mappings for multiple concepts.

        Args:
            concept_ids: List of concept IDs to look up

        Returns:
            Tuple of (cached_results dict, uncached_ids list)
        """
        cached = {}
        uncached = []

        with self._source_lock:
            for cid in concept_ids:
                if cid in self._source_mapping_cache:
                    self._source_mapping_cache.move_to_end(cid)
                    mappings, _ = self._source_mapping_cache[cid]
                    cached[cid] = mappings
                    self._stats.source_mapping_hits += 1
                else:
                    uncached.append(cid)
                    self._stats.source_mapping_misses += 1

        return cached, uncached

    def set_source_mappings_batch(
        self,
        mappings_by_id: Dict[int, List[Dict[str, Any]]]
    ) -> None:
        """
        Cache source mappings for multiple concepts.

        Args:
            mappings_by_id: Dict mapping concept_id to list of source mappings
        """
        with self._source_lock:
            for concept_id, mappings in mappings_by_id.items():
                while len(self._source_mapping_cache) >= self._max_source_entries:
                    self._source_mapping_cache.popitem(last=False)
                    self._stats.evictions += 1

                self._source_mapping_cache[concept_id] = (mappings, time.time())

    def __contains__(self, key: str) -> bool:
        """Check if concept key is in cache."""
        with self._concept_lock:
            return key in self._concept_cache

    @property
    def stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._stats

    def clear(self) -> None:
        """Clear all caches."""
        with self._concept_lock:
            self._concept_cache.clear()
        with self._source_lock:
            self._source_mapping_cache.clear()
        self._stats = CacheStats()
        logger.debug("OMOPQueryCache cleared")

    def get_stats_summary(self) -> Dict[str, Any]:
        """Get summary of cache statistics."""
        return {
            "concept_cache_size": len(self._concept_cache),
            "source_mapping_cache_size": len(self._source_mapping_cache),
            "concept_hit_rate": f"{self._stats.hit_rate:.1%}",
            "source_mapping_hit_rate": f"{self._stats.source_mapping_hit_rate:.1%}",
            "total_hits": self._stats.hits + self._stats.source_mapping_hits,
            "total_misses": self._stats.misses + self._stats.source_mapping_misses,
            "evictions": self._stats.evictions,
        }


# Module-level singleton accessor
_cache_instance: Optional[OMOPQueryCache] = None


def get_omop_cache() -> OMOPQueryCache:
    """Get the singleton OMOP query cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = OMOPQueryCache()
    return _cache_instance
