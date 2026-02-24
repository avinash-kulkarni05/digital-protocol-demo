"""
Terminology Mapping Module for SOA Pipeline

Provides concept mapping to controlled vocabularies:
- ATHENA OMOP CDM (LOINC, SNOMED, MeSH)
- CDISC Controlled Terminology (NCI Thesaurus)
"""

from .terminology_mapper import (
    TerminologyMapper,
    TerminologyMapperConfig,
    ConceptMatch,
    MappingResult,
    get_terminology_mapper,
    map_concept,
    map_concepts_batch,
)

from .enrichment import (
    enrich_stage2_with_terminology,
    enrich_expansions_list,
)

__all__ = [
    # Mapper classes
    "TerminologyMapper",
    "TerminologyMapperConfig",
    "ConceptMatch",
    "MappingResult",
    # Convenience functions
    "get_terminology_mapper",
    "map_concept",
    "map_concepts_batch",
    # Enrichment functions
    "enrich_stage2_with_terminology",
    "enrich_expansions_list",
]
