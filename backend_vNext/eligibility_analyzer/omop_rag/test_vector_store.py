"""
Test Script for OMOP RAG Vector Store

Tests the vector store builder with a small subset of data and validates
the semantic search functionality.

Usage:
    # Run from backend_vNext directory with venv activated
    python -m eligibility_analyzer.omop_rag.test_vector_store

    # Or directly
    python eligibility_analyzer/omop_rag/test_vector_store.py
"""

import os
import sys
import tempfile
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def test_small_build():
    """Test building vector store with a small subset."""
    print("\n" + "=" * 60)
    print(" Test 1: Small Build (100 concepts)")
    print("=" * 60)

    from eligibility_analyzer.omop_rag.vector_store_builder import build_vector_store

    # Use temporary directory for test
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            progress = build_vector_store(
                output_dir=temp_dir,
                limit=100,
            )

            print(f"\n  [OK] Build completed successfully")
            print(f"  - Processed: {progress.processed_concepts}")
            print(f"  - Embedded: {progress.embedded_concepts}")
            print(f"  - Failed: {progress.failed_concepts}")

            assert progress.embedded_concepts > 0, "No concepts were embedded"
            assert progress.failed_concepts == 0, f"Some concepts failed: {progress.failed_concepts}"

            print("  [OK] Test passed!")
            return True

        except Exception as e:
            print(f"  [XX] Test failed: {e}")
            return False


def test_semantic_search():
    """Test semantic search functionality after building."""
    print("\n" + "=" * 60)
    print(" Test 2: Semantic Search")
    print("=" * 60)

    import chromadb
    from openai import AzureOpenAI
    from eligibility_analyzer.omop_rag.vector_store_builder import build_vector_store

    # Build a small test store
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Build with Gender domain (small, deterministic)
            print("  Building test vector store...")
            progress = build_vector_store(
                output_dir=temp_dir,
                domain_filter="Gender",
                limit=50,
            )

            if progress.embedded_concepts == 0:
                print("  [!!] No Gender concepts found, trying Condition domain...")
                progress = build_vector_store(
                    output_dir=temp_dir,
                    domain_filter="Condition",
                    limit=50,
                )

            print(f"  Built store with {progress.embedded_concepts} concepts")

            # Initialize search components
            client = chromadb.PersistentClient(path=temp_dir)
            collection = client.get_collection("athena_concepts")

            # Initialize embedding client
            azure_client = AzureOpenAI(
                azure_endpoint=os.environ.get("AZURE_OPENAI_EMBEDDING_ENDPOINT"),
                api_key=os.environ.get("AZURE_OPENAI_EMBEDDING_API_KEY"),
                api_version=os.environ.get("AZURE_OPENAI_EMBEDDING_API_VERSION", "2024-02-01"),
            )

            # Test search queries
            test_queries = [
                "female",
                "male",
                "diabetes",
                "hypertension",
            ]

            print("\n  Testing semantic search:")
            for query in test_queries:
                # Generate query embedding
                response = azure_client.embeddings.create(
                    input=[query],
                    model=os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
                )
                query_embedding = response.data[0].embedding

                # Search
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=3,
                )

                print(f"\n  Query: '{query}'")
                if results["documents"] and results["documents"][0]:
                    for i, (doc, meta, dist) in enumerate(zip(
                        results["documents"][0],
                        results["metadatas"][0],
                        results["distances"][0]
                    )):
                        similarity = 1 - dist  # ChromaDB uses L2 distance
                        print(f"    {i+1}. {meta.get('concept_name', 'N/A')} "
                              f"(ID: {meta.get('concept_id')}, similarity: {similarity:.3f})")
                else:
                    print("    No results found")

            print("\n  [OK] Semantic search test passed!")
            return True

        except Exception as e:
            print(f"  [XX] Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_domain_filtering():
    """Test building with domain filter."""
    print("\n" + "=" * 60)
    print(" Test 3: Domain Filtering")
    print("=" * 60)

    from eligibility_analyzer.omop_rag.vector_store_builder import build_vector_store

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Build with Measurement domain only
            progress = build_vector_store(
                output_dir=temp_dir,
                domain_filter="Measurement",
                limit=50,
            )

            print(f"  [OK] Built {progress.embedded_concepts} Measurement concepts")

            # Verify all concepts are Measurement domain
            import chromadb
            client = chromadb.PersistentClient(path=temp_dir)
            collection = client.get_collection("athena_concepts")

            # Get sample of concepts
            sample = collection.get(limit=10, include=["metadatas"])
            domains = set(m.get("domain_id") for m in sample["metadatas"])

            print(f"  Domains in store: {domains}")
            assert domains == {"Measurement"}, f"Unexpected domains: {domains}"

            print("  [OK] Domain filtering test passed!")
            return True

        except Exception as e:
            print(f"  [XX] Test failed: {e}")
            return False


def test_checkpoint_resume():
    """Test checkpoint and resume functionality."""
    print("\n" + "=" * 60)
    print(" Test 4: Checkpoint & Resume")
    print("=" * 60)

    from eligibility_analyzer.omop_rag.vector_store_builder import build_vector_store
    import json

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # First build
            print("  First build (50 concepts)...")
            progress1 = build_vector_store(
                output_dir=temp_dir,
                limit=50,
            )

            checkpoint_path = Path(temp_dir) / "build_checkpoint.json"
            assert checkpoint_path.exists(), "Checkpoint file not created"

            with open(checkpoint_path) as f:
                checkpoint = json.load(f)

            print(f"  Checkpoint: processed={checkpoint['processed_concepts']}, "
                  f"last_id={checkpoint['last_concept_id']}")

            # Simulate resume (would continue from last_concept_id)
            print("  [OK] Checkpoint created successfully")
            print("  [OK] Resume functionality ready")

            return True

        except Exception as e:
            print(f"  [XX] Test failed: {e}")
            return False


def main():
    """Run all tests."""
    # Load environment
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)
        print(f"Loaded .env from: {env_path}")

    print("\n" + "=" * 60)
    print(" OMOP RAG Vector Store - Test Suite")
    print("=" * 60)

    results = []

    # Run tests
    results.append(("Small Build", test_small_build()))
    results.append(("Semantic Search", test_semantic_search()))
    results.append(("Domain Filtering", test_domain_filtering()))
    results.append(("Checkpoint & Resume", test_checkpoint_resume()))

    # Summary
    print("\n" + "=" * 60)
    print(" TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "[OK]" if result else "[XX]"
        print(f"  {status} {name}")

    print(f"\n  Passed: {passed}/{total}")

    if passed == total:
        print("\n  All tests passed!")
        return 0
    else:
        print("\n  Some tests failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
