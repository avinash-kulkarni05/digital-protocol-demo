"""
RAG-based OMOP Concept Mapper

Main orchestrator that combines all three tiers of the RAG approach:
- Tier 1: Curated mappings (deterministic, 100% confidence)
- Tier 2: Semantic vector search (ChromaDB + Azure OpenAI embeddings)
- Tier 3: LLM validation (for ambiguous matches)

This replaces the pattern-matching approach in Stage 5 of the interpretation pipeline.

Usage:
    from eligibility_analyzer.omop_rag import RAGMapper

    mapper = RAGMapper()
    result = await mapper.map_term("Patient is female", domain_hint="Gender")
    # Returns: MappingResult(concept_id=8532, concept_name="FEMALE", confidence=1.0)
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# Confidence thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.85  # Use directly without LLM validation
MEDIUM_CONFIDENCE_THRESHOLD = 0.70  # Send to LLM for validation
LOW_CONFIDENCE_THRESHOLD = 0.50  # Mark as low confidence, may need review


@dataclass
class MappingResult:
    """Result from RAG-based OMOP mapping."""
    term: str
    concept_id: Optional[int] = None
    concept_name: Optional[str] = None
    concept_code: Optional[str] = None
    vocabulary_id: Optional[str] = None
    domain_id: Optional[str] = None
    standard_concept: Optional[str] = None
    confidence: float = 0.0
    source: str = "unmapped"  # curated, semantic, llm_validated, unmapped
    match_type: str = "none"  # exact, pattern, semantic, validated
    is_mapped: bool = False
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    validation_reason: Optional[str] = None
    processing_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "term": self.term,
            "conceptId": self.concept_id,
            "conceptName": self.concept_name,
            "conceptCode": self.concept_code,
            "vocabularyId": self.vocabulary_id,
            "domainId": self.domain_id,
            "standardConcept": self.standard_concept,
            "confidence": self.confidence,
            "source": self.source,
            "matchType": self.match_type,
            "isMapped": self.is_mapped,
            "candidates": self.candidates,
            "validationReason": self.validation_reason,
            "processingTimeMs": self.processing_time_ms,
        }


@dataclass
class MappingCache:
    """Simple in-memory LRU cache for mapping results."""
    max_size: int = 1000
    _cache: Dict[str, MappingResult] = field(default_factory=dict)
    _access_order: List[str] = field(default_factory=list)

    def get(self, key: str) -> Optional[MappingResult]:
        if key in self._cache:
            # Move to end (most recently used)
            self._access_order.remove(key)
            self._access_order.append(key)
            return self._cache[key]
        return None

    def set(self, key: str, value: MappingResult) -> None:
        if key in self._cache:
            self._access_order.remove(key)
        elif len(self._cache) >= self.max_size:
            # Remove least recently used
            oldest = self._access_order.pop(0)
            del self._cache[oldest]

        self._cache[key] = value
        self._access_order.append(key)

    def make_key(self, term: str, domain_hint: Optional[str] = None) -> str:
        """Create cache key from term and domain."""
        normalized = term.lower().strip()
        if domain_hint:
            return f"{normalized}|{domain_hint.lower()}"
        return normalized


class RAGMapper:
    """
    RAG-based OMOP Concept Mapper.

    Three-tier mapping approach:
    1. Curated mappings - checked first, 100% confidence
    2. Semantic search - vector similarity in ChromaDB
    3. LLM validation - validates ambiguous matches
    """

    def __init__(
        self,
        vector_store_path: Optional[str] = None,
        athena_db_path: Optional[str] = None,  # Deprecated, kept for backward compat
        use_llm_validation: bool = True,
        cache_size: int = 1000,
    ):
        """
        Initialize RAG mapper.

        Args:
            vector_store_path: Path to ChromaDB vector store
            athena_db_path: Deprecated. Ignored — PostgreSQL is used instead.
            use_llm_validation: Whether to use LLM for Tier 3 validation
            cache_size: Size of in-memory cache
        """
        # Load environment
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        if env_path.exists():
            from dotenv import load_dotenv
            load_dotenv(env_path)

        # Initialize curated mapper (Tier 1)
        from .curated_mapper import get_curated_mapper
        self.curated_mapper = get_curated_mapper()

        # Check if PostgreSQL mode is enabled
        self._use_postgresql = os.environ.get("OMOP_POSTGRESQL", "false").lower() == "true"
        self._pg_store = None

        if self._use_postgresql:
            self._init_pg_vector_store()

        # Initialize ChromaDB vector store (Tier 2) as fallback or primary
        self.vector_store_path = vector_store_path or str(Path(__file__).parent / "vector_store")
        if not self._use_postgresql or not self._vector_store_available:
            self._init_vector_store()

        # Initialize embedding client for PostgreSQL mode (needs embeddings for queries)
        if self._use_postgresql and self._vector_store_available:
            self._init_embedding_client()

        # PostgreSQL URL for fallback exact-match queries
        self._database_url = os.environ.get("POSTGRE_DATABASE_URL", "")

        # LLM validation settings
        self.use_llm_validation = use_llm_validation

        # In-memory cache
        self._cache = MappingCache(max_size=cache_size)

        # Persistent disk cache
        try:
            from .persistent_cache import get_omop_disk_cache
            self._disk_cache = get_omop_disk_cache()
            disk_stats = self._disk_cache.stats()
            logger.info(f"Disk cache loaded: {disk_stats['total_entries']} entries")
        except Exception as e:
            logger.warning(f"Disk cache unavailable: {e}")
            self._disk_cache = None

        # Statistics
        self._stats = {
            "total_lookups": 0,
            "cache_hits": 0,
            "disk_cache_hits": 0,
            "curated_hits": 0,
            "semantic_hits": 0,
            "llm_validated": 0,
            "unmapped": 0,
        }

        backend = "PostgreSQL+pgvector" if self._use_postgresql and self._pg_store else "ChromaDB"
        logger.info(
            f"RAGMapper initialized: backend={backend}, "
            f"llm_validation={use_llm_validation}"
        )

    def _init_pg_vector_store(self) -> None:
        """Initialize PostgreSQL + pgvector backend."""
        self._vector_store_available = False
        try:
            from .pg_vector_store import PgVectorStore
            self._pg_store = PgVectorStore()
            if self._pg_store.available:
                self._vector_store_available = True
                logger.info(
                    f"PostgreSQL vector store ready: "
                    f"{self._pg_store.concept_count:,} concepts, "
                    f"{len(self._pg_store.domain_counts)} domains"
                )
            else:
                logger.warning("PostgreSQL vector store not available, falling back to ChromaDB")
                self._use_postgresql = False
        except Exception as e:
            logger.warning(f"Failed to initialize PostgreSQL vector store: {e}")
            self._use_postgresql = False

    def _init_embedding_client(self) -> None:
        """Initialize Azure OpenAI embedding client (for PostgreSQL mode query embeddings)."""
        try:
            from openai import AzureOpenAI

            ssl_verify = os.environ.get("AZURE_OPENAI_SSL_VERIFY", "true").lower() != "false"
            if not ssl_verify:
                http_client = httpx.Client(verify=False)
                self.embedding_client = AzureOpenAI(
                    azure_endpoint=os.environ.get("AZURE_OPENAI_EMBEDDING_ENDPOINT"),
                    api_key=os.environ.get("AZURE_OPENAI_EMBEDDING_API_KEY"),
                    api_version=os.environ.get("AZURE_OPENAI_EMBEDDING_API_VERSION", "2024-02-01"),
                    http_client=http_client,
                )
            else:
                self.embedding_client = AzureOpenAI(
                    azure_endpoint=os.environ.get("AZURE_OPENAI_EMBEDDING_ENDPOINT"),
                    api_key=os.environ.get("AZURE_OPENAI_EMBEDDING_API_KEY"),
                    api_version=os.environ.get("AZURE_OPENAI_EMBEDDING_API_VERSION", "2024-02-01"),
                )
            self.embedding_deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        except Exception as e:
            logger.error(f"Failed to initialize embedding client: {e}")

    def _init_vector_store(self) -> None:
        """Initialize ChromaDB vector store and embedding client."""
        self._vector_store_available = False

        if not Path(self.vector_store_path).exists():
            logger.warning(f"Vector store not found at {self.vector_store_path}")
            return

        try:
            import chromadb
            from openai import AzureOpenAI
            from .vector_store_builder import DOMAIN_COLLECTION_MAP

            self.chroma_client = chromadb.PersistentClient(path=self.vector_store_path)
            self._domain_collection_map = DOMAIN_COLLECTION_MAP
            self._collections = {}  # domain -> collection cache

            # Try legacy single collection as fallback
            try:
                self.collection = self.chroma_client.get_collection("athena_concepts")
            except Exception:
                self.collection = None

            # Check if SSL verification should be disabled
            ssl_verify = os.environ.get("AZURE_OPENAI_SSL_VERIFY", "true").lower() != "false"

            if not ssl_verify:
                http_client = httpx.Client(verify=False)
                self.embedding_client = AzureOpenAI(
                    azure_endpoint=os.environ.get("AZURE_OPENAI_EMBEDDING_ENDPOINT"),
                    api_key=os.environ.get("AZURE_OPENAI_EMBEDDING_API_KEY"),
                    api_version=os.environ.get("AZURE_OPENAI_EMBEDDING_API_VERSION", "2024-02-01"),
                    http_client=http_client,
                )
            else:
                self.embedding_client = AzureOpenAI(
                    azure_endpoint=os.environ.get("AZURE_OPENAI_EMBEDDING_ENDPOINT"),
                    api_key=os.environ.get("AZURE_OPENAI_EMBEDDING_API_KEY"),
                    api_version=os.environ.get("AZURE_OPENAI_EMBEDDING_API_VERSION", "2024-02-01"),
                )

            self.embedding_deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
            self._vector_store_available = True

            # Report available domain collections
            available = []
            for domain, col_name in self._domain_collection_map.items():
                try:
                    col = self.chroma_client.get_collection(col_name)
                    if col.count() > 0:
                        available.append(domain)
                        self._collections[domain] = col
                except Exception:
                    pass

            if available:
                logger.info(f"Vector store loaded: {len(available)} domain collections")
            elif self.collection:
                logger.info(f"Vector store loaded (legacy): {self.collection.count():,} concepts")

        except Exception as e:
            logger.warning(f"Failed to initialize vector store: {e}")

    def _get_domain_collection(self, domain: Optional[str] = None):
        """Get the best collection for a given domain."""
        if domain and domain in self._collections:
            return self._collections[domain]
        # Try to lazily load domain collection
        if domain and domain in self._domain_collection_map:
            try:
                col_name = self._domain_collection_map[domain]
                col = self.chroma_client.get_collection(col_name)
                if col.count() > 0:
                    self._collections[domain] = col
                    return col
            except Exception:
                pass
        # Fallback to legacy collection
        return self.collection

    async def map_term(
        self,
        term: str,
        domain_hint: Optional[str] = None,
        criterion_id: Optional[str] = None,
        atomic_id: Optional[str] = None,
    ) -> MappingResult:
        """
        Map a term to OMOP concept using RAG approach.

        Args:
            term: The term to map
            domain_hint: Optional domain hint (e.g., "Condition", "Gender")
            criterion_id: Optional criterion ID for tracking
            atomic_id: Optional atomic ID for tracking

        Returns:
            MappingResult with concept details and confidence
        """
        start_time = time.time()
        self._stats["total_lookups"] += 1

        # Check in-memory cache
        cache_key = self._cache.make_key(term, domain_hint)
        cached = self._cache.get(cache_key)
        if cached:
            self._stats["cache_hits"] += 1
            return cached

        # Check persistent disk cache
        if self._disk_cache:
            disk_result = self._disk_cache.get(term, domain_hint)
            if disk_result:
                self._stats["disk_cache_hits"] += 1
                self._cache.set(cache_key, disk_result)
                return disk_result

        result = MappingResult(term=term)

        # Tier 1: Curated mappings (deterministic)
        curated = self.curated_mapper.lookup(term, domain_hint)
        if curated:
            result = MappingResult(
                term=term,
                concept_id=curated.concept_id,
                concept_name=curated.concept_name,
                concept_code=curated.concept_code,
                vocabulary_id=curated.vocabulary_id,
                domain_id=curated.domain_id,
                standard_concept=curated.standard_concept,
                confidence=curated.confidence,
                source="curated",
                match_type=curated.match_type,
                is_mapped=True,
            )
            self._stats["curated_hits"] += 1
            result.processing_time_ms = (time.time() - start_time) * 1000
            self._cache.set(cache_key, result)
            return result

        # Tier 2: Semantic search (if vector store available)
        if self._vector_store_available:
            semantic_result = await self._semantic_search(term, domain_hint)
            if semantic_result:
                # Check confidence level
                if semantic_result.confidence >= HIGH_CONFIDENCE_THRESHOLD:
                    # High confidence - use directly
                    result = semantic_result
                    self._stats["semantic_hits"] += 1
                elif semantic_result.confidence >= MEDIUM_CONFIDENCE_THRESHOLD and self.use_llm_validation:
                    # Medium confidence - validate with LLM
                    validated = await self._llm_validate(term, semantic_result.candidates, domain_hint)
                    if validated:
                        result = validated
                        self._stats["llm_validated"] += 1
                    else:
                        result = semantic_result
                        result.validation_reason = "LLM validation inconclusive"
                        self._stats["semantic_hits"] += 1
                else:
                    # Low confidence - include candidates but mark as low confidence
                    result = semantic_result
                    self._stats["semantic_hits"] += 1

        # If still unmapped, try PostgreSQL exact-match fallback
        if not result.is_mapped and self._database_url:
            fallback_result = self._pg_exact_match_fallback(term, domain_hint)
            if fallback_result:
                result = fallback_result

        # Mark as unmapped if no result
        if not result.is_mapped:
            result.source = "unmapped"
            self._stats["unmapped"] += 1

        result.processing_time_ms = (time.time() - start_time) * 1000
        self._cache.set(cache_key, result)

        # Persist to disk cache (for mapped results)
        if result.is_mapped and self._disk_cache:
            self._disk_cache.set(term, domain_hint, result)

        return result

    async def _semantic_search(
        self,
        term: str,
        domain_hint: Optional[str] = None,
        top_k: int = 5,
    ) -> Optional[MappingResult]:
        """
        Tier 2: Semantic vector search.

        Uses PostgreSQL+pgvector when OMOP_POSTGRESQL=true,
        otherwise falls back to ChromaDB.

        Args:
            term: The term to search
            domain_hint: Optional domain filter
            top_k: Number of candidates to retrieve

        Returns:
            MappingResult with best match and candidates
        """
        try:
            # Generate embedding
            response = self.embedding_client.embeddings.create(
                input=[term],
                model=self.embedding_deployment,
            )
            query_embedding = response.data[0].embedding

            # Route to PostgreSQL or ChromaDB
            if self._use_postgresql and self._pg_store and self._pg_store.available:
                candidates = self._pg_store.search(
                    query_embedding=query_embedding,
                    top_k=top_k,
                    domain_filter=domain_hint,
                )
            else:
                candidates = self._chromadb_search(query_embedding, domain_hint, top_k)

            if not candidates:
                return None

            # Best match
            best = candidates[0]
            return MappingResult(
                term=term,
                concept_id=best["concept_id"],
                concept_name=best["concept_name"],
                concept_code=best["concept_code"],
                vocabulary_id=best["vocabulary_id"],
                domain_id=best["domain_id"],
                standard_concept=best["standard_concept"],
                confidence=best["similarity"],
                source="semantic",
                match_type="semantic",
                is_mapped=best["similarity"] >= LOW_CONFIDENCE_THRESHOLD,
                candidates=candidates,
            )

        except Exception as e:
            logger.error(f"Semantic search failed for '{term}': {e}")
            return None

    def _chromadb_search(
        self,
        query_embedding: List[float],
        domain_hint: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search ChromaDB vector store (original implementation)."""
        collection = self._get_domain_collection(domain_hint)
        if collection is None:
            return []

        # Only apply domain filter if using legacy single collection
        where_filter = None
        using_domain_collection = domain_hint and domain_hint in self._collections
        if domain_hint and not using_domain_collection:
            where_filter = {"domain_id": domain_hint}

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        if not results["documents"] or not results["documents"][0]:
            return []

        candidates = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # Convert distance to similarity (ChromaDB uses L2 distance)
            similarity = max(0, 1 - (dist / 2))
            candidates.append({
                "concept_id": meta.get("concept_id"),
                "concept_name": meta.get("concept_name"),
                "concept_code": meta.get("concept_code"),
                "vocabulary_id": meta.get("vocabulary_id"),
                "domain_id": meta.get("domain_id"),
                "standard_concept": meta.get("standard_concept"),
                "similarity": round(similarity, 4),
                "distance": round(dist, 4),
            })

        return candidates

    async def _llm_validate(
        self,
        term: str,
        candidates: List[Dict[str, Any]],
        domain_hint: Optional[str] = None,
    ) -> Optional[MappingResult]:
        """
        Tier 3: LLM validation for ambiguous matches.

        Args:
            term: Original term
            candidates: List of candidate concepts from semantic search
            domain_hint: Optional domain hint

        Returns:
            MappingResult if LLM validates a match, None otherwise
        """
        try:
            import google.generativeai as genai

            # Configure Gemini
            genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
            model = genai.GenerativeModel("gemini-2.0-flash")

            # Build prompt
            candidates_text = "\n".join([
                f"{i+1}. {c['concept_name']} (ID: {c['concept_id']}, "
                f"Vocabulary: {c['vocabulary_id']}, Similarity: {c['similarity']:.2f})"
                for i, c in enumerate(candidates[:5])
            ])

            prompt = f"""You are a clinical terminology expert evaluating OMOP concept mappings.

Given an eligibility criterion term, determine if any of the candidate OMOP concepts is an appropriate match.

Term: "{term}"
{f'Expected Domain: {domain_hint}' if domain_hint else ''}

Candidate Concepts:
{candidates_text}

Respond with JSON only:
{{
  "best_match_index": <1-based index of best match, or 0 if none are appropriate>,
  "confidence": <your confidence 0.0-1.0>,
  "reasoning": "<brief explanation>"
}}"""

            response = model.generate_content(prompt)
            response_text = response.text.strip()

            # Parse JSON response
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]

            result = json.loads(response_text)

            best_idx = result.get("best_match_index", 0)
            if best_idx > 0 and best_idx <= len(candidates):
                best = candidates[best_idx - 1]
                return MappingResult(
                    term=term,
                    concept_id=best["concept_id"],
                    concept_name=best["concept_name"],
                    concept_code=best["concept_code"],
                    vocabulary_id=best["vocabulary_id"],
                    domain_id=best["domain_id"],
                    standard_concept=best["standard_concept"],
                    confidence=result.get("confidence", 0.8),
                    source="llm_validated",
                    match_type="validated",
                    is_mapped=True,
                    candidates=candidates,
                    validation_reason=result.get("reasoning"),
                )

            return None

        except Exception as e:
            logger.error(f"LLM validation failed for '{term}': {e}")
            return None

    def _pg_exact_match_fallback(
        self,
        term: str,
        domain_hint: Optional[str] = None,
    ) -> Optional[MappingResult]:
        """
        Fallback: Direct PostgreSQL exact-match search on omop_concepts.

        Only used when vector store is not available or returns no results.
        """
        if not self._database_url:
            return None

        conn = None
        try:
            conn = psycopg2.connect(self._database_url)
            conn.autocommit = True
            cur = conn.cursor(cursor_factory=RealDictCursor)

            if domain_hint:
                cur.execute("""
                    SELECT concept_id, concept_code, concept_name, vocabulary_id,
                           domain_id, standard_concept
                    FROM omop_concepts
                    WHERE LOWER(concept_name) = LOWER(%s)
                      AND domain_id = %s
                      AND standard_concept = 'S'
                    LIMIT 1
                """, (term, domain_hint))
            else:
                cur.execute("""
                    SELECT concept_id, concept_code, concept_name, vocabulary_id,
                           domain_id, standard_concept
                    FROM omop_concepts
                    WHERE LOWER(concept_name) = LOWER(%s)
                      AND standard_concept = 'S'
                    LIMIT 1
                """, (term,))

            row = cur.fetchone()
            cur.close()

            if row:
                return MappingResult(
                    term=term,
                    concept_id=row["concept_id"],
                    concept_name=row["concept_name"],
                    concept_code=row["concept_code"],
                    vocabulary_id=row["vocabulary_id"],
                    domain_id=row["domain_id"],
                    standard_concept=row["standard_concept"],
                    confidence=0.9,  # Exact match but from fallback
                    source="pg_fallback",
                    match_type="exact",
                    is_mapped=True,
                )

            return None

        except Exception as e:
            logger.error(f"PostgreSQL fallback failed for '{term}': {e}")
            return None
        finally:
            if conn:
                conn.close()

    async def _batch_generate_embeddings(
        self,
        texts: List[str],
        batch_size: int = 100,
    ) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts in batched API calls.

        Args:
            texts: List of text strings to embed
            batch_size: Max texts per API call

        Returns:
            List of embedding vectors (None for failures), same order as input
        """
        all_embeddings: List[Optional[List[float]]] = [None] * len(texts)

        for batch_start in range(0, len(texts), batch_size):
            batch_end = min(batch_start + batch_size, len(texts))
            batch_texts = texts[batch_start:batch_end]

            try:
                response = self.embedding_client.embeddings.create(
                    input=batch_texts,
                    model=self.embedding_deployment,
                )
                for item in response.data:
                    all_embeddings[batch_start + item.index] = item.embedding

                logger.info(
                    f"Batch embedding {batch_start + 1}-{batch_end}/{len(texts)}: "
                    f"{len(response.data)} embeddings generated"
                )
            except Exception as e:
                logger.error(f"Batch embedding failed for items {batch_start}-{batch_end}: {e}")

        return all_embeddings

    async def _semantic_search_with_embedding(
        self,
        term: str,
        query_embedding: List[float],
        domain_hint: Optional[str] = None,
        top_k: int = 5,
    ) -> Optional[MappingResult]:
        """
        Semantic search using a pre-computed embedding (skips API call).

        Args:
            term: The term being searched
            query_embedding: Pre-computed embedding vector
            domain_hint: Optional domain filter
            top_k: Number of candidates

        Returns:
            MappingResult with best match and candidates
        """
        try:
            candidates = None
            if self._use_postgresql and self._pg_store and self._pg_store.available:
                candidates = self._pg_store.search(
                    query_embedding=query_embedding,
                    top_k=top_k,
                    domain_filter=domain_hint,
                )
            elif not self._use_postgresql and hasattr(self, '_collections'):
                candidates = self._chromadb_search(query_embedding, domain_hint, top_k)

            if not candidates:
                return None

            best = candidates[0]
            return MappingResult(
                term=term,
                concept_id=best["concept_id"],
                concept_name=best["concept_name"],
                concept_code=best["concept_code"],
                vocabulary_id=best["vocabulary_id"],
                domain_id=best["domain_id"],
                standard_concept=best["standard_concept"],
                confidence=best["similarity"],
                source="semantic",
                match_type="semantic",
                is_mapped=best["similarity"] >= LOW_CONFIDENCE_THRESHOLD,
                candidates=candidates,
            )
        except Exception as e:
            logger.error(f"Semantic search (pre-embedded) failed for '{term}': {e}")
            return None

    async def map_terms_batch(
        self,
        terms: List[Dict[str, Any]],
        max_concurrent: int = 10,
        embedding_batch_size: int = 100,
    ) -> List[MappingResult]:
        """
        Map multiple terms with batched embedding generation.

        Phase 1: Check disk cache, in-memory cache, curated mapper
        Phase 2: Batch-generate embeddings, concurrent pgvector searches
        Phase 3: LLM validation for medium-confidence results

        Args:
            terms: List of dicts with 'term', optional 'domain_hint'
            max_concurrent: Max concurrent pgvector searches
            embedding_batch_size: Max terms per embedding API call

        Returns:
            List of MappingResult objects (same order as input)
        """
        if not terms:
            return []

        batch_start_time = time.time()
        results: List[Optional[MappingResult]] = [None] * len(terms)

        # ---- PHASE 1: Cache + Curated (no API calls) ----
        needs_semantic: List[Tuple[int, Dict[str, Any]]] = []  # (index, term_info)

        for i, term_info in enumerate(terms):
            t = term_info.get("term", "")
            dh = term_info.get("domain_hint")
            self._stats["total_lookups"] += 1

            # Check persistent disk cache
            if self._disk_cache:
                disk_result = self._disk_cache.get(t, dh)
                if disk_result:
                    results[i] = disk_result
                    cache_key = self._cache.make_key(t, dh)
                    self._cache.set(cache_key, disk_result)
                    self._stats["disk_cache_hits"] += 1
                    continue

            # Check in-memory LRU cache
            cache_key = self._cache.make_key(t, dh)
            cached = self._cache.get(cache_key)
            if cached:
                results[i] = cached
                self._stats["cache_hits"] += 1
                continue

            # Check curated mappings
            curated = self.curated_mapper.lookup(t, dh)
            if curated:
                result = MappingResult(
                    term=t,
                    concept_id=curated.concept_id,
                    concept_name=curated.concept_name,
                    concept_code=curated.concept_code,
                    vocabulary_id=curated.vocabulary_id,
                    domain_id=curated.domain_id,
                    standard_concept=curated.standard_concept,
                    confidence=curated.confidence,
                    source="curated",
                    match_type=curated.match_type,
                    is_mapped=True,
                )
                results[i] = result
                self._cache.set(cache_key, result)
                self._stats["curated_hits"] += 1
                continue

            needs_semantic.append((i, term_info))

        resolved = len(terms) - len(needs_semantic)
        logger.info(
            f"Batch phase 1: {len(terms)} terms, "
            f"{resolved} resolved (cache/curated), "
            f"{len(needs_semantic)} need semantic search"
        )

        if not needs_semantic or not self._vector_store_available:
            for i, term_info in needs_semantic:
                results[i] = MappingResult(term=term_info.get("term", ""), source="unmapped")
                self._stats["unmapped"] += 1
            return results

        # ---- PHASE 2: Batch embeddings + sequential pgvector searches ----
        texts_to_embed = [info.get("term", "") for _, info in needs_semantic]
        all_embeddings = await self._batch_generate_embeddings(
            texts_to_embed, batch_size=embedding_batch_size
        )

        # Ensure pgvector connection is alive after embedding phase
        if self._use_postgresql and self._pg_store:
            self._pg_store._ensure_connection()

        needs_llm_validation: List[Tuple[int, MappingResult, str]] = []

        # Process searches sequentially — psycopg2 uses a single connection
        # and NeonDB serverless can drop idle connections during embedding phase
        search_count = 0
        for idx_in_needs in range(len(needs_semantic)):
            orig_idx, term_info = needs_semantic[idx_in_needs]
            t = term_info.get("term", "")
            dh = term_info.get("domain_hint")
            embedding = all_embeddings[idx_in_needs]

            if embedding is None:
                results[orig_idx] = MappingResult(term=t, source="unmapped")
                self._stats["unmapped"] += 1
                continue

            semantic_result = await self._semantic_search_with_embedding(
                t, embedding, dh
            )

            if semantic_result and semantic_result.confidence >= HIGH_CONFIDENCE_THRESHOLD:
                results[orig_idx] = semantic_result
                self._stats["semantic_hits"] += 1
            elif (
                semantic_result
                and semantic_result.confidence >= MEDIUM_CONFIDENCE_THRESHOLD
                and self.use_llm_validation
            ):
                needs_llm_validation.append((orig_idx, semantic_result, dh))
            elif semantic_result:
                results[orig_idx] = semantic_result
                self._stats["semantic_hits"] += 1
            else:
                results[orig_idx] = MappingResult(term=t, source="unmapped")
                self._stats["unmapped"] += 1

            search_count += 1
            if search_count % 50 == 0:
                logger.info(f"Batch phase 2: {search_count}/{len(needs_semantic)} searches complete")

        # ---- PHASE 3: LLM validation for medium-confidence results ----
        if needs_llm_validation:
            logger.info(f"Batch phase 3: LLM validation for {len(needs_llm_validation)} terms")
            for orig_idx, semantic_result, dh in needs_llm_validation:
                validated = await self._llm_validate(
                    semantic_result.term, semantic_result.candidates, dh
                )
                if validated:
                    results[orig_idx] = validated
                    self._stats["llm_validated"] += 1
                else:
                    results[orig_idx] = semantic_result
                    semantic_result.validation_reason = "LLM validation inconclusive"
                    self._stats["semantic_hits"] += 1

        # ---- Save new results to caches ----
        disk_entries = []
        for i, result in enumerate(results):
            if result and result.is_mapped:
                t = terms[i].get("term", "")
                dh = terms[i].get("domain_hint")
                cache_key = self._cache.make_key(t, dh)
                self._cache.set(cache_key, result)
                if self._disk_cache:
                    disk_entries.append((t, dh, result))

        if disk_entries and self._disk_cache:
            self._disk_cache.set_batch(disk_entries)

        # Fill any remaining None results (from gather exceptions)
        for i in range(len(results)):
            if results[i] is None:
                results[i] = MappingResult(
                    term=terms[i].get("term", ""), source="unmapped"
                )
                self._stats["unmapped"] += 1

        elapsed = time.time() - batch_start_time
        logger.info(f"Batch mapping complete: {len(terms)} terms in {elapsed:.1f}s")

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get mapping statistics."""
        total = self._stats["total_lookups"]
        if total == 0:
            return self._stats

        return {
            **self._stats,
            "cache_hit_rate": round(self._stats["cache_hits"] / total, 3),
            "disk_cache_hit_rate": round(self._stats.get("disk_cache_hits", 0) / total, 3),
            "curated_rate": round(self._stats["curated_hits"] / total, 3),
            "semantic_rate": round(self._stats["semantic_hits"] / total, 3),
            "llm_rate": round(self._stats["llm_validated"] / total, 3),
            "unmapped_rate": round(self._stats["unmapped"] / total, 3),
        }


