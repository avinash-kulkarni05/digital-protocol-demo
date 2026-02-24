"""
PostgreSQL + pgvector backend for OMOP concept vector search.

Replaces ChromaDB when OMOP_POSTGRESQL=true in .env.
Uses the omop_concepts table with vector(3072) embeddings in NeonDB.
"""

import logging
import os
from typing import Dict, List, Optional

import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector

logger = logging.getLogger(__name__)


class PgVectorStore:
    """PostgreSQL + pgvector vector store for OMOP concept search."""

    # Map domain names to match ChromaDB collection naming
    DOMAIN_LIST = [
        "Condition", "Drug", "Measurement", "Procedure", "Observation",
        "Device", "Spec Anatomic Site", "Specimen", "Gender", "Race", "Ethnicity",
    ]

    def __init__(self, database_url: Optional[str] = None):
        self._database_url = database_url or os.environ.get("POSTGRE_DATABASE_URL", "")
        self._conn = None
        self._available = False
        self._concept_count = 0
        self._domain_counts: Dict[str, int] = {}
        self._connect()

    def _connect(self) -> None:
        """Establish connection to PostgreSQL and verify omop_concepts table."""
        try:
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

            self._conn = psycopg2.connect(self._database_url)
            self._conn.autocommit = True
            register_vector(self._conn)

            cur = self._conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = 'omop_concepts';"
            )
            if cur.fetchone()[0] == 0:
                logger.warning("omop_concepts table not found in PostgreSQL")
                cur.close()
                return

            cur.execute("SELECT COUNT(*) FROM omop_concepts;")
            self._concept_count = cur.fetchone()[0]

            cur.execute(
                "SELECT domain_id, COUNT(*) FROM omop_concepts "
                "GROUP BY domain_id;"
            )
            self._domain_counts = {row[0]: row[1] for row in cur.fetchall()}
            cur.close()

            self._available = True
            logger.info(
                f"PgVectorStore connected: {self._concept_count:,} concepts, "
                f"{len(self._domain_counts)} domains"
            )
        except Exception as e:
            logger.warning(f"PgVectorStore connection failed: {e}")
            self._available = False

    def _ensure_connection(self) -> bool:
        """Check if connection is alive; reconnect if stale."""
        if not self._conn:
            self._connect()
            return self._available

        try:
            cur = self._conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            return True
        except Exception:
            logger.info("PgVectorStore: connection stale, reconnecting...")
            self._connect()
            return self._available

    @property
    def available(self) -> bool:
        return self._available

    @property
    def concept_count(self) -> int:
        return self._concept_count

    @property
    def domain_counts(self) -> Dict[str, int]:
        return self._domain_counts

    def get_available_domains(self) -> List[str]:
        """Return list of domains that have concepts loaded."""
        return [d for d in self.DOMAIN_LIST if d in self._domain_counts]

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        domain_filter: Optional[str] = None,
        vocab_filter: Optional[str] = None,
    ) -> List[Dict]:
        """
        Search for similar OMOP concepts using pgvector cosine distance.

        Args:
            query_embedding: Query embedding vector
            top_k: Number of results
            domain_filter: Filter by domain_id
            vocab_filter: Filter by vocabulary_id

        Returns:
            List of concept dicts with similarity scores
        """
        if not self._available:
            return []

        max_retries = 2
        for attempt in range(max_retries):
            try:
                # Ensure connection is alive before search
                if attempt > 0 or not self._ensure_connection():
                    if attempt == 0:
                        return []
                    self._connect()
                    if not self._available:
                        return []

                emb_array = np.array(query_embedding, dtype=np.float32)

                filter_parts = []
                filter_params = []
                if domain_filter:
                    filter_parts.append("domain_id = %s")
                    filter_params.append(domain_filter)
                if vocab_filter:
                    filter_parts.append("vocabulary_id = %s")
                    filter_params.append(vocab_filter)

                where_sql = ""
                if filter_parts:
                    where_sql = "WHERE " + " AND ".join(filter_parts)

                sql = f"""
                    SELECT
                        concept_id,
                        concept_name,
                        concept_code,
                        vocabulary_id,
                        domain_id,
                        concept_class_id,
                        standard_concept,
                        1 - (embedding <=> %s::vector) AS similarity,
                        embedding <=> %s::vector AS distance
                    FROM omop_concepts
                    {where_sql}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                """
                all_params = [emb_array, emb_array] + filter_params + [emb_array, top_k]

                cur = self._conn.cursor()
                cur.execute(sql, all_params)
                rows = cur.fetchall()
                cur.close()

                results = []
                for row in rows:
                    results.append({
                        "concept_id": row[0],
                        "concept_name": row[1],
                        "concept_code": row[2],
                        "vocabulary_id": row[3],
                        "domain_id": row[4],
                        "concept_class_id": row[5],
                        "standard_concept": row[6],
                        "similarity": round(float(row[7]), 4),
                        "distance": round(float(row[8]), 4),
                    })

                return results

            except Exception as e:
                logger.error(f"PgVectorStore search failed (attempt {attempt + 1}/{max_retries}): {e}")
                # Reconnect for retry
                try:
                    self._connect()
                except Exception:
                    pass

        return []

    def close(self):
        """Close the database connection."""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
