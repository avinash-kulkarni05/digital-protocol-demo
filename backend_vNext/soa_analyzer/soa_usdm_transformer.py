"""
SOA USDM Transformer - Converts HTML tables to USDM 4.0 format

Uses Claude (Anthropic) as the primary LLM for transformation.

Features:
- HTML table → USDM 4.0 JSON conversion
- CDISC domain mapping integration
- Provenance tracking with page references
- Multi-table merging for protocols with multiple SOAs
- Retry logic for LLM failures

Usage:
    from soa_analyzer.soa_usdm_transformer import USDMTransformer

    transformer = USDMTransformer()

    # Transform a single table
    result = await transformer.transform(
        html_content=html,
        table_name="Main SOA",
        page_start=30,
        page_end=35,
        protocol_id="NCT12345"
    )

    # Transform multiple tables
    result = await transformer.transform_all(tables)
"""

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Prompt path
PROMPT_PATH = Path(__file__).parent / "prompts" / "usdm_transform.txt"


@dataclass
class SOATable:
    """Represents an extracted SOA table with relationship metadata."""
    table_name: str
    html_content: str
    page_start: int
    page_end: int
    footnotes: Optional[str] = None
    # Table relationship metadata
    table_category: str = "MAIN_SOA"  # MAIN_SOA, PK_SOA, PD_SOA, PG_SOA, FOLLOW_UP, SCREENING, etc.
    arm_scope: str = "ALL"  # ALL, ARM_A, TREATMENT, CONTROL, specific arm name
    population_scope: str = "ALL"  # ALL, WOCBP, MALE, FEMALE, specific population
    is_merged: bool = False  # Whether this table was merged from continuations
    continuation_count: int = 0  # Number of continuation tables merged
    # Column structure for validation
    column_headers: Optional[List[str]] = None  # Visit/timepoint column headers
    # Relationship confidence
    relationship_confidence: float = 1.0  # Confidence in the table classification


@dataclass
class USDMResult:
    """Result of USDM transformation."""
    success: bool
    data: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    protocol_id: Optional[str] = None
    source_tables: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "errors": self.errors,
            "protocol_id": self.protocol_id,
            "source_tables": self.source_tables,
        }


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


