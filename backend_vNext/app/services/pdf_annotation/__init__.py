"""
PDF Annotation Service

This module provides functionality to annotate PDF documents with highlighted
provenance text snippets from USDM 4.0 extraction results.

Components:
- ProvenanceCollector: Traverses USDM JSON to extract provenance objects
- PageClassifier: Classifies PDF pages as text-based or image-based
- TextLocator: Finds text positions in PDF using multiple search strategies
- AnnotationRenderer: Renders highlights and popup comments on PDF pages
- BookmarkGenerator: Creates PDF bookmark tree organized by module
- AnnotationOutput: Generates annotation report JSON
- PDFAnnotatorService: Main orchestrator that coordinates all components
"""

from .provenance_collector import ProvenanceCollector, ProvenanceItem
from .page_classifier import PageClassifier, PageType
from .text_locator import TextLocator, TextMatch
from .annotation_renderer import AnnotationRenderer, AnnotationStyle
from .bookmark_generator import BookmarkGenerator
from .annotation_output import AnnotationOutput, AnnotationReport
from .pdf_annotator_service import PDFAnnotatorService, AnnotationResult
from .soa_provenance_adapter import SOAProvenanceAdapter, load_soa_usdm
from .soa_annotation_service import SOAAnnotationService, add_soa_annotations_to_pdf, SOAAnnotationResult

__all__ = [
    "ProvenanceCollector",
    "ProvenanceItem",
    "PageClassifier",
    "PageType",
    "TextLocator",
    "TextMatch",
    "AnnotationRenderer",
    "AnnotationStyle",
    "BookmarkGenerator",
    "AnnotationOutput",
    "AnnotationReport",
    "PDFAnnotatorService",
    "AnnotationResult",
    "SOAProvenanceAdapter",
    "load_soa_usdm",
    "SOAAnnotationService",
    "add_soa_annotations_to_pdf",
    "SOAAnnotationResult",
]
