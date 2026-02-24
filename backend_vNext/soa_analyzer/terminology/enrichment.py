"""
Terminology Enrichment for SOA Pipeline

Enriches SOA components with controlled terminology codes from:
- ATHENA OMOP CDM (LOINC, SNOMED, MeSH)
- CDISC Controlled Terminology (NCI Thesaurus)

Usage:
    from soa_analyzer.terminology.enrichment import enrich_stage2_with_terminology

    # After stage 2 expansion
    enriched_result = enrich_stage2_with_terminology(stage2_result)
"""

import logging
from typing import Any, Dict, List, Optional

from ..models.expansion_proposal import ActivityComponent, ActivityExpansion
from .terminology_mapper import (
    TerminologyMapper,
    TerminologyMapperConfig,
    MappingResult,
    get_terminology_mapper,
)

logger = logging.getLogger(__name__)


def _determine_domain_hint(parent_name: str, cdash_domain: Optional[str]) -> Optional[str]:
    """Determine CDASH domain hint from parent activity name or explicit domain."""
    if cdash_domain:
        return cdash_domain

    parent_lower = parent_name.lower()
    if "chemistry" in parent_lower or "hematology" in parent_lower or "lab" in parent_lower:
        return "LB"
    elif "vital" in parent_lower:
        return "VS"
    elif "ecg" in parent_lower or "electrocardiogram" in parent_lower:
        return "EG"
    elif "physical" in parent_lower or "exam" in parent_lower:
        return "PE"
    elif "questionnaire" in parent_lower or "qol" in parent_lower:
        return "QS"
    elif "tumor" in parent_lower or "imaging" in parent_lower:
        return "TU"
    elif "pk" in parent_lower or "pharmacokinetic" in parent_lower:
        return "PC"
    elif "sample" in parent_lower or "blood" in parent_lower or "specimen" in parent_lower:
        return "BS"

    return None


def _apply_terminology_to_component(
    component: ActivityComponent,
    mapping_result: MappingResult,
) -> None:
    """Apply terminology mapping result to a component."""
    if not mapping_result.success or not mapping_result.primary_match:
        return

    match = mapping_result.primary_match

    # Set vocabulary ID and OMOP concept ID
    component.vocabulary_id = match.vocabulary_id
    component.omop_concept_id = match.concept_id
    component.terminology_match_score = match.match_score
    component.terminology_match_type = match.match_type

    # Set vocabulary-specific codes
    if match.vocabulary_id == "LOINC":
        component.loinc_code = match.concept_code
        component.loinc_display = match.concept_name
    elif match.vocabulary_id == "SNOMED":
        component.snomed_code = match.concept_code
        component.snomed_display = match.concept_name
    elif match.vocabulary_id in ("NCIt", "NCIt_Full"):
        component.ncit_code = match.concept_code
        component.ncit_display = match.concept_name
    elif match.vocabulary_id == "CDISC":
        component.cdisc_code = match.concept_code
        component.cdisc_decode = match.concept_name


