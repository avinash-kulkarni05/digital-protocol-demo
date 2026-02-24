"""
OMOP RAG (Retrieval-Augmented Generation) Module

This module provides semantic search capabilities for OMOP concept mapping
using vector embeddings stored in PostgreSQL (pgvector).

Components:
- pg_vector_store: PostgreSQL + pgvector backend for vector search
- curated_mapper: Tier 1 deterministic mappings loaded from PostgreSQL
- rag_mapper: Full 3-tier mapping pipeline (curated + semantic + LLM)
- query_vector_store: Query interface for semantic search
- config_check: Configuration validation utility

Usage:
    # Check configuration
    python -m eligibility_analyzer.omop_rag.config_check

    # Query vector store
    python -m eligibility_analyzer.omop_rag.query_vector_store

Environment Variables Required:
    POSTGRE_DATABASE_URL: PostgreSQL connection URL (omop_concepts table with pgvector)
    OMOP_POSTGRESQL: Set to "true" to enable PostgreSQL vector search backend
    AZURE_OPENAI_EMBEDDING_ENDPOINT: Azure OpenAI endpoint
    AZURE_OPENAI_EMBEDDING_API_KEY: Azure OpenAI API key
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: Deployment name
    AZURE_OPENAI_EMBEDDING_API_VERSION: API version (optional, defaults to 2024-02-01)
"""

from .vector_store_builder import VectorStoreBuilder, BuildConfig, BuildProgress, build_vector_store, DOMAIN_COLLECTION_MAP
from .query_vector_store import VectorStoreQuery
from .curated_mapper import CuratedMapper, CuratedMapping, get_curated_mapper
from .rag_mapper import RAGMapper, MappingResult, get_rag_mapper, map_term
from .persistent_cache import OMOPMappingDiskCache, get_omop_disk_cache

__all__ = [
    # Builder
    "VectorStoreBuilder",
    "BuildConfig",
    "BuildProgress",
    "build_vector_store",
    "DOMAIN_COLLECTION_MAP",
    # Query
    "VectorStoreQuery",
    # Curated Mapper (Tier 1)
    "CuratedMapper",
    "CuratedMapping",
    "get_curated_mapper",
    # RAG Mapper (Full Pipeline)
    "RAGMapper",
    "MappingResult",
    "get_rag_mapper",
    "map_term",
    # Persistent Cache
    "OMOPMappingDiskCache",
    "get_omop_disk_cache",
]

__version__ = "1.0.0"
