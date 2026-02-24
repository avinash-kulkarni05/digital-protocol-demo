"""
SOA HTML Interpreter - Claude-based interpretation of extracted HTML tables.

Takes HTML from LandingAI and produces complete USDM-ready structure.
This is the core component of the HTML-First architecture.

v3.1: Two-Phase Extraction with LLM-Driven Timepoint Detection
- Phase 1: Extract visits (with timingModifier/parentVisit), activities, footnotes
- Phase 2: Extract compact activity-visit matrix (simplified - no 't' key needed)
- Phase 3: Expand matrix to full SAI objects (Python, no LLM)

Key Design:
- NEVER merge timepoint columns (BI/EOI/pre-dose/post-dose)
- Each column = separate encounter with timingModifier field
- LLM uses clinical judgment to detect timepoints (no hardcoded pattern list)
- parentVisit field groups related timepoint encounters
- visitGroups index provides downstream grouping

Usage:
    from soa_analyzer.soa_html_interpreter import SOAHTMLInterpreter

    interpreter = SOAHTMLInterpreter()
    result = await interpreter.interpret(html_tables, protocol_id)
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from anthropic import Anthropic
from dotenv import load_dotenv
import google.generativeai as genai

from .soa_html_grid_parser import HTMLGridParser, parse_html_tables

logger = logging.getLogger(__name__)

# Prompt directory
PROMPT_DIR = Path(__file__).parent / "prompts"


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _load_prompt(filename: str) -> str:
    """Load prompt from file."""
    path = PROMPT_DIR / filename
    if path.exists():
        with open(path, 'r') as f:
            return f.read()
    else:
        raise FileNotFoundError(f"Prompt file not found: {path}")


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


# ============================================================================
# FOOTNOTE EXTRACTION & VALIDATION
# ============================================================================

def _extract_footnotes_deterministic(html_content: str) -> List[Dict[str, str]]:
    """
    Deterministically extract footnotes from HTML content using regex.

    This is a fallback when LLM misses footnotes.
    """
    footnotes = []
    seen_markers = set()

    # Pattern 1: Standard footnote format
    standard_pattern = r'(?:^|\n)\s*([a-z]|[0-9]+)[.\)]\s*([^\n]+(?:\n(?![a-z][.\)]|\d+[.\)]).*)*)'

    for match in re.finditer(standard_pattern, html_content, re.MULTILINE | re.IGNORECASE):
        marker = match.group(1).lower()
        text = match.group(2).strip()

        text = re.sub(r'\n\s*\d+\s*$', '', text)
        text = re.sub(r'\n\s*<!-- Page \d+ -->', '', text)
        text = ' '.join(text.split())

        if marker not in seen_markers and len(text) > 10:
            footnotes.append({
                'marker': marker,
                'text': text,
                'ruleType': 'reference',
                'structuredRule': {},
                'appliesTo': []
            })
            seen_markers.add(marker)

    # Pattern 2: Inline footnotes
    inline_pattern = r'(?<=[.!?\s])([a-z])[.\)]\s+([A-Z][^.!?]*(?:[.!?](?![a-z][.\)]))*[.!?]?)'

    for match in re.finditer(inline_pattern, html_content):
        marker = match.group(1).lower()
        text = match.group(2).strip()

        if marker not in seen_markers and len(text) > 10:
            footnotes.append({
                'marker': marker,
                'text': text,
                'ruleType': 'reference',
                'structuredRule': {},
                'appliesTo': []
            })
            seen_markers.add(marker)

    def sort_key(fn):
        m = fn['marker']
        if m.isalpha():
            return (0, m)
        return (1, int(m))

    footnotes.sort(key=sort_key)
    logger.debug(f"Deterministic extraction found {len(footnotes)} footnotes: {[f['marker'] for f in footnotes]}")
    return footnotes


def _find_expected_footnote_markers(html_content: str) -> set:
    """Find all footnote markers referenced in the HTML table content.

    Uses a two-pass approach: first collect candidate markers from <sup> tags
    and unicode superscripts, then only keep those that also have a matching
    footnote definition in the text (e.g., "a. Some text..." or "a) Some text...").
    This prevents false positives from scientific notation (CO2, mg/m2, etc.).
    """
    # --- Pass 1: Collect candidate markers from superscripts ---
    sup_candidates = set()

    # Superscript tags
    sup_pattern = r'<sup[^>]*>([a-z0-9,\s]+)</sup>'
    for match in re.finditer(sup_pattern, html_content, re.IGNORECASE):
        content = match.group(1)
        for char in content:
            if char.isalnum():
                sup_candidates.add(char.lower())

    # Unicode superscripts
    unicode_superscripts = {
        'ᵃ': 'a', 'ᵇ': 'b', 'ᶜ': 'c', 'ᵈ': 'd', 'ᵉ': 'e', 'ᶠ': 'f',
        'ᵍ': 'g', 'ʰ': 'h', 'ⁱ': 'i', 'ʲ': 'j', 'ᵏ': 'k', 'ˡ': 'l',
        'ᵐ': 'm', 'ⁿ': 'n', 'ᵒ': 'o', 'ᵖ': 'p', 'ʳ': 'r', 'ˢ': 's',
        'ᵗ': 't', 'ᵘ': 'u', 'ᵛ': 'v', 'ʷ': 'w', 'ˣ': 'x', 'ʸ': 'y',
        'ᶻ': 'z', '¹': '1', '²': '2', '³': '3', '⁴': '4', '⁵': '5',
        '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9', '⁰': '0', '*': '*',
        '\u1d43': 'a', '\u1d47': 'b', '\u1d9c': 'c', '\u1d48': 'd',
        '\u1d49': 'e', '\u1da0': 'f', '\u1d4d': 'g', '\u02b0': 'h',
        '\u2071': 'i', '\u02b2': 'j', '\u1d4f': 'k', '\u02e1': 'l',
        '\u1d50': 'm', '\u207f': 'n', '\u1d52': 'o', '\u1d56': 'p',
        '\u02b3': 'r', '\u02e2': 's', '\u1d57': 't', '\u1d58': 'u',
        '\u1d5b': 'v', '\u02b7': 'w', '\u02e3': 'x', '\u02b8': 'y',
        '\u1dbb': 'z', '\u00b9': '1', '\u00b2': '2', '\u00b3': '3',
        '\u2074': '4', '\u2075': '5', '\u2076': '6', '\u2077': '7',
        '\u2078': '8', '\u2079': '9', '\u2070': '0',
    }

    for sup_char, normal_char in unicode_superscripts.items():
        if sup_char in html_content:
            sup_candidates.add(normal_char)

    # --- Pass 2: Find markers that have footnote definitions ---
    # A marker is only "expected" if it appears as a footnote definition
    # (e.g., "a. Some text" or "a) Some text" at start of line)
    defined_markers = set()
    definition_pattern = r'(?:^|\n)\s*([a-z0-9])[.\)]\s+[A-Z]'
    for match in re.finditer(definition_pattern, html_content, re.MULTILINE):
        defined_markers.add(match.group(1).lower())

    # Also check for <sup> marker followed by definition text nearby
    # (handles cases like "<sup>a</sup> Within 28 days...")
    sup_def_pattern = r'<sup[^>]*>([a-z0-9])</sup>\s*[.)\s]*([A-Z][^<]{10,})'
    for match in re.finditer(sup_def_pattern, html_content, re.IGNORECASE):
        defined_markers.add(match.group(1).lower())

    # Only keep superscript candidates that have a matching definition
    # This filters out false positives like CO2, mg/m2, etc.
    markers = sup_candidates & defined_markers

    # If no definitions found at all (unusual), fall back to all candidates
    # to avoid breaking protocols with non-standard footnote formatting
    if not defined_markers and sup_candidates:
        logger.warning(
            f"No footnote definitions found in HTML but {len(sup_candidates)} "
            f"superscript candidates exist. Using all candidates as fallback."
        )
        markers = sup_candidates

    if sup_candidates - markers:
        logger.info(
            f"Filtered out {len(sup_candidates - markers)} false positive markers: "
            f"{sorted(sup_candidates - markers)} (no matching footnote definition)"
        )

    logger.debug(f"Found expected footnote markers: {sorted(markers)}")
    return markers


def _validate_footnotes(
    llm_footnotes: List[Dict],
    expected_markers: set,
    html_content: str
) -> Dict[str, Any]:
    """Validate LLM-extracted footnotes against expected markers."""
    extracted_markers = {(fn.get('marker') or '').lower() for fn in llm_footnotes}

    missing = expected_markers - extracted_markers
    extra = extracted_markers - expected_markers
    coverage = len(extracted_markers & expected_markers) / len(expected_markers) if expected_markers else 1.0

    result = {
        'valid': len(missing) == 0,
        'missing_markers': missing,
        'extra_markers': extra,
        'coverage': coverage,
        'expected_count': len(expected_markers),
        'extracted_count': len(extracted_markers)
    }

    if missing:
        logger.warning(
            f"Footnote validation FAILED: Missing markers {sorted(missing)}. "
            f"Coverage: {coverage:.1%} ({len(extracted_markers)}/{len(expected_markers)})"
        )
    else:
        logger.info(f"Footnote validation PASSED: All {len(expected_markers)} markers found")

    return result


# ============================================================================
# FOOTNOTE CATEGORY CLASSIFICATION
# ============================================================================

FOOTNOTE_CATEGORIES = {
    'CONDITIONAL': {
        'description': 'Creates branch logic in EDC (show/hide, skip patterns)',
        'subcategories': {
            'population_subset': 'Only for specific population (e.g., females, subjects with CNS metastases)',
            'clinical_indication': 'Triggered by clinical finding (e.g., if clinically indicated, if abnormal)',
            'prior_event': 'Depends on prior study event (e.g., if Final Visit < 30 days from last dose)',
            'triggered': 'Activated by specific condition (e.g., discontinuation, adverse event)',
        },
        'detection_patterns': [
            r'\bonly\s+for\b',
            r'\bif\s+(clinically|medically)\s+indicated\b',
            r'\bif\s+(female|male|subject|patient)',
            r'\bwhen\s+(an?\s+)?investigator',
            r'\bupon\s+(discontinuation|progression)',
            r'\bsubjects?\s+with\s+',
            r'\bfor\s+(subjects?|patients?)\s+who\b',
            r'\bunless\b',
            r'\bshould\s+be\s+performed\s+if\b',
        ],
    },
    'SCHEDULING': {
        'description': 'Affects visit timing, windows, frequency',
        'subcategories': {
            'visit_window': 'Defines acceptable time range for visits (e.g., within 28 days)',
            'recurrence': 'Defines repeating schedule (e.g., every 9 weeks, q3 weeks)',
            'timing_constraint': 'Defines intra-visit timing (e.g., pre-dose, before infusion)',
            'relative_timing': 'Timing relative to another event (e.g., within 72 hours)',
        },
        'detection_patterns': [
            r'within\s+\d+\s+(days?|hours?|weeks?)',
            r'\u00b1\s*\d+\s+(days?|hours?|weeks?)',
            r'up\s+to\s+\d+\s+(days?|calendar)',
            r'every\s+\d+\s+(weeks?|months?|days?)',
            r'\bq\d+[wmdc]\b',
            r'pre-?dose',
            r'post-?dose',
            r'before\s+(infusion|administration|dosing)',
            r'after\s+(infusion|administration|dosing)',
            r'prior\s+to\s+(dosing|randomization|treatment)',
            r'morning\s+(of|administration|dose)',
        ],
    },
    'OPERATIONAL': {
        'description': 'Site procedures with no EDC logic impact',
        'subcategories': {
            'specimen_handling': 'Collection/processing/storage instructions',
            'consent_procedure': 'Informed consent requirements',
            'documentation': 'What to document/collect',
            'site_instruction': 'General site operational guidance',
        },
        'detection_patterns': [
            r'\d+\s*(ml|mL)\s+(of\s+)?(blood|plasma|serum|urine)',
            r'centrifuge',
            r'store\s+(at|in)',
            r'informed\s+consent',
            r'site\s+(is\s+advised|should|will)',
            r'contact\s+(the\s+)?subject',
            r'will\s+be\s+(collected|recorded|documented)',
            r'dispensed?\b',
        ],
    },
}

RULETYPE_TO_CATEGORY = {
    'conditional': 'CONDITIONAL',
    'visit_window': 'SCHEDULING',
    'frequency': 'SCHEDULING',
    'timing_modifier': 'SCHEDULING',
    'specimen': 'OPERATIONAL',
    'reference': 'OPERATIONAL',
}


def _classify_footnote_category(rule_type: str, text: str) -> Dict[str, Any]:
    """Deterministically classify footnote category. Fallback when LLM doesn't provide categories."""
    text_lower = text.lower()
    categories_detected = []
    subcategory = None
    reasoning_parts = []

    for cat_name, cat_def in FOOTNOTE_CATEGORIES.items():
        for pattern in cat_def['detection_patterns']:
            if re.search(pattern, text_lower, re.IGNORECASE):
                if cat_name not in categories_detected:
                    categories_detected.append(cat_name)
                    reasoning_parts.append(f"Pattern '{pattern}' matches {cat_name}")
                break

    if not categories_detected:
        default_cat = RULETYPE_TO_CATEGORY.get(rule_type, 'OPERATIONAL')
        categories_detected.append(default_cat)
        reasoning_parts.append(f"Defaulted to {default_cat} based on ruleType '{rule_type}'")

    primary_category = categories_detected[0]

    if primary_category == 'CONDITIONAL':
        if re.search(r'only\s+for|for\s+(subjects?|patients?)\s+with', text_lower):
            subcategory = 'population_subset'
        elif re.search(r'if\s+(clinically|medically)\s+indicated', text_lower):
            subcategory = 'clinical_indication'
        elif re.search(r'discontinu|progression', text_lower):
            subcategory = 'triggered'
        elif re.search(r'if\s+.*\s+(visit|dose|treatment)', text_lower):
            subcategory = 'prior_event'
        else:
            subcategory = 'triggered'
    elif primary_category == 'SCHEDULING':
        if re.search(r'within\s+\d+\s+(days?|hours?)', text_lower):
            subcategory = 'visit_window'
        elif re.search(r'every\s+\d+|q\d+[wm]', text_lower):
            subcategory = 'recurrence'
        elif re.search(r'pre-?dose|post-?dose|before\s+(infusion|administration)', text_lower):
            subcategory = 'timing_constraint'
        else:
            subcategory = 'relative_timing'
    elif primary_category == 'OPERATIONAL':
        if re.search(r'\d+\s*(ml|mL)|blood|plasma|serum|centrifuge', text_lower):
            subcategory = 'specimen_handling'
        elif re.search(r'informed\s+consent', text_lower):
            subcategory = 'consent_procedure'
        elif re.search(r'will\s+be\s+(collected|recorded|documented)', text_lower):
            subcategory = 'documentation'
        else:
            subcategory = 'site_instruction'

    category = categories_detected[0] if len(categories_detected) == 1 else categories_detected

    # Build reasoning
    reasoning = f"Deterministic classification: {'; '.join(reasoning_parts)}"

    return {
        'category': category,
        'subcategory': subcategory,
        'classificationReasoning': f"Deterministic classification: {'; '.join(reasoning_parts)}",
        'edcImpact': {
            'affectsScheduling': 'SCHEDULING' in categories_detected,
            'affectsBranching': 'CONDITIONAL' in categories_detected,
            'isInformational': categories_detected == ['OPERATIONAL'],
        }
    }


