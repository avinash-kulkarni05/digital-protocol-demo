"""
ATHENA to ChromaDB Vector Store Builder

This script reads concepts from the ATHENA SQLite database, generates embeddings
using Azure OpenAI, and stores them in ChromaDB for semantic search.

Environment Variables Required:
    ATHENA_DB_PATH: Path to ATHENA SQLite database
    AZURE_OPENAI_EMBEDDING_ENDPOINT: Azure OpenAI endpoint URL
    AZURE_OPENAI_EMBEDDING_API_KEY: Azure OpenAI API key
    AZURE_OPENAI_EMBEDDING_MODEL_NAME: Model name (e.g., text-embedding-ada-002)
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: Deployment name
    AZURE_OPENAI_EMBEDDING_API_VERSION: API version (e.g., 2024-02-01)

Optional Environment Variables:
    AZURE_OPENAI_SSL_VERIFY: Set to "false" to disable SSL verification
                            (required for corporate proxies with self-signed certs)

Usage:
    # Full build (all standard concepts)
    python vector_store_builder.py

    # Build with specific domain filter
    python vector_store_builder.py --domain Condition

    # Build with limit for testing
    python vector_store_builder.py --limit 10000

    # Resume interrupted build
    python vector_store_builder.py --resume

    # For corporate environments with SSL proxy issues:
    # Set AZURE_OPENAI_SSL_VERIFY=false in .env file
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import httpx
import chromadb
from chromadb.config import Settings
from openai import AzureOpenAI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_BATCH_SIZE = 100  # Concepts per embedding batch
DEFAULT_COLLECTION_NAME = "athena_concepts"
CHECKPOINT_INTERVAL = 5000  # Save checkpoint every N concepts
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds
CHROMA_UPSERT_RETRIES = 3  # Retries for ChromaDB upsert on compaction errors
CHROMA_UPSERT_RETRY_DELAY = 10  # seconds between ChromaDB upsert retries

# Domains to include (clinical domains relevant for eligibility criteria)
CLINICAL_DOMAINS = [
    "Condition",
    "Drug",
    "Measurement",
    "Procedure",
    "Observation",
    "Device",
    "Spec Anatomic Site",
    "Specimen",
    "Gender",
    "Race",
    "Ethnicity",
]

# Domain-to-collection name mapping for partitioned vector store
DOMAIN_COLLECTION_MAP = {
    domain: f"athena_{domain.lower().replace(' ', '_')}" for domain in CLINICAL_DOMAINS
}

# Vocabularies to prioritize (standard vocabularies)
PRIORITY_VOCABULARIES = [
    "SNOMED",
    "LOINC",
    "RxNorm",
    "RxNorm Extension",
    "ICD10CM",
    "ICD9CM",
    "CPT4",
    "HCPCS",
    "NDC",
    "NCIt",
    "HemOnc",
    "Gender",
    "Race",
    "Ethnicity",
]


@dataclass
class BuildConfig:
    """Configuration for vector store build."""
    athena_db_path: str
    output_dir: str
    collection_name: str = DEFAULT_COLLECTION_NAME
    batch_size: int = DEFAULT_BATCH_SIZE
    domain_filter: Optional[str] = None
    vocab_filter: Optional[List[str]] = None
    limit: Optional[int] = None
    resume: bool = False
    include_synonyms: bool = True
    standard_only: bool = True  # Only include standard concepts (standard_concept = 'S')


@dataclass
class BuildProgress:
    """Tracks build progress for checkpointing."""
    total_concepts: int = 0
    processed_concepts: int = 0
    embedded_concepts: int = 0
    failed_concepts: int = 0
    last_concept_id: int = 0
    start_time: Optional[str] = None
    last_checkpoint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_concepts": self.total_concepts,
            "processed_concepts": self.processed_concepts,
            "embedded_concepts": self.embedded_concepts,
            "failed_concepts": self.failed_concepts,
            "last_concept_id": self.last_concept_id,
            "start_time": self.start_time,
            "last_checkpoint": self.last_checkpoint,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BuildProgress":
        return cls(**data)


class AzureEmbeddingClient:
    """Azure OpenAI embedding client with retry logic."""

    def __init__(self):
        self.endpoint = os.environ.get("AZURE_OPENAI_EMBEDDING_ENDPOINT")
        self.api_key = os.environ.get("AZURE_OPENAI_EMBEDDING_API_KEY")
        self.model_name = os.environ.get("AZURE_OPENAI_EMBEDDING_MODEL_NAME")
        self.deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        self.api_version = os.environ.get("AZURE_OPENAI_EMBEDDING_API_VERSION", "2024-02-01")

        # Check if SSL verification should be disabled (for corporate proxies with self-signed certs)
        self.ssl_verify = os.environ.get("AZURE_OPENAI_SSL_VERIFY", "true").lower() != "false"

        self._validate_config()

        # Create custom httpx client if SSL verification is disabled
        if not self.ssl_verify:
            logger.warning("SSL verification is DISABLED. This should only be used in corporate proxy environments.")
            http_client = httpx.Client(verify=False)
            self.client = AzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
                http_client=http_client,
            )
        else:
            self.client = AzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
            )

        ssl_status = "enabled" if self.ssl_verify else "DISABLED"
        logger.info(f"Azure OpenAI client initialized: endpoint={self.endpoint}, deployment={self.deployment}, ssl_verify={ssl_status}")

    def _validate_config(self):
        """Validate required environment variables."""
        missing = []
        if not self.endpoint:
            missing.append("AZURE_OPENAI_EMBEDDING_ENDPOINT")
        if not self.api_key:
            missing.append("AZURE_OPENAI_EMBEDDING_API_KEY")
        if not self.deployment:
            missing.append("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts with retry logic.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Clean and truncate texts (Azure has token limits)
        cleaned_texts = [self._clean_text(t) for t in texts]

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.embeddings.create(
                    input=cleaned_texts,
                    model=self.deployment,
                )

                # Extract embeddings in order
                embeddings = [item.embedding for item in response.data]
                return embeddings

            except Exception as e:
                logger.warning(f"Embedding attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                else:
                    raise

        return []

    def _clean_text(self, text: str, max_length: int = 8000) -> str:
        """Clean and truncate text for embedding."""
        if not text:
            return ""
        # Remove excessive whitespace
        cleaned = " ".join(text.split())
        # Truncate if too long (Azure ada-002 has ~8k token limit)
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length]
        return cleaned


class VectorStoreBuilder:
    """
    Builds ChromaDB vector store from ATHENA concepts.

    Simple sequential flow:
    - Read concepts from ATHENA SQLite database
    - Generate embeddings via Azure OpenAI (one batch at a time)
    - Store embeddings in ChromaDB with metadata
    - Progress checkpointing for resume capability
    """

    def __init__(self, config: BuildConfig):
        self.config = config
        self.embedding_client = AzureEmbeddingClient()
        self.progress = BuildProgress()
        self.collection = None  # Set per-domain in _init_collection()

        # Initialize ChromaDB client (shared across domain collections)
        self.chroma_client = chromadb.PersistentClient(
            path=config.output_dir,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            )
        )

        logger.info(f"ChromaDB initialized at: {config.output_dir}")

    def _init_collection(self, domain: str) -> None:
        """Initialize or switch to a domain-specific collection."""
        collection_name = DOMAIN_COLLECTION_MAP.get(domain, f"athena_{domain.lower()}")
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={
                "description": f"ATHENA OMOP concept embeddings - {domain} domain",
                "source": "ATHENA CDM vocabulary",
                "domain": domain,
                "hnsw:M": 8,
                "hnsw:construction_ef": 100,
                "hnsw:batch_size": 2000,
                "hnsw:sync_threshold": 100000,
            }
        )
        logger.info(f"Collection: {collection_name} (existing docs: {self.collection.count():,})")

    def build(self, skip_domains: Optional[List[str]] = None) -> BuildProgress:
        """
        Execute the full build process with domain-based partitioning.

        Builds one domain collection at a time to stay within memory limits.
        Each domain gets its own ChromaDB collection and checkpoint file.

        Args:
            skip_domains: Optional list of domain names to skip (e.g., ["Drug", "Measurement"])

        Returns:
            BuildProgress with combined statistics across all domains
        """
        # Determine which domains to build
        if self.config.domain_filter:
            domains = [self.config.domain_filter]
        else:
            domains = list(CLINICAL_DOMAINS)

        # Remove skipped domains
        if skip_domains:
            skipped = [d for d in domains if d in skip_domains]
            domains = [d for d in domains if d not in skip_domains]
            if skipped:
                logger.info(f"Skipping domains: {', '.join(skipped)}")

        overall_start = time.time()
        total_embedded = 0
        total_failed = 0
        total_processed = 0

        for domain in domains:
            logger.info("=" * 60)
            logger.info(f"BUILDING DOMAIN: {domain}")
            logger.info("=" * 60)

            # Reset per-domain progress
            self.progress = BuildProgress()
            self.progress.start_time = datetime.now().isoformat()
            self._current_domain = domain

            # Load domain-specific checkpoint if resuming
            if self.config.resume:
                self._load_checkpoint()
                if self.progress.last_checkpoint and self.progress.processed_concepts > 0:
                    # Check if domain was already completed
                    if self.progress.processed_concepts >= self.progress.total_concepts > 0:
                        logger.info(f"Domain {domain} already completed, skipping")
                        total_embedded += self.progress.embedded_concepts
                        total_failed += self.progress.failed_concepts
                        total_processed += self.progress.processed_concepts
                        continue

            # Initialize domain-specific collection
            self._init_collection(domain)

            # Build this domain
            self._build_domain(domain)

            total_embedded += self.progress.embedded_concepts
            total_failed += self.progress.failed_concepts
            total_processed += self.progress.processed_concepts

            logger.info(f"Domain {domain} complete: "
                        f"embedded={self.progress.embedded_concepts:,}, "
                        f"failed={self.progress.failed_concepts}")

        elapsed = time.time() - overall_start
        rate = total_processed / elapsed if elapsed > 0 else 0

        logger.info("\n" + "=" * 60)
        logger.info("ALL DOMAINS COMPLETE")
        logger.info(f"  Total processed: {total_processed:,}")
        logger.info(f"  Total embedded:  {total_embedded:,}")
        logger.info(f"  Total failed:    {total_failed}")
        logger.info(f"  Average rate:    {rate:.1f} concepts/sec")
        logger.info(f"  Elapsed:         {elapsed:.0f}s")
        logger.info("=" * 60)

        # Return combined progress
        self.progress = BuildProgress(
            total_concepts=total_processed,
            processed_concepts=total_processed,
            embedded_concepts=total_embedded,
            failed_concepts=total_failed,
        )
        return self.progress

    def _build_domain(self, domain: str) -> None:
        """
        Build a single domain collection with simple sequential embedding.

        Reads concepts in batches, embeds each batch, writes to ChromaDB,
        then moves to the next batch.

        Args:
            domain: The domain to build (e.g., "Condition", "Drug")
        """
        # Temporarily set domain_filter to this domain
        original_filter = self.config.domain_filter
        self.config.domain_filter = domain

        # Connect to ATHENA database
        logger.info(f"Connecting to ATHENA database: {self.config.athena_db_path}")
        conn = sqlite3.connect(self.config.athena_db_path)
        conn.row_factory = sqlite3.Row

        try:
            # Count total concepts for this domain
            self.progress.total_concepts = self._count_concepts(conn)
            logger.info(
                f"Domain '{domain}': {self.progress.total_concepts:,} concepts | "
                f"Batch size: {self.config.batch_size}"
            )

            if self.progress.total_concepts == 0:
                logger.info(f"No concepts for domain '{domain}', skipping")
                return

            build_start_time = time.time()
            batch = []

            for concept in self._iter_concepts(conn):
                batch.append(concept)

                if len(batch) >= self.config.batch_size:
                    self._process_batch(batch)
                    batch = []

                    # Log progress every 10 batches
                    if self.progress.processed_concepts % (self.config.batch_size * 10) == 0:
                        elapsed = time.time() - build_start_time
                        rate = self.progress.processed_concepts / elapsed if elapsed > 0 else 0
                        total = max(self.progress.total_concepts, 1)
                        pct = (self.progress.processed_concepts / total) * 100
                        logger.info(
                            f"[{domain}] Progress: {self.progress.processed_concepts:,}/"
                            f"{self.progress.total_concepts:,} ({pct:.1f}%) | "
                            f"Rate: {rate:.1f} concepts/sec | "
                            f"Embedded: {self.progress.embedded_concepts:,} | "
                            f"Failed: {self.progress.failed_concepts}"
                        )

            # Process final partial batch
            if batch:
                self._process_batch(batch)

            # Final checkpoint for this domain
            self._save_checkpoint()

            elapsed = time.time() - build_start_time
            rate = self.progress.processed_concepts / elapsed if elapsed > 0 else 0

            logger.info(f"[{domain}] DOMAIN COMPLETE")
            logger.info(f"  Processed: {self.progress.processed_concepts:,}")
            logger.info(f"  Embedded:  {self.progress.embedded_concepts:,}")
            logger.info(f"  Failed:    {self.progress.failed_concepts}")
            logger.info(f"  Rate:      {rate:.1f} concepts/sec")

        finally:
            conn.close()
            self.config.domain_filter = original_filter

    def _process_batch(self, batch: List[Dict[str, Any]]) -> None:
        """
        Process a single batch: embed and write to ChromaDB.

        Args:
            batch: List of concept dictionaries
        """
        texts = [self._concept_to_text(c) for c in batch]
        ids = [str(c["concept_id"]) for c in batch]
        metadatas = [
            {
                "concept_id": int(c["concept_id"]),
                "concept_code": str(c["concept_code"] or ""),
                "concept_name": str(c["concept_name"]),
                "vocabulary_id": str(c["vocabulary_id"]),
                "domain_id": str(c["domain_id"]),
                "concept_class_id": str(c["concept_class_id"] or ""),
                "standard_concept": str(c["standard_concept"] or ""),
            }
            for c in batch
        ]

        try:
            # Generate embeddings
            embeddings = self.embedding_client.get_embeddings(texts)

            if len(embeddings) != len(batch):
                logger.error(
                    f"Embedding count mismatch: got {len(embeddings)}, expected {len(batch)}"
                )
                self.progress.failed_concepts += len(batch)
                self.progress.processed_concepts += len(batch)
                return

            # Write to ChromaDB with retry
            for attempt in range(CHROMA_UPSERT_RETRIES):
                try:
                    self.collection.upsert(
                        ids=ids,
                        embeddings=embeddings,
                        documents=texts,
                        metadatas=metadatas,
                    )
                    self.progress.embedded_concepts += len(batch)
                    self.progress.last_concept_id = max(
                        self.progress.last_concept_id, int(batch[-1]["concept_id"])
                    )
                    break
                except Exception as e:
                    if attempt < CHROMA_UPSERT_RETRIES - 1:
                        logger.warning(
                            f"ChromaDB upsert attempt {attempt + 1}/{CHROMA_UPSERT_RETRIES} failed: {e} "
                            f"— retrying in {CHROMA_UPSERT_RETRY_DELAY}s"
                        )
                        time.sleep(CHROMA_UPSERT_RETRY_DELAY)
                    else:
                        logger.error(f"ChromaDB upsert failed after {CHROMA_UPSERT_RETRIES} attempts: {e}")
                        self.progress.failed_concepts += len(batch)

        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            self.progress.failed_concepts += len(batch)

        self.progress.processed_concepts += len(batch)

        # Checkpoint periodically
        if self.progress.processed_concepts % CHECKPOINT_INTERVAL < self.config.batch_size:
            self._save_checkpoint()

    def _count_concepts(self, conn: sqlite3.Connection) -> int:
        """Count total concepts matching filter criteria."""
        query = self._build_count_query()
        cursor = conn.execute(query)
        return cursor.fetchone()[0]

    def _build_count_query(self) -> str:
        """Build SQL count query with filters."""
        conditions = []

        # Standard concept filter
        if self.config.standard_only:
            conditions.append("standard_concept = 'S'")

        # Domain filter
        if self.config.domain_filter:
            conditions.append(f"domain_id = '{self.config.domain_filter}'")
        elif CLINICAL_DOMAINS:
            domain_list = ", ".join(f"'{d}'" for d in CLINICAL_DOMAINS)
            conditions.append(f"domain_id IN ({domain_list})")

        # Vocabulary filter
        if self.config.vocab_filter:
            vocab_list = ", ".join(f"'{v}'" for v in self.config.vocab_filter)
            conditions.append(f"vocabulary_id IN ({vocab_list})")

        # Resume filter
        if self.config.resume and self.progress.last_concept_id > 0:
            conditions.append(f"concept_id > {self.progress.last_concept_id}")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"SELECT COUNT(*) FROM concept WHERE {where_clause}"

        if self.config.limit:
            query = f"SELECT COUNT(*) FROM (SELECT 1 FROM concept WHERE {where_clause} LIMIT {self.config.limit})"

        return query

    def _iter_concepts(self, conn: sqlite3.Connection) -> Generator[Dict[str, Any], None, None]:
        """
        Iterate over concepts from ATHENA database.

        Yields:
            Dict with concept data
        """
        query = self._build_select_query()
        cursor = conn.execute(query)

        count = 0
        for row in cursor:
            yield {
                "concept_id": row["concept_id"],
                "concept_code": row["concept_code"],
                "concept_name": row["concept_name"],
                "vocabulary_id": row["vocabulary_id"],
                "domain_id": row["domain_id"],
                "concept_class_id": row["concept_class_id"],
                "standard_concept": row["standard_concept"],
            }

            count += 1
            if self.config.limit and count >= self.config.limit:
                break

    def _build_select_query(self) -> str:
        """Build SQL select query with filters."""
        conditions = []

        # Standard concept filter
        if self.config.standard_only:
            conditions.append("standard_concept = 'S'")

        # Domain filter
        if self.config.domain_filter:
            conditions.append(f"domain_id = '{self.config.domain_filter}'")
        elif CLINICAL_DOMAINS:
            domain_list = ", ".join(f"'{d}'" for d in CLINICAL_DOMAINS)
            conditions.append(f"domain_id IN ({domain_list})")

        # Vocabulary filter
        if self.config.vocab_filter:
            vocab_list = ", ".join(f"'{v}'" for v in self.config.vocab_filter)
            conditions.append(f"vocabulary_id IN ({vocab_list})")

        # Resume filter
        if self.config.resume and self.progress.last_concept_id > 0:
            conditions.append(f"concept_id > {self.progress.last_concept_id}")

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT concept_id, concept_code, concept_name, vocabulary_id,
                   domain_id, concept_class_id, standard_concept
            FROM concept
            WHERE {where_clause}
            ORDER BY concept_id ASC
        """

        if self.config.limit:
            query += f" LIMIT {self.config.limit}"

        return query

    def _concept_to_text(self, concept: Dict[str, Any]) -> str:
        """
        Convert concept to text for embedding.

        Creates a rich text representation that captures semantic meaning.

        Args:
            concept: Concept dictionary

        Returns:
            Text string for embedding
        """
        parts = [concept["concept_name"]]

        # Add domain context
        if concept.get("domain_id"):
            parts.append(f"[Domain: {concept['domain_id']}]")

        # Add vocabulary context
        if concept.get("vocabulary_id"):
            parts.append(f"[Vocabulary: {concept['vocabulary_id']}]")

        # Add concept class for additional context
        if concept.get("concept_class_id"):
            parts.append(f"[Class: {concept['concept_class_id']}]")

        return " ".join(parts)

    def _get_checkpoint_path(self) -> Path:
        """Get path to domain-specific checkpoint file."""
        domain = getattr(self, '_current_domain', None)
        if domain:
            safe_name = domain.lower().replace(' ', '_')
            return Path(self.config.output_dir) / f"build_checkpoint_{safe_name}.json"
        return Path(self.config.output_dir) / "build_checkpoint.json"

    def _save_checkpoint(self) -> None:
        """Save current progress to checkpoint file."""
        self.progress.last_checkpoint = datetime.now().isoformat()
        checkpoint_path = self._get_checkpoint_path()

        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(self.progress.to_dict(), f, indent=2)

        logger.debug(f"Checkpoint saved: {checkpoint_path}")

    def _load_checkpoint(self) -> None:
        """Load progress from checkpoint file if exists."""
        checkpoint_path = self._get_checkpoint_path()

        if checkpoint_path.exists():
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.progress = BuildProgress.from_dict(data)
            logger.info(f"Resumed from checkpoint: last_concept_id={self.progress.last_concept_id}, "
                       f"processed={self.progress.processed_concepts}")
        else:
            logger.info("No checkpoint found, starting fresh build")


