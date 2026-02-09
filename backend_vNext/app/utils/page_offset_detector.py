"""
Page Offset Detection Utility.

Detects the offset between printed page numbers and physical page indices in PDFs.
Some PDFs have preliminary pages (cover, TOC) without page numbers, causing
"Page 1" to appear on a later physical page.

Uses PyMuPDF (fitz) to scan footer/header regions and detect page numbering patterns.
"""

import re
import logging
from typing import Optional
from datetime import datetime

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def detect_page_offset(pdf_bytes: bytes) -> dict:
    """
    Detect page numbering info from PDF.

    Scans the first 20 pages looking for "Page 1" or similar patterns in
    footer/header regions to determine where printed page numbering starts.

    Args:
        pdf_bytes: PDF file as bytes

    Returns:
        dict: {
            "firstNumberedPage": int,  # Physical page where "Page 1" appears (1-indexed, default: 1)
            "pageOffset": int,         # Offset to apply: physical = printed + offset (default: 0)
            "detectedAt": str,         # ISO timestamp of detection
            "confidence": str          # "high", "medium", "low", or "none"
        }

    Example:
        If "Page 1" is found at physical page 5:
        {"firstNumberedPage": 5, "pageOffset": 4, "confidence": "high"}
    """
    result = {
        "firstNumberedPage": 1,
        "pageOffset": 0,
        "detectedAt": datetime.utcnow().isoformat() + "Z",
        "confidence": "none"
    }

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)

        if total_pages == 0:
            logger.warning("PDF has no pages")
            return result

        # Scan first 20 pages (or all pages if fewer)
        pages_to_scan = min(20, total_pages)

        # Track page number detections
        detections = []

        for page_idx in range(pages_to_scan):
            page = doc[page_idx]
            physical_page = page_idx + 1  # 1-indexed

            # Get page dimensions
            page_rect = page.rect
            page_height = page_rect.height
            page_width = page_rect.width

            # Define footer region (bottom 15% of page)
            footer_rect = fitz.Rect(
                page_rect.x0,
                page_rect.y1 - (page_height * 0.15),
                page_rect.x1,
                page_rect.y1
            )

            # Define header region (top 10% of page)
            header_rect = fitz.Rect(
                page_rect.x0,
                page_rect.y0,
                page_rect.x1,
                page_rect.y0 + (page_height * 0.10)
            )

            # Extract text from footer and header
            footer_text = page.get_text("text", clip=footer_rect)
            header_text = page.get_text("text", clip=header_rect)

            # Search for page numbers in both regions
            for region_name, region_text in [("footer", footer_text), ("header", header_text)]:
                if not region_text:
                    continue

                printed_page = _extract_page_number(region_text)
                if printed_page is not None:
                    detections.append({
                        "physical_page": physical_page,
                        "printed_page": printed_page,
                        "region": region_name
                    })
                    logger.debug(
                        f"Found page number {printed_page} at physical page {physical_page} in {region_name}"
                    )

        doc.close()

        # Analyze detections to find where "Page 1" starts
        if detections:
            # Look for the page where printed page 1 appears
            page_1_detections = [d for d in detections if d["printed_page"] == 1]

            if page_1_detections:
                # Found "Page 1" explicitly
                first_numbered = page_1_detections[0]["physical_page"]
                result["firstNumberedPage"] = first_numbered
                result["pageOffset"] = first_numbered - 1
                result["confidence"] = "high"
                logger.info(
                    f"Detected 'Page 1' at physical page {first_numbered}, offset={first_numbered - 1}"
                )
            else:
                # No "Page 1" found, try to infer from other detections
                # Look for sequential page numbers and extrapolate
                inferred = _infer_offset_from_sequence(detections)
                if inferred:
                    result["firstNumberedPage"] = inferred["first_numbered_page"]
                    result["pageOffset"] = inferred["offset"]
                    result["confidence"] = "medium"
                    logger.info(
                        f"Inferred first numbered page at {inferred['first_numbered_page']}, "
                        f"offset={inferred['offset']} (from sequence analysis)"
                    )

        if result["confidence"] == "none":
            logger.info("No page numbers detected in footer/header regions")

    except Exception as e:
        logger.error(f"Error detecting page offset: {e}")
        # Return defaults on error

    return result


def _extract_page_number(text: str) -> Optional[int]:
    """
    Extract page number from footer/header text.

    Supports various formats:
    - "Page 1", "page 1", "PAGE 1"
    - "Page 1 of 100", "1 of 100"
    - "- 1 -", "– 1 –"
    - Just "1" at the start/end of line

    Returns:
        int: The extracted page number, or None if not found
    """
    if not text:
        return None

    # Normalize whitespace
    text = ' '.join(text.split())

    # Patterns to try (in order of specificity)
    patterns = [
        # "Page N" or "page N" (most common in clinical protocols)
        r'[Pp]age\s+(\d+)',

        # "N of M" format
        r'^(\d+)\s+of\s+\d+',
        r'(\d+)\s+of\s+\d+$',

        # "- N -" or "– N –" centered format
        r'[-–]\s*(\d+)\s*[-–]',

        # Just a number alone on the line (less specific)
        r'^(\d+)$',

        # Number at start or end of text (least specific)
        r'^\s*(\d+)\s',
        r'\s(\d+)\s*$',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            try:
                page_num = int(match.group(1))
                # Sanity check: page numbers should be reasonable (1-9999)
                if 1 <= page_num <= 9999:
                    return page_num
            except (ValueError, IndexError):
                continue

    return None


def _infer_offset_from_sequence(detections: list) -> Optional[dict]:
    """
    Infer page offset from a sequence of detected page numbers.

    If we found page numbers like 5, 6, 7 at physical pages 9, 10, 11,
    we can infer that "Page 1" would be at physical page 5.

    Args:
        detections: List of {"physical_page": int, "printed_page": int, "region": str}

    Returns:
        dict with "first_numbered_page" and "offset", or None if can't infer
    """
    if len(detections) < 2:
        return None

    # Sort by physical page
    sorted_detections = sorted(detections, key=lambda d: d["physical_page"])

    # Check for consistent offset across detections
    offsets = []
    for d in sorted_detections:
        offset = d["physical_page"] - d["printed_page"]
        offsets.append(offset)

    # If all offsets are the same, we have consistent page numbering
    if len(set(offsets)) == 1:
        offset = offsets[0]
        first_numbered_page = 1 + offset  # Where "Page 1" would be
        return {
            "first_numbered_page": first_numbered_page,
            "offset": offset
        }

    # If offsets vary, use the most common one
    from collections import Counter
    offset_counts = Counter(offsets)
    most_common_offset, count = offset_counts.most_common(1)[0]

    # Only use if it appears in majority of detections
    if count >= len(offsets) / 2:
        first_numbered_page = 1 + most_common_offset
        return {
            "first_numbered_page": first_numbered_page,
            "offset": most_common_offset
        }

    return None
