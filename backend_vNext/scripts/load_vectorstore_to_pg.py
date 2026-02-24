"""
Load OMOP concepts from ChromaDB vector store into PostgreSQL (NeonDB).

Reads all domain-partitioned collections from the local ChromaDB vector store
and inserts concept data (including embeddings) into the omop_concepts table.

Usage:
    python scripts/load_vectorstore_to_pg.py
    python scripts/load_vectorstore_to_pg.py --batch-size 500
    python scripts/load_vectorstore_to_pg.py --test-connection
"""


import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import chromadb
from chromadb.config import Settings
import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Load from .env
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

DATABASE_URL = os.environ.get(
    "POSTGRE_DATABASE_URL",
    "postgresql://neondb_owner:npg_WiatFgUye15o"
    "@ep-wandering-recipe-aibrb3u4.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require",
)

VECTOR_STORE_PATH = str(
    Path(__file__).resolve().parent.parent
    / "eligibility_analyzer"
    / "omop_rag"
    / "vector_store"
)

# Domain collections in the ChromaDB store
DOMAIN_COLLECTIONS = [
    "athena_condition",
    "athena_drug",
    "athena_measurement",
    "athena_procedure",
    "athena_observation",
    "athena_device",
    "athena_spec_anatomic_site",
    "athena_specimen",
    "athena_gender",
    "athena_race",
    "athena_ethnicity",
]

PG_BATCH_SIZE = 500  # rows per INSERT
CHROMA_FETCH_BATCH = 5000  # rows per ChromaDB .get() call

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

CREATE_EXTENSION_SQL = "CREATE EXTENSION IF NOT EXISTS vector;"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS omop_concepts (
    concept_id       INTEGER PRIMARY KEY,
    concept_name     TEXT,
    domain_id        VARCHAR(50),
    vocabulary_id    VARCHAR(50),
    concept_class_id VARCHAR(50),
    standard_concept VARCHAR(1),
    concept_code     VARCHAR(100),
    synonyms         TEXT[],
    metadata         JSONB,
    embedding        vector(3072)
);
"""

CREATE_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_omop_domain ON omop_concepts (domain_id);",
    "CREATE INDEX IF NOT EXISTS idx_omop_vocab ON omop_concepts (vocabulary_id);",
    "CREATE INDEX IF NOT EXISTS idx_omop_standard ON omop_concepts (standard_concept);",
]

UPSERT_SQL = """
INSERT INTO omop_concepts
    (concept_id, concept_name, domain_id, vocabulary_id,
     concept_class_id, standard_concept, concept_code,
     synonyms, metadata, embedding)
VALUES %s
ON CONFLICT (concept_id) DO UPDATE SET
    concept_name     = EXCLUDED.concept_name,
    domain_id        = EXCLUDED.domain_id,
    vocabulary_id    = EXCLUDED.vocabulary_id,
    concept_class_id = EXCLUDED.concept_class_id,
    standard_concept = EXCLUDED.standard_concept,
    concept_code     = EXCLUDED.concept_code,
    synonyms         = EXCLUDED.synonyms,
    metadata         = EXCLUDED.metadata,
    embedding        = EXCLUDED.embedding;
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def connect_pg(enable_vector=True):
    """Establish PostgreSQL connection and register pgvector type."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    if enable_vector:
        # Ensure pgvector extension exists before registering the type
        cur = conn.cursor()
        cur.execute(CREATE_EXTENSION_SQL)
        conn.commit()
        cur.close()
        register_vector(conn)
    return conn


def test_connection():
    """Test that we can connect to PostgreSQL and pgvector is available."""
    print("=" * 60)
    print("Testing PostgreSQL connection...")
    print("=" * 60)
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        print(f"  Connected OK")
        print(f"  PostgreSQL version: {version}")

        cur.execute(CREATE_EXTENSION_SQL)
        print(f"  pgvector extension: enabled")

        cur.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
        )
        row = cur.fetchone()
        if row:
            print(f"  pgvector version:   {row[0]}")

        # Register and verify vector type works
        register_vector(conn)
        print(f"  pgvector type:      registered")

        cur.close()
        conn.close()
        print("  Connection test PASSED")
        print("=" * 60)
        return True
    except Exception as e:
        print(f"  Connection test FAILED: {e}")
        print("=" * 60)
        return False


def setup_table(conn):
    """Create the omop_concepts table if it doesn't exist."""
    cur = conn.cursor()
    cur.execute(CREATE_EXTENSION_SQL)
    cur.execute(CREATE_TABLE_SQL)
    for idx_sql in CREATE_INDEX_SQL:
        cur.execute(idx_sql)
    conn.commit()
    cur.close()
    print("Table 'omop_concepts' ready (created or already exists).")


