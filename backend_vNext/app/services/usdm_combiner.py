"""
USDM 4.0 Combiner Service

Combines extraction outputs from all agents into a single USDM 4.0 compliant JSON structure.

The USDM 4.0 structure wraps all protocol data in a Study object with:
- Document metadata (source PDF, extraction timestamps)
- Study metadata (from study_metadata agent)
- Nested domain-specific sections from each agent
- Agent documentation for downstream automation

Usage:
    from app.services.usdm_combiner import USDMCombiner

    combiner = USDMCombiner()
    usdm_json = combiner.combine(all_results, pdf_path, model_name)
"""

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils.page_offset_detector import detect_page_offset
from app.utils.provenance_validator import validate_and_correct_provenance
from app.agent_documentation import (
    generate_agent_documentation_json,
    generate_all_agent_documentation_json,
    AGENT_DOCUMENTATION_REGISTRY,
)

logger = logging.getLogger(__name__)


# Mapping from module_id to USDM section key
MODULE_TO_USDM_SECTION = {
    "study_metadata": "studyMetadata",
    "arms_design": "studyDesign",
    "endpoints_estimands_sap": "endpointsEstimandsSAP",
    "adverse_events": "adverseEvents",
    "safety_decision_points": "safetyDecisionPoints",
    "concomitant_medications": "concomitantMedications",
    "biospecimen_handling": "biospecimenHandling",
    "laboratory_specifications": "laboratorySpecifications",
    "data_management": "dataManagement",
    "site_operations_logistics": "siteOperationsLogistics",
    "quality_management": "qualityManagement",
    "withdrawal_procedures": "withdrawalProcedures",
    "imaging_central_reading": "imagingCentralReading",
    "pkpd_sampling": "pkpdSampling",
    "informed_consent": "informedConsent",
    "pro_specifications": "proSpecifications",
}