def _validate_footnote_categories(footnotes: List[Dict]) -> Dict[str, Any]:
    """Validate and backfill category classification for footnotes."""
    backfilled_count = 0
    category_counts = {'CONDITIONAL': 0, 'SCHEDULING': 0, 'OPERATIONAL': 0}
    multi_label_count = 0

    for fn in footnotes:
        if not fn.get('category'):
            rule_type = fn.get('ruleType', 'reference')
            text = fn.get('text', '')
            fallback = _classify_footnote_category(rule_type, text)

            fn['category'] = fallback['category']
            fn['subcategory'] = fallback.get('subcategory')
            fn['classificationReasoning'] = fallback.get('classificationReasoning', '')
            fn['edcImpact'] = fallback.get('edcImpact', {})

            backfilled_count += 1

        categories = fn['category'] if isinstance(fn['category'], list) else [fn['category']]
        for cat in categories:
            if cat in category_counts:
                category_counts[cat] += 1

        if isinstance(fn['category'], list) and len(fn['category']) > 1:
            multi_label_count += 1

        if not fn.get('edcImpact'):
            fn['edcImpact'] = {
                'affectsScheduling': 'SCHEDULING' in categories,
                'affectsBranching': 'CONDITIONAL' in categories,
                'isInformational': categories == ['OPERATIONAL'],
            }

    total = len(footnotes)
    result = {
        'valid': backfilled_count == 0,
        'total_footnotes': total,
        'backfilled_count': backfilled_count,
        'llm_classified_count': total - backfilled_count,
        'category_distribution': category_counts,
        'multi_label_count': multi_label_count,
    }

    if backfilled_count > 0:
        logger.warning(f"Footnote category validation: {backfilled_count}/{total} required deterministic fallback")
    else:
        logger.info(f"Footnote category validation: All {total} footnotes have LLM-provided categories")

    logger.info(
        f"Category distribution: CONDITIONAL={category_counts['CONDITIONAL']}, "
        f"SCHEDULING={category_counts['SCHEDULING']}, OPERATIONAL={category_counts['OPERATIONAL']}, "
        f"multi-label={multi_label_count}"
    )

    return result