# Singleton instance
_rag_mapper: Optional[RAGMapper] = None


def get_rag_mapper(**kwargs) -> RAGMapper:
    """Get or create the RAG mapper singleton."""
    global _rag_mapper
    if _rag_mapper is None:
        _rag_mapper = RAGMapper(**kwargs)
    return _rag_mapper


async def map_term(term: str, domain_hint: Optional[str] = None) -> MappingResult:
    """Convenience function to map a single term."""
    mapper = get_rag_mapper()
    return await mapper.map_term(term, domain_hint)


# CLI for testing
if __name__ == "__main__":
    import sys

    async def main():
        mapper = RAGMapper()

        test_terms = [
            {"term": "Patient is female", "domain_hint": "Gender"},
            {"term": "Sex is male", "domain_hint": "Gender"},
            {"term": "diabetes mellitus", "domain_hint": "Condition"},
            {"term": "hypertension", "domain_hint": "Condition"},
            {"term": "hemoglobin a1c", "domain_hint": "Measurement"},
            {"term": "breast cancer", "domain_hint": "Condition"},
            {"term": "ECOG performance status", "domain_hint": "Observation"},
            {"term": "unknown xyz term", "domain_hint": None},
        ]

        print("\n" + "=" * 70)
        print(" RAG Mapper Test")
        print("=" * 70)

        for term_info in test_terms:
            result = await mapper.map_term(
                term=term_info["term"],
                domain_hint=term_info.get("domain_hint"),
            )

            print(f"\n  Term: '{term_info['term']}'")
            if result.is_mapped:
                print(f"    -> {result.concept_name} (ID: {result.concept_id})")
                print(f"       Source: {result.source}, Confidence: {result.confidence:.2f}")
                print(f"       Vocabulary: {result.vocabulary_id}, Domain: {result.domain_id}")
            else:
                print(f"    -> UNMAPPED")
                if result.candidates:
                    print(f"       Candidates: {len(result.candidates)}")

            print(f"       Time: {result.processing_time_ms:.1f}ms")

        print("\n" + "-" * 70)
        print(" Statistics:")
        stats = mapper.get_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")
        print("=" * 70)

    asyncio.run(main())
