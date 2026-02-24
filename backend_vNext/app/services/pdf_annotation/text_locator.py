"""
Text Locator

Finds text positions in PDF pages using multiple search strategies
with cascading fallback for robust matching.
"""

import logging
import re
import io
from dataclasses import dataclass, field
from typing import Optional

import fitz  # PyMuPDF
from PIL import Image

from .page_classifier import PageType

logger = logging.getLogger(__name__)

# Import fuzzy matching
try:
    from rapidfuzz import fuzz
    from rapidfuzz.process import extractOne
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logger.warning("rapidfuzz not available - fuzzy matching disabled")

# Import OCR
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract not available - OCR disabled")


@dataclass
class TextMatch:
    """Result of a text search with location and confidence."""

    rect: fitz.Rect  # Bounding rectangle for highlight
    confidence: float  # Match confidence (0.0 to 1.0)
    match_method: str  # "exact", "normalized", "sentence", "fuzzy", "keyword", "ocr"
    matched_text: str  # Actual text found in PDF
    quads: list = field(default_factory=list)  # Quad points for precise highlighting

    def __repr__(self):
        return f"TextMatch(method={self.match_method}, conf={self.confidence:.2f}, rect={self.rect})"


@dataclass
class OCRWord:
    """Word extracted from OCR with bounding box."""

    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