# ============================================================================
# STANDALONE LLM HELPER
# ============================================================================

def call_llm(
    prompt: str,
    max_tokens: int = 8192,
    gemini_file_uri: Optional[str] = None,
) -> Optional[str]:
    """Call LLM using Gemini (helper for Stage 2/3 activity expansion)."""
    try:
        import google.generativeai as genai

        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY not found in environment")
            return None

        genai.configure(api_key=api_key)

        model = genai.GenerativeModel(
            model_name=os.getenv("GEMINI_MODEL", "gemini-3-pro-preview"),
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": max_tokens,
            }
        )

        if gemini_file_uri:
            try:
                file_name = gemini_file_uri.split("/")[-1]
                gemini_file = genai.get_file(file_name)
                content = [gemini_file, prompt]
            except Exception as e:
                logger.warning(f"Failed to get Gemini file '{gemini_file_uri}': {e}. Falling back to text-only.")
                content = prompt
        else:
            content = prompt

        response = model.generate_content(content)

        if response and response.text:
            return _clean_json(response.text)

        logger.warning("Empty response from Gemini")
        return None

    except ImportError:
        logger.error("google-generativeai package not installed")
        return None
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return None


# ============================================================================
# MAIN INTERPRETER CLASS
# ============================================================================

class SOAHTMLInterpreter:
    """
    Interpret SOA HTML tables using Claude with two-phase extraction.

    v3.1: LLM-driven timepoint detection - no hardcoded pattern list.
    The LLM uses clinical judgment to identify timepoint sub-columns.
    Each column = separate encounter with timingModifier and parentVisit fields.

    Two-Phase Architecture:
    - Phase 1: Extract structure (visits with timepoints, activities, footnotes)
    - Phase 2: Extract compact matrix (activity->visits) - simplified format
    - Phase 3: Expand to full SAIs (Python, deterministic) - timing from visits
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        """Initialize the interpreter."""
        load_dotenv()

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not found - will use Gemini only")
            self.client = None
        else:
            self.client = Anthropic(api_key=api_key)

        self.model = model

        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
            gemini_model_name = os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")
            self.gemini_model = genai.GenerativeModel(gemini_model_name)
            self.gemini_available = True
            logger.info(f"Gemini fallback initialized (model: {gemini_model_name})")
        else:
            self.gemini_model = None
            self.gemini_available = False
            logger.warning("GEMINI_API_KEY not found - no fallback available")

        self.structure_prompt = _load_prompt("html_interpretation.txt")
        self.matrix_prompt = _load_prompt("matrix_extraction.txt")

        logger.info(f"SOAHTMLInterpreter initialized (model: {model}, v3.1 LLM-driven timepoints)")

    async def interpret(
        self,
        html_tables: List[Dict[str, Any]],
        protocol_id: str,
        merge_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Interpret HTML tables into USDM structure using two-phase extraction.
        """
        if merge_result and merge_result.get("mergeGroups"):
            return await self._interpret_with_timelines(
                html_tables, protocol_id, merge_result
            )

        logger.info(f"Interpreting {len(html_tables)} HTML tables for {protocol_id} (two-phase, LLM-driven timepoints)")

        # Phase 1: Extract structure
        logger.info("Phase 1: Extracting structure (visits, activities, footnotes)...")
        structure = await self._extract_structure(html_tables, protocol_id)

        visits = structure.get("visits", [])
        activities = structure.get("activities", [])
        tp_count = sum(1 for v in visits if v.get("timingModifier"))

        logger.info(f"Phase 1 complete: {len(visits)} visits ({tp_count} timepoint encounters), {len(activities)} activities")

        # Repair activity/visit markers from HTML
        self._repair_activity_footnote_markers(structure, html_tables)

        # Phase 2: Extract compact matrix
        logger.info("Phase 2: Extracting activity-visit matrix...")
        matrix = await self._extract_matrix(html_tables, protocol_id, visits, activities)

        # Repair matrix cell markers from HTML
        matrix = self._repair_matrix_footnote_markers(matrix, structure, html_tables)

        matrix_entries = sum(len(v) if isinstance(v, list) else 1 for v in matrix.values())
        logger.info(f"Phase 2 complete: {len(matrix)} activities with {matrix_entries} visit mappings")

        # Phase 3: Expand matrix to full SAIs
        logger.info("Phase 3: Expanding matrix to full SAI objects...")
        sais = self._expand_matrix_to_sais(matrix, structure, html_tables)

        logger.info(f"Phase 3 complete: {len(sais)} ScheduledActivityInstances generated")

        structure["scheduledActivityInstances"] = sais

        # Post-process and validate
        structure = self._post_process(structure, html_tables)

        logger.info(
            f"Interpretation complete: "
            f"{len(structure.get('visits', []))} visits, "
            f"{len(structure.get('activities', []))} activities, "
            f"{len(structure.get('scheduledActivityInstances', []))} instances, "
            f"visit groups: {len(structure.get('visitGroups', {}))}"
        )

        return structure

    # ========================================================================
    # TIMELINE-AWARE INTERPRETATION
    # ========================================================================

    async def _interpret_with_timelines(
        self,
        html_tables: List[Dict[str, Any]],
        protocol_id: str,
        merge_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Interpret HTML tables with scheduleTimelines structure."""
        merge_groups = merge_result.get("mergeGroups", [])
        logger.info(f"Interpreting with {len(merge_groups)} scheduleTimelines for {protocol_id}")

        table_lookup = {t.get("id"): t for t in html_tables}

        schedule_timelines = []
        all_activities = []
        encounter_cross_reference = {}

        for group in merge_groups:
            group_id = group.get("id", f"TIMELINE-{len(schedule_timelines)+1:03d}")
            table_ids = group.get("tableIds", [])
            decision = group.get("decision", "merge")
            timeline_name = group.get("timelineName", f"Schedule {len(schedule_timelines)+1}")
            timeline_description = group.get("timelineDescription", "")
            metadata = group.get("metadata", {})
            shared_encounters = group.get("sharedEncounters", [])

            logger.info(f"  Processing {group_id}: tables {table_ids}, decision={decision}")

            group_tables = [table_lookup[tid] for tid in table_ids if tid in table_lookup]

            if not group_tables:
                logger.warning(f"  No tables found for group {group_id}")
                continue

            group_structure = await self._interpret_group(group_tables, protocol_id, group_id)

            timeline_visits = group_structure.get("visits", [])
            timeline_activities = group_structure.get("activities", [])
            timeline_sais = group_structure.get("scheduledActivityInstances", [])
            timeline_footnotes = group_structure.get("footnotes", [])

            matrix_grid = self._build_matrix_grid(
                timeline_visits, timeline_activities, timeline_sais
            )

            timeline = {
                "id": group_id,
                "name": timeline_name,
                "description": timeline_description,
                "sourceTables": table_ids,
                "mergeDecision": {
                    "decision": decision,
                    "level": group.get("decisionLevel", 0),
                    "reason": group.get("decisionReason", ""),
                },
                "metadata": metadata,
                "visits": timeline_visits,
                "activities": timeline_activities,
                "matrix": {
                    "description": f"Schedule of Assessments for {timeline_name}",
                    "legend": {"X": "Required", "O": "Optional", "C": "Conditional"},
                    "grid": matrix_grid,
                },
                "footnotes": timeline_footnotes,
                "encounters": timeline_visits,
                "scheduledActivityInstances": timeline_sais,
                "visitGroups": group_structure.get("visitGroups", {}),
                "qualityMetrics": group_structure.get("qualityMetrics", {}),
            }

            # Mark shared encounters
            for encounter in timeline.get("encounters", []):
                enc_name = encounter.get("name", "")
                parent_name = encounter.get("parentVisit") or enc_name
                is_shared = enc_name in shared_encounters or parent_name in shared_encounters

                if is_shared:
                    encounter["shared"] = True
                    encounter["sharedWith"] = []
                    if enc_name not in encounter_cross_reference:
                        encounter_cross_reference[enc_name] = {
                            "canonicalId": encounter.get("id"),
                            "appearsIn": [],
                        }
                    encounter_cross_reference[enc_name]["appearsIn"].append(group_id)
                else:
                    encounter["shared"] = False

            schedule_timelines.append(timeline)

            for activity in group_structure.get("activities", []):
                existing = next(
                    (a for a in all_activities if a.get("name") == activity.get("name")),
                    None
                )
                if not existing:
                    activity["sourceTimelines"] = [group_id]
                    all_activities.append(activity)
                else:
                    if group_id not in existing.get("sourceTimelines", []):
                        existing.setdefault("sourceTimelines", []).append(group_id)

        # Populate sharedWith
        for timeline in schedule_timelines:
            for encounter in timeline.get("encounters", []):
                enc_name = encounter.get("name", "")
                if enc_name in encounter_cross_reference:
                    other_timelines = [
                        t for t in encounter_cross_reference[enc_name]["appearsIn"]
                        if t != timeline["id"]
                    ]
                    encounter["sharedWith"] = other_timelines

        result = {
            "protocolId": protocol_id,
            "protocolType": "hybrid",
            "primaryReferencePoint": "randomization",
            "scheduleTimelines": schedule_timelines,
            "activities": all_activities,
            "encounterCrossReference": encounter_cross_reference,
            "visits": self._flatten_encounters(schedule_timelines),
            "encounters": self._flatten_encounters(schedule_timelines),
            "scheduledActivityInstances": self._flatten_sais(schedule_timelines),
            "footnotes": self._flatten_footnotes(schedule_timelines),
            "visitGroups": self._flatten_visit_groups(schedule_timelines),
            "qualityMetrics": self._aggregate_quality_metrics(schedule_timelines),
        }

        logger.info(
            f"Timeline interpretation complete: "
            f"{len(schedule_timelines)} timelines, "
            f"{len(all_activities)} activities, "
            f"{len(result['visits'])} total encounters"
        )

        return result

    # ========================================================================
    # DETERMINISTIC FOOTNOTE MARKER REPAIR
    # ========================================================================

    def _parse_html_grids(self, html_tables: List[Dict[str, Any]]) -> list:
        """Parse HTML tables into TableGrid objects with deterministic markers."""
        parser = HTMLGridParser()
        grids = []
        for table in html_tables:
            html = table.get("html", "")
            table_id = table.get("id", f"table_{len(grids)}")
            page_start = table.get("pageStart", table.get("pages", [1])[0] if table.get("pages") else 1)
            grid = parser.parse(html, table_id, page_start)
            grids.append(grid)
        return grids

    def _repair_activity_footnote_markers(
        self,
        structure: Dict[str, Any],
        html_tables: List[Dict[str, Any]],
    ) -> None:
        """Repair activity and visit footnote markers from HTML deterministically.

        Parses HTML tables and extracts <sup> markers from activity-label cells
        and header cells, then populates the corresponding activity/visit
        footnoteMarkers fields.

        Only injects markers that have a matching footnote definition to avoid
        false positives from scientific notation (CO2, mg/m2, etc.).
        """
        grids = self._parse_html_grids(html_tables)

        # Build set of known footnote markers (from LLM-extracted definitions)
        known_footnote_markers = {
            (fn.get('marker') or '').lower()
            for fn in structure.get("footnotes", [])
        }

        activities = structure.get("activities", [])
        visits = structure.get("visits", [])

        # Build name-based lookups (normalized: lowercase + stripped)
        activity_by_name = {}
        for act in activities:
            name = (act.get("name") or "").strip().lower()
            if name:
                activity_by_name[name] = act

        visit_by_name = {}
        for vis in visits:
            for key in ["name", "originalName"]:
                name = (vis.get(key) or "").strip().lower()
                if name:
                    visit_by_name[name] = vis

        activity_repair_count = 0
        visit_repair_count = 0

        for grid in grids:
            for cell in grid.cells:
                if not cell.footnote_markers:
                    continue

                if cell.is_activity_label:
                    # Try provenance rowIdx match first
                    matched_activity = None
                    for act in activities:
                        prov = act.get("provenance", {})
                        if prov.get("rowIdx") == cell.position.row_idx:
                            matched_activity = act
                            break

                    # Fallback: name-based match
                    if not matched_activity:
                        cell_name = cell.normalized_text.strip().lower()
                        # Remove marker characters from end for matching
                        for marker in cell.footnote_markers:
                            cell_name = cell_name.rstrip(marker)
                        cell_name = cell_name.strip()
                        matched_activity = activity_by_name.get(cell_name)

                    if matched_activity:
                        existing = set(matched_activity.get("footnoteMarkers", []))
                        # Only add markers that have a known footnote definition
                        new_markers = [
                            m for m in cell.footnote_markers
                            if m not in existing and m in known_footnote_markers
                        ]
                        if new_markers:
                            matched_activity.setdefault("footnoteMarkers", []).extend(new_markers)
                            activity_repair_count += 1

                elif cell.is_header and cell.position.col_idx > 0:
                    # Visit header cell - try provenance colIdx match
                    matched_visit = None
                    for vis in visits:
                        prov = vis.get("provenance", {})
                        if prov.get("colIdx") == cell.position.col_idx:
                            matched_visit = vis
                            break

                    # Fallback: name-based match
                    if not matched_visit:
                        cell_name = cell.normalized_text.strip().lower()
                        for marker in cell.footnote_markers:
                            cell_name = cell_name.rstrip(marker)
                        cell_name = cell_name.strip()
                        matched_visit = visit_by_name.get(cell_name)

                    if matched_visit:
                        existing = set(matched_visit.get("footnoteMarkers", []))
                        # Only add markers that have a known footnote definition
                        new_markers = [
                            m for m in cell.footnote_markers
                            if m not in existing and m in known_footnote_markers
                        ]
                        if new_markers:
                            matched_visit.setdefault("footnoteMarkers", []).extend(new_markers)
                            visit_repair_count += 1

        if activity_repair_count > 0:
            logger.info(f"Activity marker repair: populated markers for {activity_repair_count} activities")
        if visit_repair_count > 0:
            logger.info(f"Visit marker repair: populated markers for {visit_repair_count} visits")

    def _repair_matrix_footnote_markers(
        self,
        matrix: Dict[str, Any],
        structure: Dict[str, Any],
        html_tables: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Repair matrix cell footnote markers from HTML deterministically.

        Cross-validates LLM-extracted matrix markers against deterministically
        parsed HTML cell markers and fills in any the LLM missed.

        Only injects markers that have a matching footnote definition to avoid
        false positives from scientific notation (CO2, mg/m2, etc.).
        """
        grids = self._parse_html_grids(html_tables)

        # Build set of known footnote markers (from LLM-extracted definitions)
        known_footnote_markers = {
            (fn.get('marker') or '').lower()
            for fn in structure.get("footnotes", [])
        }

        # Build (row_idx, col_idx) → [markers] lookup from all grids
        # Only include markers that have a known footnote definition
        html_markers_lookup: Dict[tuple, List[str]] = {}
        for grid in grids:
            for cell in grid.cells:
                if cell.footnote_markers and not cell.is_header and not cell.is_activity_label:
                    valid_markers = [m for m in cell.footnote_markers if m in known_footnote_markers]
                    if valid_markers:
                        key = (cell.position.row_idx, cell.position.col_idx)
                        html_markers_lookup[key] = valid_markers

        if not html_markers_lookup:
            return matrix

        # Build activity_id → rowIdx and visit_id → colIdx from provenance
        activity_row = {}
        for act in structure.get("activities", []):
            prov = act.get("provenance", {})
            row_idx = prov.get("rowIdx")
            if row_idx is not None:
                activity_row[act["id"]] = row_idx

        visit_col = {}
        for vis in structure.get("visits", []):
            prov = vis.get("provenance", {})
            col_idx = prov.get("colIdx")
            if col_idx is not None:
                visit_col[vis["id"]] = col_idx

        # Fallback: build name-based lookups from grids
        name_to_row = {}
        name_to_col = {}
        for grid in grids:
            for row_idx, name in grid.row_to_activity.items():
                name_to_row[name.strip().lower()] = row_idx
            for col_idx, name in grid.col_to_visit.items():
                name_to_col[name.strip().lower()] = col_idx

        activity_lookup = {a["id"]: a for a in structure.get("activities", [])}
        visit_lookup = {v["id"]: v for v in structure.get("visits", [])}

        repair_count = 0

        for activity_id, visit_entries in matrix.items():
            if not isinstance(visit_entries, list):
                visit_entries = [visit_entries]

            row_idx = activity_row.get(activity_id)
            # Fallback: name-based row match
            if row_idx is None:
                act = activity_lookup.get(activity_id)
                if act:
                    act_name = (act.get("name") or "").strip().lower()
                    row_idx = name_to_row.get(act_name)

            if row_idx is None:
                continue

            for entry in visit_entries:
                if isinstance(entry, str):
                    visit_id = entry
                elif isinstance(entry, dict):
                    visit_id = entry.get("v")
                else:
                    continue

                col_idx = visit_col.get(visit_id)
                # Fallback: name-based col match
                if col_idx is None:
                    vis = visit_lookup.get(visit_id)
                    if vis:
                        for key in ["name", "originalName"]:
                            vis_name = (vis.get(key) or "").strip().lower()
                            if vis_name in name_to_col:
                                col_idx = name_to_col[vis_name]
                                break

                if col_idx is None:
                    continue

                expected_markers = html_markers_lookup.get((row_idx, col_idx), [])
                if not expected_markers:
                    continue

                # Get current markers from matrix entry
                if isinstance(entry, str):
                    # Convert string entry to dict to add markers
                    idx = visit_entries.index(entry)
                    entry = {"v": entry, "m": expected_markers}
                    visit_entries[idx] = entry
                    repair_count += 1
                elif isinstance(entry, dict):
                    current = set(entry.get("m", []))
                    missing = [m for m in expected_markers if m not in current]
                    if missing:
                        entry.setdefault("m", []).extend(missing)
                        repair_count += 1

            # Write back in case we converted entries
            matrix[activity_id] = visit_entries

        if repair_count > 0:
            logger.info(f"Matrix marker repair: fixed {repair_count} cells with missing footnote markers")

        return matrix

    async def _interpret_group(
        self,
        group_tables: List[Dict[str, Any]],
        protocol_id: str,
        group_id: str,
    ) -> Dict[str, Any]:
        """Interpret a single group of tables."""
        logger.info(f"    Interpreting group {group_id} ({len(group_tables)} tables)")

        structure = await self._extract_structure(group_tables, protocol_id)

        visits = structure.get("visits", [])
        activities = structure.get("activities", [])
        logger.info(f"    Group {group_id} Phase 1: {len(visits)} visits, {len(activities)} activities")

        # Repair activity/visit markers from HTML before matrix extraction
        self._repair_activity_footnote_markers(structure, group_tables)

        matrix = await self._extract_matrix(group_tables, protocol_id, visits, activities)
        # Repair matrix cell markers from HTML
        matrix = self._repair_matrix_footnote_markers(matrix, structure, group_tables)
        sais = self._expand_matrix_to_sais(matrix, structure, group_tables)
        logger.info(f"    Group {group_id} Phase 3: {len(sais)} SAIs")

        structure["scheduledActivityInstances"] = sais
        structure = self._post_process(structure, group_tables)

        for visit in structure.get("visits", []):
            visit["timelineId"] = group_id
        for sai in structure.get("scheduledActivityInstances", []):
            sai["timelineId"] = group_id

        return structure

    # ========================================================================
    # FLATTEN HELPERS FOR TIMELINE MODE
    # ========================================================================

    def _flatten_encounters(self, timelines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        encounters = []
        seen_ids = set()
        for timeline in timelines:
            for enc in timeline.get("encounters", []):
                enc_id = enc.get("id")
                if enc_id in seen_ids:
                    enc_id = f"{enc_id}_{timeline['id']}"
                    enc = enc.copy()
                    enc["id"] = enc_id
                seen_ids.add(enc_id)
                encounters.append(enc)
        return encounters

    def _flatten_sais(self, timelines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sais = []
        sai_counter = 1
        for timeline in timelines:
            for sai in timeline.get("scheduledActivityInstances", []):
                sai_copy = sai.copy()
                sai_copy["id"] = f"SAI-{sai_counter:03d}"
                sai_copy["timelineId"] = timeline["id"]
                sais.append(sai_copy)
                sai_counter += 1
        return sais

    def _flatten_footnotes(self, timelines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        footnotes = []
        seen_markers = set()
        for timeline in timelines:
            for fn in timeline.get("footnotes", []):
                marker = fn.get("marker", "")
                if marker not in seen_markers:
                    fn_copy = fn.copy()
                    fn_copy["sourceTimeline"] = timeline["id"]
                    footnotes.append(fn_copy)
                    seen_markers.add(marker)
        return footnotes

    def _flatten_visit_groups(self, timelines: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        combined = {}
        for timeline in timelines:
            for parent_name, enc_ids in timeline.get("visitGroups", {}).items():
                combined.setdefault(parent_name, []).extend(enc_ids)
        return combined
    
    def _build_table_scope(self, html_tables: List[Dict[str, Any]]) -> str:
        if not html_tables or len(html_tables) != 1:
            return ""
        table = html_tables[0]
        table_id = table.get("id", "")
        category = table.get("category", "MAIN_SOA")
        
        if category and category != "MAIN_SOA":
            html = table.get("html", "")
            titles = re.findall(
                r'(Table\s+\d+\.?\s*[^\n<]+?)(?:\s*<table)',
                html,
                re.IGNORECASE
            )
            
            scope = (
                f"\n## TABLE SCOPE (CRITICAL)\n"
                f"This HTML contains multiple tables. "
                f"You MUST extract ONLY from the table matching category: **{category}**\n\n"
            )
            if titles:
                scope += "Tables found in this HTML:\n"
                for t in titles:
                    scope += f"  - {t.strip()}\n"
                scope += (
                    f"\nSelect the ONE table that matches **{category}** and extract ONLY from it. "
                    f"Ignore all other tables completely.\n"
                )
            else:
                scope += (
                    f"Ignore all tables that do not match {category}.\n"
                )
            return scope
        return ""

    def _aggregate_quality_metrics(self, timelines: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_visits = 0
        total_sais = 0
        total_footnotes = 0
        total_tp = 0
        total_groups = 0

        for timeline in timelines:
            metrics = timeline.get("qualityMetrics", {})
            total_visits += metrics.get("totalVisits", len(timeline.get("encounters", [])))
            total_sais += metrics.get("totalScheduledInstances", len(timeline.get("scheduledActivityInstances", [])))
            total_footnotes += metrics.get("footnotesLinked", len(timeline.get("footnotes", [])))
            total_tp += metrics.get("timepointEncounters", 0)
            total_groups += metrics.get("visitGroupCount", 0)

        return {
            "totalTimelines": len(timelines),
            "totalVisits": total_visits,
            "totalScheduledInstances": total_sais,
            "footnotesLinked": total_footnotes,
            "timepointEncounters": total_tp,
            "visitGroupCount": total_groups,
        }

    # ========================================================================
    # MATRIX GRID BUILDER
    # ========================================================================

    def _build_matrix_grid(
        self,
        visits: List[Dict[str, Any]],
        activities: List[Dict[str, Any]],
        sais: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Build matrix grid for frontend display."""
        sai_lookup = {}
        for sai in sais:
            key = (sai.get("activityId"), sai.get("visitId"))
            sai_lookup[key] = sai

        grid = []
        for activity in activities:
            activity_id = activity.get("id")
            activity_name = activity.get("name", "")

            cells = []
            for visit in visits:
                visit_id = visit.get("id")
                sai = sai_lookup.get((activity_id, visit_id))

                if sai:
                    # Determine cell value based on SAI properties
                    is_required = sai.get("isRequired", True)
                    has_condition = sai.get("condition") is not None
                    footnote_markers = sai.get("footnoteMarkers", [])

                    if has_condition:
                        value = "C"
                    elif sai.get("isRequired", True):
                        value = "X"
                    else:
                        value = "O"

                    cell = {
                        "visitId": visit_id,
                        "value": value,
                        "isScheduled": True,
                        "footnoteMarkers": sai.get("footnoteMarkers", []),
                        "timingModifier": visit.get("timingModifier"),
                        "parentVisit": visit.get("parentVisit"),
                    }
                else:
                    cell = {
                        "visitId": visit_id,
                        "value": "",
                        "isScheduled": False,
                        "footnoteMarkers": [],
                        "timingModifier": visit.get("timingModifier"),
                        "parentVisit": visit.get("parentVisit"),
                    }

                cells.append(cell)

            grid.append({
                "activityId": activity_id,
                "activityName": activity.get("name", ""),
                "category": activity.get("category", "OTHER"),
                "cells": cells,
            })

        return grid

    # ========================================================================
    # LLM CALL WITH FALLBACK
    # ========================================================================

    def _call_llm_with_fallback(
        self,
        prompt: str,
        max_tokens: int = None,
        phase_name: str = "LLM call",
    ) -> str:
        """Call LLM with Anthropic-first, Gemini fallback strategy."""
        if max_tokens is None:
            max_tokens = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "16000"))

        anthropic_error = None

        if self.client:
            try:
                collected_text = []
                with self.client.messages.stream(
                    model=self.model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}]
                ) as stream:
                    for text in stream.text_stream:
                        collected_text.append(text)
                result = "".join(collected_text)

                if len(result) < 10:
                    logger.warning(f"{phase_name}: Anthropic response suspiciously short ({len(result)} chars)")

                return result
            except Exception as e:
                anthropic_error = str(e)
                logger.warning(f"{phase_name}: Anthropic failed: {e}")

        if self.gemini_available and self.gemini_model:
            try:
                gemini_model_name = os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")
                logger.info(f"{phase_name}: Using Gemini fallback ({gemini_model_name})")
                response = self.gemini_model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=max_tokens,
                        temperature=0.1,
                        response_mime_type="application/json",
                    )
                )
                logger.info(f"{phase_name}: Gemini fallback succeeded")
                return response.text
            except Exception as e:
                logger.error(f"{phase_name}: Gemini fallback also failed: {e}")
                raise RuntimeError(
                    f"{phase_name} failed: Anthropic error: {anthropic_error}, Gemini error: {e}"
                )

        raise RuntimeError(
            f"{phase_name} failed: Anthropic error: {anthropic_error}, no Gemini fallback available"
        )

    # ========================================================================
    # PHASE 1: STRUCTURE EXTRACTION
    # ========================================================================

    async def _extract_structure(
        self,
        html_tables: List[Dict[str, Any]],
        protocol_id: str,
    ) -> Dict[str, Any]:
        html_content = self._build_html_context(html_tables)

        all_pages = []
        for table in html_tables:
            all_pages.extend(table.get("pages", []))
        page_start = min(all_pages) if all_pages else 1

        expected_markers = _find_expected_footnote_markers(html_content)

        # Build table scope instruction for multi-table disambiguation
        table_scope = self._build_table_scope(html_tables)
        logger.info(f"TABLE SCOPE for {html_tables[0].get('id', '?')}: '{table_scope[:100]}...' " if table_scope else f"TABLE SCOPE: empty (category={html_tables[0].get('category', '?')})")


        prompt = self.structure_prompt.format(
            protocol_id=protocol_id,
            html_content=html_content,
            page_start=page_start,
            table_scope=table_scope,
        )

        structure = None
        validation_result = None

        # First LLM attempt
        try:
            raw_text = self._call_llm_with_fallback(
                prompt=prompt,
                phase_name="Phase 1 (structure extraction)"
            )
            structure = json.loads(_clean_json(raw_text))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Phase 1 failed to parse JSON: {e}")
        except Exception as e:
            raise RuntimeError(f"Phase 1 failed: {e}")

        # Validate footnotes
        llm_footnotes = structure.get("footnotes", [])
        validation_result = _validate_footnotes(llm_footnotes, expected_markers, html_content)

        # Retry if validation failed — SURGICAL MERGE: only add missing footnotes,
        # never replace the entire structure (visits/activities are already good)
        if not validation_result['valid'] and validation_result['missing_markers']:
            missing = sorted(validation_result['missing_markers'])
            logger.warning(f"Footnote validation failed. Retrying for missing markers: {missing}")

            retry_prompt = f"""{prompt}

**CRITICAL CORRECTION REQUIRED**:
Your previous extraction missed the following footnotes: {', '.join(missing)}

These footnotes EXIST in the HTML content. Look carefully for lines starting with:
{chr(10).join(f'  - "{m}." or "{m})"' for m in missing)}

You MUST include ALL of these missing footnotes in your response.
Expected total footnotes: {len(expected_markers)} (markers: {', '.join(sorted(expected_markers))})
"""

            try:
                retry_text = self._call_llm_with_fallback(
                    prompt=retry_prompt,
                    phase_name="Phase 1 retry (footnote correction)"
                )
                retry_structure = json.loads(_clean_json(retry_text))
                retry_footnotes = retry_structure.get("footnotes", [])
                retry_validation = _validate_footnotes(retry_footnotes, expected_markers, html_content)

                if retry_validation['valid'] or retry_validation['coverage'] > validation_result['coverage']:
                    logger.info(f"Retry improved footnote coverage: {validation_result['coverage']:.1%} -> {retry_validation['coverage']:.1%}")

                    # Surgical merge: only add footnotes that were missing from attempt 1
                    # NEVER replace visits/activities — the first attempt's structure is trusted
                    existing_markers = {(fn.get('marker') or '').lower() for fn in structure.get("footnotes", [])}
                    merged_count = 0
                    for fn in retry_footnotes:
                        marker = (fn.get('marker') or '').lower()
                        if marker and marker not in existing_markers:
                            structure["footnotes"].append(fn)
                            existing_markers.add(marker)
                            merged_count += 1

                    # Also update any existing footnotes that the retry improved
                    # (e.g., retry provided better appliesTo or category for a footnote
                    # that attempt 1 had with sparse data)
                    retry_by_marker = {(fn.get('marker') or '').lower(): fn for fn in retry_footnotes}
                    enriched_count = 0
                    for fn in structure.get("footnotes", []):
                        marker = (fn.get('marker') or '').lower()
                        retry_fn = retry_by_marker.get(marker)
                        if retry_fn:
                            # Only enrich fields that are empty/default in attempt 1
                            if not fn.get('appliesTo') and retry_fn.get('appliesTo'):
                                fn['appliesTo'] = retry_fn['appliesTo']
                                enriched_count += 1
                            if not fn.get('category') and retry_fn.get('category'):
                                fn['category'] = retry_fn['category']
                            if not fn.get('subcategory') and retry_fn.get('subcategory'):
                                fn['subcategory'] = retry_fn['subcategory']
                            if not fn.get('classificationReasoning') and retry_fn.get('classificationReasoning'):
                                fn['classificationReasoning'] = retry_fn['classificationReasoning']
                            if not fn.get('edcImpact') and retry_fn.get('edcImpact'):
                                fn['edcImpact'] = retry_fn['edcImpact']

                    logger.info(f"Surgical merge: added {merged_count} missing footnotes, enriched {enriched_count} existing")

                    # Re-validate after merge
                    validation_result = _validate_footnotes(
                        structure.get("footnotes", []), expected_markers, html_content
                    )
            except Exception as e:
                logger.error(f"Phase 1 retry failed: {e}")

        # Deterministic fallback for still-missing footnotes
        if not validation_result['valid'] and validation_result['missing_markers']:
            logger.warning(f"Applying deterministic fallback for: {sorted(validation_result['missing_markers'])}")

            deterministic_footnotes = _extract_footnotes_deterministic(html_content)
            existing_markers = {(fn.get('marker') or '').lower(): fn for fn in structure.get("footnotes", [])}

            added_count = 0
            for det_fn in deterministic_footnotes:
                marker = (det_fn.get('marker') or '').lower()
                if marker in validation_result['missing_markers'] and marker not in existing_markers:
                    structure["footnotes"].append(det_fn)
                    existing_markers[marker] = det_fn
                    added_count += 1

            if added_count > 0:
                logger.info(f"Deterministic fallback added {added_count} missing footnotes")

        # Validate footnote categories
        if structure.get("footnotes"):
            category_validation = _validate_footnote_categories(structure["footnotes"])
            structure["_categoryMetrics"] = {
                "llmClassifiedCount": category_validation['llm_classified_count'],
                "backfilledCount": category_validation['backfilled_count'],
                "distribution": category_validation['category_distribution'],
                "multiLabelCount": category_validation['multi_label_count'],
            }

        return structure

    # ========================================================================
    # PHASE 2: MATRIX EXTRACTION
    # ========================================================================

    async def _extract_matrix(
        self,
        html_tables: List[Dict[str, Any]],
        protocol_id: str,
        visits: List[Dict],
        activities: List[Dict],
    ) -> Dict[str, Any]:
        """Phase 2: Extract compact activity-visit matrix."""
        html_content = self._build_html_context(html_tables)

        visits_compact = [
            {
                "id": v["id"],
                "name": v.get("name", ""),
                "originalName": v.get("originalName", v.get("name", "")),
                "timingModifier": v.get("timingModifier"),
            }
            for v in visits
        ]
        activities_compact = [{"id": a["id"], "name": a["name"]} for a in activities]

        table_scope = self._build_table_scope(html_tables)

        prompt = self.matrix_prompt.format(
            protocol_id=protocol_id,
            html_content=html_content,
            visits_json=json.dumps(visits_compact, indent=2),
            activities_json=json.dumps(activities_compact, indent=2),
            table_scope=table_scope,
        )

        try:
            raw_text = self._call_llm_with_fallback(
                prompt=prompt,
                phase_name="Phase 2 (matrix extraction)"
            )

            if not raw_text or not raw_text.strip():
                raise ValueError("Empty response from LLM")

            cleaned = _clean_json(raw_text)
            if not cleaned or not cleaned.strip():
                raise ValueError("Empty JSON after cleaning")

            return json.loads(cleaned)

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Phase 2: JSON parsing failed ({e}), trying direct Gemini fallback")

            if self.gemini_available and self.gemini_model:
                try:
                    max_tokens = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "16000"))
                    response = self.gemini_model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            max_output_tokens=max_tokens,
                            temperature=0.1,
                            response_mime_type="application/json",
                        )
                    )
                    if response and response.text:
                        gemini_text = _clean_json(response.text)
                        logger.info(f"Phase 2: Gemini fallback response: {len(gemini_text)} chars")
                        return json.loads(gemini_text)
                    else:
                        logger.error("Phase 2: Gemini returned empty response")

                except Exception as gemini_e:
                    logger.error(f"Phase 2: Gemini fallback also failed: {gemini_e}")

            logger.error(f"Phase 2: All attempts failed")
            return {}

        except Exception as e:
            logger.error(f"Phase 2: LLM call failed: {e}")
            return {}

    # ========================================================================
    # PHASE 3: MATRIX -> SAI EXPANSION
    # ========================================================================

    def _expand_matrix_to_sais(
        self,
        matrix: Dict[str, Any],
        structure: Dict[str, Any],
        html_tables: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Phase 3: Expand compact matrix to full SAI objects.

        timingModifier and parentVisit come from the VISIT object.
        Pure Python, no LLM - deterministic and fast.
        """
        sais = []
        sai_counter = 1

        visit_lookup = {v["id"]: v for v in structure.get("visits", [])}
        activity_lookup = {a["id"]: a for a in structure.get("activities", [])}
        default_page = html_tables[0].get("pageStart", 1) if html_tables else 1

        for activity_id, visit_entries in matrix.items():
            activity = activity_lookup.get(activity_id)
            if not activity:
                logger.warning(f"Matrix references unknown activity: {activity_id}")
                continue

            if not isinstance(visit_entries, list):
                visit_entries = [visit_entries]

            for entry in visit_entries:
                cell_page = None
                footnote_markers = []

                if isinstance(entry, str):
                    visit_id = entry
                    timing_modifier = None
                    footnote_markers = []
                elif isinstance(entry, dict):
                    visit_id = entry.get("v")
                    timing_modifier = entry.get("t")
                    footnote_markers = entry.get("m", [])
                    cell_page = entry.get("p")
                else:
                    logger.warning(f"Invalid entry format for {activity_id}: {entry}")
                    continue

                visit = visit_lookup.get(visit_id)
                if not visit:
                    logger.warning(f"Matrix references unknown visit: {visit_id}")
                    continue

                activity_prov = activity.get("provenance", {})
                visit_prov = visit.get("provenance", {})

                page_number = (
                    cell_page
                    or visit_prov.get("pageNumber")
                    or activity_prov.get("pageNumber")
                    or default_page
                )
                table_id = visit_prov.get("tableId") or activity_prov.get("tableId", "SOA-1")

                provenance = {
                    "pageNumber": page_number,
                    "tableId": table_id,
                    "rowIdx": activity_prov.get("rowIdx"),
                    "colIdx": visit_prov.get("colIdx"),
                }

                sai = {
                    "id": f"SAI-{sai_counter:03d}",
                    "activityId": activity_id,
                    "activityName": activity.get("name", ""),
                    "visitId": visit_id,
                    "visitName": visit.get("name", ""),
                    "isRequired": True,
                    "condition": None,
                    "timingModifier": visit.get("timingModifier"),
                    "parentVisit": visit.get("parentVisit"),
                    "footnoteMarkers": footnote_markers if footnote_markers else [],
                    "provenance": {
                        "pageNumber": page_number,
                        "tableId": visit_prov.get("tableId") or activity_prov.get("tableId", "SOA-1"),
                        "rowIdx": activity_prov.get("rowIdx"),
                        "colIdx": visit_prov.get("colIdx"),
                    },
                }

                sais.append(sai)
                sai_counter += 1

        return sais

    # ========================================================================
    # HTML CONTEXT BUILDER
    # ========================================================================

    def _build_html_context(self, html_tables: List[Dict[str, Any]]) -> str:
        """Build HTML context string from all tables."""
        parts = []
        for table in html_tables:
            table_id = table.get("id", "unknown")
            category = table.get("category", "MAIN_SOA")
            page_start = table.get("pageStart", table.get("pages", [1])[0] if table.get("pages") else 1)
            page_end = table.get("pageEnd", page_start)
            html = table.get("html", "")

            parts.append(f"""### Table: {table_id}
Category: {category}
Pages: {page_start}-{page_end}

{html}
""")
        return "\n\n---\n\n".join(parts)

    # ========================================================================
    # POST-PROCESSING
    # ========================================================================

    def _post_process(
        self,
        result: Dict[str, Any],
        html_tables: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Post-process: defaults, visitGroups, quality metrics."""
        result.setdefault("protocolType", "hybrid")
        result.setdefault("primaryReferencePoint", "randomization")
        result.setdefault("visits", [])
        result.setdefault("activities", [])
        result.setdefault("scheduledActivityInstances", [])
        result.setdefault("footnotes", [])

        # ---- Process visits ----
        seen_visit_ids = set()
        for i, visit in enumerate(result.get("visits", [])):
            if not visit.get("id") or visit["id"] in seen_visit_ids:
                visit["id"] = f"ENC-{i+1:03d}"
            seen_visit_ids.add(visit["id"])

            visit.setdefault("name", f"Visit {i+1}")
            visit.setdefault("originalName", visit["name"])
            visit.setdefault("visitType", "treatment")
            visit.setdefault("timingModifier", None)
            visit.setdefault("parentVisit", None)
            visit.setdefault("timing", {})
            visit.setdefault("window", None)
            visit.setdefault("recurrence", None)
            visit.setdefault("footnoteMarkers", [])
            visit.setdefault("provenance", {
                "pageNumber": html_tables[0].get("pageStart", 1) if html_tables else 1
            })

        # ---- Build visitGroups from parentVisit ----
        visit_groups = {}
        for visit in result.get("visits", []):
            parent = visit.get("parentVisit")
            if parent:
                visit_groups.setdefault(parent, []).append(visit["id"])

        # Merge with LLM-provided visitGroups
        for parent_name, enc_ids in result.get("visitGroups", {}).items():
            if parent_name not in visit_groups:
                visit_groups[parent_name] = enc_ids
            else:
                for enc_id in enc_ids:
                    if enc_id not in visit_groups[parent_name]:
                        visit_groups[parent_name].append(enc_id)

        result["visitGroups"] = visit_groups

        # ---- Process activities ----
        seen_activity_ids = set()
        for i, activity in enumerate(result.get("activities", [])):
            if not activity.get("id") or activity["id"] in seen_activity_ids:
                activity["id"] = f"ACT-{i+1:03d}"
            seen_activity_ids.add(activity["id"])

            activity.setdefault("name", f"Activity {i+1}")
            activity.setdefault("category", "OTHER")
            activity.setdefault("cdashDomain", None)
            activity.setdefault("footnoteMarkers", [])
            activity.setdefault("provenance", {
                "pageNumber": html_tables[0].get("pageStart", 1) if html_tables else 1
            })

        # ---- Process SAIs ----
        seen_sai_ids = set()
        for i, sai in enumerate(result.get("scheduledActivityInstances", [])):
            if not sai.get("id") or sai["id"] in seen_sai_ids:
                sai["id"] = f"SAI-{i+1:03d}"
            seen_sai_ids.add(sai["id"])

            sai.setdefault("activityId", None)
            sai.setdefault("visitId", None)
            sai.setdefault("isRequired", True)
            sai.setdefault("condition", None)
            sai.setdefault("timingModifier", None)
            sai.setdefault("parentVisit", None)
            sai.setdefault("footnoteMarkers", [])
            sai.setdefault("provenance", {})

            # Backfill denormalized names
            if not sai.get("activityName"):
                activity_id = sai.get("activityId")
                if activity_id:
                    for act in result.get("activities", []):
                        if act.get("id") == activity_id:
                            sai["activityName"] = act.get("name", "")
                            break
            if not sai.get("visitName"):
                visit_id = sai.get("visitId")
                if visit_id:
                    for vis in result.get("visits", []):
                        if vis.get("id") == visit_id:
                            sai["visitName"] = vis.get("name", "")
                            break

        # ---- Process footnotes ----
        default_page = html_tables[0].get("pageStart", 1) if html_tables else 1
        for i, footnote in enumerate(result.get("footnotes", [])):
            footnote.setdefault("marker", str(i+1))
            footnote.setdefault("text", "")
            footnote.setdefault("ruleType", "reference")
            footnote.setdefault("structuredRule", {})
            footnote.setdefault("appliesTo", [])
            footnote.setdefault("category", "OPERATIONAL")
            footnote.setdefault("subcategory", "site_instruction")
            footnote.setdefault("classificationReasoning", "")
            footnote.setdefault("edcImpact", {
                "affectsScheduling": False,
                "affectsBranching": False,
                "isInformational": True
            })
            footnote.setdefault("provenance", {
                "pageNumber": default_page,
                "tableId": html_tables[0].get("tableId", "SOA-1") if html_tables else "SOA-1",
                "location": "table_footer"
            })

        # ---- Populate footnote appliesTo from SAI footnoteMarkers ----
        marker_to_footnote = {}
        for fn in result.get("footnotes", []):
            marker = (fn.get("marker") or "").lower()
            if marker:
                marker_to_footnote[marker] = fn

        for sai in result.get("scheduledActivityInstances", []):
            for marker in sai.get("footnoteMarkers", []):
                fn = marker_to_footnote.get(marker.lower())
                if fn:
                    sai_ref = f"{sai.get('activityId')}@{sai.get('visitId')}"
                    if sai_ref not in fn.get("appliesTo", []):
                        fn.setdefault("appliesTo", []).append(sai_ref)

        # ---- Quality metrics ----
        visits = result.get("visits", [])
        activities = result.get("activities", [])
        sais = result.get("scheduledActivityInstances", [])
        footnotes = result.get("footnotes", [])

        total_possible = len(visits) * len(activities) if visits and activities else 1
        matrix_coverage = len(sais) / total_possible if total_possible > 0 else 0

        category_counts = {"CONDITIONAL": 0, "SCHEDULING": 0, "OPERATIONAL": 0, "multiLabel": 0}
        for fn in footnotes:
            cats = fn.get("category", "OPERATIONAL")
            cats = cats if isinstance(cats, list) else [cats]
            for cat in cats:
                if cat in category_counts:
                    category_counts[cat] += 1
            if len(cats) > 1:
                category_counts["multiLabel"] += 1

        timepoint_encounters = sum(1 for v in visits if v.get("timingModifier"))

        result["qualityMetrics"] = {
            "totalVisits": len(visits),
            "visitsWithWindows": sum(1 for v in visits if v.get("window")),
            "visitsWithRecurrence": sum(1 for v in visits if v.get("recurrence")),
            "timepointEncounters": timepoint_encounters,
            "standaloneEncounters": len(visits) - timepoint_encounters,
            "visitGroupCount": len(visit_groups),
            "totalActivities": len(activities),
            "totalScheduledInstances": len(sais),
            "matrixCoverage": round(matrix_coverage, 3),
            "footnotesLinked": len(footnotes),
            "footnoteCategoryDistribution": category_counts,
        }

        expected_min = total_possible * 0.2
        if len(sais) < expected_min and len(sais) < 100:
            logger.warning(
                f"Low SAI count: {len(sais)} generated, expected at least {int(expected_min)}. "
                f"Matrix coverage: {matrix_coverage:.1%}"
            )

        return result


# ============================================================================
# CLI SUPPORT FOR TESTING
# ============================================================================

if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)

    sample_html = """
    <!-- Page 41 -->
    <table>
        <thead>
            <tr>
                <th>Assessment</th>
                <th>Screening<sup>a</sup></th>
                <th>C1D1 BI</th>
                <th>C1D1 EOI</th>
                <th>Cycle 1 Day 8</th>
                <th>End of Treatment</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Vital Signs</td>
                <td>X</td>
                <td>X<sup>b</sup></td>
                <td>X</td>
                <td>X</td>
                <td>X</td>
            </tr>
            <tr>
                <td>Physical Examination</td>
                <td>X</td>
                <td>X</td>
                <td></td>
                <td></td>
                <td>X</td>
            </tr>
            <tr>
                <td>PK Blood Sample</td>
                <td></td>
                <td>X<sup>c</sup></td>
                <td>X<sup>c</sup></td>
                <td></td>
                <td></td>
            </tr>
        </tbody>
    </table>
    <p><sup>a</sup> Within 28 days prior to randomization.</p>
    <p><sup>b</sup> Pre-dose vital signs required.</p>
    <p><sup>c</sup> PK samples: pre-infusion trough and end-of-infusion peak.</p>
    """

    html_tables = [
        {
            "id": "SOA-1",
            "html": sample_html,
            "pages": [41, 42],
            "pageStart": 41,
            "pageEnd": 42,
            "category": "MAIN_SOA"
        }
    ]

    async def test():
        interpreter = SOAHTMLInterpreter()
        result = await interpreter.interpret(html_tables, "TEST-001")
        print(json.dumps(result, indent=2))
        print(f"\n--- Summary ---")
        print(f"Visits: {len(result.get('visits', []))}")
        print(f"  - Timepoint encounters: {result.get('qualityMetrics', {}).get('timepointEncounters', 0)}")
        print(f"  - Standalone encounters: {result.get('qualityMetrics', {}).get('standaloneEncounters', 0)}")
        print(f"  - Visit groups: {result.get('qualityMetrics', {}).get('visitGroupCount', 0)}")
        print(f"Activities: {len(result.get('activities', []))}")
        print(f"SAIs: {len(result.get('scheduledActivityInstances', []))}")
        print(f"Matrix Coverage: {result.get('qualityMetrics', {}).get('matrixCoverage', 0):.1%}")
        print(f"\nVisit Groups: {json.dumps(result.get('visitGroups', {}), indent=2)}")

    asyncio.run(test())