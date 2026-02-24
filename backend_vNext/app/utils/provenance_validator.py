"""
Provenance Validator and Corrector.

Validates and corrects provenance page numbers by searching for text_snippets
in the actual PDF. This fixes LLM hallucination issues where the model returns
incorrect page numbers.

Uses PyMuPDF (fitz) to search for text in the PDF and find the correct page.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def validate_and_correct_provenance(pdf_bytes: bytes, data: Any) -> Dict[str, Any]:
    """
    Validate and correct all provenance page numbers in the extracted data.

    Searches for each text_snippet in the PDF and corrects the page_number
    if found on a different page.

    Args:
        pdf_bytes: PDF file as bytes
        data: Extracted data with provenance objects

    Returns:
        dict with correction statistics:
        {
            "total_provenance": int,
            "corrected": int,
            "validated": int,
            "not_found": int,
            "corrections": [{"path": str, "original": int, "corrected": int, "snippet_preview": str}]
        }
    """
    stats = {
        "total_provenance": 0,
        "corrected": 0,
        "validated": 0,
        "not_found": 0,
        "corrections": []
    }

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        # Recursively find and correct all provenance objects
        _correct_provenance_recursive(doc, data, "", stats)

        doc.close()

        logger.info(
            f"Provenance validation: {stats['total_provenance']} total, "
            f"{stats['corrected']} corrected, {stats['validated']} validated, "
            f"{stats['not_found']} not found"
        )

    except Exception as e:
        logger.error(f"Error validating provenance: {e}")

    return stats


def _correct_provenance_recursive(
    doc: fitz.Document,
    data: Any,
    path: str,
    stats: Dict[str, Any]
) -> None:
    """Recursively find and correct provenance objects."""

    if isinstance(data, dict):
        # Check if this dict has a provenance object
        if "provenance" in data and isinstance(data["provenance"], dict):
            prov = data["provenance"]
            prov_path = f"{path}.provenance" if path else "provenance"
            _validate_single_provenance(doc, prov, prov_path, stats)

        # Also check if this dict itself is a provenance object
        if "page_number" in data and "text_snippet" in data:
            _validate_single_provenance(doc, data, path, stats)

        # Recurse into all values
        for key, value in data.items():
            child_path = f"{path}.{key}" if path else key
            _correct_provenance_recursive(doc, value, child_path, stats)

    elif isinstance(data, list):
        for i, item in enumerate(data):
            child_path = f"{path}[{i}]"
            _correct_provenance_recursive(doc, item, child_path, stats)


def _validate_single_provenance(
    doc: fitz.Document,
    prov: Dict[str, Any],
    path: str,
    stats: Dict[str, Any]
) -> None:
    """Validate and correct a single provenance object."""

    page_number = prov.get("page_number")
    text_snippet = prov.get("text_snippet")

    if not isinstance(page_number, int) or not text_snippet:
        return

    stats["total_provenance"] += 1

    # Search for the text snippet in the PDF
    correct_page = _find_text_in_pdf(doc, text_snippet)

    if correct_page is None:
        stats["not_found"] += 1
        logger.debug(f"Text not found in PDF: {text_snippet[:50]}...")
        return

    if correct_page == page_number:
        # Page number is correct
        stats["validated"] += 1
    else:
        # Page number needs correction
        original = page_number
        prov["page_number"] = correct_page
        prov["_original_page_number"] = original
        prov["_corrected"] = True

        stats["corrected"] += 1
        stats["corrections"].append({
            "path": path,
            "original": original,
            "corrected": correct_page,
            "snippet_preview": text_snippet[:50] + "..." if len(text_snippet) > 50 else text_snippet
        })

        logger.debug(f"Corrected page {original} -> {correct_page} for: {text_snippet[:50]}...")


def _find_text_in_pdf(doc: fitz.Document, text_snippet: str) -> Optional[int]:
    """
    Search for text_snippet in the PDF and return the page number (1-indexed).

    Tries multiple search strategies:
    1. Exact match
    2. Normalized match (collapsed whitespace)
    3. First sentence/phrase match
    4. Keyword-based match

    Args:
        doc: PyMuPDF document
        text_snippet: Text to search for

    Returns:
        Page number (1-indexed) where text was found, or None
    """
    if not text_snippet or len(text_snippet.strip()) < 10:
        return None

    # Clean the snippet
    snippet = text_snippet.strip()

    # Strategy 1: Exact match
    page = _search_exact(doc, snippet)
    if page:
        return page

    # Strategy 2: Normalized match
    page = _search_normalized(doc, snippet)
    if page:
        return page

    # Strategy 3: First phrase/sentence
    page = _search_first_phrase(doc, snippet)
    if page:
        return page

    # Strategy 4: Keyword anchor search
    page = _search_keywords(doc, snippet)
    if page:
        return page

    return None


def _search_exact(doc: fitz.Document, snippet: str) -> Optional[int]:
    """Try exact text search."""
    for page_idx, page in enumerate(doc):
        if page.search_for(snippet):
            return page_idx + 1  # 1-indexed
    return None


def _search_normalized(doc: fitz.Document, snippet: str) -> Optional[int]:
    """Try normalized text search (collapsed whitespace)."""
    # Normalize snippet
    normalized = ' '.join(snippet.split())

    for page_idx, page in enumerate(doc):
        page_text = page.get_text("text")
        page_normalized = ' '.join(page_text.split())

        if normalized in page_normalized:
            return page_idx + 1

    return None


def _search_first_phrase(doc: fitz.Document, snippet: str) -> Optional[int]:
    """Search for just the first phrase/sentence of the snippet."""
    # Get first sentence or first 100 chars
    first_sentence = snippet.split('.')[0] if '.' in snippet else snippet[:100]
    first_sentence = first_sentence.strip()

    if len(first_sentence) < 20:
        return None

    for page_idx, page in enumerate(doc):
        if page.search_for(first_sentence):
            return page_idx + 1

    # Try normalized
    normalized = ' '.join(first_sentence.split())
    for page_idx, page in enumerate(doc):
        page_text = ' '.join(page.get_text("text").split())
        if normalized in page_text:
            return page_idx + 1

    return None


def _search_keywords(doc: fitz.Document, snippet: str) -> Optional[int]:
    """
    Search using significant keywords from the snippet.

    Extract unique/significant words and find pages containing most of them.
    """
    # Extract keywords (longer words, excluding common words)
    common_words = {
        'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had',
        'her', 'was', 'one', 'our', 'out', 'has', 'have', 'been', 'were', 'will',
        'with', 'that', 'this', 'from', 'they', 'which', 'their', 'would', 'there',
        'should', 'could', 'other', 'into', 'more', 'some', 'such', 'only', 'than',
        'then', 'also', 'must', 'being', 'those', 'both', 'each', 'either', 'neither'
    }

    words = re.findall(r'\b[a-zA-Z]{4,}\b', snippet.lower())
    keywords = [w for w in words if w not in common_words]

    # Take top 5 most unique-looking keywords
    keywords = sorted(set(keywords), key=lambda w: len(w), reverse=True)[:5]

    if len(keywords) < 2:
        return None

    # Find pages with most keyword matches
    best_page = None
    best_score = 0

    for page_idx, page in enumerate(doc):
        page_text = page.get_text("text").lower()
        score = sum(1 for kw in keywords if kw in page_text)

        if score > best_score and score >= len(keywords) * 0.6:
            best_score = score
            best_page = page_idx + 1

    return best_page
