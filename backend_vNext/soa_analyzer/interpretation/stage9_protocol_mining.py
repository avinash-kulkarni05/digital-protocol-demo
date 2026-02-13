"""
Stage 9: Protocol Mining

Cross-reference non-SOA protocol sections (18 extraction modules) to enrich SOA activities
with laboratory specifications, PK/PD parameters, safety requirements, biospecimen details,
endpoint linkages, oncology imaging/tumor assessments, and dose modification rules.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

from ..models.protocol_mining import (
    BiospecimenEnrichment,
    DoseModificationEnrichment,
    EndpointEnrichment,
    EnrichmentType,
    ImagingEnrichment,
    LabManualEnrichment,
    MatchConfidence,
    MiningDecision,
    MiningEnrichment,
    MiningProvenance,
    PKPDEnrichment,
    SafetyEnrichment,
    SourceModule,
    Stage9Config,
    Stage9Result,
)

logger = logging.getLogger(__name__)


class ModuleMappingRegistry:
    """Loads and manages module mappings from config files"""

    def __init__(self, config_dir: Optional[Path] = None):
        self._config_dir = config_dir or Path(__file__).parent.parent / "config"
        self._domain_mappings: Dict[str, List[str]] = {}
        self._keyword_hints: Dict[str, List[str]] = {}
        self._therapeutic_area_modules: Dict[str, List[str]] = {}
        self._module_weights: Dict[str, float] = {}
        self._enrichment_fields: Dict[str, Dict[str, Any]] = {}
        self._keyword_index: Dict[str, List[str]] = {}  # Inverted index for O(1) lookup
        self._load_configs()

    def _load_configs(self) -> None:
        """Load configuration files"""
        # Load section_activity_mappings.json
        mappings_file = self._config_dir / "section_activity_mappings.json"
        if mappings_file.exists():
            with open(mappings_file, "r") as f:
                data = json.load(f)
                self._domain_mappings = data.get("domain_module_mappings", {})
                self._keyword_hints = data.get("activity_keyword_hints", {})
                self._therapeutic_area_modules = data.get("therapeutic_area_modules", {})
                self._module_weights = data.get("module_priority_weights", {})
                self._build_keyword_index()
        else:
            logger.warning(f"Config file not found: {mappings_file}")

        # Load enrichment_fields.json
        fields_file = self._config_dir / "enrichment_fields.json"
        if fields_file.exists():
            with open(fields_file, "r") as f:
                data = json.load(f)
                # Filter out metadata
                self._enrichment_fields = {
                    k: v for k, v in data.items() if not k.startswith("_")
                }
        else:
            logger.warning(f"Config file not found: {fields_file}")

    def _build_keyword_index(self) -> None:
        """Build inverted index for O(1) keyword lookup"""
        self._keyword_index = {}
        for keyword, modules in self._keyword_hints.items():
            # Index by lowercase keyword
            self._keyword_index[keyword.lower()] = modules
            # Also index individual words for partial matching
            for word in keyword.lower().split():
                if word not in self._keyword_index:
                    self._keyword_index[word] = []
                self._keyword_index[word].extend(modules)

    def get_candidate_modules(
        self, domain: Optional[str], activity_name: str
    ) -> List[str]:
        """Get candidate modules based on domain and activity name"""
        candidates = set()

        # Add domain-based modules
        if domain and domain in self._domain_mappings:
            candidates.update(self._domain_mappings[domain])

        # Add keyword-based modules using index
        activity_lower = activity_name.lower()

        # Check exact keyword match first
        if activity_lower in self._keyword_index:
            candidates.update(self._keyword_index[activity_lower])

        # Check for keyword substrings in activity name
        for keyword, modules in self._keyword_hints.items():
            if keyword.lower() in activity_lower:
                candidates.update(modules)

        return list(candidates)

    def get_enrichment_fields(self, module: str) -> Dict[str, Any]:
        """Get enrichment field definitions for a module"""
        return self._enrichment_fields.get(module, {})

    def get_module_weight(self, module: str) -> float:
        """Get priority weight for a module"""
        return self._module_weights.get(module, 0.5)

    def get_all_modules(self) -> List[str]:
        """Get list of all available modules"""
        return list(self._enrichment_fields.keys())


class ProtocolMiner:
    """Main Stage 9 handler for protocol mining"""

    def __init__(self, config: Optional[Stage9Config] = None):
        self.config = config or Stage9Config()
        self._registry = ModuleMappingRegistry()
        self._cache: Dict[str, MiningDecision] = {}
        self._prompt_template: str = ""
        self._gemini_client = None
        self._claude_client = None
        self._azure_client = None
        self._gemini_file_uri: Optional[str] = None  # Set per-call in mine_protocol()
        self._load_resources()

    def _load_resources(self) -> None:
        """Load prompt template and initialize clients"""
        # Load prompt template
        prompt_file = Path(__file__).parent.parent / "prompts" / "protocol_mining.txt"
        if prompt_file.exists():
            with open(prompt_file, "r") as f:
                self._prompt_template = f.read()
        else:
            logger.warning(f"Prompt file not found: {prompt_file}")

        # Load cache if exists
        if self.config.use_cache:
            self._load_cache()

        # Initialize LLM clients lazily
        self._init_llm_clients()

    def _init_llm_clients(self) -> None:
        """Initialize LLM clients"""
        try:
            import google.generativeai as genai

            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
                self._gemini_client = genai.GenerativeModel(self.config.model_name)
                logger.info(f"Initialized Gemini client: {self.config.model_name}")
        except Exception as e:
            logger.warning(f"Failed to initialize Gemini client: {e}")

        try:
            from openai import AzureOpenAI

            azure_key = os.getenv("AZURE_OPENAI_API_KEY")
            azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            if azure_key and azure_endpoint:
                self._azure_client = AzureOpenAI(
                    api_key=azure_key,
                    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
                    azure_endpoint=azure_endpoint,
                )
                logger.info("Initialized Azure OpenAI client")
        except Exception as e:
            logger.warning(f"Failed to initialize Azure client: {e}")

        # Initialize Claude client
        try:
            import anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                self._claude_client = anthropic.Anthropic(api_key=api_key)
                logger.info("Initialized Anthropic Claude client")
        except Exception as e:
            logger.warning(f"Failed to initialize Anthropic client: {e}")

    # ============ MAIN ENTRY POINT ============

    async def mine_protocol(
        self,
        usdm_output: Dict[str, Any],
        extraction_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
        gemini_file_uri: Optional[str] = None,
    ) -> Stage9Result:
        """
        Main entry point for protocol mining.

        Args:
            usdm_output: USDM output from Stage 8
            extraction_outputs: Dict of module_name -> extraction JSON (optional)
            gemini_file_uri: Gemini File API URI for PDF validation (optional)

        Returns:
            Stage9Result with enrichments and metrics
        """
        self._gemini_file_uri = gemini_file_uri
        start_time = time.time()
        result = Stage9Result()

        # Handle missing extraction_outputs gracefully
        if extraction_outputs is None:
            logger.warning("No extraction_outputs provided - Stage 9 returning empty result")
            result.errors.append("extraction_outputs not provided - protocol mining skipped")
            result.processing_time_seconds = time.time() - start_time
            return result

        try:
            # Phase 1: Extract activities
            activities = self._extract_activities(usdm_output)
            result.total_activities_processed = len(activities)
            logger.info(f"Extracted {len(activities)} activities for mining")

            if not activities:
                logger.warning("No activities found to mine")
                return result

            # Get available modules from extraction outputs
            available_modules = list(extraction_outputs.keys())
            logger.info(f"Available modules: {available_modules}")

            # Phase 2: Match activities to modules
            decisions = await self._match_activities(
                activities, available_modules, extraction_outputs
            )
            result.decisions = decisions
            result.cache_hits = sum(1 for d in decisions.values() if d.source == "cache")
            result.llm_calls = sum(1 for d in decisions.values() if d.source == "llm")

            # Phase 2.5: PDF Validation for low-confidence matches (0.70-0.89)
            if self._gemini_file_uri:
                pdf_validations = 0
                for activity in activities:
                    activity_id = activity.get("id", "")
                    decision = decisions.get(activity_id)
                    if decision and 0.70 <= decision.confidence < 0.90:
                        validated_decision = await self._validate_with_pdf(activity, decision)
                        decisions[activity_id] = validated_decision
                        pdf_validations += 1
                if pdf_validations > 0:
                    logger.info(f"PDF validation completed for {pdf_validations} low-confidence matches")
                    result.pdf_validations = pdf_validations

            # Phase 3: Extract enrichments
            for activity in activities:
                activity_id = activity.get("id", "")
                decision = decisions.get(activity_id)

                if not decision or not decision.matched_modules:
                    result.activities_no_match += 1
                    continue

                enrichment = self._extract_enrichment(
                    activity, decision, extraction_outputs
                )

                if enrichment:
                    result.enrichments.append(enrichment)
                    result.activities_enriched += 1

                    # Track modules used
                    for module in decision.matched_modules:
                        result.modules_used[module] = result.modules_used.get(module, 0) + 1

                    # Track review items
                    if enrichment.requires_human_review:
                        result.review_items.append({
                            "activityId": activity_id,
                            "activityName": activity.get("activityName", ""),
                            "confidence": enrichment.overall_confidence,
                            "reason": "Low confidence match"
                        })

            # Calculate average confidence
            if result.enrichments:
                total_confidence = sum(e.overall_confidence for e in result.enrichments)
                result.avg_confidence = total_confidence / len(result.enrichments)

            # Save cache
            if self.config.use_cache:
                self._save_cache()

        except Exception as e:
            logger.error(f"Error in protocol mining: {e}", exc_info=True)
            result.errors.append(str(e))

        result.processing_time_seconds = time.time() - start_time
        logger.info(f"Protocol mining completed: {result.get_summary()}")

        return result

    # ============ PHASE 1: ACTIVITY EXTRACTION ============

    def _extract_activities(self, usdm_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract scheduledActivityInstances with domain info"""
        activities = []

        # Get scheduled activity instances
        sais = usdm_output.get("scheduledActivityInstances", [])

        # Also check nested structures
        if not sais:
            schedule = usdm_output.get("schedule", {})
            sais = schedule.get("scheduledActivityInstances", [])

        for sai in sais:
            # Skip activities already enriched by Stage 2 (protocol-driven expansion)
            if self._is_already_enriched_by_stage2(sai):
                logger.debug(f"Skipping activity '{sai.get('activityName', sai.get('name', ''))}' - already enriched by Stage 2")
                continue

            activity = {
                "id": sai.get("id", ""),
                "activityId": sai.get("activityId", ""),
                "activityName": sai.get("activityName", sai.get("name", "")),
                "encounterId": sai.get("encounterId", ""),
                "domain": self._extract_domain(sai),
                "footnoteMarkers": sai.get("footnoteMarkers", []),
                "timingModifier": sai.get("timingModifier"),
                "isRequired": sai.get("isRequired", True),
            }
            activities.append(activity)

        return activities

    def _is_already_enriched_by_stage2(self, sai: Dict[str, Any]) -> bool:
        """
        Check if activity has Stage 2 expansion with protocol extraction data.

        Stage 2 (Activity Expansion) now uses protocol-driven expansion, which
        already cross-references extraction modules (lab_specs, biospecimen, etc.).
        We skip these activities in Stage 9 to avoid duplicate enrichment.

        Returns:
            True if activity was expanded by Stage 2 with extraction data
        """
        # Check for expansion metadata from Stage 2
        expansion = sai.get("_expansion", {})
        if expansion:
            # Stage 2 v2.0 sets source to "protocol_extraction"
            if expansion.get("source") == "protocol_extraction":
                return True
            # Check component count - if expanded, it has components
            if expansion.get("componentCount", 0) > 0:
                return True

        # Check for explicit flag (alternative marker)
        if sai.get("_enriched_by_stage2", False):
            return True

        return False

    def _extract_domain(self, sai: Dict[str, Any]) -> Optional[str]:
        """Extract CDISC domain from activity"""
        # Check domain code object
        domain_code = sai.get("domainCode", {})
        if isinstance(domain_code, dict):
            return domain_code.get("code") or domain_code.get("decode")

        # Check direct domain field
        return sai.get("domain")

    # ============ PHASE 2: ACTIVITY MATCHING ============

    async def _match_activities(
        self,
        activities: List[Dict[str, Any]],
        available_modules: List[str],
        extraction_outputs: Dict[str, Dict[str, Any]],
    ) -> Dict[str, MiningDecision]:
        """Match activities to modules using cache and LLM"""
        decisions = {}
        uncached_activities = []

        # Check cache first
        for activity in activities:
            cached = self._check_cache(activity)
            if cached:
                decisions[activity["id"]] = cached
                logger.debug(f"Cache hit for activity: {activity['activityName']}")
            else:
                uncached_activities.append(activity)

        # Process uncached activities in batches
        if uncached_activities:
            logger.info(f"Processing {len(uncached_activities)} uncached activities")

            # Generate module summaries for LLM
            module_summaries = self._generate_module_summaries(extraction_outputs)

            # Process in batches
            for i in range(0, len(uncached_activities), self.config.batch_size):
                batch = uncached_activities[i:i + self.config.batch_size]
                batch_decisions = await self._match_activities_batch(
                    batch, available_modules, module_summaries
                )
                decisions.update(batch_decisions)

                # Update cache
                for decision in batch_decisions.values():
                    self._update_cache(decision.cache_key, decision)

        return decisions

    def _check_cache(self, activity: Dict[str, Any]) -> Optional[MiningDecision]:
        """Check cache for existing decision"""
        if not self.config.use_cache:
            return None

        cache_key = self._generate_cache_key(activity)
        cached = self._cache.get(cache_key)

        if cached:
            cached.source = "cache"
            return cached

        return None

    def _generate_cache_key(self, activity: Dict[str, Any]) -> str:
        """Generate cache key from activity"""
        activity_id = activity.get("id", "")
        activity_name = activity.get("activityName", "")
        model = self.config.model_name
        key_str = f"{activity_id}:{activity_name}:{model}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _generate_module_summaries(
        self, extraction_outputs: Dict[str, Dict[str, Any]]
    ) -> Dict[str, str]:
        """Generate summaries of module data for LLM prompt"""
        summaries = {}

        for module_name, data in extraction_outputs.items():
            if not data:
                continue

            summary_parts = []
            fields_config = self._registry.get_enrichment_fields(module_name)
            target_fields = fields_config.get("target_fields", [])

            # Extract key field values for summary
            for field_path in target_fields[:5]:  # Limit to first 5 fields
                value = self._get_nested_value(data, field_path)
                if value:
                    if isinstance(value, list) and len(value) > 3:
                        value = value[:3] + ["..."]
                    summary_parts.append(f"- {field_path}: {value}")

            if summary_parts:
                summaries[module_name] = "\n".join(summary_parts)
            else:
                summaries[module_name] = "No extractable data available"

        return summaries

    def _get_nested_value(self, data: Dict, field_path: str) -> Any:
        """Get nested value from dict using dot notation with array support"""
        parts = field_path.replace("[]", "[0]").split(".")
        current = data

        for part in parts:
            if current is None:
                return None

            # Handle array index
            match = re.match(r"(\w+)\[(\d+)\]", part)
            if match:
                key, idx = match.groups()
                if isinstance(current, dict) and key in current:
                    arr = current[key]
                    if isinstance(arr, list) and len(arr) > int(idx):
                        current = arr[int(idx)]
                    else:
                        return None
                else:
                    return None
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                return None

        return current

    async def _match_activities_batch(
        self,
        activities: List[Dict[str, Any]],
        available_modules: List[str],
        module_summaries: Dict[str, str],
    ) -> Dict[str, MiningDecision]:
        """Batch LLM call to match activities to modules"""
        # Prepare activities JSON
        activities_json = json.dumps([
            {
                "activity_id": a["id"],
                "activity_name": a["activityName"],
                "domain": a.get("domain"),
                "footnotes": a.get("footnoteMarkers", [])
            }
            for a in activities
        ], indent=2)

        # Format module summaries
        summaries_text = "\n\n".join([
            f"### {module}\n{summary}"
            for module, summary in module_summaries.items()
        ])

        # Build prompt
        prompt = self._prompt_template.format(
            available_modules=", ".join(available_modules),
            activities_json=activities_json,
            module_summaries=summaries_text
        )

        # Call LLM with fallback
        response_text, model_used = await self._call_llm_with_fallback(prompt)

        # Parse response
        return self._parse_match_response(response_text, activities, model_used)

    async def _call_llm_with_fallback(self, prompt: str) -> Tuple[str, str]:
        """Call LLM with Gemini → Claude → Azure fallback"""
        last_error = None

        # Try Gemini first
        if self._gemini_client:
            for attempt in range(self.config.max_retries):
                try:
                    response = self._gemini_client.generate_content(
                        prompt,
                        generation_config={
                            "temperature": self.config.temperature,
                            "max_output_tokens": self.config.max_output_tokens,
                        }
                    )
                    return response.text, self.config.model_name
                except Exception as e:
                    last_error = e
                    logger.warning(f"Gemini attempt {attempt + 1} failed: {e}")
                    await asyncio.sleep(self.config.retry_delay_seconds * (attempt + 1))

        # Fallback to Claude
        logger.info("Gemini failed - falling back to Anthropic Claude...")
        if self._claude_client:
            for attempt in range(self.config.max_retries):
                try:
                    response = self._claude_client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=self.config.max_output_tokens,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    content = response.content[0].text if response.content else None
                    if content:
                        logger.info(f"Anthropic Claude responded ({len(content)} chars)")
                        return content, "claude-sonnet-4-20250514"
                except Exception as e:
                    last_error = e
                    logger.warning(f"Claude attempt {attempt + 1} failed: {e}")
                    await asyncio.sleep(self.config.retry_delay_seconds * (attempt + 1))

        # Fallback to Azure
        logger.info("Claude failed - falling back to Azure OpenAI...")
        if self._azure_client:
            for attempt in range(self.config.max_retries):
                try:
                    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
                    response = self._azure_client.chat.completions.create(
                        model=deployment,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=self.config.temperature,
                        max_tokens=min(self.config.max_output_tokens, 16384),
                    )
                    return response.choices[0].message.content, self.config.fallback_model
                except Exception as e:
                    last_error = e
                    logger.warning(f"Azure attempt {attempt + 1} failed: {e}")
                    await asyncio.sleep(self.config.retry_delay_seconds * (attempt + 1))

        raise RuntimeError(f"All LLM calls failed. Last error: {last_error}")

    def _parse_match_response(
        self,
        response_text: str,
        activities: List[Dict[str, Any]],
        model_used: str,
    ) -> Dict[str, MiningDecision]:
        """Parse LLM response into MiningDecision objects"""
        decisions = {}

        try:
            # Clean response text
            response_text = response_text.strip()
            if response_text.startswith("```"):
                response_text = re.sub(r"^```\w*\n?", "", response_text)
                response_text = re.sub(r"\n?```$", "", response_text)

            response_data = json.loads(response_text)
            matches = response_data.get("matches", [])

            # Create activity lookup
            activity_lookup = {a["id"]: a for a in activities}

            for match in matches:
                activity_id = match.get("activity_id", "")
                activity = activity_lookup.get(activity_id)

                if not activity:
                    continue

                decision = MiningDecision.from_llm_response(
                    match, activity, model_used
                )
                decisions[activity_id] = decision

            # Create decisions for any missing activities
            for activity in activities:
                if activity["id"] not in decisions:
                    decisions[activity["id"]] = MiningDecision(
                        activity_id=activity["id"],
                        activity_name=activity.get("activityName", ""),
                        domain=activity.get("domain"),
                        matched_modules=[],
                        confidence=0.0,
                        source="llm",
                        requires_human_review=True,
                        model_used=model_used
                    )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            # Create review-needed decisions for all activities
            for activity in activities:
                decisions[activity["id"]] = MiningDecision(
                    activity_id=activity["id"],
                    activity_name=activity.get("activityName", ""),
                    domain=activity.get("domain"),
                    matched_modules=[],
                    confidence=0.0,
                    source="llm",
                    requires_human_review=True,
                    model_used=model_used
                )

        return decisions

    # ============ PHASE 2.5: PDF VALIDATION FOR LOW-CONFIDENCE MATCHES ============

    async def _validate_with_pdf(
        self,
        activity: Dict[str, Any],
        decision: MiningDecision,
    ) -> MiningDecision:
        """
        Use Gemini File API to validate low-confidence matches against PDF.

        For matches with confidence 0.70-0.89, search PDF for additional evidence
        to either improve confidence or flag for human review.

        Args:
            activity: Activity dict with name, domain, footnotes
            decision: Current MiningDecision with matched_modules and confidence

        Returns:
            Updated MiningDecision with improved confidence and PDF evidence
        """
        if not self._gemini_file_uri:
            logger.debug("No gemini_file_uri available for PDF validation")
            return decision

        # Only validate low-confidence matches (0.70-0.89)
        if decision.confidence >= 0.90 or decision.confidence < 0.70:
            return decision

        if not self._gemini_client:
            logger.warning("Gemini client not available for PDF validation")
            return decision

        activity_name = activity.get("activityName", "")
        domain = activity.get("domain", "")
        footnotes = activity.get("footnoteMarkers", [])

        try:
            # Build PDF search prompt
            prompt = f"""Search this clinical trial protocol PDF for information about the activity "{activity_name}".

Activity Details:
- Name: {activity_name}
- CDISC Domain: {domain or 'Unknown'}
- Footnote markers: {', '.join(footnotes) if footnotes else 'None'}
- Currently matched modules: {', '.join(decision.matched_modules)}
- Current confidence: {decision.confidence:.2f}

Find specific protocol text that:
1. Describes this activity's requirements (timing, frequency, procedures)
2. References laboratory specifications, specimen requirements, or safety monitoring
3. Links this activity to endpoints, biospecimen collection, or PK/PD sampling
4. Contains any footnotes or special instructions for this activity

Return a JSON response:
{{
    "found_evidence": true/false,
    "page_numbers": [list of page numbers where found],
    "evidence_summary": "Brief summary of what was found",
    "supports_modules": ["list of modules this evidence supports"],
    "additional_context": "Any additional relevant context from the protocol",
    "confidence_adjustment": 0.0 to 0.15 (how much to increase confidence based on evidence)
}}"""

            # Call Gemini with PDF context
            import google.generativeai as genai
            response = self._gemini_client.generate_content(
                [
                    genai.protos.Part(file_data=genai.protos.FileData(file_uri=self._gemini_file_uri)),
                    prompt
                ],
                generation_config={
                    "temperature": 0.1,
                    "max_output_tokens": 2048,
                }
            )

            # Parse response
            response_text = response.text.strip()
            if response_text.startswith("```"):
                response_text = re.sub(r"^```\w*\n?", "", response_text)
                response_text = re.sub(r"\n?```$", "", response_text)

            pdf_evidence = json.loads(response_text)

            # Update decision with PDF evidence
            if pdf_evidence.get("found_evidence"):
                confidence_boost = min(pdf_evidence.get("confidence_adjustment", 0.0), 0.15)
                new_confidence = min(decision.confidence + confidence_boost, 0.98)

                # Create updated decision
                decision.confidence = new_confidence
                decision.pdf_validation = {
                    "validated": True,
                    "page_numbers": pdf_evidence.get("page_numbers", []),
                    "evidence_summary": pdf_evidence.get("evidence_summary", ""),
                    "supports_modules": pdf_evidence.get("supports_modules", []),
                }

                # Update human review flag based on new confidence
                if new_confidence >= 0.90:
                    decision.requires_human_review = False

                logger.info(
                    f"PDF validation improved confidence for '{activity_name}': "
                    f"{decision.confidence - confidence_boost:.2f} → {new_confidence:.2f}"
                )
            else:
                # No supporting evidence found - keep or lower confidence
                decision.pdf_validation = {
                    "validated": True,
                    "page_numbers": [],
                    "evidence_summary": "No supporting evidence found in PDF",
                    "supports_modules": [],
                }
                logger.info(f"PDF validation found no additional evidence for '{activity_name}'")

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse PDF validation response: {e}")
            decision.pdf_validation = {"validated": False, "error": str(e)}
        except Exception as e:
            logger.warning(f"PDF validation failed for '{activity_name}': {e}")
            decision.pdf_validation = {"validated": False, "error": str(e)}

        return decision

    # ============ PHASE 3: ENRICHMENT EXTRACTION ============

    def _extract_enrichment(
        self,
        activity: Dict[str, Any],
        decision: MiningDecision,
        extraction_outputs: Dict[str, Dict[str, Any]],
    ) -> Optional[MiningEnrichment]:
        """Extract enrichment data from matched modules"""
        enrichment = MiningEnrichment(
            id=f"MINE-{uuid.uuid4().hex[:12].upper()}",
            activity_id=activity["id"],
            activity_name=activity.get("activityName", ""),
            overall_confidence=decision.confidence,
            sources_used=decision.matched_modules.copy(),
            requires_human_review=decision.requires_human_review,
        )

        # Extract from each matched module
        for module in decision.matched_modules:
            module_data = extraction_outputs.get(module, {})
            if not module_data:
                continue

            if module == "laboratory_specifications":
                enrichment.lab_manual_enrichment = self._extract_lab_enrichment(
                    activity, module_data
                )
            elif module == "pkpd_sampling":
                enrichment.pkpd_enrichment = self._extract_pkpd_enrichment(
                    activity, module_data
                )
            elif module in ("adverse_events", "sae_reporting", "safety_monitoring"):
                if not enrichment.safety_enrichment:
                    enrichment.safety_enrichment = self._extract_safety_enrichment(
                        activity, module_data
                    )
            elif module == "biospecimen_handling":
                enrichment.biospecimen_enrichment = self._extract_biospecimen_enrichment(
                    activity, module_data
                )
            elif module in ("endpoints_estimands", "endpoints_estimands_sap"):
                enrichment.endpoint_enrichment = self._extract_endpoint_enrichment(
                    activity, module_data
                )
            elif module == "imaging_central_reading":
                enrichment.imaging_enrichment = self._extract_imaging_enrichment(
                    activity, module_data
                )
            elif module == "dose_modifications":
                enrichment.dose_modification_enrichment = self._extract_dose_modification_enrichment(
                    activity, module_data
                )

        # Check if any enrichment was extracted
        if not any([
            enrichment.lab_manual_enrichment,
            enrichment.pkpd_enrichment,
            enrichment.safety_enrichment,
            enrichment.biospecimen_enrichment,
            enrichment.endpoint_enrichment,
            enrichment.imaging_enrichment,
            enrichment.dose_modification_enrichment,
        ]):
            return None

        return enrichment

    def _extract_lab_enrichment(
        self, activity: Dict[str, Any], lab_output: Dict[str, Any]
    ) -> Optional[LabManualEnrichment]:
        """Extract lab manual enrichment with deep field extraction from actual schema structure.

        Handles both snake_case (actual schema) and camelCase (legacy) field names.
        Uses fuzzy matching for activity-to-test/panel correlation.
        """
        activity_name = activity.get("activityName", "").lower()

        # Get lab tests from actual schema structure (snake_case)
        lab_tests = lab_output.get("laboratory_tests", lab_output.get("labTests", []))
        discovered_panels = lab_output.get("discovered_panels", lab_output.get("discoveredPanels", []))
        central_lab = lab_output.get("central_laboratory", lab_output.get("centralLabInfo", {}))
        sample_requirements = lab_output.get("sample_collection_requirements", {})

        # First try to match by panel name (higher-level match)
        matched_panel = None
        matched_tests = []

        # Panel name mapping for common SOA activity names
        panel_keywords = {
            "hematology": ["hematology", "cbc", "blood count", "hemoglobin", "hematocrit"],
            "chemistry": ["chemistry", "metabolic", "liver function", "renal function", "electrolytes"],
            "urinalysis": ["urinalysis", "urine", "ua"],
            "coagulation": ["coagulation", "pt", "inr", "aptt", "fibrinogen"],
            "thyroid": ["thyroid", "tsh", "t3", "t4"],
            "lipid": ["lipid", "cholesterol", "triglyceride", "ldl", "hdl"],
            "pregnancy": ["pregnancy", "hcg", "beta-hcg"],
        }

        for panel in discovered_panels:
            panel_name = (panel.get("panel_name") or panel.get("panelName") or "").lower()
            panel_category = (panel.get("panel_category") or panel.get("panelCategory") or "").lower()

            # Check for direct match or keyword-based match
            if panel_name and (panel_name in activity_name or activity_name in panel_name):
                matched_panel = panel
                break

            # Check panel keywords
            for keyword_type, keywords in panel_keywords.items():
                if any(kw in activity_name for kw in keywords):
                    if keyword_type in panel_category or any(kw in panel_name for kw in keywords):
                        matched_panel = panel
                        break
            if matched_panel:
                break

        # Find matching tests (either by panel or by name)
        for test in lab_tests:
            test_name = (test.get("test_name") or test.get("testName") or "").lower()
            panel_ref = test.get("panel_ref") or test.get("panelRef")

            # If we matched a panel, get all tests for that panel
            if matched_panel:
                panel_id = matched_panel.get("panel_id") or matched_panel.get("panelId")
                if panel_ref == panel_id:
                    matched_tests.append(test)
            # Otherwise try direct test name matching
            elif test_name:
                test_words = set(test_name.replace("/", " ").replace("-", " ").split())
                # Check for word overlap (fuzzy matching)
                if activity_words & test_words or test_name in activity_name or activity_name in test_name:
                    matched_tests.append(test)

        # If no matches found, return None
        if not matched_panel and not matched_tests:
            return None

        # Build enrichment from matched data
        primary_test = matched_tests[0] if matched_tests else {}

        # Aggregate specimen types and tubes from all matched tests
        specimen_types = list(set(
            t.get("specimen_type") or t.get("specimenType")
            for t in matched_tests if t.get("specimen_type") or t.get("specimenType")
        ))
        tube_types = list(set(
            t.get("collection_container") or t.get("tubeType")
            for t in matched_tests if t.get("collection_container") or t.get("tubeType")
        ))
        volumes = list(set(
            t.get("collection_volume") or t.get("sampleVolume")
            for t in matched_tests if t.get("collection_volume") or t.get("sampleVolume")
        ))

        # Create provenance from matched source
        provenance_source = matched_panel or primary_test
        provenance = self._create_provenance(
            "laboratory_specifications",
            "discovered_panels[]" if matched_panel else "laboratory_tests[]",
            provenance_source
        )

        logger.debug(f"Lab enrichment for {activity.get('activityName')}: matched_panel={matched_panel.get('panel_name') if matched_panel else None}, tests_count={len(matched_tests)}")

        return LabManualEnrichment(
            lab_test_name=matched_panel.get("panel_name") or matched_panel.get("panelName") if matched_panel else primary_test.get("test_name") or primary_test.get("testName"),
            test_code=primary_test.get("test_code") or primary_test.get("testCode") or (matched_panel.get("panel_code") or matched_panel.get("panelCode") if matched_panel else None),
            loinc_code=primary_test.get("test_code") if (primary_test.get("test_code") or "").startswith("LOINC") else None,
            specimen_type=specimen_types[0] if specimen_types else None,
            collection_requirements=sample_requirements.get("timing_requirements") or sample_requirements.get("timingRequirements"),
            processing_instructions=sample_requirements.get("processing_requirements") or sample_requirements.get("processingRequirements"),
            stability_requirements=sample_requirements.get("storage_requirements") or sample_requirements.get("storageRequirements"),
            tube_type=tube_types[0] if tube_types else None,
            sample_volume=volumes[0] if volumes else None,
            fasting_required=primary_test.get("fasting_required") or primary_test.get("fastingRequired") or sample_requirements.get("fasting_requirements") is not None,
            reference_ranges=primary_test.get("reference_ranges") or primary_test.get("referenceRanges"),
            central_lab_name=central_lab.get("vendor_name") or central_lab.get("labName"),
            provenance=[provenance] if provenance else [],
        )

    def _extract_pkpd_enrichment(
        self, activity: Dict[str, Any], pkpd_output: Dict[str, Any]
    ) -> Optional[PKPDEnrichment]:
        """Extract PK/PD enrichment with deep field extraction from actual schema structure.

        Handles both snake_case (actual schema) and camelCase (legacy) field names.
        Extracts from pk_sampling, pk_parameters, pd_assessments, immunogenicity.
        """
        activity_name = activity.get("activityName", "").lower()

        # Get PK sampling from actual schema structure (snake_case)
        pk_sampling_obj = pkpd_output.get("pk_sampling", pkpd_output.get("pkSampling", {}))
        pk_parameters_obj = pkpd_output.get("pk_parameters", pkpd_output.get("pkParameters", {}))
        pd_assessments_obj = pkpd_output.get("pd_assessments", pkpd_output.get("pdAssessments", {}))
        immunogenicity_obj = pkpd_output.get("immunogenicity", {})
        sample_handling_obj = pkpd_output.get("sample_handling", {})

        # Check if PK/PD data exists
        pk_required = pk_sampling_obj.get("pk_sampling_required") or pk_sampling_obj.get("pkSamplingRequired")
        pd_required = pd_assessments_obj.get("pd_assessments_required") or pd_assessments_obj.get("pdAssessmentsRequired")

        if not pk_required and not pd_required:
            return None

        # Extract analytes from pk_sampling
        analytes = pk_sampling_obj.get("analytes", [])
        matched_analyte = None
        if analytes:
            # Try to match by activity name (e.g., "PK Sampling" might match drug name)
            for analyte in analytes:
                analyte_name = (analyte.get("analyte_name") or analyte.get("analyteName") or "").lower()
                if analyte_name and (analyte_name in activity_name or activity_name in analyte_name):
                    matched_analyte = analyte
                    break
            # Default to first analyte if no match
            if not matched_analyte and analytes:
                matched_analyte = analytes[0]

        # Extract sampling schedule
        sampling_schedule = pk_sampling_obj.get("sampling_schedule", pk_sampling_obj.get("samplingSchedule", []))
        timepoints = []
        for schedule in sampling_schedule:
            schedule_timepoints = schedule.get("timepoints", [])
            for tp in schedule_timepoints:
                tp_name = tp.get("timepoint_name") or tp.get("timepointName") or ""
                if tp_name:
                    timepoints.append(tp_name)

        # Extract PK parameters (with null checks for both lists)
        primary_params = pk_parameters_obj.get("primary_parameters", pk_parameters_obj.get("primaryParameters", []))
        secondary_params = pk_parameters_obj.get("secondary_parameters", pk_parameters_obj.get("secondaryParameters", []))
        pk_params = []
        if isinstance(primary_params, list):
            pk_params.extend(primary_params)
        if isinstance(secondary_params, list):
            pk_params.extend(secondary_params)

        # Extract PD biomarkers
        pd_biomarkers = pd_assessments_obj.get("pd_biomarkers", pd_assessments_obj.get("pdBiomarkers", []))
        pd_markers = [b.get("biomarker_name") or b.get("biomarkerName") or "" for b in pd_biomarkers if b]

        # Extract sample volume
        sample_volume_str = pk_sampling_obj.get("sample_volume") or pk_sampling_obj.get("sampleVolume")
        sample_volume_ml = None
        if isinstance(sample_volume_str, dict):
            sample_volume_ml = sample_volume_str.get("value")
        elif isinstance(sample_volume_str, str):
            # Try to parse "Approximately 3 mL" -> 3.0
            match = re.search(r"(\d+(?:\.\d+)?)\s*(?:mL|ml)", sample_volume_str)
            if match:
                sample_volume_ml = float(match.group(1))

        # Extract sample handling info
        processing_requirements = sample_handling_obj.get("processing_requirements") or sample_handling_obj.get("processingRequirements")
        storage_conditions = sample_handling_obj.get("storage_conditions") or sample_handling_obj.get("storageConditions")
        collection_tubes = sample_handling_obj.get("collection_tubes") or sample_handling_obj.get("collectionTubes")

        # Check immunogenicity
        ada_required = immunogenicity_obj.get("ada_testing_required") or immunogenicity_obj.get("adaTestingRequired")

        # Create provenance
        provenance_source = matched_analyte or pk_sampling_obj
        provenance = self._create_provenance(
            "pkpd_sampling",
            "pk_sampling.analytes[]" if matched_analyte else "pk_sampling",
            provenance_source
        )

        logger.debug(f"PKPD enrichment for {activity.get('activityName')}: matched_analyte={matched_analyte.get('analyte_name') if matched_analyte else None}, timepoints_count={len(timepoints)}")

        return PKPDEnrichment(
            analyte_name=matched_analyte.get("analyte_name") or matched_analyte.get("analyteName") if matched_analyte else None,
            analyte_type=matched_analyte.get("analyte_type") or matched_analyte.get("analyteType") if matched_analyte else None,
            sampling_timepoints=timepoints[:10],  # Limit to first 10 timepoints
            sampling_windows=None,  # Not directly available in schema
            sample_volume_ml=sample_volume_ml,
            sample_matrix=matched_analyte.get("matrix") if matched_analyte else None,
            processing_requirements=processing_requirements,
            storage_conditions=storage_conditions,
            bioanalytical_method=matched_analyte.get("bioanalytical_method") or matched_analyte.get("bioanalyticalMethod") if matched_analyte else None,
            pk_parameters=pk_params if isinstance(pk_params, list) else [],
            pd_markers=pd_markers,
            immunogenicity_sampling=ada_required,
            provenance=[provenance] if provenance else [],
        )

    def _extract_safety_enrichment(
        self, activity: Dict[str, Any], ae_output: Dict[str, Any]
    ) -> Optional[SafetyEnrichment]:
        """Extract safety enrichment with deep field extraction from actual schema structure.

        Handles both snake_case (actual schema) and camelCase (legacy) field names.
        """
        # Get data from actual schema structure (snake_case)
        grading = ae_output.get("grading_system", ae_output.get("gradingSystem", {}))
        ae_defs = ae_output.get("ae_definitions", ae_output.get("aeDefinitions", {}))
        aesi_list = ae_output.get("aesi_list", ae_output.get("aesiList", []))
        causality = ae_output.get("causality_assessment", ae_output.get("causalityAssessment", {}))
        reporting = ae_output.get("reporting_procedures", ae_output.get("reportingProcedures", {}))

        if not grading and not ae_defs and not aesi_list:
            logger.debug(f"No safety data found for activity: {activity.get('activityName')}")
            return None

        # Extract AESI terms
        aesi_terms = []
        if isinstance(aesi_list, list):
            for aesi in aesi_list:
                if isinstance(aesi, dict):
                    term = aesi.get("term") or aesi.get("aesi_term") or aesi.get("aesiTerm") or ""
                    if term:
                        aesi_terms.append(term)

        # Extract causality categories
        causality_categories = []
        if isinstance(causality, dict):
            categories = causality.get("categories", [])
            if isinstance(categories, list):
                for cat in categories:
                    if isinstance(cat, dict):
                        cat_name = cat.get("category") or cat.get("name") or ""
                        if cat_name:
                            causality_categories.append(cat_name)
                    elif isinstance(cat, str):
                        causality_categories.append(cat)

        provenance = self._create_provenance(
            "adverse_events",
            "grading_system",
            grading
        )

        logger.debug(f"Safety enrichment extracted: grading={grading.get('system_name')}, aesi_count={len(aesi_terms)}")

        return SafetyEnrichment(
            safety_assessment_type=grading.get("system_name") or grading.get("systemName"),
            grading_system_version=grading.get("system_version") or grading.get("systemVersion"),
            reporting_period=ae_defs.get("collection_end") or ae_defs.get("collectionEnd"),
            related_aes=[],  # Would need activity-specific matching
            aesi_terms=aesi_terms,
            monitoring_requirements=reporting.get("monitoring_requirements") or ae_output.get("monitoringRequirements"),
            dose_modification_triggers=[],
            causality_categories=causality_categories,
            provenance=[provenance] if provenance else [],
        )

    def _extract_biospecimen_enrichment(
        self, activity: Dict[str, Any], biospecimen_output: Dict[str, Any]
    ) -> Optional[BiospecimenEnrichment]:
        """Extract biospecimen enrichment with deep field extraction from actual schema structure.

        Handles both snake_case (actual schema) and camelCase (legacy) field names.
        Matches activity to discovered specimen types for relevant enrichment.
        """
        activity_name = activity.get("activityName", "").lower()

        # Get specimen types from actual schema structure (snake_case)
        discovered_specimen_types = biospecimen_output.get("discovered_specimen_types", biospecimen_output.get("discoveredSpecimenTypes", []))
        storage_requirements = biospecimen_output.get("storage_requirements", biospecimen_output.get("storageRequirements", []))
        shipping_requirements = biospecimen_output.get("shipping_requirements", biospecimen_output.get("shippingRequirements", []))
        regulatory_requirements = biospecimen_output.get("regulatory_requirements", biospecimen_output.get("regulatoryRequirements", {}))
        processing_requirements = biospecimen_output.get("processing_requirements", biospecimen_output.get("processingRequirements", []))

        # Try to match specimen type to activity
        matched_specimen = None
        specimen_keywords = {
            "blood": ["blood", "plasma", "serum", "hematology", "chemistry"],
            "urine": ["urine", "urinalysis"],
            "tissue": ["tissue", "biopsy", "tumor"],
            "genetic": ["genetic", "dna", "pharmacogenomics", "genomic"],
            "pk": ["pk", "pharmacokinetic", "pk/pd"],
            "pd": ["pd", "pharmacodynamic", "biomarker"],
        }

        for specimen in discovered_specimen_types:
            specimen_name = (specimen.get("specimen_name") or specimen.get("specimenName") or "").lower()
            specimen_purpose = (specimen.get("purpose") or "").lower()
            specimen_category = (specimen.get("specimen_category") or specimen.get("specimenCategory") or "").lower()

            # Direct name match
            if specimen_name and (specimen_name in activity_name or activity_name in specimen_name):
                matched_specimen = specimen
                break

            # Keyword-based match
            for kw_type, keywords in specimen_keywords.items():
                if any(kw in activity_name for kw in keywords):
                    if kw_type in specimen_category or kw_type in specimen_purpose or any(kw in specimen_name for kw in keywords):
                        matched_specimen = specimen
                        break
            if matched_specimen:
                break

        # Extract storage conditions
        short_term_storage = None
        long_term_storage = None
        for storage in storage_requirements:
            storage_phase = storage.get("storage_phase") or storage.get("storagePhase") or ""
            temp_condition = storage.get("temperature_condition", storage.get("temperatureCondition", {}))
            temp_desc = temp_condition.get("description") if isinstance(temp_condition, dict) else str(temp_condition) if temp_condition else None

            if "short" in storage_phase.lower() or "temporary" in storage_phase.lower():
                short_term_storage = temp_desc
            elif "long" in storage_phase.lower() or "archive" in storage_phase.lower():
                long_term_storage = temp_desc

        # Extract shipping requirements
        shipping_info = None
        if shipping_requirements:
            first_ship = shipping_requirements[0] if isinstance(shipping_requirements, list) else shipping_requirements
            ship_temp = first_ship.get("temperature_condition", first_ship.get("temperatureCondition", {}))
            ship_temp_desc = ship_temp.get("description") if isinstance(ship_temp, dict) else str(ship_temp) if ship_temp else None
            shipping_info = ship_temp_desc

        # Extract regulatory info (includes consent, genetic testing)
        genetic_consent = regulatory_requirements.get("genetic_consent") or regulatory_requirements.get("geneticConsent")
        future_use_consent = regulatory_requirements.get("future_use_consent") or regulatory_requirements.get("futureUseConsent")
        retention_period = regulatory_requirements.get("retention_period") or regulatory_requirements.get("retentionPeriod")
        destruction_procedures = regulatory_requirements.get("destruction_procedures") or regulatory_requirements.get("destructionProcedures")

        # Early return if no matched specimen and no regulatory requirements
        if not matched_specimen and not regulatory_requirements:
            logger.debug(f"No biospecimen match found for activity: {activity.get('activityName')}")
            return None

        # Determine if genetic testing is involved
        genetic_testing_included = False
        if matched_specimen:
            purpose = (matched_specimen.get("purpose") or "").lower()
            purpose_desc = (matched_specimen.get("purpose_description") or matched_specimen.get("purposeDescription") or "").lower()
            genetic_testing_included = "genetic" in purpose or "genetic" in purpose_desc or "dna" in purpose_desc

        # Build future_research_uses list, filtering out empty strings
        future_research_uses = []
        if matched_specimen:
            purpose_description = matched_specimen.get("purpose_description") or matched_specimen.get("purposeDescription") or ""
            if purpose_description.strip():  # Only add non-empty strings
                future_research_uses.append(purpose_description)

        # Create provenance
        provenance_source = matched_specimen or regulatory_requirements or biospecimen_output
        provenance = self._create_provenance(
            "biospecimen_handling",
            "discovered_specimen_types[]" if matched_specimen else "regulatory_requirements",
            provenance_source
        )

        logger.debug(f"Biospecimen enrichment for {activity.get('activityName')}: matched_specimen={matched_specimen.get('specimen_name') if matched_specimen else None}")

        return BiospecimenEnrichment(
            biobank_consent_required=future_use_consent is not None,
            consent_type="optional" if matched_specimen and "optional" in (matched_specimen.get("purpose_description") or "").lower() else "required",
            short_term_storage=short_term_storage,
            long_term_storage_conditions=long_term_storage,
            future_research_uses=future_research_uses,
            genetic_testing_included=genetic_testing_included,
            genetic_consent_required=genetic_consent,
            retention_period=retention_period,
            destruction_policy=destruction_procedures,
            shipping_requirements=shipping_info,
            provenance=[provenance] if provenance else [],
        )

    def _extract_endpoint_enrichment(
        self, activity: Dict[str, Any], endpoint_output: Dict[str, Any]
    ) -> Optional[EndpointEnrichment]:
        """Extract endpoint enrichment with provenance"""
        protocol_endpoints = endpoint_output.get("protocol_endpoints", endpoint_output)
        endpoints = protocol_endpoints.get("endpoints", [])
        estimands = protocol_endpoints.get("estimands", [])

        if not endpoints:
            return None

        # Find related endpoints
        activity_name = activity.get("activityName", "").lower()
        related = []
        endpoint_type = None

        for ep in endpoints:
            ep_name = (ep.get("name") or "").lower()
            if ep_name and (activity_name in ep_name or any(word in ep_name for word in activity_name.split())):
                related.append(ep.get("name", ""))
                endpoint_type = ep.get("endpointType")

        provenance = self._create_provenance(
            "endpoints_estimands",
            "endpoints[]",
            endpoints[0] if endpoints else {}
        )

        return EndpointEnrichment(
            related_endpoints=related,
            endpoint_type=endpoint_type,
            linked_objective=None,
            measurement_method=None,
            estimand_strategy=estimands[0].get("strategy") if estimands else None,
            intercurrent_events=[],
            analysis_population=None,
            assessment_timing=None,
            provenance=[provenance] if provenance else [],
        )

    # ============ ONCOLOGY-SPECIFIC EXTRACTION ============

    def _extract_imaging_enrichment(
        self, activity: Dict[str, Any], imaging_output: Dict[str, Any]
    ) -> Optional[ImagingEnrichment]:
        """Extract imaging/RECIST enrichment with provenance (ONCOLOGY)"""
        response_criteria = imaging_output.get("response_criteria", {})
        modalities = imaging_output.get("imaging_modalities", [])
        schedule = imaging_output.get("assessment_schedule", {})
        lesions = imaging_output.get("lesion_requirements", {})
        central = imaging_output.get("central_reading", {})
        categories = imaging_output.get("response_categories", [])
        immune = imaging_output.get("immune_related_criteria", {})

        if not response_criteria and not modalities:
            return None

        # Get first modality
        first_modality = modalities[0] if modalities else {}

        provenance = self._create_provenance(
            "imaging_central_reading",
            "response_criteria",
            response_criteria
        )

        return ImagingEnrichment(
            response_criteria=response_criteria.get("primary_criteria"),
            criteria_version=response_criteria.get("criteria_version"),
            secondary_criteria=response_criteria.get("secondary_criteria", []),
            criteria_modifications=response_criteria.get("modifications"),
            immune_related_criteria=immune.get("irecist_used"),
            imaging_modality=first_modality.get("modality_type"),
            body_regions=first_modality.get("body_regions", []),
            contrast_required=first_modality.get("contrast_required"),
            contrast_type=first_modality.get("contrast_type"),
            slice_thickness=first_modality.get("slice_thickness"),
            technical_requirements=first_modality.get("technical_requirements"),
            baseline_window=schedule.get("baseline_window"),
            assessment_frequency=schedule.get("on_treatment_frequency"),
            first_assessment_timing=schedule.get("first_assessment_timing"),
            post_treatment_schedule=schedule.get("post_treatment_schedule"),
            confirmatory_scan_required=schedule.get("confirmatory_scan_required"),
            confirmatory_scan_window=schedule.get("confirmatory_scan_window"),
            measurable_disease_definition=lesions.get("measurable_disease_definition"),
            target_lesion_criteria=lesions.get("target_lesion_minimum_size"),
            lymph_node_criteria=lesions.get("lymph_node_criteria"),
            max_target_lesions=lesions.get("max_target_lesions"),
            max_target_lesions_per_organ=lesions.get("max_target_lesions_per_organ"),
            non_target_lesion_definition=lesions.get("non_target_lesion_definition"),
            bicr_required=central.get("bicr_required"),
            bicr_purpose=central.get("bicr_purpose"),
            bicr_vendor=central.get("vendor_name"),
            reading_methodology=central.get("reading_methodology"),
            reader_qualifications=central.get("reader_qualifications"),
            blinding_requirements=central.get("blinding_requirements"),
            adjudication_process=central.get("adjudication_process"),
            turnaround_time=central.get("turnaround_time"),
            response_categories=[c.get("category_code", "") for c in categories],
            pseudoprogression_handling=immune.get("pseudoprogression_handling"),
            treatment_beyond_progression=immune.get("treatment_beyond_progression"),
            provenance=[provenance] if provenance else [],
        )

    def _extract_dose_modification_enrichment(
        self, activity: Dict[str, Any], dose_mod_output: Dict[str, Any]
    ) -> Optional[DoseModificationEnrichment]:
        """Extract DLT/dose modification enrichment with provenance (ONCOLOGY)"""
        dlt = dose_mod_output.get("dlt_criteria", {})
        reduction = dose_mod_output.get("dose_reduction_rules", {})
        delay = dose_mod_output.get("dose_delay_rules", {})
        reescalation = dose_mod_output.get("re_escalation", {})
        supportive = dose_mod_output.get("supportive_care", {})

        if not dlt and not reduction:
            return None

        provenance = self._create_provenance(
            "dose_modifications",
            "dlt_criteria",
            dlt
        )

        return DoseModificationEnrichment(
            dlt_definition=dlt.get("definition"),
            dlt_evaluation_period=dlt.get("evaluation_period"),
            dlt_criteria=dlt.get("qualifying_events", []),
            non_dlt_exceptions=dlt.get("non_dlt_exceptions", []),
            starting_dose=reduction.get("starting_dose"),
            dose_reduction_levels=reduction.get("levels", []),
            dose_reduction_triggers=reduction.get("triggers", []),
            max_dose_reductions=reduction.get("max_reductions"),
            dose_delay_criteria=delay.get("criteria"),
            max_delay_duration=delay.get("max_duration"),
            recovery_requirements=delay.get("recovery_requirements"),
            discontinuation_criteria=dose_mod_output.get("discontinuation_criteria", []),
            permanent_discontinuation_criteria=[],
            re_escalation_allowed=reescalation.get("allowed"),
            re_escalation_criteria=reescalation.get("criteria"),
            re_escalation_conditions=reescalation.get("conditions"),
            gcsf_allowed=supportive.get("g_csf_allowed"),
            supportive_care_notes=None,
            provenance=[provenance] if provenance else [],
        )

    def _create_provenance(
        self, module: str, field_path: str, source_data: Dict[str, Any]
    ) -> Optional[MiningProvenance]:
        """Create provenance record from source data"""
        if not source_data:
            return None

        # Extract page numbers from provenance field
        prov = source_data.get("provenance", {})
        page_numbers = []
        text_snippets = []

        if isinstance(prov, dict):
            page = prov.get("page_number") or prov.get("pageNumber")
            if page:
                page_numbers = [page] if isinstance(page, int) else page

            snippet = prov.get("text_snippet") or prov.get("textSnippet")
            if snippet:
                text_snippets = [snippet[:500]]  # Truncate to 500 chars

        return MiningProvenance(
            source_module=module,
            field_path=field_path,
            page_numbers=page_numbers,
            text_snippets=text_snippets,
            model_used=self.config.model_name,
        )

    # ============ OUTPUT ============

    def apply_enrichments_to_usdm(
        self, usdm_output: Dict[str, Any], result: Stage9Result
    ) -> Dict[str, Any]:
        """Apply mining enrichments to USDM output"""
        # Create enrichment lookup
        enrichment_lookup = {e.activity_id: e for e in result.enrichments}

        # Get SAIs
        sais = usdm_output.get("scheduledActivityInstances", [])
        if not sais:
            schedule = usdm_output.get("schedule", {})
            sais = schedule.get("scheduledActivityInstances", [])

        # Apply enrichments
        for sai in sais:
            activity_id = sai.get("id", "")
            enrichment = enrichment_lookup.get(activity_id)

            if enrichment:
                sai["_miningEnrichment"] = enrichment.to_dict()

        return usdm_output

    # ============ CACHE MANAGEMENT ============

    def _load_cache(self) -> None:
        """Load cache from disk"""
        cache_path = Path(__file__).parent.parent / ".cache" / self.config.cache_file
        if cache_path.exists():
            try:
                with open(cache_path, "r") as f:
                    data = json.load(f)
                    for key, value in data.items():
                        self._cache[key] = MiningDecision.from_dict(value)
                logger.info(f"Loaded {len(self._cache)} cached decisions")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")

    def _save_cache(self) -> None:
        """Persist cache to disk"""
        cache_dir = Path(__file__).parent.parent / ".cache"
        cache_dir.mkdir(exist_ok=True)
        cache_path = cache_dir / self.config.cache_file

        try:
            data = {key: decision.to_dict() for key, decision in self._cache.items()}
            with open(cache_path, "w") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(self._cache)} decisions to cache")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def _update_cache(self, key: str, decision: MiningDecision) -> None:
        """Update in-memory cache"""
        self._cache[key] = decision


# ============ CONVENIENCE FUNCTION ============

async def mine_protocol(
    usdm_output: Dict[str, Any],
    extraction_outputs: Optional[Dict[str, Dict[str, Any]]] = None,
    config: Optional[Stage9Config] = None,
) -> Tuple[Dict[str, Any], Stage9Result]:
    """
    Convenience function for protocol mining.

    Args:
        usdm_output: USDM output from Stage 8
        extraction_outputs: Dict of module_name -> extraction JSON (optional)
        config: Optional Stage9Config

    Returns:
        Tuple of (updated_usdm, Stage9Result)
    """
    miner = ProtocolMiner(config)
    result = await miner.mine_protocol(usdm_output, extraction_outputs)
    updated_usdm = miner.apply_enrichments_to_usdm(usdm_output, result)
    return updated_usdm, result