def enrich_stage2_with_terminology(
    stage2_result: Dict[str, Any],
    use_llm_disambiguation: bool = False,
    mapper: Optional[TerminologyMapper] = None,
) -> Dict[str, Any]:
    """
    Enrich stage 2 expansion result with controlled terminology codes.

    Performs batched terminology lookup for all components across all expansions.

    Args:
        stage2_result: Stage 2 result dictionary with expansions
        use_llm_disambiguation: Whether to use LLM for ambiguous matches
        mapper: Optional pre-configured terminology mapper

    Returns:
        Enriched stage 2 result with terminology codes added to components
    """
    if mapper is None:
        mapper = get_terminology_mapper()

    expansions = stage2_result.get("expansions", [])
    if not expansions:
        logger.info("No expansions to enrich with terminology")
        return stage2_result

    # Collect all components for batch processing
    all_terms = []
    component_map: Dict[str, Dict] = {}  # term -> {expansion_idx, component_idx}

    for exp_idx, expansion in enumerate(expansions):
        parent_name = expansion.get("parentActivityName", "")
        components = expansion.get("components", [])

        for comp_idx, component in enumerate(components):
            name = component.get("name", "")
            if name and len(name) > 2:
                cdash_domain = component.get("cdashDomain")
                domain_hint = _determine_domain_hint(parent_name, cdash_domain)

                all_terms.append({
                    "term": name,
                    "domain_hint": domain_hint,
                    "context": f"Component of {parent_name}",
                })
                component_map[name] = {
                    "expansion_idx": exp_idx,
                    "component_idx": comp_idx,
                    "domain_hint": domain_hint,
                }

    if not all_terms:
        logger.info("No components to enrich")
        return stage2_result

    logger.info(f"Enriching {len(all_terms)} components with terminology codes...")

    # Batch terminology lookup
    results = mapper.map_concepts_batch(all_terms, use_llm_disambiguation=use_llm_disambiguation)

    # Apply results to components
    matched_count = 0
    for term, mapping_result in results.items():
        if term not in component_map:
            continue

        info = component_map[term]
        exp_idx = info["expansion_idx"]
        comp_idx = info["component_idx"]

        component_dict = expansions[exp_idx]["components"][comp_idx]

        if mapping_result.success and mapping_result.primary_match:
            match = mapping_result.primary_match
            matched_count += 1

            # Add terminology data to component dict
            terminology = {
                "vocabularyId": match.vocabulary_id,
                "omopConceptId": match.concept_id,
                "conceptCode": match.concept_code,
                "conceptName": match.concept_name,
                "matchScore": match.match_score,
                "matchType": match.match_type,
            }

            # Set vocabulary-specific fields
            if match.vocabulary_id == "LOINC":
                component_dict["loincCode"] = match.concept_code
                component_dict["loincDisplay"] = match.concept_name
            elif match.vocabulary_id == "SNOMED":
                terminology["snomedCode"] = match.concept_code
                terminology["snomedDisplay"] = match.concept_name
            elif match.vocabulary_id in ("NCIt", "NCIt_Full"):
                terminology["ncitCode"] = match.concept_code
                terminology["ncitDisplay"] = match.concept_name

            component_dict["terminology"] = terminology

    logger.info(
        f"Terminology enrichment complete: {matched_count}/{len(all_terms)} "
        f"({100*matched_count/len(all_terms):.1f}%) components mapped"
    )

    # Add enrichment metadata
    stage2_result["terminologyEnrichment"] = {
        "totalComponents": len(all_terms),
        "mappedComponents": matched_count,
        "coverageRate": matched_count / len(all_terms) if all_terms else 0,
        "llmDisambiguation": use_llm_disambiguation,
    }

    return stage2_result


def enrich_expansions_list(
    expansions: List[ActivityExpansion],
    use_llm_disambiguation: bool = False,
    mapper: Optional[TerminologyMapper] = None,
) -> List[ActivityExpansion]:
    """
    Enrich a list of ActivityExpansion objects with terminology codes.

    This variant works with actual dataclass objects instead of dicts.

    Args:
        expansions: List of ActivityExpansion objects
        use_llm_disambiguation: Whether to use LLM for ambiguous matches
        mapper: Optional pre-configured terminology mapper

    Returns:
        Same list of expansions with terminology codes added to components
    """
    if mapper is None:
        mapper = get_terminology_mapper()

    if not expansions:
        return expansions

    # Collect all components for batch processing
    all_terms = []
    component_refs: List[tuple] = []  # (expansion_idx, component_idx)

    for exp_idx, expansion in enumerate(expansions):
        for comp_idx, component in enumerate(expansion.components):
            if component.name and len(component.name) > 2:
                domain_hint = _determine_domain_hint(
                    expansion.parent_activity_name,
                    component.cdash_domain
                )
                all_terms.append({
                    "term": component.name,
                    "domain_hint": domain_hint,
                    "context": f"Component of {expansion.parent_activity_name}",
                })
                component_refs.append((exp_idx, comp_idx, component.name))

    if not all_terms:
        return expansions

    logger.info(f"Enriching {len(all_terms)} components with terminology codes...")

    # Batch terminology lookup
    results = mapper.map_concepts_batch(all_terms, use_llm_disambiguation=use_llm_disambiguation)

    # Apply results to components
    matched_count = 0
    for exp_idx, comp_idx, term in component_refs:
        if term not in results:
            continue

        mapping_result = results[term]
        component = expansions[exp_idx].components[comp_idx]
        _apply_terminology_to_component(component, mapping_result)

        if mapping_result.success:
            matched_count += 1

    logger.info(
        f"Terminology enrichment complete: {matched_count}/{len(all_terms)} "
        f"({100*matched_count/len(all_terms):.1f}%) components mapped"
    )

    return expansions
