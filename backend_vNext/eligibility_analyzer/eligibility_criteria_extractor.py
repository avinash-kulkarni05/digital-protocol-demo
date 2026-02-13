"""
Eligibility Criteria Extractor - Phase 2 of Eligibility Extraction Pipeline

Two-phase extraction using Gemini 2.5 Pro:
- Phase 2a: Extract all criteria with type classification
- Phase 2b: Enhance with precise provenance (page + text snippet)

Key Features:
- Two-phase extraction for quality assurance
- Provenance tracking with page numbers and text snippets
- Cross-reference detection and resolution
- Raw criteria preservation (exact text from protocol)
- Azure OpenAI (gpt-5-mini) fallback when Gemini fails

Usage:
    from eligibility_analyzer.eligibility_criteria_extractor import EligibilityCriteriaExtractor

    extractor = EligibilityCriteriaExtractor()
    result = extractor.extract(pdf_path, section_detection_result)
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import google.generativeai as genai
from openai import AzureOpenAI
import fitz  # PyMuPDF for PDF text extraction
from dotenv import load_dotenv

from eligibility_analyzer.eligibility_section_detector import DetectionResult, CrossReference

load_dotenv()

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

MAX_SNIPPET_LENGTH = 500  # Maximum length for text snippets

# Phase 2a: Criteria Extraction Prompt
CRITERIA_EXTRACTION_PROMPT = """You are extracting eligibility criteria from a clinical trial protocol.

## DETECTED SECTIONS
- Inclusion Criteria: Pages {inc_start} to {inc_end}
- Exclusion Criteria: Pages {exc_start} to {exc_end}

## TASK
Extract ALL inclusion and exclusion criteria from the protocol. For each criterion:
1. Preserve the EXACT original text (do not paraphrase)
2. Classify as "Inclusion" or "Exclusion"
3. Capture the criterion number/ID if present
4. Note any cross-references to other sections

## EXTRACTION RULES
1. **Preserve exact text**: Copy criterion text verbatim including numbers, symbols, units
2. **Include sub-criteria**: If criterion has sub-items (a, b, c), include them as part of the criterion
3. **Capture cross-references**: Note any "see Section X", "refer to Appendix Y" references
4. **Split correctly**: Each numbered criterion should be a separate item (1, 2, 3 OR a, b, c)
5. **Don't skip**: Extract ALL criteria, even if they seem redundant or complex

## OUTPUT FORMAT (JSON only)
{{
  "criteria": [
    {{
      "criterionId": "<number from protocol, e.g., '1' or '5.2.1.a'>",
      "originalText": "<exact verbatim text from protocol>",
      "type": "Inclusion" or "Exclusion",
      "hasSubCriteria": <boolean>,
      "subCriteria": [
        {{
          "subId": "a",
          "text": "<sub-criterion text>"
        }}
      ],
      "crossReferences": [
        {{
          "referenceText": "<e.g., 'see Appendix A'>",
          "targetSection": "<e.g., 'Appendix A'>"
        }}
      ]
    }}
  ],
  "extractionNotes": "<any issues or observations during extraction>",
  "counts": {{
    "inclusion": <number>,
    "exclusion": <number>,
    "total": <number>
  }}
}}

## IMPORTANT
- Return valid JSON only - no additional text
- Do NOT paraphrase - use exact text from the protocol
- Include ALL criteria - do not skip any
- If a criterion spans multiple paragraphs, include the full text

Now extract all criteria from the protocol."""


# Phase 2b: Provenance Enhancement Prompt
PROVENANCE_ENHANCEMENT_PROMPT = """You are adding provenance information to extracted eligibility criteria.

## EXTRACTED CRITERIA
{criteria_json}

## TASK
For EACH criterion above, find the EXACT location in the protocol PDF:
1. Page number where the criterion appears
2. Text snippet (first 500 characters) showing the criterion in context

## RULES
1. Page numbers are 1-indexed (first page = 1)
2. Text snippet should start at or just before the criterion text
3. Include enough context to verify the criterion
4. If criterion spans multiple pages, use the start page

## OUTPUT FORMAT (JSON only)
{{
  "criteria": [
    {{
      "criterionId": "<same ID from input>",
      "type": "<Inclusion or Exclusion - same as input>",
      "provenance": {{
        "pageNumber": <integer>,
        "textSnippet": "<up to 500 chars of source text>",
        "confidence": <0.0-1.0>
      }}
    }}
  ]
}}

