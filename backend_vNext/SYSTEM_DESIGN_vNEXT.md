# Backend vNext System Design

## Protocol to USDM Extraction Backend - Production Architecture v4.0

**Version**: 4.0 (Process-Based Extraction + REST API)
**Last Updated**: December 2025
**Status**: Production Ready

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Five-Dimensional Quality Framework](#3-five-dimensional-quality-framework)
4. [Two-Phase Extraction Pipeline](#4-two-phase-extraction-pipeline)
5. [Post-Processing Pipeline](#5-post-processing-pipeline)
6. [CDISC Terminology Validation](#6-cdisc-terminology-validation)
7. [Provenance Architecture](#7-provenance-architecture)
8. [Schema Design](#8-schema-design)
9. [Configuration Management](#9-configuration-management)
10. [API Reference](#10-api-reference)
11. [Directory Structure](#11-directory-structure)
12. [Testing Guide](#12-testing-guide)
13. [SOA Pipeline v2 Architecture](#13-soa-pipeline-v2-architecture)
14. [SOA Interpretation Pipeline (12-Stage)](#14-soa-interpretation-pipeline-12-stage)
15. [Eligibility Analyzer Architecture](#15-eligibility-analyzer-architecture)

---

## 1. Executive Summary

### 1.1 Purpose

Transform clinical trial protocol PDFs into structured USDM 4.0 JSON with:

- **Five-dimensional quality scoring** (accuracy, completeness, compliance, provenance, terminology)
- **Automatic post-processing** for CDISC code correction and snippet truncation
- **100% provenance coverage** with explicit PDF citations
- **CDISC CT compliance** via NCI Thesaurus codes

### 1.2 Key Features (v4.0)

| Feature | Description |
|---------|-------------|
| **5D Quality Framework** | Accuracy, Completeness, Compliance, Provenance, Terminology |
| **Integrated Provenance** | Value+provenance co-located in single object |
| **Auto-Correction** | CDISC codes auto-corrected based on decode values |
| **Snippet Truncation** | Long text_snippets auto-truncated to 500 chars |
| **Quality Feedback Loop** | Failed extractions retry with detailed error feedback |
| **Configurable Thresholds** | All quality thresholds configurable in config.yaml |
| **12-Stage SOA Pipeline** | Complete interpretation pipeline with LLM-first approach |
| **LLM-Based Validation** | Component validation using semantic LLM reasoning |

### 1.3 Quality Thresholds

| Dimension | Threshold | Description |
|-----------|-----------|-------------|
| Accuracy | 95% | No placeholders, valid formats |
| Completeness | 90% | Required fields present |
| Compliance | 90% | JSON Schema valid |
| Provenance | 95% | PDF citations present |
| Terminology | 90% | CDISC CT codes valid |

---

## 2. Architecture Overview

### 2.1 High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    EXTRACTION PIPELINE FLOW                              │
└─────────────────────────────────────────────────────────────────────────┘

     ┌───────────┐
     │ PDF Input │
     └─────┬─────┘
           │
           ▼
┌─────────────────────┐     ┌─────────────────────┐
│  Gemini File API    │────▶│  Pass 1: Values     │
│  (Upload + Cache)   │     │  (No Provenance)    │
└─────────────────────┘     └──────────┬──────────┘
                                       │
                            ┌──────────▼──────────┐
                            │  Quality Check      │
                            │  (Accuracy +        │
                            │   Completeness +    │
                            │   Compliance)       │
                            └──────────┬──────────┘
                                       │ Retry if < threshold
                                       ▼
                            ┌─────────────────────┐
                            │  Pass 2: Provenance │
                            │  (Citations Only)   │
                            └──────────┬──────────┘
                                       │
                            ┌──────────▼──────────┐
                            │  Quality Check      │
                            │  (All 5 Dimensions) │
                            └──────────┬──────────┘
                                       │ Retry if < threshold
                                       ▼
                            ┌─────────────────────┐
                            │  Post-Processing    │
                            │  - Truncate snippets│
                            │  - Auto-correct     │
                            │    CDISC codes      │
                            └──────────┬──────────┘
                                       │
                            ┌──────────▼──────────┐
                            │  Final Quality      │
                            │  Evaluation         │
                            └──────────┬──────────┘
                                       │
                                       ▼
                            ┌─────────────────────┐
                            │  USDM 4.0 JSON      │
                            │  + Quality Report   │
                            └─────────────────────┘
```

### 2.2 Technology Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI (Python 3.10+) |
| Task Queue | Celery 5.x + Redis |
| Database | PostgreSQL (NeonDB) |
| LLM Provider | Google Gemini 2.5 Flash |
| Validation | JSON Schema, Pydantic |
| CDISC CT | NCI EVS Protocol Terminology |

---

## 3. Five-Dimensional Quality Framework

### 3.1 Overview

The quality framework evaluates extraction output across five orthogonal dimensions. Each dimension is independently measurable and has a clear, defensible definition.

**Overall Score Formula:**
```
Overall = (Accuracy × 0.25) + (Completeness × 0.20) + (Compliance × 0.20)
        + (Provenance × 0.20) + (Terminology × 0.15)
```

**Default Thresholds (all must be met):**

| Dimension | Weight | Threshold | One-Liner Definition |
|-----------|--------|-----------|---------------------|
| Accuracy | 25% | 95% | Is it real data or placeholder garbage? |
| Completeness | 20% | 90% | Did we extract everything we were supposed to? |
| Compliance | 20% | 100% | Does it match the expected data structure? |
| Provenance | 20% | 95% | Can we trace every value back to the source? |
| Terminology | 15% | 90% | Are the codes valid per CDISC standards? |

### 3.2 Accuracy (Weight: 25%, Threshold: 95%)

**Definition**: Measures whether extracted values are real data vs. placeholders/hallucinations.

**What It Checks:**
- **Date Format Validation**: Dates must match `YYYY-MM-DD` pattern (or partial dates)
- **Page Number Validation**: Page numbers must be positive integers (≥ 1)
- **Placeholder Detection**: Scans all string values for 23 placeholder patterns
- **Snippet Length Validation**: Text snippets must be ≥ 15 characters

**Formula:**
```
accuracy = passed_checks / total_checks
```

**Placeholder Patterns Detected:**
```python
PLACEHOLDER_PATTERNS = [
    "TBD", "TODO", "PLACEHOLDER", "N/A", "???",
    "[PLACEHOLDER]", "[TBD]", "[TODO]", "[N/A]",
    "NOT AVAILABLE", "NOT SPECIFIED", "VALUE_NOT_FOUND",
    "EXTRACTED_VALUE", "UNKNOWN", "UNSPECIFIED",
    "TO BE DETERMINED", "TO BE CONFIRMED", "PENDING",
    "<PLACEHOLDER>", "<TBD>", "STRING", "NULL", "NONE",
]
```

**Defense**: *"We're verifying the LLM didn't hallucinate or leave placeholders. If a value says 'TBD' or has an invalid date format, it's not usable data."*

### 3.3 Completeness (Weight: 20%, Threshold: 90%)

**Definition**: Measures whether all required fields defined in the JSON schema are present and non-empty.

**What It Checks:**
- Loads module's JSON Schema and identifies all fields in the `"required"` array
- For each required field, checks if the value exists and is non-empty:
  - Value is NOT `null`
  - Value is NOT empty string `""`
  - Value is NOT empty array `[]`

**Formula:**
```
completeness = fields_present / required_fields_count
```

**Issues Recorded:**
- `missing_required_field` - Required field present in schema but missing/empty in data

**Defense**: *"We're measuring extraction coverage against a predefined schema. If the schema says 'studyPhase' is required and it's missing, that's incomplete."*

### 3.4 Compliance (Weight: 20%, Threshold: 100%)

**Definition**: Measures whether the output structure is valid JSON that conforms to the USDM 4.0 schema.

**What It Checks:**
- Full JSON Schema validation using `jsonschema` library
- Type validation (string, number, array, object)
- Enum validation (allowed values)
- Pattern validation (regex patterns)
- Required properties validation

**Formula:**
```
if schema_valid:
    compliance = 1.0
else:
    compliance = max(0.0, 1.0 - (min(error_count, 10) × 0.1))
```

**Examples:**
- 0 errors: 1.0 (100%)
- 1 error: 0.9 (90%)
- 5 errors: 0.5 (50%)
- 10+ errors: 0.0 (0%)

**Defense**: *"This is objective - either the JSON validates against the schema or it doesn't. We use standard JSON Schema validation (Draft 2020-12)."*

### 3.5 Provenance (Weight: 20%, Threshold: 95%)

**Definition**: Measures whether extracted values have source citations (page number + text snippet from the PDF).

**What It Checks:**
- Each extracted value must have a `provenance` object
- Provenance must contain:
  - `page_number`: Integer ≥ 1 (physical page in PDF)
  - `text_snippet`: String ≥ 15 characters (exact quote from PDF)

**Formula:**
```
provenance = values_with_citations / total_extractable_values
```

**Supported Patterns:**
```json
// Pattern 1: Nested provenance (code objects)
{
  "studyPhase": {
    "code": "C15602",
    "decode": "Phase 3",
    "provenance": { "page_number": 1, "text_snippet": "..." }
  }
}

// Pattern 2: Integrated value+provenance (text fields)
{
  "therapeuticArea": {
    "value": "Oncology",
    "provenance": { "page_number": 53, "text_snippet": "..." }
  }
}

// Pattern 3: Array with shared provenance
{
  "countries": {
    "values": ["USA", "Japan", "Germany"],
    "provenance": { "page_number": 15, "text_snippet": "..." }
  }
}
```

**Defense**: *"Every extracted value should be traceable to a specific page in the source document. This enables verification, audit, and regulatory compliance."*

### 3.6 Terminology (Weight: 15%, Threshold: 90%)

**Definition**: Measures whether coded values use valid CDISC Controlled Terminology codes.

**What It Checks:**
- Validates code/decode pairs against CDISC CT and NCI Thesaurus
- Validated domains include:
  - `studyPhase`, `studyType`, `trialPhase`, `trialType`
  - `sex` codes in studyPopulation
  - `blinding`, `interventionModel`, `interventionType`
  - `armType`, `endpointLevel`, `objectiveLevel`
  - `populationType`, `epochType`, `route`
  - `intercurrentEventStrategy`, `summaryMeasure`

**Formula:**
```
if no_coded_fields:
    terminology = 1.0  # Nothing to validate
else:
    terminology = max(0.0, 1.0 - (invalid_codes / recognized_coded_fields))
```

**Examples:**
- 0 issues in 10 fields: 1.0 (100%)
- 1 issue in 10 fields: 0.9 (90%)
- 5 issues in 10 fields: 0.5 (50%)

**Valid Code Object Structure (USDM 4.0):**
```json
{
  "code": "C15602",
  "decode": "Phase 3",
  "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
  "codeSystemVersion": "24.12",
  "instanceType": "Code"
}
```

**Defense**: *"CDISC CT is the regulatory standard for clinical trials. If we say studyPhase is 'C15602', that code must actually mean 'Phase 3' per NCI Thesaurus."*

### 3.7 Quality Score Data Model

```python
@dataclass
class QualityScore:
    """Quality assessment scores for extraction output."""

    # Dimension scores (0.0 to 1.0)
    accuracy: float      # No placeholders, valid formats
    completeness: float  # Required fields present
    compliance: float    # JSON Schema valid
    provenance: float    # PDF citations present
    terminology: float   # CDISC CT codes valid

    # Issue lists for feedback
    accuracy_issues: List[Dict]      # Path + issue type
    completeness_issues: List[Dict]  # Missing field names
    compliance_issues: List[Dict]    # Schema validation errors
    provenance_issues: List[Dict]    # Fields missing citations
    terminology_issues: List[Dict]   # Invalid code/decode pairs

    @property
    def overall_score(self) -> float:
        """Weighted average of all dimensions."""
        return (
            self.accuracy * 0.25 +
            self.completeness * 0.20 +
            self.compliance * 0.20 +
            self.provenance * 0.20 +
            self.terminology * 0.15
        )

    def passes_thresholds(self, thresholds: Dict) -> bool:
        """Check if all dimensions meet their thresholds."""
        return (
            self.accuracy >= thresholds.get("accuracy", 0.95) and
            self.completeness >= thresholds.get("completeness", 0.90) and
            self.compliance >= thresholds.get("compliance", 1.0) and
            self.provenance >= thresholds.get("provenance", 0.95) and
            self.terminology >= thresholds.get("terminology", 0.90)
        )
```

### 3.8 Key Implementation Notes

1. **Compliance is STRICTEST**: Default threshold is 100% - any schema error causes failure
2. **Accuracy focuses on patterns**: Date formats, page numbers, placeholder detection, snippet length
3. **Completeness is binary per field**: Either a required field is present or it's not
4. **Provenance is proportional**: Score based on percentage of values with citations
5. **Terminology only counts recognized fields**: Unknown code types are ignored (no penalty)
6. **Post-processing happens before final scoring**: Snippets are auto-truncated, codes are auto-corrected

---

## 4. Two-Phase Extraction Pipeline

### 4.1 Pass 1: Value Extraction

**Goal**: Extract all values without provenance

```python
async def run_pass1(self, gemini_file_uri: str, module_id: str) -> Dict:
    """Extract values only, no provenance."""

    prompt = self.prompt_manager.get_pass1_prompt(module_id)

    for attempt in range(MAX_RETRIES):
        response = await self.gemini_service.generate(
            gemini_file_uri,
            prompt,
            response_mime_type="application/json"
        )

        data = json.loads(response.text)
        quality = self.quality_checker.evaluate_pass1(data, module_id)

        if quality.passes_thresholds(PASS1_THRESHOLDS):
            return data

        # Add feedback for retry
        prompt = self._add_feedback(prompt, quality)

    return data  # Best effort
```

### 4.2 Pass 2: Provenance Extraction

**Goal**: Find PDF citations for all Pass 1 values

```python
async def run_pass2(self, gemini_file_uri: str, pass1_data: Dict, module_id: str) -> Dict:
    """Add provenance to Pass 1 data."""

    prompt = self.prompt_manager.get_pass2_prompt(module_id, pass1_data)

    for attempt in range(MAX_RETRIES):
        response = await self.gemini_service.generate(
            gemini_file_uri,
            prompt,
            response_mime_type="application/json"
        )

        merged_data = self._merge_provenance(pass1_data, json.loads(response.text))
        quality = self.quality_checker.evaluate(merged_data, module_id)

        if quality.passes_thresholds(FULL_THRESHOLDS):
            return merged_data

        prompt = self._add_feedback(prompt, quality)

    return merged_data
```

### 4.3 Quality Feedback Loop

When extraction fails quality thresholds, detailed feedback is provided:

```python
def generate_feedback_prompt(self, quality: QualityScore, thresholds: Dict) -> str:
    """Generate feedback for LLM retry."""

    lines = ["## QUALITY FEEDBACK - CORRECTIONS REQUIRED"]

    if quality.accuracy_issues:
        lines.append("### Accuracy Issues:")
        for issue in quality.accuracy_issues[:10]:
            lines.append(f"- `{issue['path']}`: {issue['issue']}")

    if quality.compliance_issues:
        lines.append("### Schema Compliance Errors:")
        for issue in quality.compliance_issues[:10]:
            lines.append(f"- `{issue['path']}`: {issue['message']}")

    if quality.terminology_issues:
        lines.append("### CDISC Terminology Issues:")
        for issue in quality.terminology_issues[:10]:
            lines.append(f"- `{issue['path']}`: {issue['error']}")

    return "\n".join(lines)
```

---

## 5. Post-Processing Pipeline

### 5.1 Overview

Post-processing automatically fixes common issues before final quality evaluation:

```python
def post_process(self, data: Dict, module_id: str) -> Dict:
    """Post-process extraction data to fix common issues."""

    data = copy.deepcopy(data)

    # 1. Truncate long snippets to schema max (500 chars)
    self._truncate_snippets(data)

    # 2. Auto-correct CDISC codes based on decode values
    self._auto_correct_terminology(data, module_id)

    return data
```

### 5.2 Snippet Truncation

Long text_snippets are truncated intelligently:

```python
def _truncate_snippets(self, data: Any, path: str = "$") -> None:
    """Truncate text_snippet fields to schema max length (500 chars)."""

    if isinstance(data, dict):
        for key, value in data.items():
            if key == "text_snippet" and isinstance(value, str):
                if len(value) > MAX_SNIPPET_LENGTH:
                    # Try to truncate at sentence boundary
                    truncated = value[:MAX_SNIPPET_LENGTH]
                    last_period = truncated.rfind('. ')

                    if last_period > MAX_SNIPPET_LENGTH * 0.6:
                        data[key] = truncated[:last_period + 1].strip()
                    else:
                        # Truncate at word boundary
                        last_space = truncated.rfind(' ')
                        data[key] = truncated[:last_space].strip()
```

### 5.3 CDISC Code Auto-Correction

Wrong NCI codes are auto-corrected based on decode values:

```python
def _auto_correct_terminology(self, data: Any, module_id: str, path: str = "$") -> None:
    """Auto-correct CDISC codes based on decode values."""

    if isinstance(data, dict):
        if "code" in data and "decode" in data:
            code = data.get("code")
            decode = data.get("decode")

            domain = self._infer_domain_from_path(path)
            if domain:
                is_valid, error = self.terminology_validator.validate_code_decode_pair(
                    code, decode, domain
                )
                if not is_valid:
                    correct_code = self.terminology_validator.get_code_for_decode(decode, domain)
                    if correct_code:
                        logger.info(f"Auto-correcting code: '{code}' -> '{correct_code}' for decode '{decode}'")
                        data["code"] = correct_code
```

**Example**: If LLM outputs `{"code": "C49686", "decode": "Phase 3"}`, but C49686 is "Phase 2A", the system auto-corrects to `{"code": "C15602", "decode": "Phase 3"}`.

---

## 6. CDISC Terminology Validation

### 6.1 Validation Sources

1. **Official NCI EVS Protocol Terminology** (`config/cdisc_protocol_terminology.txt`)
2. **Curated Vocabulary** (`config/cdisc_vocab.yaml`)

### 6.2 Supported Domains

| Domain | Example Codes |
|--------|---------------|
| study_phase | C15600 (Phase 1), C15601 (Phase 2), C15602 (Phase 3) |
| study_type | C98388 (Interventional), C142615 (Observational) |
| sex | C20197 (Male), C16576 (Female) |
| blinding | C49659 (Open Label), C15228 (Double Blind) |
| arm_types | C174266 (Experimental), C174267 (Active Comparator) |
| endpoint_level | C98747 (Primary), C98748 (Secondary) |
| population_type | C71104 (ITT), C70927 (Per-Protocol) |

### 6.3 Validation Methods

```python
class CDISCTerminologyValidator:

    def validate_code(self, code: str, domain: str) -> Tuple[bool, Optional[str]]:
        """Validate if NCI code is valid for domain."""

    def validate_decode(self, decode: str, domain: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Validate decode value and return canonical form."""

    def validate_code_decode_pair(self, code: str, decode: str, domain: str) -> Tuple[bool, Optional[str]]:
        """Validate code/decode pair consistency."""

    def get_code_for_decode(self, decode: str, domain: str) -> Optional[str]:
        """Find correct NCI code for a decode value."""
```

---

## 7. Provenance Architecture

### 7.1 Provenance Schema

```typescript
interface Provenance {
  section_number: string | null;  // "8.4.1" or null for cover pages
  page_number: number;            // 1-indexed physical page
  text_snippet: string;           // 15-500 chars, exact quote
  char_start?: number;            // Optional character offset
  char_end?: number;
  verification_status?: "verified" | "unverified" | "pending";
  confidence_score?: number;      // 0-100
}
```

### 7.2 Provenance Patterns

**Pattern 1: Nested Provenance** (for code objects)

Provenance inside complex objects with multiple fields:
```json
{
  "studyPhase": {
    "code": "C15602",
    "decode": "Phase 3",
    "codeSystem": "NCI Thesaurus",
    "provenance": {
      "page_number": 1,
      "text_snippet": "A Phase 3, Open-label, Randomized Study..."
    }
  }
}
```

**Pattern 2: Integrated Value+Provenance** (v3.1 - for text fields)

Value and provenance co-located in a single object - makes relationship explicit:
```json
{
  "therapeuticArea": {
    "value": "Oncology",
    "provenance": {
      "section_number": "2.1.1",
      "page_number": 53,
      "text_snippet": "Lung cancer is the most common cancer and the leading cause..."
    }
  },
  "indication": {
    "value": "Advanced or Metastatic Non-Small Cell Lung Cancer",
    "provenance": {
      "section_number": "2.1.1",
      "page_number": 53,
      "text_snippet": "patients with metastatic NSCLC are now surviving longer."
    }
  },
  "sponsorName": {
    "value": "Daiichi Sankyo, Inc.",
    "provenance": {
      "section_number": null,
      "page_number": 1,
      "text_snippet": "DAIICHI SANKYO, INC. 211 MOUNT AIRY ROAD..."
    }
  }
}
```

**Pattern 3: Integrated Array+Provenance** (v3.1 - for text arrays)

Array values with shared container provenance:
```json
{
  "keyInclusionSummary": {
    "values": [
      "Pathologically documented Stage IIIB, IIIC, or Stage IV NSCLC",
      "Documentation of radiographic disease progression",
      "ECOG performance status of 0 or 1 at Screening"
    ],
    "provenance": {
      "section_number": "5.1",
      "page_number": 73,
      "text_snippet": "Subjects must meet all of the following criteria..."
    }
  },
  "countries": {
    "values": ["USA", "Japan", "Argentina", "Czech Republic", "Australia"],
    "provenance": {
      "section_number": "1.1",
      "page_number": 15,
      "text_snippet": "Global study conducted at approximately 190 study sites..."
    }
  }
}
```

### 7.3 Array Item Provenance (for code arrays)

Each dict item in code arrays must have its own provenance:

```json
{
  "sex": {
    "allowed": [
      {
        "code": "C20197",
        "decode": "Male",
        "provenance": {
          "page_number": 77,
          "text_snippet": "If male, the subject must be surgically sterile..."
        }
      },
      {
        "code": "C16576",
        "decode": "Female",
        "provenance": {
          "page_number": 77,
          "text_snippet": "If the subject is a female of childbearing potential..."
        }
      }
    ]
  }
}
```

### 7.4 Benefits of Integrated Pattern (v3.1)

| Benefit | Description |
|---------|-------------|
| **Explicit Relationship** | Value and provenance are co-located - no naming convention needed |
| **Self-Documenting** | Downstream apps don't need logic to match `field` with `fieldProvenance` |
| **Type-Safe** | Schema enforces `{value, provenance}` structure |
| **Consistent** | Same pattern for scalars (`value`) and arrays (`values`) |

---

## 8. Schema Design

### 8.1 Integrated Provenance Types (v3.1)

Schema defines reusable types for integrated value+provenance:

**textWithProvenance** - for scalar text fields:
```json
{
  "textWithProvenance": {
    "type": "object",
    "properties": {
      "value": { "type": "string" },
      "provenance": { "$ref": "#/$defs/provenance" }
    },
    "required": ["value", "provenance"]
  }
}
```

**textArrayWithProvenance** - for text arrays:
```json
{
  "textArrayWithProvenance": {
    "type": "object",
    "properties": {
      "values": {
        "type": "array",
        "items": { "type": "string" }
      },
      "provenance": { "$ref": "#/$defs/provenance" }
    },
    "required": ["values", "provenance"]
  }
}
```

### 8.2 Fields Using Integrated Pattern

**Root-level text fields** (using `textWithProvenance`):
- `therapeuticArea` → `{value: "Oncology", provenance: {...}}`
- `indication` → `{value: "NSCLC", provenance: {...}}`
- `sponsorName` → `{value: "Daiichi Sankyo", provenance: {...}}`

**Text array fields** (using `textArrayWithProvenance`):
- `studyPopulation.keyInclusionSummary` → `{values: [...], provenance: {...}}`
- `studyPopulation.keyExclusionSummary` → `{values: [...], provenance: {...}}`
- `studyDesignInfo.countries` → `{values: [...], provenance: {...}}`

### 8.3 Schema Files

| Module | Schema File |
|--------|-------------|
| Study Metadata | `schemas/study_metadata_schema.json` |
| Safety Management | `schemas/safety_management_schema.json` |
| Arms Design | `schemas/arms_design_schema.json` |
| Endpoints/Estimands | `schemas/endpoints_estimands_sap_schema.json` |
| Quality Management | `schemas/quality_management_schema.json` |

---

## 9. Configuration Management

### 9.1 Quality Thresholds

```python
# app/config.py

DEFAULT_QUALITY_THRESHOLDS = {
    "accuracy": 0.95,       # 95% minimum accuracy
    "completeness": 0.90,   # 90% required fields present
    "compliance": 0.90,     # 90% schema compliance
    "provenance": 0.95,     # 95% provenance coverage
}

class Settings(BaseSettings):
    # Quality thresholds (configurable)
    quality_accuracy_threshold: float = Field(default=0.95)
    quality_completeness_threshold: float = Field(default=0.90)
    quality_compliance_threshold: float = Field(default=0.90)
    quality_provenance_threshold: float = Field(default=0.95)

    # Extraction settings
    max_retries: int = Field(default=3)
    gemini_model: str = Field(default="gemini-2.5-flash-preview-05-20")
    gemini_max_output_tokens: int = Field(default=65536)
```

### 9.2 Environment Variables

```bash
# .env file
DATABASE_URL=postgresql://...
GEMINI_API_KEY=...
REDIS_URL=redis://localhost:6379/0

# Optional Azure OpenAI
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_DEPLOYMENT=...
```

---

## 10. API Reference

### 10.1 Base URL

```
http://localhost:8080/api/v1
```

### 10.2 Protocol Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/protocols/upload` | Upload protocol PDF |
| GET | `/protocols/{id}` | Get protocol details |
| POST | `/protocols/{id}/extract` | Start extraction job (process-based) |
| GET | `/protocols/{id}/jobs` | List all jobs for a protocol |

### 10.3 Job Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/jobs/{id}` | Get job status with module progress |
| GET | `/jobs/{id}/results` | Get all module results |
| GET | `/jobs/{id}/results/{module}` | Get specific module result |
| PUT | `/jobs/{id}/results/{module}` | Update module result (user edits) |
| GET | `/jobs/{id}/results/{module}/edits` | Get audit trail for module |
| GET | `/jobs/{id}/events` | SSE stream for real-time progress |
| GET | `/jobs/{id}/summary` | Get extraction statistics |
| DELETE | `/jobs/{id}` | Cancel running job |

### 10.4 Process-Based Extraction Architecture

Extraction runs in a **separate OS process** to keep the API responsive during long-running LLM extractions (30+ minutes):

```
API Process                    Extraction Process
───────────                    ──────────────────
1. POST /protocols/{id}/extract
2. Create job record
3. spawn_extraction() ──────► 4. Worker process starts
4. Return immediately          5. Run extraction modules
5. Handle other requests       6. Update DB directly
                               7. Exit when complete
```

Key design decisions:
- Uses `multiprocessing.Process` for OS-level isolation
- Worker connects to its own database session
- No shared state (communicates via database)
- Fire-and-forget pattern - poll `/jobs/{id}` for status

### 10.5 SSE Event Types

```json
{
  "event_type": "module_started|module_completed|module_failed|job_finished",
  "module_id": "study_metadata",
  "payload": {...},
  "timestamp": "2024-12-06T10:30:00Z"
}
```

### 10.6 Quality Report Response

```json
{
  "quality_scores": {
    "accuracy": 0.973,
    "completeness": 1.0,
    "compliance": 1.0,
    "provenance": 0.95,
    "terminology": 1.0,
    "overall_score": 0.975
  },
  "thresholds": {
    "accuracy": 0.95,
    "completeness": 0.90,
    "compliance": 0.90,
    "provenance": 0.95
  },
  "passed": true,
  "accuracy_issues": [],
  "compliance_issues": [],
  "provenance_issues": [],
  "terminology_issues": []
}
```

---

## 11. Directory Structure

```
backend_vNext/
├── app/
│   ├── __init__.py
│   ├── main.py                         # FastAPI entry point
│   ├── celery_app.py                   # Celery configuration (optional)
│   ├── config.py                       # Settings (quality thresholds)
│   ├── db.py                           # SQLAlchemy models
│   ├── module_registry.py              # 16 module configurations
│   │
│   ├── routers/
│   │   ├── auth.py                     # Authentication (optional)
│   │   ├── protocol.py                 # PDF upload, extraction trigger
│   │   └── jobs.py                     # Job status, results, SSE
│   │
│   ├── services/
│   │   ├── extraction_worker.py        # Process-based extraction
│   │   ├── gemini_file_service.py      # Gemini File API
│   │   ├── two_phase_extractor.py      # Core extraction
│   │   ├── sequential_orchestrator.py  # Module orchestration
│   │   ├── parallel_orchestrator.py    # Parallel extraction (optional)
│   │   ├── usdm_combiner.py            # USDM 4.0 output builder
│   │   └── checkpoint_service.py       # Resumption support
│   │
│   ├── tasks/
│   │   └── extraction_tasks.py         # Celery tasks (optional)
│   │
│   └── utils/
│       ├── quality_checker.py          # 5D quality framework
│       ├── provenance_compliance.py    # Provenance validation
│       ├── schema_validator.py         # JSON Schema validation
│       ├── cdisc_validator.py          # CDISC CT validation
│       ├── cdisc_normalizer.py         # CDISC normalization
│       ├── cdisc_ct_parser.py          # NCI EVS parser
│       └── extraction_cache.py         # Version-aware caching
│
├── soa_analyzer/                       # SOA Extraction Module
│   ├── soa_extraction_pipeline.py      # Main pipeline (full end-to-end)
│   ├── soa_html_interpreter.py         # Claude-based HTML interpretation
│   ├── soa_page_detector.py            # Vision-based SOA detection
│   ├── soa_quality_checker.py          # 5D quality framework
│   ├── soa_terminology_mapper.py       # Deterministic CDISC mapping
│   ├── soa_llm_terminology_mapper.py   # LLM-based CDISC fallback
│   ├── soa_cache.py                    # Stage-level caching
│   ├── interpretation/                 # 12-stage interpretation pipeline
│   │   ├── interpretation_pipeline.py  # Pipeline orchestrator
│   │   ├── context_assembler.py        # Assembles protocol context for LLM
│   │   ├── component_validator.py      # LLM-based component validation
│   │   ├── cdisc_code_enricher.py      # CDISC code enrichment
│   │   ├── stage1_domain_categorization.py
│   │   ├── stage2_activity_expansion.py
│   │   ├── stage3_hierarchy_builder.py
│   │   ├── stage4_alternative_resolution.py
│   │   ├── stage5_specimen_enrichment.py
│   │   ├── stage6_conditional_expansion.py
│   │   ├── stage7_timing_distribution.py
│   │   ├── stage8_cycle_expansion.py
│   │   ├── stage9_protocol_mining.py
│   │   ├── stage10_human_review.py
│   │   ├── stage11_schedule_generation.py
│   │   └── stage12_usdm_compliance.py
│   ├── models/                         # Data models
│   ├── config/                         # CDISC codes, patterns
│   ├── prompts/                        # LLM prompts for interpretation
│   └── tests/                          # Test suite
│
├── eligibility_analyzer/               # Eligibility Extraction Module
│   ├── eligibility_criteria_pipeline.py
│   ├── disease_config_loader.py
│   ├── modules/
│   └── prompts/
│
├── config/
│   ├── cdisc_codelists.json            # Centralized code-decode pairs
│   ├── cdisc_concepts.json             # CDISC concepts
│   ├── cdisc_vocab.yaml                # Curated vocabulary (fallback)
│   └── cdisc_protocol_terminology.txt  # Official NCI EVS CT
│
├── schemas/                            # JSON Schemas (16)
│   ├── study_metadata_schema.json
│   ├── arms_design_schema.json
│   ├── endpoints_estimands_sap_schema.json
│   └── ...
│
├── prompts/                            # LLM prompts (Pass 1 + Pass 2)
│   ├── study_metadata_pass1_values.txt
│   ├── study_metadata_pass2_provenance.txt
│   └── ...
│
├── scripts/
│   └── main.py                         # CLI extraction entry
│
├── config.yaml                         # Module enabled/disabled config
├── requirements.txt
├── run.py                              # uvicorn launcher
├── init_schema.py                      # Database initialization
├── README.md                           # Project overview
├── CLAUDE.md                           # Claude Code instructions
└── SYSTEM_DESIGN_vNEXT.md              # This document
```

---

## 12. Testing Guide

### 12.1 Run Extraction Test

```bash
# Activate virtual environment
source venv/bin/activate

# Run study metadata extraction
python scripts/test_study_metadata_extraction.py \
    --pdf /path/to/protocol.pdf \
    --output /path/to/output/
```

### 12.2 Expected Output

```
============================================================
Starting Study Metadata Extraction
PDF: NCT04656652_Protocol_SAP.pdf
Output: /path/to/extraction_output
============================================================

[1/5] Uploading PDF to Gemini File API...
Upload completed in 3.32s

[2/5] Running two-phase extraction with quality feedback...

[3/5] Extraction completed in 180.00s

[4/5] Post-processing extraction result...
  - Truncated long snippets
  - Auto-corrected CDISC codes

[5/5] Quality re-evaluation after post-processing:

============================================================
QUALITY SCORES (after post-processing)
============================================================
  Accuracy:     97.3%
  Completeness: 100.0%
  Compliance:   100.0%
  Provenance:   95.0%
  Terminology:  100.0%
  --------------------
  Overall:      98.5%

  Passes thresholds: YES
```

---

## 13. SOA Extraction Pipeline Architecture

### 13.1 Overview

The Schedule of Assessments (SOA) pipeline extracts clinical trial visit schedules from PDF protocols into USDM 4.0 compliant JSON. Located in `soa_analyzer/`.

**Key Characteristics:**
- HTML-first extraction (more accurate than direct PDF parsing)
- Full 12-stage interpretation pipeline integrated
- Complete USDM 4.0 field preservation
- Two-tier terminology resolution (deterministic + LLM fallback)
- Stage-level caching for performance

**Entry Point:** `soa_analyzer/soa_extraction_pipeline.py`

**Usage:**
```python
from soa_analyzer import SOAExtractionPipeline, run_soa_extraction

# Option 1: Class-based
pipeline = SOAExtractionPipeline()
result = await pipeline.run("/path/to/protocol.pdf")

# Option 2: Convenience function
result = await run_soa_extraction("/path/to/protocol.pdf")

# CLI
python soa_analyzer/soa_extraction_pipeline.py /path/to/protocol.pdf
```

### 13.2 Pipeline Phases

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SOA EXTRACTION PIPELINE FLOW                          │
└─────────────────────────────────────────────────────────────────────────┘

     ┌───────────┐
     │ PDF Input │
     └─────┬─────┘
           │
           ▼
┌─────────────────────┐
│  Phase 1: Detection │  Gemini Vision finds SOA pages
│  (Cached)           │  Output: page numbers [61, 62, 63]
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Phase 2: Extraction│  LandingAI @ 7x zoom
│  (Cached)           │  Output: HTML tables
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Phase 3: Interpret │  Two sub-phases:
│                     │  3a. Claude HTML → raw USDM
│                     │  3b. 12-stage interpretation pipeline
│                     │      - Domain Categorization
│                     │      - Activity Expansion
│                     │      - Hierarchy Building
│                     │      - Alternative Resolution
│                     │      - Specimen Enrichment
│                     │      - Conditional Expansion
│                     │      - Timing Distribution
│                     │      - Cycle Expansion
│                     │      - Protocol Mining
│                     │      - Human Review Assembly
│                     │      - USDM Compliance
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Phase 4: Validate  │  5D Quality framework
│                     │  + LLM terminology fallback
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Phase 5: Output    │  Timestamped folder
│                     │  {pdf_dir}/soa_output/{YYYYMMDD_HHMMSS}/
└─────────────────────┘
```

### 13.3 Stage 1: Detection Implementation

**File:** `soa_page_detector_v2.py`

Uses Gemini Vision to identify SOA table pages in the PDF:

```python
class SOAPageDetectorV2:
    """Vision-based SOA page detection using Gemini."""

    def __init__(self, model: str = "gemini-2.5-flash"):
        self.model = genai.GenerativeModel(model)

    async def detect(self, pdf_path: str) -> List[int]:
        """Detect SOA pages using vision analysis."""
        # Convert PDF pages to images
        images = self._render_pdf_pages(pdf_path, dpi=150)

        # Batch analyze with Gemini Vision
        prompt = """Analyze this PDF page. Is it a Schedule of Assessments (SOA) table?
        SOA tables show clinical trial visits as columns and assessments/procedures as rows.
        Return JSON: {"is_soa": true/false, "confidence": 0.0-1.0}"""

        soa_pages = []
        for page_num, image in enumerate(images, 1):
            response = await self.model.generate_content_async([prompt, image])
            result = json.loads(response.text)
            if result["is_soa"] and result["confidence"] > 0.7:
                soa_pages.append(page_num)

        return soa_pages
```

**Cache Key:** `detection_v2_{protocol_id}_{pdf_hash[:16]}`

### 13.4 Stage 2: Extraction Implementation

**File:** `soa_pipeline_v2.py` (`_stage_extraction` method)

Uses LandingAI's document extraction API with 7x zoom for table accuracy:

```python
async def _stage_extraction(
    self,
    pdf_path: str,
    soa_pages: List[int],
    protocol_id: str,
) -> StageResult:
    """Extract HTML tables from SOA pages using LandingAI."""

    # Check cache first
    cache_key = f"extraction_html_v2_{protocol_id}_{self._hash_pages(soa_pages)}"
    cached = self.cache.get(cache_key)
    if cached:
        return StageResult(success=True, data=cached, cached=True)

    # Extract each page with LandingAI
    html_tables = []
    for page_num in soa_pages:
        # Render page at 7x zoom (504 DPI) for table accuracy
        image = self._render_page(pdf_path, page_num, dpi=504)

        # Call LandingAI table extraction
        result = await self.landing_ai.extract_table(image)
        html_tables.append({
            "page_number": page_num,
            "html": result["html"],
            "confidence": result["confidence"],
        })

    self.cache.set(cache_key, html_tables)
    return StageResult(success=True, data=html_tables)
```

**Cache Key:** `extraction_html_v2_{protocol_id}_{pages_hash[:16]}`

### 13.5 Stage 3: Interpretation Implementation

**File:** `soa_html_interpreter.py`

Three-phase Claude-based interpretation of HTML tables:

```python
class SOAHTMLInterpreter:
    """Two-phase HTML table interpretation using Claude."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic()
        self.model = model

    async def interpret(
        self,
        html_tables: List[Dict],
        protocol_id: str,
    ) -> Dict[str, Any]:
        """Interpret HTML tables into USDM structure."""

        # Combine HTML tables
        combined_html = "\n\n".join(
            f"<!-- Page {t['page_number']} -->\n{t['html']}"
            for t in html_tables
        )

        # Phase 1: Extract structure (visits, activities, footnotes)
        phase1_prompt = self._load_prompt("html_interpretation.txt")
        phase1_result = await self._call_claude(phase1_prompt, combined_html)

        # Phase 2: Extract activity-visit matrix with timing modifiers
        phase2_prompt = self._load_prompt("matrix_extraction.txt")
        phase2_result = await self._call_claude(
            phase2_prompt,
            combined_html,
            context=phase1_result,
        )

        # Phase 3: Expand matrix to full SAI objects
        interpretation = self._expand_to_sai_objects(
            phase1_result,
            phase2_result,
        )

        return interpretation
```

**Phase 1 Output Structure:**
```json
{
  "visits": [
    {
      "id": "ENC-001",
      "name": "Screening",
      "type": "screening",
      "timing": { "value": -28, "unit": "days" },
      "window": { "earlyBound": -28, "lateBound": 0, "description": "Up to 28 days before" },
      "footnoteMarkers": ["a"]
    }
  ],
  "activities": [
    {
      "id": "ACT-001",
      "name": "Informed Consent",
      "category": "Administrative",
      "cdashDomain": "DS"
    }
  ],
  "footnotes": [
    {
      "marker": "a",
      "text": "Must be completed before any study procedures",
      "structuredRule": { "type": "timing", "constraint": "before_procedures" }
    }
  ]
}
```

**Phase 2 Output Structure (Matrix):**
```json
{
  "activityVisitMatrix": [
    {
      "activityId": "ACT-006",
      "visitMappings": [
        {
          "visitId": "ENC-002",
          "performed": true,
          "timingModifier": "BI",
          "footnoteMarkers": ["c", "i"],
          "isRequired": true
        },
        {
          "visitId": "ENC-002",
          "performed": true,
          "timingModifier": "EOI",
          "footnoteMarkers": ["c"],
          "isRequired": true
        }
      ]
    }
  ]
}
```

**Phase 3: SAI Expansion** (`_expand_to_sai_objects`):
```python
def _expand_to_sai_objects(
    self,
    phase1: Dict,
    phase2: Dict,
) -> Dict[str, Any]:
    """Expand matrix to full ScheduledActivityInstance objects."""

    sai_list = []
    sai_counter = 1

    for activity_mapping in phase2["activityVisitMatrix"]:
        activity_id = activity_mapping["activityId"]

        for visit_mapping in activity_mapping["visitMappings"]:
            if not visit_mapping.get("performed"):
                continue

            sai = {
                "id": f"SAI-{sai_counter:03d}",
                "activityId": activity_id,
                "visitId": visit_mapping["visitId"],
                "timingModifier": visit_mapping.get("timingModifier"),
                "footnoteMarkers": visit_mapping.get("footnoteMarkers", []),
                "isRequired": visit_mapping.get("isRequired", True),
                "condition": visit_mapping.get("condition"),
                "provenance": {
                    "page_number": self._get_page_for_visit(visit_mapping["visitId"]),
                },
            }
            sai_list.append(sai)
            sai_counter += 1

    return {
        "visits": phase1["visits"],
        "activities": phase1["activities"],
        "footnotes": phase1["footnotes"],
        "scheduledActivityInstances": sai_list,
    }
```

**Prompt Files:**
- `soa_analyzer/prompts/html_interpretation.txt` - Phase 1 structure extraction
- `soa_analyzer/prompts/matrix_extraction.txt` - Phase 2 matrix extraction

### 13.6 USDM Transformation Implementation

**File:** `soa_pipeline_v2.py` (`_build_usdm` method)

Transforms interpretation output to USDM 4.0 format with full field preservation:

```python
def _build_usdm(self, interpretation: Dict[str, Any]) -> Dict[str, Any]:
    """Build USDM 4.0 compliant output from interpretation."""

    # Build schedule timeline
    timeline = {
        "id": "TIMELINE-1",
        "name": "Main Schedule",
        "mainTimeline": True,
        "instanceType": "ScheduleTimeline",
    }

    # Transform encounters (visits) with full field preservation
    encounters = []
    for visit in interpretation.get("visits", []):
        encounter = {
            "id": visit.get("id"),
            "name": visit.get("name"),
            "label": visit.get("originalName", visit.get("name")),
            "instanceType": "Encounter",
            "type": self._map_encounter_type(visit.get("type")),
            "provenance": visit.get("provenance"),
        }

        # Add footnoteMarkers if present
        if visit.get("footnoteMarkers"):
            encounter["footnoteMarkers"] = visit.get("footnoteMarkers")

        # Add timing if present
        timing = visit.get("timing")
        if timing and timing.get("value") is not None:
            encounter["scheduledAtTimingValue"] = timing.get("value")
            encounter["scheduledAtTimingUnit"] = timing.get("unit", "days")

        # Add window if present
        window = visit.get("window")
        if window:
            encounter["window"] = {
                "earlyBound": window.get("earlyBound"),
                "lateBound": window.get("lateBound"),
                "type": window.get("type", "symmetric"),
            }
            if window.get("description"):
                encounter["window"]["description"] = window.get("description")

        # Add recurrence if present
        if visit.get("recurrence"):
            encounter["recurrence"] = visit.get("recurrence")

        # Add mergedTimepoints if present
        if visit.get("mergedTimepoints"):
            encounter["mergedTimepoints"] = visit.get("mergedTimepoints")

        encounters.append(encounter)

    # Transform activities
    activities = []
    for act in interpretation.get("activities", []):
        activity = {
            "id": act.get("id"),
            "name": act.get("name"),
            "instanceType": "Activity",
            "provenance": act.get("provenance"),
        }
        if act.get("cdashDomain"):
            activity["cdashDomain"] = act.get("cdashDomain")
        if act.get("category"):
            activity["category"] = act.get("category")
        activities.append(activity)

    # Transform scheduled activity instances with full field preservation
    scheduled_instances = []
    for sai in interpretation.get("scheduledActivityInstances", []):
        sai_obj = {
            "id": sai.get("id"),
            "instanceType": "ScheduledActivityInstance",
            "activityId": sai.get("activityId"),
            "scheduledInstanceTimelineId": "TIMELINE-1",
            "scheduledInstanceEncounterId": sai.get("visitId"),
            "defaultConditionId": sai.get("condition"),
            "provenance": sai.get("provenance"),
        }

        # Add timingModifier if present (BI, EOI, pre-dose, post-dose)
        if sai.get("timingModifier"):
            sai_obj["timingModifier"] = sai.get("timingModifier")

        # Add footnoteMarkers if present
        if sai.get("footnoteMarkers"):
            sai_obj["footnoteMarkers"] = sai.get("footnoteMarkers")

        # Add isRequired flag
        if sai.get("isRequired") is not None:
            sai_obj["isRequired"] = sai.get("isRequired")

        scheduled_instances.append(sai_obj)

    # Build final USDM structure
    return {
        "studyVersion": [{
            "scheduleTimelines": [timeline],
            "encounters": encounters,
            "activities": activities,
            "scheduledActivityInstances": scheduled_instances,
        }],
        "footnotes": interpretation.get("footnotes", []),
    }
```

### 13.7 Stage 4: Quality Validation Implementation

**File:** `soa_quality_checker.py`

Five-dimensional quality evaluation with LLM terminology fallback:

```python
class SOAQualityChecker:
    """5D quality checker with LLM terminology fallback."""

    def __init__(self):
        self.terminology_mapper = get_mapper()  # Deterministic mapper
        self._usdm_schema = self._load_usdm_schema()

    async def evaluate_with_llm(
        self,
        data: Dict[str, Any],
        use_llm_fallback: bool = True,
    ) -> QualityScore:
        """Evaluate with optional LLM terminology fallback."""

        # Run deterministic evaluation first
        score = self.evaluate(data)

        # Apply LLM fallback for unmapped terminology
        if use_llm_fallback and score.unmapped_terms:
            await self._apply_llm_fallback(score)

        return score

    def evaluate(self, data: Dict[str, Any]) -> QualityScore:
        """Evaluate all 5 quality dimensions."""
        score = QualityScore()

        # Extract study version data
        study_version = self._extract_study_version_data(data)

        # 1. Accuracy - No placeholders, valid formats
        self._check_accuracy(data, score)

        # 2. Completeness - Required USDM fields present
        self._check_completeness(study_version, score)

        # 3. Compliance - JSON Schema validation
        self._check_compliance(study_version, score)

        # 4. Provenance - Page references present
        self._check_provenance(study_version, score)

        # 5. Terminology - CDISC codes valid
        self._check_terminology(study_version, score)

        return score
```

**Quality Dimension Implementations:**

```python
def _check_accuracy(self, data: Dict, score: QualityScore, path: str = "$"):
    """Check for placeholders and valid formats."""

    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}"
            score.total_fields += 1

            if isinstance(value, str):
                # Check for placeholder values
                if self._is_placeholder(value):
                    score.accuracy_issues.append(QualityIssue(
                        dimension="accuracy",
                        severity="error",
                        path=current_path,
                        message="Placeholder value detected",
                        value=value,
                    ))
                else:
                    score.valid_fields += 1

                # Check time format - EXCLUDE ID reference fields
                is_id_field = key.endswith("Id") or key.endswith("_id")
                if ("time" in key.lower() or "duration" in key.lower()) and not is_id_field:
                    if not self._is_valid_time_or_duration(value):
                        score.accuracy_issues.append(QualityIssue(
                            dimension="accuracy",
                            severity="warning",
                            path=current_path,
                            message="Invalid time/duration format",
                            value=value,
                        ))

def _check_provenance(self, data: Dict, score: QualityScore, path: str = "$"):
    """Check provenance coverage for values."""

    if isinstance(data, dict):
        has_provenance = "provenance" in data or "page_number" in data

        value_fields = ["value", "name", "description", "label"]
        for field in value_fields:
            if field in data and data[field]:
                # EXCLUDE window.description from provenance requirements
                if field == "description" and path.endswith(".window"):
                    continue

                score.total_provenance += 1
                if has_provenance:
                    score.valid_provenance += 1
                else:
                    score.provenance_issues.append(QualityIssue(
                        dimension="provenance",
                        severity="warning",
                        path=f"{path}.{field}",
                        message="Value lacks provenance (page reference)",
                        value=str(data[field])[:50],
                    ))
```

**LLM Terminology Fallback:**

```python
async def _apply_llm_fallback(self, score: QualityScore) -> None:
    """Apply LLM fallback for unmapped terminology."""

    llm_mapper = get_llm_mapper()  # soa_llm_terminology_mapper.py
    if not llm_mapper:
        return

    # Extract unique terms
    unique_terms = list(set(term for term, _ in score.unmapped_terms))
    logger.info(f"LLM terminology fallback for {len(unique_terms)} terms...")

    # Batch LLM call (single API call for efficiency)
    batch_result = await llm_mapper.map_batch(unique_terms)

    # Update score for successfully mapped terms
    mapped_count = 0
    for term, path in score.unmapped_terms:
        mapping = batch_result.get_mapping(term)
        if mapping and mapping.is_mapped():
            mapped_count += 1

    score.valid_terminology += mapped_count
    score.llm_mapped_count = mapped_count

    # Recalculate terminology score
    if score.total_terminology > 0:
        score.terminology = score.valid_terminology / score.total_terminology
```

### 13.8 Caching Strategy

**File:** `soa_cache.py`

Stage-level caching with content-aware invalidation:

```python
class SOACache:
    """Stage-level cache for SOA pipeline."""

    def __init__(self, cache_dir: Path = None):
        self.cache_dir = cache_dir or Path(__file__).parent / ".cache" / "soa"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _generate_key(self, prefix: str, protocol_id: str, content_hash: str) -> str:
        """Generate cache key with content hash."""
        return f"{prefix}_{protocol_id}_{content_hash[:16]}"

    def get(self, key: str) -> Optional[Any]:
        """Get cached value if exists and not expired."""
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)
        return None

    def set(self, key: str, value: Any) -> None:
        """Cache value to disk."""
        cache_file = self.cache_dir / f"{key}.json"
        with open(cache_file, "w") as f:
            json.dump(value, f)
```

**Cache Keys by Stage:**
| Stage | Cache Key Pattern | Invalidates When |
|-------|-------------------|------------------|
| Detection | `detection_v2_{protocol}_{pdf_hash}` | PDF changes |
| Extraction | `extraction_html_v2_{protocol}_{pages_hash}` | Detected pages change |
| Interpretation | Not cached | Always fresh |
| Terminology LLM | `term_mapping_{term_hash}` | Never (permanent) |

### 13.9 Data Models

**File:** `soa_pipeline_v2.py`

```python
@dataclass
class StageResult:
    """Result from a single pipeline stage."""
    success: bool
    stage: str = ""
    duration: float = 0.0
    data: Any = None
    error: Optional[str] = None
    cached: bool = False

@dataclass
class PipelineResultV2:
    """Complete pipeline execution result."""
    success: bool
    protocol_id: str
    stages: List[StageResult] = field(default_factory=list)
    interpretation: Optional[Dict] = None
    usdm_data: Optional[Dict] = None
    quality_score: Optional[QualityScore] = None
    output_files: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration: float = 0.0

@dataclass
class QualityScore:
    """5D quality assessment scores."""
    accuracy: float = 0.0
    completeness: float = 0.0
    compliance: float = 0.0
    provenance: float = 0.0
    terminology: float = 0.0

    # Issue lists
    accuracy_issues: List[QualityIssue] = field(default_factory=list)
    completeness_issues: List[QualityIssue] = field(default_factory=list)
    compliance_issues: List[QualityIssue] = field(default_factory=list)
    provenance_issues: List[QualityIssue] = field(default_factory=list)
    terminology_issues: List[QualityIssue] = field(default_factory=list)

    # Terminology tracking
    unmapped_terms: List[Tuple[str, str]] = field(default_factory=list)
    llm_mapped_count: int = 0

    @property
    def overall_score(self) -> float:
        """Weighted average of all dimensions."""
        return (
            self.accuracy * 0.25 +
            self.completeness * 0.20 +
            self.compliance * 0.20 +
            self.provenance * 0.20 +
            self.terminology * 0.15
        )

    def passes_thresholds(self) -> bool:
        """Check if all dimensions meet thresholds."""
        return (
            self.accuracy >= 0.95 and
            self.completeness >= 0.90 and
            self.compliance >= 1.00 and
            self.provenance >= 0.95 and
            self.terminology >= 0.90
        )
```

### 13.10 Configuration

**Environment Variables:**
```bash
# Required
ANTHROPIC_API_KEY=...    # Claude for interpretation + Stage 8 fallback
GEMINI_API_KEY=...       # Gemini Vision for detection + LLM terminology
LANDINGAI_API_KEY=...    # LandingAI for table extraction

# Optional Azure OpenAI (Stage 8 fallback)
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_DEPLOYMENT=...
AZURE_OPENAI_API_VERSION=...

# Optional SOA Settings
SOA_CACHE_ENABLED=true              # Enable stage caching (default: true)
SOA_MODEL=claude-sonnet-4-20250514  # Claude model for interpretation
USE_CLAUDE_PRIMARY=false            # Set to 'true' to use Claude as primary LLM in Stage 8
```

### 13.11 Output Structure

```
{pdf_dir}/soa_output/{YYYYMMDD_HHMMSS}/
├── {protocol}_soa_usdm.json            # Primary USDM 4.0 output
├── {protocol}_soa_quality.json         # Quality scores and issues
├── {protocol}_pipeline_summary.json    # Pipeline execution summary
└── interpretation_stages/              # 12-stage intermediate results
    ├── stage01_result.json
    ├── stage02_result.json
    └── ...
```

**Quality Report Structure:**
```json
{
  "scores": {
    "accuracy": 1.0,
    "completeness": 1.0,
    "compliance": 1.0,
    "provenance": 1.0,
    "terminology": 1.0,
    "overall": 1.0
  },
  "thresholds_met": true,
  "failed_dimensions": [],
  "counts": {
    "total_fields": 3263,
    "valid_fields": 3056,
    "total_provenance": 146,
    "valid_provenance": 146,
    "total_terminology": 65,
    "valid_terminology": 65
  },
  "issues": {
    "accuracy": [],
    "completeness": [],
    "compliance": [],
    "provenance": [],
    "terminology": []
  }
}
```

### 13.12 Key Files Reference

| File | Purpose | Key Methods |
|------|---------|-------------|
| `soa_extraction_pipeline.py` | Full end-to-end pipeline | `run()`, `_phase_*()` |
| `interpretation/interpretation_pipeline.py` | 12-stage orchestrator | `run()`, `_execute_stage()` |
| `soa_html_interpreter.py` | Claude HTML interpretation | `interpret()`, `_expand_to_sai_objects()` |
| `soa_page_detector_v2.py` | Gemini Vision detection | `detect()` |
| `soa_quality_checker.py` | 5D quality framework | `evaluate()`, `evaluate_with_llm()` |
| `soa_llm_terminology_mapper.py` | LLM CDISC mapping | `map_batch()`, `get_mapping()` |
| `soa_terminology_mapper.py` | Deterministic CDISC lookup | `map_term()`, `_match_cdisc_*()` |
| `soa_cache.py` | Stage-level caching | `get()`, `set()` |
| `interpretation/stage11_schedule_generation.py` | Schedule generation | `generate_schedule()` |
| `prompts/html_interpretation.txt` | Phase 1 prompt | - |
| `prompts/matrix_extraction.txt` | Phase 2 prompt | - |

---

## 14. SOA Interpretation Pipeline (12-Stage)

### 14.1 Overview

The SOA Interpretation Pipeline is a comprehensive 12-stage system that transforms extracted SOA tables into complete, USDM 4.0 compliant visit schedules. Located in `soa_analyzer/interpretation/`.

**Design Principles:**
1. **LLM-First** - Use semantic LLM reasoning over brittle regex/hardcoded rules
2. **Confidence-Based** - Auto-apply high-confidence (≥0.90), escalate low-confidence to human review
3. **Audit Trail** - Full provenance for every generated entity
4. **USDM Compliant** - 6-field Code objects, referential integrity, Condition linkage

### 14.2 Pipeline Stages

| Stage | Name | Status | Purpose |
|-------|------|--------|---------|
| **1** | Domain Categorization | ✅ IMPLEMENTED | Map activities to CDISC domains |
| **2** | Activity Expansion | ✅ IMPLEMENTED | Decompose parent activities to components |
| **3** | Hierarchy Building | ✅ IMPLEMENTED | Build parent-child activity trees |
| **4** | Alternative Resolution | ✅ IMPLEMENTED | Handle X or Y choice points |
| **5** | Specimen Enrichment | ✅ IMPLEMENTED | Extract tube/volume details |
| **6** | Conditional Expansion | ✅ IMPLEMENTED | Apply population/clinical conditions |
| **7** | Timing Distribution | ✅ IMPLEMENTED | Expand BI/EOI, pre/post-dose timings |
| **8** | Cycle Expansion | ✅ IMPLEMENTED (v2.0) | Generate visits for repeating patterns (triple LLM fallback) |
| **9** | Protocol Mining | ✅ IMPLEMENTED | Cross-reference non-SOA sections |
| **10** | Human Review Assembly | ✅ IMPLEMENTED | Package for human review |
| **11** | Schedule Generation | ✅ IMPLEMENTED | Apply decisions, generate final |
| **12** | USDM Compliance | ✅ IMPLEMENTED | Code object expansion + validation |

**Pipeline Orchestrator:** `soa_analyzer/interpretation/interpretation_pipeline.py`

```python
from soa_analyzer.interpretation import InterpretationPipeline, run_interpretation_pipeline

# Run all 12 stages
pipeline = InterpretationPipeline()
result = await pipeline.run(soa_output, config)

# Access results
print(result.get_summary())  # Stage completion summary
print(result.final_usdm)     # Final USDM output
```

### 14.3 Stage 1: Domain Categorization (CRITICAL)

**File:** `interpretation/stage1_domain_categorization.py`

Maps all SOA activities to CDISC domains (LB, VS, EG, PE, etc.):

```python
class DomainCategorizer:
    """LLM-first domain categorization for SOA activities."""

    async def categorize(self, activities: List[Dict]) -> CategorizationResult:
        """
        Categorize activities into CDISC domains using batch LLM.

        Features:
        - Single LLM call for all activities (efficiency)
        - Confidence-based classification: high / needs_review / uncertain
        - Caching by activity name + model version
        - Fallback: Gemini → Azure OpenAI
        """
```

**Valid CDISC Domains:** LB, VS, EG, PE, DA, CM, AE, MH, DM, DS, SC, IE, DV, FA, QS, RS, TU, TR, AG, SU, MO, EC

### 14.4 Stage 2: Activity Expansion

**File:** `interpretation/stage2_activity_expansion.py`

Decomposes collapsed parent activities into component tests using protocol-specific data:

```python
class ActivityExpander:
    """Protocol-driven, LLM-first activity expansion (v3.0)."""

    def expand_activities(
        self,
        usdm_output: Dict,
        extraction_outputs: Dict,
        gemini_file_uri: str,
    ) -> Stage2Result:
        """
        Expand collapsed activities (e.g., "Chemistry Panel" → individual tests)

        Design Principles (v3.0):
        - Protocol-Only: Use ONLY data from this protocol (no static library)
        - LLM-First: Single unified Gemini query with JSON + PDF context
        - Full Provenance: Every component traced to source (page, JSON path)
        - Conservative: Only expand with high confidence (>= 0.85)

        Data Sources:
        - Extraction module JSON outputs (lab_specs, biospecimen, pkpd, etc.)
        - Protocol PDF text via Gemini Files API
        """
```

**v3.0 Changes:**
- Replaced static library (`activity_components.json`) with LLM-based expansion
- Added `ComponentValidator` for intelligent garbage filtering
- Deduplication uses LLM semantic understanding (e.g., WBC = White Blood Cell Count)
- Tiered validation: cache lookup → LLM batch validation → confidence thresholds

**Example:**
- Input: "Complete Blood Count with Differential"
- Output: ["WBC", "RBC", "Hemoglobin", "Hematocrit", "Platelet Count", "Neutrophils", "Lymphocytes", ...]
- Provenance: Each component traced to protocol section/page

### 14.5 Stage 3: Hierarchy Building

**File:** `interpretation/stage3_hierarchy_builder.py`

Builds parent-child activity trees grouped by CDISC domain:

```python
class HierarchyBuilder:
    """Domain-grouped activity hierarchy construction."""

    def build(self, activities: List[Dict]) -> Stage3Result:
        """
        Build hierarchical activity trees.

        Features:
        - Group by CDISC domain (primary grouping)
        - Detect header rows using pattern matching
        - Sort by domain priority (VS=1, LB=2, EG=3, PE=4, etc.)
        """
```

### 14.6 Stage 8: Cycle Expansion (CRITICAL)

**File:** `interpretation/stage8_cycle_expansion.py`

Generates visits for repeating cycle patterns with triple-LLM fallback:

```python
class CycleExpander:
    """LLM-first cycle expansion with triple fallback."""

    async def expand_cycles(self, usdm_output: Dict) -> Stage8Result:
        """
        Expand encounters with cycle patterns into individual cycle visits.

        LLM Fallback Chain (v2.0):
        1. Gemini 2.5 Flash (primary)
        2. Azure OpenAI (fallback 1)
        3. Anthropic Claude (fallback 2)

        Set USE_CLAUDE_PRIMARY=true to test Claude as primary.
        """
```

**Open-Ended Detection Logic (v2.0 - December 2025):**

The `_is_open_ended_pattern()` function uses a conservative approach:
- Returns `True` ONLY if BOTH `endCycle` is null AND `maxCycles` is null
- Explicit ranges like "Cycle 2-6" have `endCycle=6` → NOT open-ended → expand normally
- Patterns like "Cycle 4+" have `endCycle=null` → open-ended → require human review

```python
def _is_open_ended_pattern(self, pattern: str, llm_decision: Dict) -> bool:
    """Determine if pattern is genuinely open-ended (unbounded)."""
    end_cycle = llm_decision.get("endCycle")
    max_cycles = llm_decision.get("maxCycles")

    # Conservative: Only open-ended if BOTH are null
    if end_cycle is not None or max_cycles is not None:
        return False  # Has a bound - not open-ended

    pattern_type = llm_decision.get("patternType", "").lower()
    return pattern_type in {"open_ended", "open-ended", "unbounded", "continuing"}
```

**Pattern Examples:**

| Pattern | endCycle | patternType | isOpenEnded | Action |
|---------|----------|-------------|-------------|--------|
| "Cycle 2-6 Day 1" | 6 | explicit_range | False | Expand to 5 visits |
| "Cycles 1-3" | 3 | explicit_range | False | Expand to 3 visits |
| "Cycle 4+" | null | open_ended | True | Human review |
| "Cycle 4 and subsequent" | null | continuing | True | Human review |

### 14.7 Stage 7: Timing Distribution (CRITICAL)

**File:** `interpretation/stage7_timing_distribution.py`

Expands SAIs with merged/complex timing modifiers into separate atomic SAI objects:

```python
class TimingDistributor:
    """LLM-first timing distribution with USDM Code object generation."""

    async def distribute_timing(self, usdm_output: Dict) -> Stage7Result:
        """
        Expand merged timing modifiers (e.g., "BI/EOI") into atomic SAIs.

        Processing Flow:
        1. Extract unique timing modifiers from all SAIs
        2. Check cache for each modifier
        3. Send uncached modifiers to LLM in single batch
        4. Validate LLM results against known patterns
        5. Generate expanded SAIs with USDM Code objects
        6. Apply expansions to USDM output
        """

    def _get_timing_code(self, timing: str) -> Dict[str, Any]:
        """Get USDM 4.0 compliant Code object for timing modifier."""
```

**Supported Timing Patterns (60+):**

| Pattern | Example Input | Expanded Output |
|---------|---------------|-----------------|
| BI/EOI split | `"BI/EOI"` | `["BI", "EOI"]` |
| Pre/Post dose | `"pre-dose/post-dose"` | `["pre-dose", "post-dose"]` |
| Hour offsets | `"0h, 2h, 4h post-dose"` | `["0h post-dose", "2h post-dose", "4h post-dose"]` |
| Minute offsets | `"30min, 60min pre-dose"` | `["30min pre-dose", "60min pre-dose"]` |
| Trough/Peak | `"trough/peak"` | `["trough", "peak"]` |
| Day-based | `"Day 1, Day 8, Day 15"` | `["Day 1", "Day 8", "Day 15"]` |
| Cycle-based | `"C1D1, C2D1"` | `["C1D1", "C2D1"]` |

**USDM Code Object Generation:**

Expanded SAIs have USDM 4.0 compliant 6-field Code objects:

```json
{
  "id": "SAI-042-BI",
  "activityId": "ACT-006",
  "scheduledInstanceEncounterId": "ENC-002",
  "timingModifier": {
    "id": "CODE-TIM-A1B2C3D4",
    "code": "C71148",
    "decode": "Before Infusion",
    "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
    "codeSystemVersion": "24.12",
    "instanceType": "Code"
  },
  "_timingExpansion": {
    "originalId": "SAI-042",
    "originalTimingModifier": "BI/EOI",
    "expandedTiming": "BI",
    "confidence": 0.98,
    "rationale": "Standard BI/EOI split for PK sampling",
    "stage": "Stage7TimingDistribution",
    "model": "gemini-2.5-flash",
    "timestamp": "2025-12-06T10:30:00Z",
    "source": "llm",
    "cacheHit": false
  }
}
```

**CDISC Timing Codes** (`config/timing_codes.json`):

| Timing | Code | Decode |
|--------|------|--------|
| BI | C71148 | Before Infusion |
| EOI | C71149 | End of Infusion |
| SOI | C71150 | Start of Infusion |
| pre-dose | C82489 | Pre-dose |
| post-dose | C82490 | Post-dose |
| trough | C64639 | Trough |
| peak | C64638 | Peak |
| fasting | C49666 | Fasting |
| fed | C64846 | Fed State |

**Footnote Condition Flagging:**

SAIs with footnotes are flagged for human review:
```json
{
  "_hasFootnoteCondition": true,
  "_footnoteMarkersPreserved": ["a", "c"]
}
```

### 14.7 Stage 12: USDM Compliance (CRITICAL)

**File:** `interpretation/stage12_usdm_compliance.py`

Final USDM 4.0 compliance enforcement and validation:

```python
class USDMComplianceChecker:
    """USDM 4.0 compliance validation and auto-fix."""

    def ensure_compliance(self, usdm_output: Dict) -> Tuple[Dict, ComplianceResult]:
        """
        Ensure full USDM 4.0 compliance.

        Steps:
        1. Collect all entity IDs for referential integrity
        2. Expand simple code/decode pairs to 6-field Code objects
        3. Validate all ID references point to existing entities
        4. Extract and link conditions from footnotes
        5. Generate comprehensive compliance report
        """
```

**Compliance Checks:**
- Code object expansion: `{code, decode}` → 6-field Code objects
- Referential integrity: All referenced IDs must exist
- Condition linkage: Footnotes → Condition objects → ConditionAssignments

### 14.8 Data Models

**File:** `models/timing_expansion.py`

```python
@dataclass
class TimingPattern:
    """Pattern definition for timing validation."""
    id: str
    pattern_regex: str
    atomic_timings: List[str]
    description: Optional[str] = None

@dataclass
class TimingDecision:
    """LLM decision for a timing modifier."""
    timing_modifier: str
    should_expand: bool
    expanded_timings: List[str]
    confidence: float
    rationale: Optional[str] = None
    source: str = "llm"  # "llm", "cache", "default"
    model_name: Optional[str] = None

@dataclass
class TimingExpansion:
    """Result of expanding a single SAI."""
    id: str = field(default_factory=lambda: f"EXP-{uuid.uuid4().hex[:8].upper()}")
    original_sai_id: str = ""
    original_timing_modifier: str = ""
    expanded_sais: List[Dict[str, Any]] = field(default_factory=list)
    decision: Optional[TimingDecision] = None
    requires_review: bool = False
    review_reason: Optional[str] = None

@dataclass
class Stage7Result:
    """Complete Stage 7 result with metrics."""
    expansions: List[TimingExpansion] = field(default_factory=list)
    review_items: List[HumanReviewItem] = field(default_factory=list)
    decisions: Dict[str, TimingDecision] = field(default_factory=dict)
    discrepancies: List[ValidationDiscrepancy] = field(default_factory=list)

    # Metrics
    unique_timings_analyzed: int = 0
    sais_processed: int = 0
    sais_with_timing: int = 0
    sais_expanded: int = 0
    sais_created: int = 0
    sais_unchanged: int = 0
    cache_hits: int = 0
    llm_calls: int = 0
    validation_flags: int = 0
```

### 14.9 Configuration Files

| File | Purpose |
|------|---------|
| `config/timing_codes.json` | CDISC code mapping for atomic timings |
| `config/timing_patterns.json` | 60+ known expansion patterns for validation |
| `config/activity_domain_map.json` | Activity to domain mapping |
| `prompts/timing_distribution.txt` | LLM prompt for timing analysis |
| `prompts/domain_categorization.txt` | LLM prompt for domain mapping |
| `prompts/activity_expansion_unified.txt` | LLM prompt for protocol-driven activity expansion |
| `prompts/component_validation.txt` | LLM prompt for component validation |
| `prompts/terminology_disambiguation.txt` | LLM prompt for CDISC terminology disambiguation |

### 14.10 Caching Strategy

Stage 7 uses two-level caching:

**Level 1: In-Memory**
- Session lifetime, fast lookups
- Cache key: `md5(timing_modifier.lower().strip())`

**Level 2: Disk**
- Persistent across runs
- File: `.cache/timing_distribution/decisions_cache.json`

**Cache Value:**
```json
{
  "shouldExpand": true,
  "expandedTimings": ["BI", "EOI"],
  "confidence": 0.98,
  "rationale": "Standard BI/EOI split for PK sampling",
  "source": "llm",
  "model_name": "gemini-2.5-flash",
  "cached_at": "2025-12-06T10:30:00Z"
}
```

### 14.11 Testing

**Unit Tests:** `tests/test_stage7_timing_distribution.py` (33 tests)
```bash
python -m pytest soa_analyzer/tests/test_stage7_timing_distribution.py -v
```

**Integration Tests:** `tests/test_stage7_12_integration.py` (13 tests)
```bash
python -m pytest soa_analyzer/tests/test_stage7_12_integration.py -v
```

**Test Coverage:**
- TimingPatternRegistry (pattern loading, atomic detection, expansion lookup)
- TimingDecision, TimingExpansion, Stage7Result (data models)
- TimingDistributor (SAI generation, caching, LLM parsing)
- Stage 7→12 integration (Code objects, referential integrity, provenance)

### 14.12 Key Files Reference

| File | Purpose |
|------|---------|
| `interpretation/__init__.py` | Pipeline exports and stage documentation |
| `interpretation/interpretation_pipeline.py` | 12-stage orchestrator |
| `interpretation/context_assembler.py` | Assembles protocol context for LLM queries |
| `interpretation/component_validator.py` | LLM-based semantic component validation |
| `interpretation/cdisc_code_enricher.py` | CDISC code enrichment and validation |
| `interpretation/stage1_domain_categorization.py` | CDISC domain mapping |
| `interpretation/stage2_activity_expansion.py` | Protocol-driven activity decomposition |
| `interpretation/stage3_hierarchy_builder.py` | Parent-child tree building |
| `interpretation/stage7_timing_distribution.py` | Timing modifier expansion |
| `interpretation/stage8_cycle_expansion.py` | Cycle pattern expansion (triple LLM fallback) |
| `interpretation/stage11_schedule_generation.py` | Draft schedule generation |
| `interpretation/stage12_usdm_compliance.py` | USDM 4.0 compliance |
| `models/timing_expansion.py` | Stage 7 data models |
| `models/cycle_expansion.py` | Stage 8 data models |
| `models/expansion_proposal.py` | Activity expansion data models |
| `models/code_object.py` | USDM Code object implementation |
| `models/condition.py` | Condition extraction from footnotes |

---

## 15. Eligibility Analyzer Architecture

### 15.1 Overview

The Eligibility Analyzer is a specialized module for extracting, decomposing, and structuring eligibility criteria from clinical trial protocols. It produces USDM 4.0 compliant JSON with OMOP CDM integration for patient feasibility analysis.

**Key Capabilities:**
- Expression tree model for complex boolean logic (AND/OR/NOT/EXCEPT)
- Atomic decomposition of compound criteria into SQL-queryable units
- OMOP concept mapping via ATHENA database
- Queryable Eligibility Blocks (QEB) for feasibility applications
- Patient funnel generation with population estimates

### 15.2 Five-Phase Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ELIGIBILITY EXTRACTION PIPELINE                        │
└─────────────────────────────────────────────────────────────────────────┘

     ┌───────────┐
     │ PDF Input │
     └─────┬─────┘
           │
           ▼
┌─────────────────────┐     ┌─────────────────────┐
│  Phase 1: Detection │────▶│  Find eligibility   │
│  (Gemini File API)  │     │  sections in PDF    │
└─────────────────────┘     └──────────┬──────────┘
                                       │
                            ┌──────────▼──────────┐
                            │  Phase 2: Extraction│
                            │  (Claude Two-Phase) │
                            │  - Pass 1: Values   │
                            │  - Pass 2: Provenance│
                            └──────────┬──────────┘
                                       │
                            ┌──────────▼──────────┐
                            │  Phase 3:           │
                            │  Interpretation     │
                            │  (12-Stage Pipeline)│
                            └──────────┬──────────┘
                                       │
                            ┌──────────▼──────────┐
                            │  Phase 4: Validation│
                            │  5D Quality Scoring │
                            │  + Surgical Retry   │
                            └──────────┬──────────┘
                                       │
                                       ▼
                            ┌─────────────────────┐
                            │  Phase 5: Output    │
                            │  - USDM JSON        │
                            │  - SQL Templates    │
                            │  - Quality Report   │
                            │  - QEB for Feasibility│
                            └─────────────────────┘
```

### 15.3 12-Stage Interpretation Pipeline

The interpretation pipeline transforms raw extracted criteria into structured, queryable eligibility blocks.

**Stage Execution Order**: `[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]`

| Stage | Name | Purpose | Critical |
|-------|------|---------|----------|
| 1 | Cohort Detection | Identify study arms/cohorts | No |
| 2 | **Atomic Decomposition** | Break compound criteria into atomics | **YES** |
| 3 | Clinical Categorization | Assign clinical domains (demographics, oncology, labs) | No |
| 4 | Term Extraction | Extract searchable terms + LLM concept expansion | No |
| 5 | **OMOP Concept Mapping** | Map to ATHENA concepts | **YES** |
| 6 | SQL Template Generation | Generate OMOP CDM SQL queries | No |
| 7 | **USDM Compliance** | Transform to USDM 4.0 format | **YES** |
| 8 | Tier Assignment | Assign criticality tiers | No |
| 9 | Human Review Assembly | Package for human review | No |
| 10 | Final Output Generation | Generate output files | No |
| 11 | Feasibility Analysis | Patient funnel + population estimates | No |
| 12 | QEB Builder | Build Queryable Eligibility Blocks | No |

**Critical Stages** (pipeline fails if these fail): Stages 2, 5, 7

**Cacheable Stages**: Stages 2, 5, 11, 12

### 15.4 Stage 2: Atomic Decomposition

The most complex stage, responsible for breaking compound eligibility criteria into SQL-queryable atomic units while preserving logical relationships.

#### 15.4.1 Expression Tree Model

```python
@dataclass
class ExpressionNode:
    """Recursive tree node for eligibility logic."""
    node_id: str
    node_type: Literal["atomic", "operator", "temporal"]
    operator: Optional[Literal["AND", "OR", "NOT", "EXCEPT"]] = None
    children: List["ExpressionNode"] = field(default_factory=list)

    # Atomic node fields
    atomic_text: Optional[str] = None
    is_negated: bool = False
    omop_table: Optional[str] = None
    sql_template: Optional[str] = None

    # Temporal constraints
    temporal_constraint: Optional[TemporalConstraint] = None
```

**Supported Operators:**
- `AND`: All conditions must be true
- `OR`: At least one condition must be true
- `NOT`: Negation of condition
- `EXCEPT`: Exception handling (e.g., "X unless Y")

**Example Decomposition:**

```
Original: "Patients with confirmed NSCLC (Stage IIIB or IV) who have not
           received prior systemic therapy unless disease recurrence >6 months"

Expression Tree:
AND
├── atomic: "confirmed NSCLC diagnosis"
│   └── omop_table: condition_occurrence
├── OR
│   ├── atomic: "Stage IIIB disease"
│   └── atomic: "Stage IV disease"
└── EXCEPT
    ├── NOT
    │   └── atomic: "received prior systemic therapy"
    └── temporal: "disease recurrence >6 months ago"
        └── constraint: duration_days > 180
```

#### 15.4.2 LLM Configuration

**Primary LLM**: Gemini 2.5 Pro (best for complex JSON generation)
**Fallback LLM**: Azure OpenAI (gpt-4o-mini)

**JSON Repair**: Uses reflection loop pattern - if JSON parse fails, LLM receives error message and attempts repair (up to 3 retries).

**Parallel Processing**: Batch size of 5 criteria processed concurrently.

#### 15.4.3 OMOP Table Inference

Stage 2 infers the target OMOP table from text patterns:

| Pattern | OMOP Table |
|---------|-----------|
| diagnosis, disease, cancer, tumor | `condition_occurrence` |
| medication, drug, therapy, treatment | `drug_exposure` |
| lab, level, count, test, measurement | `measurement` |
| surgery, procedure, biopsy | `procedure_occurrence` |
| age, gender, sex, weight | `observation` |

### 15.5 Stage 5: OMOP Concept Mapping

Maps extracted terms to OMOP concepts using the ATHENA database with parallelized queries.

#### 15.5.1 LLM-First Approach

1. **Stage 4 LLM Expansion**: Terms are first normalized by LLM to get:
   - Standard term spelling
   - Abbreviation expansions (e.g., "NSCLC" → "Non-Small Cell Lung Cancer")
   - Synonym variants
   - OMOP domain hints (Condition, Drug, Measurement, etc.)
   - Vocabulary hints (ICD10CM, SNOMED, LOINC, RxNorm, etc.)

2. **Parallel ATHENA Search**: Uses ThreadPoolExecutor with 10 workers
   - Exact name matching
   - Pattern matching (LIKE queries)
   - Synonym lookup via `concept_synonym` table

3. **Stage 5.5 Clinical Reasoning**: For unmapped terms, LLM attempts clinical reasoning to find related concepts

#### 15.5.2 Vocabulary Priority by Domain

| Domain | Vocabulary Priority |
|--------|---------------------|
| Condition | ICD10CM, SNOMED, ICD9CM |
| Drug | RxNorm, RxNorm Extension, NDC, HemOnc |
| Measurement | LOINC, SNOMED |
| Procedure | CPT4, HCPCS, ICD10PCS, SNOMED |
| Observation | SNOMED, NCIt, LOINC |
| Device | SNOMED, HCPCS |

### 15.6 Stage 11: Feasibility Analysis

Generates patient funnel for site feasibility assessment.

**Key Components:**
- `CriterionClassifier`: LLM-based classification into funnel categories
- `KeyCriteriaNormalizer`: Applies 80/20 rule to identify ~10-15 key criteria
- `PopulationEstimator`: Estimates eligible population with confidence intervals
- `EligibilityFunnelBuilder`: Builds sequential elimination funnel

**Killer Criteria**: Criteria identified as having high elimination rates (requires epidemiological evidence).

**Queryability Classification**:
- `QUERYABLE`: Can be directly queried in EHR/CDM
- `SCREENING_ONLY`: Requires manual screening/chart review
- `NOT_APPLICABLE`: Administrative criteria (e.g., informed consent)

### 15.7 Stage 12: QEB Builder

Builds Queryable Eligibility Blocks for integration with feasibility applications.

#### 15.7.1 QEB Structure

```python
@dataclass
class QueryableEligibilityBlock:
    """Maps 1:1 to original protocol criterion."""
    qeb_id: str
    criterion_id: str
    criterion_type: Literal["inclusion", "exclusion"]
    original_text: str
    clinical_name: str  # LLM-generated clinical name

    # Atomic decomposition
    atomics: List[AtomicCriterion]
    expression_tree: ExpressionNode

    # SQL
    combined_sql: str  # Uses INTERSECT/UNION/EXCEPT
    individual_sqls: List[str]

    # Classification
    queryable_status: Literal["QUERYABLE", "SCREENING_ONLY", "NOT_APPLICABLE"]
    funnel_cluster: str  # Demographics, Disease, Treatment, etc.
    is_killer_criterion: bool
```

#### 15.7.2 SQL Combination Logic

The expression tree maps to SQL set operations:

| Operator | SQL Operation |
|----------|---------------|
| AND | `INTERSECT` |
| OR | `UNION` |
| NOT | `EXCEPT` (from base population) |
| EXCEPT | `EXCEPT` |

**Example Combined SQL:**
```sql
-- Expression: (A AND B) OR C
(
  SELECT person_id FROM A_query
  INTERSECT
  SELECT person_id FROM B_query
)
UNION
SELECT person_id FROM C_query
```

#### 15.7.3 LLM-Powered Enrichment

Stage 12 uses LLM for several tasks:

1. **Clinical Naming**: Generate concise clinical names for criteria
2. **Queryability Assessment**: Classify as QUERYABLE/SCREENING_ONLY/NOT_APPLICABLE
3. **Funnel Clustering**: Group into clinical categories (Demographics, Disease, Treatment, Labs)
4. **Killer Criteria Identification**: Flag high-elimination criteria

### 15.8 Caching Architecture

The eligibility pipeline uses SQLite-based caching:

```
eligibility_analyzer/
└── .cache/
    └── eligibility_cache.db
```

**Cacheable Operations:**
- Stage 2 atomic decomposition results
- Stage 5 OMOP mapping results
- Stage 11 feasibility analysis
- Stage 12 QEB outputs

**Cache TTL**: 30 days (configurable via `PipelineConfig.cache_ttl_days`)

### 15.9 Output Files

| File | Description |
|------|-------------|
| `{protocol}_eligibility_criteria.json` | USDM 4.0 compliant eligibility criteria |
| `{protocol}_atomic_decomposition.json` | Stage 2 output with expression trees |
| `{protocol}_omop_mappings.json` | Stage 5 OMOP concept mappings |
| `{protocol}_sql_templates.json` | Stage 6 SQL query templates |
| `{protocol}_funnel_result.json` | Stage 11 feasibility funnel |
| `{protocol}_qeb_output.json` | Stage 12 queryable eligibility blocks |
| `{protocol}_eligibility_quality_report.json` | 5D quality scores |

### 15.10 Key File Locations

| Component | Location |
|-----------|----------|
| Pipeline Entry Point | `eligibility_analyzer/eligibility_extraction_pipeline.py` |
| Section Detector | `eligibility_analyzer/eligibility_section_detector.py` |
| Criteria Extractor | `eligibility_analyzer/eligibility_criteria_extractor.py` |
| Quality Checker | `eligibility_analyzer/eligibility_quality_checker.py` |
| Interpretation Pipeline | `eligibility_analyzer/interpretation/interpretation_pipeline.py` |
| Stage 2 (Atomic) | `eligibility_analyzer/interpretation/stage2_atomic_decomposition.py` |
| Stage 11 (Feasibility) | `eligibility_analyzer/interpretation/stage11_feasibility.py` |
| Stage 12 (QEB) | `eligibility_analyzer/interpretation/stage12_qeb_builder.py` |
| Feasibility Models | `eligibility_analyzer/feasibility/data_models.py` |
| QEB Models | `eligibility_analyzer/feasibility/qeb_models.py` |
| Prompts | `eligibility_analyzer/prompts/*.txt` |
| Reference Data | `eligibility_analyzer/reference_data/` |

### 15.11 Usage Examples

#### CLI Extraction

```bash
cd backend_vNext
source venv/bin/activate

# Full extraction pipeline
python eligibility_analyzer/eligibility_extraction_pipeline.py /path/to/protocol.pdf

# With ATHENA database for OMOP mapping
ATHENA_DB_PATH=/path/to/athena_concepts_full.db \
  python eligibility_analyzer/eligibility_extraction_pipeline.py /path/to/protocol.pdf
```

#### Programmatic Usage

```python
from eligibility_analyzer.eligibility_extraction_pipeline import (
    EligibilityExtractionPipeline,
    run_eligibility_extraction,
)

# Option 1: Class-based
pipeline = EligibilityExtractionPipeline(athena_db_path="/path/to/athena.db")
result = await pipeline.run("/path/to/protocol.pdf")

# Option 2: Convenience function
result = await run_eligibility_extraction("/path/to/protocol.pdf")

# Access results
print(f"Success: {result.success}")
print(f"Quality: {result.quality_score.overall_score:.1%}")
print(f"Atomics: {result.atomic_count}")
print(f"Key Criteria: {result.key_criteria_count}")
```

### 15.12 Integration with Main Pipeline

The eligibility analyzer integrates with the main extraction pipeline via the USDM combiner:

```bash
python app/services/usdm_combiner.py \
  --main /path/to/usdm_4.0.json \
  --soa /path/to/soa_usdm_draft.json \
  --eligibility /path/to/eligibility_criteria.json
```

This produces a combined USDM 4.0 JSON with:
- Study metadata from main extraction
- Schedule of Activities from SOA analyzer
- Eligibility criteria from eligibility analyzer

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 4.2 | Dec 2025 | Added Section 15: Eligibility Analyzer Architecture - 12-stage interpretation pipeline, expression tree model for boolean logic, QEB builder, OMOP CDM integration, patient feasibility funnel |
| 4.1 | Dec 2025 | Stage 8 fix: Open-ended detection now checks both endCycle AND maxCycles; Added Claude as third LLM fallback (Gemini → Azure → Claude); Added USE_CLAUDE_PRIMARY env var |
| 4.0 | Dec 2025 | Unified SOAExtractionPipeline: Full 12-stage interpretation, Stage 11 schedule generation |
| 3.5 | Dec 2024 | 12-Stage Interpretation Pipeline: Stage 7 Timing Distribution with USDM Code objects |
| 3.4 | Dec 2024 | SOA Pipeline v2: USDM field preservation, timestamped output, LLM terminology fallback |
| 3.1 | Dec 2024 | Integrated value+provenance pattern for text fields |
| 3.0 | Dec 2024 | Five-dimensional quality framework, auto-correction, snippet truncation |
| 2.0 | Nov 2024 | Two-phase extraction, sequential execution |
| 1.0 | Oct 2024 | Initial implementation |

---

## Related Documents

- `CLAUDE.md` - Backend-specific Claude Code instructions
- `../CLAUDE.md` - Project-wide Claude Code instructions
- `../SYSTEM_DESIGN.md` - Full pipeline system architecture
