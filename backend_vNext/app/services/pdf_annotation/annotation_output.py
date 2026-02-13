"""
Annotation Output

Generates annotation report JSON with detailed statistics
and per-item success/failure information.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .provenance_collector import ProvenanceItem, CollectionStats
from .page_classifier import PageClassification
from .annotation_renderer import AnnotationResult

logger = logging.getLogger(__name__)


@dataclass
class PageAnnotationSummary:
    """Summary of annotations for a single page."""

    page_number: int
    page_type: str
    annotations_attempted: int
    annotations_successful: int
    items: list = field(default_factory=list)


@dataclass
class FailedItem:
    """Details of a failed annotation attempt."""

    field_path: str
    module: str
    page_number: int
    snippet_preview: str
    reason: str


@dataclass
class AnnotationStatistics:
    """Overall annotation statistics."""

    total_provenance_items: int = 0
    unique_items_after_dedup: int = 0
    pages_with_annotations: int = 0
    successful_annotations: int = 0
    failed_annotations: int = 0
    success_rate: float = 0.0

    # Match method distribution
    exact_matches: int = 0
    normalized_matches: int = 0
    sentence_matches: int = 0
    fuzzy_matches: int = 0
    keyword_matches: int = 0
    ocr_matches: int = 0

    # Page type distribution
    text_based_pages: int = 0
    image_based_pages: int = 0
    mixed_pages: int = 0

    def calculate_success_rate(self):
        """Calculate success rate from counts."""
        total = self.successful_annotations + self.failed_annotations
        if total > 0:
            self.success_rate = (self.successful_annotations / total) * 100
        else:
            self.success_rate = 0.0


@dataclass
class AnnotationReport:
    """Complete annotation report."""

    source_pdf: str
    annotated_pdf: str
    timestamp: str
    statistics: AnnotationStatistics
    page_summary: list = field(default_factory=list)
    failed_items: list = field(default_factory=list)
    bookmarks_created: int = 0
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert report to dictionary for JSON serialization."""
        return {
            "source_pdf": self.source_pdf,
            "annotated_pdf": self.annotated_pdf,
            "timestamp": self.timestamp,
            "statistics": asdict(self.statistics),
            "page_summary": self.page_summary,
            "failed_items": self.failed_items,
            "bookmarks_created": self.bookmarks_created,
            "warnings": self.warnings
        }