class USDMCombiner:
    """
    Combines multiple agent extraction outputs into a unified USDM 4.0 document.
    """

    SCHEMA_VERSION = "4.0.0"
    INSTANCE_TYPE = "StudyDocument"

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.USDMCombiner")

    def combine(
        self,
        agent_results: Dict[str, Any],
        pdf_path: str,
        model_name: str,
        quality_report: Optional[Dict[str, Any]] = None,
        include_agent_documentation: bool = True,
    ) -> Dict[str, Any]:
        """
        Combine all agent extraction results into a single USDM 4.0 document.

        Args:
            agent_results: Dictionary mapping module_id to extraction result
            pdf_path: Path to source PDF document
            model_name: LLM model used for extraction
            quality_report: Optional quality scores per agent
            include_agent_documentation: Whether to include agent documentation
                for downstream automation (default: True)

        Returns:
            USDM 4.0 compliant JSON structure
        """
        pdf_file = Path(pdf_path)
        protocol_id = self._extract_protocol_id(agent_results, pdf_file.stem)

        # Build source document metadata
        source_document = self._build_source_document(pdf_file)

        # Build extraction metadata
        extraction_metadata = self._build_extraction_metadata(
            agent_results=agent_results,
            model_name=model_name,
            quality_report=quality_report,
            pdf_path=pdf_file,
        )

        # Build USDM structure
        usdm_document = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "schemaVersion": self.SCHEMA_VERSION,
            "instanceType": self.INSTANCE_TYPE,
            "id": f"USDM-{protocol_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "name": f"Protocol Extraction: {protocol_id}",
            "sourceDocument": source_document,
            "extractionMetadata": extraction_metadata,
        }

        # Add study metadata first (root-level study information)
        if "study_metadata" in agent_results:
            study_data = agent_results["study_metadata"]
            # Study metadata becomes root-level properties
            usdm_document["study"] = self._normalize_study_metadata(study_data)

        # Add all domain sections with optional agent documentation
        usdm_document["domainSections"] = self._build_domain_sections(
            agent_results,
            include_agent_documentation=include_agent_documentation,
        )

        # Add provenance summary
        usdm_document["provenanceSummary"] = self._build_provenance_summary(agent_results)

        # Validate and correct provenance page numbers by searching for text_snippets in the PDF
        # This fixes LLM hallucination issues where the model returns incorrect page numbers
        if pdf_file.exists():
            try:
                with open(pdf_file, "rb") as f:
                    pdf_bytes = f.read()

                self.logger.info("Validating and correcting provenance page numbers...")
                validation_stats = validate_and_correct_provenance(pdf_bytes, usdm_document)

                # Store validation stats in metadata
                extraction_metadata["provenanceValidation"] = {
                    "totalProvenance": validation_stats["total_provenance"],
                    "corrected": validation_stats["corrected"],
                    "validated": validation_stats["validated"],
                    "notFound": validation_stats["not_found"],
                }

                if validation_stats["corrected"] > 0:
                    self.logger.info(
                        f"Corrected {validation_stats['corrected']} provenance page numbers "
                        f"(out of {validation_stats['total_provenance']} total)"
                    )
                    # Log some example corrections for debugging
                    for correction in validation_stats["corrections"][:5]:
                        self.logger.debug(
                            f"  Page {correction['original']} -> {correction['corrected']}: "
                            f"{correction['snippet_preview']}"
                        )
            except Exception as e:
                self.logger.warning(f"Failed to validate provenance: {e}")

        # Add agent documentation catalog for downstream automation
        if include_agent_documentation:
            usdm_document["agentDocumentation"] = self._build_agent_documentation_catalog(
                agent_results
            )

        self.logger.info(f"Combined {len(agent_results)} agent outputs into USDM 4.0 document")

        return usdm_document

    def _extract_protocol_id(
        self,
        agent_results: Dict[str, Any],
        fallback_id: str,
    ) -> str:
        """Extract protocol ID from study metadata or use fallback."""
        if "study_metadata" in agent_results:
            study = agent_results["study_metadata"]
            # Try different field names for protocol ID
            for field in ["protocolId", "protocol_id", "id", "studyProtocolVersion"]:
                if field in study:
                    value = study[field]
                    if isinstance(value, dict) and "value" in value:
                        return str(value["value"])
                    elif isinstance(value, str):
                        return value
        return fallback_id

    def _build_source_document(self, pdf_file: Path) -> Dict[str, Any]:
        """Build source document metadata with file fingerprint."""
        doc_info = {
            "documentId": None,
            "filename": pdf_file.name,
            "sha256Hash": None,
            "byteSize": None,
            "uploadTimestamp": datetime.now().isoformat(),
            "pageCount": None,
        }

        if pdf_file.exists():
            # Compute SHA256 hash
            sha256_hash = hashlib.sha256()
            with open(pdf_file, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256_hash.update(chunk)

            doc_info["sha256Hash"] = sha256_hash.hexdigest()
            doc_info["byteSize"] = pdf_file.stat().st_size
            doc_info["documentId"] = f"DOC-{sha256_hash.hexdigest()[:16].upper()}"

            # Try to get page count
            try:
                import fitz  # PyMuPDF
                with fitz.open(str(pdf_file)) as pdf:
                    doc_info["pageCount"] = len(pdf)
            except Exception:
                pass  # Page count is optional

        return doc_info

    def _build_extraction_metadata(
        self,
        agent_results: Dict[str, Any],
        model_name: str,
        quality_report: Optional[Dict[str, Any]] = None,
        pdf_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Build extraction process metadata."""
        metadata = {
            "extractionTimestamp": datetime.now().isoformat(),
            "pipelineVersion": "3.1",
            "primaryModel": model_name,
            "agentCount": len(agent_results),
            "successfulAgents": [],
            "failedAgents": [],
        }

        # Detect page numbering offset from PDF
        if pdf_path and pdf_path.exists():
            try:
                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()
                page_numbering_info = detect_page_offset(pdf_bytes)
                metadata["pageNumberingInfo"] = page_numbering_info
                self.logger.info(
                    f"Page numbering info detected: firstNumberedPage={page_numbering_info['firstNumberedPage']}, "
                    f"pageOffset={page_numbering_info['pageOffset']}, confidence={page_numbering_info['confidence']}"
                )
            except Exception as e:
                self.logger.warning(f"Failed to detect page offset: {e}")
                # Default values if detection fails
                metadata["pageNumberingInfo"] = {
                    "firstNumberedPage": 1,
                    "pageOffset": 0,
                    "detectedAt": datetime.now().isoformat() + "Z",
                    "confidence": "none",
                    "error": str(e)
                }

        # Categorize agents by success/failure
        for module_id in agent_results:
            if agent_results[module_id] is not None:
                metadata["successfulAgents"].append(module_id)
            else:
                metadata["failedAgents"].append(module_id)

        # Add quality summary if available
        if quality_report:
            quality_summary = {}
            for module_id, scores in quality_report.items():
                if isinstance(scores, dict) and "overall" in scores:
                    quality_summary[module_id] = {
                        "overallScore": scores.get("overall", 0),
                        "fromCache": scores.get("from_cache", False),
                    }
            metadata["qualitySummary"] = quality_summary

            # Compute average quality
            valid_scores = [
                s.get("overall", 0)
                for s in quality_report.values()
                if isinstance(s, dict) and "error" not in s
            ]
            if valid_scores:
                metadata["averageQualityScore"] = sum(valid_scores) / len(valid_scores)

        return metadata

    def _normalize_study_metadata(self, study_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize study metadata to USDM 4.0 Study structure.

        This extracts the core study information and structures it properly.
        """
        normalized = {
            "instanceType": "Study",
        }

        # Copy all fields from study_data, handling value+provenance patterns
        for key, value in study_data.items():
            if key in ["_metadata", "schemaVersion", "sourceDocument"]:
                continue  # Skip internal metadata

            # Handle value+provenance pattern
            if isinstance(value, dict) and "value" in value:
                normalized[key] = value  # Keep the structure
            else:
                normalized[key] = value

        return normalized

    def _apply_page_offset_to_provenance(self, data: Any, offset: int) -> None:
        """
        Recursively apply page offset correction to all provenance page numbers.

        The LLM extracts printed page numbers from document footers, but we need
        physical PDF page numbers. This function adds the offset to convert:
            physical_page = printed_page + offset

        Args:
            data: Any JSON-serializable data structure (dict, list, or primitive)
            offset: The page offset to add (physical_page - printed_page)
        """
        if isinstance(data, dict):
            # Check if this is a provenance object with page_number
            if "provenance" in data and isinstance(data["provenance"], dict):
                prov = data["provenance"]
                if "page_number" in prov and isinstance(prov["page_number"], int):
                    original = prov["page_number"]
                    prov["page_number"] = original + offset
                    # Store original for debugging/audit
                    prov["_original_page_number"] = original

            # Also check if this dict itself is a provenance object
            if "page_number" in data and "text_snippet" in data:
                if isinstance(data["page_number"], int):
                    original = data["page_number"]
                    data["page_number"] = original + offset
                    data["_original_page_number"] = original

            # Recurse into all values
            for value in data.values():
                self._apply_page_offset_to_provenance(value, offset)

        elif isinstance(data, list):
            # Recurse into all items
            for item in data:
                self._apply_page_offset_to_provenance(item, offset)

    def _build_domain_sections(
        self,
        agent_results: Dict[str, Any],
        include_agent_documentation: bool = True,
    ) -> Dict[str, Any]:
        """
        Build domain-specific sections from agent results.

        Each agent's output becomes a named section in the USDM document.
        Optionally includes agent documentation for downstream automation.
        """
        sections = {}

        for module_id, result in agent_results.items():
            if result is None:
                continue

            # Get USDM section key
            section_key = MODULE_TO_USDM_SECTION.get(module_id, module_id)

            # Skip study_metadata (handled separately at root level)
            if module_id == "study_metadata":
                continue

            # Clean the result (remove internal metadata)
            cleaned = self._clean_section_data(result)

            section_entry = {
                "moduleId": module_id,
                "instanceType": self._get_instance_type(module_id),
                "data": cleaned,
            }

            # Add agent documentation for downstream automation context
            if include_agent_documentation:
                agent_doc = generate_agent_documentation_json(module_id)
                if agent_doc:
                    section_entry["_agentDocumentation"] = agent_doc

            sections[section_key] = section_entry

        return sections

    def _build_agent_documentation_catalog(
        self,
        agent_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build a catalog of agent documentation for downstream automation.

        This section provides comprehensive documentation about what each agent
        extracts, how the data should be used, and integration points with
        downstream systems (EDC, IRT, ePRO, etc.).
        """
        catalog = {
            "description": (
                "Agent documentation for downstream system automation. "
                "Each agent's documentation describes its purpose, key insights, "
                "downstream system integrations, and automation use cases."
            ),
            "agents": {},
            "downstreamSystemCoverage": {},
            "automationCategories": {},
        }

        # Build per-agent documentation
        for module_id in agent_results:
            if agent_results[module_id] is None:
                continue

            agent_doc = generate_agent_documentation_json(module_id)
            if agent_doc:
                catalog["agents"][module_id] = agent_doc

                # Track downstream system coverage
                for system in agent_doc.get("downstreamSystems", []):
                    if system not in catalog["downstreamSystemCoverage"]:
                        catalog["downstreamSystemCoverage"][system] = []
                    catalog["downstreamSystemCoverage"][system].append(module_id)

                # Track automation categories
                for insight in agent_doc.get("keyInsights", []):
                    category = insight.get("automationCategory")
                    if category:
                        if category not in catalog["automationCategories"]:
                            catalog["automationCategories"][category] = []
                        catalog["automationCategories"][category].append({
                            "agent": module_id,
                            "insight": insight.get("name"),
                            "priority": insight.get("priority"),
                        })

        # Build integration graph
        catalog["integrationGraph"] = self._build_integration_graph(agent_results)

        return catalog

    def _build_integration_graph(
        self,
        agent_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build a graph showing how agents integrate with each other.

        Returns:
            Dictionary with nodes (agents) and edges (data flows).
        """
        nodes = []
        edges = []

        for module_id in agent_results:
            if agent_results[module_id] is None:
                continue

            if module_id not in AGENT_DOCUMENTATION_REGISTRY:
                continue

            doc = AGENT_DOCUMENTATION_REGISTRY[module_id]
            nodes.append({
                "id": module_id,
                "displayName": doc.display_name,
                "wave": doc.wave,
                "priority": doc.priority,
            })

            # Add dependency edges
            for dep in doc.depends_on:
                edges.append({
                    "source": dep,
                    "target": module_id,
                    "type": "depends_on",
                })

            # Add enrichment edges
            for target in doc.enriches:
                edges.append({
                    "source": module_id,
                    "target": target,
                    "type": "enriches",
                })

            # Add cross-reference edges
            for ref in doc.cross_references:
                edges.append({
                    "source": module_id,
                    "target": ref,
                    "type": "cross_references",
                })

        return {
            "nodes": nodes,
            "edges": edges,
        }

    def _clean_section_data(self, data: Any) -> Any:
        """Remove internal metadata fields from section data."""
        if isinstance(data, dict):
            cleaned = {}
            for key, value in data.items():
                # Skip internal fields
                if key.startswith("_") or key in ["schemaVersion", "sourceDocument"]:
                    continue
                cleaned[key] = self._clean_section_data(value)
            return cleaned
        elif isinstance(data, list):
            return [self._clean_section_data(item) for item in data]
        else:
            return data

    def _get_instance_type(self, module_id: str) -> str:
        """Get USDM instance type for a module."""
        instance_types = {
            "arms_design": "StudyDesign",
            "endpoints_estimands_sap": "EndpointsEstimandsSAP",
            "adverse_events": "AdverseEvents",
            "safety_decision_points": "SafetyDecisionPoints",
            "concomitant_medications": "ConcomitantMedications",
            "biospecimen_handling": "BiospecimenHandling",
            "laboratory_specifications": "LaboratorySpecifications",
            "data_management": "DataManagement",
            "site_operations_logistics": "SiteOperationsLogistics",
            "quality_management": "QualityManagement",
            "withdrawal_procedures": "WithdrawalProcedures",
            "imaging_central_reading": "ImagingCentralReading",
            "pkpd_sampling": "PKPDSampling",
            "informed_consent": "InformedConsentElements",
            "pro_specifications": "PROSpecifications",
        }
        return instance_types.get(module_id, module_id)

    def _build_provenance_summary(
        self,
        agent_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build a summary of provenance information across all sections.

        Collects all page references to show which pages were used.
        """
        page_references: Dict[int, List[str]] = {}
        section_pages: Dict[str, List[int]] = {}

        for module_id, result in agent_results.items():
            if result is None:
                continue

            # Collect pages from this section
            pages = self._collect_page_numbers(result)

            section_key = MODULE_TO_USDM_SECTION.get(module_id, module_id)
            section_pages[section_key] = sorted(list(pages))

            # Build reverse index
            for page in pages:
                if page not in page_references:
                    page_references[page] = []
                page_references[page].append(section_key)

        # Get all unique pages
        all_pages = sorted(page_references.keys())

        return {
            "totalPagesReferenced": len(all_pages),
            "pageRange": [min(all_pages), max(all_pages)] if all_pages else [0, 0],
            "sectionPageCounts": {
                section: len(pages)
                for section, pages in section_pages.items()
            },
            "pageToSections": {
                str(page): sections
                for page, sections in sorted(page_references.items())
            },
        }

    def _collect_page_numbers(self, data: Any, pages: Optional[set] = None) -> set:
        """Recursively collect all page numbers from provenance fields."""
        if pages is None:
            pages = set()

        if isinstance(data, dict):
            # Check for page_number in provenance
            if "page_number" in data and isinstance(data["page_number"], int):
                pages.add(data["page_number"])

            # Also check for provenance sub-object
            if "provenance" in data and isinstance(data["provenance"], dict):
                if "page_number" in data["provenance"]:
                    page = data["provenance"]["page_number"]
                    if isinstance(page, int):
                        pages.add(page)

            # Recurse into all values
            for value in data.values():
                self._collect_page_numbers(value, pages)

        elif isinstance(data, list):
            for item in data:
                self._collect_page_numbers(item, pages)

        return pages


def combine_agent_outputs(
    agent_results: Dict[str, Any],
    pdf_path: str,
    model_name: str,
    quality_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Convenience function to combine agent outputs into USDM 4.0.

    Args:
        agent_results: Dictionary mapping module_id to extraction result
        pdf_path: Path to source PDF document
        model_name: LLM model used for extraction
        quality_report: Optional quality scores per agent

    Returns:
        USDM 4.0 compliant JSON structure
    """
    combiner = USDMCombiner()
    return combiner.combine(
        agent_results=agent_results,
        pdf_path=pdf_path,
        model_name=model_name,
        quality_report=quality_report,
    )
