"""
SOA Annotation Service

Adds SOA-specific provenance annotations to an already-annotated PDF.
Uses light blue highlighting to distinguish from main pipeline's yellow highlights.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from .soa_provenance_adapter import SOAProvenanceAdapter, load_soa_usdm
from .provenance_collector import ProvenanceItem
from .page_classifier import PageClassifier, PageType
from .text_locator import TextLocator
from .annotation_renderer import AnnotationRenderer, AnnotationStyle, AnnotationResult
from .bookmark_generator import BookmarkGenerator, BookmarkEntry, MODULE_DISPLAY_NAMES

logger = logging.getLogger(__name__)

# Add SOA module to display names
MODULE_DISPLAY_NAMES["soa_schedule"] = "Schedule of Activities"


@dataclass
class SOAAnnotationResult:
    """Result of adding SOA annotations."""

    success: bool
    output_path: Optional[Path] = None
    soa_items_found: int = 0
    soa_annotations_added: int = 0
    soa_annotations_failed: int = 0
    success_rate: float = 0.0
    error: Optional[str] = None


class SOAAnnotationStyle(AnnotationStyle):
    """Style for SOA annotations - light blue instead of yellow."""

    def __init__(self):
        super().__init__()
        # Light blue for SOA highlights (distinguishes from yellow main pipeline)
        self.highlight_color = (0.7, 0.85, 1.0)  # Light blue RGB
        self.stroke_color = (0.5, 0.7, 0.9)  # Slightly darker blue for borders


class SOAAnnotationService:
    """
    Service to add SOA annotations to an existing annotated PDF.

    Features:
    - Uses light blue highlighting for SOA items (vs yellow for main pipeline)
    - Adds SOA bookmarks under existing bookmark tree
    - Generates detailed popup comments with activity/visit context
    - Never blocks - gracefully handles failures
    """

    def __init__(self, config: Optional[dict] = None):
        """Initialize SOA annotation service."""
        self.config = config or {}

        # Use SOA-specific style (light blue)
        self.style = SOAAnnotationStyle()

        # Reuse main pipeline components
        fuzzy_threshold = self.config.get("fuzzy_threshold", 0.85)
        self.classifier = PageClassifier()
        self.locator = TextLocator(fuzzy_threshold=fuzzy_threshold)
        self.renderer = AnnotationRenderer(style=self.style)
        self.adapter = SOAProvenanceAdapter()

    def add_soa_annotations(
        self,
        annotated_pdf_path: Path | str,
        soa_usdm_path: Path | str,
        output_path: Optional[Path | str] = None
    ) -> SOAAnnotationResult:
        """
        Add SOA annotations to an already-annotated PDF.

        Args:
            annotated_pdf_path: Path to the annotated PDF from main pipeline
            soa_usdm_path: Path to SOA USDM JSON file
            output_path: Optional output path (defaults to overwriting input)

        Returns:
            SOAAnnotationResult with statistics
        """
        annotated_pdf_path = Path(annotated_pdf_path)
        soa_usdm_path = Path(soa_usdm_path)

        if output_path:
            output_path = Path(output_path)
        else:
            # Overwrite the input file
            output_path = annotated_pdf_path

        logger.info(f"Adding SOA annotations to {annotated_pdf_path.name}")

        try:
            # Step 1: Load SOA USDM and extract provenance
            logger.info("Step 1: Loading SOA USDM and extracting provenance")
            soa_usdm = load_soa_usdm(soa_usdm_path)
            if not soa_usdm:
                return SOAAnnotationResult(
                    success=False,
                    error=f"Failed to load SOA USDM from {soa_usdm_path}"
                )

            all_items = self.adapter.collect_from_soa_usdm(soa_usdm)
            if not all_items:
                logger.warning("No SOA provenance items found")
                return SOAAnnotationResult(
                    success=True,
                    output_path=output_path,
                    soa_items_found=0,
                    error="No SOA provenance items found in USDM"
                )

            # Deduplicate and group
            unique_items = self.adapter.deduplicate(all_items)
            items_by_page = self.adapter.group_by_page(unique_items)
            stats = self.adapter.get_stats()

            logger.info(
                f"Found {stats.total_found} SOA items, "
                f"{stats.unique_after_dedup} unique, "
                f"across {stats.pages_covered} pages"
            )

            # Step 2: Open existing annotated PDF
            logger.info("Step 2: Opening annotated PDF")
            doc = fitz.open(annotated_pdf_path)

            if doc.is_encrypted:
                doc.close()
                return SOAAnnotationResult(
                    success=False,
                    error="PDF is encrypted"
                )

            # Step 3: Add SOA annotations page by page
            logger.info("Step 3: Adding SOA annotations")
            annotation_results = []

            for page_num in sorted(items_by_page.keys()):
                page_items = items_by_page[page_num]

                # Validate page number
                page_idx = page_num - 1
                if page_idx < 0 or page_idx >= len(doc):
                    logger.warning(f"SOA page {page_num} out of range")
                    for item in page_items:
                        annotation_results.append(AnnotationResult(
                            success=False,
                            provenance_item=item,
                            error=f"Page {page_num} out of range"
                        ))
                    continue

                page = doc[page_idx]
                classification = self.classifier.classify(page)

                # Locate and annotate each item
                matches_to_annotate = []

                for item in page_items:
                    # For SOA, we search for the activity/visit name in the SOA table
                    # The text_snippet contains the formatted name
                    search_text = self._extract_search_text(item)

                    matches = self.locator.locate_text(
                        page,
                        search_text,
                        classification.page_type
                    )

                    if matches:
                        matches_to_annotate.append((item, matches[0]))
                    else:
                        annotation_results.append(AnnotationResult(
                            success=False,
                            provenance_item=item,
                            error="No match found for SOA item"
                        ))

                # Render SOA annotations
                if matches_to_annotate:
                    page_results = self.renderer.annotate_page(
                        page,
                        matches_to_annotate,
                        classification.page_type
                    )
                    annotation_results.extend(page_results)

            # Step 4: Update bookmarks to include SOA section
            logger.info("Step 4: Updating bookmarks")
            self._add_soa_bookmarks(doc, annotation_results, items_by_page)

            # Step 5: Save updated PDF
            logger.info(f"Step 5: Saving to {output_path}")

            # If output is same as input, save to temp then rename
            if output_path == annotated_pdf_path:
                temp_path = output_path.with_suffix(".tmp.pdf")
                doc.save(temp_path, garbage=4, deflate=True)
                doc.close()
                temp_path.replace(output_path)
            else:
                doc.save(output_path, garbage=4, deflate=True)
                doc.close()

            # Calculate statistics
            successful = sum(1 for r in annotation_results if r.success)
            failed = sum(1 for r in annotation_results if not r.success)
            total = successful + failed
            success_rate = (successful / total * 100) if total > 0 else 0

            logger.info(
                f"SOA annotation complete: {successful}/{total} annotations "
                f"({success_rate:.1f}% success)"
            )

            return SOAAnnotationResult(
                success=True,
                output_path=output_path,
                soa_items_found=stats.total_found,
                soa_annotations_added=successful,
                soa_annotations_failed=failed,
                success_rate=success_rate
            )

        except Exception as e:
            logger.error(f"SOA annotation failed: {e}", exc_info=True)
            return SOAAnnotationResult(
                success=False,
                error=str(e)
            )

    def _extract_search_text(self, item: ProvenanceItem) -> str:
        """
        Extract the actual text to search for in the PDF.

        For SOA items, text_snippet contains formatted context like:
        - "Visit: Screening"
        - "Activity: Vital Signs [VS]"
        - "Vital Signs @ Screening"

        We extract the key name for searching.
        """
        snippet = item.text_snippet

        # Handle different formats
        if snippet.startswith("Visit: "):
            return snippet[7:]  # Remove "Visit: " prefix
        elif snippet.startswith("Activity: "):
            # Remove prefix and domain code suffix
            text = snippet[10:]
            if "[" in text:
                text = text.split("[")[0].strip()
            return text
        elif " @ " in snippet:
            # For instances, search for activity name
            return snippet.split(" @ ")[0]
        elif snippet.startswith("Footnote "):
            # For footnotes, extract marker
            parts = snippet.split(":")
            if len(parts) >= 2:
                return parts[0]  # "Footnote a"
            return snippet

        return snippet

    def _add_soa_bookmarks(
        self,
        doc: fitz.Document,
        annotation_results: list[AnnotationResult],
        items_by_page: dict[int, list[ProvenanceItem]]
    ) -> None:
        """
        Add SOA section to existing bookmark tree.

        Structure:
        - [Existing bookmarks]
        - Schedule of Activities (N annotations)
          - Page X: activity1, activity2
          - Page Y: activity3
        """
        # Get existing TOC
        existing_toc = doc.get_toc()

        # Filter successful annotations
        successful_items = [
            r.provenance_item for r in annotation_results if r.success
        ]

        if not successful_items:
            logger.info("No successful SOA annotations - skipping bookmark update")
            return

        # Build SOA bookmark entries
        soa_bookmarks = []

        # Root entry for SOA
        min_page = min(item.page_number for item in successful_items)
        soa_bookmarks.append([
            1,  # Level 1 (same as other module sections)
            f"Schedule of Activities ({len(successful_items)} annotations)",
            min_page
        ])

        # Group successful items by page
        successful_by_page = {}
        for item in successful_items:
            if item.page_number not in successful_by_page:
                successful_by_page[item.page_number] = []
            successful_by_page[item.page_number].append(item)

        # Add page-level entries
        for page_num in sorted(successful_by_page.keys()):
            page_items = successful_by_page[page_num]
            field_names = [item.field_name[:25] for item in page_items[:3]]
            if len(page_items) > 3:
                field_names.append(f"+{len(page_items) - 3} more")

            soa_bookmarks.append([
                2,  # Level 2 (child of SOA section)
                f"Page {page_num}: {', '.join(field_names)}",
                page_num
            ])

        # Combine existing and new bookmarks
        combined_toc = existing_toc + soa_bookmarks
        doc.set_toc(combined_toc)

        logger.info(f"Added {len(soa_bookmarks)} SOA bookmark entries")


def add_soa_annotations_to_pdf(
    annotated_pdf_path: Path | str,
    soa_usdm_path: Path | str,
    output_path: Optional[Path | str] = None,
    config: Optional[dict] = None
) -> SOAAnnotationResult:
    """
    Convenience function to add SOA annotations to an annotated PDF.

    Args:
        annotated_pdf_path: Path to annotated PDF from main pipeline
        soa_usdm_path: Path to SOA USDM JSON
        output_path: Optional output path (defaults to overwriting input)
        config: Optional configuration

    Returns:
        SOAAnnotationResult
    """
    service = SOAAnnotationService(config=config)
    return service.add_soa_annotations(
        annotated_pdf_path,
        soa_usdm_path,
        output_path
    )
