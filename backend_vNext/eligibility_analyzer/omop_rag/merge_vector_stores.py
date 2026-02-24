"""
Merge two ChromaDB vector stores containing different domain collections.

Reads all collections from the source store and upserts them into the target store.
Since domains are different across stores, each collection is copied as-is.
Embeddings are preserved — no re-embedding cost.

Usage:
    # Merge source into target (target is modified in-place)
    python merge_vector_stores.py --source ./vector_store_A --target ./vector_store_B

    # Merge into a new directory (copies target first, then merges source)
    python merge_vector_stores.py --source ./vector_store_A --target ./vector_store_B --output ./vector_store_merged

    # Dry run to see what would be merged
    python merge_vector_stores.py --source ./vector_store_A --target ./vector_store_B --dry-run
"""

import argparse
import logging
import shutil
import sys
import time
from pathlib import Path

import chromadb
from chromadb.config import Settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 5000  # ChromaDB get/upsert batch size


def list_collections_info(client: chromadb.ClientAPI) -> list[dict]:
    """List all collections with their document counts."""
    collections = client.list_collections()
    info = []
    for col in collections:
        collection = client.get_collection(col.name)
        info.append({
            "name": col.name,
            "count": collection.count(),
            "metadata": col.metadata,
        })
    return info


def merge_collection(
    source_client: chromadb.ClientAPI,
    target_client: chromadb.ClientAPI,
    collection_name: str,
    source_metadata: dict | None = None,
) -> int:
    """
    Copy a single collection from source to target.

    Returns number of documents merged.
    """
    source_col = source_client.get_collection(collection_name)
    total = source_col.count()

    if total == 0:
        logger.info(f"  [{collection_name}] Empty collection, skipping")
        return 0

    # Create or get target collection with same metadata
    target_col = target_client.get_or_create_collection(
        name=collection_name,
        metadata=source_metadata or {},
    )

    existing = target_col.count()
    if existing > 0:
        logger.info(f"  [{collection_name}] Target already has {existing:,} docs, will upsert (dedup by ID)")

    merged = 0
    offset = 0

    while offset < total:
        # Fetch batch from source (includes embeddings)
        batch = source_col.get(
            limit=BATCH_SIZE,
            offset=offset,
            include=["embeddings", "documents", "metadatas"],
        )

        ids = batch["ids"]
        if not ids:
            break

        # Upsert into target
        target_col.upsert(
            ids=ids,
            embeddings=batch["embeddings"],
            documents=batch["documents"],
            metadatas=batch["metadatas"],
        )

        merged += len(ids)
        offset += len(ids)
        logger.info(f"  [{collection_name}] {merged:,}/{total:,} ({merged * 100 / total:.1f}%)")

    return merged


def merge_stores(source_path: str, target_path: str, output_path: str | None = None, dry_run: bool = False):
    """
    Merge all collections from source into target.

    Args:
        source_path: Path to source ChromaDB persistent store
        target_path: Path to target ChromaDB persistent store
        output_path: If provided, copy target to this path first, then merge into it
        dry_run: If True, only show what would be merged
    """
    # Validate paths
    if not Path(source_path).exists():
        logger.error(f"Source not found: {source_path}")
        sys.exit(1)
    if not Path(target_path).exists():
        logger.error(f"Target not found: {target_path}")
        sys.exit(1)

    # If output path specified, copy target there first
    actual_target = target_path
    if output_path:
        if Path(output_path).exists():
            logger.error(f"Output path already exists: {output_path}. Remove it first or use a different path.")
            sys.exit(1)
        logger.info(f"Copying target to output: {output_path}")
        shutil.copytree(target_path, output_path)
        actual_target = output_path
        logger.info("Copy complete")

    # Open both stores
    source_client = chromadb.PersistentClient(
        path=source_path,
        settings=Settings(anonymized_telemetry=False),
    )
    target_client = chromadb.PersistentClient(
        path=actual_target,
        settings=Settings(anonymized_telemetry=False),
    )

    # Inventory
    source_collections = list_collections_info(source_client)
    target_collections = list_collections_info(target_client)

    source_names = {c["name"] for c in source_collections}
    target_names = {c["name"] for c in target_collections}

    logger.info("=" * 60)
    logger.info("SOURCE COLLECTIONS:")
    for c in source_collections:
        logger.info(f"  {c['name']}: {c['count']:,} docs")

    logger.info("TARGET COLLECTIONS:")
    for c in target_collections:
        logger.info(f"  {c['name']}: {c['count']:,} docs")

    new_collections = source_names - target_names
    overlapping = source_names & target_names
    if new_collections:
        logger.info(f"New collections to add: {', '.join(sorted(new_collections))}")
    if overlapping:
        logger.info(f"Overlapping collections (will upsert): {', '.join(sorted(overlapping))}")
    logger.info("=" * 60)

    if dry_run:
        logger.info("DRY RUN — no changes made")
        return

    # Merge each source collection into target
    start = time.time()
    total_merged = 0

    for col_info in source_collections:
        name = col_info["name"]
        logger.info(f"Merging: {name} ({col_info['count']:,} docs)")
        count = merge_collection(source_client, target_client, name, col_info.get("metadata"))
        total_merged += count

    elapsed = time.time() - start

    # Final report
    final_collections = list_collections_info(target_client)

    logger.info("")
    logger.info("=" * 60)
    logger.info("MERGE COMPLETE")
    logger.info(f"  Documents merged: {total_merged:,}")
    logger.info(f"  Elapsed: {elapsed:.1f}s")
    logger.info(f"  Target: {actual_target}")
    logger.info("")
    logger.info("FINAL COLLECTIONS:")
    total_docs = 0
    for c in sorted(final_collections, key=lambda x: x["name"]):
        logger.info(f"  {c['name']}: {c['count']:,} docs")
        total_docs += c["count"]
    logger.info(f"  TOTAL: {total_docs:,} docs")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Merge two ChromaDB vector stores with different domain collections",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Merge source into target (modifies target in-place)
    python merge_vector_stores.py --source ./vector_store_A --target ./vector_store_B

    # Merge into a new output directory (target is not modified)
    python merge_vector_stores.py --source ./vector_store_A --target ./vector_store_B --output ./merged

    # Preview what would be merged
    python merge_vector_stores.py --source ./vector_store_A --target ./vector_store_B --dry-run
        """,
    )

    parser.add_argument("--source", "-s", required=True, help="Source vector store directory (read-only)")
    parser.add_argument("--target", "-t", required=True, help="Target vector store directory (modified in-place unless --output is used)")
    parser.add_argument("--output", "-o", help="Output directory for merged store (copies target first, then merges source into it)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be merged without making changes")

    args = parser.parse_args()

    merge_stores(
        source_path=args.source,
        target_path=args.target,
        output_path=args.output,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