class USDMTransformer:
    """
    Transforms SOA HTML tables to USDM 4.0 format using Claude (Anthropic).

    Features:
    - 2-stage transformation (normalize → USDM)
    - CDISC domain mapping
    - Provenance tracking
    - Multi-table merging
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 8192,
        temperature: float = 0.0,
    ):
        """
        Initialize transformer.

        Args:
            api_key: Anthropic API key (falls back to ANTHROPIC_API_KEY env var)
            model: Claude model to use
            max_tokens: Maximum output tokens
            temperature: Sampling temperature
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        if not self.api_key:
            logger.warning("No Anthropic API key found. Set ANTHROPIC_API_KEY env var.")

        # Load prompt template
        self._prompt_template: Optional[str] = None
        self._load_prompt()

        logger.info(f"USDMTransformer initialized (model: {self.model})")

    def _load_prompt(self):
        """Load prompt template from file."""
        if PROMPT_PATH.exists():
            with open(PROMPT_PATH, 'r') as f:
                self._prompt_template = f.read()
            logger.info(f"Loaded USDM transformation prompt from {PROMPT_PATH}")
        else:
            logger.warning(f"Prompt template not found: {PROMPT_PATH}")
            # Use inline fallback with full context support
            self._prompt_template = """Transform this SOA HTML table to USDM 4.0 JSON.

Protocol: {protocol_id}
Table: {table_name}
Pages: {page_start}-{page_end}

{table_context}

HTML:
{html_content}

{footnotes_section}

Output USDM 4.0 JSON with: scheduleTimelines, encounters, activities, scheduledActivityInstances, timings.
Include provenance with page_number for each entity.
Include tableMetadata with tableCategory, armScope, populationScope in each scheduleTimeline.
Respond with JSON only."""

    def _build_table_context(
        self,
        table_category: str,
        arm_scope: str,
        population_scope: str,
        is_merged: bool,
        continuation_count: int,
    ) -> str:
        """
        Build context section for the transformation prompt.

        Args:
            table_category: Type of SOA table
            arm_scope: Which study arm this applies to
            population_scope: Which population this applies to
            is_merged: Whether merged from continuations
            continuation_count: Number of continuations

        Returns:
            Formatted context string
        """
        context_lines = ["## TABLE CONTEXT"]

        # Table category mapping to USDM timeline type
        category_desc = {
            "MAIN_SOA": "Primary study Schedule of Activities covering core study procedures",
            "PK_SOA": "Pharmacokinetic sampling schedule - map activities to PK domain",
            "PD_SOA": "Pharmacodynamic assessment schedule - map activities to PD domain",
            "PG_SOA": "Pharmacogenetic/biomarker collection schedule",
            "FOLLOW_UP": "Follow-up period schedule - post-treatment observations",
            "SCREENING": "Screening period schedule - pre-randomization assessments",
            "ARM_SPECIFIC": "Arm-specific schedule - applies only to specific treatment arm",
            "OTHER": "Supplementary schedule",
        }

        context_lines.append(f"- Table Category: {table_category}")
        if table_category in category_desc:
            context_lines.append(f"  Description: {category_desc[table_category]}")

        # Arm scope
        if arm_scope != "ALL":
            context_lines.append(f"- Arm Scope: {arm_scope}")
            context_lines.append(f"  NOTE: This schedule applies ONLY to subjects in the '{arm_scope}' arm.")
            context_lines.append(f"  Include studyArmId reference in the scheduleTimeline.")
        else:
            context_lines.append("- Arm Scope: ALL (applies to all study arms)")

        # Population scope
        if population_scope != "ALL":
            context_lines.append(f"- Population Scope: {population_scope}")
            context_lines.append(f"  NOTE: This schedule applies ONLY to {population_scope} subjects.")
            context_lines.append(f"  Include populationScope in the scheduleTimeline metadata.")
        else:
            context_lines.append("- Population Scope: ALL (applies to all subjects)")

        # Merged table info
        if is_merged:
            context_lines.append(f"- Merged from {continuation_count + 1} page sections")
            context_lines.append("  NOTE: This table was split across multiple pages and merged.")
            context_lines.append("  Visits/timepoints should flow continuously across the merged content.")

        return "\n".join(context_lines)

    async def _call_claude(self, prompt: str) -> str:
        """
        Call Claude API using streaming for long requests.

        Returns:
            Raw response text
        """
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.api_key)

            # Use streaming to handle long requests (>10 min) as required by Anthropic API
            collected_text = []
            with client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            ) as stream:
                for text in stream.text_stream:
                    collected_text.append(text)

            return "".join(collected_text)

        except ImportError:
            logger.error("anthropic package not installed. Run: pip install anthropic")
            raise RuntimeError("anthropic package required")
        except Exception as e:
            logger.error(f"Claude API call failed: {e}")
            raise

    async def transform(
        self,
        html_content: str,
        table_name: str,
        page_start: int,
        page_end: int,
        protocol_id: str = "UNKNOWN",
        footnotes: Optional[str] = None,
        max_retries: int = 3,
        # Table metadata for context-aware transformation
        table_category: str = "MAIN_SOA",
        arm_scope: str = "ALL",
        population_scope: str = "ALL",
        is_merged: bool = False,
        continuation_count: int = 0,
    ) -> USDMResult:
        """
        Transform a single SOA table to USDM 4.0 format.

        Args:
            html_content: HTML content of the SOA table
            table_name: Name of the table
            page_start: First page of the table
            page_end: Last page of the table
            protocol_id: Protocol identifier
            footnotes: Optional footnotes text
            max_retries: Maximum retry attempts
            table_category: Type of SOA table (MAIN_SOA, PK_SOA, etc.)
            arm_scope: Which study arm this applies to
            population_scope: Which population this applies to
            is_merged: Whether this was merged from continuation tables
            continuation_count: Number of continuation tables merged

        Returns:
            USDMResult with transformed data
        """
        if not self.api_key:
            return USDMResult(
                success=False,
                data={},
                errors=["No Anthropic API key configured"],
                protocol_id=protocol_id,
            )

        # Build footnotes section
        footnotes_section = ""
        if footnotes:
            footnotes_section = f"\nFootnotes:\n{footnotes}"

        # Build table context section for better LLM understanding
        table_context = self._build_table_context(
            table_category=table_category,
            arm_scope=arm_scope,
            population_scope=population_scope,
            is_merged=is_merged,
            continuation_count=continuation_count,
        )

        # Format prompt with context
        prompt = self._prompt_template.format(
            protocol_id=protocol_id,
            table_name=table_name,
            page_start=page_start,
            page_end=page_end,
            html_content=html_content,
            footnotes_section=footnotes_section,
            table_context=table_context,
        )

        last_error = None

        for attempt in range(max_retries):
            try:
                logger.info(f"Transforming '{table_name}' (attempt {attempt + 1}/{max_retries})")

                response = await self._call_claude(prompt)
                cleaned = _clean_json(response)
                data = json.loads(cleaned)

                # Post-process: ensure required fields with full metadata
                data = self._post_process(
                    data=data,
                    protocol_id=protocol_id,
                    table_name=table_name,
                    page_start=page_start,
                    table_category=table_category,
                    arm_scope=arm_scope,
                    population_scope=population_scope,
                    is_merged=is_merged,
                    continuation_count=continuation_count,
                )

                logger.info(f"Successfully transformed '{table_name}' ({table_category}, arm={arm_scope})")

                return USDMResult(
                    success=True,
                    data=data,
                    protocol_id=protocol_id,
                    source_tables=[table_name],
                )

            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {e}"
                logger.warning(f"Attempt {attempt + 1} failed: {last_error}")

                # Add error feedback to prompt for retry
                prompt += f"\n\nPREVIOUS ATTEMPT FAILED: {last_error}\nPlease output valid JSON only."

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Attempt {attempt + 1} failed: {last_error}")

        return USDMResult(
            success=False,
            data={},
            errors=[last_error or "Unknown error"],
            protocol_id=protocol_id,
            source_tables=[table_name],
        )

    def _post_process(
        self,
        data: Dict[str, Any],
        protocol_id: str,
        table_name: str,
        page_start: int,
        table_category: str = "MAIN_SOA",
        arm_scope: str = "ALL",
        population_scope: str = "ALL",
        is_merged: bool = False,
        continuation_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Post-process USDM data to ensure required fields and consistency.

        Args:
            data: Raw USDM data from LLM
            protocol_id: Protocol identifier
            table_name: Source table name
            page_start: First page number
            table_category: Type of SOA table
            arm_scope: Which study arm this applies to
            population_scope: Which population this applies to
            is_merged: Whether merged from continuations
            continuation_count: Number of continuations

        Returns:
            Post-processed data
        """
        # Ensure all required arrays exist
        required_arrays = [
            "scheduleTimelines",
            "encounters",
            "activities",
            "scheduledActivityInstances",
            "timings",
        ]

        for arr in required_arrays:
            if arr not in data:
                data[arr] = []

        # Ensure each entity has required fields AND table metadata
        for timeline in data.get("scheduleTimelines", []):
            if "instanceType" not in timeline:
                timeline["instanceType"] = "ScheduleTimeline"
            if "id" not in timeline:
                timeline["id"] = f"TL-{uuid.uuid4().hex[:8].upper()}"
            if "mainTimeline" not in timeline:
                timeline["mainTimeline"] = True

            # Add table metadata to timeline (USDM extension)
            timeline["tableMetadata"] = {
                "tableCategory": table_category,
                "armScope": arm_scope,
                "populationScope": population_scope,
                "isMerged": is_merged,
                "continuationCount": continuation_count,
            }

            # Map table category to USDM timeline attributes
            if table_category == "SCREENING":
                timeline["timelineType"] = "SCREENING"
            elif table_category == "FOLLOW_UP":
                timeline["timelineType"] = "FOLLOW_UP"
            elif table_category in ["PK_SOA", "PD_SOA", "PG_SOA"]:
                timeline["timelineType"] = "ASSESSMENT"
                timeline["assessmentType"] = table_category.replace("_SOA", "")
            else:
                timeline["timelineType"] = "TREATMENT"

            # Add arm reference if arm-specific
            if arm_scope != "ALL":
                timeline["studyArmScope"] = arm_scope

            # Add population reference if population-specific
            if population_scope != "ALL":
                timeline["populationScope"] = population_scope

        for encounter in data.get("encounters", []):
            if "instanceType" not in encounter:
                encounter["instanceType"] = "Encounter"
            if "id" not in encounter:
                encounter["id"] = f"ENC-{uuid.uuid4().hex[:8].upper()}"

        for activity in data.get("activities", []):
            if "instanceType" not in activity:
                activity["instanceType"] = "Activity"
            if "id" not in activity:
                activity["id"] = f"ACT-{uuid.uuid4().hex[:8].upper()}"

        for sai in data.get("scheduledActivityInstances", []):
            if "instanceType" not in sai:
                sai["instanceType"] = "ScheduledActivityInstance"
            if "id" not in sai:
                sai["id"] = f"SAI-{uuid.uuid4().hex[:8].upper()}"

        for timing in data.get("timings", []):
            if "instanceType" not in timing:
                timing["instanceType"] = "Timing"
            if "id" not in timing:
                timing["id"] = f"TIM-{uuid.uuid4().hex[:8].upper()}"

        # Add comprehensive metadata
        data["_metadata"] = {
            "protocol_id": protocol_id,
            "source_table": table_name,
            "source_page": page_start,
            "transformer_version": "1.1",
            "tableMetadata": {
                "tableCategory": table_category,
                "armScope": arm_scope,
                "populationScope": population_scope,
                "isMerged": is_merged,
                "continuationCount": continuation_count,
            },
        }

        return data

    async def transform_table(self, table: SOATable, protocol_id: str = "UNKNOWN") -> USDMResult:
        """
        Transform a SOATable object to USDM format.

        Args:
            table: SOATable object
            protocol_id: Protocol identifier

        Returns:
            USDMResult
        """
        # Get metadata from table attributes (may be dynamically set)
        table_category = getattr(table, 'table_category', 'MAIN_SOA')
        arm_scope = getattr(table, 'arm_scope', 'ALL')
        population_scope = getattr(table, 'population_scope', 'ALL')
        is_merged = getattr(table, 'is_merged', False)
        continuation_count = getattr(table, 'continuation_count', 0)

        return await self.transform(
            html_content=table.html_content,
            table_name=table.table_name,
            page_start=table.page_start,
            page_end=table.page_end,
            protocol_id=protocol_id,
            footnotes=table.footnotes,
            table_category=table_category,
            arm_scope=arm_scope,
            population_scope=population_scope,
            is_merged=is_merged,
            continuation_count=continuation_count,
        )

    async def transform_all(
        self,
        tables: List[SOATable],
        protocol_id: str = "UNKNOWN",
    ) -> USDMResult:
        """
        Transform multiple SOA tables and merge into single USDM document.

        Args:
            tables: List of SOATable objects
            protocol_id: Protocol identifier

        Returns:
            Merged USDMResult
        """
        if not tables:
            return USDMResult(
                success=False,
                data={},
                errors=["No tables provided"],
                protocol_id=protocol_id,
            )

        all_results = []
        errors = []
        source_tables = []

        for table in tables:
            result = await self.transform_table(table, protocol_id)
            if result.success:
                all_results.append(result.data)
                source_tables.append(table.table_name)
            else:
                errors.extend(result.errors)

        if not all_results:
            return USDMResult(
                success=False,
                data={},
                errors=errors or ["All transformations failed"],
                protocol_id=protocol_id,
            )

        # Merge all results
        merged = self._merge_usdm(all_results, protocol_id)

        return USDMResult(
            success=True,
            data=merged,
            errors=errors,
            protocol_id=protocol_id,
            source_tables=source_tables,
        )

    def _merge_usdm(
        self,
        results: List[Dict[str, Any]],
        protocol_id: str
    ) -> Dict[str, Any]:
        """
        Merge multiple USDM results into a single document.

        Args:
            results: List of USDM data dictionaries
            protocol_id: Protocol identifier

        Returns:
            Merged USDM document
        """
        merged = {
            "scheduleTimelines": [],
            "encounters": [],
            "activities": [],
            "scheduledActivityInstances": [],
            "timings": [],
        }

        # Track seen IDs to avoid duplicates
        seen_ids = {
            "scheduleTimelines": set(),
            "encounters": set(),
            "activities": set(),
            "scheduledActivityInstances": set(),
            "timings": set(),
        }

        for result in results:
            for key in merged.keys():
                items = result.get(key, [])
                for item in items:
                    item_id = item.get("id", "")
                    # Skip duplicates based on name (not just ID)
                    item_name = item.get("name", "")
                    dedup_key = f"{item_id}_{item_name}"
                    if dedup_key not in seen_ids[key]:
                        merged[key].append(item)
                        seen_ids[key].add(dedup_key)

        # Add merged metadata
        merged["_metadata"] = {
            "protocol_id": protocol_id,
            "table_count": len(results),
            "transformer_version": "1.0",
            "merged": True,
        }

        return merged

    def validate_usdm(self, data: Dict[str, Any]) -> List[str]:
        """
        Validate USDM data structure.

        Args:
            data: USDM data to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        required_arrays = [
            "scheduleTimelines",
            "encounters",
            "activities",
        ]

        for arr in required_arrays:
            if arr not in data:
                errors.append(f"Missing required array: {arr}")
            elif not isinstance(data[arr], list):
                errors.append(f"{arr} must be an array")
            elif len(data[arr]) == 0:
                errors.append(f"{arr} is empty")

        # Check scheduleTimelines requirements
        for i, timeline in enumerate(data.get("scheduleTimelines", [])):
            for req_field in ["id", "name", "instanceType"]:
                if req_field not in timeline:
                    errors.append(f"scheduleTimelines[{i}] missing required field: {req_field}")

        # Check encounters requirements
        for i, encounter in enumerate(data.get("encounters", [])):
            for req_field in ["id", "name", "instanceType"]:
                if req_field not in encounter:
                    errors.append(f"encounters[{i}] missing required field: {req_field}")

        # Check activities requirements
        for i, activity in enumerate(data.get("activities", [])):
            for req_field in ["id", "name", "instanceType"]:
                if req_field not in activity:
                    errors.append(f"activities[{i}] missing required field: {req_field}")

        return errors


# Singleton instance
_transformer_instance: Optional[USDMTransformer] = None


def get_transformer() -> USDMTransformer:
    """Get the singleton transformer instance."""
    global _transformer_instance
    if _transformer_instance is None:
        _transformer_instance = USDMTransformer()
    return _transformer_instance


# CLI support
if __name__ == "__main__":
    import asyncio
    import sys

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    async def main():
        if len(sys.argv) < 2:
            print("Usage: python soa_usdm_transformer.py <html_file> [protocol_id]")
            print("\nTransforms SOA HTML table to USDM 4.0 JSON.")
            sys.exit(1)

        html_path = sys.argv[1]
        protocol_id = sys.argv[2] if len(sys.argv) > 2 else "TEST"

        if not Path(html_path).exists():
            print(f"Error: File not found: {html_path}")
            sys.exit(1)

        with open(html_path, 'r') as f:
            html_content = f.read()

        transformer = get_transformer()

        result = await transformer.transform(
            html_content=html_content,
            table_name="SOA Table",
            page_start=1,
            page_end=5,
            protocol_id=protocol_id,
        )

        if result.success:
            print(json.dumps(result.data, indent=2))
        else:
            print(f"Transformation failed: {result.errors}")
            sys.exit(1)

    asyncio.run(main())