class AnnotationOutput:
    """
    Generates and saves annotation reports.

    Creates detailed JSON reports with:
    - Overall statistics (success rate, match methods)
    - Per-page summaries with annotation details
    - Failed items with reasons
    - Warnings and issues encountered
    """

    def __init__(self):
        self._report: Optional[AnnotationReport] = None

    def create_report(
        self,
        source_pdf: str,
        annotated_pdf: str,
        collection_stats: CollectionStats,
        annotation_results: list[AnnotationResult],
        page_classifications: dict[int, PageClassification],
        bookmarks_created: int = 0
    ) -> AnnotationReport:
        """
        Create a comprehensive annotation report.

        Args:
            source_pdf: Path to original PDF
            annotated_pdf: Path to annotated PDF
            collection_stats: Statistics from provenance collection
            annotation_results: Results from annotation rendering
            page_classifications: Page type classifications
            bookmarks_created: Number of bookmarks added

        Returns:
            Complete AnnotationReport
        """
        timestamp = datetime.now().isoformat()

        # Calculate statistics
        statistics = self._calculate_statistics(
            collection_stats,
            annotation_results,
            page_classifications
        )

        # Build page summaries
        page_summary = self._build_page_summary(
            annotation_results,
            page_classifications
        )

        # Collect failed items
        failed_items = self._collect_failed_items(annotation_results)

        # Collect warnings
        warnings = self._collect_warnings(statistics, annotation_results)

        self._report = AnnotationReport(
            source_pdf=str(source_pdf),
            annotated_pdf=str(annotated_pdf),
            timestamp=timestamp,
            statistics=statistics,
            page_summary=page_summary,
            failed_items=failed_items,
            bookmarks_created=bookmarks_created,
            warnings=warnings
        )

        return self._report

    def save_report(self, output_path: Path) -> None:
        """
        Save the annotation report to a JSON file.

        Args:
            output_path: Path to save the JSON report
        """
        if not self._report:
            raise ValueError("No report to save. Call create_report() first.")

        report_dict = self._report.to_dict()

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_dict, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved annotation report to {output_path}")

    def get_report(self) -> Optional[AnnotationReport]:
        """Get the current report."""
        return self._report

    def _calculate_statistics(
        self,
        collection_stats: CollectionStats,
        annotation_results: list[AnnotationResult],
        page_classifications: dict[int, PageClassification]
    ) -> AnnotationStatistics:
        """Calculate overall statistics."""
        stats = AnnotationStatistics(
            total_provenance_items=collection_stats.total_found,
            unique_items_after_dedup=collection_stats.unique_after_dedup,
            pages_with_annotations=collection_stats.pages_covered
        )

        # Count successes and failures by match method
        for result in annotation_results:
            if result.success:
                stats.successful_annotations += 1

                if result.match:
                    method = result.match.match_method
                    if method == "exact":
                        stats.exact_matches += 1
                    elif method == "normalized":
                        stats.normalized_matches += 1
                    elif method == "sentence":
                        stats.sentence_matches += 1
                    elif method == "fuzzy":
                        stats.fuzzy_matches += 1
                    elif method == "keyword":
                        stats.keyword_matches += 1
                    elif method == "ocr":
                        stats.ocr_matches += 1
            else:
                stats.failed_annotations += 1

        # Count page types
        for classification in page_classifications.values():
            if classification.page_type.value == "text_based":
                stats.text_based_pages += 1
            elif classification.page_type.value == "image_based":
                stats.image_based_pages += 1
            elif classification.page_type.value == "mixed":
                stats.mixed_pages += 1

        stats.calculate_success_rate()

        return stats

    def _build_page_summary(
        self,
        annotation_results: list[AnnotationResult],
        page_classifications: dict[int, PageClassification]
    ) -> list[dict]:
        """Build per-page annotation summaries."""
        # Group results by page
        results_by_page: dict[int, list[AnnotationResult]] = {}

        for result in annotation_results:
            page_num = result.provenance_item.page_number
            if page_num not in results_by_page:
                results_by_page[page_num] = []
            results_by_page[page_num].append(result)

        # Build summaries
        summaries = []

        for page_num in sorted(results_by_page.keys()):
            page_results = results_by_page[page_num]
            classification = page_classifications.get(page_num)

            page_type = classification.page_type.value if classification else "unknown"
            successful = sum(1 for r in page_results if r.success)

            items = []
            for result in page_results:
                item = result.provenance_item
                item_data = {
                    "field_path": item.field_path,
                    "module": item.module_name,
                    "snippet_preview": item.text_snippet[:50] + "..." if len(item.text_snippet) > 50 else item.text_snippet,
                    "status": "success" if result.success else "failed"
                }

                if result.success and result.match:
                    item_data["match_method"] = result.match.match_method
                    item_data["confidence"] = round(result.match.confidence, 2)
                    item_data["rect"] = [
                        round(result.match.rect.x0, 1),
                        round(result.match.rect.y0, 1),
                        round(result.match.rect.x1, 1),
                        round(result.match.rect.y1, 1)
                    ]
                elif result.error:
                    item_data["error"] = result.error

                items.append(item_data)

            summary = {
                "page_number": page_num,
                "page_type": page_type,
                "annotations_attempted": len(page_results),
                "annotations_successful": successful,
                "items": items
            }

            summaries.append(summary)

        return summaries

    def _collect_failed_items(self, annotation_results: list[AnnotationResult]) -> list[dict]:
        """Collect details of failed annotation attempts."""
        failed = []

        for result in annotation_results:
            if not result.success:
                item = result.provenance_item

                failed.append({
                    "field_path": item.field_path,
                    "module": item.module_name,
                    "page_number": item.page_number,
                    "snippet": item.text_snippet[:200] + "..." if len(item.text_snippet) > 200 else item.text_snippet,
                    "reason": result.error or "No match found with any search strategy"
                })

        return failed

    def _collect_warnings(
        self,
        statistics: AnnotationStatistics,
        annotation_results: list[AnnotationResult]
    ) -> list[str]:
        """Collect warnings based on annotation results."""
        warnings = []

        # Low success rate warning
        if statistics.success_rate < 80:
            warnings.append(
                f"Low annotation success rate: {statistics.success_rate:.1f}% "
                f"({statistics.failed_annotations} items failed)"
            )

        # High OCR usage warning
        total_successful = statistics.successful_annotations
        if total_successful > 0:
            ocr_ratio = statistics.ocr_matches / total_successful
            if ocr_ratio > 0.5:
                warnings.append(
                    f"High OCR usage: {statistics.ocr_matches}/{total_successful} "
                    "matches required OCR (PDF may have many image-based pages)"
                )

        # Low exact match rate warning
        if total_successful > 0:
            exact_ratio = statistics.exact_matches / total_successful
            if exact_ratio < 0.3:
                warnings.append(
                    f"Low exact match rate: {statistics.exact_matches}/{total_successful} "
                    "(text snippets may not match PDF exactly)"
                )

        return warnings


def generate_annotation_filename(protocol_id: str) -> str:
    """
    Generate filename for annotated PDF.

    Args:
        protocol_id: Protocol identifier

    Returns:
        Filename string
    """
    # Clean protocol ID for filename
    clean_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in protocol_id)
    return f"{clean_id}_annotated.pdf"


def generate_report_filename(protocol_id: str) -> str:
    """
    Generate filename for annotation report.

    Args:
        protocol_id: Protocol identifier

    Returns:
        Filename string
    """
    clean_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in protocol_id)
    return f"{clean_id}_annotation_report.json"
