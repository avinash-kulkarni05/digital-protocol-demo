"""
Stage 4: Alternative Resolution - Main Implementation

Identifies and resolves alternative/choice points in SOA tables where activities
have multiple options ("Test A or Test B", "CT / MRI").

Design principles:
1. LLM-First - LLM analyzes ALL activities, patterns validate
2. M:N Expansion - Handle multiple SAIs referencing same activity
3. USDM 4.0 Compliant - 6-field Code objects, Condition (not ScheduledDecisionInstance)
4. Full Provenance - Track stage, model, timestamp, cacheHit, cacheKey
5. Referential Integrity - Validate all IDs before and after expansion

Critical fixes applied (from gap analysis):
- C-01: Use Condition with conditionType (NOT ScheduledDecisionInstance)
- C-02: All Code objects have 6 fields
- C-03: Referential integrity validation
- C-04: Azure OpenAI fallback with retry
- C-05: Full provenance on all entities
- H-02: M:N activity→SAI expansion
- H-04: Multi-way alternatives (3+ options)
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..models.alternative_expansion import (
    AlternativeType,
    ResolutionAction,
    AlternativeOption,
    AlternativeDecision,
    AlternativeProvenance,
    AlternativeExpansion,
    HumanReviewItem,
    Stage4Result,
    AlternativeResolutionConfig,
    is_timing_pattern,
    is_unit_pattern,
    is_and_pattern,
    should_analyze_for_alternatives,
    generate_activity_id,
    generate_sai_id,
    generate_condition_id,
    generate_assignment_id,
)
from ..models.code_object import CodeObject, NCI_EVS_CODE_SYSTEM, NCI_EVS_VERSION

logger = logging.getLogger(__name__)

# File paths
BASE_DIR = Path(__file__).parent.parent
PATTERNS_PATH = BASE_DIR / "config" / "alternative_patterns.json"
CODES_PATH = BASE_DIR / "config" / "alternative_codes.json"
PROMPT_PATH = BASE_DIR / "prompts" / "alternative_resolution.txt"
CACHE_DIR = BASE_DIR / ".cache" / "alternative_resolution"


class AlternativePatternRegistry:
    """
    Registry for alternative patterns used for validation (NOT routing).

    LLM-first approach: patterns cross-check LLM decisions, don't drive them.
    """

    def __init__(self):
        self._patterns: Dict[str, Any] = {}
        self._codes: Dict[str, Any] = {}
        self._load_patterns()
        self._load_codes()

    def _load_patterns(self) -> None:
        """Load patterns from config file."""
        if PATTERNS_PATH.exists():
            with open(PATTERNS_PATH) as f:
                self._patterns = json.load(f)
            logger.info(f"Loaded {len(self._patterns.get('known_alternatives', {}))} known alternatives")
        else:
            logger.warning(f"Patterns file not found: {PATTERNS_PATH}")

    def _load_codes(self) -> None:
        """Load CDISC codes from config file."""
        if CODES_PATH.exists():
            with open(CODES_PATH) as f:
                self._codes = json.load(f)
            logger.info(f"Loaded CDISC codes for alternative resolution")
        else:
            logger.warning(f"Codes file not found: {CODES_PATH}")

    def is_timing_pattern(self, text: str) -> bool:
        """Check if text is a timing pattern (Stage 7 handles)."""
        timing_patterns = self._patterns.get("timing_patterns", [])
        normalized = text.lower().strip()
        return any(p.lower() in normalized for p in timing_patterns) or is_timing_pattern(text)

    def is_unit_pattern(self, text: str) -> bool:
        """Check if text contains dosing units (NOT alternatives)."""
        unit_patterns = self._patterns.get("unit_patterns", [])
        normalized = text.lower().strip()
        return any(p.lower() in normalized for p in unit_patterns) or is_unit_pattern(text)

    def is_non_alternative(self, text: str) -> bool:
        """Check if text matches non-alternative patterns."""
        non_patterns = self._patterns.get("non_alternative_patterns", [])
        normalized = text.lower().strip()
        return any(p.lower() in normalized for p in non_patterns)

    def get_known_alternative(self, text: str) -> Optional[Dict[str, Any]]:
        """Get known alternative expansion if exists."""
        known = self._patterns.get("known_alternatives", {})
        normalized = text.lower().strip()
        for key, value in known.items():
            if key.lower() in normalized or normalized in key.lower():
                return value
        return None

    def validate_decision(self, decision: AlternativeDecision) -> List[str]:
        """
        Validate LLM decision against known patterns.

        Returns list of discrepancy warnings.
        """
        discrepancies = []
        text = decision.activity_name

        # Check if LLM marked timing pattern as alternative
        if decision.is_alternative and self.is_timing_pattern(text):
            discrepancies.append(f"LLM marked timing pattern as alternative: {text}")

        # Check if LLM marked unit pattern as alternative
        if decision.is_alternative and self.is_unit_pattern(text):
            discrepancies.append(f"LLM marked unit pattern as alternative: {text}")

        # Check if LLM missed known alternative
        known = self.get_known_alternative(text)
        if known and not decision.is_alternative:
            discrepancies.append(f"LLM missed known alternative: {text}")

        # Check if known alternative has different type
        if known and decision.is_alternative:
            expected_type = known.get("type", "").lower()
            actual_type = decision.alternative_type.value if decision.alternative_type else ""
            if expected_type and actual_type and expected_type != actual_type:
                discrepancies.append(
                    f"Alternative type mismatch for '{text}': expected {expected_type}, got {actual_type}"
                )

        return discrepancies

    def get_condition_type_code(self, alternative_type: AlternativeType) -> Dict[str, Any]:
        """
        Get USDM 4.0 compliant 6-field Code object for condition type.

        NOTE: Alternative resolution codes are EXTENSION codes (not official NCI EVS).
        They use a separate code system URI to clearly distinguish from official codes.
        """
        code_map = {
            AlternativeType.MUTUALLY_EXCLUSIVE: "MUTUALLY_EXCLUSIVE",
            AlternativeType.DISCRETIONARY: "INVESTIGATOR_DISCRETION",
            AlternativeType.CONDITIONAL: "CONDITIONAL_ALTERNATIVE",
            AlternativeType.PREFERRED_WITH_FALLBACK: "PREFERRED_ALTERNATIVE",
            AlternativeType.UNCERTAIN: "ALTERNATIVE_SELECTION",
        }

        code_key = code_map.get(alternative_type, "ALTERNATIVE_SELECTION")
        codes = self._codes.get("condition_type_codes", {})
        code_data = codes.get(code_key, codes.get("ALTERNATIVE_SELECTION", {}))

        # Use extension code system for alternative resolution codes
        extension_code_system = self._codes.get("extension_code_system", {})

        return {
            "id": f"CODE-COND-TYPE-{code_data.get('code', 'UNKNOWN')}",
            "code": code_data.get("code"),
            "decode": code_data.get("decode"),
            "codeSystem": extension_code_system.get(
                "uri",
                "http://protocol-digitalization.example.org/codesystem/soa-alternative-resolution"
            ),
            "codeSystemVersion": extension_code_system.get("version", "1.0.0"),
            "instanceType": "Code",
        }


class AlternativeResolver:
    """
    Stage 4: Alternative Resolution Handler (LLM-First).

    Analyzes activities for alternatives and expands them into separate
    entities with proper conditions and referential integrity.
    """

    def __init__(self, config: Optional[AlternativeResolutionConfig] = None):
        self.config = config or AlternativeResolutionConfig()
        self._registry = AlternativePatternRegistry()
        self._cache: Dict[str, AlternativeDecision] = {}
        self._gemini_client = None
        self._azure_client = None
        self._prompt_template: str = ""
        self._load_prompt()
        self._ensure_cache_dir()

    def _load_prompt(self) -> None:
        """Load LLM prompt template."""
        if PROMPT_PATH.exists():
            with open(PROMPT_PATH) as f:
                self._prompt_template = f.read()
            logger.info("Loaded alternative resolution prompt")
        else:
            raise FileNotFoundError(f"Required prompt file not found: {PROMPT_PATH}")

    def _ensure_cache_dir(self) -> None:
        """Ensure cache directory exists."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # =========== Main Entry Point ===========

    async def resolve_alternatives(self, usdm_output: Dict[str, Any]) -> Stage4Result:
        """
        Process all activities and resolve alternatives.

        Steps:
        1. Extract activities with potential alternatives
        2. Filter out timing patterns, unit patterns, "and" patterns
        3. Check cache for each activity
        4. Send uncached to LLM in batches
        5. Validate LLM decisions against patterns
        6. Generate expanded entities (activities, SAIs, conditions)
        7. Validate referential integrity
        """
        result = Stage4Result()

        # Extract candidate activities
        activities = usdm_output.get("activities", [])
        sais = usdm_output.get("scheduledActivityInstances", [])

        candidates = self._extract_candidate_activities(activities, result)
        result.activities_analyzed = len(candidates)

        if not candidates:
            logger.info("No candidate activities found for alternative resolution")
            return result

        logger.info(f"Analyzing {len(candidates)} candidate activities for alternatives")

        # Check cache and collect uncached
        uncached = []
        for activity in candidates:
            cache_key = self._get_cache_key(activity["name"])
            cached = self._check_cache(cache_key)

            if cached:
                result.cache_hits += 1
                cached.source = "cache"
                result.decisions[activity["id"]] = cached
            else:
                uncached.append(activity)

        # LLM batch analysis for uncached
        if uncached:
            try:
                llm_decisions = await self._analyze_batch(uncached)
                result.llm_calls += 1

                for activity_id, decision in llm_decisions.items():
                    # Validate against patterns
                    discrepancies = self._registry.validate_decision(decision)
                    if discrepancies:
                        result.validation_discrepancies += len(discrepancies)
                        for d in discrepancies:
                            logger.warning(f"Validation discrepancy: {d}")

                    # Cache the decision
                    cache_key = self._get_cache_key(decision.activity_name)
                    self._update_cache(cache_key, decision)

                    result.decisions[activity_id] = decision

            except Exception as e:
                logger.error(f"LLM analysis failed: {e}")
                # Mark all uncached as needing review
                for activity in uncached:
                    result.decisions[activity["id"]] = AlternativeDecision(
                        activity_id=activity["id"],
                        activity_name=activity["name"],
                        is_alternative=False,
                        recommended_action=ResolutionAction.REVIEW,
                        confidence=0.0,
                        rationale=f"LLM analysis failed: {e}",
                        requires_human_review=True,
                        review_reason=str(e),
                    )
                    result.needs_review += 1

        # Count detected alternatives
        for decision in result.decisions.values():
            if decision.is_alternative:
                result.alternatives_detected += 1

        # Generate expansions for high-confidence alternatives
        for activity_id, decision in result.decisions.items():
            if not decision.is_alternative:
                continue

            if decision.confidence >= self.config.confidence_threshold_auto:
                if decision.recommended_action in [ResolutionAction.EXPAND, ResolutionAction.CONDITION]:
                    # Find original activity
                    original_activity = next(
                        (a for a in activities if a["id"] == activity_id), None
                    )
                    if original_activity:
                        expansion = self._generate_expansion(
                            original_activity, decision, sais, usdm_output
                        )
                        # Resolve any nested alternatives using LLM
                        # (e.g., CT/MRI within expanded activities)
                        expansion = await self._resolve_nested_alternatives_llm(expansion, sais)
                        result.add_expansion(expansion)
            else:
                # Flag for review
                review_item = HumanReviewItem(
                    id=f"REVIEW-ALT-{activity_id}",
                    item_type="alternative",
                    activity_id=activity_id,
                    activity_name=decision.activity_name,
                    reason=decision.review_reason or f"Low confidence: {decision.confidence:.2f}",
                    confidence=decision.confidence,
                    alternatives=[alt.name for alt in decision.alternatives],
                    proposed_resolution=decision.to_dict(),
                )
                result.review_items.append(review_item)
                result.needs_review += 1

        # Save cache to disk
        self._save_cache()

        return result

    def apply_resolutions_to_usdm(
        self, usdm: Dict[str, Any], result: Stage4Result
    ) -> Dict[str, Any]:
        """
        Apply alternative resolutions to USDM structure.

        Steps:
        1. Validate referential integrity (pre)
        2. Remove original activities that were expanded
        3. Add expanded activities
        4. Remove original SAIs that were expanded
        5. Add expanded SAIs
        6. Add conditions and assignments
        7. Validate referential integrity (post)
        """
        if not result.expansions:
            return usdm

        # Deep copy to avoid mutation
        updated = json.loads(json.dumps(usdm))

        # Collect IDs to remove and entities to add
        activities_to_remove: Set[str] = set()
        sais_to_remove: Set[str] = set()
        new_activities: List[Dict] = []
        new_sais: List[Dict] = []
        new_conditions: List[Dict] = []
        new_assignments: List[Dict] = []

        for expansion in result.expansions:
            activities_to_remove.add(expansion.original_activity_id)
            new_activities.extend(expansion.expanded_activities)

            # Collect original SAIs to remove
            for new_sai in expansion.expanded_sais:
                original_sai_id = new_sai.get("_alternativeResolution", {}).get("originalSaiId")
                if original_sai_id:
                    sais_to_remove.add(original_sai_id)

            new_sais.extend(expansion.expanded_sais)
            new_conditions.extend(expansion.conditions_created)
            new_assignments.extend(expansion.assignments_created)

        # Pre-validation: check for ID collisions
        existing_activity_ids = {a["id"] for a in updated.get("activities", [])}
        existing_sai_ids = {s["id"] for s in updated.get("scheduledActivityInstances", [])}
        existing_condition_ids = {c["id"] for c in updated.get("conditions", [])}

        collision_errors = []
        for act in new_activities:
            if act["id"] in existing_activity_ids and act["id"] not in activities_to_remove:
                collision_errors.append(f"Activity ID collision: {act['id']}")
        for sai in new_sais:
            if sai["id"] in existing_sai_ids and sai["id"] not in sais_to_remove:
                collision_errors.append(f"SAI ID collision: {sai['id']}")
        for cond in new_conditions:
            if cond["id"] in existing_condition_ids:
                collision_errors.append(f"Condition ID collision: {cond['id']}")

        if collision_errors:
            result.referential_integrity_errors = len(collision_errors)
            for err in collision_errors:
                logger.error(err)
            raise ValueError(f"Referential integrity errors: {collision_errors}")

        # Apply changes
        updated["activities"] = [
            a for a in updated.get("activities", [])
            if a["id"] not in activities_to_remove
        ] + new_activities

        updated["scheduledActivityInstances"] = [
            s for s in updated.get("scheduledActivityInstances", [])
            if s["id"] not in sais_to_remove
        ] + new_sais

        # Ensure conditions and conditionAssignments arrays exist
        if "conditions" not in updated:
            updated["conditions"] = []
        if "conditionAssignments" not in updated:
            updated["conditionAssignments"] = []

        updated["conditions"].extend(new_conditions)
        updated["conditionAssignments"].extend(new_assignments)

        # Post-validation: check referential integrity
        self._validate_referential_integrity(updated, result)

        return updated

    # =========== Activity Extraction ===========

    def _extract_candidate_activities(
        self, activities: List[Dict], result: Stage4Result
    ) -> List[Dict]:
        """Extract activities that should be analyzed for alternatives."""
        candidates = []

        for activity in activities:
            name = activity.get("name", "")

            # Skip timing patterns
            if self._registry.is_timing_pattern(name):
                result.timing_patterns_filtered += 1
                continue

            # Skip unit patterns
            if self._registry.is_unit_pattern(name):
                result.unit_patterns_filtered += 1
                continue

            # Check for alternative markers
            if should_analyze_for_alternatives(name):
                candidates.append(activity)

        return candidates

    # =========== LLM Analysis ===========

    async def _analyze_batch(
        self, activities: List[Dict]
    ) -> Dict[str, AlternativeDecision]:
        """
        Analyze batch of activities using LLM.

        Implements Azure fallback and retry logic.
        """
        # Build prompt
        activities_json = json.dumps([
            {"id": a["id"], "name": a["name"]}
            for a in activities
        ], indent=2)

        prompt = self._prompt_template.replace(
            "{activities_json}", activities_json
        ).replace(
            "{activity_count}", str(len(activities))
        )

        # Try Gemini first, then Azure fallback
        response_text = await self._call_llm_with_fallback(prompt)

        if not response_text:
            raise Exception("All LLM providers failed")

        # Parse response
        return self._parse_llm_response(response_text, activities)

    async def _call_llm_with_fallback(self, prompt: str) -> Optional[str]:
        """Call LLM with Gemini primary, Claude fallback, Azure last fallback."""
        # Try Gemini
        for attempt in range(self.config.max_retries):
            try:
                response = await self._call_gemini(prompt)
                if response:
                    return response
            except Exception as e:
                logger.warning(f"Gemini attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

        # Fallback to Claude
        logger.info("Gemini failed - falling back to Anthropic Claude...")
        for attempt in range(self.config.max_retries):
            try:
                response = await self._call_claude(prompt)
                if response:
                    return response
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
                    return response
            except Exception as e:
                logger.warning(f"Azure attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        return None

    async def _call_gemini(self, prompt: str) -> Optional[str]:
        """Call Gemini API."""
        try:
            import google.generativeai as genai

            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not set")

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(self.config.model_name)

            response = await asyncio.wait_for(
                asyncio.to_thread(
                    model.generate_content,
                    prompt,
                    generation_config=genai.GenerationConfig(
                        max_output_tokens=8192,
                        temperature=0.1,
                    ),
                ),
                timeout=self.config.timeout_seconds,
            )

            return response.text
        except Exception as e:
            logger.error(f"Gemini call failed: {e}")
            raise

    async def _call_claude(self, prompt: str) -> Optional[str]:
        """Call Anthropic Claude API."""
        try:
            import anthropic

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not set")

            client = anthropic.Anthropic(api_key=api_key)

            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.messages.create,
                    model="claude-sonnet-4-20250514",
                    max_tokens=8192,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=self.config.timeout_seconds,
            )

            content = response.content[0].text if response.content else None
            if content:
                logger.info(f"Anthropic Claude responded ({len(content)} chars)")
            return content
        except Exception as e:
            logger.error(f"Claude call failed: {e}")
            raise

    async def _call_azure(self, prompt: str) -> Optional[str]:
        """Call Azure OpenAI API."""
        try:
            from openai import AzureOpenAI

            client = AzureOpenAI(
                api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
                azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
            )

            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.chat.completions.create,
                    model=os.environ.get("AZURE_OPENAI_DEPLOYMENT", self.config.azure_model_name),
                    messages=[
                        {"role": "system", "content": "You are a clinical trial protocol expert."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=8192,
                    temperature=0.1,
                ),
                timeout=self.config.timeout_seconds,
            )

            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Azure call failed: {e}")
            raise

    def _parse_llm_response(
        self, response_text: str, activities: List[Dict]
    ) -> Dict[str, AlternativeDecision]:
        """Parse LLM JSON response into AlternativeDecision objects."""
        decisions = {}

        # Clean response (remove markdown code blocks if present)
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"```json?\s*", "", cleaned)
            cleaned = re.sub(r"```\s*$", "", cleaned)

        try:
            response_data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.debug(f"Response text: {response_text[:500]}...")
            # Return empty decisions for all activities
            for activity in activities:
                decisions[activity["id"]] = AlternativeDecision(
                    activity_id=activity["id"],
                    activity_name=activity["name"],
                    is_alternative=False,
                    recommended_action=ResolutionAction.REVIEW,
                    confidence=0.0,
                    rationale="Failed to parse LLM response",
                    requires_human_review=True,
                    review_reason=str(e),
                )
            return decisions

        # Parse each activity's decision
        for activity in activities:
            activity_id = activity["id"]
            if activity_id in response_data:
                decisions[activity_id] = AlternativeDecision.from_llm_response(
                    activity_id, response_data[activity_id], self.config.model_name
                )
            else:
                # Activity not in response - keep as-is
                decisions[activity_id] = AlternativeDecision(
                    activity_id=activity_id,
                    activity_name=activity["name"],
                    is_alternative=False,
                    recommended_action=ResolutionAction.KEEP,
                    confidence=1.0,
                    rationale="Not returned in LLM response - keeping original",
                )

        return decisions

    # =========== Expansion Generation ===========

    def _generate_expansion(
        self,
        activity: Dict,
        decision: AlternativeDecision,
        all_sais: List[Dict],
        usdm: Dict,
    ) -> AlternativeExpansion:
        """Generate expanded activities, SAIs, and conditions for an alternative."""
        expansion = AlternativeExpansion(
            id=f"EXP-{activity['id']}",
            original_activity_id=activity["id"],
            original_activity_name=activity["name"],
            decision=decision,
            confidence=decision.confidence,
            alternative_type=decision.alternative_type or AlternativeType.MUTUALLY_EXCLUSIVE,
        )

        # Find ALL SAIs referencing this activity (M:N handling)
        affected_sais = [
            sai for sai in all_sais
            if sai.get("activityId") == activity["id"]
        ]

        # Generate expanded activities
        for i, alt in enumerate(decision.alternatives, 1):
            new_activity_id = generate_activity_id(activity["id"], i, len(decision.alternatives))
            suffix = chr(ord('A') + i - 1) if i <= 26 else str(i)

            provenance = AlternativeProvenance(
                original_activity_id=activity["id"],
                original_activity_name=activity["name"],
                alternative_type=decision.alternative_type.value if decision.alternative_type else "unknown",
                alternative_index=i,
                alternative_count=len(decision.alternatives),
                confidence=decision.confidence,
                rationale=decision.rationale,
                model=self.config.model_name,
                timestamp=datetime.utcnow().isoformat() + "Z",
                source=decision.source,
                cache_hit=decision.source == "cache",
                cache_key=decision.get_cache_key(self.config.model_name),
            )

            new_activity = {
                "id": new_activity_id,
                "name": alt.name,
                "instanceType": "Activity",
                # Preserve original fields
                "cdiscDomain": alt.cdisc_domain or activity.get("cdiscDomain"),
                "_alternativeResolution": provenance.to_dict(),
            }

            # Preserve other original fields
            for key in ["description", "biomedicalConceptId", "procedureType"]:
                if key in activity:
                    new_activity[key] = activity[key]

            expansion.expanded_activities.append(new_activity)

            # Generate condition for this alternative
            condition_id = generate_condition_id(activity["id"], i)
            condition_type_code = self._registry.get_condition_type_code(
                decision.alternative_type or AlternativeType.MUTUALLY_EXCLUSIVE
            )

            condition = {
                "id": condition_id,
                "instanceType": "Condition",
                "name": f"{alt.name} selected",
                "text": f"Subject assigned to {alt.name} option for {activity['name']}",
                "conditionType": condition_type_code,
                "_alternativeResolution": {
                    "originalActivityId": activity["id"],
                    "alternativeIndex": i,
                    "alternativeName": alt.name,
                    "stage": "Stage4AlternativeResolution",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
            }
            expansion.conditions_created.append(condition)

            # Generate SAIs for each affected SAI
            for sai in affected_sais:
                new_sai_id = generate_sai_id(sai["id"], suffix)

                new_sai = {
                    "id": new_sai_id,
                    "instanceType": sai.get("instanceType", "ScheduledActivityInstance"),
                    "activityId": new_activity_id,
                    "scheduledInstanceEncounterId": sai.get(
                        "scheduledInstanceEncounterId", sai.get("visitId")
                    ),
                    "defaultConditionId": condition_id,
                    "isRequired": sai.get("isRequired", True),
                    "footnoteMarkers": sai.get("footnoteMarkers", []).copy(),
                    "_alternativeResolution": {
                        "originalSaiId": sai["id"],
                        "originalActivityId": activity["id"],
                        "alternativeIndex": i,
                        "alternativeName": alt.name,
                        "stage": "Stage4AlternativeResolution",
                        "model": self.config.model_name,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "confidence": decision.confidence,
                        "source": decision.source,
                        "cacheHit": decision.source == "cache",
                    },
                }

                # Preserve timing modifier if present
                if "timingModifier" in sai:
                    new_sai["timingModifier"] = sai["timingModifier"]

                expansion.expanded_sais.append(new_sai)

                # Generate condition assignment
                assignment_id = generate_assignment_id(condition_id, new_sai_id)
                assignment = {
                    "id": assignment_id,
                    "instanceType": "ConditionAssignment",
                    "conditionId": condition_id,
                    "conditionTargetId": new_sai_id,
                    "_alternativeResolution": {
                        "stage": "Stage4AlternativeResolution",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    },
                }
                expansion.assignments_created.append(assignment)

        return expansion

    # =========== Nested Alternative Resolution ===========

    async def _resolve_nested_alternatives_llm(
        self,
        expansion: AlternativeExpansion,
        all_sais: List[Dict],
    ) -> AlternativeExpansion:
        """
        Check expanded activities for nested alternatives using LLM analysis.

        Uses the same LLM-based approach as the main alternative resolution
        to properly understand semantic meaning of compound terms.

        Example: "Bone Scan or 18F FDG PET/CT or CT/MRI" expands to:
        - Bone Scan (ok)
        - 18F FDG PET/CT (ok - LLM recognizes as single combined modality)
        - CT/MRI (LLM identifies as alternative) -> CT and MRI separately

        Returns the expansion with nested alternatives resolved.
        """
        # Check each expanded activity for potential nested alternatives
        # Use simple pattern detection to identify CANDIDATES, but let LLM decide
        candidates = []
        non_candidates = []

        for activity in expansion.expanded_activities:
            name = activity.get("name", "")
            # Simple heuristic: if it has "/" or " or ", send to LLM for analysis
            if "/" in name or " or " in name.lower():
                candidates.append(activity)
            else:
                non_candidates.append(activity)

        if not candidates:
            return expansion  # No potential nested alternatives

        logger.info(f"Found {len(candidates)} potential nested alternatives - analyzing with LLM")

        # Analyze candidates using LLM (same approach as main analysis)
        nested_decisions = await self._analyze_batch(candidates)

        # Process LLM decisions
        activities_final = non_candidates.copy()

        for activity in candidates:
            activity_id = activity["id"]
            decision = nested_decisions.get(activity_id)

            if not decision or not decision.is_alternative:
                # LLM says it's NOT an alternative (e.g., "PET/CT" is single modality)
                activities_final.append(activity)
                logger.info(f"  LLM: '{activity['name']}' is NOT an alternative - keeping as-is")
                continue

            if decision.recommended_action != ResolutionAction.EXPAND:
                # LLM doesn't recommend expansion
                activities_final.append(activity)
                continue

            logger.info(
                f"  LLM: '{activity['name']}' -> {[a.name for a in decision.alternatives]} "
                f"(type={decision.alternative_type}, confidence={decision.confidence})"
            )

            # Get base ID (remove existing suffix)
            base_id = activity["id"]
            original_suffix = base_id.split("-")[-1] if "-" in base_id else ""

            # Find SAIs for this activity
            activity_sais = [
                sai for sai in expansion.expanded_sais
                if sai.get("activityId") == activity["id"]
            ]

            # Remove old SAIs for this activity
            expansion.expanded_sais = [
                sai for sai in expansion.expanded_sais
                if sai.get("activityId") != activity["id"]
            ]

            # Remove old condition for this activity
            old_condition_id = activity_sais[0].get("defaultConditionId") if activity_sais else None
            if old_condition_id:
                expansion.conditions_created = [
                    c for c in expansion.conditions_created
                    if c.get("id") != old_condition_id
                ]
                expansion.assignments_created = [
                    a for a in expansion.assignments_created
                    if a.get("conditionId") != old_condition_id
                ]

            # Create expanded activities for each LLM-identified alternative
            for i, alt in enumerate(decision.alternatives, 1):
                # Generate new sub-suffix (e.g., C1, C2 for nested under C)
                sub_suffix = f"{original_suffix}{i}"
                new_activity_id = f"{base_id.rsplit('-', 1)[0]}-{sub_suffix}"

                new_activity = {
                    "id": new_activity_id,
                    "name": alt.name,
                    "instanceType": "Activity",
                    "cdiscDomain": alt.cdisc_domain or activity.get("cdiscDomain"),
                    "_alternativeResolution": {
                        **activity.get("_alternativeResolution", {}),
                        "nestedResolution": True,
                        "parentAlternativeName": activity["name"],
                        "nestedAlternativeIndex": i,
                        "nestedAlternativeCount": len(decision.alternatives),
                        "llmAnalyzed": True,
                        "llmConfidence": decision.confidence,
                        "llmAlternativeType": decision.alternative_type.value if decision.alternative_type else None,
                    },
                }
                activities_final.append(new_activity)

                # Create new condition for this nested alternative
                condition_id = f"COND-ALT-NESTED-{new_activity_id.replace('ACT-', '')}"
                condition_type_code = self._registry.get_condition_type_code(
                    decision.alternative_type or AlternativeType.MUTUALLY_EXCLUSIVE
                )

                condition = {
                    "id": condition_id,
                    "instanceType": "Condition",
                    "name": f"{alt.name} selected",
                    "text": f"Subject assigned to {alt.name} option (nested from {activity['name']})",
                    "conditionType": condition_type_code,
                    "_alternativeResolution": {
                        "originalActivityId": activity["id"],
                        "nestedAlternativeIndex": i,
                        "nestedAlternativeName": alt.name,
                        "parentAlternativeName": activity["name"],
                        "stage": "Stage4AlternativeResolution",
                        "nestedResolution": True,
                        "llmAnalyzed": True,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                    },
                }
                expansion.conditions_created.append(condition)

                # Create SAIs for each original SAI
                for sai in activity_sais:
                    new_sai_id = f"{sai['id'].rsplit('-', 1)[0]}-{sub_suffix}"
                    new_sai = {
                        "id": new_sai_id,
                        "instanceType": sai.get("instanceType", "ScheduledActivityInstance"),
                        "activityId": new_activity_id,
                        "scheduledInstanceEncounterId": sai.get("scheduledInstanceEncounterId"),
                        "defaultConditionId": condition_id,
                        "isRequired": sai.get("isRequired", True),
                        "footnoteMarkers": sai.get("footnoteMarkers", []).copy(),
                        "_alternativeResolution": {
                            **sai.get("_alternativeResolution", {}),
                            "nestedResolution": True,
                            "parentAlternativeName": activity["name"],
                            "nestedAlternativeIndex": i,
                            "llmAnalyzed": True,
                        },
                    }
                    if "timingModifier" in sai:
                        new_sai["timingModifier"] = sai["timingModifier"]
                    expansion.expanded_sais.append(new_sai)

                    # Create condition assignment
                    assignment_id = generate_assignment_id(condition_id, new_sai_id)
                    assignment = {
                        "id": assignment_id,
                        "instanceType": "ConditionAssignment",
                        "conditionId": condition_id,
                        "conditionTargetId": new_sai_id,
                        "_alternativeResolution": {
                            "stage": "Stage4AlternativeResolution",
                            "nestedResolution": True,
                            "llmAnalyzed": True,
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                        },
                    }
                    expansion.assignments_created.append(assignment)

        expansion.expanded_activities = activities_final
        return expansion

    # =========== Referential Integrity ===========

    def _validate_referential_integrity(
        self, usdm: Dict, result: Stage4Result
    ) -> None:
        """Validate referential integrity after expansion."""
        errors = []

        # Build ID sets
        activity_ids = {a["id"] for a in usdm.get("activities", [])}
        encounter_ids = {e["id"] for e in usdm.get("encounters", [])}
        condition_ids = {c["id"] for c in usdm.get("conditions", [])}

        # Validate SAI references
        for sai in usdm.get("scheduledActivityInstances", []):
            # Check activityId
            if sai.get("activityId") and sai["activityId"] not in activity_ids:
                errors.append(f"SAI {sai['id']} references non-existent activity: {sai['activityId']}")

            # Check encounter reference
            enc_id = sai.get("scheduledInstanceEncounterId") or sai.get("visitId")
            if enc_id and enc_id not in encounter_ids:
                errors.append(f"SAI {sai['id']} references non-existent encounter: {enc_id}")

            # Check condition reference
            cond_id = sai.get("defaultConditionId")
            if cond_id and cond_id not in condition_ids:
                errors.append(f"SAI {sai['id']} references non-existent condition: {cond_id}")

        # Validate condition assignment references
        sai_ids = {s["id"] for s in usdm.get("scheduledActivityInstances", [])}
        for assignment in usdm.get("conditionAssignments", []):
            if assignment.get("conditionId") not in condition_ids:
                errors.append(
                    f"Assignment {assignment['id']} references non-existent condition: {assignment.get('conditionId')}"
                )
            if assignment.get("conditionTargetId") not in sai_ids:
                errors.append(
                    f"Assignment {assignment['id']} references non-existent SAI: {assignment.get('conditionTargetId')}"
                )

        if errors:
            result.referential_integrity_errors = len(errors)
            for err in errors:
                logger.error(f"Referential integrity error: {err}")

    # =========== Caching ===========

    def _get_cache_key(self, activity_name: str) -> str:
        """Generate cache key including model version."""
        normalized = activity_name.lower().strip()
        key_source = f"{normalized}:{self.config.model_name}"
        return hashlib.md5(key_source.encode()).hexdigest()

    def _check_cache(self, cache_key: str) -> Optional[AlternativeDecision]:
        """Check in-memory and disk cache."""
        # Check in-memory first
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Check disk cache
        cache_file = CACHE_DIR / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)

                # Reconstruct AlternativeDecision
                decision = AlternativeDecision(
                    activity_id=data.get("activityId", ""),
                    activity_name=data.get("activityName", ""),
                    is_alternative=data.get("isAlternative", False),
                    alternative_type=AlternativeType(data["alternativeType"]) if data.get("alternativeType") else None,
                    alternatives=[
                        AlternativeOption(
                            name=alt["name"],
                            order=alt["order"],
                            confidence=alt.get("confidence", 1.0),
                        )
                        for alt in data.get("alternatives", [])
                    ],
                    recommended_action=ResolutionAction(data.get("recommendedAction", "keep")),
                    confidence=data.get("confidence", 1.0),
                    rationale=data.get("rationale"),
                    source="cache",
                    cached_at=data.get("cachedAt"),
                    model_name=data.get("modelName"),
                )

                # Store in memory cache
                self._cache[cache_key] = decision
                return decision

            except Exception as e:
                logger.warning(f"Failed to load cache file {cache_file}: {e}")

        return None

    def _update_cache(self, cache_key: str, decision: AlternativeDecision) -> None:
        """Update in-memory cache."""
        self._cache[cache_key] = decision

    def _save_cache(self) -> None:
        """Save in-memory cache to disk."""
        for cache_key, decision in self._cache.items():
            cache_file = CACHE_DIR / f"{cache_key}.json"
            try:
                with open(cache_file, "w") as f:
                    json.dump(decision.to_dict(), f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to save cache file {cache_file}: {e}")


# =========== Convenience Functions ===========

async def resolve_alternatives(
    usdm_output: Dict[str, Any],
    config: Optional[AlternativeResolutionConfig] = None,
) -> Tuple[Dict[str, Any], Stage4Result]:
    """
    Convenience function to resolve alternatives in USDM output.

    Returns: (updated_usdm, result)
    """
    resolver = AlternativeResolver(config)
    result = await resolver.resolve_alternatives(usdm_output)
    updated_usdm = resolver.apply_resolutions_to_usdm(usdm_output, result)
    return updated_usdm, result
