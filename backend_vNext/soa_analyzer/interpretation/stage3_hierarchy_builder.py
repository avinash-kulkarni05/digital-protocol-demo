"""
Stage 3: Activity Hierarchy Builder (Enhanced with Stage 2 Expansions)

Builds hierarchical structure from activities and their component expansions:
1. CDISC domain groupings as top-level categories
2. Activities as second level (parents with expanded components, or leaves)
3. Component activities from Stage 2 as children of expanded activities

Design Principles:
1. Domain-First Grouping - Use cdashDomain as primary hierarchy level
2. Expansion Integration - Incorporate Stage 2 component expansions as children
3. UI-Friendly Tree - Build collapsible tree for frontend display
4. Provenance Preservation - Link components to source activities

Output Structure:
    DOM-VS (Vital Signs)
    ├── ACT-006 Vital Signs [expanded]
    │   ├── COMP-xxx Systolic Blood Pressure
    │   ├── COMP-xxx Diastolic Blood Pressure
    │   └── COMP-xxx Pulse
    ├── ACT-007 SpO2 [leaf]
    └── ACT-009 Height [leaf]

Usage:
    from soa_analyzer.interpretation.stage3_hierarchy_builder import HierarchyBuilder

    builder = HierarchyBuilder()
    result = builder.build_hierarchy(usdm_output, stage2_result)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..models.expansion_proposal import (
    ActivityHierarchy,
    ActivityHierarchyNode,
    HumanReviewItem,
)

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


# Domain display names and order
DOMAIN_INFO = {
    "DM": {"name": "Demographics", "order": 1},
    "MH": {"name": "Medical History", "order": 2},
    "PE": {"name": "Physical Examination", "order": 3},
    "VS": {"name": "Vital Signs", "order": 4},
    "EG": {"name": "ECG/Cardiac Assessments", "order": 5},
    "LB": {"name": "Laboratory Tests", "order": 6},
    "MI": {"name": "Medical Imaging", "order": 7},
    "BS": {"name": "Biospecimen Collection", "order": 8},
    "PC": {"name": "Pharmacokinetics", "order": 9},
    "EX": {"name": "Exposure/Treatment", "order": 10},
    "CM": {"name": "Concomitant Medications", "order": 11},
    "AE": {"name": "Adverse Events", "order": 12},
    "QS": {"name": "Questionnaires/PROs", "order": 13},
    "TU": {"name": "Tumor/Oncology", "order": 14},
    "PR": {"name": "Procedures", "order": 15},
    "DS": {"name": "Disposition", "order": 16},
}


@dataclass
class HierarchyConfig:
    """Configuration for hierarchy building."""
    use_llm_enhancement: bool = False
    detect_header_rows: bool = True
    group_by_domain: bool = True
    include_uncategorized: bool = True


@dataclass
class Stage3Result:
    """Result of Stage 3 hierarchy building."""
    hierarchy: ActivityHierarchy = field(default_factory=ActivityHierarchy)
    header_rows: List[str] = field(default_factory=list)
    domain_counts: Dict[str, int] = field(default_factory=dict)
    review_items: List[HumanReviewItem] = field(default_factory=list)
    activities_processed: int = 0
    categories_created: int = 0
    header_rows_detected: int = 0
    # New: Stage 2 expansion integration
    activities_with_components: int = 0
    total_components: int = 0
    leaf_activities: int = 0

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of hierarchy building results."""
        return {
            "activitiesProcessed": self.activities_processed,
            "categoriesCreated": self.categories_created,
            "headerRowsDetected": self.header_rows_detected,
            "activitiesWithComponents": self.activities_with_components,
            "totalComponents": self.total_components,
            "leafActivities": self.leaf_activities,
            "domainCounts": self.domain_counts,
            "reviewItemsCount": len(self.review_items),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary for stage output."""
        return {
            "stage": 3,
            "stageName": "Hierarchy Builder",
            "success": True,
            "hierarchy": self.hierarchy.to_dict() if self.hierarchy else None,
            "headerRows": self.header_rows,
            "metrics": {
                "activitiesProcessed": self.activities_processed,
                "categoriesCreated": self.categories_created,
                "headerRowsDetected": self.header_rows_detected,
                "activitiesWithComponents": self.activities_with_components,
                "totalComponents": self.total_components,
                "leafActivities": self.leaf_activities,
                "domainCounts": self.domain_counts,
            },
            "reviewItems": [r.to_dict() for r in self.review_items],
        }


class HierarchyBuilder:
    """
    Stage 3: Activity Hierarchy Builder.

    Builds hierarchical organization of activities for UI display.
    """

    def __init__(self, config: Optional[HierarchyConfig] = None):
        """Initialize the hierarchy builder."""
        self.config = config or HierarchyConfig()

    def build_hierarchy(
        self,
        usdm_output: Dict[str, Any],
        stage2_result: Optional[Dict[str, Any]] = None,
    ) -> Stage3Result:
        """
        Build activity hierarchy with Stage 2 component expansions.

        Args:
            usdm_output: USDM output with categorized activities
            stage2_result: Stage 2 result with component expansions (optional)

        Returns:
            Stage3Result with hierarchy including parent-child relationships

        Output Structure:
            DOM-VS (category)
            ├── ACT-006 Vital Signs (activity, has components)
            │   ├── COMP-xxx Systolic Blood Pressure (component)
            │   ├── COMP-xxx Diastolic Blood Pressure (component)
            │   └── COMP-xxx Pulse (component)
            ├── ACT-007 SpO2 (activity, leaf)
            └── ACT-009 Height (activity, leaf)
        """
        result = Stage3Result()
        result.hierarchy = ActivityHierarchy()

        # Get activities from USDM structure
        activities = self._get_activities(usdm_output)
        result.activities_processed = len(activities)

        # Build expansion map from Stage 2 result: {parent_activity_id: [components]}
        expansion_map: Dict[str, List[Dict[str, Any]]] = {}
        if stage2_result:
            expansions = stage2_result.get("expansions", [])
            for expansion in expansions:
                parent_id = expansion.get("parentActivityId", "")
                components = expansion.get("components", [])
                if parent_id and components:
                    expansion_map[parent_id] = components
                    result.total_components += len(components)

        logger.info(
            f"Stage 3: Building hierarchy for {len(activities)} activities "
            f"({len(expansion_map)} with component expansions, {result.total_components} total components)"
        )

        # Step 1: Detect header rows
        if self.config.detect_header_rows:
            header_activity_ids = self._detect_header_rows(activities)
            result.header_rows = list(header_activity_ids)
            result.header_rows_detected = len(header_activity_ids)
        else:
            header_activity_ids = set()

        # Step 2: Group activities by domain
        domain_groups: Dict[str, List[Dict[str, Any]]] = {}
        uncategorized: List[Dict[str, Any]] = []

        for activity in activities:
            activity_id = activity.get("id", "")

            # Skip header rows
            if activity_id in header_activity_ids:
                continue

            cdash_domain = activity.get("cdashDomain", "")

            if cdash_domain and cdash_domain in DOMAIN_INFO:
                if cdash_domain not in domain_groups:
                    domain_groups[cdash_domain] = []
                domain_groups[cdash_domain].append(activity)
            else:
                uncategorized.append(activity)

        # Step 3: Build hierarchy tree with component children
        for domain, activities_in_domain in domain_groups.items():
            domain_info = DOMAIN_INFO.get(domain, {"name": domain, "order": 99})

            # Create domain node
            domain_node = ActivityHierarchyNode(
                id=f"DOM-{domain}",
                name=domain_info["name"],
                node_type="category",
                cdash_domain=domain,
                order=domain_info["order"],
            )

            # Add activities as children of domain
            for idx, activity in enumerate(activities_in_domain):
                activity_id = activity.get("id", "")
                activity_name = activity.get("name", "")

                # Check if this activity has component expansions
                if activity_id in expansion_map:
                    # Create activity node with component children
                    activity_node = ActivityHierarchyNode(
                        id=activity_id,
                        name=activity_name,
                        node_type="activity",
                        cdash_domain=domain,
                        order=idx,
                        is_expanded=True,
                    )

                    # Add components as children (with full metadata from Stage 2)
                    for comp_idx, component in enumerate(expansion_map[activity_id]):
                        component_node = ActivityHierarchyNode(
                            id=component.get("id", f"COMP-{activity_id}-{comp_idx}"),
                            name=component.get("name", ""),
                            node_type="component",
                            cdash_domain=domain,
                            order=comp_idx,
                            is_expanded=False,
                            # Component-specific metadata from Stage 2
                            confidence=component.get("confidence"),
                            unit=component.get("unit"),
                            is_required=component.get("isRequired"),
                            provenance=component.get("provenance"),
                        )
                        activity_node.children.append(component_node)

                    domain_node.children.append(activity_node)
                    result.activities_with_components += 1
                else:
                    # Leaf activity (no expansion)
                    activity_node = ActivityHierarchyNode(
                        id=activity_id,
                        name=activity_name,
                        node_type="activity",
                        cdash_domain=domain,
                        order=idx,
                        is_expanded=False,
                    )
                    domain_node.children.append(activity_node)
                    result.leaf_activities += 1

            result.hierarchy.root_nodes.append(domain_node)
            result.hierarchy.total_categories += 1
            result.hierarchy.total_activities += len(activities_in_domain)
            result.domain_counts[domain] = len(activities_in_domain)

        # Step 4: Handle uncategorized activities
        if uncategorized and self.config.include_uncategorized:
            uncategorized_node = ActivityHierarchyNode(
                id="DOM-UNKNOWN",
                name="Uncategorized",
                node_type="category",
                cdash_domain="UNKNOWN",
                order=999,
            )

            for idx, activity in enumerate(uncategorized):
                activity_id = activity.get("id", "")
                activity_name = activity.get("name", "")

                # Check for expansions even in uncategorized
                if activity_id in expansion_map:
                    activity_node = ActivityHierarchyNode(
                        id=activity_id,
                        name=activity_name,
                        node_type="activity",
                        cdash_domain="UNKNOWN",
                        order=idx,
                        is_expanded=True,
                    )
                    for comp_idx, component in enumerate(expansion_map[activity_id]):
                        component_node = ActivityHierarchyNode(
                            id=component.get("id", f"COMP-{activity_id}-{comp_idx}"),
                            name=component.get("name", ""),
                            node_type="component",
                            order=comp_idx,
                        )
                        activity_node.children.append(component_node)
                    uncategorized_node.children.append(activity_node)
                    result.activities_with_components += 1
                else:
                    activity_node = ActivityHierarchyNode(
                        id=activity_id,
                        name=activity_name,
                        node_type="activity",
                        order=idx,
                    )
                    uncategorized_node.children.append(activity_node)
                    result.leaf_activities += 1

            if uncategorized_node.children:
                result.hierarchy.root_nodes.append(uncategorized_node)
                result.hierarchy.total_categories += 1
                result.hierarchy.total_activities += len(uncategorized)
                result.domain_counts["UNKNOWN"] = len(uncategorized)

                result.review_items.append(HumanReviewItem(
                    item_type="hierarchy",
                    title=f"{len(uncategorized)} uncategorized activities",
                    description="These activities could not be assigned to a CDISC domain",
                    priority="medium",
                    confidence=0.0,
                ))

        # Step 5: Sort hierarchy
        result.hierarchy.sort_nodes()
        result.categories_created = len(result.hierarchy.root_nodes)

        logger.info(
            f"Stage 3 complete: {result.categories_created} categories, "
            f"{result.hierarchy.total_activities} activities "
            f"({result.activities_with_components} with {result.total_components} components, "
            f"{result.leaf_activities} leaf activities)"
        )

        return result

    def _get_activities(self, usdm_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract activities from USDM structure."""
        # Handle nested structure
        if "studyVersion" in usdm_output:
            study_version = usdm_output["studyVersion"]
            if isinstance(study_version, list) and study_version:
                return study_version[0].get("activities", [])
        return usdm_output.get("activities", [])

    def _detect_header_rows(self, activities: List[Dict[str, Any]]) -> Set[str]:
        """
        Detect activities that are likely header rows (not actual assessments).

        Header row indicators:
        - ALL CAPS text (must be entirely uppercase)
        - Category keywords (TESTS, ASSESSMENTS, PROCEDURES)
        - Activities with no SAI references
        """
        header_ids = set()

        # Patterns that should match case-sensitively (for ALL CAPS detection)
        all_caps_pattern = r"^[A-Z][A-Z\s]+$"  # Starts with uppercase, rest is uppercase or space

        # Patterns that match common header keywords (case-insensitive)
        keyword_patterns = [
            r"(?:LABORATORY|SAFETY|EFFICACY|SCREENING|TREATMENT)\s+(?:TESTS|ASSESSMENTS|PROCEDURES)$",
            r"^(?:SECTION|CATEGORY)\s*:?\s*",
        ]

        for activity in activities:
            activity_id = activity.get("id", "")
            activity_name = activity.get("name", "").strip()

            is_header = False

            # Check if ALL CAPS (and longer than 10 chars to avoid abbreviations like "ECG")
            if len(activity_name) > 10 and activity_name.isupper():
                # Verify it's truly all caps (no lowercase letters mixed in)
                if re.match(all_caps_pattern, activity_name):
                    is_header = True

            # Check keyword patterns (case-insensitive)
            if not is_header:
                for pattern in keyword_patterns:
                    if re.search(pattern, activity_name, re.IGNORECASE):
                        is_header = True
                        break

            if is_header:
                header_ids.add(activity_id)
                logger.debug(f"Detected header row: '{activity_name}'")

        return header_ids

    def _build_subcategories(
        self,
        activities: List[Dict[str, Any]],
        domain_node: ActivityHierarchyNode,
    ) -> None:
        """
        Build subcategories within a domain based on activity names.

        For example, within LB domain:
        - Hematology
        - Clinical Chemistry
        - Urinalysis
        """
        # Group by category if available
        category_groups: Dict[str, List[str]] = {}

        for activity in activities:
            activity_id = activity.get("id", "")
            category = activity.get("category", "")

            if category and category != "UNKNOWN":
                if category not in category_groups:
                    category_groups[category] = []
                category_groups[category].append(activity_id)

        # If we have subcategories, create child nodes
        if len(category_groups) > 1:
            for category, activity_ids in category_groups.items():
                subcat_node = ActivityHierarchyNode(
                    id=f"SUBCAT-{category[:8].upper()}",
                    name=category.replace("_", " ").title(),
                    node_type="subcategory",
                    cdash_domain=domain_node.cdash_domain,
                    activity_ids=activity_ids,
                )
                domain_node.children.append(subcat_node)
        else:
            # No subcategories, add activities directly
            for activity in activities:
                domain_node.activity_ids.append(activity.get("id", ""))

    def apply_hierarchy_to_usdm(
        self,
        usdm_output: Dict[str, Any],
        result: Stage3Result,
    ) -> Dict[str, Any]:
        """
        Apply hierarchy information to USDM output.

        Adds _hierarchy metadata to activities and creates a hierarchy index.

        New structure (3 levels):
        - Domain nodes (category) → children are activity nodes
        - Activity nodes → children are component nodes (if expanded)
        - Component nodes → leaf nodes
        """
        # Create activity-to-domain mapping from new 3-level structure
        activity_domain_map: Dict[str, str] = {}
        activity_component_count: Dict[str, int] = {}

        for domain_node in result.hierarchy.root_nodes:
            domain = domain_node.cdash_domain or ""

            # Activity nodes are now children of domain nodes
            for activity_node in domain_node.children:
                activity_id = activity_node.id
                activity_domain_map[activity_id] = domain
                activity_component_count[activity_id] = len(activity_node.children)

        # Get activities (handle nested structure safely)
        if "studyVersion" in usdm_output:
            study_version = usdm_output.get("studyVersion", [])
            if isinstance(study_version, list) and study_version:
                activities = study_version[0].get("activities", [])
            else:
                activities = []
        else:
            activities = usdm_output.get("activities", [])

        # Annotate activities with hierarchy metadata
        for activity in activities:
            activity_id = activity.get("id", "")

            if activity_id in result.header_rows:
                activity["_isHeaderRow"] = True

            if activity_id in activity_domain_map:
                activity["_hierarchyDomain"] = activity_domain_map[activity_id]

            if activity_id in activity_component_count:
                activity["_componentCount"] = activity_component_count[activity_id]

        # Add hierarchy to output (handle nested structure safely)
        if "studyVersion" in usdm_output:
            study_version = usdm_output.get("studyVersion", [])
            if isinstance(study_version, list) and study_version:
                study_version[0]["_activityHierarchy"] = result.hierarchy.to_dict()
        else:
            usdm_output["_activityHierarchy"] = result.hierarchy.to_dict()

        return usdm_output

    def build_hierarchy_with_llm(
        self,
        usdm_output: Dict[str, Any],
    ) -> Stage3Result:
        """
        Build hierarchy using LLM for complex relationship detection.

        This method is used when config.use_llm_enhancement is True.
        """
        result = self.build_hierarchy(usdm_output)

        if not self.config.use_llm_enhancement:
            return result

        # Get activities for LLM analysis
        activities = self._get_activities(usdm_output)

        if not activities:
            return result

        # Load prompt template
        prompt_file = PROMPTS_DIR / "hierarchy_detection.txt"
        if not prompt_file.exists():
            logger.warning("Hierarchy detection prompt not found, skipping LLM enhancement")
            return result

        try:
            with open(prompt_file, "r") as f:
                prompt_template = f.read()
        except Exception as e:
            logger.error(f"Failed to load prompt template: {e}")
            return result

        # Prepare activities JSON
        activities_for_llm = [
            {
                "activityId": a.get("id", ""),
                "activityName": a.get("name", ""),
                "category": a.get("category", ""),
                "cdashDomain": a.get("cdashDomain", ""),
            }
            for a in activities
        ]

        activities_json = json.dumps(activities_for_llm, indent=2)
        prompt = prompt_template.format(
            activities_json=activities_json,
            activity_count=len(activities),
        )

        # Call LLM
        try:
            from ..soa_html_interpreter import call_llm
            response = call_llm(prompt, max_tokens=8192)

            if response:
                llm_result = self._parse_llm_hierarchy(response)
                result = self._merge_llm_hierarchy(result, llm_result)

        except ImportError:
            logger.warning("LLM module not available, skipping LLM enhancement")
        except Exception as e:
            logger.error(f"LLM hierarchy enhancement failed: {e}")

        return result

    def _parse_llm_hierarchy(self, response: str) -> Dict[str, Any]:
        """Parse LLM hierarchy response."""
        try:
            # First try direct parse
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in response
        json_match = re.search(r"\{[\s\S]*\}", response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse LLM hierarchy response as JSON")
        return {}

    def _merge_llm_hierarchy(
        self,
        result: Stage3Result,
        llm_result: Dict[str, Any],
    ) -> Stage3Result:
        """Merge LLM hierarchy insights with domain-based hierarchy."""
        # Add any additional header rows detected by LLM
        for header in llm_result.get("headerRows", []):
            if header.get("isHeader", False):
                activity_id = header.get("activityId", "")
                if activity_id and activity_id not in result.header_rows:
                    result.header_rows.append(activity_id)
                    result.header_rows_detected += 1

        # Add parent-child relationships as review items if confidence is low
        for relationship in llm_result.get("parentChildRelationships", []):
            confidence = relationship.get("confidence", 0.0)
            if confidence < 0.90:
                result.review_items.append(HumanReviewItem(
                    item_type="hierarchy_relationship",
                    title=f"Review parent-child: {relationship.get('parentActivityName', '')}",
                    description=f"LLM suggests {len(relationship.get('childActivityIds', []))} child activities",
                    confidence=confidence,
                    priority="low",
                ))

        return result


def build_hierarchy(
    usdm_output: Dict[str, Any],
    stage2_result: Optional[Dict[str, Any]] = None,
    config: Optional[HierarchyConfig] = None,
) -> Tuple[Dict[str, Any], Stage3Result]:
    """
    Convenience function to build hierarchy with Stage 2 expansions.

    Args:
        usdm_output: USDM output with categorized activities
        stage2_result: Stage 2 result with component expansions
        config: Optional hierarchy configuration

    Returns:
        Tuple of (updated USDM output, hierarchy result)
    """
    builder = HierarchyBuilder(config)
    result = builder.build_hierarchy(usdm_output, stage2_result)
    updated_output = builder.apply_hierarchy_to_usdm(usdm_output, result)
    return updated_output, result