IMPORTANT: Include BOTH criterionId AND type in each output entry, as the same
criterionId can exist for both Inclusion and Exclusion criteria (e.g., criterion "1"
may exist as both Inclusion criterion 1 and Exclusion criterion 1).

Find the provenance for each criterion now."""


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class Provenance:
    """Provenance information for a criterion."""
    page_number: int
    text_snippet: str
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pageNumber": self.page_number,
            "textSnippet": self.text_snippet[:MAX_SNIPPET_LENGTH] if self.text_snippet else "",
            "confidence": self.confidence,
        }


@dataclass
class SubCriterion:
    """Sub-criterion within a parent criterion."""
    sub_id: str
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subId": self.sub_id,
            "text": self.text,
        }


@dataclass
class RawCriterion:
    """Raw extracted criterion before interpretation."""
    criterion_id: str
    original_text: str
    criterion_type: str  # "Inclusion" or "Exclusion"
    has_sub_criteria: bool = False
    sub_criteria: List[SubCriterion] = field(default_factory=list)
    cross_references: List[Dict[str, str]] = field(default_factory=list)
    provenance: Optional[Provenance] = None
    resolved_references: Dict[str, str] = field(default_factory=dict)

    @property
    def unique_criterion_id(self) -> str:
        """
        Generate unique criterion ID by prefixing with type.

        This ensures Inclusion criterion "1" and Exclusion criterion "1"
        have distinct IDs: "INC_1" and "EXC_1" respectively.

        This prevents the duplicate criterionId bug where OMOP mappings
        from unrelated criteria would bleed into each other.
        """
        prefix = "INC" if self.criterion_type == "Inclusion" else "EXC"

        # Strip any existing INC_/EXC_ prefix to avoid double-prefixing
        # This handles cases where the LLM already returned a prefixed ID
        clean_id = self.criterion_id or ""  # Handle None from LLM returning null
        if clean_id.startswith("INC_"):
            clean_id = clean_id[4:]
        elif clean_id.startswith("EXC_"):
            clean_id = clean_id[4:]

        return f"{prefix}_{clean_id}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "criterionId": self.unique_criterion_id,  # Use unique ID with INC_/EXC_ prefix
            "originalCriterionId": self.criterion_id,  # Preserve original for display
            "originalText": self.original_text,
            "type": self.criterion_type,
            "instanceType": "EligibilityCriterion",  # USDM 4.0 compliance
            "hasSubCriteria": self.has_sub_criteria,
            "subCriteria": [sc.to_dict() for sc in self.sub_criteria],
            "crossReferences": self.cross_references,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "resolvedReferences": self.resolved_references if self.resolved_references else None,
        }


@dataclass
class ExtractionResult:
    """Result from criteria extraction."""
    success: bool
    criteria: List[RawCriterion] = field(default_factory=list)
    inclusion_count: int = 0
    exclusion_count: int = 0
    extraction_notes: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "criteria": [c.to_dict() for c in self.criteria],
            "counts": {
                "inclusion": self.inclusion_count,
                "exclusion": self.exclusion_count,
                "total": len(self.criteria),
            },
            "extractionNotes": self.extraction_notes,
            "error": self.error,
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _clean_json(text: str) -> str:
    """Strip markdown code fences from LLM response."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _truncate_snippet(text: str, max_length: int = MAX_SNIPPET_LENGTH) -> str:
    """Truncate text snippet to maximum length."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


# =============================================================================
# MAIN EXTRACTOR CLASS
# =============================================================================


class EligibilityCriteriaExtractor:
    """
    Extracts eligibility criteria from protocol PDFs using two-phase Gemini extraction.

    Phase 2a: Extract all criteria text with type classification
    Phase 2b: Add provenance (page numbers, text snippets)
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        model: str = "gemini-2.5-pro"
    ):
        """
        Initialize the extractor.

        Args:
            gemini_api_key: API key for Gemini (falls back to env var)
            model: Gemini model to use
        """
        self.gemini_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.model = model

        if not self.gemini_key:
            raise ValueError("GEMINI_API_KEY not set")

        genai.configure(api_key=self.gemini_key)

        # Initialize Azure OpenAI fallback client
        self._azure_client: Optional[AzureOpenAI] = None
        self._azure_deployment: Optional[str] = None
        self._init_azure_fallback()

        logger.info(f"EligibilityCriteriaExtractor initialized with model: {model}")

    def _init_azure_fallback(self) -> None:
        """Initialize Azure OpenAI client for fallback."""
        azure_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
        azure_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-01-preview")

        if azure_key and azure_endpoint:
            try:
                self._azure_client = AzureOpenAI(
                    api_key=azure_key,
                    api_version=azure_version,
                    azure_endpoint=azure_endpoint,
                    timeout=120.0
                )
                self._azure_deployment = azure_deployment
                logger.info(f"Azure OpenAI fallback initialized: {azure_deployment}")
            except Exception as e:
                logger.warning(f"Failed to initialize Azure OpenAI fallback: {e}")
        else:
            logger.info("Azure OpenAI credentials not found - fallback disabled")

    def _extract_pdf_text_for_fallback(self, pdf_path: str, max_pages: int = 50) -> str:
        """Extract text from PDF for Azure OpenAI text-based fallback."""
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            pages_to_extract = min(total_pages, max_pages)

            text_parts = []
            for page_num in range(pages_to_extract):
                page = doc[page_num]
                page_text = page.get_text()
                text_parts.append(f"=== PAGE {page_num + 1} ===\n{page_text}")

            doc.close()

            full_text = "\n\n".join(text_parts)
            # Truncate to avoid token limits
            if len(full_text) > 150000:
                full_text = full_text[:150000] + "\n\n[TEXT TRUNCATED]"

            return full_text
        except Exception as e:
            logger.error(f"Failed to extract PDF text: {e}")
            return ""

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if error is retryable."""
        error_str = str(error).lower()
        retryable_patterns = [
            "503", "504", "429", "rate limit", "deadline",
            "timeout", "resource exhausted", "connection"
        ]
        return any(p in error_str for p in retryable_patterns)

    def _extract_criteria_with_azure(
        self,
        pdf_path: str,
        original_prompt: str
    ) -> Optional[Dict[str, Any]]:
        """
        Extract criteria using Azure OpenAI (text-based fallback).

        Args:
            pdf_path: Path to PDF file
            original_prompt: The extraction prompt

        Returns:
            Parsed JSON data or None if failed
        """
        if not self._azure_client or not self._azure_deployment:
            return None

        logger.info("Azure OpenAI fallback: Extracting PDF text...")
        pdf_text = self._extract_pdf_text_for_fallback(pdf_path)

        if not pdf_text:
            logger.error("Azure fallback failed: Could not extract PDF text")
            return None

        # Build text-based prompt
        text_prompt = f"""You are extracting eligibility criteria from a clinical trial protocol.

