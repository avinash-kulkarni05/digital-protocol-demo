"""
Annotation Renderer

Renders highlights and popup comments on PDF pages.
Supports native highlight annotations for text pages and
rectangle overlays for image pages.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import fitz  # PyMuPDF

from .page_classifier import PageType
from .provenance_collector import ProvenanceItem
from .text_locator import TextMatch

logger = logging.getLogger(__name__)


@dataclass
class AnnotationStyle:
    """Configuration for annotation appearance."""

    # Highlight color (RGB, 0.0-1.0)
    highlight_color: tuple = (1.0, 1.0, 0.0)  # Yellow

    # Highlight opacity (0.0-1.0)
    highlight_opacity: float = 0.3

    # Stroke color for image page overlays
    stroke_color: tuple = (1.0, 0.8, 0.0)  # Orange

    # Stroke width for image page overlays
    stroke_width: float = 1.5

    # Popup comment author
    popup_author: str = "Protocol Extraction"

    @classmethod
    def from_config(cls, config: dict) -> "AnnotationStyle":
        """Create style from configuration dictionary."""
        style = cls()

        if "highlight_color" in config:
            color = config["highlight_color"]
            if isinstance(color, list) and len(color) == 3:
                # Convert from 0-255 to 0.0-1.0 if needed
                if any(c > 1 for c in color):
                    color = [c / 255.0 for c in color]
                style.highlight_color = tuple(color)

        if "highlight_opacity" in config:
            style.highlight_opacity = float(config["highlight_opacity"])

        return style


@dataclass
class AnnotationResult:
    """Result of annotating a single item."""

    success: bool
    provenance_item: ProvenanceItem
    match: Optional[TextMatch] = None
    annotation_type: str = ""  # "highlight", "rect_overlay"
    error: Optional[str] = None


class AnnotationRenderer:
    """
    Renders annotations on PDF pages.

    For text-based pages: Uses native PDF highlight annotations
    For image-based pages: Draws semi-transparent rectangle overlays
    All annotations include popup comments with provenance metadata
    """

    def __init__(self, style: Optional[AnnotationStyle] = None):
        """
        Initialize the annotation renderer.

        Args:
            style: Annotation style configuration
        """
        self.style = style or AnnotationStyle()

    def annotate_page(
        self,
        page: fitz.Page,
        matches: list[tuple[ProvenanceItem, TextMatch]],
        page_type: PageType
    ) -> list[AnnotationResult]:
        """
        Apply all annotations to a page.

        Args:
            page: PyMuPDF page object
            matches: List of (ProvenanceItem, TextMatch) pairs
            page_type: Classification of the page

        Returns:
            List of AnnotationResult for each match
        """
        results = []

        # Merge overlapping rectangles to avoid visual clutter
        merged_matches = self._merge_overlapping_matches(matches)

        for item, match in merged_matches:
            try:
                if page_type in (PageType.TEXT_BASED, PageType.MIXED):
                    result = self._add_highlight_annotation(page, item, match)
                else:
                    result = self._add_rect_overlay(page, item, match)

                results.append(result)

            except Exception as e:
                logger.error(f"Failed to annotate '{item.field_name}' on page {page.number + 1}: {e}")
                results.append(AnnotationResult(
                    success=False,
                    provenance_item=item,
                    match=match,
                    error=str(e)
                ))

        return results

    def _add_highlight_annotation(
        self,
        page: fitz.Page,
        item: ProvenanceItem,
        match: TextMatch
    ) -> AnnotationResult:
        """
        Add native PDF highlight annotation for text pages.

        Args:
            page: PyMuPDF page object
            item: Provenance item being annotated
            match: Text match with location

        Returns:
            AnnotationResult
        """
        try:
            # Create highlight annotation
            if match.quads:
                # Use quads for precise highlighting
                annot = page.add_highlight_annot(match.quads)
            else:
                # Fall back to rectangle
                annot = page.add_highlight_annot(match.rect)

            # Set highlight color
            annot.set_colors(stroke=self.style.highlight_color)
            annot.set_opacity(self.style.highlight_opacity)

            # Add popup comment with provenance metadata
            popup_text = self._format_popup_comment(item, match)
            annot.set_info(
                title=self.style.popup_author,
                content=popup_text,
                subject=item.module_name
            )

            annot.update()

            logger.debug(f"Added highlight annotation for '{item.field_name}' on page {page.number + 1}")

            return AnnotationResult(
                success=True,
                provenance_item=item,
                match=match,
                annotation_type="highlight"
            )

        except Exception as e:
            logger.error(f"Failed to add highlight: {e}")
            return AnnotationResult(
                success=False,
                provenance_item=item,
                match=match,
                error=str(e)
            )

    def _add_rect_overlay(
        self,
        page: fitz.Page,
        item: ProvenanceItem,
        match: TextMatch
    ) -> AnnotationResult:
        """
        Draw semi-transparent rectangle overlay for image pages.

        Args:
            page: PyMuPDF page object
            item: Provenance item being annotated
            match: Text match with location

        Returns:
            AnnotationResult
        """
        try:
            rect = match.rect

            # Create shape for drawing
            shape = page.new_shape()

            # Draw filled rectangle with semi-transparency
            shape.draw_rect(rect)
            shape.finish(
                color=self.style.stroke_color,
                fill=self.style.highlight_color,
                fill_opacity=self.style.highlight_opacity,
                width=self.style.stroke_width
            )

            shape.commit()

            # Add a text annotation (sticky note) for the popup
            # Position it at the top-right corner of the rectangle
            note_point = fitz.Point(rect.x1 - 10, rect.y0 + 10)
            popup_text = self._format_popup_comment(item, match)

            annot = page.add_text_annot(
                note_point,
                popup_text,
                icon="Note"
            )
            annot.set_info(
                title=self.style.popup_author,
                subject=item.module_name
            )
            annot.set_colors(stroke=self.style.stroke_color)
            annot.update()

            logger.debug(f"Added rect overlay for '{item.field_name}' on page {page.number + 1}")

            return AnnotationResult(
                success=True,
                provenance_item=item,
                match=match,
                annotation_type="rect_overlay"
            )

        except Exception as e:
            logger.error(f"Failed to add rect overlay: {e}")
            return AnnotationResult(
                success=False,
                provenance_item=item,
                match=match,
                error=str(e)
            )

    def _format_popup_comment(self, item: ProvenanceItem, match: TextMatch) -> str:
        """
        Format the popup comment text with provenance metadata.

        Args:
            item: Provenance item
            match: Text match result

        Returns:
            Formatted popup text
        """
        lines = [
            "━━━ PROVENANCE ━━━",
            f"Field: {item.field_name}",
            f"Module: {item.module_name}",
            f"Path: {item.field_path}",
            f"Match: {match.match_method} ({match.confidence * 100:.0f}%)",
        ]

        if item.section_number:
            lines.insert(2, f"Section: {item.section_number}")

        lines.append("━━━━━━━━━━━━━━━━━━")

        return "\n".join(lines)

    def _merge_overlapping_matches(
        self,
        matches: list[tuple[ProvenanceItem, TextMatch]]
    ) -> list[tuple[ProvenanceItem, TextMatch]]:
        """
        Merge overlapping annotations to avoid visual clutter.

        When multiple provenance items highlight the same region,
        merge them into a single annotation with combined metadata.

        Args:
            matches: List of (item, match) pairs

        Returns:
            Merged list with overlapping regions combined
        """
        if len(matches) <= 1:
            return matches

        # Sort by rectangle position (top-left corner)
        sorted_matches = sorted(matches, key=lambda m: (m[1].rect.y0, m[1].rect.x0))

        merged = []
        current_group = [sorted_matches[0]]

        for i in range(1, len(sorted_matches)):
            item, match = sorted_matches[i]
            prev_item, prev_match = current_group[-1]

            # Check if rectangles overlap significantly
            if self._rects_overlap(prev_match.rect, match.rect, threshold=0.5):
                current_group.append((item, match))
            else:
                # Process current group
                merged.extend(self._merge_group(current_group))
                current_group = [(item, match)]

        # Process final group
        merged.extend(self._merge_group(current_group))

        if len(merged) < len(matches):
            logger.debug(f"Merged {len(matches)} annotations into {len(merged)}")

        return merged

    def _rects_overlap(self, rect1: fitz.Rect, rect2: fitz.Rect, threshold: float = 0.5) -> bool:
        """
        Check if two rectangles overlap significantly.

        Args:
            rect1: First rectangle
            rect2: Second rectangle
            threshold: Minimum overlap ratio (0.0-1.0)

        Returns:
            True if overlap exceeds threshold
        """
        # Calculate intersection
        intersection = rect1 & rect2

        if intersection.is_empty:
            return False

        # Calculate overlap ratio
        intersection_area = intersection.width * intersection.height
        smaller_area = min(
            rect1.width * rect1.height,
            rect2.width * rect2.height
        )

        if smaller_area == 0:
            return False

        overlap_ratio = intersection_area / smaller_area
        return overlap_ratio >= threshold

    def _merge_group(
        self,
        group: list[tuple[ProvenanceItem, TextMatch]]
    ) -> list[tuple[ProvenanceItem, TextMatch]]:
        """
        Merge a group of overlapping matches.

        For now, we keep all matches but could combine them into one
        with merged metadata. This preserves individual provenance info.

        Args:
            group: Group of overlapping matches

        Returns:
            Processed group (currently unchanged)
        """
        # For now, keep all matches to preserve individual provenance
        # Could enhance to create merged annotations with combined popups
        return group

    def remove_existing_annotations(self, page: fitz.Page) -> int:
        """
        Remove existing highlight and text annotations from a page.

        Useful for re-annotating a page without duplicates.

        Args:
            page: PyMuPDF page object

        Returns:
            Number of annotations removed
        """
        removed = 0
        annots_to_delete = []

        for annot in page.annots():
            if annot.type[0] in (fitz.PDF_ANNOT_HIGHLIGHT, fitz.PDF_ANNOT_TEXT):
                annots_to_delete.append(annot)

        for annot in annots_to_delete:
            page.delete_annot(annot)
            removed += 1

        if removed > 0:
            logger.debug(f"Removed {removed} existing annotations from page {page.number + 1}")

        return removed
