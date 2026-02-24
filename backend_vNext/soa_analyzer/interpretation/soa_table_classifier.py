"""
SOA Table Classifier: LLM-Driven Structural Analysis for Protocol-Agnostic Interpretation

Computes structural features from the USDM output and uses an LLM to classify
the table type and generate per-stage guidance. The resulting profile is injected
into downstream stage prompts so each stage has context about what kind of SOA
table it's processing.

Architecture:
  1. compute_structural_features() — deterministic, pure Python
  2. classify() — LLM call with triple fallback (Gemini → Azure → Claude)

Usage:
    from soa_analyzer.interpretation.soa_table_classifier import SOATableClassifier

    classifier = SOATableClassifier()
    profile = await classifier.classify(usdm_output, extraction_outputs=extraction_outputs)
    usdm_output["soaTableProfile"] = profile
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Prompt file path
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "soa_table_classification.txt"

# Cache directory
CACHE_DIR = Path(__file__).parent.parent / ".cache" / "table_classification"


class SOATableClassifier:
    """
    Classifies SOA tables using structural features + LLM reasoning.

    Produces a soaTableProfile dict with:
      - tableStructureType: free-text clinical classification
      - confidence: 0.0-1.0
      - characteristics: key observations
      - stageGuidance: per-stage natural-language guidance
      - structuralFeatures: the computed features (audit trail)
    """

    def __init__(self, use_cache: bool = True, cache_dir: Optional[Path] = None):
        self.use_cache = use_cache
        self.cache_dir = cache_dir or CACHE_DIR

        # LLM clients (lazy loaded)
        self._gemini_client = None
        self._azure_client = None
        self._azure_deployment = None
        self._claude_client = None

        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # STRUCTURAL FEATURE COMPUTATION (deterministic)
    # =========================================================================

    def compute_structural_features(self, usdm_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structural features from USDM output. Pure Python, no LLM.

        Args:
            usdm_output: USDM output (after HTML interpretation, before or during stages)

        Returns:
            Dict of structural features for classification
        """
        encounters = usdm_output.get("encounters", usdm_output.get("visits", []))
        activities = usdm_output.get("activities", [])
        sais = usdm_output.get("scheduledActivityInstances", [])
        quality_metrics = usdm_output.get("qualityMetrics", {})
        visit_groups = usdm_output.get("visitGroups", {})

        total_visits = len(encounters)
        timepoint_encounters = quality_metrics.get("timepointEncounters", 0)
        standalone_encounters = quality_metrics.get("standaloneEncounters", 0)

        # If qualityMetrics not available, compute from encounters directly
        if not quality_metrics:
            timepoint_encounters = sum(
                1 for e in encounters if e.get("timingModifier")
            )
            standalone_encounters = total_visits - timepoint_encounters

        timepoint_ratio = (
            timepoint_encounters / total_visits if total_visits > 0 else 0.0
        )

        visits_with_recurrence = quality_metrics.get(
            "visitsWithRecurrence",
            sum(1 for e in encounters if e.get("recurrence")),
        )
        visit_group_count = quality_metrics.get(
            "visitGroupCount", len(visit_groups)
        )
        matrix_coverage = quality_metrics.get("matrixCoverage", 0.0)

        # Encounter name sample (first 20)
        encounter_names = [e.get("name", "") for e in encounters[:20]]

        # Visit groups: parentVisit -> encounter names
        visit_group_map = {}
        if visit_groups:
            visit_group_map = visit_groups
        else:
            # Build from encounter parentVisit fields
            parent_map: Dict[str, List[str]] = defaultdict(list)
            for e in encounters:
                parent = e.get("parentVisit")
                if parent:
                    parent_map[parent].append(e.get("name", e.get("id", "")))
            if parent_map:
                visit_group_map = dict(parent_map)

        # Activity domain distribution
        domain_distribution: Dict[str, int] = defaultdict(int)
        for act in activities:
            domain_code = act.get("domainCode")
            if isinstance(domain_code, dict):
                domain = domain_code.get("decode", domain_code.get("code", "unknown"))
            elif isinstance(domain_code, str):
                domain = domain_code
            else:
                # Fall back to raw categories
                for cat in act.get("categories", []):
                    if isinstance(cat, str):
                        domain_distribution[cat] += 1
                continue
            domain_distribution[domain] += 1

        # Footnote categories
        footnote_categories = quality_metrics.get("footnoteCategoryDistribution", {})

        # Explicit cycle labels
        cycle_pattern = re.compile(r"cycle", re.IGNORECASE)
        has_explicit_cycle_labels = any(
            cycle_pattern.search(e.get("name", "")) for e in encounters
        )

        # Day-based naming
        day_pattern = re.compile(r"(?:^|\b)(?:day|d)\s*[-:]?\s*\d+", re.IGNORECASE)
        has_day_based_naming = any(
            day_pattern.search(e.get("name", "")) for e in encounters
        )

        # Recurrence types
        recurrence_types = set()
        for e in encounters:
            rec = e.get("recurrence")
            if rec and isinstance(rec, dict):
                rec_type = rec.get("type")
                if rec_type:
                    recurrence_types.add(rec_type)

        return {
            "totalVisits": total_visits,
            "timepointEncounters": timepoint_encounters,
            "standaloneEncounters": standalone_encounters,
            "timepointRatio": round(timepoint_ratio, 3),
            "visitsWithRecurrence": visits_with_recurrence,
            "visitGroupCount": visit_group_count,
            "matrixCoverage": matrix_coverage,
            "encounterNameSample": encounter_names,
            "visitGroups": visit_group_map,
            "activityDomainDistribution": dict(domain_distribution),
            "footnoteCategories": footnote_categories,
            "hasExplicitCycleLabels": has_explicit_cycle_labels,
            "hasDayBasedNaming": has_day_based_naming,
            "recurrenceTypes": sorted(recurrence_types),
        }

    # =========================================================================
    # CLASSIFICATION (LLM)
    # =========================================================================

    async def classify(
        self,
        usdm_output: Dict[str, Any],
        extraction_outputs: Optional[Dict[str, Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Classify the SOA table using structural features + LLM.

        Args:
            usdm_output: USDM output from HTML interpretation
            extraction_outputs: Optional extraction outputs for protocol context

        Returns:
            soaTableProfile dict with classification, guidance, and features
        """
        features = self.compute_structural_features(usdm_output)

        # Check cache
        if self.use_cache:
            cached = self._check_cache(features)
            if cached:
                logger.info("Table classification cache hit")
                return cached

        # Build protocol context from extraction_outputs
        protocol_context = self._extract_protocol_context(extraction_outputs)

        # Build LLM prompt
        prompt = self._build_prompt(features, protocol_context)

        # LLM call with triple fallback
        profile = await self._classify_with_llm(prompt)

        if profile:
            profile["structuralFeatures"] = features
        else:
            # Safe default — stages run with no guidance (identical to pre-classifier behavior)
            logger.warning(
                "Table classification failed (all LLMs) — using empty profile"
            )
            profile = {
                "tableStructureType": "unknown",
                "confidence": 0.0,
                "characteristics": [],
                "stageGuidance": {},
                "structuralFeatures": features,
            }

        # Cache result
        if self.use_cache:
            self._save_to_cache(features, profile)

        return profile

    # =========================================================================
    # PROTOCOL CONTEXT
    # =========================================================================

    def _extract_protocol_context(
        self, extraction_outputs: Optional[Dict[str, Dict]]
    ) -> str:
        """Extract protocol context string from extraction outputs."""
        if not extraction_outputs:
            return "(No protocol context available)"

        parts = []

        study_metadata = extraction_outputs.get("study_metadata", {})
        if study_metadata:
            # Phase
            phase = study_metadata.get("studyPhase")
            if phase:
                parts.append(f"Study Phase: {phase}")

            # Therapeutic area
            ta = study_metadata.get("therapeuticArea")
            if isinstance(ta, dict):
                ta = ta.get("value", ta.get("decode", ""))
            if ta:
                parts.append(f"Therapeutic Area: {ta}")

            # Indication
            indication = study_metadata.get("indication")
            if isinstance(indication, dict):
                indication = indication.get("value", indication.get("decode", ""))
            if indication:
                parts.append(f"Indication: {indication}")

            # Treatment design
            treatment = study_metadata.get("treatmentDesign", {})
            if treatment:
                desc = treatment.get("description")
                duration = treatment.get("duration")
                cycles = treatment.get("cycles")
                if desc:
                    parts.append(f"Treatment Design: {desc}")
                if duration:
                    parts.append(f"Treatment Duration: {duration}")
                if cycles:
                    parts.append(f"Treatment Cycles: {cycles}")

            # Study type
            study_type = study_metadata.get("studyType")
            if study_type:
                parts.append(f"Study Type: {study_type}")

        return "\n".join(parts) if parts else "(No protocol context available)"

    # =========================================================================
    # PROMPT CONSTRUCTION
    # =========================================================================

    def _build_prompt(self, features: Dict[str, Any], protocol_context: str) -> str:
        """Build the classification prompt from template."""
        if PROMPT_PATH.exists():
            with open(PROMPT_PATH) as f:
                template = f.read()
        else:
            raise FileNotFoundError(f"Classification prompt not found: {PROMPT_PATH}")

        features_json = json.dumps(features, indent=2, default=str)

        return template.format(
            features_json=features_json,
            protocol_context=protocol_context,
        )

    # =========================================================================
    # LLM CALLS (Triple Fallback)
    # =========================================================================

    async def _classify_with_llm(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Run classification with triple-fallback LLM routing."""
        use_claude_primary = os.getenv("USE_CLAUDE_PRIMARY", "").lower() == "true"

        if use_claude_primary:
            logger.info("Table classifier: Claude primary")
            result = await self._call_claude(prompt)
            if not result:
                logger.info("Claude failed — falling back to Gemini...")
                result = await self._call_gemini(prompt)
            if not result:
                logger.info("Gemini failed — falling back to Azure...")
                result = await self._call_azure(prompt)
        else:
            result = await self._call_gemini(prompt)
            if not result:
                logger.info("Gemini failed — falling back to Azure...")
                result = await self._call_azure(prompt)
            if not result:
                logger.info("Azure failed — falling back to Claude...")
                result = await self._call_claude(prompt)

        return result

    async def _call_gemini(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Classify with Gemini."""
        client = self._get_gemini_client()
        if not client:
            return None
        try:
            from google.generativeai.types import HarmCategory, HarmBlockThreshold

            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
            response = await asyncio.to_thread(
                client.generate_content,
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": 2048,
                    "response_mime_type": "application/json",
                },
                safety_settings=safety_settings,
            )
            if response.candidates and response.candidates[0].finish_reason.name == "SAFETY":
                logger.warning("Gemini safety filter blocked classification")
                return None
            if not response.text:
                return None
            return self._parse_response(response.text)
        except Exception as e:
            logger.warning(f"Gemini classification failed: {e}")
            return None

    async def _call_azure(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Classify with Azure OpenAI."""
        client = self._get_azure_client()
        if not client:
            return None
        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=self._azure_deployment,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=2048,
                temperature=0.2,
            )
            content = response.choices[0].message.content
            if not content:
                return None
            return self._parse_response(content)
        except Exception as e:
            logger.warning(f"Azure classification failed: {e}")
            return None

    async def _call_claude(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Classify with Anthropic Claude."""
        client = self._get_claude_client()
        if not client:
            return None
        try:
            response = await asyncio.to_thread(
                client.messages.create,
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.content[0].text if response.content else None
            if not content:
                return None
            return self._parse_response(content)
        except Exception as e:
            logger.warning(f"Claude classification failed: {e}")
            return None

    def _parse_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Parse LLM response into profile dict."""
        try:
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            data = json.loads(text)
            if not isinstance(data, dict):
                logger.warning("Classification response is not a dict")
                return None

            # Validate required fields
            required = ["tableStructureType", "confidence", "characteristics", "stageGuidance"]
            for field in required:
                if field not in data:
                    logger.warning(f"Classification response missing '{field}'")
                    return None

            # Ensure confidence is float in range
            data["confidence"] = max(0.0, min(1.0, float(data["confidence"])))

            logger.info(
                f"Parsed table classification: {data['tableStructureType']} "
                f"(confidence: {data['confidence']:.2f})"
            )
            return data

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse classification response: {e}")
            return None

    # =========================================================================
    # LLM CLIENTS (lazy loaded)
    # =========================================================================

    def _get_gemini_client(self):
        """Lazy load Gemini client."""
        if self._gemini_client is None:
            try:
                import google.generativeai as genai
                from google.generativeai.types import HarmCategory, HarmBlockThreshold

                api_key = os.getenv("GEMINI_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)
                    safety_settings = {
                        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                    }
                    self._gemini_client = genai.GenerativeModel(
                        "gemini-3-pro-preview",
                        safety_settings=safety_settings,
                    )
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini for classifier: {e}")
        return self._gemini_client

    def _get_azure_client(self):
        """Lazy load Azure OpenAI client."""
        if self._azure_client is None:
            try:
                from openai import AzureOpenAI

                api_key = os.getenv("AZURE_OPENAI_API_KEY")
                endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
                deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
                api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-01-preview")

                if api_key and endpoint:
                    self._azure_client = AzureOpenAI(
                        api_key=api_key,
                        api_version=api_version,
                        azure_endpoint=endpoint,
                        timeout=60.0,
                    )
                    self._azure_deployment = deployment
            except Exception as e:
                logger.warning(f"Failed to initialize Azure for classifier: {e}")
        return self._azure_client

    def _get_claude_client(self):
        """Lazy load Anthropic Claude client."""
        if self._claude_client is None:
            try:
                import anthropic

                api_key = os.getenv("ANTHROPIC_API_KEY")
                if api_key:
                    self._claude_client = anthropic.Anthropic(api_key=api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Claude for classifier: {e}")
        return self._claude_client

    # =========================================================================
    # CACHING
    # =========================================================================

    def _compute_features_hash(self, features: Dict[str, Any]) -> str:
        """Compute hash of structural features for cache key."""
        # Use a stable JSON serialization for hashing
        serialized = json.dumps(features, sort_keys=True, default=str)
        return hashlib.md5(serialized.encode()).hexdigest()

    def _check_cache(self, features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check if classification is cached for these features."""
        features_hash = self._compute_features_hash(features)
        cache_file = self.cache_dir / f"{features_hash}.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read classification cache: {e}")
        return None

    def _save_to_cache(
        self, features: Dict[str, Any], profile: Dict[str, Any]
    ) -> None:
        """Save classification result to cache."""
        try:
            features_hash = self._compute_features_hash(features)
            cache_file = self.cache_dir / f"{features_hash}.json"
            with open(cache_file, "w") as f:
                json.dump(profile, f, indent=2, default=str)
            logger.debug(f"Cached table classification: {cache_file}")
        except Exception as e:
            logger.warning(f"Failed to save classification cache: {e}")
