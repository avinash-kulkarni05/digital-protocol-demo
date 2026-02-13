"""
Stage 5: Specimen Enrichment

Extracts and enriches specimen/biospecimen data from SOA tables and footnotes.
Handles collection, processing, storage, and shipping requirements.

Design Principles:
1. LLM-First - LLM analyzes ALL activities in batch, patterns validate
2. Cache-Heavy - Cache LLM decisions by activity name for reuse
3. Confidence-Based - Auto-apply ≥0.90, escalate <0.90 to review
4. Audit Trail - Full provenance for every enriched entity
5. USDM Compliant - Proper ID generation, referential integrity

Usage:
    from soa_analyzer.interpretation.stage5_specimen_enrichment import SpecimenEnricher

    enricher = SpecimenEnricher()
    result = await enricher.enrich_specimens(usdm_output)
    updated_output = enricher.apply_enrichments_to_usdm(usdm_output, result)
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..models.specimen_enrichment import (
    SpecimenCategory,
    SpecimenSubtype,
    SpecimenPurpose,
    TubeType,
    TubeColor,
    StoragePhase,
    EquipmentType,
    ShippingCondition,
    VolumeSpecification,
    TemperatureRange,
    TubeSpecification,
    ProcessingRequirement,
    StorageRequirement,
    ShippingRequirement,
    SpecimenDecision,
    SpecimenProvenance,
    SpecimenEnrichment,
    HumanReviewItem,
    ValidationDiscrepancy,
    Stage5Result,
    SpecimenEnrichmentConfig,
    infer_specimen_from_activity_name,
    infer_subtype_from_panel,
    generate_specimen_collection_id,
    generate_condition_id,
    generate_code_id,
    generate_review_id,
)
from ..models.code_object import (
    CodeObject,
    NCI_EVS_CODE_SYSTEM,
    NCI_EVS_VERSION,
)
from ..utils.athena_lookup import AthenaLookupService

logger = logging.getLogger(__name__)

# Paths
CACHE_DIR = Path(__file__).parent.parent / ".cache" / "specimen_enrichment"
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "specimen_enrichment.txt"
SPECIMEN_CODES_PATH = Path(__file__).parent.parent / "config" / "specimen_codes.json"
SPECIMEN_PATTERNS_PATH = Path(__file__).parent.parent / "config" / "specimen_patterns.json"
ACTIVITY_COMPONENTS_PATH = Path(__file__).parent.parent / "config" / "activity_components.json"
PROCESSING_SPECS_PATH = Path(__file__).parent.parent / "config" / "processing_specifications.json"
STORAGE_SPECS_PATH = Path(__file__).parent.parent / "config" / "storage_specifications.json"
PEDIATRIC_VOLUMES_PATH = Path(__file__).parent.parent / "config" / "pediatric_volumes.json"

# Domains that involve specimen collection
SPECIMEN_DOMAINS = {"LB", "PC", "PP", "BS", "IS", "MB", "MS", "GF"}

# Domains that do NOT involve specimen collection
NON_SPECIMEN_DOMAINS = {"VS", "EG", "PE", "FA", "QS", "MI", "DM", "DS", "SC", "MH", "AE", "CM"}


class SpecimenPatternRegistry:
    """
    Registry of known specimen patterns for validation (NOT primary routing).

    Used to cross-check LLM decisions, not to drive enrichment.
    Uses O(1) alias index for efficient activity name lookups.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self._activity_mappings: Dict[str, Dict[str, Any]] = {}
        self._volume_patterns: Dict[str, List[str]] = {}
        self._conditional_patterns: Dict[str, List[str]] = {}
        self._fasting_patterns: Dict[str, Any] = {}
        self._non_specimen_keywords: List[str] = []
        self._tube_defaults: Dict[str, Dict[str, Any]] = {}
        # O(1) alias index: lowercase alias → primary key
        self._alias_index: Dict[str, str] = {}
        self._load_config(config_path or SPECIMEN_PATTERNS_PATH)

    def _load_config(self, config_path: Path) -> None:
        """Load patterns from JSON config and build alias index."""
        if not config_path.exists():
            logger.warning(f"Specimen patterns config not found: {config_path}")
            return

        try:
            with open(config_path) as f:
                data = json.load(f)

            self._activity_mappings = data.get("activity_specimen_mappings", {})
            self._volume_patterns = data.get("volume_patterns", {})
            self._conditional_patterns = data.get("conditional_patterns", {})
            self._fasting_patterns = data.get("fasting_patterns", {})
            self._non_specimen_keywords = data.get("non_specimen_activities", {}).get("keywords", [])
            self._tube_defaults = data.get("tube_volume_defaults", {})

            # Build O(1) alias index for fast lookups
            self._alias_index.clear()
            for key, mapping in self._activity_mappings.items():
                # Skip metadata entries
                if key.startswith("_") or not isinstance(mapping, dict):
                    continue
                # Index the primary key itself
                self._alias_index[key.lower()] = key
                # Index all aliases
                for alias in mapping.get("aliases", []):
                    self._alias_index[alias.lower()] = key

            logger.info(
                f"Loaded {len(self._activity_mappings)} activity-specimen mappings, "
                f"{len(self._alias_index)} total indexed entries"
            )
        except Exception as e:
            logger.warning(f"Failed to load specimen patterns config: {e}")

    def get_activity_mapping(self, activity_name: str) -> Optional[Dict[str, Any]]:
        """
        Get known specimen mapping for an activity.

        Uses O(1) alias index for efficient lookups instead of O(n) iteration.
        """
        name_lower = activity_name.lower().strip()

        # O(1) lookup via alias index
        primary_key = self._alias_index.get(name_lower)
        if primary_key:
            mapping = self._activity_mappings.get(primary_key)
            if isinstance(mapping, dict):
                return mapping

        return None

    def is_non_specimen_activity(self, activity_name: str) -> bool:
        """Check if activity does not require specimen collection."""
        name_lower = activity_name.lower()
        return any(kw in name_lower for kw in self._non_specimen_keywords)

    def validate_decision(
        self, decision: SpecimenDecision
    ) -> List[ValidationDiscrepancy]:
        """Validate LLM decision against known patterns."""
        discrepancies = []

        if not decision.has_specimen:
            return discrepancies

        # Get expected mapping
        expected = self.get_activity_mapping(decision.activity_name)
        if not expected:
            return discrepancies

        # Check specimen category
        if decision.specimen_category:
            expected_category = expected.get("category")
            if expected_category and decision.specimen_category.value != expected_category:
                discrepancies.append(ValidationDiscrepancy(
                    activity_id=decision.activity_id,
                    activity_name=decision.activity_name,
                    field="specimenCategory",
                    llm_value=decision.specimen_category.value,
                    expected_value=expected_category,
                    severity="warning",
                    message=f"LLM returned {decision.specimen_category.value}, expected {expected_category}"
                ))

        # Check tube type
        if decision.tube_specification and decision.tube_specification.tube_type:
            expected_tube = expected.get("tube_type")
            if expected_tube and decision.tube_specification.tube_type.value != expected_tube:
                discrepancies.append(ValidationDiscrepancy(
                    activity_id=decision.activity_id,
                    activity_name=decision.activity_name,
                    field="tubeType",
                    llm_value=decision.tube_specification.tube_type.value,
                    expected_value=expected_tube,
                    severity="warning",
                    message=f"LLM returned tube type {decision.tube_specification.tube_type.value}, expected {expected_tube}"
                ))

        return discrepancies


