"""
Stage 2: Activity Component Expansion (Protocol-Driven)

Decomposes parent activities (e.g., "Hematology") into individual component tests
(e.g., WBC, RBC, Hemoglobin) using protocol-specific data:
1. Extraction module JSON outputs (lab_specs, biospecimen, pkpd, etc.)
2. Protocol PDF text via Gemini Files API

Design Principles:
1. Protocol-Only - Use ONLY data from this protocol (no static library)
2. LLM-First - Single unified Gemini query with JSON + PDF context
3. Full Provenance - Every component traced to source (page, JSON path)
4. Conservative - Only expand with high confidence (>= 0.85)

v3.0 Changes (LLM-Based Validation):
- Replaced brittle regex recovery with LLM-based semantic validation
- Uses ComponentValidator for intelligent garbage filtering
- Deduplication now uses LLM semantic understanding (e.g., WBC = White Blood Cell Count)
- Tiered validation: cache lookup → LLM batch validation → confidence thresholds
- Fixed 3x component duplication bug in Chemistry/Hematology activities

v2.1 Changes (Bug Fix - Incomplete Expansions):
- Added confidence equalization for components from same explicit list
- Added validation: rationale component count vs actual output count
- Added text_snippet parsing to recover missing components when LLM fails
- Fixed issue where explicit lists like "A, B, C, D, E" only returned 1 component

v2.0 Changes:
- Removed static library (activity_components.json) - had unknown provenance
- Added unified LLM approach for scalability
- Full provenance and rationale for every component

Usage:
    from soa_analyzer.interpretation.stage2_activity_expansion import ActivityExpander

    expander = ActivityExpander()
    result = expander.expand_activities(usdm_output, extraction_outputs, gemini_file_uri)
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..models.expansion_proposal import (
    ActivityComponent,
    ActivityExpansion,
    ExpansionType,
    HumanReviewItem,
)
from .context_assembler import ContextAssembler
from .component_validator import ComponentValidator

logger = logging.getLogger(__name__)

# Paths
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
UNIFIED_PROMPT_FILE = PROMPTS_DIR / "activity_expansion_unified.txt"

# Confidence threshold - only expand if above this
HIGH_CONFIDENCE_THRESHOLD = 0.85


@dataclass
class ExpansionConfig:
    """Configuration for activity expansion."""
    confidence_threshold: float = HIGH_CONFIDENCE_THRESHOLD
    max_components_per_activity: int = 20
    include_optional_components: bool = True
    # LLM settings
    llm_model: str = "gemini-3-pro-preview"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 8192


@dataclass
class Stage2Result:
    """Result of Stage 2 activity expansion."""
    expansions: List[ActivityExpansion] = field(default_factory=list)
    review_items: List[HumanReviewItem] = field(default_factory=list)
    activities_processed: int = 0
    activities_expanded: int = 0
    components_created: int = 0
    library_matches: int = 0
    llm_expansions: int = 0
    skipped: int = 0

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of expansion results."""
        return {
            "activitiesProcessed": self.activities_processed,
            "activitiesExpanded": self.activities_expanded,
            "componentsCreated": self.components_created,
            "libraryMatches": self.library_matches,
            "llmExpansions": self.llm_expansions,
            "skipped": self.skipped,
            "reviewItemsCount": len(self.review_items),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary for stage output."""
        return {
            "stage": 2,
            "stageName": "Activity Expansion",
            "success": True,
            "expansions": [e.to_dict() for e in self.expansions],
            "metrics": {
                "activitiesProcessed": self.activities_processed,
                "activitiesExpanded": self.activities_expanded,
                "componentsCreated": self.components_created,
                "libraryMatches": self.library_matches,
                "llmExpansions": self.llm_expansions,
                "skipped": self.skipped,
            },
            "reviewItems": [r.to_dict() for r in self.review_items],
        }


class ActivityExpander:
    """
    Stage 2: Activity Component Expander (Protocol-Driven).

    Expands composite activities into their individual components using
    protocol-specific data from extraction modules and PDF mining.

    v2.0: Removed static library, uses unified LLM approach.
    """

    def __init__(self, config: Optional[ExpansionConfig] = None):
        """Initialize the activity expander."""
        self.config = config or ExpansionConfig()
        self._unified_prompt_template: Optional[str] = None
        self._load_unified_prompt()

    def _load_unified_prompt(self) -> None:
        """Load the unified activity expansion prompt template."""
        if UNIFIED_PROMPT_FILE.exists():
            try:
                with open(UNIFIED_PROMPT_FILE, "r") as f:
                    self._unified_prompt_template = f.read()
                logger.info("Loaded unified activity expansion prompt")
            except Exception as e:
                logger.warning(f"Failed to load unified prompt: {e}")
                self._unified_prompt_template = None
        else:
            logger.warning(f"Unified prompt not found at {UNIFIED_PROMPT_FILE}")

    def _find_activity_components(
        self,
        activity_name: str,
        cdash_domain: str,
        extraction_context: Dict[str, Any],
        gemini_file_uri: Optional[str] = None,
    ) -> Tuple[List[Dict], float, str]:
        """
        Single Gemini query to find activity components from JSON + PDF.

        Uses the unified LLM approach - passes extraction JSON and PDF reference
        to Gemini and asks for components with full provenance.

        Args:
            activity_name: Name of the activity (e.g., "Hematology")
            cdash_domain: CDISC domain (LB, VS, IM, QS, etc.)
            extraction_context: Relevant extraction JSON data from ContextAssembler
            gemini_file_uri: Optional Gemini Files API URI for PDF

        Returns:
            Tuple of (components_list, overall_confidence, expansion_rationale)
        """
        if not self._unified_prompt_template:
            logger.warning("No unified prompt template - cannot expand activities")
            return [], 0.0, "No prompt template available"

        # Format extraction JSON for the prompt
        extraction_json = json.dumps(
            extraction_context.get("extraction_data", {}),
            indent=2,
            default=str
        )

        # Build the prompt
        prompt = self._unified_prompt_template.format(
            activity_name=activity_name,
            cdash_domain=cdash_domain,
            extraction_json=extraction_json,
        )

        # Call Gemini (with optional PDF access)
        try:
            from ..soa_html_interpreter import call_llm
            response = call_llm(
                prompt,
                max_tokens=self.config.llm_max_tokens,
                gemini_file_uri=gemini_file_uri,
            )

            if not response:
                logger.warning(f"Empty LLM response for '{activity_name}'")
                return [], 0.0, "Empty LLM response"

            # Parse the response
            return self._parse_unified_response(response, activity_name, cdash_domain)

        except ImportError:
            logger.warning("LLM module not available")
            return [], 0.0, "LLM module not available"
        except Exception as e:
            logger.error(f"LLM call failed for '{activity_name}': {e}")
            return [], 0.0, f"LLM call failed: {str(e)}"

    def _parse_unified_response(
        self,
        response: str,
        activity_name: str,
        cdash_domain: str = "LB",
    ) -> Tuple[List[Dict], float, str]:
        """
        Parse the unified LLM response.

        Args:
            response: LLM response text
            activity_name: Name of the activity being expanded
            cdash_domain: CDISC domain for context (e.g., LB, VS, PE)

        Returns:
            Tuple of (components_list, overall_confidence, expansion_rationale)
        """
        try:
            # Try direct parse
            try:
                data = json.loads(response)
            except json.JSONDecodeError:
                # Try to find JSON object in response
                json_match = re.search(r"\{[\s\S]*\}", response)
                if json_match:
                    data = json.loads(json_match.group())
                else:
                    logger.warning(f"Could not parse LLM response as JSON for '{activity_name}'")
                    return [], 0.0, "Failed to parse LLM response"

            # Extract fields
            should_expand = data.get("should_expand", False)
            components = data.get("components", [])
            overall_confidence = data.get("overall_confidence", 0.0)
            rationale = data.get("expansion_rationale", "")

            if not should_expand:
                logger.debug(f"LLM decided not to expand '{activity_name}': {rationale}")
                return [], overall_confidence, rationale

            # Step 1: Equalize confidence for components from the same explicit list
            components = self._equalize_explicit_list_confidence(components, activity_name)

            # Step 2: Try to recover missing components from text_snippet
            # Uses LLM-based validation for semantic deduplication and garbage filtering
            components = self._recover_missing_components_from_snippet(
                components, activity_name, cdash_domain
            )

            # Step 3: Filter components by confidence
            filtered_components = [
                c for c in components
                if c.get("confidence", 0.0) >= HIGH_CONFIDENCE_THRESHOLD
            ]

            # Step 4: Validate rationale vs actual count
            self._validate_component_count(
                rationale, len(components), len(filtered_components), activity_name
            )

            if not filtered_components and components:
                logger.warning(
                    f"All {len(components)} components for '{activity_name}' "
                    f"below confidence threshold ({HIGH_CONFIDENCE_THRESHOLD}). "
                    f"Check if LLM assigned inconsistent confidence scores."
                )

            return filtered_components, overall_confidence, rationale

        except Exception as e:
            logger.error(f"Error parsing unified response for '{activity_name}': {e}")
            return [], 0.0, f"Parse error: {str(e)}"

    def _equalize_explicit_list_confidence(
        self,
        components: List[Dict],
        activity_name: str,
    ) -> List[Dict]:
        """
        Equalize confidence for components from the same explicit list.

        When components share the same page_number and similar text_snippet,
        they likely came from the same explicit list and should have equal confidence.
        Use the maximum confidence among them.

        Args:
            components: List of component dicts from LLM
            activity_name: Activity name for logging

        Returns:
            Components with equalized confidence where applicable
        """
        if not components or len(components) <= 1:
            return components

        # Group components by page_number
        page_groups: Dict[int, List[Dict]] = {}
        for comp in components:
            page = comp.get("page_number")
            if page is not None:
                if page not in page_groups:
                    page_groups[page] = []
                page_groups[page].append(comp)

        # For each page group, check if they're from an explicit list
        equalized_count = 0
        for page, group in page_groups.items():
            if len(group) >= 2:
                # Multiple components from same page - likely explicit list
                # Find max confidence in the group
                max_confidence = max(c.get("confidence", 0.0) for c in group)
                min_confidence = min(c.get("confidence", 0.0) for c in group)

                # If there's a significant gap (>0.10), equalize to max
                if max_confidence - min_confidence > 0.10:
                    logger.info(
                        f"Equalizing confidence for {len(group)} components from page {page} "
                        f"for '{activity_name}': {min_confidence:.2f} -> {max_confidence:.2f}"
                    )
                    for comp in group:
                        if comp.get("confidence", 0.0) < max_confidence:
                            comp["confidence"] = max_confidence
                            comp["_confidence_equalized"] = True
                            equalized_count += 1

        if equalized_count > 0:
            logger.info(
                f"Equalized confidence for {equalized_count} components in '{activity_name}'"
            )

        return components

    def _validate_component_count(
        self,
        rationale: str,
        total_components: int,
        filtered_components: int,
        activity_name: str,
    ) -> None:
        """
        Validate that rationale component count matches actual output.

        Extracts numbers from rationale like "Found 5 components" and warns
        if there's a mismatch with actual output.

        Args:
            rationale: The expansion rationale string
            total_components: Total components returned by LLM
            filtered_components: Components after confidence filtering
            activity_name: Activity name for logging
        """
        # Try to extract claimed count from rationale
        # Patterns like "Found 5 components", "5 components explicitly"
        count_patterns = [
            r"[Ff]ound\s+(\d+)\s+component",
            r"(\d+)\s+component[s]?\s+explicitly",
            r"(\d+)\s+explicit\s+component",
            r"identifies?\s+(\d+)\s+component",
        ]

        claimed_count = None
        for pattern in count_patterns:
            match = re.search(pattern, rationale)
            if match:
                claimed_count = int(match.group(1))
                break

        if claimed_count is not None:
            if filtered_components < claimed_count:
                logger.warning(
                    f"VALIDATION WARNING for '{activity_name}': "
                    f"Rationale claims {claimed_count} components but only "
                    f"{filtered_components} passed confidence threshold "
                    f"(LLM returned {total_components} total). "
                    f"This may indicate inconsistent confidence scoring."
                )
            elif total_components < claimed_count:
                logger.warning(
                    f"VALIDATION WARNING for '{activity_name}': "
                    f"Rationale claims {claimed_count} components but LLM only "
                    f"returned {total_components}. The LLM may have lost components."
                )

    def _recover_missing_components_from_snippet(
        self,
        components: List[Dict],
        activity_name: str,
        cdash_domain: str = "LB",
    ) -> List[Dict]:
        """
        Recover and validate missing components from text_snippet using LLM reasoning.

        v3.0: Replaced brittle regex with LLM-based semantic validation.

        If the text_snippet contains component names that the LLM missed, this method:
        1. Extracts candidate names from snippets (simple splitting)
        2. Validates candidates using LLM semantic reasoning
        3. Deduplicates using LLM understanding of clinical terminology
        4. Adds validated components with proper provenance

        Args:
            components: List of component dicts from LLM
            activity_name: Activity name for logging
            cdash_domain: CDISC domain (LB, VS, PE, etc.) for context

        Returns:
            Components list with validated recovered components added
        """
        import asyncio

        if not components:
            return components

        # Step 1: Extract candidate names from text snippets
        candidates = self._extract_candidates_from_snippets(components)

        if not candidates:
            return components

        # Get existing component names for deduplication (exact match pre-filter)
        existing_names = {c.get("name", "").lower().strip() for c in components}

        # Filter out candidates that already exist (exact match)
        new_candidates = [
            c for c in candidates
            if c.get("name", "").lower().strip() not in existing_names
        ]

        if not new_candidates:
            logger.debug(f"No new candidates to validate for '{activity_name}'")
            return components

        # Build list of existing component names for semantic deduplication by LLM
        # Include the parent activity name to prevent "Urinalysis" as component of Urinalysis
        existing_component_names = [c.get("name", "") for c in components if c.get("name")]
        existing_component_names.append(activity_name)  # Prevent parent as component

        # Step 2: Validate candidates using LLM with semantic deduplication
        logger.info(
            f"Validating {len(new_candidates)} candidate components for '{activity_name}' "
            f"using LLM semantic reasoning (checking against {len(existing_component_names)} existing)"
        )

        try:
            validator = ComponentValidator()
            # Run async validation - handle both sync and async contexts
            try:
                loop = asyncio.get_running_loop()
                # Already in async context - use nest_asyncio or create a task
                import nest_asyncio
                nest_asyncio.apply()
                validation_result = loop.run_until_complete(
                    validator.validate_components(
                        new_candidates, activity_name, cdash_domain, existing_component_names
                    )
                )
            except RuntimeError:
                # No running loop - safe to use asyncio.run
                validation_result = asyncio.run(
                    validator.validate_components(
                        new_candidates, activity_name, cdash_domain, existing_component_names
                    )
                )
        except ImportError:
            # nest_asyncio not installed - skip validation
            logger.warning(f"nest_asyncio not installed - skipping LLM validation for '{activity_name}'")
            return components
        except Exception as e:
            logger.error(f"LLM validation failed for '{activity_name}': {e}")
            return components

        # Step 3: Add validated components
        recovered_count = 0
        for valid_comp in validation_result.valid_components:
            canonical = valid_comp.canonical_form or valid_comp.name
            canonical_lower = canonical.lower().strip()

            # Final deduplication check
            if canonical_lower in existing_names:
                continue

            # Find the source metadata from the candidate
            source_candidate = next(
                (c for c in new_candidates if c.get("name", "").lower() == valid_comp.name.lower()),
                {}
            )

            # Create recovered component with validated name
            recovered_comp = {
                "name": canonical,  # Use LLM-validated canonical form
                "confidence": valid_comp.confidence,
                "page_number": source_candidate.get("page_number"),
                "source": source_candidate.get("source", "pdf_text"),
                "json_path": source_candidate.get("json_path"),
                "text_snippet": source_candidate.get("source_snippet", "")[:200],
                "rationale": f"LLM-validated: {valid_comp.rationale}",
                "_recovered_from_snippet": True,
                "_llm_validated": True,
            }
            components.append(recovered_comp)
            existing_names.add(canonical_lower)
            recovered_count += 1

        if recovered_count > 0:
            logger.info(
                f"Recovered {recovered_count} LLM-validated components from text snippets "
                f"for '{activity_name}'"
            )

        # Log rejected and review items for debugging
        if validation_result.rejected_components:
            rejected_names = [c.name for c in validation_result.rejected_components]
            logger.debug(
                f"Rejected {len(rejected_names)} invalid candidates for '{activity_name}': "
                f"{rejected_names[:5]}{'...' if len(rejected_names) > 5 else ''}"
            )

        if validation_result.review_items:
            review_names = [c.name for c in validation_result.review_items]
            logger.info(
                f"Components flagged for review in '{activity_name}': {review_names}"
            )

        return components

    def _extract_candidates_from_snippets(
        self,
        components: List[Dict],
    ) -> List[Dict]:
        """
        Extract candidate component names from text snippets.

        Simple extraction using delimiters - LLM will do semantic validation.

        Args:
            components: List of component dicts from LLM

        Returns:
            List of candidate dicts with name and source metadata
        """
        candidates = []
        seen_snippets = set()
        seen_names = set()

        for comp in components:
            snippet = comp.get("text_snippet", "")
            if not snippet or len(snippet) < 30 or snippet in seen_snippets:
                continue
            seen_snippets.add(snippet)

            metadata = {
                "page_number": comp.get("page_number"),
                "source": comp.get("source"),
                "json_path": comp.get("json_path"),
                "source_snippet": snippet[:200],
            }

            # Simple splitting by common delimiters
            # LLM will validate whether each part is a valid component
            for delimiter in [",", ";", "\n"]:
                if delimiter in snippet:
                    parts = snippet.split(delimiter)
                    for part in parts:
                        part = part.strip()
                        # Basic length filter only - LLM validates semantics
                        if 2 < len(part) < 100:
                            part_lower = part.lower()
                            if part_lower not in seen_names:
                                seen_names.add(part_lower)
                                candidates.append({
                                    "name": part,
                                    **metadata,
                                })

        return candidates

    def _should_expand(self, activity: Dict[str, Any]) -> bool:
        """Determine if an activity should be expanded."""
        cdash_domain = activity.get("cdashDomain", "")

        # Domains that can be expanded - includes procedure types for protocol mining
        expandable_domains = {"LB", "VS", "EG", "QS", "IM", "PC", "PE", "TU", "SC", "MH"}
        if cdash_domain not in expandable_domains:
            return False

        # Never expand certain activity types (based on name patterns)
        activity_name = activity.get("name", "").lower()
        never_expand_patterns = [
            "pregnancy test",
            "informed consent",
            "adverse event",
            "concomitant",
            "disposition",
            "demographics",
        ]
        for pattern in never_expand_patterns:
            if pattern in activity_name:
                return False

        return True

    def _create_expansion_from_components(
        self,
        activity: Dict[str, Any],
        components_data: List[Dict],
        confidence: float,
        rationale: str,
    ) -> ActivityExpansion:
        """Create an ActivityExpansion from LLM-returned components with provenance."""
        components = []
        for idx, comp_data in enumerate(components_data):
            component = ActivityComponent(
                name=comp_data.get("name", ""),
                loinc_code=comp_data.get("loinc_code"),
                loinc_display=comp_data.get("loinc_display"),
                cdisc_code=comp_data.get("cdisc_code"),
                unit=comp_data.get("unit"),
                specimen_type=comp_data.get("specimen_type"),
                cdash_domain=activity.get("cdashDomain"),
                is_required=True,
                order=idx,
                # Provenance fields (v2.0)
                source=comp_data.get("source"),
                json_path=comp_data.get("json_path"),
                page_number=comp_data.get("page_number"),
                text_snippet=comp_data.get("text_snippet"),
                rationale=comp_data.get("rationale"),
                confidence=comp_data.get("confidence", 1.0),
                # Specimen details
                tube_type=comp_data.get("tube_type"),
                collection_volume=comp_data.get("collection_volume"),
                fasting_required=comp_data.get("fasting_required", False),
                processing_requirements=comp_data.get("processing_requirements"),
                storage_requirements=comp_data.get("storage_requirements"),
            )
            components.append(component)

        return ActivityExpansion(
            parent_activity_id=activity.get("id", ""),
            parent_activity_name=activity.get("name", ""),
            components=components,
            expansion_type=ExpansionType.COMPONENT_EXPANSION,
            confidence=confidence,
            rationale=rationale,
            source="protocol_extraction",
            requires_review=False,  # Conservative: only expand high-confidence items
        )

    def expand_activities(
        self,
        usdm_output: Dict[str, Any],
        extraction_outputs: Optional[Dict[str, Dict]] = None,
        gemini_file_uri: Optional[str] = None,
    ) -> Stage2Result:
        """
        Expand composite activities into components using protocol-specific data.

        Uses a unified LLM approach:
        1. Assemble context from extraction JSON files (lab_specs, biospecimen, etc.)
        2. Single Gemini query per activity with JSON + PDF context
        3. Only expand if confidence >= 0.85 (conservative threshold)

        Args:
            usdm_output: USDM output from previous stages
            extraction_outputs: Dict of extraction module outputs
            gemini_file_uri: Optional Gemini Files API URI for PDF access

        Returns:
            Stage2Result with expansions (no review items for unexpanded activities)
        """
        result = Stage2Result()

        # Initialize context assembler
        context_assembler = ContextAssembler(extraction_outputs) if extraction_outputs else None

        # Get activities from USDM structure
        activities = self._get_activities(usdm_output)
        result.activities_processed = len(activities)

        logger.info(f"Stage 2: Processing {len(activities)} activities for expansion (protocol-driven)")
        if extraction_outputs:
            logger.info(f"  - Extraction modules available: {list(extraction_outputs.keys())}")
        else:
            logger.warning("  - No extraction outputs provided")

        for activity in activities:
            activity_id = activity.get("id", "")
            activity_name = activity.get("name", "")
            cdash_domain = activity.get("cdashDomain", "")

            # Check if this activity should be expanded
            if not self._should_expand(activity):
                result.skipped += 1
                logger.debug(f"Skipping '{activity_name}' ({cdash_domain}) - not expandable domain/type")
                continue

            # Assemble context for this activity
            extraction_context = {}
            if context_assembler:
                extraction_context = context_assembler.get_context_for_activity(
                    activity_name,
                    cdash_domain
                )

            # Check if we have any context to work with
            has_extraction_context = bool(extraction_context.get("modules_found"))
            has_pdf_access = bool(gemini_file_uri)

            if not has_extraction_context and not has_pdf_access:
                result.skipped += 1
                logger.info(f"Skipping '{activity_name}' - no extraction data or PDF available")
                continue

            # Log when only PDF is available (activity will still be processed)
            if not has_extraction_context and has_pdf_access:
                logger.info(f"Processing '{activity_name}' ({cdash_domain}) with PDF-only context")

            # Single unified LLM query
            components, confidence, rationale = self._find_activity_components(
                activity_name,
                cdash_domain,
                extraction_context,
                gemini_file_uri,
            )

            # Conservative expansion decision
            if not components or confidence < self.config.confidence_threshold:
                result.skipped += 1
                logger.info(
                    f"Skipping '{activity_name}' - confidence {confidence:.2f} "
                    f"below threshold ({self.config.confidence_threshold})"
                )
                logger.debug(f"  Rationale: {rationale}")
                continue  # Activity passes through UNCHANGED

            # Create expansion with full provenance
            expansion = self._create_expansion_from_components(
                activity,
                components,
                confidence,
                rationale,
            )
            result.expansions.append(expansion)
            result.activities_expanded += 1
            result.components_created += len(expansion.components)
            result.llm_expansions += 1

            logger.info(
                f"Expanded '{activity_name}' with {len(components)} components "
                f"(confidence: {confidence:.2f})"
            )

        logger.info(
            f"Stage 2 complete: {result.activities_expanded}/{result.activities_processed} "
            f"activities expanded, {result.components_created} components created "
            f"(skipped: {result.skipped})"
        )

        return result

    def _get_activities(self, usdm_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract activities from USDM structure."""
        # Handle nested structure
        if "studyVersion" in usdm_output:
            study_version = usdm_output["studyVersion"]
            if isinstance(study_version, list) and study_version:
                return study_version[0].get("activities", [])
        return usdm_output.get("activities", [])

    def apply_expansions_to_usdm(
        self,
        usdm_output: Dict[str, Any],
        result: Stage2Result,
    ) -> Dict[str, Any]:
        """
        Apply expansions to USDM output structure.

        This adds component activities as children of parent activities.
        """
        # Create a mapping of parent activity ID to expansion
        expansion_map = {exp.parent_activity_id: exp for exp in result.expansions}

        # Get activities (handle nested structure safely)
        if "studyVersion" in usdm_output:
            study_version = usdm_output.get("studyVersion", [])
            if isinstance(study_version, list) and study_version:
                activities = study_version[0].get("activities", [])
            else:
                activities = []
        else:
            activities = usdm_output.get("activities", [])

        # Add expansion metadata to activities
        for activity in activities:
            activity_id = activity.get("id", "")
            if activity_id in expansion_map:
                expansion = expansion_map[activity_id]
                activity["_expansion"] = {
                    "expansionId": expansion.id,
                    "componentCount": len(expansion.components),
                    "components": [c.to_dict() for c in expansion.components],
                    "confidence": expansion.confidence,
                    "source": expansion.source,
                }

        return usdm_output


def expand_activities(
    usdm_output: Dict[str, Any],
    extraction_outputs: Optional[Dict[str, Dict]] = None,
    gemini_file_uri: Optional[str] = None,
    config: Optional[ExpansionConfig] = None,
) -> Tuple[Dict[str, Any], Stage2Result]:
    """
    Convenience function to expand activities using protocol-specific data.

    Uses a unified LLM approach:
    1. Assemble context from extraction JSON files (lab_specs, biospecimen, etc.)
    2. Single Gemini query per activity with JSON + PDF context
    3. Only expand if confidence >= 0.85 (conservative threshold)

    Args:
        usdm_output: USDM output from previous stages
        extraction_outputs: Dict of extraction module outputs (lab_specs, etc.)
        gemini_file_uri: Optional Gemini Files API URI for PDF access
        config: Optional expansion configuration

    Returns:
        Tuple of (updated USDM output, expansion result)
    """
    expander = ActivityExpander(config)
    result = expander.expand_activities(usdm_output, extraction_outputs, gemini_file_uri)
    updated_output = expander.apply_expansions_to_usdm(usdm_output, result)
    return updated_output, result
