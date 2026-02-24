"""
Page Classifier

Classifies PDF pages as text-based or image-based to determine
the appropriate annotation strategy.
"""

import logging
from enum import Enum
from dataclasses import dataclass

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class PageType(Enum):
    """Classification of PDF page types for annotation strategy."""

    TEXT_BASED = "text_based"  # Native text extraction works well
    IMAGE_BASED = "image_based"  # Need OCR for text location
    MIXED = "mixed"  # Has both text and significant images


@dataclass
class PageClassification:
    """Result of page classification with supporting metrics."""

    page_type: PageType
    text_length: int
    image_count: int
    confidence: float  # 0.0 to 1.0 confidence in classification

    @property
    def is_text_based(self) -> bool:
        """Returns True if page can be processed with text extraction."""
        return self.page_type in (PageType.TEXT_BASED, PageType.MIXED)

    @property
    def needs_ocr(self) -> bool:
        """Returns True if page requires OCR for text location."""
        return self.page_type == PageType.IMAGE_BASED


class PageClassifier:
    """
    Classifies PDF pages to determine annotation strategy.

    Classification Logic:
    1. Extract text from page
    2. Check for embedded images
    3. Decision tree:
       - Little text + images → IMAGE_BASED (likely scanned)
       - Good text + no images → TEXT_BASED
       - Good text + images → MIXED (can use text extraction)
       - Little text + no images → IMAGE_BASED (likely scanned without images)
    """

    # Minimum text length to consider page as having extractable text
    MIN_TEXT_LENGTH = 50

    # Minimum characters per image ratio to consider as having "good" text
    CHARS_PER_IMAGE_THRESHOLD = 200

    def __init__(self, min_text_length: int = 50):
        """
        Initialize the page classifier.

        Args:
            min_text_length: Minimum text length to classify as text-based
        """
        self.min_text_length = min_text_length
        self._cache: dict[int, PageClassification] = {}

    def classify(self, page: fitz.Page) -> PageClassification:
        """
        Determine page type based on content analysis.

        Args:
            page: PyMuPDF page object

        Returns:
            PageClassification with type and metrics
        """
        page_num = page.number

        # Check cache first
        if page_num in self._cache:
            return self._cache[page_num]

        # Extract metrics
        text = page.get_text("text")
        text_length = len(text.strip())
        images = page.get_images(full=False)
        image_count = len(images)

        # Classify based on metrics
        classification = self._determine_type(text_length, image_count)

        # Cache result
        self._cache[page_num] = classification

        logger.debug(
            f"Page {page_num + 1}: {classification.page_type.value} "
            f"(text={text_length}, images={image_count})"
        )

        return classification

    def classify_pages(self, doc: fitz.Document, page_numbers: list[int]) -> dict[int, PageClassification]:
        """
        Classify multiple pages at once.

        Args:
            doc: PyMuPDF document
            page_numbers: List of 1-indexed page numbers to classify

        Returns:
            Dictionary mapping page numbers to classifications
        """
        results = {}

        for page_num in page_numbers:
            # Convert to 0-indexed for PyMuPDF
            page_idx = page_num - 1

            if 0 <= page_idx < len(doc):
                page = doc[page_idx]
                classification = self.classify(page)
                results[page_num] = classification
            else:
                logger.warning(f"Page {page_num} out of range (doc has {len(doc)} pages)")

        return results

    def clear_cache(self) -> None:
        """Clear the classification cache."""
        self._cache.clear()

    def _determine_type(self, text_length: int, image_count: int) -> PageClassification:
        """
        Apply classification logic based on text and image metrics.

        Args:
            text_length: Length of extracted text
            image_count: Number of embedded images

        Returns:
            PageClassification result
        """
        has_good_text = text_length >= self.min_text_length
        has_images = image_count > 0

        if has_good_text and not has_images:
            # Clean text page - highest confidence
            return PageClassification(
                page_type=PageType.TEXT_BASED,
                text_length=text_length,
                image_count=image_count,
                confidence=1.0
            )

        elif has_good_text and has_images:
            # Mixed content - text extraction should still work
            # Confidence based on text-to-image ratio
            chars_per_image = text_length / max(image_count, 1)
            confidence = min(chars_per_image / self.CHARS_PER_IMAGE_THRESHOLD, 1.0)

            return PageClassification(
                page_type=PageType.MIXED,
                text_length=text_length,
                image_count=image_count,
                confidence=confidence
            )

        elif not has_good_text and has_images:
            # Little text with images - likely scanned page
            return PageClassification(
                page_type=PageType.IMAGE_BASED,
                text_length=text_length,
                image_count=image_count,
                confidence=0.9
            )

        else:
            # No text, no images - unusual, treat as image-based
            # Could be a page with vector graphics rendered as paths
            return PageClassification(
                page_type=PageType.IMAGE_BASED,
                text_length=text_length,
                image_count=image_count,
                confidence=0.7
            )

    def _has_extractable_text(self, page: fitz.Page) -> bool:
        """
        Check if page has substantial extractable text.

        Args:
            page: PyMuPDF page object

        Returns:
            True if text extraction yields useful content
        """
        text = page.get_text("text")
        return len(text.strip()) >= self.min_text_length

    def _has_embedded_images(self, page: fitz.Page) -> bool:
        """
        Check if page contains embedded images.

        Args:
            page: PyMuPDF page object

        Returns:
            True if page has embedded images
        """
        images = page.get_images(full=False)
        return len(images) > 0

    def _is_scanned_page(self, page: fitz.Page) -> bool:
        """
        Detect if page is likely a scanned image without text layer.

        A scanned page typically has:
        - One large image covering most of the page
        - Little to no extractable text

        Args:
            page: PyMuPDF page object

        Returns:
            True if page appears to be scanned
        """
        text = page.get_text("text")
        images = page.get_images(full=False)

        # Check for single large image with minimal text
        if len(images) == 1 and len(text.strip()) < 20:
            # Get image dimensions
            try:
                img_info = images[0]
                # img_info is (xref, smask, width, height, bpc, colorspace, alt, name, filter)
                img_width = img_info[2]
                img_height = img_info[3]
                page_rect = page.rect

                # Check if image covers most of the page
                page_area = page_rect.width * page_rect.height
                img_area = img_width * img_height

                # If image area is > 50% of page area, likely scanned
                if img_area > page_area * 0.5:
                    return True
            except (IndexError, TypeError):
                pass

        return False

    def get_summary(self, classifications: dict[int, PageClassification]) -> dict:
        """
        Generate a summary of page classifications.

        Args:
            classifications: Dictionary of page classifications

        Returns:
            Summary statistics
        """
        type_counts = {pt.value: 0 for pt in PageType}
        total_text = 0
        total_images = 0

        for classification in classifications.values():
            type_counts[classification.page_type.value] += 1
            total_text += classification.text_length
            total_images += classification.image_count

        return {
            "total_pages": len(classifications),
            "type_distribution": type_counts,
            "total_text_chars": total_text,
            "total_images": total_images,
            "avg_text_per_page": total_text / max(len(classifications), 1),
            "avg_images_per_page": total_images / max(len(classifications), 1)
        }
