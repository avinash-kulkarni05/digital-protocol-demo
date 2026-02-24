"""
SOA Enrichment Module - CDASH/SDTM mapping and EDC-ready output

Enriches USDM data with:
- CDASH annotation mappings for activities
- SDTM domain mappings
- Applicability rules (conditional triggers)
- Recurrence patterns for repeated assessments
- EDC-ready field specifications

Usage:
    from soa_analyzer.soa_enrichment import SOAEnrichment

    enricher = SOAEnrichment()

    # Enrich USDM data
    enriched = enricher.enrich(usdm_data)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from soa_analyzer.soa_terminology_mapper import TerminologyMapper, get_mapper, MappingResult

logger = logging.getLogger(__name__)


# CDASH domain mappings (activity type → CDASH domain)
CDASH_DOMAIN_MAP = {
    "LB": {
        "domain": "LB",
        "cdash": "LB",
        "sdtm": "LB",
        "description": "Laboratory Test Results",
        "core_variables": ["LBTESTCD", "LBTEST", "LBCAT", "LBORRES", "LBORRESU", "LBORNRLO", "LBORNRHI"],
    },
    "VS": {
        "domain": "VS",
        "cdash": "VS",
        "sdtm": "VS",
        "description": "Vital Signs",
        "core_variables": ["VSTESTCD", "VSTEST", "VSORRES", "VSORRESU", "VSPOS"],
    },
    "EG": {
        "domain": "EG",
        "cdash": "EG",
        "sdtm": "EG",
        "description": "ECG Test Results",
        "core_variables": ["EGTESTCD", "EGTEST", "EGORRES", "EGORRESU", "EGMETHOD"],
    },
    "PE": {
        "domain": "PE",
        "cdash": "PE",
        "sdtm": "PE",
        "description": "Physical Examination",
        "core_variables": ["PETESTCD", "PETEST", "PEORRES", "PELOC", "PEMETHOD"],
    },
    "QS": {
        "domain": "QS",
        "cdash": "QS",
        "sdtm": "QS",
        "description": "Questionnaires",
        "core_variables": ["QSTESTCD", "QSTEST", "QSCAT", "QSORRES", "QSSTRESC"],
    },
    "PR": {
        "domain": "PR",
        "cdash": "PR",
        "sdtm": "PR",
        "description": "Procedures",
        "core_variables": ["PRTRT", "PRCAT", "PRSTDTC", "PRENDTC", "PRLOC"],
    },
    "PC": {
        "domain": "PC",
        "cdash": "PC",
        "sdtm": "PC",
        "description": "Pharmacokinetics Concentrations",
        "core_variables": ["PCTESTCD", "PCTEST", "PCSPEC", "PCORRES", "PCORRESU", "PCLLOQ"],
    },
    "PP": {
        "domain": "PP",
        "cdash": "PP",
        "sdtm": "PP",
        "description": "Pharmacokinetics Parameters",
        "core_variables": ["PPTESTCD", "PPTEST", "PPORRES", "PPORRESU", "PPCAT"],
    },
    "DA": {
        "domain": "DA",
        "cdash": "DA",
        "sdtm": "DA",
        "description": "Drug Accountability",
        "core_variables": ["DATRT", "DADOSE", "DADOSU", "DASTDTC", "DAENDTC"],
    },
    "CM": {
        "domain": "CM",
        "cdash": "CM",
        "sdtm": "CM",
        "description": "Concomitant Medications",
        "core_variables": ["CMTRT", "CMDOSE", "CMDOSU", "CMSTDTC", "CMENDTC"],
    },
    "AE": {
        "domain": "AE",
        "cdash": "AE",
        "sdtm": "AE",
        "description": "Adverse Events",
        "core_variables": ["AETERM", "AEDECOD", "AESTDTC", "AEENDTC", "AESEV", "AESER"],
    },
    "MH": {
        "domain": "MH",
        "cdash": "MH",
        "sdtm": "MH",
        "description": "Medical History",
        "core_variables": ["MHTERM", "MHDECOD", "MHCAT", "MHSTDTC", "MHENDTC"],
    },
}


# Common applicability patterns
APPLICABILITY_PATTERNS = {
    "screening_only": {
        "condition": "VISIT == 'Screening'",
        "description": "Performed only at screening",
    },
    "baseline_only": {
        "condition": "VISIT == 'Baseline' OR VISIT == 'Day 1'",
        "description": "Performed only at baseline",
    },
    "end_of_treatment": {
        "condition": "VISIT == 'End of Treatment' OR VISIT == 'EOT'",
        "description": "Performed at end of treatment",
    },
    "follow_up_only": {
        "condition": "EPOCH == 'Follow-up'",
        "description": "Performed during follow-up period",
    },
    "if_clinically_indicated": {
        "condition": "CLINICAL_INDICATION == TRUE",
        "description": "Performed if clinically indicated",
    },
    "unscheduled": {
        "condition": "VISIT_TYPE == 'Unscheduled'",
        "description": "Unscheduled visit only",
    },
    "female_only": {
        "condition": "SEX == 'F'",
        "description": "Female subjects only",
    },
    "fasting_required": {
        "condition": "FASTING == TRUE",
        "description": "Fasting required before assessment",
    },
    "pre_dose": {
        "condition": "TIMING == 'Pre-dose'",
        "description": "Performed before dosing",
    },
    "post_dose": {
        "condition": "TIMING == 'Post-dose'",
        "description": "Performed after dosing",
    },
}


@dataclass
class EnrichmentResult:
    """Result of enrichment process."""
    success: bool
    data: Dict[str, Any]
    activities_enriched: int = 0
    terminology_mapped: int = 0
    applicability_rules_added: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "statistics": {
                "activities_enriched": self.activities_enriched,
                "terminology_mapped": self.terminology_mapped,
                "applicability_rules_added": self.applicability_rules_added,
            },
            "errors": self.errors,
        }


class SOAEnrichment:
    """
    Enriches SOA USDM data with CDASH/SDTM mappings and EDC specifications.

    Features:
    - CDASH domain annotation
    - SDTM variable mapping
    - Applicability rule detection
    - Recurrence pattern extraction
    - CDISC/OMOP terminology integration
    """

    def __init__(
        self,
        terminology_mapper: Optional[TerminologyMapper] = None,
    ):
        """
        Initialize enrichment module.

        Args:
            terminology_mapper: Optional TerminologyMapper instance
        """
        self.terminology_mapper = terminology_mapper

        logger.info("SOAEnrichment initialized")

    def _get_mapper(self) -> TerminologyMapper:
        """Get or create terminology mapper."""
        if self.terminology_mapper is None:
            self.terminology_mapper = get_mapper()
        return self.terminology_mapper

    def enrich(self, usdm_data: Dict[str, Any]) -> EnrichmentResult:
        """
        Enrich USDM data with CDASH/SDTM mappings.

        Args:
            usdm_data: USDM-formatted SOA data

        Returns:
            EnrichmentResult with enriched data
        """
        import copy
        data = copy.deepcopy(usdm_data)

        result = EnrichmentResult(success=True, data=data)

        try:
            # 1. Enrich activities with CDASH/SDTM mappings
            self._enrich_activities(data, result)

            # 2. Add applicability rules
            self._add_applicability_rules(data, result)

            # 3. Enrich encounters with visit types
            self._enrich_encounters(data, result)

            # 4. Add recurrence patterns
            self._add_recurrence_patterns(data, result)

            # 5. Generate EDC specifications
            self._generate_edc_specs(data, result)

            result.data = data
            logger.info(
                f"Enrichment complete: {result.activities_enriched} activities, "
                f"{result.terminology_mapped} terms mapped, "
                f"{result.applicability_rules_added} rules added"
            )

        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            logger.error(f"Enrichment failed: {e}")

        return result

    def _enrich_activities(self, data: Dict[str, Any], result: EnrichmentResult):
        """Enrich activities with CDASH/SDTM mappings and terminology."""
        mapper = self._get_mapper()

        for activity in data.get("activities", []):
            activity_name = activity.get("name", "")

            if not activity_name:
                continue

            # Map to terminology
            mapping = mapper.map(activity_name)

            if mapping.cdisc_code or mapping.omop_concept_id:
                result.terminology_mapped += 1

            # Add CDISC mapping
            if mapping.cdisc_code:
                activity["cdiscMapping"] = {
                    "code": mapping.cdisc_code,
                    "domain": mapping.cdisc_domain,
                    "name": mapping.cdisc_name,
                    "specimen": mapping.cdisc_specimen,
                    "method": mapping.cdisc_method,
                }

            # Add OMOP mapping
            if mapping.omop_concept_id:
                activity["omopMapping"] = {
                    "conceptId": mapping.omop_concept_id,
                    "conceptName": mapping.omop_concept_name,
                    "vocabularyId": mapping.omop_vocabulary_id,
                    "domainId": mapping.omop_domain_id,
                    "conceptCode": mapping.omop_concept_code,
                }

            # Add CDASH/SDTM domain info
            domain = mapping.cdisc_domain or activity.get("cdiscDomain")
            if domain and domain in CDASH_DOMAIN_MAP:
                domain_info = CDASH_DOMAIN_MAP[domain]
                activity["cdashAnnotation"] = {
                    "domain": domain_info["domain"],
                    "cdashDomain": domain_info["cdash"],
                    "sdtmDomain": domain_info["sdtm"],
                    "description": domain_info["description"],
                    "coreVariables": domain_info["core_variables"],
                }

            result.activities_enriched += 1

    def _add_applicability_rules(self, data: Dict[str, Any], result: EnrichmentResult):
        """
        Add applicability rules based on activity context and footnotes.

        Detects patterns like:
        - "Screening only"
        - "If clinically indicated"
        - "Female subjects only"
        """
        # Keywords that trigger applicability rules
        keyword_patterns = {
            "screening": "screening_only",
            "baseline": "baseline_only",
            "end of treatment": "end_of_treatment",
            "eot": "end_of_treatment",
            "follow-up": "follow_up_only",
            "follow up": "follow_up_only",
            "if clinically indicated": "if_clinically_indicated",
            "as clinically indicated": "if_clinically_indicated",
            "unscheduled": "unscheduled",
            "female": "female_only",
            "women": "female_only",
            "fasting": "fasting_required",
            "pre-dose": "pre_dose",
            "predose": "pre_dose",
            "post-dose": "post_dose",
            "postdose": "post_dose",
        }

        for activity in data.get("activities", []):
            rules = []

            # Check activity name and description for patterns
            check_text = " ".join([
                activity.get("name", ""),
                activity.get("description", ""),
                str(activity.get("footnote", "")),
            ]).lower()

            for keyword, rule_key in keyword_patterns.items():
                if keyword in check_text:
                    if rule_key in APPLICABILITY_PATTERNS:
                        rules.append({
                            "ruleId": f"RULE-{len(rules)+1:03d}",
                            "type": rule_key,
                            "condition": APPLICABILITY_PATTERNS[rule_key]["condition"],
                            "description": APPLICABILITY_PATTERNS[rule_key]["description"],
                            "source": "auto-detected",
                        })
                        result.applicability_rules_added += 1

            if rules:
                activity["applicabilityRules"] = rules

    def _enrich_encounters(self, data: Dict[str, Any], result: EnrichmentResult):
        """Enrich encounters with visit type classifications."""
        for encounter in data.get("encounters", []):
            name = encounter.get("name", "").lower()

            # Classify visit type
            visit_type = "treatment"  # default
            if any(kw in name for kw in ["screen", "eligibility"]):
                visit_type = "screening"
            elif any(kw in name for kw in ["baseline", "day 1", "d1", "day1"]):
                visit_type = "baseline"
            elif any(kw in name for kw in ["follow", "survival", "safety follow"]):
                visit_type = "follow_up"
            elif any(kw in name for kw in ["eot", "end of treatment", "termination"]):
                visit_type = "end_of_treatment"
            elif any(kw in name for kw in ["unscheduled", "unsch"]):
                visit_type = "unscheduled"

            encounter["visitClassification"] = {
                "type": visit_type,
                "isRequired": visit_type in ["screening", "baseline"],
                "isRepeating": visit_type == "treatment" and any(
                    kw in name for kw in ["cycle", "week", "day"]
                ),
            }

            # Extract timing info from name
            timing = self._extract_timing(encounter.get("name", ""))
            if timing:
                encounter["timingInfo"] = timing

    def _extract_timing(self, name: str) -> Optional[Dict[str, Any]]:
        """Extract timing information from visit name."""
        patterns = [
            (r"day\s*(\d+)", "day"),
            (r"d(\d+)", "day"),
            (r"week\s*(\d+)", "week"),
            (r"w(\d+)", "week"),
            (r"cycle\s*(\d+)", "cycle"),
            (r"c(\d+)", "cycle"),
            (r"month\s*(\d+)", "month"),
            (r"m(\d+)", "month"),
            (r"visit\s*(\d+)", "visit"),
            (r"v(\d+)", "visit"),
        ]

        name_lower = name.lower()
        for pattern, unit in patterns:
            match = re.search(pattern, name_lower)
            if match:
                return {
                    "value": int(match.group(1)),
                    "unit": unit,
                    "label": name,
                }

        return None

    def _add_recurrence_patterns(self, data: Dict[str, Any], result: EnrichmentResult):
        """
        Detect and add recurrence patterns for repeated assessments.

        Examples:
        - "Every 2 weeks"
        - "Each cycle"
        - "Daily x 5 days"
        """
        recurrence_patterns = [
            (r"every\s*(\d+)\s*(day|week|month|cycle)s?", "interval"),
            (r"each\s*(cycle|visit|week)", "each"),
            (r"daily", "daily"),
            (r"weekly", "weekly"),
            (r"monthly", "monthly"),
            (r"(\d+)\s*times\s*per\s*(day|week|cycle)", "frequency"),
            (r"q(\d+)([hdwm])", "q_notation"),  # q4h, q2d, etc.
        ]

        for activity in data.get("activities", []):
            check_text = " ".join([
                activity.get("name", ""),
                activity.get("description", ""),
            ]).lower()

            for pattern, pattern_type in recurrence_patterns:
                match = re.search(pattern, check_text)
                if match:
                    recurrence = {
                        "patternType": pattern_type,
                        "rawPattern": match.group(0),
                    }

                    if pattern_type == "interval":
                        recurrence["interval"] = int(match.group(1))
                        recurrence["unit"] = match.group(2)
                    elif pattern_type == "q_notation":
                        recurrence["interval"] = int(match.group(1))
                        unit_map = {"h": "hour", "d": "day", "w": "week", "m": "month"}
                        recurrence["unit"] = unit_map.get(match.group(2), match.group(2))

                    activity["recurrencePattern"] = recurrence
                    break

    def _generate_edc_specs(self, data: Dict[str, Any], result: EnrichmentResult):
        """Generate EDC-ready specifications for each activity."""
        for activity in data.get("activities", []):
            cdash = activity.get("cdashAnnotation", {})

            if not cdash:
                continue

            # Generate EDC field specifications
            edc_spec = {
                "formName": f"{cdash.get('domain', 'MISC')}_FORM",
                "fields": [],
            }

            # Add core variable fields
            for var in cdash.get("coreVariables", []):
                field_spec = {
                    "variableName": var,
                    "label": self._variable_to_label(var),
                    "dataType": self._infer_data_type(var),
                    "required": self._is_required_variable(var),
                }
                edc_spec["fields"].append(field_spec)

            # Add date/time fields
            edc_spec["fields"].append({
                "variableName": f"{cdash.get('domain', 'MISC')}DTC",
                "label": "Date/Time of Assessment",
                "dataType": "datetime",
                "required": True,
            })

            activity["edcSpecification"] = edc_spec

    def _variable_to_label(self, var: str) -> str:
        """Convert variable name to human-readable label."""
        # Remove domain prefix and convert
        if len(var) > 2:
            suffix = var[2:]
            label_map = {
                "TESTCD": "Test Code",
                "TEST": "Test Name",
                "CAT": "Category",
                "ORRES": "Original Result",
                "ORRESU": "Original Units",
                "ORNRLO": "Normal Range Lower",
                "ORNRHI": "Normal Range Upper",
                "STRESC": "Standardized Result (Character)",
                "STRESN": "Standardized Result (Numeric)",
                "POS": "Position",
                "LOC": "Location",
                "METHOD": "Method",
                "TRT": "Treatment",
                "DOSE": "Dose",
                "DOSU": "Dose Units",
                "STDTC": "Start Date/Time",
                "ENDTC": "End Date/Time",
                "SEV": "Severity",
                "SER": "Serious",
                "DECOD": "Dictionary-Derived Term",
                "TERM": "Reported Term",
                "SPEC": "Specimen",
                "LLOQ": "Lower Limit of Quantification",
            }
            return label_map.get(suffix, suffix)
        return var

    def _infer_data_type(self, var: str) -> str:
        """Infer data type from variable name."""
        if var.endswith("DTC"):
            return "datetime"
        elif var.endswith(("STRESN", "DOSE", "ORNRLO", "ORNRHI", "LLOQ")):
            return "number"
        elif var.endswith(("SEV", "SER", "YN")):
            return "boolean"
        elif var.endswith(("CD", "CAT")):
            return "code"
        else:
            return "text"

    def _is_required_variable(self, var: str) -> bool:
        """Determine if variable is required."""
        required_suffixes = ["TESTCD", "TEST", "ORRES", "DTC", "TRT", "TERM"]
        return any(var.endswith(s) for s in required_suffixes)


# Singleton instance
_enrichment_instance: Optional[SOAEnrichment] = None


def get_enrichment() -> SOAEnrichment:
    """Get the singleton enrichment instance."""
    global _enrichment_instance
    if _enrichment_instance is None:
        _enrichment_instance = SOAEnrichment()
    return _enrichment_instance


# CLI support
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    def print_usage():
        print("Usage: python soa_enrichment.py <usdm_json_file>")
        print("\nEnriches USDM data with CDASH/SDTM mappings.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print_usage()

    json_path = sys.argv[1]
    if not Path(json_path).exists():
        print(f"Error: File not found: {json_path}")
        sys.exit(1)

    try:
        with open(json_path, 'r') as f:
            data = json.load(f)

        enricher = get_enrichment()
        result = enricher.enrich(data)

        print(f"\nEnrichment Results:")
        print(f"  Activities enriched: {result.activities_enriched}")
        print(f"  Terms mapped: {result.terminology_mapped}")
        print(f"  Rules added: {result.applicability_rules_added}")

        # Output enriched data
        output_path = json_path.replace(".json", "_enriched.json")
        with open(output_path, 'w') as f:
            json.dump(result.data, f, indent=2)
        print(f"\nEnriched data saved to: {output_path}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
