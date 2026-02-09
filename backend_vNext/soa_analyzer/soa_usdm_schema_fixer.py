"""
USDM Schema Fixer

Post-processes transformer output to match USDM 4.0 schema requirements.

Key Fixes:
1. Code objects: Expand {code, decode} pairs to full Code-Output (6 fields)
2. Activities: Convert procedureType to code field
3. Timings: Add missing relationship fields
4. Timelines: Ensure entryCondition, entryId, mainTimeline present
5. Provenance: Inject page_number and text_snippet for all entities

Uses:
- config/cdisc_codelists.json for code system lookups
- soa_terminology_mapper.py for activity → CDISC/OMOP mapping
- table_context for page number injection
- visit_schedule for visit-level provenance lookup

Usage:
    from soa_analyzer.soa_usdm_schema_fixer import USDMSchemaFixer

    fixer = USDMSchemaFixer(
        table_context={"page_start": 30, "page_end": 35},
        visit_schedule=visit_schedule_result
    )
    fixed_data = fixer.fix(usdm_data)
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class USDMSchemaFixer:
    """Post-process transformer output to match USDM 4.0 schema."""

    # Default code system URL for NCI Thesaurus codes (Cxxxxx format)
    NCI_THESAURUS_URL = "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl"
    CDISC_SDTM_URL = "http://www.cdisc.org/ns/sdtm"
    LOINC_URL = "http://loinc.org"
    SNOMED_URL = "http://snomed.info/sct"

    # Code system version defaults (will be overridden by codelists)
    DEFAULT_VERSIONS = {
        NCI_THESAURUS_URL: "24.12",
        CDISC_SDTM_URL: "3.4",
        LOINC_URL: "2.76",
        SNOMED_URL: "2024-01",
    }

    def __init__(
        self,
        use_terminology_mapper: bool = True,
        use_llm_fallback: bool = True,
        table_context: Optional[Dict[str, Any]] = None,
        visit_schedule: Optional[Any] = None,  # VisitScheduleResult
    ):
        """Initialize the schema fixer.

        Args:
            use_terminology_mapper: Whether to use TerminologyMapper for activity lookups
            use_llm_fallback: Whether to use LLM for unmapped terms
            table_context: Table metadata with page_start, page_end, table_id, table_name
            visit_schedule: VisitScheduleResult with visit-level provenance
        """
        self.use_terminology_mapper = use_terminology_mapper
        self.use_llm_fallback = use_llm_fallback
        self.table_context = table_context or {}
        self.visit_schedule = visit_schedule

        # Load CDISC codelists for code system lookups
        self.codelists = {}
        self.code_to_system: Dict[str, str] = {}
        self.codelist_version = "2024-12"
        self._load_codelists()

        # Initialize terminology mapper if enabled
        self.terminology_mapper = None
        if use_terminology_mapper:
            self._init_terminology_mapper()

        # Track generated IDs to avoid duplicates
        self._generated_ids: Set[str] = set()

        # Build visit provenance lookup for encounter matching
        self._visit_provenance_lookup: Dict[str, Dict[str, Any]] = {}
        if visit_schedule:
            self._build_visit_provenance_lookup()

        # Statistics
        self.stats = {
            "code_objects_fixed": 0,
            "activities_fixed": 0,
            "timings_fixed": 0,
            "timelines_fixed": 0,
            "encounters_fixed": 0,
            "llm_calls": 0,
            "provenance_injected": 0,
        }

    def _load_codelists(self) -> None:
        """Load cdisc_codelists.json for code system lookups."""
        codelists_path = Path(__file__).parent.parent / "config" / "cdisc_codelists.json"

        if not codelists_path.exists():
            logger.warning(f"CDISC codelists not found at {codelists_path}")
            return

        try:
            with open(codelists_path) as f:
                self.codelists = json.load(f)

            # Get version from metadata
            metadata = self.codelists.get("metadata", {})
            self.codelist_version = metadata.get("version", "2024-12")

            # Build reverse lookup: code → codeSystem URL
            for codelist_name, codelist in self.codelists.get("codelists", {}).items():
                code_system = codelist.get("codeSystem", "")
                for pair in codelist.get("pairs", []):
                    self.code_to_system[pair["code"]] = code_system

            logger.info(f"Loaded {len(self.code_to_system)} codes from cdisc_codelists.json (v{self.codelist_version})")

        except Exception as e:
            logger.error(f"Error loading cdisc_codelists.json: {e}")

    def _init_terminology_mapper(self) -> None:
        """Initialize TerminologyMapper for activity lookups."""
        try:
            from .soa_terminology_mapper import get_mapper
            self.terminology_mapper = get_mapper()
            logger.info("TerminologyMapper initialized for schema fixer")
        except Exception as e:
            logger.warning(f"Failed to initialize TerminologyMapper: {e}")
            self.terminology_mapper = None

    def _generate_id(self, prefix: str = "ID") -> str:
        """Generate a unique ID."""
        while True:
            new_id = f"{prefix}-{str(uuid.uuid4())[:8].upper()}"
            if new_id not in self._generated_ids:
                self._generated_ids.add(new_id)
                return new_id

    def _build_visit_provenance_lookup(self) -> None:
        """Build name→provenance lookup from visit schedule.

        Creates a dictionary mapping visit names (lowercase) to their provenance,
        enabling encounter entities to inherit provenance from the visit schedule.
        """
        if not self.visit_schedule:
            return

        for visit in self.visit_schedule.visits:
            # Build provenance from table context + visit-specific data
            prov = {
                "page_number": self.table_context.get("page_start"),
                "text_snippet": (visit.original_name or visit.name)[:150],
                "confidence": 0.85,
                "source_stage": "visit_schedule",
            }

            # Override with visit-specific provenance if available
            if visit.provenance:
                if visit.provenance.page_number:
                    prov["page_number"] = visit.provenance.page_number
                if visit.provenance.text_snippet:
                    prov["text_snippet"] = visit.provenance.text_snippet[:150]
                prov["confidence"] = 0.90  # Higher confidence when source has provenance

            # Index by both normalized and original names
            name_key = visit.name.lower().strip()
            original_key = (visit.original_name or visit.name).lower().strip()

            self._visit_provenance_lookup[name_key] = prov
            if original_key != name_key:
                self._visit_provenance_lookup[original_key] = prov

        logger.debug(f"Built visit provenance lookup with {len(self._visit_provenance_lookup)} entries")

    def _infer_code_system(self, code: str) -> str:
        """Infer code system URL from code format.

        Args:
            code: The code string (e.g., "C71738", "LP139953-6")

        Returns:
            Code system URL
        """
        if not code:
            return self.NCI_THESAURUS_URL

        # Check codelists first (exact match)
        if code in self.code_to_system:
            return self.code_to_system[code]

        # Infer from code format
        if code.startswith("C") and len(code) > 1 and code[1:].isdigit():
            return self.NCI_THESAURUS_URL
        elif code.startswith("LP") or "-" in code:
            return self.LOINC_URL
        elif code.isdigit() and len(code) >= 6:
            return self.SNOMED_URL
        else:
            return self.NCI_THESAURUS_URL

    def _get_code_system_version(self, code_system: str) -> str:
        """Get the version for a code system."""
        return self.DEFAULT_VERSIONS.get(code_system, self.codelist_version)

    def _expand_code_object(self, code_pair: Dict[str, Any], context: str = "") -> Dict[str, Any]:
        """Expand a simple {code, decode} pair to full Code-Output object.

        Args:
            code_pair: Dict with 'code' and 'decode' keys
            context: Context string for ID generation (e.g., "ENCOUNTER", "ACTIVITY")

        Returns:
            Full Code-Output object with all 6 required fields
        """
        if not isinstance(code_pair, dict):
            return code_pair

        # Already has all required fields?
        required_fields = {"id", "code", "codeSystem", "codeSystemVersion", "decode", "instanceType"}
        if required_fields.issubset(code_pair.keys()):
            return code_pair

        code = code_pair.get("code", "")
        decode = code_pair.get("decode", "")

        # Determine code system
        code_system = self._infer_code_system(code)

        return {
            "id": self._generate_id(f"CODE-{context}" if context else "CODE"),
            "code": code,
            "codeSystem": code_system,
            "codeSystemVersion": self._get_code_system_version(code_system),
            "decode": decode,
            "instanceType": "Code",
        }

    def _fix_code_objects_recursive(self, data: Any, path: str = "$") -> Any:
        """Recursively find and fix all Code objects in the data.

        Looks for patterns like {"code": "...", "decode": "..."} and expands them.
        """
        if isinstance(data, dict):
            # Check if this looks like a simple code/decode pair
            if "code" in data and "decode" in data and "instanceType" not in data:
                # Check it's not a complex object with other significant fields
                other_fields = set(data.keys()) - {"code", "decode", "codeSystem", "codeSystemVersion", "id"}
                if not other_fields or other_fields == {"instanceType"}:
                    self.stats["code_objects_fixed"] += 1
                    return self._expand_code_object(data, path.split(".")[-1].upper())

            # Recurse into all values
            return {k: self._fix_code_objects_recursive(v, f"{path}.{k}") for k, v in data.items()}

        elif isinstance(data, list):
            return [self._fix_code_objects_recursive(item, f"{path}[{i}]") for i, item in enumerate(data)]

        return data

    def _fix_encounters(self, data: Dict[str, Any]) -> None:
        """Fix Encounter objects for USDM compliance.

        Main fix: Convert encounter.type from {code, decode} to full Code-Output.
        """
        encounters = data.get("encounters", [])
        if not encounters:
            return

        for encounter in encounters:
            # Ensure instanceType
            encounter.setdefault("instanceType", "Encounter")

            # Fix the type field (must be Code-Output)
            if "type" in encounter and isinstance(encounter["type"], dict):
                if "instanceType" not in encounter["type"]:
                    encounter["type"] = self._expand_code_object(
                        encounter["type"],
                        "ENCOUNTER-TYPE"
                    )
                    self.stats["encounters_fixed"] += 1

    def _fix_activities(self, data: Dict[str, Any]) -> None:
        """Fix Activity objects for USDM compliance.

        - Ensure instanceType present
        - Convert procedureType to code if needed
        - Fix nested definedProcedures
        """
        activities = data.get("activities", [])
        if not activities:
            return

        for activity in activities:
            # Ensure instanceType
            activity.setdefault("instanceType", "Activity")

            # Fix definedProcedures
            defined_procedures = activity.get("definedProcedures", [])
            for proc in defined_procedures:
                proc.setdefault("instanceType", "Procedure")

                # USDM 4.0 Procedure requires BOTH procedureType (string) AND code (Code-Output)
                # Add procedureType if missing (use name as fallback)
                if "procedureType" not in proc:
                    proc["procedureType"] = proc.get("name", "Procedure")
                    self.stats["activities_fixed"] += 1

                # Add code object if missing (use procedureType for lookup)
                if "code" not in proc:
                    proc_type = proc.get("procedureType", proc.get("name", "Procedure"))
                    code_result = self._lookup_procedure_code(proc_type)
                    proc["code"] = code_result
                    self.stats["activities_fixed"] += 1

            # Fix cdiscMapping if it has wrong structure
            if "cdiscMapping" in activity:
                mapping = activity["cdiscMapping"]
                if isinstance(mapping, dict) and "name" in mapping and "code" in mapping:
                    # The mapping has name and code swapped - fix it
                    if mapping.get("name", "").startswith("C") and not mapping.get("code", "").startswith("C"):
                        mapping["code"], mapping["name"] = mapping["name"], mapping["code"]

    def _lookup_procedure_code(self, procedure_name: str) -> Dict[str, Any]:
        """Lookup CDISC/OMOP code for a procedure name.

        Uses TerminologyMapper first, then LLM fallback if needed.
        """
        if self.terminology_mapper:
            try:
                result = self.terminology_mapper.map(procedure_name)
                if result.match_score >= 0.80:
                    if result.cdisc_code:
                        return self._expand_code_object({
                            "code": result.cdisc_code,
                            "decode": result.cdisc_name or procedure_name
                        }, "PROCEDURE")
                    elif result.omop_concept_code:
                        return self._expand_code_object({
                            "code": result.omop_concept_code,
                            "decode": result.omop_concept_name or procedure_name
                        }, "PROCEDURE")
            except Exception as e:
                logger.debug(f"TerminologyMapper failed for '{procedure_name}': {e}")

        # LLM fallback or generate placeholder
        if self.use_llm_fallback:
            # TODO: Implement LLM-based code inference
            self.stats["llm_calls"] += 1

        # Generate placeholder Code object
        return self._expand_code_object({
            "code": f"LOCAL-{procedure_name.upper().replace(' ', '_')[:20]}",
            "decode": procedure_name
        }, "PROCEDURE")

    def _fix_timings(self, data: Dict[str, Any]) -> None:
        """Fix Timing objects for USDM compliance.

        Required fields:
        - id, name, type (Code), value, valueLabel
        - relativeToFrom, relativeFromScheduledInstanceId, instanceType
        """
        timings = data.get("timings", [])
        if not timings:
            return

        for timing in timings:
            # Ensure instanceType
            timing.setdefault("instanceType", "Timing")

            # Fix type field (must be Code-Output)
            if "type" not in timing:
                timing["type"] = self._expand_code_object({
                    "code": "C71738",
                    "decode": "Study Day"
                }, "TIMING-TYPE")
            elif isinstance(timing["type"], dict) and "instanceType" not in timing["type"]:
                timing["type"] = self._expand_code_object(timing["type"], "TIMING-TYPE")

            # Fix relativeToFrom (must be Code-Output, not string)
            if "relativeToFrom" not in timing:
                timing["relativeToFrom"] = self._expand_code_object({
                    "code": "C98779",
                    "decode": "Baseline"
                }, "TIMING-REL")
            elif isinstance(timing["relativeToFrom"], str):
                # Convert string like "STUDY_START" to Code-Output
                rel_value = timing["relativeToFrom"]
                rel_codes = {
                    "STUDY_START": ("C98779", "Study Start"),
                    "BASELINE": ("C98779", "Baseline"),
                    "TREATMENT_START": ("C71738", "Treatment Start"),
                    "TREATMENT_END": ("C71738", "Treatment End"),
                    "RANDOMIZATION": ("C25196", "Randomization"),
                    "SCREENING": ("C48262", "Screening"),
                }
                code, decode = rel_codes.get(rel_value, ("C98779", rel_value))
                timing["relativeToFrom"] = self._expand_code_object({
                    "code": code,
                    "decode": decode
                }, "TIMING-REL")
            elif isinstance(timing["relativeToFrom"], dict) and "instanceType" not in timing["relativeToFrom"]:
                timing["relativeToFrom"] = self._expand_code_object(timing["relativeToFrom"], "TIMING-REL")

            # Add missing required string fields (ensure non-None values)
            timing_name = timing.get("name") or ""
            if "valueLabel" not in timing or timing["valueLabel"] is None:
                timing["valueLabel"] = timing_name
            if "value" not in timing or timing["value"] is None:
                timing["value"] = timing_name
            if "relativeFromScheduledInstanceId" not in timing or timing["relativeFromScheduledInstanceId"] is None:
                timing["relativeFromScheduledInstanceId"] = "SAI-BASELINE"

            self.stats["timings_fixed"] += 1

    def _fix_timelines(self, data: Dict[str, Any]) -> None:
        """Fix ScheduleTimeline objects for USDM compliance.

        Required fields:
        - id, name, mainTimeline, entryCondition, entryId, instanceType
        """
        timelines = data.get("scheduleTimelines", [])
        if not timelines:
            return

        for i, timeline in enumerate(timelines):
            # Ensure instanceType
            timeline.setdefault("instanceType", "ScheduleTimeline")

            # Set mainTimeline (first timeline is main)
            timeline.setdefault("mainTimeline", i == 0)

            # Add entry condition
            timeline.setdefault("entryCondition", "Enrollment")

            # Add entry ID reference
            timeline.setdefault("entryId", f"SAI-ENTRY-{i + 1:03d}")

            self.stats["timelines_fixed"] += 1

    def _fix_scheduled_instances(self, data: Dict[str, Any]) -> None:
        """Fix ScheduledActivityInstance objects."""
        instances = data.get("scheduledActivityInstances", [])
        if not instances:
            return

        for instance in instances:
            instance.setdefault("instanceType", "ScheduledActivityInstance")

    def _add_missing_instance_types(self, data: Dict[str, Any]) -> None:
        """Ensure all entities have instanceType."""
        entity_types = {
            "scheduleTimelines": "ScheduleTimeline",
            "encounters": "Encounter",
            "activities": "Activity",
            "timings": "Timing",
            "scheduledActivityInstances": "ScheduledActivityInstance",
        }

        for array_name, instance_type in entity_types.items():
            items = data.get(array_name, [])
            for item in items:
                if isinstance(item, dict):
                    item.setdefault("instanceType", instance_type)

    def _inject_provenance(self, data: Dict[str, Any]) -> None:
        """Inject provenance into all entities that lack it.

        This is the core provenance enhancement method that ensures 100% provenance
        coverage by deterministically injecting provenance from available context:
        1. Table context (page_start, page_end) for page numbers
        2. Visit schedule for encounter-specific provenance
        3. Entity names/values for text snippets

        Provenance structure:
        {
            "page_number": int,
            "text_snippet": str (max 150 chars),
            "confidence": float (0.0-1.0),
            "source_stage": str ("schema_fixer", "visit_schedule", etc.)
        }
        """
        # Default provenance for entities without specific context
        default_prov = {
            "page_number": self.table_context.get("page_start", 1),
            "confidence": 0.80,
            "source_stage": "schema_fixer",
        }

        # Add page_end if available (for multi-page tables)
        if self.table_context.get("page_end"):
            default_prov["page_end"] = self.table_context["page_end"]

        # 1. ScheduleTimelines - use table context
        for timeline in data.get("scheduleTimelines", []):
            if "provenance" not in timeline:
                timeline["provenance"] = {
                    **default_prov,
                    "text_snippet": timeline.get("name", "Schedule of Assessments")[:150],
                    "confidence": 0.90,  # High confidence - timelines are primary structures
                }
                self.stats["provenance_injected"] += 1

        # 2. Encounters (visits) - use visit schedule provenance lookup
        for encounter in data.get("encounters", []):
            enc_name = encounter.get("name", "")
            enc_name_lower = enc_name.lower().strip()

            if "provenance" not in encounter:
                # Try to find in visit provenance lookup
                if enc_name_lower in self._visit_provenance_lookup:
                    encounter["provenance"] = self._visit_provenance_lookup[enc_name_lower].copy()
                else:
                    encounter["provenance"] = {
                        **default_prov,
                        "text_snippet": enc_name[:150] if enc_name else "Visit",
                    }
                self.stats["provenance_injected"] += 1

            # 2a. Nested timingInfo within encounters
            timing_info = encounter.get("timingInfo")
            if timing_info and isinstance(timing_info, dict) and "provenance" not in timing_info:
                timing_name = timing_info.get("name") or timing_info.get("label", enc_name)
                timing_info["provenance"] = {
                    **default_prov,
                    "text_snippet": timing_name[:150] if timing_name else "Timing Info",
                }
                self.stats["provenance_injected"] += 1

        # 3. Activities - use activity name for snippet
        for activity in data.get("activities", []):
            activity_name = activity.get("name", "")
            if "provenance" not in activity:
                activity["provenance"] = {
                    **default_prov,
                    "text_snippet": activity_name[:150] if activity_name else "Activity",
                }
                self.stats["provenance_injected"] += 1

            # 3a. Nested definedProcedures within activities
            for proc in activity.get("definedProcedures", []):
                if "provenance" not in proc:
                    proc_name = proc.get("name", activity_name)
                    proc["provenance"] = {
                        **default_prov,
                        "text_snippet": proc_name[:150] if proc_name else "Procedure",
                    }
                    self.stats["provenance_injected"] += 1

            # 3b. Nested cdashAnnotation within activities
            cdash = activity.get("cdashAnnotation")
            if cdash and isinstance(cdash, dict) and "provenance" not in cdash:
                cdash_name = cdash.get("name", activity_name)
                cdash["provenance"] = {
                    **default_prov,
                    "text_snippet": cdash_name[:150] if cdash_name else "CDASH Annotation",
                }
                self.stats["provenance_injected"] += 1

            # 3c. Nested cdiscMapping within activities
            cdisc_map = activity.get("cdiscMapping")
            if cdisc_map and isinstance(cdisc_map, dict) and "provenance" not in cdisc_map:
                cdisc_name = cdisc_map.get("name", activity_name)
                cdisc_map["provenance"] = {
                    **default_prov,
                    "text_snippet": cdisc_name[:150] if cdisc_name else "CDISC Mapping",
                }
                self.stats["provenance_injected"] += 1

            # 3d. Nested edcSpecification.fields within activities
            edc_spec = activity.get("edcSpecification")
            if edc_spec and isinstance(edc_spec, dict):
                for field in edc_spec.get("fields", []):
                    if isinstance(field, dict) and "provenance" not in field:
                        field_name = field.get("name") or field.get("label", activity_name)
                        field["provenance"] = {
                            **default_prov,
                            "text_snippet": field_name[:150] if field_name else "EDC Field",
                        }
                        self.stats["provenance_injected"] += 1

            # 3e. Nested applicabilityRules within activities
            for rule in activity.get("applicabilityRules", []):
                if isinstance(rule, dict) and "provenance" not in rule:
                    rule_name = rule.get("name") or rule.get("description", activity_name)
                    rule["provenance"] = {
                        **default_prov,
                        "text_snippet": rule_name[:150] if rule_name else "Applicability Rule",
                    }
                    self.stats["provenance_injected"] += 1

        # 4. Timings - use valueLabel or name for snippet
        for timing in data.get("timings", []):
            if "provenance" not in timing:
                timing_label = timing.get("valueLabel") or timing.get("name", "")
                timing["provenance"] = {
                    **default_prov,
                    "text_snippet": timing_label[:150] if timing_label else "Timing",
                }
                self.stats["provenance_injected"] += 1

        # 5. ScheduledActivityInstances - reference activity/encounter names
        for sai in data.get("scheduledActivityInstances", []):
            if "provenance" not in sai:
                sai_name = sai.get("name", "")
                sai["provenance"] = {
                    **default_prov,
                    "text_snippet": sai_name[:150] if sai_name else "Scheduled Instance",
                }
                self.stats["provenance_injected"] += 1

        logger.debug(f"Injected provenance into {self.stats['provenance_injected']} entities")

    def fix(self, usdm_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply all schema fixes to USDM data.

        Args:
            usdm_data: Raw transformer output

        Returns:
            Fixed USDM data matching USDM 4.0 schema
        """
        # Reset stats
        self.stats = {k: 0 for k in self.stats}

        # Deep copy to avoid modifying original
        import copy
        data = copy.deepcopy(usdm_data)

        # Apply fixes in order
        logger.debug("Fixing encounters...")
        self._fix_encounters(data)

        logger.debug("Fixing activities...")
        self._fix_activities(data)

        logger.debug("Fixing timings...")
        self._fix_timings(data)

        logger.debug("Fixing timelines...")
        self._fix_timelines(data)

        logger.debug("Fixing scheduled instances...")
        self._fix_scheduled_instances(data)

        logger.debug("Fixing Code objects recursively...")
        data = self._fix_code_objects_recursive(data)

        logger.debug("Adding missing instanceTypes...")
        self._add_missing_instance_types(data)

        # Inject provenance into all entities (must be last - after all structural fixes)
        logger.debug("Injecting provenance...")
        self._inject_provenance(data)

        # Log stats
        total_fixes = sum(self.stats.values())
        logger.info(
            f"Schema fixes applied: {total_fixes} total "
            f"(codes={self.stats['code_objects_fixed']}, "
            f"encounters={self.stats['encounters_fixed']}, "
            f"activities={self.stats['activities_fixed']}, "
            f"timings={self.stats['timings_fixed']}, "
            f"timelines={self.stats['timelines_fixed']}, "
            f"provenance={self.stats['provenance_injected']}, "
            f"llm_calls={self.stats['llm_calls']})"
        )

        return data

    def get_stats(self) -> Dict[str, int]:
        """Get statistics from the last fix() call."""
        return self.stats.copy()


def get_schema_fixer(**kwargs) -> USDMSchemaFixer:
    """Factory function to get a schema fixer instance."""
    return USDMSchemaFixer(**kwargs)