class SpecimenEnricher:
    """
    Stage 5: Specimen Enrichment Handler (LLM-First Strategy).

    Extracts and enriches specimen data from SOA activities and footnotes.
    Uses LLM-first approach with caching and pattern validation.
    """

    def __init__(
        self,
        config: Optional[SpecimenEnrichmentConfig] = None,
        use_cache: bool = True,
        cache_dir: Optional[Path] = None,
    ):
        """
        Initialize specimen enricher.

        Args:
            config: Configuration for specimen enrichment
            use_cache: Whether to use persistent caching
            cache_dir: Directory for cache files
        """
        self.config = config or SpecimenEnrichmentConfig()
        self.use_cache = use_cache
        self.cache_dir = cache_dir or CACHE_DIR

        # Pattern registry for validation
        self._pattern_registry = SpecimenPatternRegistry()

        # Athena lookup service for validated NCI codes
        self._athena = AthenaLookupService()

        # Load activity components for inference
        self._activity_components = self._load_activity_components()

        # Load processing specifications
        self._processing_specs = self._load_processing_specs()

        # Load storage specifications
        self._storage_specs = self._load_storage_specs()

        # Load pediatric volume specifications
        self._pediatric_volumes = self._load_pediatric_volumes()

        # Load prompt template
        self._prompt_template = self._load_prompt_template()

        # In-memory cache: activity_name -> SpecimenDecision
        self._cache: Dict[str, SpecimenDecision] = {}
        self._cache_loaded = False

        # LLM clients (lazy loaded)
        self._gemini_client = None
        self._azure_client = None
        self._azure_deployment = None

        # Extraction context (set during enrich_specimens)
        self._extraction_outputs: Dict[str, Dict] = {}
        self._biospecimen_context: Dict[str, Any] = {}
        self._gemini_file_uri: Optional[str] = None

        # Ensure cache directory exists
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # NOTE: _load_specimen_codes removed - using AthenaLookupService instead

    def _load_activity_components(self) -> Dict[str, Dict[str, Any]]:
        """Load activity components for specimen inference."""
        components = {}
        if ACTIVITY_COMPONENTS_PATH.exists():
            try:
                with open(ACTIVITY_COMPONENTS_PATH) as f:
                    components = json.load(f)
                logger.info(f"Loaded activity components config")
            except Exception as e:
                logger.warning(f"Failed to load activity components: {e}")
        return components

    def _load_processing_specs(self) -> Dict[str, Dict[str, Any]]:
        """Load standard processing specifications."""
        specs = {}
        if PROCESSING_SPECS_PATH.exists():
            try:
                with open(PROCESSING_SPECS_PATH) as f:
                    data = json.load(f)
                specs = data.get("standard_processing", {})
                logger.info(f"Loaded {len(specs)} processing specifications")
            except Exception as e:
                logger.warning(f"Failed to load processing specs: {e}")
        return specs

    def _load_storage_specs(self) -> Dict[str, Dict[str, Any]]:
        """Load storage specifications."""
        specs = {}
        if STORAGE_SPECS_PATH.exists():
            try:
                with open(STORAGE_SPECS_PATH) as f:
                    data = json.load(f)
                specs = data.get("storage_conditions", {})
                logger.info(f"Loaded {len(specs)} storage specifications")
            except Exception as e:
                logger.warning(f"Failed to load storage specs: {e}")
        return specs

    def _load_pediatric_volumes(self) -> Dict[str, Any]:
        """Load pediatric volume specifications."""
        volumes = {}
        if PEDIATRIC_VOLUMES_PATH.exists():
            try:
                with open(PEDIATRIC_VOLUMES_PATH) as f:
                    volumes = json.load(f)
                logger.info(
                    f"Loaded pediatric volume specs: {len(volumes.get('weight_classes', {}))} weight classes, "
                    f"{len(volumes.get('panel_volumes', {}))} panel volumes"
                )
            except Exception as e:
                logger.warning(f"Failed to load pediatric volumes: {e}")
        return volumes

    def get_pediatric_volume(
        self,
        panel_name: str,
        weight_class: str = "adult"
    ) -> Optional[float]:
        """
        Get appropriate volume for a panel based on weight class.

        Args:
            panel_name: Name of the panel (e.g., "hematology", "chemistry_comprehensive")
            weight_class: Weight class (e.g., "adult", "adolescent", "child", "infant", "neonate")

        Returns:
            Volume in mL or None if not found
        """
        panel_volumes = self._pediatric_volumes.get("panel_volumes", {})
        panel_data = panel_volumes.get(panel_name.lower().replace(" ", "_"))
        if not panel_data:
            return None

        # Map weight class to volume key
        volume_key = f"{weight_class}_ml"
        if volume_key in panel_data:
            return panel_data[volume_key]

        # Fallback to adult volume
        return panel_data.get("adult_ml")

    def _load_prompt_template(self) -> str:
        """Load LLM prompt template."""
        if PROMPT_PATH.exists():
            try:
                with open(PROMPT_PATH) as f:
                    template = f.read()
                logger.info("Loaded specimen enrichment prompt template")
                return template
            except Exception as e:
                logger.warning(f"Failed to load prompt template: {e}")
        return ""

    # =========================================================================
    # CACHE METHODS
    # =========================================================================

    def _get_cache_key(self, activity_name: str) -> str:
        """Generate cache key including model version."""
        normalized = f"{activity_name.lower().strip()}:{self.config.model_name}"
        return hashlib.md5(normalized.encode()).hexdigest()

    def _load_cache(self) -> None:
        """Load cache from disk into memory."""
        if self._cache_loaded:
            return

        cache_file = self.cache_dir / "decisions_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                for key, value in data.items():
                    self._cache[key] = SpecimenDecision.from_dict(value)
                logger.info(f"Loaded {len(self._cache)} cached specimen decisions")
            except Exception as e:
                logger.warning(f"Error loading cache: {e}")

        self._cache_loaded = True

    def _check_cache(self, activity_name: str) -> Optional[SpecimenDecision]:
        """Check cache for existing decision."""
        if not self.use_cache:
            return None

        if not self._cache_loaded:
            self._load_cache()

        cache_key = self._get_cache_key(activity_name)
        if cache_key in self._cache:
            decision = self._cache[cache_key]
            decision.source = "cache"
            return decision

        return None

    def _update_cache(self, activity_name: str, decision: SpecimenDecision) -> None:
        """Update in-memory cache with new decision."""
        if not self.use_cache:
            return

        cache_key = self._get_cache_key(activity_name)
        decision.cached_at = datetime.utcnow().isoformat() + "Z"
        self._cache[cache_key] = decision

    def _save_cache(self) -> None:
        """Save in-memory cache to disk."""
        if not self.use_cache:
            return

        cache_file = self.cache_dir / "decisions_cache.json"
        try:
            data = {}
            for key, decision in self._cache.items():
                data[key] = decision.to_dict()
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(data)} decisions to cache")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    # =========================================================================
    # LLM METHODS
    # =========================================================================

    def _init_gemini_client(self) -> None:
        """Initialize Gemini client."""
        if self._gemini_client is not None:
            return

        try:
            import google.generativeai as genai

            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                logger.warning("GEMINI_API_KEY not set")
                return

            genai.configure(api_key=api_key)
            self._gemini_client = genai.GenerativeModel(
                model_name=self.config.model_name,
                generation_config={
                    "temperature": self.config.temperature,
                    "max_output_tokens": self.config.max_output_tokens,
                },
            )
            logger.info(f"Initialized Gemini client: {self.config.model_name}")
        except Exception as e:
            logger.warning(f"Failed to initialize Gemini client: {e}")

    def _init_azure_client(self) -> None:
        """Initialize Azure OpenAI client."""
        if self._azure_client is not None:
            return

        try:
            from openai import AzureOpenAI

            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

            if not all([api_key, endpoint, deployment]):
                logger.warning("Azure OpenAI credentials not fully configured")
                return

            self._azure_client = AzureOpenAI(
                api_key=api_key,
                api_version=api_version,
                azure_endpoint=endpoint,
            )
            self._azure_deployment = deployment
            logger.info(f"Initialized Azure OpenAI client: {deployment}")
        except Exception as e:
            logger.warning(f"Failed to initialize Azure client: {e}")

    async def _call_gemini(self, prompt: str, gemini_file_uri: Optional[str] = None) -> Optional[str]:
        """
        Call Gemini API with optional PDF multimodal support.

        Args:
            prompt: The prompt text
            gemini_file_uri: Optional Gemini Files API URI for PDF validation

        Returns:
            LLM response text or None
        """
        self._init_gemini_client()
        if not self._gemini_client:
            return None

        try:
            # Build content - text-only or multimodal with PDF
            if gemini_file_uri:
                try:
                    import google.generativeai as genai
                    # Extract file name from URI (e.g., "files/abc123" -> "abc123")
                    file_name = gemini_file_uri.split("/")[-1]
                    gemini_file = genai.get_file(file_name)
                    content = [gemini_file, prompt]  # Multimodal: PDF + text
                    logger.info(f"Using multimodal content with PDF: {file_name}")
                except Exception as e:
                    logger.warning(f"Failed to get Gemini file '{gemini_file_uri}': {e}, falling back to text-only")
                    content = prompt
            else:
                content = prompt

            response = await asyncio.to_thread(
                self._gemini_client.generate_content, content
            )
            if response and response.text:
                return response.text
        except Exception as e:
            logger.warning(f"Gemini call failed: {e}")

        return None

    async def _call_azure(self, prompt: str) -> Optional[str]:
        """Call Azure OpenAI API."""
        self._init_azure_client()
        if not self._azure_client or not self._azure_deployment:
            return None

        try:
            response = await asyncio.to_thread(
                self._azure_client.chat.completions.create,
                model=self._azure_deployment,
                messages=[
                    {"role": "system", "content": "You are a clinical trial biospecimen expert."},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_output_tokens,
            )
            if response and response.choices:
                return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"Azure call failed: {e}")

        return None

    async def _call_claude(self, prompt: str) -> Optional[str]:
        """Call Anthropic Claude API (text-only fallback)."""
        try:
            import anthropic

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                logger.warning("ANTHROPIC_API_KEY not set")
                return None

            client = anthropic.Anthropic(api_key=api_key)

            response = await asyncio.to_thread(
                client.messages.create,
                model="claude-sonnet-4-20250514",
                max_tokens=self.config.max_output_tokens,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text if response.content else None
            if content:
                logger.info(f"Anthropic Claude responded ({len(content)} chars)")
            return content
        except Exception as e:
            logger.warning(f"Claude call failed: {e}")

        return None

    async def _call_llm_with_fallback(
        self, prompt: str, gemini_file_uri: Optional[str] = None
    ) -> Tuple[Optional[str], str]:
        """
        Call LLM with retry and fallback, with optional PDF multimodal support.

        Args:
            prompt: The prompt text
            gemini_file_uri: Optional Gemini Files API URI for PDF validation

        Returns:
            Tuple of (response_text, actual_model_name)
        """
        # Try Gemini first (with multimodal PDF if available)
        for attempt in range(self.config.max_retries):
            try:
                response = await self._call_gemini(prompt, gemini_file_uri)
                if response:
                    return response, self.config.model_name
            except Exception as e:
                logger.warning(f"Gemini attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        # Fallback to Claude (text-only, no PDF multimodal)
        logger.info("Gemini failed - falling back to Anthropic Claude (text-only)...")
        for attempt in range(self.config.max_retries):
            try:
                response = await self._call_claude(prompt)
                if response:
                    return response, "claude-sonnet-4-20250514"
            except Exception as e:
                logger.warning(f"Claude attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        # Fallback to Azure OpenAI
        logger.info("Claude failed - falling back to Azure OpenAI...")
        for attempt in range(self.config.max_retries):
            try:
                response = await self._call_azure(prompt)
                if response:
                    # Return actual Azure model name
                    azure_model = self._azure_deployment or self.config.azure_model_name
                    return response, f"azure-openai/{azure_model}"
            except Exception as e:
                logger.warning(f"Azure attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        return None, "unknown"

    # =========================================================================
    # EXTRACTION METHODS
    # =========================================================================

    def _extract_candidate_activities(
        self, usdm_output: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract activities that may require specimen enrichment."""
        candidates = []

        activities = usdm_output.get("activities", [])
        for activity in activities:
            activity_id = activity.get("id", "")
            activity_name = activity.get("name", "")
            domain = activity.get("domain", {})

            if isinstance(domain, dict):
                domain_code = domain.get("code", "")
            else:
                domain_code = str(domain)

            # Include if specimen domain
            if domain_code in SPECIMEN_DOMAINS:
                candidates.append(activity)
                continue

            # Exclude if definitely non-specimen
            if domain_code in NON_SPECIMEN_DOMAINS:
                continue

            # Check by activity name
            if self._pattern_registry.is_non_specimen_activity(activity_name):
                continue

            # Check if activity name suggests specimen
            if infer_specimen_from_activity_name(activity_name):
                candidates.append(activity)
                continue

            # Include activities with specimen-related footnotes
            # (would need footnote data from USDM)

        logger.info(f"Extracted {len(candidates)} candidate activities for specimen enrichment")
        return candidates

    def _find_biospecimen_provenance(self, activity_name: str, specimen_category: str = None) -> dict:
        """
        Find matching provenance from biospecimen_handling data.

        Uses fuzzy matching to connect lab tests (Hematology, Chemistry) with
        specimen types (Plasma, Serum, Whole Blood).

        Returns dict with page_numbers, text_snippets, and section_reference if found.
        """
        provenance = {
            "page_numbers": [],
            "text_snippets": [],
            "section_reference": None,
        }

        if not self._biospecimen_context:
            return provenance

        name_lower = activity_name.lower()

        # Map common lab tests to specimen types for matching
        lab_to_specimen_keywords = {
            "hematology": ["blood", "whole blood", "edta"],
            "cbc": ["blood", "whole blood", "edta"],
            "chemistry": ["serum", "blood"],
            "serum": ["serum"],
            "liver function": ["serum", "blood"],
            "lft": ["serum", "blood"],
            "renal": ["serum", "blood"],
            "coagulation": ["plasma", "citrate", "blood"],
            "coag": ["plasma", "citrate", "blood"],
            "pt": ["plasma", "citrate"],
            "inr": ["plasma", "citrate"],
            "urinalysis": ["urine"],
            "urine": ["urine"],
            "pk": ["plasma", "blood"],
            "pharmacokinetic": ["plasma", "blood"],
            "immunogenicity": ["serum", "blood", "ada"],
            "ada": ["serum", "blood", "ada"],
            "anti-drug": ["serum", "blood", "ada"],
            "pregnancy": ["serum", "blood", "hcg"],
            "hcg": ["serum", "blood", "hcg"],
            "biomarker": ["serum", "plasma", "blood"],
            "pharmacogenomic": ["blood", "dna", "pharmacogenomic"],
            "pgx": ["blood", "dna", "pharmacogenomic"],
            "dna": ["blood", "cfdna", "dna"],
            "genetic": ["blood", "dna"],
            "biopsy": ["tissue", "biopsy", "tumor"],
            "tumor": ["tissue", "biopsy", "tumor"],
        }

        # Find matching keywords for this activity
        matching_keywords = []
        for lab_term, specimen_terms in lab_to_specimen_keywords.items():
            if lab_term in name_lower:
                matching_keywords.extend(specimen_terms)

        # Also add the category if provided
        if specimen_category:
            matching_keywords.append(specimen_category.lower())

        # If no specific keywords, use the activity name itself
        if not matching_keywords:
            matching_keywords = [name_lower]

        # Search discovered_specimen_types for matching specimens
        for spec in self._biospecimen_context.get("discovered_specimen_types", []):
            spec_name = spec.get("specimen_name", "").lower()
            spec_category = spec.get("specimen_category", "").lower()
            spec_purpose = spec.get("purpose", "").lower()

            # Check if any of our keywords match the specimen
            is_match = False
            for keyword in matching_keywords:
                if keyword in spec_name or keyword in spec_category or keyword in spec_purpose:
                    is_match = True
                    break

            # Also check direct name match
            if not is_match:
                if spec_name in name_lower or name_lower in spec_name:
                    is_match = True

            if is_match:
                prov = spec.get("provenance", {})
                if prov:
                    page = prov.get("page_number")
                    if page and page not in provenance["page_numbers"]:
                        provenance["page_numbers"].append(page)
                    snippet = prov.get("text_snippet")
                    if snippet and snippet not in provenance["text_snippets"]:
                        provenance["text_snippets"].append(snippet[:200])  # Truncate
                    section = prov.get("section_number")
                    if section and not provenance["section_reference"]:
                        provenance["section_reference"] = section

        # Also check collection_containers for additional provenance
        for container in self._biospecimen_context.get("collection_containers", []):
            container_name = container.get("container_name", "").lower()
            for keyword in matching_keywords:
                if keyword in container_name:
                    prov = container.get("provenance", {})
                    if prov:
                        page = prov.get("page_number")
                        if page and page not in provenance["page_numbers"]:
                            provenance["page_numbers"].append(page)
                    break

        return provenance

    def _check_activity_components(
        self, activity_name: str
    ) -> Optional[SpecimenDecision]:
        """Check activity_components.json for specimen inference."""
        if not self.config.infer_from_activity_components:
            return None

        name_lower = activity_name.lower().strip()

        # Look for matching panel
        for panel_name, panel_data in self._activity_components.items():
            if panel_name.lower() in name_lower or name_lower in panel_name.lower():
                specimen_type = panel_data.get("specimen_type")
                if specimen_type:
                    # Map specimen_type to category/subtype
                    category = None
                    subtype = None

                    specimen_lower = specimen_type.lower()
                    if "blood" in specimen_lower:
                        category = SpecimenCategory.BLOOD
                        if "whole" in specimen_lower:
                            subtype = SpecimenSubtype.WHOLE_BLOOD
                    elif "serum" in specimen_lower:
                        category = SpecimenCategory.BLOOD
                        subtype = SpecimenSubtype.SERUM
                    elif "plasma" in specimen_lower:
                        category = SpecimenCategory.BLOOD
                        if "citrate" in specimen_lower:
                            subtype = SpecimenSubtype.CITRATE_PLASMA
                        elif "edta" in specimen_lower:
                            subtype = SpecimenSubtype.EDTA_PLASMA
                        else:
                            subtype = SpecimenSubtype.PLASMA
                    elif "urine" in specimen_lower:
                        category = SpecimenCategory.URINE
                        subtype = SpecimenSubtype.URINE_SPOT

                    if category:
                        # Look up provenance from biospecimen_handling
                        prov = self._find_biospecimen_provenance(
                            activity_name,
                            specimen_category=category.value if category else None
                        )
                        decision = SpecimenDecision(
                            activity_id="",  # Will be set later
                            activity_name=activity_name,
                            has_specimen=True,
                            specimen_category=category,
                            specimen_subtype=subtype,
                            purpose=SpecimenPurpose.SAFETY,
                            confidence=0.98,
                            rationale=f"Inferred from activity_components.json: {panel_name} → {specimen_type}",
                            source="config",
                            # Provenance from biospecimen_handling
                            page_numbers=prov.get("page_numbers", []),
                            text_snippets=prov.get("text_snippets", []),
                            section_reference=prov.get("section_reference"),
                        )

                        # Add tube specification if known
                        if subtype == SpecimenSubtype.WHOLE_BLOOD:
                            decision.tube_specification = TubeSpecification(
                                tube_type=TubeType.EDTA,
                                tube_color=TubeColor.LAVENDER,
                                anticoagulant="K2 EDTA",
                            )
                        elif subtype == SpecimenSubtype.SERUM:
                            decision.tube_specification = TubeSpecification(
                                tube_type=TubeType.SST,
                                tube_color=TubeColor.GOLD,
                            )
                        elif subtype == SpecimenSubtype.CITRATE_PLASMA:
                            decision.tube_specification = TubeSpecification(
                                tube_type=TubeType.SODIUM_CITRATE,
                                tube_color=TubeColor.LIGHT_BLUE,
                                anticoagulant="3.2% Sodium Citrate",
                                fill_critical=True,
                            )

                        return decision

        return None

    async def _analyze_batch(
        self, activities: List[Dict[str, Any]], footnotes: List[Dict[str, Any]]
    ) -> Dict[str, SpecimenDecision]:
        """
        Analyze activities in batch using LLM.

        Uses chunking to prevent token limit issues with large activity lists.
        """
        decisions = {}

        if not activities:
            return decisions

        # Chunk activities to prevent token limit issues
        batch_size = self.config.max_batch_size
        total_activities = len(activities)
        total_batches = (total_activities + batch_size - 1) // batch_size

        logger.info(f"Processing {total_activities} activities in {total_batches} batches of up to {batch_size}")

        for batch_idx in range(0, total_activities, batch_size):
            batch_activities = activities[batch_idx:batch_idx + batch_size]
            batch_num = (batch_idx // batch_size) + 1

            logger.debug(f"Processing batch {batch_num}/{total_batches} ({len(batch_activities)} activities)")

            # Build activities JSON for this batch
            activities_json = json.dumps([
                {
                    "id": a.get("id", ""),
                    "name": a.get("name", ""),
                    "domain": a.get("domain", {}).get("code", "") if isinstance(a.get("domain"), dict) else "",
                    "footnoteMarkers": a.get("footnoteMarkers", []),
                }
                for a in batch_activities
            ], indent=2)

            # Build footnotes JSON (shared across batches)
            footnotes_json = json.dumps([
                {
                    "marker": fn.get("marker", ""),
                    "text": fn.get("text", ""),
                }
                for fn in footnotes
            ], indent=2) if footnotes else "[]"

            # Build biospecimen context if available
            biospecimen_json = ""
            if self._biospecimen_context:
                # Include relevant biospecimen data as first-pass context
                bio_context = {
                    "discovered_specimen_types": self._biospecimen_context.get("discovered_specimen_types", [])[:10],
                    "collection_containers": self._biospecimen_context.get("collection_containers", [])[:10],
                    "processing_requirements": self._biospecimen_context.get("processing_requirements", [])[:5],
                    "storage_requirements": self._biospecimen_context.get("storage_requirements", [])[:5],
                }
                biospecimen_json = json.dumps(bio_context, indent=2)

            # Build prompt
            prompt = self._prompt_template.replace(
                "{activities_json}", activities_json
            ).replace(
                "{footnotes_json}", footnotes_json
            ).replace(
                "{activity_count}", str(len(batch_activities))
            ).replace(
                "{biospecimen_json}", biospecimen_json if biospecimen_json else "No biospecimen data available"
            )

            # Call LLM for this batch (with PDF multimodal if available)
            response_text, actual_model = await self._call_llm_with_fallback(
                prompt, self._gemini_file_uri
            )
            if not response_text:
                logger.error(f"All LLM providers failed for batch {batch_num}")
                # Return default decisions for this batch
                for activity in batch_activities:
                    decisions[activity.get("id", "")] = SpecimenDecision(
                        activity_id=activity.get("id", ""),
                        activity_name=activity.get("name", ""),
                        has_specimen=False,
                        confidence=0.0,
                        rationale=f"LLM analysis failed for batch {batch_num}",
                        requires_human_review=True,
                        review_reason="LLM analysis failed",
                        model_name=actual_model,
                    )
                continue

            # Parse response with actual model name used and merge into decisions
            batch_decisions = self._parse_llm_response(response_text, batch_activities, actual_model)
            decisions.update(batch_decisions)

            logger.debug(f"Batch {batch_num} complete: {len(batch_decisions)} decisions parsed")

        return decisions

    def _parse_llm_response(
        self, response_text: str, activities: List[Dict[str, Any]], actual_model: str
    ) -> Dict[str, SpecimenDecision]:
        """Parse LLM JSON response into SpecimenDecision objects."""
        decisions = {}

        # Clean response
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"```json?\s*", "", cleaned)
            cleaned = re.sub(r"```\s*$", "", cleaned)

        try:
            response_data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.debug(f"Response text: {response_text[:500]}...")

            # Return default decisions
            for activity in activities:
                decisions[activity.get("id", "")] = SpecimenDecision(
                    activity_id=activity.get("id", ""),
                    activity_name=activity.get("name", ""),
                    has_specimen=False,
                    confidence=0.0,
                    rationale="Failed to parse LLM response",
                    requires_human_review=True,
                    review_reason=str(e),
                    model_name=actual_model,
                )
            return decisions

        # Parse each activity's decision
        for activity in activities:
            activity_id = activity.get("id", "")
            activity_name = activity.get("name", "")

            if activity_id in response_data:
                decision = SpecimenDecision.from_llm_response(
                    activity_id,
                    activity_name,
                    response_data[activity_id],
                    actual_model,  # Use actual model, not config default
                )
                decisions[activity_id] = decision
            else:
                # Activity not in response
                decisions[activity_id] = SpecimenDecision(
                    activity_id=activity_id,
                    activity_name=activity_name,
                    has_specimen=False,
                    confidence=0.5,
                    rationale="Not returned in LLM response",
                    model_name=actual_model,
                )

        return decisions

    # =========================================================================
    # CODE OBJECT METHODS
    # =========================================================================

    def _create_specimen_code(
        self, category: SpecimenCategory, subtype: Optional[SpecimenSubtype] = None
    ) -> Dict[str, Any]:
        """Create USDM 4.0 Code object for specimen type using validated Athena codes."""
        # Map enum values to Athena lookup keys
        specimen_key = subtype.value if subtype else category.value
        concept = self._athena.get_specimen_code(specimen_key)

        if concept:
            code_obj = concept.to_usdm_code()
            code_obj["id"] = f"CODE-SPEC-{uuid.uuid4().hex[:12].upper()}"
            return code_obj
        else:
            # Fallback: search by name in Athena
            search_name = specimen_key.replace("_", " ").title()
            results = self._athena.search_by_name(search_name, exact=False, limit=1)
            if results:
                code_obj = results[0].to_usdm_code()
                code_obj["id"] = f"CODE-SPEC-{uuid.uuid4().hex[:12].upper()}"
                return code_obj

            # Last resort: return with empty code (will need manual review)
            logger.warning(f"No Athena code found for specimen: {specimen_key}")
            return {
                "id": f"CODE-SPEC-{uuid.uuid4().hex[:12].upper()}",
                "code": "",
                "decode": search_name,
                "codeSystem": NCI_EVS_CODE_SYSTEM,
                "codeSystemVersion": NCI_EVS_VERSION,
                "instanceType": "Code",
            }

    def _create_tube_code(self, tube_type: TubeType) -> Dict[str, Any]:
        """Create USDM 4.0 Code object for tube type using validated Athena codes."""
        # Map TubeType enum to Athena tube keys
        tube_mapping = {
            TubeType.EDTA: "edta_tube",
            TubeType.SST: "serum_tube",
            TubeType.LITHIUM_HEPARIN: "lithium_heparin",
            TubeType.SODIUM_CITRATE: "sodium_citrate",
            TubeType.PAXGENE: "paxgene",
            TubeType.PLAIN: "whole_blood_tube",
        }

        athena_key = tube_mapping.get(tube_type, f"{tube_type.value}_tube")
        concept = self._athena.get_tube_code(athena_key)

        if concept:
            code_obj = concept.to_usdm_code()
            code_obj["id"] = f"CODE-TUBE-{uuid.uuid4().hex[:12].upper()}"
            return code_obj
        else:
            # Fallback: search by tube type name
            search_name = tube_type.value.replace("_", " ").upper() + " Tube"
            results = self._athena.search_by_name(search_name, exact=False, limit=1)
            if results:
                code_obj = results[0].to_usdm_code()
                code_obj["id"] = f"CODE-TUBE-{uuid.uuid4().hex[:12].upper()}"
                return code_obj

            logger.warning(f"No Athena code found for tube type: {tube_type.value}")
            return {
                "id": f"CODE-TUBE-{uuid.uuid4().hex[:12].upper()}",
                "code": "",
                "decode": tube_type.value.replace("_", " ").upper(),
                "codeSystem": NCI_EVS_CODE_SYSTEM,
                "codeSystemVersion": NCI_EVS_VERSION,
                "instanceType": "Code",
            }

    def _create_purpose_code(self, purpose: SpecimenPurpose) -> Dict[str, Any]:
        """Create USDM 4.0 Code object for specimen purpose using validated Athena codes."""
        # Map SpecimenPurpose enum to Athena purpose keys
        purpose_mapping = {
            SpecimenPurpose.PK: "pharmacokinetic",
            SpecimenPurpose.PD: "pharmacokinetic",  # PD not separate in Athena
            SpecimenPurpose.BIOMARKER: "biomarker",
            SpecimenPurpose.SAFETY: "safety",
            SpecimenPurpose.EFFICACY: "efficacy",
            SpecimenPurpose.EXPLORATORY: "exploratory",
            SpecimenPurpose.GENETIC: "biomarker",  # Genetic is a type of biomarker
            SpecimenPurpose.IMMUNOGENICITY: "safety",  # Immunogenicity is safety-related
        }

        athena_key = purpose_mapping.get(purpose, purpose.value)
        concept = self._athena.get_purpose_code(athena_key)

        if concept:
            code_obj = concept.to_usdm_code()
            code_obj["id"] = f"CODE-PURP-{uuid.uuid4().hex[:12].upper()}"
            return code_obj
        else:
            logger.warning(f"No Athena code found for purpose: {purpose.value}")
            return {
                "id": f"CODE-PURP-{uuid.uuid4().hex[:12].upper()}",
                "code": "",
                "decode": purpose.value.replace("_", " ").title(),
                "codeSystem": NCI_EVS_CODE_SYSTEM,
                "codeSystemVersion": NCI_EVS_VERSION,
                "instanceType": "Code",
            }

    # =========================================================================
    # ENRICHMENT GENERATION
    # =========================================================================

    def _generate_enrichment(
        self, decision: SpecimenDecision
    ) -> Optional[SpecimenEnrichment]:
        """Generate SpecimenEnrichment from decision."""
        if not decision.has_specimen:
            return None

        enrichment_id = generate_specimen_collection_id(decision.activity_id)

        # Build specimenCollection object
        specimen_collection = {
            "id": enrichment_id,
            "instanceType": "SpecimenCollection",
        }

        # Add specimen type Code object
        if decision.specimen_category:
            specimen_collection["specimenType"] = self._create_specimen_code(
                decision.specimen_category, decision.specimen_subtype
            )

        # Add purpose Code object
        if decision.purpose:
            specimen_collection["purpose"] = self._create_purpose_code(decision.purpose)

        # Add collection volume
        if decision.volumes:
            # Use first volume as primary
            primary_vol = decision.volumes[0]
            specimen_collection["collectionVolume"] = {
                "value": primary_vol.value,
                "unit": primary_vol.unit,
            }

            # If multiple volumes (visit-dependent), add to array
            if len(decision.volumes) > 1:
                specimen_collection["visitDependentVolumes"] = [
                    v.to_dict() for v in decision.volumes
                ]

        # Add collection container (tube)
        if decision.tube_specification and decision.tube_specification.tube_type:
            specimen_collection["collectionContainer"] = self._create_tube_code(
                decision.tube_specification.tube_type
            )

            # Add fill volume if specified
            if decision.tube_specification.fill_volume:
                specimen_collection["fillVolume"] = decision.tube_specification.fill_volume.to_dict()

        # Add fasting requirement
        if decision.fasting_required is not None:
            specimen_collection["fastingRequired"] = decision.fasting_required
            if decision.fasting_duration:
                specimen_collection["fastingDuration"] = decision.fasting_duration

        # Add processing requirements
        if decision.processing:
            specimen_collection["processingRequirements"] = [
                p.to_dict() for p in decision.processing
            ]

        # Add storage requirements
        if decision.storage:
            specimen_collection["storageRequirements"] = [
                s.to_dict() for s in decision.storage
            ]

        # Add shipping requirements
        if decision.shipping:
            specimen_collection["shippingRequirements"] = decision.shipping.to_dict()

        # Add provenance
        specimen_collection["_specimenEnrichment"] = SpecimenProvenance(
            activity_id=decision.activity_id,
            activity_name=decision.activity_name,
            specimen_category=decision.specimen_category.value if decision.specimen_category else None,
            model=decision.model_name,
            timestamp=datetime.utcnow().isoformat() + "Z",
            source=decision.source,
            cache_hit=decision.source == "cache",
            confidence=decision.confidence,
            rationale=decision.rationale,
            footnote_markers=decision.footnote_markers,
            page_numbers=decision.page_numbers,
        ).to_dict()

        # Build biospecimenRequirements object (for Activity)
        biospecimen_requirements = {
            "specimenType": specimen_collection.get("specimenType"),
            "collectionContainer": specimen_collection.get("collectionContainer"),
            "purpose": specimen_collection.get("purpose"),
        }

        # Create conditions for optional specimens
        conditions_created = []
        if decision.is_optional and self.config.create_conditions_for_optional:
            condition_id = generate_condition_id(decision.activity_id, "optional")
            condition = {
                "id": condition_id,
                "instanceType": "Condition",
                "name": f"Optional specimen: {decision.activity_name}",
                "text": decision.condition_text or "Optional specimen collection",
                "_specimenEnrichment": {
                    "stage": "Stage5SpecimenEnrichment",
                    "sourceActivityId": decision.activity_id,
                    "conditionType": "optional",
                },
            }
            conditions_created.append(condition)

        return SpecimenEnrichment(
            id=enrichment_id,
            activity_id=decision.activity_id,
            activity_name=decision.activity_name,
            specimen_collection=specimen_collection,
            biospecimen_requirements=biospecimen_requirements,
            conditions_created=conditions_created,
            decision=decision,
            confidence=decision.confidence,
            requires_review=decision.requires_human_review,
            review_reason=decision.review_reason,
        )

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    async def enrich_specimens(
        self,
        usdm_output: Dict[str, Any],
        extraction_outputs: Optional[Dict[str, Dict]] = None,
        gemini_file_uri: Optional[str] = None,
    ) -> Stage5Result:
        """
        Main entry point: Enrich activities with specimen data.

        Args:
            usdm_output: USDM output from previous stages
            extraction_outputs: Optional extraction outputs from main pipeline
                               (includes biospecimen_handling with provenance)
            gemini_file_uri: Optional Gemini file URI for PDF validation

        Returns:
            Stage5Result with enrichments, decisions, and metrics
        """
        result = Stage5Result()

        # Store for use in LLM calls
        self._extraction_outputs = extraction_outputs or {}
        self._gemini_file_uri = gemini_file_uri

        # Extract biospecimen_handling context if available
        self._biospecimen_context = self._extraction_outputs.get("biospecimen_handling", {})

        # Extract candidate activities
        activities = self._extract_candidate_activities(usdm_output)
        result.activities_analyzed = len(activities)

        if not activities:
            logger.info("No candidate activities for specimen enrichment")
            return result

        # Collect footnotes from USDM
        footnotes = usdm_output.get("footnotes", [])

        # Process each activity
        uncached_activities = []

        for activity in activities:
            activity_id = activity.get("id", "")
            activity_name = activity.get("name", "")

            # Check activity_components.json first (high confidence)
            config_decision = self._check_activity_components(activity_name)
            if config_decision:
                config_decision.activity_id = activity_id
                result.decisions[activity_id] = config_decision
                result.inferred_from_config += 1
                result.cache_hits += 1

                # Generate enrichment
                enrichment = self._generate_enrichment(config_decision)
                if enrichment:
                    result.add_enrichment(enrichment)
                    result.activities_with_specimens += 1
                continue

            # Check cache
            cached_decision = self._check_cache(activity_name)
            if cached_decision:
                cached_decision.activity_id = activity_id
                result.decisions[activity_id] = cached_decision
                result.cache_hits += 1

                # Generate enrichment
                enrichment = self._generate_enrichment(cached_decision)
                if enrichment:
                    result.add_enrichment(enrichment)
                    result.activities_with_specimens += 1
                continue

            # Add to uncached list for LLM analysis
            uncached_activities.append(activity)
            result.cache_misses += 1

        # LLM batch analysis for uncached activities
        if uncached_activities:
            logger.info(f"Analyzing {len(uncached_activities)} uncached activities with LLM")
            result.llm_calls += 1
            result.analyzed_by_llm = len(uncached_activities)

            try:
                llm_decisions = await self._analyze_batch(uncached_activities, footnotes)

                for activity_id, decision in llm_decisions.items():
                    result.decisions[activity_id] = decision

                    # Cache the decision
                    self._update_cache(decision.activity_name, decision)

                    # Validate against patterns
                    if self.config.validate_against_patterns:
                        discrepancies = self._pattern_registry.validate_decision(decision)
                        result.discrepancies.extend(discrepancies)
                        result.validation_discrepancies += len(discrepancies)

                    # Generate enrichment
                    if decision.has_specimen:
                        enrichment = self._generate_enrichment(decision)
                        if enrichment:
                            result.add_enrichment(enrichment)
                            result.activities_with_specimens += 1

                            # Track complexity metrics
                            if len(decision.volumes) > 1:
                                result.visit_dependent_volumes += 1
                            if decision.is_optional:
                                result.conditional_specimens += 1
                            if decision.processing:
                                result.with_processing += 1
                            if decision.storage:
                                result.with_storage += 1
                            if decision.shipping:
                                result.with_shipping += 1

                    # Create review items for low confidence
                    if decision.requires_human_review or decision.confidence < self.config.confidence_threshold_review:
                        result.review_items.append(HumanReviewItem(
                            id=generate_review_id(),
                            item_type="specimen",
                            activity_id=decision.activity_id,
                            activity_name=decision.activity_name,
                            title=f"Review specimen for: {decision.activity_name}",
                            description=f"Confidence: {decision.confidence:.2f}. {decision.rationale or ''}",
                            reason=decision.review_reason or "Low confidence",
                            priority="high" if decision.confidence < 0.50 else "medium",
                            confidence=decision.confidence,
                            proposed_resolution=decision.to_dict(),
                        ))

            except Exception as e:
                logger.error(f"LLM analysis failed: {e}")
                # Mark all uncached as needing review
                for activity in uncached_activities:
                    result.decisions[activity.get("id", "")] = SpecimenDecision(
                        activity_id=activity.get("id", ""),
                        activity_name=activity.get("name", ""),
                        has_specimen=False,
                        confidence=0.0,
                        rationale=f"LLM analysis failed: {e}",
                        requires_human_review=True,
                        review_reason=str(e),
                    )
                    result.needs_review += 1

        # Save cache
        self._save_cache()

        logger.info(
            f"Stage 5 complete: {result.specimens_enriched} specimens enriched, "
            f"{result.cache_hits} cache hits, {result.analyzed_by_llm} LLM analyzed, "
            f"{result.needs_review} need review"
        )

        return result

    def apply_enrichments_to_usdm(
        self, usdm_output: Dict[str, Any], result: Stage5Result
    ) -> Dict[str, Any]:
        """
        Apply enrichments to USDM output.

        Adds specimenCollection to SAIs and biospecimenRequirements to Activities.
        """
        if not result.enrichments:
            return usdm_output

        # Create lookup by activity_id
        enrichment_by_activity = {e.activity_id: e for e in result.enrichments}

        # Update activities
        activities = usdm_output.get("activities", [])
        for activity in activities:
            activity_id = activity.get("id", "")
            if activity_id in enrichment_by_activity:
                enrichment = enrichment_by_activity[activity_id]
                activity["biospecimenRequirements"] = enrichment.biospecimen_requirements
                result.sais_updated += 1

        # Update SAIs (ScheduledActivityInstances)
        sais = usdm_output.get("scheduledActivityInstances", [])
        for sai in sais:
            activity_id = sai.get("activityId", "")
            if activity_id in enrichment_by_activity:
                enrichment = enrichment_by_activity[activity_id]
                sai["specimenCollection"] = enrichment.specimen_collection

        # Add conditions
        conditions = usdm_output.get("conditions", [])
        for enrichment in result.enrichments:
            conditions.extend(enrichment.conditions_created)

        usdm_output["conditions"] = conditions

        return usdm_output


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def enrich_specimens(
    usdm_output: Dict[str, Any],
    config: Optional[SpecimenEnrichmentConfig] = None,
) -> Tuple[Dict[str, Any], Stage5Result]:
    """
    Convenience function to run specimen enrichment.

    Args:
        usdm_output: USDM output from previous stages
        config: Optional configuration

    Returns:
        Tuple of (updated USDM output, Stage5Result)
    """
    enricher = SpecimenEnricher(config=config)
    result = await enricher.enrich_specimens(usdm_output)
    updated_output = enricher.apply_enrichments_to_usdm(usdm_output, result)
    return updated_output, result
