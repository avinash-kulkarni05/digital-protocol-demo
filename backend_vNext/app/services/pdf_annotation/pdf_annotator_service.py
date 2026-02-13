"""
PDF Annotator Service

Main orchestrator that coordinates all annotation components
to produce an annotated PDF with highlighted provenance.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any

import fitz  # PyMuPDF

from .provenance_collector import ProvenanceCollector, ProvenanceItem
from .page_classifier import PageClassifier, PageType, PageClassification
from .text_locator import TextLocator, TextMatch, verify_tesseract_installation
from .annotation_renderer import AnnotationRenderer, AnnotationStyle, AnnotationResult
from .bookmark_generator import BookmarkGenerator, add_document_metadata
from .annotation_output import (
    AnnotationOutput,
    AnnotationReport,
    generate_annotation_filename,
    generate_report_filename
)

logger = logging.getLogger(__name__)


@dataclass
class PDFAnnotationResult:
    """Result of the PDF annotation process."""

    success: bool
    annotated_pdf_path: Optional[Path] = None
    report_path: Optional[Path] = None
    success_rate: float = 0.0
    total_annotations: int = 0
    successful_annotations: int = 0
    failed_annotations: int = 0
    error: Optional[str] = None
    report: Optional[AnnotationReport] = None


class PDFAnnotatorService:
    """
    Main service for annotating PDFs with provenance highlights.

    Orchestrates:
    1. Provenance collection from USDM JSON
    2. Page classification (text vs image)
    3. Text location with multiple search strategies
    4. Annotation rendering (highlights + popups)
    5. Bookmark generation (by module)
    6. Report generation

    Never blocks the pipeline - always produces output even if some
    annotations fail.
    """

    def __init__(self, config: Optional[dict] = None):
        """
        Initialize the PDF annotator service.

        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}

        # Initialize components with config
        self.style = AnnotationStyle.from_config(self.config)
        fuzzy_threshold = self.config.get("fuzzy_threshold", 0.85)
        ocr_language = self.config.get("ocr_language", "eng")

        self.collector = ProvenanceCollector()
        self.classifier = PageClassifier()
        self.locator = TextLocator(
            fuzzy_threshold=fuzzy_threshold,
            ocr_language=ocr_language
        )
        self.renderer = AnnotationRenderer(style=self.style)
        self.bookmark_gen = BookmarkGenerator()
        self.output_gen = AnnotationOutput()

        # Verify OCR availability at startup
        self._ocr_available = verify_tesseract_installation()
        if not self._ocr_available:
            logger.warning(
                "Tesseract OCR not available. Image-based pages will not be annotated. "
                "Install Tesseract: brew install tesseract (macOS) or "
                "apt-get install tesseract-ocr (Ubuntu)"
            )

    def annotate(
        self,
        pdf_path: Path | str,
        usdm_json: dict,
        output_dir: Path | str,
        protocol_id: Optional[str] = None
    ) -> PDFAnnotationResult:
        """
        Annotate a PDF with provenance highlights from USDM JSON.

        Args:
            pdf_path: Path to the source PDF
            usdm_json: Complete USDM 4.0 JSON document
            output_dir: Directory to save annotated PDF and report
            protocol_id: Optional protocol ID (extracted from JSON if not provided)

        Returns:
            PDFAnnotationResult with paths and statistics
        """
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)

        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Starting PDF annotation for {pdf_path.name}")

        try:
            # Step 1: Collect provenance from USDM JSON
            logger.info("Step 1: Collecting provenance items from USDM JSON")
            all_items = self.collector.collect(usdm_json)

            if not all_items:
                logger.warning("No provenance items found in USDM JSON")
                return PDFAnnotationResult(
                    success=True,
                    error="No provenance items found in USDM JSON"
                )

            # Deduplicate and group
            unique_items = self.collector.deduplicate(all_items)
            items_by_page = self.collector.group_by_page(unique_items)
            items_by_module = self.collector.group_by_module(unique_items)
            collection_stats = self.collector.get_stats()

            logger.info(
                f"Found {collection_stats.total_found} provenance items, "
                f"{collection_stats.unique_after_dedup} unique, "
                f"across {collection_stats.pages_covered} pages"
            )

            # Step 2: Open PDF document
            logger.info("Step 2: Opening PDF document")
            doc = fitz.open(pdf_path)

            # Check if PDF is encrypted
            if doc.is_encrypted:
                logger.error(f"PDF is encrypted and cannot be annotated: {pdf_path}")
                doc.close()
                return PDFAnnotationResult(
                    success=False,
                    error="PDF is encrypted and cannot be annotated. Please provide an unencrypted PDF."
                )

            # Get protocol ID
            if not protocol_id:
                protocol_id = self._extract_protocol_id(usdm_json, pdf_path)

            # Step 3: Classify pages and locate/annotate text
            logger.info("Step 3: Processing pages and adding annotations")
            annotation_results = []
            page_classifications = {}

            for page_num in sorted(items_by_page.keys()):
                page_items = items_by_page[page_num]

                # Validate page number
                page_idx = page_num - 1  # Convert to 0-indexed
                if page_idx < 0 or page_idx >= len(doc):
                    logger.warning(f"Page {page_num} out of range (doc has {len(doc)} pages)")
                    for item in page_items:
                        annotation_results.append(AnnotationResult(
                            success=False,
                            provenance_item=item,
                            error=f"Page {page_num} out of range"
                        ))
                    continue

                page = doc[page_idx]

                # Classify page
                classification = self.classifier.classify(page)
                page_classifications[page_num] = classification

                logger.debug(
                    f"Page {page_num}: {classification.page_type.value} "
                    f"(text={classification.text_length}, images={classification.image_count})"
                )

                # Skip OCR pages if Tesseract not available
                if classification.needs_ocr and not self._ocr_available:
                    logger.warning(
                        f"Skipping {len(page_items)} annotations on page {page_num} "
                        "(image-based page, OCR unavailable)"
                    )
                    for item in page_items:
                        annotation_results.append(AnnotationResult(
                            success=False,
                            provenance_item=item,
                            error="Image-based page requires OCR (Tesseract not available)"
                        ))
                    continue

                # Locate and annotate each item
                matches_to_annotate = []

                for item in page_items:
                    matches = self.locator.locate_text(
                        page,
                        item.text_snippet,
                        classification.page_type
                    )

                    if matches:
                        # Use first (best) match
                        matches_to_annotate.append((item, matches[0]))
                    else:
                        annotation_results.append(AnnotationResult(
                            success=False,
                            provenance_item=item,
                            error="No match found with any search strategy"
                        ))

                # Render annotations for this page
                if matches_to_annotate:
                    page_results = self.renderer.annotate_page(
                        page,
                        matches_to_annotate,
                        classification.page_type
                    )
                    annotation_results.extend(page_results)

            # Step 4: Generate bookmarks
            logger.info("Step 4: Generating bookmarks")
            bookmarks_created = self.bookmark_gen.generate_bookmarks(
                doc,
                annotation_results,
                items_by_module
            )

            # Step 5: Update document metadata
            from datetime import datetime
            annotation_timestamp = datetime.now().isoformat()
            add_document_metadata(
                doc,
                protocol_id,
                annotation_timestamp
            )

            # Step 6: Save annotated PDF
            annotated_filename = generate_annotation_filename(protocol_id)
            annotated_path = output_dir / annotated_filename

            logger.info(f"Step 5: Saving annotated PDF to {annotated_path}")
            doc.save(annotated_path, garbage=4, deflate=True)
            doc.close()

            # Step 7: Generate and save report
            logger.info("Step 6: Generating annotation report")
            report = self.output_gen.create_report(
                source_pdf=str(pdf_path),
                annotated_pdf=str(annotated_path),
                collection_stats=collection_stats,
                annotation_results=annotation_results,
                page_classifications=page_classifications,
                bookmarks_created=bookmarks_created
            )

            report_filename = generate_report_filename(protocol_id)
            report_path = output_dir / report_filename
            self.output_gen.save_report(report_path)

            # Calculate final statistics
            successful = sum(1 for r in annotation_results if r.success)
            failed = sum(1 for r in annotation_results if not r.success)
            total = successful + failed
            success_rate = (successful / total * 100) if total > 0 else 0

            # Log warnings if success rate is low
            min_success_rate = self.config.get("min_success_rate", 0.80) * 100
            if success_rate < min_success_rate:
                logger.warning(
                    f"Annotation success rate ({success_rate:.1f}%) below threshold ({min_success_rate:.1f}%)"
                )

            logger.info(
                f"PDF annotation complete: {successful}/{total} annotations successful "
                f"({success_rate:.1f}%)"
            )

            return PDFAnnotationResult(
                success=True,
                annotated_pdf_path=annotated_path,
                report_path=report_path,
                success_rate=success_rate,
                total_annotations=total,
                successful_annotations=successful,
                failed_annotations=failed,
                report=report
            )

        except Exception as e:
            logger.error(f"PDF annotation failed: {e}", exc_info=True)
            return PDFAnnotationResult(
                success=False,
                error=str(e)
            )

    def _extract_protocol_id(self, usdm_json: dict, pdf_path: Path) -> str:
        """
        Extract protocol ID from USDM JSON or derive from PDF filename.

        Args:
            usdm_json: USDM JSON document
            pdf_path: Path to PDF file

        Returns:
            Protocol ID string
        """
        # Try to get from study metadata
        try:
            # Check various paths where protocol ID might be
            if "study" in usdm_json:
                study = usdm_json["study"]
                if "id" in study:
                    return study["id"]
                if "name" in study:
                    return study["name"][:50]

            if "id" in usdm_json:
                return usdm_json["id"]

            if "sourceDocument" in usdm_json:
                doc_info = usdm_json["sourceDocument"]
                if "documentId" in doc_info:
                    return doc_info["documentId"]

        except (KeyError, TypeError):
            pass

        # Fall back to PDF filename
        return pdf_path.stem

    def validate_config(self) -> list[str]:
        """
        Validate the annotation configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check fuzzy threshold
        fuzzy_threshold = self.config.get("fuzzy_threshold", 0.85)
        if not 0 < fuzzy_threshold <= 1:
            errors.append(f"fuzzy_threshold must be between 0 and 1, got {fuzzy_threshold}")

        # Check highlight opacity
        opacity = self.config.get("highlight_opacity", 0.3)
        if not 0 < opacity <= 1:
            errors.append(f"highlight_opacity must be between 0 and 1, got {opacity}")

        # Check OCR
        if not self._ocr_available:
            errors.append(
                "Tesseract OCR not installed. Image-based pages cannot be annotated."
            )

        return errors


def create_annotator_from_config(config_path: Path | str) -> PDFAnnotatorService:
    """
    Create a PDFAnnotatorService from a YAML config file.

    Args:
        config_path: Path to config.yaml

    Returns:
        Configured PDFAnnotatorService
    """
    import yaml

    config_path = Path(config_path)

    if not config_path.exists():
        logger.warning(f"Config file not found: {config_path}, using defaults")
        return PDFAnnotatorService()

    with open(config_path, 'r') as f:
        full_config = yaml.safe_load(f)

    annotation_config = full_config.get("annotation", {})

    return PDFAnnotatorService(config=annotation_config)