class TextLocator:
    """
    Locates text in PDF pages using multiple search strategies.

    Search Strategy (Cascading Fallback):
    1. Exact search using PyMuPDF's search_for()
    2. Normalized search (whitespace, quotes normalized)
    3. Sentence search (split and search each sentence)
    4. Fuzzy search with rapidfuzz
    5. Keyword anchor search
    6. OCR search for image-based pages
    """

    # Default configuration
    DEFAULT_FUZZY_THRESHOLD = 85  # Minimum score for fuzzy match (0-100)
    DEFAULT_OCR_DPI = 300  # DPI for OCR image conversion
    MAX_OCR_DIMENSION = 4000  # Maximum dimension in pixels to prevent OOM

    def __init__(
        self,
        fuzzy_threshold: float = 0.85,
        ocr_language: str = "eng",
        ocr_dpi: int = 300
    ):
        """
        Initialize the text locator.

        Args:
            fuzzy_threshold: Minimum fuzzy match score (0.0-1.0)
            ocr_language: Tesseract language code
            ocr_dpi: DPI for page-to-image conversion for OCR
        """
        self.fuzzy_threshold = int(fuzzy_threshold * 100)  # Convert to 0-100 scale
        self.ocr_language = ocr_language
        self.ocr_dpi = ocr_dpi

        # Validate dependencies
        if not RAPIDFUZZ_AVAILABLE:
            logger.warning("Fuzzy matching unavailable - install rapidfuzz")
        if not TESSERACT_AVAILABLE:
            logger.warning("OCR unavailable - install pytesseract and tesseract")

    def locate_text(
        self,
        page: fitz.Page,
        snippet: str,
        page_type: PageType
    ) -> list[TextMatch]:
        """
        Find all occurrences of snippet on page using appropriate strategies.

        Args:
            page: PyMuPDF page object
            snippet: Text snippet to find
            page_type: Classification of the page (text-based or image-based)

        Returns:
            List of TextMatch objects (may be empty if not found)
        """
        if not snippet or len(snippet.strip()) < 5:
            logger.warning(f"Snippet too short to search: '{snippet[:50]}...'")
            return []

        # Initialize matches to avoid unbound variable error
        matches = []

        # For text-based pages, try text extraction methods first
        if page_type in (PageType.TEXT_BASED, PageType.MIXED):
            matches = self._search_text_based(page, snippet)
            if matches:
                return matches

        # For image-based pages or if text search failed, try OCR
        if page_type == PageType.IMAGE_BASED or not matches:
            if TESSERACT_AVAILABLE:
                matches = self._search_ocr(page, snippet)
                if matches:
                    return matches
            else:
                logger.warning(f"Cannot search image-based page {page.number + 1} - OCR unavailable")

        return []

    def _search_text_based(self, page: fitz.Page, snippet: str) -> list[TextMatch]:
        """
        Apply text-based search strategies in order.

        Args:
            page: PyMuPDF page object
            snippet: Text to search for

        Returns:
            List of matches (first successful strategy)
        """
        # Strategy 1: Exact search
        matches = self._search_exact(page, snippet)
        if matches:
            return matches

        # Strategy 2: Normalized search
        matches = self._search_normalized(page, snippet)
        if matches:
            return matches

        # Strategy 3: Multi-line/phrase chunk search (for text spanning multiple lines)
        matches = self._search_multiline(page, snippet)
        if matches:
            return matches

        # Strategy 4: Sentence search
        matches = self._search_sentences(page, snippet)
        if matches:
            return matches

        # Strategy 5: Fuzzy search
        if RAPIDFUZZ_AVAILABLE:
            matches = self._search_fuzzy(page, snippet)
            if matches:
                return matches

        # Strategy 6: Keyword anchor search
        matches = self._search_keywords(page, snippet)
        if matches:
            return matches

        return []

    def _search_exact(self, page: fitz.Page, snippet: str) -> list[TextMatch]:
        """
        Use PyMuPDF's built-in text search.

        Args:
            page: PyMuPDF page object
            snippet: Exact text to find

        Returns:
            List of TextMatch objects
        """
        matches = []

        # Search for full snippet
        quads = page.search_for(snippet, quads=True)

        if quads:
            for quad in quads:
                rect = quad.rect
                matches.append(TextMatch(
                    rect=rect,
                    confidence=1.0,
                    match_method="exact",
                    matched_text=snippet,
                    quads=[quad]
                ))
            logger.debug(f"Exact match found: {len(matches)} occurrences")

        return matches

    def _search_normalized(self, page: fitz.Page, snippet: str) -> list[TextMatch]:
        """
        Search with normalized whitespace and quotes.

        Args:
            page: PyMuPDF page object
            snippet: Text to normalize and search

        Returns:
            List of TextMatch objects
        """
        # Normalize the snippet
        normalized = self._normalize_text(snippet)

        if normalized == snippet:
            return []  # No change after normalization, skip

        # Try exact search with normalized text
        quads = page.search_for(normalized, quads=True)

        if quads:
            matches = []
            for quad in quads:
                matches.append(TextMatch(
                    rect=quad.rect,
                    confidence=0.95,
                    match_method="normalized",
                    matched_text=normalized,
                    quads=[quad]
                ))
            logger.debug(f"Normalized match found: {len(matches)} occurrences")
            return matches

        return []

    def _search_multiline(self, page: fitz.Page, snippet: str) -> list[TextMatch]:
        """
        Search for text that spans multiple lines in the PDF.

        PDFs store text line-by-line, so a long title or paragraph that spans
        multiple visual lines won't be found by exact search. This method:
        1. Splits the snippet into smaller chunks (phrases)
        2. Searches for each chunk separately
        3. Merges adjacent matches into a single highlight

        Args:
            page: PyMuPDF page object
            snippet: Text that may span multiple lines

        Returns:
            List of TextMatch objects with merged rectangles
        """
        # Only use this for longer text that likely spans lines
        if len(snippet) < 50:
            return []

        # Normalize the snippet first
        normalized = self._normalize_text(snippet)

        # Split into phrases/chunks (aim for ~40-60 chars per chunk)
        chunks = self._split_into_chunks(normalized, target_size=50)

        if len(chunks) < 2:
            return []  # Not worth multi-line search for single chunk

        found_rects = []
        found_quads = []
        matched_chunks = 0

        for chunk in chunks:
            chunk = chunk.strip()
            if len(chunk) < 10:
                continue

            # Search for this chunk
            quads = page.search_for(chunk, quads=True)
            if quads:
                matched_chunks += 1
                for quad in quads:
                    found_rects.append(quad.rect)
                    found_quads.append(quad)

        # Require at least 60% of chunks to be found
        min_required = max(2, int(len(chunks) * 0.6))
        if matched_chunks >= min_required and found_rects:
            # Merge all found rectangles
            merged_rect = self._merge_rects(found_rects)
            confidence = matched_chunks / len(chunks)

            logger.debug(f"Multi-line match: {matched_chunks}/{len(chunks)} chunks found")

            return [TextMatch(
                rect=merged_rect,
                confidence=confidence,
                match_method="multiline",
                matched_text=f"[{matched_chunks} of {len(chunks)} phrases matched]",
                quads=found_quads
            )]

        # Try searching for first and last significant phrases
        # This helps when middle parts have minor variations
        if len(chunks) >= 3:
            first_chunk = chunks[0].strip()
            last_chunk = chunks[-1].strip()

            if len(first_chunk) >= 15 and len(last_chunk) >= 15:
                first_quads = page.search_for(first_chunk, quads=True)
                last_quads = page.search_for(last_chunk, quads=True)

                if first_quads and last_quads:
                    # Find the best pair (first rect that's above/before last rect)
                    for fq in first_quads:
                        for lq in last_quads:
                            # Check if last is below or to the right of first
                            if lq.rect.y0 >= fq.rect.y0 - 10:  # Allow small tolerance
                                # Merge first to last
                                merged = self._merge_rects([fq.rect, lq.rect])

                                logger.debug("Multi-line match via first+last phrases")

                                return [TextMatch(
                                    rect=merged,
                                    confidence=0.85,
                                    match_method="multiline",
                                    matched_text=f"[first+last phrase match]",
                                    quads=[fq, lq]
                                )]

        return []

    def _split_into_chunks(self, text: str, target_size: int = 50) -> list[str]:
        """
        Split text into chunks suitable for searching.

        Tries to split at natural boundaries (spaces) while keeping
        chunks around the target size.

        Args:
            text: Text to split
            target_size: Target chunk size in characters

        Returns:
            List of text chunks
        """
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0

        for word in words:
            word_len = len(word) + 1  # +1 for space

            if current_length + word_len > target_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = [word]
                current_length = len(word)
            else:
                current_chunk.append(word)
                current_length += word_len

        # Add remaining words
        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks

    def _search_sentences(self, page: fitz.Page, snippet: str) -> list[TextMatch]:
        """
        Split snippet into sentences and search each.

        Args:
            page: PyMuPDF page object
            snippet: Multi-sentence text

        Returns:
            Combined matches if majority of sentences found
        """
        # Split into sentences
        sentences = self._split_sentences(snippet)

        if len(sentences) < 2:
            return []  # Not worth sentence search for single sentence

        found_rects = []
        found_count = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:
                continue

            quads = page.search_for(sentence, quads=True)
            if quads:
                found_count += 1
                for quad in quads:
                    found_rects.append(quad.rect)

        # Require at least 50% of sentences found
        if found_count >= len(sentences) * 0.5 and found_rects:
            # Merge all found rectangles into one
            merged_rect = self._merge_rects(found_rects)
            confidence = found_count / len(sentences)

            logger.debug(f"Sentence match: {found_count}/{len(sentences)} sentences found")

            return [TextMatch(
                rect=merged_rect,
                confidence=confidence,
                match_method="sentence",
                matched_text=f"[{found_count} sentences matched]"
            )]

        return []

    def _search_fuzzy(self, page: fitz.Page, snippet: str) -> list[TextMatch]:
        """
        Use fuzzy string matching to find similar text.

        Args:
            page: PyMuPDF page object
            snippet: Text to fuzzy match

        Returns:
            Best fuzzy match if above threshold
        """
        if not RAPIDFUZZ_AVAILABLE:
            return []

        # Get all text blocks from page
        blocks = page.get_text("dict")["blocks"]
        text_blocks = []

        for block in blocks:
            if block.get("type") == 0:  # Text block
                block_text = ""
                block_rect = fitz.Rect(block["bbox"])

                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        block_text += span.get("text", "") + " "

                block_text = block_text.strip()
                if len(block_text) >= 10:
                    text_blocks.append((block_text, block_rect))

        if not text_blocks:
            return []

        # Find best fuzzy match
        texts = [t[0] for t in text_blocks]
        result = extractOne(
            snippet,
            texts,
            scorer=fuzz.partial_ratio,
            score_cutoff=self.fuzzy_threshold
        )

        if result:
            matched_text, score, idx = result
            _, block_rect = text_blocks[idx]

            logger.debug(f"Fuzzy match found: score={score}")

            return [TextMatch(
                rect=block_rect,
                confidence=score / 100.0,
                match_method="fuzzy",
                matched_text=matched_text[:100] + "..." if len(matched_text) > 100 else matched_text
            )]

        return []

    def _search_keywords(self, page: fitz.Page, snippet: str) -> list[TextMatch]:
        """
        Extract keywords from snippet and find text blocks containing them.

        Args:
            page: PyMuPDF page object
            snippet: Text to extract keywords from

        Returns:
            Match if enough keywords found in a block
        """
        # Extract keywords (words > 4 chars, not common words)
        keywords = self._extract_keywords(snippet)

        if len(keywords) < 3:
            return []  # Need at least 3 keywords

        # Get all text blocks
        blocks = page.get_text("dict")["blocks"]
        best_match = None
        best_keyword_count = 0

        for block in blocks:
            if block.get("type") != 0:
                continue

            block_text = ""
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    block_text += span.get("text", "") + " "

            block_text_lower = block_text.lower()

            # Count keywords found
            keyword_count = sum(1 for kw in keywords if kw.lower() in block_text_lower)

            if keyword_count >= 3 and keyword_count > best_keyword_count:
                best_keyword_count = keyword_count
                best_match = (block_text.strip(), fitz.Rect(block["bbox"]), keyword_count)

        if best_match:
            text, rect, count = best_match
            confidence = count / len(keywords)

            logger.debug(f"Keyword match: {count}/{len(keywords)} keywords found")

            return [TextMatch(
                rect=rect,
                confidence=confidence,
                match_method="keyword",
                matched_text=f"[{count} keywords matched]"
            )]

        return []

    def _search_ocr(self, page: fitz.Page, snippet: str) -> list[TextMatch]:
        """
        Use OCR to extract text with bounding boxes from page image.

        Args:
            page: PyMuPDF page object
            snippet: Text to find via OCR

        Returns:
            Matches based on OCR text
        """
        if not TESSERACT_AVAILABLE:
            return []

        try:
            # Convert page to image with size limit to prevent OOM
            base_zoom = self.ocr_dpi / 72  # 72 DPI is default

            # Calculate zoom that respects MAX_OCR_DIMENSION
            page_rect = page.rect
            max_page_dim = max(page_rect.width, page_rect.height)
            max_zoom_for_limit = self.MAX_OCR_DIMENSION / max_page_dim if max_page_dim > 0 else base_zoom

            # Use the smaller zoom to stay within limits
            zoom = min(base_zoom, max_zoom_for_limit)

            if zoom < base_zoom:
                logger.debug(f"Reduced OCR zoom from {base_zoom:.2f} to {zoom:.2f} to stay within {self.MAX_OCR_DIMENSION}px limit")

            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix)

            # Convert to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Run OCR with bounding boxes
            ocr_data = pytesseract.image_to_data(
                img,
                lang=self.ocr_language,
                output_type=pytesseract.Output.DICT
            )

            # Parse OCR results into words
            ocr_words = self._parse_ocr_data(ocr_data, zoom)

            if not ocr_words:
                return []

            # Build full text for fuzzy matching
            full_text = " ".join(w.text for w in ocr_words)

            # Try exact match in OCR text
            matches = self._match_ocr_text(ocr_words, snippet, zoom, page)

            if matches:
                logger.debug(f"OCR match found on page {page.number + 1}")
                return matches

            # Try fuzzy match
            if RAPIDFUZZ_AVAILABLE:
                score = fuzz.partial_ratio(snippet.lower(), full_text.lower())
                if score >= self.fuzzy_threshold:
                    # Find best matching region
                    matches = self._find_ocr_fuzzy_region(ocr_words, snippet, zoom, page)
                    if matches:
                        return matches

        except Exception as e:
            logger.error(f"OCR search failed on page {page.number + 1}: {e}")

        return []

    def _parse_ocr_data(self, ocr_data: dict, zoom: float) -> list[OCRWord]:
        """Parse pytesseract output into OCRWord objects."""
        words = []
        n_boxes = len(ocr_data.get("text", []))

        for i in range(n_boxes):
            text = ocr_data["text"][i].strip()
            conf = int(ocr_data["conf"][i])

            if text and conf > 0:  # Filter empty and low confidence
                words.append(OCRWord(
                    text=text,
                    left=int(ocr_data["left"][i] / zoom),
                    top=int(ocr_data["top"][i] / zoom),
                    width=int(ocr_data["width"][i] / zoom),
                    height=int(ocr_data["height"][i] / zoom),
                    confidence=conf / 100.0
                ))

        return words

    def _match_ocr_text(
        self,
        ocr_words: list[OCRWord],
        snippet: str,
        zoom: float,
        page: fitz.Page
    ) -> list[TextMatch]:
        """Find exact match of snippet in OCR words."""
        snippet_words = snippet.lower().split()
        if not snippet_words:
            return []

        # Sliding window search
        for i in range(len(ocr_words) - len(snippet_words) + 1):
            window_words = ocr_words[i:i + len(snippet_words)]
            window_text = " ".join(w.text.lower() for w in window_words)

            if self._text_matches(window_text, " ".join(snippet_words)):
                # Calculate bounding rect
                rect = self._words_to_rect(window_words)

                return [TextMatch(
                    rect=rect,
                    confidence=0.85,
                    match_method="ocr",
                    matched_text=" ".join(w.text for w in window_words)
                )]

        return []

    def _find_ocr_fuzzy_region(
        self,
        ocr_words: list[OCRWord],
        snippet: str,
        zoom: float,
        page: fitz.Page
    ) -> list[TextMatch]:
        """Find best fuzzy matching region in OCR text."""
        snippet_words = snippet.split()
        window_size = len(snippet_words)

        best_score = 0
        best_words = []

        for i in range(max(1, len(ocr_words) - window_size + 1)):
            window = ocr_words[i:i + window_size]
            window_text = " ".join(w.text for w in window)

            score = fuzz.partial_ratio(snippet.lower(), window_text.lower())
            if score > best_score:
                best_score = score
                best_words = window

        if best_score >= self.fuzzy_threshold and best_words:
            rect = self._words_to_rect(best_words)

            return [TextMatch(
                rect=rect,
                confidence=best_score / 100.0,
                match_method="ocr",
                matched_text=" ".join(w.text for w in best_words)[:100]
            )]

        return []

    def _words_to_rect(self, words: list[OCRWord]) -> fitz.Rect:
        """Convert list of OCR words to bounding rectangle."""
        if not words:
            return fitz.Rect()

        left = min(w.left for w in words)
        top = min(w.top for w in words)
        right = max(w.right for w in words)
        bottom = max(w.bottom for w in words)

        return fitz.Rect(left, top, right, bottom)

    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for more flexible matching.

        - Normalize line breaks (PDF uses different breaks than extraction)
        - Collapse multiple whitespace to single space
        - Normalize quotes and dashes
        - Expand common ligatures
        - Trim whitespace
        """
        # Normalize all line break variants to space
        text = text.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')

        # Collapse multiple whitespace to single space
        text = re.sub(r'\s+', ' ', text)

        # Normalize quotes (curly to straight)
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace("'", "'").replace("'", "'")

        # Normalize dashes (en-dash and em-dash to hyphen)
        text = text.replace('–', '-').replace('—', '-')

        # Expand common ligatures that may not match
        text = text.replace('ﬁ', 'fi').replace('ﬂ', 'fl')
        text = text.replace('ﬀ', 'ff').replace('ﬃ', 'ffi').replace('ﬄ', 'ffl')

        return text.strip()

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        # Simple sentence splitting on period followed by space and capital
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        return [s.strip() for s in sentences if s.strip()]

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract significant keywords from text."""
        # Common words to skip
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
            'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
            'this', 'that', 'these', 'those', 'it', 'its', 'they', 'them', 'their',
            'we', 'our', 'you', 'your', 'he', 'she', 'him', 'her', 'his', 'hers'
        }

        # Extract words
        words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())

        # Filter stop words and duplicates
        keywords = []
        seen = set()
        for word in words:
            if word not in stop_words and word not in seen:
                keywords.append(word)
                seen.add(word)
                if len(keywords) >= 10:  # Limit to 10 keywords
                    break

        return keywords

    def _merge_rects(self, rects: list[fitz.Rect]) -> fitz.Rect:
        """Merge multiple rectangles into one bounding rectangle."""
        if not rects:
            return fitz.Rect()

        x0 = min(r.x0 for r in rects)
        y0 = min(r.y0 for r in rects)
        x1 = max(r.x1 for r in rects)
        y1 = max(r.y1 for r in rects)

        return fitz.Rect(x0, y0, x1, y1)

    def _text_matches(self, text1: str, text2: str) -> bool:
        """Check if two texts match (case-insensitive, whitespace-normalized)."""
        t1 = re.sub(r'\s+', ' ', text1.lower().strip())
        t2 = re.sub(r'\s+', ' ', text2.lower().strip())
        return t1 == t2


def verify_tesseract_installation() -> bool:
    """
    Verify that Tesseract OCR is installed and accessible.

    Returns:
        True if Tesseract is available, False otherwise
    """
    if not TESSERACT_AVAILABLE:
        return False

    try:
        version = pytesseract.get_tesseract_version()
        logger.info(f"Tesseract OCR version: {version}")
        return True
    except pytesseract.TesseractNotFoundError:
        logger.error(
            "Tesseract OCR not found. Please install it:\n"
            "  macOS: brew install tesseract\n"
            "  Ubuntu: apt-get install tesseract-ocr\n"
            "  Windows: https://github.com/UB-Mannheim/tesseract/wiki"
        )
        return False
    except Exception as e:
        logger.error(f"Error checking Tesseract: {e}")
        return False
