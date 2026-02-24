"""
Bookmark Generator

Creates PDF bookmark tree organized by extraction module
for easy navigation to annotated sections.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import fitz  # PyMuPDF

from .provenance_collector import ProvenanceItem
from .annotation_renderer import AnnotationResult

logger = logging.getLogger(__name__)


@dataclass
class BookmarkEntry:
    """Represents a single bookmark entry."""

    title: str
    page_number: int  # 0-indexed for PyMuPDF
    level: int  # Bookmark hierarchy level (0 = root)
    children: list = None

    def __post_init__(self):
        if self.children is None:
            self.children = []


# Human-readable names for modules
MODULE_DISPLAY_NAMES = {
    "study_metadata": "Study Metadata",
    "arms_design": "Arms & Design",
    "endpoints_estimands_sap": "Endpoints & Estimands",
    "adverse_events": "Adverse Events",
    "safety_decision_points": "Safety Decision Points",
    "concomitant_medications": "Concomitant Medications",
    "biospecimen_handling": "Biospecimen Handling",
    "laboratory_specifications": "Laboratory Specifications",
    "informed_consent": "Informed Consent",
    "pro_specifications": "PRO Specifications",
    "data_management": "Data Management",
    "site_operations_logistics": "Site Operations",
    "quality_management": "Quality Management",
    "withdrawal_procedures": "Withdrawal Procedures",
    "imaging_central_reading": "Imaging & Central Reading",
    "pkpd_sampling": "PK/PD Sampling",
    "root": "Protocol Root",
}


class BookmarkGenerator:
    """
    Generates PDF bookmarks organized by extraction module.

    Bookmark Structure:
    - Provenance Annotations (root)
      - study_metadata (N annotations)
        - Page X: field1, field2
        - Page Y: field3
      - arms_design (M annotations)
        - Page Z: field4
      ...
    """

    ROOT_BOOKMARK_TITLE = "Provenance Annotations"

    def __init__(self):
        self._bookmarks: list[BookmarkEntry] = []

    def generate_bookmarks(
        self,
        doc: fitz.Document,
        annotation_results: list[AnnotationResult],
        provenance_by_module: dict[str, list[ProvenanceItem]]
    ) -> int:
        """
        Generate bookmarks for annotated PDF.

        Args:
            doc: PyMuPDF document
            annotation_results: Results from annotation rendering
            provenance_by_module: Provenance items grouped by module

        Returns:
            Number of bookmarks created
        """
        # Build bookmark structure
        root_entry = self._build_bookmark_tree(annotation_results, provenance_by_module)

        if not root_entry.children:
            logger.info("No bookmarks to create - no successful annotations")
            self._bookmarks = []
            return 0

        # Store for summary access
        self._bookmarks = [root_entry]

        # Clear existing bookmarks
        doc.set_toc([])

        # Convert to PyMuPDF TOC format and set
        toc = self._to_toc_format(root_entry)
        doc.set_toc(toc)

        bookmark_count = len(toc)
        logger.info(f"Created {bookmark_count} bookmarks organized by module")

        return bookmark_count

    def _build_bookmark_tree(
        self,
        annotation_results: list[AnnotationResult],
        provenance_by_module: dict[str, list[ProvenanceItem]]
    ) -> BookmarkEntry:
        """
        Build the bookmark tree structure.

        Args:
            annotation_results: Results from annotation rendering
            provenance_by_module: Provenance items grouped by module

        Returns:
            Root bookmark entry with children
        """
        # Create successful annotations lookup
        successful_items = {
            (r.provenance_item.page_number, r.provenance_item.field_path): r
            for r in annotation_results
            if r.success
        }

        # Create root entry
        root = BookmarkEntry(
            title=self.ROOT_BOOKMARK_TITLE,
            page_number=0,
            level=0
        )

        # Add module entries
        for module_name in sorted(provenance_by_module.keys()):
            items = provenance_by_module[module_name]

            # Filter to only successfully annotated items
            successful_module_items = [
                item for item in items
                if (item.page_number, item.field_path) in successful_items
            ]

            if not successful_module_items:
                continue

            # Create module entry
            display_name = MODULE_DISPLAY_NAMES.get(module_name, module_name.replace("_", " ").title())
            annotation_count = len(successful_module_items)

            module_entry = BookmarkEntry(
                title=f"{display_name} ({annotation_count} annotations)",
                page_number=min(item.page_number for item in successful_module_items) - 1,  # 0-indexed
                level=1
            )

            # Group items by page within this module
            items_by_page = self._group_by_page(successful_module_items)

            for page_num in sorted(items_by_page.keys()):
                page_items = items_by_page[page_num]
                field_names = [item.field_name for item in page_items[:5]]  # Limit to 5 fields

                if len(page_items) > 5:
                    field_names.append(f"+{len(page_items) - 5} more")

                page_entry = BookmarkEntry(
                    title=f"Page {page_num}: {', '.join(field_names)}",
                    page_number=page_num - 1,  # 0-indexed
                    level=2
                )

                module_entry.children.append(page_entry)

            root.children.append(module_entry)

        return root

    def _group_by_page(self, items: list[ProvenanceItem]) -> dict[int, list[ProvenanceItem]]:
        """Group provenance items by page number."""
        grouped = {}
        for item in items:
            if item.page_number not in grouped:
                grouped[item.page_number] = []
            grouped[item.page_number].append(item)
        return grouped

    def _to_toc_format(self, entry: BookmarkEntry, result: list = None) -> list:
        """
        Convert bookmark tree to PyMuPDF TOC format.

        PyMuPDF TOC format: [[level, title, page_number], ...]

        Args:
            entry: Root bookmark entry
            result: Accumulator list (for recursion)

        Returns:
            List in PyMuPDF TOC format
        """
        if result is None:
            result = []

        # Add this entry
        result.append([entry.level + 1, entry.title, entry.page_number + 1])

        # Add children
        for child in entry.children:
            self._to_toc_format(child, result)

        return result

    def get_bookmark_summary(self) -> dict:
        """
        Get a summary of the generated bookmarks.

        Returns:
            Summary dictionary
        """
        if not self._bookmarks:
            return {"total_bookmarks": 0, "modules": []}

        # Count bookmarks at each level
        level_counts = {}
        module_names = []

        def count_recursive(entry):
            level_counts[entry.level] = level_counts.get(entry.level, 0) + 1
            if entry.level == 1:
                module_names.append(entry.title)
            for child in entry.children:
                count_recursive(child)

        if self._bookmarks:
            count_recursive(self._bookmarks[0] if isinstance(self._bookmarks[0], BookmarkEntry)
                          else BookmarkEntry("Root", 0, 0, self._bookmarks))

        return {
            "total_bookmarks": sum(level_counts.values()),
            "level_distribution": level_counts,
            "modules": module_names
        }


def add_document_metadata(doc: fitz.Document, protocol_id: str, timestamp: str) -> None:
    """
    Update PDF document metadata with annotation information.

    Args:
        doc: PyMuPDF document
        protocol_id: Protocol identifier
        timestamp: Annotation timestamp
    """
    metadata = doc.metadata or {}

    # Update metadata (only standard PDF keys allowed by PyMuPDF)
    metadata["title"] = f"{protocol_id} - Annotated Protocol"
    metadata["subject"] = f"Protocol with provenance annotations (annotated: {timestamp})"
    metadata["keywords"] = "clinical trial, protocol, provenance, USDM"
    metadata["creator"] = "Protocol Extraction Pipeline"
    metadata["producer"] = "PyMuPDF with Provenance Annotations"

    doc.set_metadata(metadata)

    logger.debug(f"Updated document metadata for {protocol_id}")
