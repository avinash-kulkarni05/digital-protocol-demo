"""
SOA Quick Annotator

Fast page-level annotation for Stage 1 (page detection).
Adds visual indicators (cyan borders and labels) to detected SOA pages
without requiring text search or full provenance data.

This is used during the human-in-the-loop verification step when
only page numbers are known (before full extraction runs).
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class SOAPageInfo:
    """Information about a detected SOA table."""
    id: str  # e.g., "SOA-1"
    page_start: int  # 1-indexed
    page_end: int  # 1-indexed
    category: str  # e.g., "MAIN_SOA", "PK_SOA"


@dataclass
class QuickAnnotationResult:
    """Result of quick annotation."""
    success: bool
    pdf_bytes: Optional[bytes] = None
    pages_annotated: int = 0
    error: Optional[str] = None


class SOAQuickAnnotator:
    """
    Fast page-level annotator for SOA detection verification.

    Adds visual indicators to detected SOA pages:
    - Light cyan border around page content area
    - "SOA-X Detected" label in top-right corner
    - Distinct from yellow (main pipeline) and light blue (full SOA annotations)

    Performance: ~100ms for 20 pages (no text search required)
    """

    # Light cyan color (distinct from yellow main and light blue Stage 2)
    BORDER_COLOR = (0.7, 0.9, 1.0)  # RGB
    FILL_COLOR = (0.9, 0.97, 1.0)  # Very light cyan for label background
    TEXT_COLOR = (0.2, 0.4, 0.6)  # Dark blue-gray for text
    BORDER_WIDTH = 3.0

    def annotate_detected_pages(
        self,
        pdf_bytes: bytes,
        detected_pages: List[dict]
    ) -> QuickAnnotationResult:
        """
        Add visual indicators to detected SOA pages.

        Args:
            pdf_bytes: Original PDF as bytes
            detected_pages: List of detected SOA tables, each with:
                - id: str (e.g., "SOA-1")
                - pageStart: int (1-indexed)
                - pageEnd: int (1-indexed)
                - category: str (e.g., "MAIN_SOA")

        Returns:
            QuickAnnotationResult with annotated PDF bytes
        """
        try:
            # Parse detected pages into structured format
            soa_pages = self._parse_detected_pages(detected_pages)

            if not soa_pages:
                logger.warning("No valid SOA pages to annotate")
                return QuickAnnotationResult(
                    success=True,
                    pdf_bytes=pdf_bytes,
                    pages_annotated=0
                )

            # Open PDF from bytes
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            pages_annotated = 0

            # Build page-to-SOA mapping
            page_soa_map = self._build_page_map(soa_pages, doc.page_count)

            # Annotate each page
            for page_num, soa_info in page_soa_map.items():
                try:
                    page = doc[page_num]  # 0-indexed
                    self._annotate_page(page, soa_info)
                    pages_annotated += 1
                except Exception as e:
                    logger.warning(f"Failed to annotate page {page_num + 1}: {e}")

            # Get annotated PDF as bytes
            annotated_bytes = doc.tobytes()
            doc.close()

            logger.info(f"Quick annotation complete: {pages_annotated} pages annotated")

            return QuickAnnotationResult(
                success=True,
                pdf_bytes=annotated_bytes,
                pages_annotated=pages_annotated
            )

        except Exception as e:
            logger.error(f"Quick annotation failed: {e}")
            return QuickAnnotationResult(
                success=False,
                error=str(e)
            )

    def _parse_detected_pages(self, detected_pages: List[dict]) -> List[SOAPageInfo]:
        """Parse raw detected pages into structured format."""
        result = []
        for item in detected_pages:
            try:
                # Handle both camelCase and snake_case keys
                soa_id = item.get("id") or item.get("soa_id", f"SOA-{len(result) + 1}")
                page_start = item.get("pageStart") or item.get("page_start", 0)
                page_end = item.get("pageEnd") or item.get("page_end", page_start)
                category = item.get("category") or item.get("tableCategory", "SOA")

                if page_start > 0:
                    result.append(SOAPageInfo(
                        id=soa_id,
                        page_start=page_start,
                        page_end=page_end,
                        category=category
                    ))
            except Exception as e:
                logger.warning(f"Failed to parse SOA page info: {e}")

        return result

    def _build_page_map(
        self,
        soa_pages: List[SOAPageInfo],
        total_pages: int
    ) -> dict:
        """Build mapping of page numbers to SOA info."""
        page_map = {}

        for soa in soa_pages:
            for page_num in range(soa.page_start - 1, soa.page_end):  # Convert to 0-indexed
                if 0 <= page_num < total_pages:
                    # If page already has an SOA, keep track of all
                    if page_num in page_map:
                        page_map[page_num].append(soa)
                    else:
                        page_map[page_num] = [soa]

        return page_map

    def _annotate_page(self, page: fitz.Page, soa_list: List[SOAPageInfo]) -> None:
        """
        Add visual indicators to a single page.

        Args:
            page: PyMuPDF page object
            soa_list: List of SOA tables that include this page
        """
        rect = page.rect

        # Draw border around page content area (with margin)
        margin = 10
        border_rect = fitz.Rect(
            rect.x0 + margin,
            rect.y0 + margin,
            rect.x1 - margin,
            rect.y1 - margin
        )

        # Draw the border
        shape = page.new_shape()
        shape.draw_rect(border_rect)
        shape.finish(
            color=self.BORDER_COLOR,
            width=self.BORDER_WIDTH,
            stroke_opacity=0.8
        )
        shape.commit()

        # Add label in top-right corner
        label_text = ", ".join([soa.id for soa in soa_list])
        if len(label_text) > 30:
            label_text = label_text[:27] + "..."

        # Calculate label position and size
        font_size = 10
        text_width = fitz.get_text_length(label_text, fontname="helv", fontsize=font_size)
        padding = 6

        label_rect = fitz.Rect(
            rect.x1 - text_width - padding * 3 - margin,
            rect.y0 + margin + 5,
            rect.x1 - margin - 5,
            rect.y0 + margin + font_size + padding * 2 + 5
        )

        # Draw label background
        shape = page.new_shape()
        shape.draw_rect(label_rect)
        shape.finish(
            color=self.BORDER_COLOR,
            fill=self.FILL_COLOR,
            width=1.5,
            stroke_opacity=0.9,
            fill_opacity=0.95
        )
        shape.commit()

        # Insert label text
        text_point = fitz.Point(
            label_rect.x0 + padding,
            label_rect.y0 + padding + font_size - 2
        )
        page.insert_text(
            text_point,
            label_text,
            fontname="helv",
            fontsize=font_size,
            color=self.TEXT_COLOR
        )


def annotate_soa_pages_quick(
    pdf_bytes: bytes,
    detected_pages: List[dict]
) -> QuickAnnotationResult:
    """
    Convenience function for quick SOA page annotation.

    Args:
        pdf_bytes: Original PDF as bytes
        detected_pages: List of detected SOA tables

    Returns:
        QuickAnnotationResult with annotated PDF bytes
    """
    annotator = SOAQuickAnnotator()
    return annotator.annotate_detected_pages(pdf_bytes, detected_pages)