## PROTOCOL TEXT (with page markers)
{pdf_text}

{original_prompt}"""

        try:
            logger.info(f"Calling Azure OpenAI fallback ({self._azure_deployment})...")
            response = self._azure_client.chat.completions.create(
                model=self._azure_deployment,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a clinical protocol analyst. Extract eligibility criteria and return valid JSON only."
                    },
                    {"role": "user", "content": text_prompt}
                ],
                max_completion_tokens=16384,
                response_format={"type": "json_object"}
            )

            if response and response.choices:
                content = response.choices[0].message.content
                if content:
                    logger.info("Azure OpenAI fallback succeeded")
                    return json.loads(_clean_json(content))

        except Exception as e:
            logger.error(f"Azure OpenAI fallback failed: {e}")

        return None

    def extract(
        self,
        pdf_path: str,
        detection_result: DetectionResult,
        gemini_file_uri: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Extract criteria from protocol PDF using two-phase approach.

        Args:
            pdf_path: Path to protocol PDF
            detection_result: Section detection result from Phase 1
            gemini_file_uri: Optional pre-uploaded Gemini file URI

        Returns:
            ExtractionResult with all extracted criteria
        """
        if not detection_result.success:
            return ExtractionResult(
                success=False,
                error="Section detection failed - cannot extract criteria"
            )

        try:
            # Use existing Gemini file from detection result, or upload if not available
            uploaded_file = None

            # First try to use the gemini_file_uri from detection_result
            if detection_result.gemini_file_uri:
                try:
                    logger.info(f"Reusing Gemini file from detection: {detection_result.gemini_file_uri}")
                    uploaded_file = genai.get_file(detection_result.gemini_file_uri)
                except Exception as e:
                    logger.warning(f"Failed to get cached Gemini file: {e}, will re-upload")

            # Fall back to provided gemini_file_uri parameter
            if not uploaded_file and gemini_file_uri:
                try:
                    logger.info(f"Using provided Gemini file URI: {gemini_file_uri}")
                    uploaded_file = genai.get_file(gemini_file_uri)
                except Exception as e:
                    logger.warning(f"Failed to get provided Gemini file: {e}, will re-upload")

            # Last resort: upload the PDF
            if not uploaded_file:
                logger.info("Uploading PDF to Gemini for criteria extraction...")
                uploaded_file = genai.upload_file(pdf_path)

            # Phase 2a: Extract criteria
            logger.info("Phase 2a: Extracting criteria text...")
            raw_criteria = self._extract_criteria(
                uploaded_file,
                detection_result.inclusion_section,
                detection_result.exclusion_section,
                pdf_path=pdf_path
            )

            if not raw_criteria:
                return ExtractionResult(
                    success=False,
                    error="No criteria extracted from Phase 2a"
                )

            # Phase 2b: Add provenance
            logger.info("Phase 2b: Adding provenance information...")
            criteria_with_provenance = self._add_provenance(
                uploaded_file,
                raw_criteria,
                detection_result
            )

            # Phase 2c: Resolve cross-references
            logger.info("Phase 2c: Resolving cross-references...")
            final_criteria = self._resolve_cross_references(
                uploaded_file,
                criteria_with_provenance,
                detection_result.cross_references
            )

            # Count by type
            inclusion_count = sum(1 for c in final_criteria if c.criterion_type == "Inclusion")
            exclusion_count = sum(1 for c in final_criteria if c.criterion_type == "Exclusion")

            logger.info(f"Extraction complete: {inclusion_count} inclusion, {exclusion_count} exclusion criteria")

            return ExtractionResult(
                success=True,
                criteria=final_criteria,
                inclusion_count=inclusion_count,
                exclusion_count=exclusion_count,
            )

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return ExtractionResult(
                success=False,
                error=str(e)
            )

    def _extract_criteria(
        self,
        uploaded_file: Any,
        inclusion_section: Any,
        exclusion_section: Any,
        pdf_path: Optional[str] = None
    ) -> List[RawCriterion]:
        """
        Phase 2a: Extract criteria text from PDF.

        Uses Gemini to read the PDF and extract all criteria.
        Falls back to Azure OpenAI with text extraction if Gemini fails.
        """
        gemini_model = genai.GenerativeModel("gemini-2.5-pro")

        # Build extraction prompt
        inc_start = inclusion_section.page_start if inclusion_section else 1
        inc_end = inclusion_section.page_end if inclusion_section else 1
        exc_start = exclusion_section.page_start if exclusion_section else inc_end
        exc_end = exclusion_section.page_end if exclusion_section else exc_start

        prompt = CRITERIA_EXTRACTION_PROMPT.format(
            inc_start=inc_start,
            inc_end=inc_end,
            exc_start=exc_start,
            exc_end=exc_end
        )

        data = None

        # Try Gemini first
        try:
            response = gemini_model.generate_content(
                [uploaded_file, prompt],
                generation_config={"max_output_tokens": 65536}
            )
            data = json.loads(_clean_json(response.text))

        except Exception as gemini_error:
            if self._is_retryable_error(gemini_error) and self._azure_client and pdf_path:
                logger.warning(f"Gemini failed: {gemini_error}. Trying Azure OpenAI fallback...")
                data = self._extract_criteria_with_azure(pdf_path, prompt)
            else:
                raise

        if not data:
            logger.error("Both Gemini and Azure fallback failed for criteria extraction")
            return []

        criteria = []
        for item in data.get("criteria", []):
            # Parse sub-criteria
            sub_criteria = []
            for sc in item.get("subCriteria", []):
                sub_criteria.append(SubCriterion(
                    sub_id=sc.get("subId", ""),
                    text=sc.get("text", "")
                ))

            criterion = RawCriterion(
                criterion_id=item.get("criterionId", ""),
                original_text=item.get("originalText", ""),
                criterion_type=item.get("type", "Inclusion"),
                has_sub_criteria=item.get("hasSubCriteria", False),
                sub_criteria=sub_criteria,
                cross_references=item.get("crossReferences", []),
            )
            criteria.append(criterion)

        logger.info(f"Phase 2a: Extracted {len(criteria)} criteria")
        return criteria

    def _add_provenance(
        self,
        uploaded_file: Any,
        criteria: List[RawCriterion],
        detection_result: DetectionResult
    ) -> List[RawCriterion]:
        """
        Phase 2b: Add provenance information to each criterion.

        Uses Gemini to find exact page and text snippet for each criterion.
        """
        gemini_model = genai.GenerativeModel("gemini-2.5-pro")

        # Build criteria JSON for the prompt
        criteria_json = json.dumps([{
            "criterionId": c.criterion_id,
            "originalText": c.original_text[:500],  # Truncate for prompt
            "type": c.criterion_type
        } for c in criteria], indent=2)

        prompt = PROVENANCE_ENHANCEMENT_PROMPT.format(criteria_json=criteria_json)

        # Get provenance using Gemini
        response = gemini_model.generate_content(
            [uploaded_file, prompt],
            generation_config={"max_output_tokens": 65536}
        )

        # Parse response
        data = json.loads(_clean_json(response.text))

        # Build lookup using composite key (criterionId, type)
        # This prevents Exclusion criteria from overwriting Inclusion criteria with same ID
        provenance_lookup = {}
        for item in data.get("criteria", []):
            crit_id = item.get("criterionId", "")
            crit_type = item.get("type", "Inclusion")  # Default to Inclusion if missing
            prov = item.get("provenance", {})
            # Use composite key to distinguish Inclusion vs Exclusion with same ID
            lookup_key = (crit_id, crit_type)
            provenance_lookup[lookup_key] = Provenance(
                page_number=prov.get("pageNumber", 0),
                text_snippet=_truncate_snippet(prov.get("textSnippet", "")),
                confidence=prov.get("confidence", 0.8)
            )

        # Apply provenance to criteria using composite key
        for criterion in criteria:
            lookup_key = (criterion.criterion_id, criterion.criterion_type)
            if lookup_key in provenance_lookup:
                criterion.provenance = provenance_lookup[lookup_key]
            else:
                # Default provenance based on type
                if criterion.criterion_type == "Inclusion" and detection_result.inclusion_section:
                    criterion.provenance = Provenance(
                        page_number=detection_result.inclusion_section.page_start,
                        text_snippet="",
                        confidence=0.5
                    )
                elif criterion.criterion_type == "Exclusion" and detection_result.exclusion_section:
                    criterion.provenance = Provenance(
                        page_number=detection_result.exclusion_section.page_start,
                        text_snippet="",
                        confidence=0.5
                    )

        logger.info(f"Phase 2b: Added provenance to {len(criteria)} criteria")
        return criteria

    def _resolve_cross_references(
        self,
        uploaded_file: Any,
        criteria: List[RawCriterion],
        global_cross_refs: List[CrossReference]
    ) -> List[RawCriterion]:
        """
        Phase 2c: Resolve cross-references in criteria (BATCHED for performance).

        All cross-references are resolved in a SINGLE Gemini call instead of
        N separate calls, reducing API latency from N*20s to ~20s total.
        """
        gemini_model = genai.GenerativeModel("gemini-2.5-pro")

        # Collect all unique cross-references
        all_refs = {}

        # From criteria
        for criterion in criteria:
            for xref in criterion.cross_references:
                target = xref.get("targetSection", "")
                if target and target not in all_refs:
                    all_refs[target] = xref.get("referenceText", "")

        # From global detection
        for gxref in global_cross_refs:
            if gxref.target_section not in all_refs:
                all_refs[gxref.target_section] = gxref.reference_text

        if not all_refs:
            logger.info("Phase 2c: No cross-references to resolve")
            return criteria

        logger.info(f"Phase 2c: Resolving {len(all_refs)} cross-references in single batch call")

        # Build batched prompt for ALL cross-references
        refs_list = []
        for i, (target, ref_text) in enumerate(all_refs.items(), 1):
            refs_list.append({
                "id": i,
                "targetSection": target,
                "referenceText": ref_text
            })

        batch_prompt = f"""Find and extract content from multiple sections referenced in eligibility criteria.

## CROSS-REFERENCES TO RESOLVE
{json.dumps(refs_list, indent=2)}

## TASK
For EACH cross-reference above:
1. Find the target section in this protocol
2. Extract the specific requirements, lists, or criteria relevant for eligibility evaluation
3. Return the content (max 2000 chars per section)

## OUTPUT FORMAT (JSON only)
{{
  "resolutions": [
    {{
      "id": <number matching input>,
      "targetSection": "<section name>",
      "found": true/false,
      "page": <page number if found>,
      "content": "<extracted text, max 2000 chars>",
      "summary": "<1-2 sentence summary>"
    }}
  ]
}}

Resolve ALL cross-references now."""

        resolved = {}
        try:
            response = gemini_model.generate_content(
                [uploaded_file, batch_prompt],
                generation_config={"max_output_tokens": 65536}
            )
            data = json.loads(_clean_json(response.text))

            for resolution in data.get("resolutions", []):
                if resolution.get("found"):
                    target = resolution.get("targetSection", "")
                    content = resolution.get("content", "")
                    if target and content:
                        resolved[target] = content
                        logger.info(f"Resolved cross-reference: {target}")
                else:
                    target = resolution.get("targetSection", "")
                    logger.warning(f"Cross-reference not found: {target}")

        except Exception as e:
            logger.error(f"Batch cross-reference resolution failed: {e}")
            # Fall back to individual resolution if batch fails
            logger.info("Falling back to individual cross-reference resolution...")
            for target, ref_text in all_refs.items():
                prompt = f"""Find the section "{target}" in this protocol and extract its relevant content.

This section is referenced in eligibility criteria: "{ref_text}"

Extract the specific requirements, lists, or criteria from this section that are relevant for eligibility evaluation.

Return JSON:
{{
  "found": true/false,
  "page": <page number>,
  "content": "<extracted text, max 2000 chars>",
  "summary": "<1-2 sentence summary>"
}}"""

                try:
                    response = gemini_model.generate_content([uploaded_file, prompt])
                    data = json.loads(_clean_json(response.text))
                    if data.get("found"):
                        resolved[target] = data.get("content", "")
                        logger.info(f"Resolved cross-reference: {target}")
                except Exception as e2:
                    logger.warning(f"Failed to resolve {target}: {e2}")

        # Apply resolved content to criteria
        for criterion in criteria:
            for xref in criterion.cross_references:
                target = xref.get("targetSection", "")
                if target in resolved:
                    criterion.resolved_references[target] = resolved[target]

        logger.info(f"Phase 2c: Resolved {len(resolved)} cross-references")
        return criteria