def get_existing_count(conn):
    """Get current row count in the table."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM omop_concepts;")
    count = cur.fetchone()[0]
    cur.close()
    return count


def open_chroma():
    """Open ChromaDB persistent client."""
    print(f"\nOpening ChromaDB at: {VECTOR_STORE_PATH}")
    client = chromadb.PersistentClient(
        path=VECTOR_STORE_PATH,
        settings=Settings(anonymized_telemetry=False),
    )
    collections = client.list_collections()
    print(f"  Found {len(collections)} collections:")
    for c in collections:
        print(f"    - {c.name}  ({c.count()} items)")
    return client


def load_collection(conn, chroma_client, collection_name, pg_batch_size):
    """Load one ChromaDB collection into PostgreSQL."""
    try:
        collection = chroma_client.get_collection(collection_name)
    except Exception:
        print(f"  [SKIP] Collection '{collection_name}' not found.")
        return 0

    total = collection.count()
    if total == 0:
        print(f"  [SKIP] Collection '{collection_name}' is empty.")
        return 0

    print(f"\n  Loading '{collection_name}' ({total:,} concepts)...")

    loaded = 0
    offset = 0
    cur = conn.cursor()

    while offset < total:
        fetch_size = min(CHROMA_FETCH_BATCH, total - offset)

        result = collection.get(
            limit=fetch_size,
            offset=offset,
            include=["metadatas", "embeddings", "documents"],
        )

        ids = result["ids"]
        metadatas = result["metadatas"]
        embeddings = result["embeddings"]
        documents = result["documents"]

        rows = []
        for i, _id in enumerate(ids):
            meta = metadatas[i] if metadatas is not None else {}
            emb = embeddings[i] if embeddings is not None else None
            doc = documents[i] if documents is not None else None

            concept_id = meta.get("concept_id")
            if concept_id is None:
                continue

            concept_name = meta.get("concept_name", "")
            domain_id = meta.get("domain_id", "")
            vocabulary_id = meta.get("vocabulary_id", "")
            concept_class_id = meta.get("concept_class_id", "")
            standard_concept = meta.get("standard_concept") or None
            concept_code = meta.get("concept_code", "")

            # Build metadata JSON with extra info
            extra_meta = {
                "document_text": doc,
                "source_collection": collection_name,
            }

            # Convert embedding to numpy array for pgvector
            emb_val = np.array(emb, dtype=np.float32) if emb is not None else None

            rows.append((
                int(concept_id),
                concept_name,
                domain_id,
                vocabulary_id,
                concept_class_id,
                standard_concept,
                str(concept_code),
                None,  # synonyms - not available in ChromaDB metadata
                json.dumps(extra_meta),
                emb_val,
            ))

        if rows:
            # Insert in sub-batches
            for start in range(0, len(rows), pg_batch_size):
                batch = rows[start : start + pg_batch_size]
                execute_values(
                    cur,
                    UPSERT_SQL,
                    batch,
                    template=(
                        "(%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector)"
                    ),
                    page_size=pg_batch_size,
                )
            conn.commit()

        loaded += len(rows)
        offset += fetch_size

        pct = (loaded / total) * 100
        print(
            f"    Progress: {loaded:>8,} / {total:,}  ({pct:5.1f}%)",
            end="\r",
            flush=True,
        )

    print(
        f"    Progress: {loaded:>8,} / {total:,}  (100.0%)  - DONE"
    )
    cur.close()
    return loaded


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Load ChromaDB OMOP vector store into PostgreSQL"
    )
    parser.add_argument(
        "--test-connection",
        action="store_true",
        help="Only test the database connection and exit",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=PG_BATCH_SIZE,
        help=f"PostgreSQL INSERT batch size (default: {PG_BATCH_SIZE})",
    )
    args = parser.parse_args()

    # ---- Test connection ----
    if not test_connection():
        sys.exit(1)

    if args.test_connection:
        sys.exit(0)

    # ---- Open stores ----
    conn = connect_pg()
    setup_table(conn)

    existing = get_existing_count(conn)
    print(f"Existing rows in omop_concepts: {existing:,}")

    chroma_client = open_chroma()

    # ---- Load each collection ----
    grand_total = 0
    start_time = time.time()

    print("\n" + "=" * 60)
    print("Starting data load...")
    print("=" * 60)

    for coll_name in DOMAIN_COLLECTIONS:
        t0 = time.time()
        count = load_collection(conn, chroma_client, coll_name, args.batch_size)
        elapsed = time.time() - t0
        if count > 0:
            rate = count / elapsed if elapsed > 0 else 0
            print(f"    Loaded {count:,} rows in {elapsed:.1f}s ({rate:.0f} rows/s)")
        grand_total += count

    # ---- Final summary ----
    total_elapsed = time.time() - start_time
    final_count = get_existing_count(conn)

    conn.close()

    print("\n" + "=" * 60)
    print("LOAD COMPLETE")
    print("=" * 60)
    print(f"  Collections processed : {len(DOMAIN_COLLECTIONS)}")
    print(f"  Rows loaded this run  : {grand_total:,}")
    print(f"  Total rows in table   : {final_count:,}")
    print(f"  Total time            : {total_elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
