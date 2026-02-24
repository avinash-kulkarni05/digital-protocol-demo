"""
Query Utility for OMOP RAG Vector Store

Interactive tool to query the built vector store and test semantic search.

Usage:
    # Interactive mode
    python query_vector_store.py

    # Single query mode
    python query_vector_store.py --query "diabetes mellitus"

    # With domain filter
    python query_vector_store.py --query "hemoglobin A1c" --domain Measurement
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

import httpx
from openai import AzureOpenAI


class VectorStoreQuery:
    """Query interface for OMOP RAG vector store (domain-partitioned).

    Supports two backends:
    - ChromaDB (default): Local vector store
    - PostgreSQL+pgvector: When OMOP_POSTGRESQL=true in .env
    """

    def __init__(self, vector_store_path: Optional[str] = None):
        """
        Initialize query interface.

        Args:
            vector_store_path: Path to ChromaDB vector store directory
        """
        # Load environment
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        if env_path.exists():
            from dotenv import load_dotenv
            load_dotenv(env_path)

        # Check if PostgreSQL mode is enabled
        self._use_postgresql = os.environ.get("OMOP_POSTGRESQL", "false").lower() == "true"
        self._pg_store = None

        if self._use_postgresql:
            self._init_pg_backend()

        # Initialize embedding client (needed for both backends)
        self._init_embedding_client()

        # Initialize ChromaDB backend if not using PostgreSQL (or as fallback)
        if not self._use_postgresql or not self._pg_store:
            self._init_chromadb_backend(vector_store_path)

    def _init_pg_backend(self):
        """Initialize PostgreSQL+pgvector backend."""
        try:
            from .pg_vector_store import PgVectorStore
            self._pg_store = PgVectorStore()
            if self._pg_store.available:
                print(
                    f"PostgreSQL vector store loaded: "
                    f"{self._pg_store.concept_count:,} concepts, "
                    f"{len(self._pg_store.domain_counts)} domains "
                    f"({', '.join(self._pg_store.get_available_domains())})"
                )
            else:
                print("PostgreSQL vector store not available, falling back to ChromaDB")
                self._use_postgresql = False
                self._pg_store = None
        except Exception as e:
            print(f"PostgreSQL init failed ({e}), falling back to ChromaDB")
            self._use_postgresql = False
            self._pg_store = None

    def _init_embedding_client(self):
        """Initialize Azure OpenAI embedding client."""
        ssl_verify = os.environ.get("AZURE_OPENAI_SSL_VERIFY", "true").lower() != "false"

        if not ssl_verify:
            http_client = httpx.Client(verify=False)
            self.azure_client = AzureOpenAI(
                azure_endpoint=os.environ.get("AZURE_OPENAI_EMBEDDING_ENDPOINT"),
                api_key=os.environ.get("AZURE_OPENAI_EMBEDDING_API_KEY"),
                api_version=os.environ.get("AZURE_OPENAI_EMBEDDING_API_VERSION", "2024-02-01"),
                http_client=http_client,
            )
        else:
            self.azure_client = AzureOpenAI(
                azure_endpoint=os.environ.get("AZURE_OPENAI_EMBEDDING_ENDPOINT"),
                api_key=os.environ.get("AZURE_OPENAI_EMBEDDING_API_KEY"),
                api_version=os.environ.get("AZURE_OPENAI_EMBEDDING_API_VERSION", "2024-02-01"),
            )
        self.deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

    def _init_chromadb_backend(self, vector_store_path: Optional[str] = None):
        """Initialize ChromaDB backend."""
        import chromadb
        from .vector_store_builder import DOMAIN_COLLECTION_MAP

        self.store_path = vector_store_path or str(Path(__file__).parent / "vector_store")

        if not Path(self.store_path).exists():
            raise FileNotFoundError(
                f"Vector store not found at {self.store_path}. "
                "Run vector_store_builder.py first to build it."
            )

        self._domain_collection_map = DOMAIN_COLLECTION_MAP

        self.chroma_client = chromadb.PersistentClient(path=self.store_path)
        self._collections = {}

        try:
            self.collection = self.chroma_client.get_collection("athena_concepts")
        except Exception:
            self.collection = None

        available = self._list_available_domains()
        if available:
            print(f"ChromaDB vector store loaded: {len(available)} domain collections ({', '.join(available)})")
        elif self.collection:
            print(f"ChromaDB vector store loaded (legacy): {self.collection.count():,} concepts")

    def _get_collection(self, domain: Optional[str] = None):
        """Get domain-specific ChromaDB collection, with fallback to legacy collection."""
        if not hasattr(self, '_domain_collection_map'):
            return getattr(self, 'collection', None)
        if domain and domain in self._domain_collection_map:
            if domain not in self._collections:
                try:
                    collection_name = self._domain_collection_map[domain]
                    self._collections[domain] = self.chroma_client.get_collection(collection_name)
                except Exception:
                    return self.collection
            return self._collections[domain]
        return self.collection

    def _list_available_domains(self) -> List[str]:
        """List domains that have built collections."""
        if not hasattr(self, '_domain_collection_map'):
            return []
        available = []
        for domain, collection_name in self._domain_collection_map.items():
            try:
                col = self.chroma_client.get_collection(collection_name)
                if col.count() > 0:
                    available.append(domain)
            except Exception:
                pass
        return available

    def search(
        self,
        query: str,
        top_k: int = 5,
        domain_filter: Optional[str] = None,
        vocab_filter: Optional[str] = None,
        min_similarity: float = 0.0,
    ) -> List[dict]:
        """
        Search for similar OMOP concepts.

        Routes to PostgreSQL+pgvector or ChromaDB based on OMOP_POSTGRESQL flag.

        Args:
            query: Search query text
            top_k: Number of results to return
            domain_filter: Filter by domain (e.g., "Condition", "Drug")
            vocab_filter: Filter by vocabulary (e.g., "SNOMED", "LOINC")
            min_similarity: Minimum similarity threshold (0-1)

        Returns:
            List of matching concepts with metadata
        """
        # Generate query embedding
        response = self.azure_client.embeddings.create(
            input=[query],
            model=self.deployment,
        )
        query_embedding = response.data[0].embedding

        # Route to PostgreSQL or ChromaDB
        if self._use_postgresql and self._pg_store:
            return self._pg_search(query_embedding, top_k, domain_filter, vocab_filter, min_similarity)
        else:
            return self._chromadb_search(query_embedding, top_k, domain_filter, vocab_filter, min_similarity)

    def _pg_search(
        self,
        query_embedding: List[float],
        top_k: int,
        domain_filter: Optional[str],
        vocab_filter: Optional[str],
        min_similarity: float,
    ) -> List[dict]:
        """Search using PostgreSQL+pgvector backend."""
        results = self._pg_store.search(
            query_embedding=query_embedding,
            top_k=top_k,
            domain_filter=domain_filter,
            vocab_filter=vocab_filter,
        )
        # Filter by min_similarity
        if min_similarity > 0:
            results = [r for r in results if r["similarity"] >= min_similarity]
        return results

    def _chromadb_search(
        self,
        query_embedding: List[float],
        top_k: int,
        domain_filter: Optional[str],
        vocab_filter: Optional[str],
        min_similarity: float,
    ) -> List[dict]:
        """Search using ChromaDB backend."""
        collection = self._get_collection(domain_filter)
        if collection is None:
            return []

        # Build filter — skip domain_id filter if using domain-specific collection
        where_filter = None
        using_domain_collection = domain_filter and domain_filter in self._collections
        if vocab_filter and domain_filter and not using_domain_collection:
            where_filter = {"$and": [{"domain_id": domain_filter}, {"vocabulary_id": vocab_filter}]}
        elif vocab_filter:
            where_filter = {"vocabulary_id": vocab_filter}
        elif domain_filter and not using_domain_collection:
            where_filter = {"domain_id": domain_filter}

        # Query ChromaDB
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        # Format results
        formatted = []
        if results["documents"] and results["documents"][0]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                # Convert L2 distance to similarity (approximate)
                # ChromaDB uses L2 distance by default
                similarity = max(0, 1 - (dist / 2))  # Normalize to 0-1 range

                if similarity >= min_similarity:
                    formatted.append({
                        "concept_id": meta.get("concept_id"),
                        "concept_name": meta.get("concept_name"),
                        "concept_code": meta.get("concept_code"),
                        "vocabulary_id": meta.get("vocabulary_id"),
                        "domain_id": meta.get("domain_id"),
                        "concept_class_id": meta.get("concept_class_id"),
                        "standard_concept": meta.get("standard_concept"),
                        "similarity": round(similarity, 4),
                        "distance": round(dist, 4),
                    })

        return formatted

    def get_stats(self) -> dict:
        """Get vector store statistics."""
        if self._use_postgresql and self._pg_store:
            return self._pg_stats()
        return self._chromadb_stats()

    def _pg_stats(self) -> dict:
        """Get statistics from PostgreSQL backend."""
        return {
            "total_concepts": self._pg_store.concept_count,
            "domains": dict(sorted(self._pg_store.domain_counts.items(), key=lambda x: -x[1])),
            "vocabularies": {},  # Would require additional query
            "backend": "PostgreSQL+pgvector",
        }

    def _chromadb_stats(self) -> dict:
        """Get statistics from ChromaDB backend."""
        if not hasattr(self, 'collection') or self.collection is None:
            return {"total_concepts": 0, "domains": {}, "vocabularies": {}, "backend": "ChromaDB"}

        total = self.collection.count()

        # Sample to get domain/vocab distribution
        sample = self.collection.get(
            limit=min(10000, total),
            include=["metadatas"],
        )

        domains = {}
        vocabs = {}
        for meta in sample["metadatas"]:
            domain = meta.get("domain_id", "Unknown")
            vocab = meta.get("vocabulary_id", "Unknown")
            domains[domain] = domains.get(domain, 0) + 1
            vocabs[vocab] = vocabs.get(vocab, 0) + 1

        return {
            "total_concepts": total,
            "domains": dict(sorted(domains.items(), key=lambda x: -x[1])[:10]),
            "vocabularies": dict(sorted(vocabs.items(), key=lambda x: -x[1])[:10]),
            "backend": "ChromaDB",
        }


def print_results(results: List[dict], query: str):
    """Pretty print search results."""
    print(f"\nQuery: '{query}'")
    print("-" * 80)

    if not results:
        print("  No results found")
        return

    for i, r in enumerate(results, 1):
        print(f"\n  {i}. {r['concept_name']}")
        print(f"     ID: {r['concept_id']} | Code: {r['concept_code']}")
        print(f"     Vocabulary: {r['vocabulary_id']} | Domain: {r['domain_id']}")
        print(f"     Similarity: {r['similarity']:.3f}")


def interactive_mode(query_interface: VectorStoreQuery):
    """Run interactive query mode."""
    print("\n" + "=" * 60)
    print(" OMOP RAG Vector Store - Interactive Query")
    print("=" * 60)
    print("\nCommands:")
    print("  <query>              - Search for concepts")
    print("  /domain <name>       - Set domain filter (e.g., /domain Condition)")
    print("  /vocab <name>        - Set vocabulary filter (e.g., /vocab SNOMED)")
    print("  /clear               - Clear filters")
    print("  /stats               - Show vector store statistics")
    print("  /help                - Show this help")
    print("  /quit or /exit       - Exit")
    print("-" * 60)

    domain_filter = None
    vocab_filter = None

    while True:
        try:
            prompt = "\nQuery"
            if domain_filter or vocab_filter:
                filters = []
                if domain_filter:
                    filters.append(f"domain={domain_filter}")
                if vocab_filter:
                    filters.append(f"vocab={vocab_filter}")
                prompt += f" [{', '.join(filters)}]"
            prompt += ": "

            query = input(prompt).strip()

            if not query:
                continue

            # Handle commands
            if query.startswith("/"):
                parts = query.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else None

                if cmd in ["/quit", "/exit", "/q"]:
                    print("Goodbye!")
                    break
                elif cmd == "/domain":
                    domain_filter = arg
                    print(f"Domain filter set to: {domain_filter}")
                elif cmd == "/vocab":
                    vocab_filter = arg
                    print(f"Vocabulary filter set to: {vocab_filter}")
                elif cmd == "/clear":
                    domain_filter = None
                    vocab_filter = None
                    print("Filters cleared")
                elif cmd == "/stats":
                    stats = query_interface.get_stats()
                    print(f"\nTotal concepts: {stats['total_concepts']:,}")
                    print("\nTop domains:")
                    for d, c in stats["domains"].items():
                        print(f"  - {d}: {c:,}")
                    print("\nTop vocabularies:")
                    for v, c in stats["vocabularies"].items():
                        print(f"  - {v}: {c:,}")
                elif cmd == "/help":
                    print("\nCommands:")
                    print("  <query>              - Search for concepts")
                    print("  /domain <name>       - Set domain filter")
                    print("  /vocab <name>        - Set vocabulary filter")
                    print("  /clear               - Clear filters")
                    print("  /stats               - Show statistics")
                    print("  /quit                - Exit")
                else:
                    print(f"Unknown command: {cmd}")
                continue

            # Execute search
            results = query_interface.search(
                query=query,
                top_k=5,
                domain_filter=domain_filter,
                vocab_filter=vocab_filter,
            )
            print_results(results, query)

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Query OMOP RAG vector store",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--query", "-q",
        help="Single query (non-interactive mode)"
    )
    parser.add_argument(
        "--domain", "-d",
        help="Filter by domain (e.g., Condition, Drug, Measurement)"
    )
    parser.add_argument(
        "--vocab", "-v",
        help="Filter by vocabulary (e.g., SNOMED, LOINC)"
    )
    parser.add_argument(
        "--top-k", "-k",
        type=int,
        default=5,
        help="Number of results (default: 5)"
    )
    parser.add_argument(
        "--store-path", "-s",
        help="Path to vector store directory"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show vector store statistics"
    )

    args = parser.parse_args()

    try:
        query_interface = VectorStoreQuery(args.store_path)

        if args.stats:
            stats = query_interface.get_stats()
            print(f"\nVector Store Statistics")
            print("=" * 40)
            print(f"Total concepts: {stats['total_concepts']:,}")
            print("\nDomains:")
            for d, c in stats["domains"].items():
                print(f"  - {d}: {c:,}")
            print("\nVocabularies:")
            for v, c in stats["vocabularies"].items():
                print(f"  - {v}: {c:,}")
            return 0

        if args.query:
            # Single query mode
            results = query_interface.search(
                query=args.query,
                top_k=args.top_k,
                domain_filter=args.domain,
                vocab_filter=args.vocab,
            )
            print_results(results, args.query)
        else:
            # Interactive mode
            interactive_mode(query_interface)

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