# =============================================================================
# CLI SUPPORT
# =============================================================================


if __name__ == "__main__":
    import sys
    from eligibility_analyzer.eligibility_section_detector import detect_eligibility_sections

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    if len(sys.argv) < 2:
        print("Usage: python eligibility_criteria_extractor.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    print(f"Extracting eligibility criteria from: {pdf_path}")

    try:
        # Phase 1: Detect sections
        print("\n=== Phase 1: Section Detection ===")
        detection_result = detect_eligibility_sections(pdf_path)

        if not detection_result.success:
            print(f"Section detection failed: {detection_result.error}")
            sys.exit(1)

        print(f"Inclusion: pages {detection_result.inclusion_section.page_start}-{detection_result.inclusion_section.page_end}")
        print(f"Exclusion: pages {detection_result.exclusion_section.page_start}-{detection_result.exclusion_section.page_end}")

        # Phase 2: Extract criteria
        print("\n=== Phase 2: Criteria Extraction ===")
        extractor = EligibilityCriteriaExtractor()
        result = extractor.extract(pdf_path, detection_result)

        if result.success:
            print(f"\nExtracted {result.inclusion_count} inclusion, {result.exclusion_count} exclusion criteria")

            print("\n=== Sample Criteria ===")
            for i, criterion in enumerate(result.criteria[:5]):
                print(f"\n{i+1}. [{criterion.criterion_type}] {criterion.criterion_id}")
                print(f"   Text: {criterion.original_text[:100]}...")
                if criterion.provenance:
                    print(f"   Page: {criterion.provenance.page_number}")

            print("\n=== Full JSON ===")
            print(json.dumps(result.to_dict(), indent=2)[:5000])
        else:
            print(f"Extraction failed: {result.error}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
