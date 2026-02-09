# SOA Analysis Module - Solution Overview

## Executive Summary

The Schedule of Assessments (SOA) Analysis Module is an AI-powered system that transforms clinical trial protocol PDFs into structured, machine-readable USDM 4.0 compliant JSON. This document outlines the solution architecture, design philosophy, and how it addresses critical requirements for EDC (Electronic Data Capture) build automation.

---

## Table of Contents

1. [Business Context & EDC Requirements](#1-business-context--edc-requirements)
2. [Solution Architecture](#2-solution-architecture)
3. [Design Philosophy](#3-design-philosophy)
4. [Multi-Phase Extraction Pipeline](#4-multi-phase-extraction-pipeline)
5. [The 12-Stage Interpretation Pipeline](#5-the-12-stage-interpretation-pipeline)
6. [Data Flow & Transformation](#6-data-flow--transformation)
7. [Quality Framework](#7-quality-framework)
8. [Integration Points](#8-integration-points)
9. [Human-in-the-Loop Design](#9-human-in-the-loop-design)
10. [EDC Build Automation Mapping](#10-edc-build-automation-mapping)
11. [Technical Implementation](#11-technical-implementation)

---

## 1. Business Context & EDC Requirements

### 1.1 The EDC Build Challenge

Building an Electronic Data Capture system for a clinical trial requires translating protocol requirements into:

| EDC Component | Source in Protocol | Challenge |
|---------------|-------------------|-----------|
| **Visit Schedule** | SOA table columns | Identifying visit windows, cycle patterns, conditional visits |
| **Forms/eCRFs** | SOA table rows + protocol sections | Mapping activities to CDASH domains, determining data fields |
| **Edit Checks** | Footnotes + protocol text | Extracting conditional logic, visit windows, timing rules |
| **Lab Panels** | Lab specifications section | Linking SOA activities to detailed specimen requirements |
| **Timing Rules** | SOA headers + footnotes | Parsing relative timing (Day 1, Week 4), windows (±3 days) |

### 1.2 Core EDC Automation Requirements

The SOA Analysis Module addresses these key requirements:

#### R1: Visit Structure Extraction
**Requirement**: Extract complete visit schedule with timing, windows, and cycle patterns.
**Solution**: Stages 7-8 handle timing distribution and cycle expansion, producing structured visit definitions with:
- Absolute and relative timing
- Visit windows (early/late bounds)
- Cycle-based repetition patterns
- Open-ended pattern detection (e.g., "Cycle 4 and subsequent")

#### R2: Activity-to-Domain Mapping
**Requirement**: Map SOA activities to CDASH/SDTM domains for eCRF design.
**Solution**: Stage 1 performs domain categorization using LLM reasoning against CDISC codelist terminology, producing:
- Domain codes (VS, LB, EG, etc.)
- Confidence scores for human review
- Batch processing for efficiency

#### R3: Activity Decomposition
**Requirement**: Break down composite activities (e.g., "Vital Signs") into individual data collection items.
**Solution**: Stage 2 expands parent activities into components using protocol context:
- "Vital Signs" → Blood Pressure, Heart Rate, Temperature, SpO2, Respiratory Rate
- "Hematology" → 31 individual lab parameters
- Uses extraction outputs from main pipeline for accuracy

#### R4: Specimen Requirements
**Requirement**: Link lab activities to tube types, volumes, and processing requirements.
**Solution**: Stage 5 enriches specimen-collecting activities with:
- Tube type (EDTA, SST, etc.)
- Collection volume
- Processing instructions
- Storage conditions
- ATHENA concept mappings

#### R5: Conditional Logic Extraction
**Requirement**: Identify activities with population or clinical conditions.
**Solution**: Stage 6 parses footnotes to extract:
- Population conditions ("For female subjects only")
- Clinical conditions ("If clinically indicated")
- Links conditions to specific activities via ConditionAssignment

#### R6: Cross-Reference Enrichment
**Requirement**: Link SOA activities to detailed specifications in other protocol sections.
**Solution**: Stage 9 (Protocol Mining) cross-references 15+ extraction modules:
- Laboratory specifications → detailed panel definitions
- PK/PD sampling → sampling timepoints and volumes
- Biospecimen handling → processing requirements
- Adverse events → safety monitoring parameters

#### R7: Human Review Integration
**Requirement**: Flag uncertain extractions for SME review before EDC build.
**Solution**: Stage 10 assembles a review package with:
- All low-confidence items (<0.95)
- Expansion decisions requiring validation
- Open-ended patterns needing manual specification

#### R8: USDM Compliance
**Requirement**: Output must conform to USDM 4.0 standard for downstream tooling.
**Solution**: Stage 12 enforces compliance:
- Injects `instanceType` fields
- Expands Code objects to 6-field USDM format
- Validates referential integrity
- Generates schedule timelines

---

## 2. Solution Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         SOA EXTRACTION PIPELINE                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                      PHASE 1-2: EXTRACTION                                   │ │
│  │  ┌──────────────┐    ┌──────────────┐                                       │ │
│  │  │  Detection   │───▶│  Extraction  │                                       │ │
│  │  │ Gemini Vision│    │  LandingAI   │                                       │ │
│  │  │  SOA Pages   │    │  7x Zoom OCR │                                       │ │
│  │  └──────────────┘    └──────────────┘                                       │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                   PHASE 3: HTML INTERPRETATION                               │ │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │ │
│  │  │  Claude P1   │───▶│  Claude P2   │───▶│   Python P3  │                   │ │
│  │  │  Structure   │    │ Compact Matrix│   │ SAI Expansion│                   │ │
│  │  │ 16K tokens   │    │  8K tokens   │    │ Deterministic│                   │ │
│  │  └──────────────┘    └──────────────┘    └──────────────┘                   │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │              PHASE 3 (CONTINUED): 12-STAGE INTERPRETATION                    │ │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐   │ │
│  │  │ S1  │▶│ S2  │▶│ S3  │▶│ S4  │▶│ S5  │▶│ S6  │▶│ S7  │▶│ S8  │▶│ S9  │   │ │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘   │ │
│  │      │                                                               │       │ │
│  │      ▼                                                               ▼       │ │
│  │  ┌─────┐ ◀──────────────────────────────────────────────────── ┌─────┐     │ │
│  │  │ S12 │                                                        │ S10 │     │ │
│  │  └─────┘ ───────────────────────────────────────────────────── └─────┘     │ │
│  │      │                                                               ▲       │ │
│  │      ▼                                                               │       │ │
│  │  ┌─────┐ ──────────────────────────────────────────────────────────┘       │ │
│  │  │ S11 │                                                                    │ │
│  │  └─────┘                                                                    │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │                      PHASE 4-5: VALIDATION & OUTPUT                          │ │
│  │  ┌──────────────┐    ┌──────────────┐                                       │ │
│  │  │  Validation  │───▶│    Output    │                                       │ │
│  │  │ 5D Quality   │    │  USDM JSON   │                                       │ │
│  │  │  Framework   │    │ Quality Rpt  │                                       │ │
│  │  └──────────────┘    └──────────────┘                                       │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Responsibilities

| Component | Technology | Responsibility |
|-----------|------------|----------------|
| **SOA Page Detector** | Gemini Vision | Identify SOA table boundaries in PDF |
| **Table Extractor** | LandingAI OCR | Convert PDF pages to HTML at 7x zoom |
| **HTML Interpreter** | Claude Sonnet | Three-phase HTML to USDM transformation |
| **Interpretation Pipeline** | 12 Stages | Enrich, expand, and validate |
| **Quality Checker** | Rules + LLM | 5-dimensional quality scoring |
| **Protocol Miner** | Gemini Flash | Cross-reference with extraction outputs |

---

## 3. Design Philosophy

### 3.1 Core Principles

#### Principle 1: LLM-First Semantic Analysis
**Philosophy**: Use LLMs for semantic reasoning instead of brittle regex patterns.

**Rationale**: Clinical trial protocols contain natural language with domain-specific terminology. Rule-based parsing fails on:
- Varied nomenclature ("BP" vs "Blood Pressure" vs "Vital Signs - BP")
- Implicit relationships ("As per local lab" requires context understanding)
- Conditional logic buried in footnotes

**Implementation**: Every stage that requires semantic understanding uses LLM calls with structured JSON output, validated against expected schemas.

#### Principle 2: Confidence-Based Escalation
**Philosophy**: Quantify uncertainty and escalate appropriately.

**Rationale**: Not all extractions are equal. A domain mapping with 95% confidence can be auto-applied; one with 70% confidence needs human review.

**Implementation**:
```
Confidence ≥ 0.95  →  Auto-approve
Confidence 0.70-0.95  →  Escalate to review
Confidence < 0.70  →  Flag as uncertain
```

#### Principle 3: Provenance Throughout
**Philosophy**: Every value must trace back to its source.

**Rationale**: EDC build teams need to verify extractions against source. Auditors need evidence of extraction accuracy.

**Implementation**: ProvenanceRecord tracks:
- Source page number
- Cell coordinates in table
- Transformation chain (each stage's modifications)
- Confidence at each step

#### Principle 4: Protocol-Driven Enrichment
**Philosophy**: Only use information from THIS protocol, not generic knowledge.

**Rationale**: "Hematology" panel contents vary by protocol. Generic expansion would introduce errors.

**Implementation**: Stage 2 (Activity Expansion) uses:
- Protocol's Laboratory Specifications section
- Protocol's Biospecimen Handling section
- Gemini PDF search for context verification

#### Principle 5: Human-in-the-Loop by Design
**Philosophy**: The system produces drafts; humans approve finals.

**Rationale**: Regulatory requirements demand human oversight. Zero-touch automation is neither achievable nor desirable.

**Implementation**:
- Stage 10 assembles review packages
- Stage 11 supports Draft mode (all options) and Final mode (decisions applied)
- Clear escalation paths for uncertain extractions

### 3.2 Why This Architecture?

#### Challenge: Complex Table Structures
SOA tables are notoriously complex:
- Multi-row headers with merged cells
- Footnote markers throughout
- Continuation across pages
- Nested activities within categories

**Solution**: HTML-first architecture
1. LandingAI extracts at 7x zoom for accuracy
2. Claude interprets HTML structure (not raw PDF coordinates)
3. Multi-phase interpretation handles complexity incrementally

#### Challenge: Semantic Variability
The same concept appears differently across protocols:
- "C1D1" vs "Cycle 1 Day 1" vs "Treatment Day 1"
- "ECHO" vs "Echocardiogram" vs "LVEF Assessment"

**Solution**: LLM-based categorization with confidence scoring
- Stage 1 maps to standardized CDISC domains
- Batch processing enables cross-activity context
- Low-confidence mappings escalated for review

#### Challenge: Context-Dependent Expansion
"Laboratory Assessments" means different things in different trials:
- Oncology: May include tumor markers
- Cardiology: May include cardiac enzymes
- Phase 1: May include extensive safety panels

**Solution**: Protocol-aware expansion
- Stage 2 searches the specific protocol's PDF via Gemini Files API
- Uses extraction outputs from main pipeline
- Confidence threshold (≥0.85) prevents hallucination

---

## 4. Multi-Phase Extraction Pipeline

### 4.1 Phase Overview

The SOA extraction pipeline consists of 5 sequential phases:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         5-PHASE EXTRACTION PIPELINE                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  PHASE 1         PHASE 2         PHASE 3           PHASE 4         PHASE 5     │
│  ─────────       ─────────       ─────────────     ─────────       ─────────   │
│  Detection       Extraction      Interpretation    Validation      Output       │
│  (Gemini)        (LandingAI)     (Claude + 12)     (5D Quality)    (Files)     │
│                                                                                  │
│  PDF → Pages     Pages → HTML    HTML → USDM       Score USDM      Save JSON   │
│                                                                                  │
│  ~5-10s          ~30-60s         ~120-300s         ~10-20s         ~2-5s       │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Phase 1: Detection (Gemini Vision)

**Purpose**: Locate SOA tables in the protocol PDF.

**Technology**: Gemini 2.5 Pro with PDF vision capability

**Output**:
```json
{
  "totalSOAs": 2,
  "soaTables": [
    {
      "id": "SOA-1",
      "pageStart": 42,
      "pageEnd": 45,
      "tableCategory": "MAIN_SOA",
      "isContinuation": false
    },
    {
      "id": "SOA-2",
      "pageStart": 78,
      "pageEnd": 79,
      "tableCategory": "PK_SOA",
      "isContinuation": false
    }
  ]
}
```

**Key Features**:
- Vision-based detection (not text pattern matching)
- Multi-page table detection with continuation tracking
- Category classification (MAIN_SOA, PK_SOA, PD_SOA, SAFETY_SOA)

### 4.3 Phase 2: Extraction (LandingAI 7x Zoom)

**Purpose**: Convert PDF pages to structured HTML tables.

**Technology**: LandingAI Table Extraction API with 7x zoom factor

**Process**:
1. Render each SOA page at 7x zoom (for accuracy)
2. Send to LandingAI for table structure recognition
3. Receive HTML with `<table>`, `<tr>`, `<td>` structure
4. Inject page markers (`<!-- Page N -->`) for provenance

**Output**: HTML string per SOA table with page boundaries preserved

**Why 7x Zoom?**:
- Clinical protocols often use small fonts (8-10pt)
- 7x zoom ensures character-level accuracy
- LandingAI performs better with larger images
- Results in ~2000x2500px images (manageable size)

### 4.4 Phase 3: Interpretation (Claude Three-Phase + 12-Stage Pipeline)

Phase 3 is the core of the system, consisting of two major components:

#### 4.4.1 Claude HTML Interpretation (Three Sub-Phases)

The Claude HTML interpreter converts extracted HTML into USDM-ready JSON using three sub-phases optimized for token efficiency:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                 CLAUDE HTML INTERPRETATION (3 SUB-PHASES)                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  SUB-PHASE 1           SUB-PHASE 2           SUB-PHASE 3                        │
│  ──────────────        ──────────────        ──────────────                     │
│  Structure Extract     Compact Matrix        SAI Expansion                       │
│  (Claude 16K)          (Claude 8K)           (Python)                           │
│                                                                                  │
│  Extracts:             Extracts:             Generates:                         │
│  • Visit definitions   • Activity→Visit      • Full SAI objects                 │
│  • Activity list         mapping matrix      • Timing linkage                   │
│  • Footnotes           • X marks/conditions  • Footnote refs                    │
│  • Protocol type                             • Provenance                       │
│                                                                                  │
│  Output: ~16K tokens   Output: ~8K tokens    Output: Deterministic             │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Sub-Phase 1: Structure Extraction**
- Input: HTML tables
- LLM: Claude Sonnet (16K token limit)
- Extracts: visits, activities, footnotes, protocol metadata
- Does NOT extract the activity-visit matrix (too large)

**Sub-Phase 2: Compact Matrix Extraction**
- Input: HTML tables
- LLM: Claude Sonnet (8K token limit)
- Extracts: Compact `{activityId: [visitIds]}` mapping
- Much smaller than full SAI objects

**Sub-Phase 3: SAI Expansion**
- Input: Sub-phase 1 + Sub-phase 2 outputs
- Processing: Pure Python (no LLM)
- Generates: Full `scheduledActivityInstances` array
- Deterministic expansion with provenance tracking

**Why Three Sub-Phases?**:
- Large SOAs can generate 500+ SAIs
- Full SAI objects would exceed LLM context limits
- Compact matrix is ~10x smaller than full SAIs
- Python expansion is deterministic and fast

#### 4.4.2 12-Stage Interpretation Pipeline

After Claude interpretation, the 12-stage pipeline enriches and validates the USDM structure. See [Section 5](#5-the-12-stage-interpretation-pipeline) for details.

### 4.5 Phase 4: Validation (5D Quality Framework)

**Purpose**: Score extraction quality across 5 dimensions.

**Dimensions**:
| Dimension | Weight | Threshold | Check |
|-----------|--------|-----------|-------|
| Accuracy | 25% | 95% | No placeholders, valid formats |
| Completeness | 20% | 90% | Required fields present |
| Compliance | 20% | 100% | JSON Schema valid |
| Provenance | 20% | 95% | Page references present |
| Terminology | 15% | 90% | CDISC codes valid |

**Quality Gate**:
- Overall ≥ 85%: PASS
- Overall < 85%: FAIL (escalate for review)

### 4.6 Phase 5: Output

**Files Generated**:
| File | Content |
|------|---------|
| `{protocol}_soa_usdm.json` | Complete USDM 4.0 output |
| `{protocol}_soa_quality.json` | Quality scores and issues |
| `{protocol}_pipeline_summary.json` | Execution metadata |
| `interpretation_stages/*.json` | Per-stage results (12 files) |
| `00_foundational_extraction.json` | Pre-enrichment USDM |

---

## 5. The 12-Stage Interpretation Pipeline

### 5.1 Pipeline Overview

The 12-stage pipeline enriches the raw USDM output from Claude interpretation with domain knowledge, protocol context, and USDM compliance validation.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      12-STAGE INTERPRETATION PIPELINE                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  SEMANTIC ENRICHMENT (Stages 1-6)                                               │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  │
│  │ Stage 1 │──│ Stage 2 │──│ Stage 3 │──│ Stage 4 │──│ Stage 5 │──│ Stage 6 │  │
│  │ Domain  │  │Activity │  │Hierarchy│  │ Altern. │  │Specimen │  │ Condit. │  │
│  │Categori.│  │Expansion│  │Building │  │ Resolut.│  │Enrichmt.│  │Expansion│  │
│  │CRITICAL │  │         │  │         │  │         │  │         │  │         │  │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘  │
│                                                                                  │
│  TEMPORAL & STRUCTURAL (Stages 7-9)                                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                                          │
│  │ Stage 7 │──│ Stage 8 │──│ Stage 9 │                                          │
│  │ Timing  │  │  Cycle  │  │Protocol │                                          │
│  │ Distrib.│  │Expansion│  │ Mining  │                                          │
│  └─────────┘  └─────────┘  └─────────┘                                          │
│                                    │                                             │
│  COMPLIANCE & OUTPUT (Stages 10-12)│                                             │
│                                    ▼                                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                                          │
│  │Stage 12 │──│Stage 11 │──│Stage 10 │                                          │
│  │  USDM   │  │Schedule │  │ Human   │                                          │
│  │Complian.│  │ Generat.│  │ Review  │                                          │
│  │CRITICAL │  │         │  │Assembly │                                          │
│  └─────────┘  └─────────┘  └─────────┘                                          │
│                                                                                  │
│  Execution Order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 12 → 11 → 10             │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Stage Execution Order

**Important**: The stages execute in this specific order:

```
[1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 11, 10]
```

**Rationale for Non-Sequential Order**:
- Stage 12 (USDM Compliance) runs before Stage 11 (Schedule Generation) to ensure Code objects are properly expanded before generating schedules
- Stage 11 (Schedule Generation) produces the draft schedule
- Stage 10 (Human Review Assembly) runs last to collect all results including the draft schedule

### 5.3 Stage Details

#### Stage 1: Domain Categorization (CRITICAL)
**Purpose**: Map each activity to its CDASH/SDTM domain.
**EDC Impact**: Determines which eCRF forms are needed.
**Technology**: LLM batch categorization with CDISC codelist lookup

| Input | Processing | Output |
|-------|------------|--------|
| Activity names | LLM batch categorization | Domain codes (VS, LB, EG, etc.) |
| | CDISC codelist lookup | Confidence scores |
| | Cache by activity name | Mapping rationale |

**Example**:
```json
{
  "activityName": "12-Lead ECG",
  "domain": "EG",
  "domainDescription": "ECG Test Results",
  "confidence": 0.95,
  "rationale": "Electrocardiogram activity maps to EG domain"
}
```

#### Stage 2: Activity Expansion (v2.0 Protocol-Driven)
**Purpose**: Decompose parent activities into measurable components.
**EDC Impact**: Defines individual data fields within forms.
**Technology**: Gemini with PDF multimodal + extraction outputs

| Input | Processing | Output |
|-------|------------|--------|
| Parent activity | Protocol PDF search (Gemini Files API) | Component activities |
| Extraction outputs | LLM expansion with context | Parent-child relationships |
| | Confidence filtering (≥0.85) | Data collection items |

**Example**:
```json
{
  "parentActivity": "Vital Signs",
  "components": [
    {"name": "Systolic Blood Pressure", "unit": "mmHg", "method": "Sitting"},
    {"name": "Diastolic Blood Pressure", "unit": "mmHg", "method": "Sitting"},
    {"name": "Heart Rate", "unit": "bpm", "method": "Pulse"},
    {"name": "Temperature", "unit": "°C", "method": "Oral"},
    {"name": "Respiratory Rate", "unit": "breaths/min"}
  ],
  "confidence": 0.92,
  "source": "Protocol Section 8.1"
}
```

#### Stage 3: Hierarchy Building
**Purpose**: Build parent-child activity trees from Stage 2 expansions.
**EDC Impact**: Structures form sections and data groupings.

#### Stage 4: Alternative Resolution
**Purpose**: Resolve "X or Y" choice points in activities.
**EDC Impact**: Determines branching logic in eCRFs.

**Example**: "CT/MRI" → Creates two mutually exclusive activities with selection logic.

#### Stage 5: Specimen Enrichment (v2.0 Protocol-Driven)
**Purpose**: Add specimen collection details to lab activities.
**EDC Impact**: Populates lab requisition forms and biospecimen tracking.
**Technology**: Uses biospecimen_handling extraction + Gemini PDF validation

| Enrichment | Source | Usage |
|------------|--------|-------|
| Tube type | Biospecimen handling module | Lab kit configuration |
| Volume | Laboratory specifications | Sample sufficiency checks |
| Processing | Protocol appendix | Lab manual generation |
| Storage | Biospecimen section | Central lab coordination |

#### Stage 6: Conditional Expansion
**Purpose**: Link activities to population/clinical conditions from footnotes.
**EDC Impact**: Configures conditional form display and edit checks.

**Example**:
```json
{
  "condition": {
    "type": "POPULATION",
    "description": "Female subjects of childbearing potential",
    "expression": "SEX == 'F' AND CBPFL == 'Y'"
  },
  "applies_to": ["Pregnancy Test", "FSH Assessment"]
}
```

#### Stage 7: Timing Distribution
**Purpose**: Expand relative timing (BI/EOI, pre/post-dose) to absolute values.
**EDC Impact**: Configures visit scheduling and windows.

| Pattern | Expansion | EDC Configuration |
|---------|-----------|-------------------|
| "Day 1" | relativeTo: cycle_start, value: 1 | Visit date = Cycle start |
| "±3 days" | window: {early: -3, late: 3} | Visit window in scheduler |
| "Pre-dose" | relativeTo: dosing, value: -0.5 | Pre-dose timepoint |
| "4h post-dose" | relativeTo: dosing, value: 4 | PK collection timepoint |
| "EOI" | End of Infusion | Post-infusion assessment |

#### Stage 8: Cycle Expansion
**Purpose**: Generate visits for repeating cycle patterns.
**EDC Impact**: Creates visit schedule with cycle-specific naming.
**Technology**: LLM batch analysis with triple fallback (Gemini → Azure → Claude)

| Pattern | Handling | Output |
|---------|----------|--------|
| "Cycles 1-3 Day 1" | Fixed expansion | 3 discrete visits |
| "Cycle 2-6 Day 1" | Explicit range | 5 discrete visits (bounded) |
| "Cycle 4 and subsequent" | Open-ended flag | Human review required |
| "Cycle 4+" | Open-ended flag | Human review required |
| "Every 3 weeks" | Interval-based | Q3W schedule |

**Critical Feature**: Open-ended patterns are NOT auto-expanded. They are flagged for human specification of maximum cycle count.

**Open-Ended Detection Logic** (v2.0 - December 2025):
The `_is_open_ended_pattern()` function uses a conservative approach to detect unbounded patterns:
- Returns `True` ONLY if BOTH `endCycle` is null AND `maxCycles` is null
- Explicit cycle ranges like "Cycle 2-6" have `endCycle=6`, so they are NOT open-ended
- Patterns like "Cycle 4+" have `endCycle=null`, so they ARE open-ended

```python
def _is_open_ended_pattern(self, pattern: str, llm_decision: Dict) -> bool:
    """Determine if pattern is genuinely open-ended (unbounded)."""
    pattern_type = llm_decision.get("patternType", "").lower()
    end_cycle = llm_decision.get("endCycle")
    max_cycles = llm_decision.get("maxCycles")

    # Conservative: Only open-ended if BOTH endCycle AND maxCycles are null
    if end_cycle is not None or max_cycles is not None:
        return False  # Has a bound - not open-ended

    # Check pattern type from LLM
    open_ended_types = {"open_ended", "open-ended", "unbounded", "continuing"}
    return pattern_type in open_ended_types
```

**LLM Fallback Chain** (v2.0 - December 2025):
Stage 8 uses a triple-fallback LLM architecture for robustness:
1. **Primary**: Gemini 2.5 Flash (default)
2. **Fallback 1**: Azure OpenAI (if Gemini fails)
3. **Fallback 2**: Anthropic Claude (if Azure fails)

Set `USE_CLAUDE_PRIMARY=true` in environment to use Claude as the primary LLM (for testing).

#### Stage 9: Protocol Mining
**Purpose**: Cross-reference activities with extraction module outputs.
**EDC Impact**: Enriches activities with detailed specifications from other protocol sections.

| Module | Enrichment |
|--------|------------|
| laboratory_specifications | Detailed panel definitions, reference ranges |
| biospecimen_handling | Processing requirements, aliquoting |
| pkpd_sampling | PK timepoints, sample volumes |
| adverse_events | Safety parameters, grading criteria |
| imaging_central_reading | Imaging modalities, assessment criteria |
| pro_specifications | PRO instruments, timing |

#### Stage 10: Human Review Assembly
**Purpose**: Package uncertain extractions for SME review (runs LAST).
**EDC Impact**: Defines review workflow before EDC build.

**Review Package Contents**:
- Low-confidence domain mappings (<0.95)
- Activity expansions requiring validation
- Open-ended cycle patterns
- Conditional logic interpretations
- Alternative resolution decisions
- Draft schedule from Stage 11

#### Stage 11: Schedule Generation
**Purpose**: Generate final schedule applying review decisions.
**EDC Impact**: Produces the definitive visit/activity matrix for EDC configuration.

**Two Modes**:
1. **Draft Mode**: All options included, marked with review status (default)
2. **Final Mode**: Human decisions applied, clean output

#### Stage 12: USDM Compliance (CRITICAL)
**Purpose**: Ensure output conforms to USDM 4.0 standard.
**EDC Impact**: Guarantees interoperability with USDM-aware tooling.

**Validations**:
- `instanceType` injection on all objects
- Code object expansion to 6-field format
- Referential integrity (all IDs resolve)
- Schedule timeline generation
- CDISC code validation

---

## 6. Data Flow & Transformation

### 6.1 End-to-End Data Flow

```
Protocol PDF
    │
    ▼ Phase 1: Detection
┌──────────────────────────────────┐
│ {                                │
│   "soaTables": [                 │
│     {"id": "SOA-1",              │
│      "pageStart": 42,            │
│      "pageEnd": 44,              │
│      "category": "MAIN_SOA"}     │
│   ]                              │
│ }                                │
└──────────────────────────────────┘
    │
    ▼ Phase 2: Extraction
┌──────────────────────────────────┐
│ {                                │
│   "id": "SOA-1",                 │
│   "html": "<table>...</table>",  │
│   "pages": [42, 43, 44]          │
│ }                                │
└──────────────────────────────────┘
    │
    ▼ Phase 3: HTML Interpretation (3-phase)
┌──────────────────────────────────┐
│ {                                │
│   "visits": [...],               │
│   "activities": [...],           │
│   "scheduledActivityInstances":  │
│     [...],                       │
│   "footnotes": [...]             │
│ }                                │
└──────────────────────────────────┘
    │
    ▼ Phase 3: 12-Stage Pipeline
┌──────────────────────────────────┐
│ Enriched USDM with:              │
│ - Domain mappings                │
│ - Expanded activities            │
│ - Activity hierarchies           │
│ - Alternative resolutions        │
│ - Specimen details               │
│ - Conditions                     │
│ - Timing/cycles                  │
│ - Protocol mining enrichments    │
│ - USDM compliance                │
│ - Draft schedule                 │
│ - Review package                 │
└──────────────────────────────────┘
    │
    ▼ Phase 4: Quality Validation
┌──────────────────────────────────┐
│ {                                │
│   "overall_score": 0.95,         │
│   "accuracy": 1.0,               │
│   "completeness": 1.0,           │
│   "compliance": 1.0,             │
│   "provenance": 1.0,             │
│   "terminology": 0.90            │
│ }                                │
└──────────────────────────────────┘
    │
    ▼ Phase 5: Output
┌──────────────────────────────────┐
│ - {protocol}_soa_usdm.json       │
│ - {protocol}_soa_quality.json    │
│ - {protocol}_pipeline_summary.json│
│ - interpretation_stages/*.json   │
│ - 00_foundational_extraction.json│
└──────────────────────────────────┘
```

### 6.2 USDM Output Structure

```json
{
  "protocolId": "NCT04656652",
  "protocolType": "cycle_based",
  "primaryReferencePoint": "randomization",

  "encounters": [
    {
      "id": "ENC-001",
      "name": "Screening",
      "type": {"code": "C48262", "decode": "Screening", ...},
      "timing": {"value": -28, "unit": "days", "relativeTo": "randomization"},
      "window": {"earlyBound": 0, "lateBound": 14},
      "provenance": {"pageNumber": 42}
    }
  ],

  "activities": [
    {
      "id": "ACT-001",
      "name": "Vital Signs",
      "definedActivity": {"domain": "VS", ...},
      "childActivities": ["ACT-001-1", "ACT-001-2", ...],
      "provenance": {"pageNumber": 42}
    }
  ],

  "scheduledActivityInstances": [
    {
      "id": "SAI-001",
      "encounterId": "ENC-001",
      "activityId": "ACT-001",
      "timing": {"relativeToEncounter": true},
      "provenance": {"pageNumber": 42}
    }
  ],

  "conditions": [
    {
      "id": "COND-001",
      "type": "POPULATION",
      "description": "Female subjects of childbearing potential",
      "structuredRule": {...}
    }
  ],

  "footnotes": [
    {
      "id": "FN-001",
      "number": "a",
      "text": "Pregnancy test required for female subjects",
      "appliesTo": ["SAI-015"]
    }
  ],

  "scheduleTimelines": [...],
  "qualityMetrics": {...}
}
```

---

## 7. Quality Framework

### 7.1 Five-Dimensional Scoring

| Dimension | Weight | Threshold | What It Measures |
|-----------|--------|-----------|------------------|
| **Accuracy** | 25% | 95% | No placeholders (TBD, TODO), valid formats, no hallucinations |
| **Completeness** | 20% | 90% | Required USDM fields present, all activities mapped |
| **Compliance** | 20% | 100% | Valid against USDM 4.0 JSON schema |
| **Provenance** | 20% | 95% | Source page reference for every extracted value |
| **Terminology** | 15% | 90% | Valid CDISC codes, correct code-decode pairs |

### 7.2 Quality Gates

```
Phase 3 Output (Interpretation)
        │
        ▼
    Compliance Check (Stage 12)
        │ FAIL → Pipeline fails
        ▼ PASS
    Quality Scoring (Phase 4)
        │
        ├── Overall ≥ 85% → PASS
        │
        └── Overall < 85% → FAIL (escalate)
```

### 7.3 Issue Detection

**Placeholder Detection** (50+ patterns):
- TBD, TODO, UNKNOWN, N/A, NULL
- [PLACEHOLDER], {TO_BE_COMPLETED}
- Question marks in values

**Referential Integrity**:
- Every `activityId` in SAI must exist in `activities`
- Every `encounterId` in SAI must exist in `encounters`
- Every `conditionId` in assignment must exist in `conditions`

**Terminology Validation**:
- Uses TerminologyMapper + CDISC codelists
- LLM fallback for unmapped terms
- Invalid codes flagged as terminology issues

---

## 8. Integration Points

### 8.1 Main Pipeline Integration

The SOA module integrates with the 17-module main extraction pipeline:

```
Main Pipeline (scripts/main.py)
├── 17 extraction modules (Wave 0, 1, 2)
├── USDM combiner
└── Output: {protocol}_usdm_4.0.json
        │
        ▼
SOA Pipeline (soa_extraction_pipeline.py)
├── --extraction-outputs flag
├── Loads domainSections from USDM
├── Stage 2: Activity expansion uses extraction outputs
├── Stage 5: Specimen enrichment uses biospecimen_handling
└── Stage 9: Protocol Mining cross-references all modules
        │
        ▼
Enriched SOA with cross-references
```

**Usage**:
```bash
python soa_analyzer/soa_extraction_pipeline.py \
    /path/to/protocol.pdf \
    --extraction-outputs /path/to/protocol_usdm_4.0.json
```

### 8.2 Module Cross-References (Stage 9)

| Extraction Module | SOA Enrichment |
|-------------------|----------------|
| laboratory_specifications | Lab panel details, reference ranges |
| biospecimen_handling | Tube types, volumes, processing |
| pkpd_sampling | PK timepoints, sampling schedule |
| adverse_events | Safety parameters, grading |
| imaging_central_reading | Imaging requirements |
| pro_specifications | PRO instruments, timing |
| endpoints_estimands_sap | Endpoint assessments |

### 8.3 External System Integration

**EDC System Integration Points**:

| Integration | Data Source | Usage |
|-------------|-------------|-------|
| Visit Scheduler | `encounters` + `scheduleTimelines` | Configure visit calendar |
| Form Builder | `activities` + domain mappings | Generate eCRF structure |
| Edit Check Engine | `conditions` + `footnotes` | Configure validation rules |
| Lab Kit Config | Stage 5 specimen enrichments | Set up collection kits |
| Randomization | `encounters` with window definitions | Visit window validation |

---

## 9. Human-in-the-Loop Design

### 9.1 Review Package Structure

Stage 10 produces a review package containing:

```json
{
  "reviewItems": [
    {
      "id": "REV-001",
      "stage": "Stage2ActivityExpansion",
      "type": "EXPANSION_VALIDATION",
      "activity": "Hematology",
      "components": [...],
      "confidence": 0.82,
      "reason": "Below auto-approval threshold",
      "suggestedAction": "Validate component list against protocol"
    },
    {
      "id": "REV-002",
      "stage": "Stage8CycleExpansion",
      "type": "OPEN_ENDED_PATTERN",
      "encounter": "Cycle 4 and Subsequent Cycles Day 1",
      "pattern": "CYCLE:4+",
      "reason": "Open-ended pattern requires max cycle specification",
      "suggestedAction": "Specify maximum cycle count"
    }
  ],
  "autoApproved": [...],
  "draftSchedule": {...},  // From Stage 11
  "statistics": {
    "totalItems": 45,
    "autoApproved": 38,
    "pendingReview": 7
  }
}
```

### 9.2 Review Workflow

```
┌────────────────────────────────────────────────────────────────┐
│                      REVIEW WORKFLOW                            │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐    │
│  │   Draft     │      │   Human     │      │   Final     │    │
│  │  Schedule   │─────▶│   Review    │─────▶│  Schedule   │    │
│  │  (Stage 11) │      │             │      │  (Stage 11) │    │
│  └─────────────┘      └─────────────┘      └─────────────┘    │
│        │                    │                    │             │
│        ▼                    ▼                    ▼             │
│  All options         Review package       Decisions applied   │
│  included            with decisions       Clean output        │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### 9.3 Confidence Thresholds

| Threshold | Action | Example |
|-----------|--------|---------|
| ≥ 0.95 | Auto-approve | Clear domain mapping: "Vital Signs" → VS |
| 0.85 - 0.95 | Light review | Component expansion with good context |
| 0.70 - 0.85 | Full review | Ambiguous activity categorization |
| < 0.70 | Flag uncertain | No clear mapping found |

---

## 10. EDC Build Automation Mapping

### 10.1 SOA Output to EDC Configuration

| SOA Output | EDC Configuration | Automation Level |
|------------|-------------------|------------------|
| `encounters` | Visit definitions | Full |
| `encounters.timing` | Visit scheduling rules | Full |
| `encounters.window` | Visit window configuration | Full |
| `activities` | Form/eCRF definitions | Partial (needs field mapping) |
| `activities.domain` | CDASH domain assignment | Full |
| `scheduledActivityInstances` | Visit-form matrix | Full |
| `conditions` | Conditional display rules | Partial (needs rule translation) |
| `footnotes` | Edit check source | Partial (needs rule extraction) |
| Stage 5 specimens | Lab kit configuration | Full |
| Stage 9 enrichments | Cross-reference data | Reference |

### 10.2 Automation Coverage

```
┌─────────────────────────────────────────────────────────────────┐
│                    EDC BUILD AUTOMATION                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  FULLY AUTOMATED (80%)                                          │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ • Visit schedule structure                                  │ │
│  │ • Visit windows and timing                                  │ │
│  │ • Activity-to-visit matrix                                  │ │
│  │ • Domain categorization                                     │ │
│  │ • Specimen requirements                                     │ │
│  │ • Cycle-based visit generation                              │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  HUMAN-ASSISTED (15%)                                           │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ • Activity expansion validation                             │ │
│  │ • Open-ended pattern specification                          │ │
│  │ • Complex conditional logic                                 │ │
│  │ • Alternative resolution decisions                          │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  MANUAL CONFIGURATION (5%)                                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ • Custom edit checks                                        │ │
│  │ • Protocol-specific business rules                          │ │
│  │ • Integration with external systems                         │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 11. Technical Implementation

### 11.1 File Organization

```
soa_analyzer/
├── soa_extraction_pipeline.py    # Main 5-phase orchestrator
├── soa_html_interpreter.py       # Claude 3-phase HTML → USDM
├── soa_page_detector.py          # Gemini Vision detection
├── soa_quality_checker.py        # 5D quality scoring
├── soa_llm_terminology_mapper.py # CDISC term mapping
├── soa_cache.py                  # Version-aware caching
│
├── interpretation/               # 12-stage pipeline
│   ├── __init__.py              # Exports InterpretationPipeline
│   ├── interpretation_pipeline.py # Stage orchestrator
│   ├── context_assembler.py     # Context builder for stages
│   ├── stage1_domain_categorization.py
│   ├── stage2_activity_expansion.py
│   ├── stage3_hierarchy_builder.py
│   ├── stage4_alternative_resolution.py
│   ├── stage5_specimen_enrichment.py
│   ├── stage6_conditional_expansion.py
│   ├── stage7_timing_distribution.py
│   ├── stage8_cycle_expansion.py
│   ├── stage9_protocol_mining.py
│   ├── stage10_human_review.py
│   ├── stage11_schedule_generation.py
│   └── stage12_usdm_compliance.py
│
├── models/                       # Data structures
│   ├── code_object.py           # USDM Code objects
│   ├── provenance_models.py     # Audit trail
│   ├── alternative_expansion.py  # Stage 4 models
│   ├── cycle_expansion.py       # Stage 8 models
│   ├── protocol_mining.py       # Stage 9 models
│   ├── specimen_enrichment.py   # Stage 5 models
│   └── timing_expansion.py      # Stage 7 models
│
├── prompts/                      # LLM prompts
│   ├── html_interpretation_structure.txt    # Claude P1
│   ├── html_interpretation_matrix.txt       # Claude P2
│   ├── domain_categorization.txt            # Stage 1
│   ├── activity_expansion_unified.txt       # Stage 2
│   └── ...
│
├── config/                       # Configuration
│   ├── cycle_patterns.json
│   ├── section_activity_mappings.json
│   └── ...
│
└── tests/                        # Test suite
    ├── test_stage02_abbvie.py
    ├── test_stage7_timing_distribution.py
    └── ...
```

### 11.2 Usage Examples

**Basic Extraction**:
```bash
python soa_analyzer/soa_extraction_pipeline.py /path/to/protocol.pdf
```

**With Protocol Mining**:
```bash
python soa_analyzer/soa_extraction_pipeline.py \
    /path/to/protocol.pdf \
    --extraction-outputs /path/to/protocol_usdm_4.0.json
```

**Skip Interpretation (Raw Extraction Only)**:
```bash
python soa_analyzer/soa_extraction_pipeline.py \
    /path/to/protocol.pdf \
    --no-interpretation
```

**Programmatic Usage**:
```python
from soa_analyzer import SOAExtractionPipeline, run_soa_extraction

# Option 1: Class-based
pipeline = SOAExtractionPipeline()
result = await pipeline.run(
    pdf_path="/path/to/protocol.pdf",
    extraction_outputs=main_pipeline_outputs,
)

# Option 2: Convenience function
result = await run_soa_extraction(
    pdf_path="/path/to/protocol.pdf",
    extraction_outputs=main_pipeline_outputs,
)

print(f"Success: {result.success}")
print(f"Quality: {result.quality_score.overall_score:.1%}")
print(f"Visits: {result.visits_count}")
print(f"Activities: {result.activities_count}")
print(f"Output: {result.output_dir}")
```

### 11.3 Output Files

| File | Content | Usage |
|------|---------|-------|
| `{protocol}_soa_usdm.json` | Complete USDM 4.0 output | EDC configuration input |
| `{protocol}_soa_quality.json` | Quality scores | QA validation |
| `{protocol}_pipeline_summary.json` | Execution metadata | Debugging |
| `interpretation_stages/stage01_result.json` | Domain categorization | Audit trail |
| `interpretation_stages/stage02_result.json` | Activity expansion | Audit trail |
| ... | ... | ... |
| `interpretation_stages/stage12_result.json` | USDM compliance | Audit trail |
| `00_foundational_extraction.json` | Pre-enrichment USDM | Baseline comparison |

---

## Conclusion

The SOA Analysis Module represents a paradigm shift in clinical trial protocol digitalization. By combining:

1. **Multi-phase extraction** for handling complex PDF tables
2. **LLM-powered semantic analysis** for accurate interpretation
3. **12-stage interpretation pipeline** for comprehensive enrichment
4. **Confidence-based escalation** for appropriate human oversight
5. **Complete provenance** for audit compliance
6. **USDM 4.0 compliance** for interoperability
7. **Protocol-specific enrichment** for accuracy

The system enables 80%+ automation of EDC build setup while maintaining the human oversight required for regulatory compliance. The architecture handles complex SOA table structures through the HTML-first approach, while the 12-stage interpretation pipeline provides the depth of analysis needed for clinical trial protocols.

---

*Document Version: 2.1*
*Last Updated: December 2025*
*Module Version: 4.1*

**Changelog v2.1 (December 2025):**
- Stage 8: Fixed open-ended detection logic to check both `endCycle` AND `maxCycles`
- Stage 8: Added Anthropic Claude as third LLM fallback option (Gemini → Azure → Claude)
- Stage 8: Added `USE_CLAUDE_PRIMARY` environment variable for testing Claude as primary LLM
- Stage 8: Explicit cycle ranges (e.g., "Cycle 2-6") now correctly expand instead of being flagged as open-ended