def build_vector_store(
    athena_db_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    domain_filter: Optional[str] = None,
    skip_domains: Optional[List[str]] = None,
    limit: Optional[int] = None,
    resume: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> BuildProgress:
    """
    Convenience function to build vector store.

    Args:
        athena_db_path: Path to ATHENA database (defaults to env var)
        output_dir: Output directory for ChromaDB (defaults to ./vector_store)
        domain_filter: Optional single domain to build (e.g., "Condition")
        skip_domains: Optional list of domains to skip (e.g., ["Drug", "Measurement"])
        limit: Optional limit on number of concepts
        resume: Whether to resume from checkpoint
        batch_size: Number of concepts per embedding batch

    Returns:
        BuildProgress with statistics
    """
    # Load environment variables from .env if available
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)
        logger.info(f"Loaded environment from: {env_path}")

    # Get paths
    db_path = athena_db_path or os.environ.get("ATHENA_DB_PATH")
    if not db_path:
        raise ValueError("ATHENA_DB_PATH not provided and not in environment")

    if not Path(db_path).exists():
        raise FileNotFoundError(f"ATHENA database not found: {db_path}")

    out_dir = output_dir or str(Path(__file__).parent / "vector_store")

    # Create output directory
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    # Build config
    config = BuildConfig(
        athena_db_path=db_path,
        output_dir=out_dir,
        domain_filter=domain_filter,
        limit=limit,
        resume=resume,
        batch_size=batch_size,
    )

    # Run builder
    builder = VectorStoreBuilder(config)
    return builder.build(skip_domains=skip_domains)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build ChromaDB vector store from ATHENA concepts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Full build with all standard concepts
    python vector_store_builder.py

    # Build only Condition domain
    python vector_store_builder.py --domain Condition

    # Test build with 1000 concepts
    python vector_store_builder.py --limit 1000

    # Resume interrupted build
    python vector_store_builder.py --resume

    # Custom output directory
    python vector_store_builder.py --output ./my_vector_store
        """
    )

    parser.add_argument(
        "--athena-db",
        help="Path to ATHENA SQLite database (default: ATHENA_DB_PATH env var)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output directory for ChromaDB (default: ./vector_store)"
    )
    parser.add_argument(
        "--domain", "-d",
        choices=CLINICAL_DOMAINS,
        help="Filter to specific domain"
    )
    parser.add_argument(
        "--skip-domains",
        nargs="+",
        metavar="DOMAIN",
        help="Domains to skip (e.g., --skip-domains Drug Measurement)"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        help="Limit number of concepts (for testing)"
    )
    parser.add_argument(
        "--resume", "-r",
        action="store_true",
        help="Resume from last checkpoint"
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Batch size for embedding (default: {DEFAULT_BATCH_SIZE})"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        progress = build_vector_store(
            athena_db_path=args.athena_db,
            output_dir=args.output,
            domain_filter=args.domain,
            skip_domains=args.skip_domains,
            limit=args.limit,
            resume=args.resume,
            batch_size=args.batch_size,
        )

        print("\n" + "=" * 60)
        print("BUILD SUMMARY")
        print("=" * 60)
        print(f"  Total concepts:    {progress.total_concepts:,}")
        print(f"  Processed:         {progress.processed_concepts:,}")
        print(f"  Embedded:          {progress.embedded_concepts:,}")
        print(f"  Failed:            {progress.failed_concepts}")
        print(f"  Success rate:      {(progress.embedded_concepts / max(progress.processed_concepts, 1)) * 100:.1f}%")
        print("=" * 60)

    except Exception as e:
        logger.error(f"Build failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
