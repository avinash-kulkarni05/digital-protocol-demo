# Stage 4: Alternative Resolution - Implementation Design

**Priority**: HIGH (Foundation for choice-point handling)
**Status**: DESIGN COMPLETE - Ready for Implementation
**Date**: 2025-12-06

---

## 1. Overview

Stage 4 identifies and resolves alternative/choice points in SOA tables where activities have multiple options ("Test A or Test B", "CT / MRI").

**Input**: USDM with activities potentially containing alternatives
**Output**: USDM with resolved alternatives (expanded to separate entities or flagged for review)

### Problem Statement

Clinical protocols often present activities with alternatives:
- "Hematology or Chemistry panel" (site chooses one)
- "CT scan / MRI" (imaging modality choice)
- "Urine or serum pregnancy test" (specimen type choice)
- "ECG (or Holter if indicated)" (conditional alternative)

Current pipeline passes these through as single merged activities, losing the choice-point semantics needed for EDC automation.

---

## 2. Alternative Types & Examples

### Type 1: MUTUALLY_EXCLUSIVE
One option must be chosen; both cannot be performed.

| Example | Alternatives | Resolution |
|---------|-------------|------------|
| "CT scan or MRI" | [CT scan, MRI] | Create 2 SAIs with exclusive conditions |
| "Blood or urine sample" | [Blood, Urine] | Create 2 SAIs with specimen conditions |
| "Method A / Method B" | [Method A, Method B] | Create 2 activities, link via conditions |

### Type 2: DISCRETIONARY
Site/investigator chooses based on clinical judgment.

| Example | Alternatives | Resolution |
|---------|-------------|------------|
| "Additional labs if indicated" | [Standard, Extended] | Create ScheduledDecisionInstance |
| "ECG at investigator discretion" | [ECG, None] | Create optional activity with condition |

### Type 3: CONDITIONAL
Alternative depends on patient characteristic or clinical state.

| Example | Alternatives | Resolution |
|---------|-------------|------------|
| "Serum pregnancy test (females only)" | [Pregnancy test, None] | Link to DEMOGRAPHIC_SEX condition |
| "HbA1c for diabetics" | [HbA1c, None] | Link to clinical condition |

### Type 4: PREFERRED_WITH_FALLBACK
One option is preferred, fallback used if unavailable.

| Example | Alternatives | Resolution |
|---------|-------------|------------|
| "CT preferred, MRI if CT unavailable" | [CT (preferred), MRI (fallback)] | Create with priority metadata |

---

## 3. Detection Patterns

### High-Confidence Patterns (≥0.90)

```
Explicit OR:
- "Test A or Test B"
- "Test A OR Test B"
- "either Test A or Test B"

Slash Notation (not timing):
- "CT / MRI"
- "blood/urine sample"
- "Method A/Method B"

Parenthetical:
- "Test A (or Test B)"
- "Test A (or Test B if indicated)"
```

### Medium-Confidence Patterns (0.70-0.89)

```
Conditional alternatives:
- "Test A; Test B if abnormal"
- "Test A, repeat if clinically indicated"

Implied alternatives:
- "Test A as needed"
- "Test A per investigator judgment"
```

### Non-Alternative Patterns (DO NOT expand)

```
- "Test A and Test B" (both required)
- "Test A / see Section X" (reference, not alternative)
- "Test A at all visits" (timing, not choice)
- "BI/EOI" (timing modifier - Stage 7 handles this)
- "pre-dose/post-dose" (timing modifier)
```

---

## 4. Architecture (LLM-First)

### Class Structure

```
Stage 4: Alternative Resolution Handler

Class: AlternativeResolver
├── Config: AlternativeResolutionConfig
│   ├── confidence_threshold_auto: float = 0.90
│   ├── confidence_threshold_review: float = 0.70
│   ├── expand_mutually_exclusive: bool = True
│   ├── create_conditions: bool = True
│   ├── max_alternatives_per_activity: int = 5
│   └── model_name: str = "gemini-2.0-flash-exp"
│
├── Registry: AlternativePatternRegistry
│   ├── Load from: config/alternative_patterns.json
│   ├── Methods:
│   │   ├── is_non_alternative(text) → bool
│   │   ├── is_timing_pattern(text) → bool
│   │   ├── get_known_alternatives(text) → List[str]
│   │   └── validate_decision(decision) → List[discrepancies]
│
├── LLM Processing:
│   ├── Prompt: prompts/alternative_resolution.txt
│   ├── Primary: Gemini 2.0 Flash
│   ├── Fallback: Azure OpenAI
│   ├── Batch Size: 20 activities per call
│   └── Cache: Two-level (memory + disk)
│
├── Resolution Engine:
│   ├── _expand_mutually_exclusive()
│   ├── _create_discretionary_decision()
│   ├── _link_conditional_alternative()
│   └── _flag_for_review()
│
└── Output:
    ├── Stage4Result (metrics, expansions, review items)
    └── apply_resolutions_to_usdm(usdm, result) → updated_usdm
```

### Processing Flow

```
Input: USDM with activities from Stages 1-3
                    ↓
┌─────────────────────────────────────────────────────────────┐
│  1. Extract Activities with Potential Alternatives           │
│     - Scan all activity names for "/" or "or" patterns       │
│     - Exclude known timing patterns (BI/EOI, pre/post-dose)  │
│     - Build: {activity_id: activity_text}                    │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│  2. Check Cache for Each Activity                            │
│     - Cache key: md5(activity_text.lower().strip())          │
│     - Include model version in key for invalidation          │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│  3. LLM Batch Analysis (Uncached Only)                       │
│     - Send ALL uncached activities to LLM in one call        │
│     - LLM returns: isAlternative, alternativeType,           │
│       alternatives[], recommendedResolution, confidence      │
│     - Gemini primary, Azure fallback                         │
│     - Cache all LLM results                                  │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│  4. Validate with Pattern Registry                           │
│     - Cross-check LLM decisions against known patterns       │
│     - Flag discrepancies for review                          │
│     - Library is validation, NOT primary routing             │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│  5. Apply Resolution Based on Type & Confidence              │
│                                                               │
│  If MUTUALLY_EXCLUSIVE + confidence ≥ 0.90:                  │
│    → Create separate Activity for each alternative           │
│    → Create SAIs for each at same encounters                 │
│    → Create mutually exclusive Conditions                    │
│    → Link via ConditionAssignments                           │
│                                                               │
│  If DISCRETIONARY + confidence ≥ 0.90:                       │
│    → Create ScheduledDecisionInstance                        │
│    → Mark as VISIT_OPTIONAL condition                        │
│                                                               │
│  If CONDITIONAL + confidence ≥ 0.90:                         │
│    → Link to existing Condition (from Stage 6)               │
│    → Or create new Condition if needed                       │
│                                                               │
│  If confidence < threshold:                                   │
│    → Create HumanReviewItem with options                     │
│    → Preserve original activity unchanged                    │
└─────────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────┐
│  6. Update USDM Structure                                    │
│     - Remove original merged activities (if expanded)        │
│     - Insert expanded activities at same position            │
│     - Update SAI references                                  │
│     - Add new Conditions and ConditionAssignments            │
│     - Preserve all provenance metadata                       │
└─────────────────────────────────────────────────────────────┘
                    ↓
Output: USDM with resolved alternatives + Stage4Result
```

---

## 5. Data Models

### AlternativeType Enum

```python
class AlternativeType(str, Enum):
    """Types of alternative patterns in SOA tables."""
    MUTUALLY_EXCLUSIVE = "mutually_exclusive"  # One or the other
    DISCRETIONARY = "discretionary"            # Investigator choice
    CONDITIONAL = "conditional"                # Based on patient/clinical state
    PREFERRED_WITH_FALLBACK = "preferred_with_fallback"  # Preference order
    UNCERTAIN = "uncertain"                    # Unclear, needs review
```

### AlternativeDecision

```python
@dataclass
class AlternativeDecision:
    """LLM decision for an alternative choice point."""
    activity_id: str
    activity_name: str
    is_alternative: bool
    alternative_type: Optional[AlternativeType] = None
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    # Each alternative: {name, confidence, rationale, cdiscDomain?, order?}
    recommended_resolution: str = "keep"  # "expand", "condition", "decision", "keep", "review"
    confidence: float = 1.0
    rationale: Optional[str] = None
    source: str = "llm"  # "llm", "cache", "pattern"
    requires_human_review: bool = False
    review_reason: Optional[str] = None
    cached_at: Optional[str] = None
```

### AlternativeExpansion

```python
@dataclass
class AlternativeExpansion:
    """Result of expanding an alternative into separate entities."""
    id: str
    original_activity_id: str
    original_activity_name: str
    expanded_activities: List[Dict[str, Any]]  # New activity objects
    expanded_sais: List[Dict[str, Any]]        # New SAI objects
    conditions_created: List[Dict[str, Any]]    # New Condition objects
    assignments_created: List[Dict[str, Any]]   # New ConditionAssignment objects
    decision_instances: List[Dict[str, Any]]    # ScheduledDecisionInstance (if any)
    confidence: float = 1.0
    alternative_type: AlternativeType = AlternativeType.MUTUALLY_EXCLUSIVE
    provenance: Optional[Dict[str, Any]] = None
```

### Stage4Result

```python
@dataclass
class Stage4Result:
    """Result of alternative resolution stage."""
    expansions: List[AlternativeExpansion] = field(default_factory=list)
    decisions: Dict[str, AlternativeDecision] = field(default_factory=dict)
    review_items: List[HumanReviewItem] = field(default_factory=list)

    # Metrics
    activities_analyzed: int = 0
    alternatives_detected: int = 0
    activities_expanded: int = 0
    sais_created: int = 0
    conditions_created: int = 0
    auto_applied: int = 0
    needs_review: int = 0
    cache_hits: int = 0
    llm_calls: int = 0
    validation_discrepancies: int = 0
```

---

## 6. USDM Output Structure

### Before (Merged Alternative)

```json
{
  "activities": [
    {
      "id": "ACT-001",
      "name": "CT scan or MRI",
      "instanceType": "Activity"
    }
  ],
  "scheduledActivityInstances": [
    {
      "id": "SAI-001",
      "activityId": "ACT-001",
      "scheduledInstanceEncounterId": "ENC-001"
    }
  ]
}
```

### After (Resolved Mutually Exclusive)

```json
{
  "activities": [
    {
      "id": "ACT-001-A",
      "name": "CT scan",
      "instanceType": "Activity",
      "_alternativeResolution": {
        "originalActivityId": "ACT-001",
        "originalActivityName": "CT scan or MRI",
        "alternativeType": "mutually_exclusive",
        "alternativeIndex": 1,
        "alternativeCount": 2,
        "confidence": 0.95,
        "stage": "Stage4AlternativeResolution",
        "model": "gemini-2.0-flash-exp",
        "timestamp": "2025-12-06T..."
      }
    },
    {
      "id": "ACT-001-B",
      "name": "MRI",
      "instanceType": "Activity",
      "_alternativeResolution": {
        "originalActivityId": "ACT-001",
        "originalActivityName": "CT scan or MRI",
        "alternativeType": "mutually_exclusive",
        "alternativeIndex": 2,
        "alternativeCount": 2,
        "confidence": 0.95,
        "stage": "Stage4AlternativeResolution",
        "model": "gemini-2.0-flash-exp",
        "timestamp": "2025-12-06T..."
      }
    }
  ],
  "conditions": [
    {
      "id": "COND-ALT-001-A",
      "instanceType": "Condition",
      "name": "CT scan selected",
      "text": "CT scan imaging modality selected for this subject",
      "conditionType": {
        "code": "C98772",
        "decode": "Alternative Selection",
        "instanceType": "Code"
      }
    },
    {
      "id": "COND-ALT-001-B",
      "instanceType": "Condition",
      "name": "MRI selected",
      "text": "MRI imaging modality selected for this subject",
      "conditionType": {
        "code": "C98772",
        "decode": "Alternative Selection",
        "instanceType": "Code"
      }
    }
  ],
  "conditionAssignments": [
    {
      "id": "CA-ALT-001",
      "instanceType": "ConditionAssignment",
      "conditionId": "COND-ALT-001-A",
      "conditionTargetId": "SAI-001-A"
    },
    {
      "id": "CA-ALT-002",
      "instanceType": "ConditionAssignment",
      "conditionId": "COND-ALT-001-B",
      "conditionTargetId": "SAI-001-B"
    }
  ],
  "scheduledActivityInstances": [
    {
      "id": "SAI-001-A",
      "activityId": "ACT-001-A",
      "scheduledInstanceEncounterId": "ENC-001",
      "defaultConditionId": "COND-ALT-001-A",
      "_alternativeResolution": {
        "originalSaiId": "SAI-001",
        "alternativeName": "CT scan"
      }
    },
    {
      "id": "SAI-001-B",
      "activityId": "ACT-001-B",
      "scheduledInstanceEncounterId": "ENC-001",
      "defaultConditionId": "COND-ALT-001-B",
      "_alternativeResolution": {
        "originalSaiId": "SAI-001",
        "alternativeName": "MRI"
      }
    }
  ]
}
```

---

## 7. Configuration Files

### config/alternative_patterns.json

```json
{
  "_metadata": {
    "description": "Alternative resolution validation patterns for Stage 4",
    "purpose": "Cross-check LLM decisions - NOT for primary routing",
    "version": "1.0.0"
  },
  "timing_patterns": [
    "BI/EOI", "BI / EOI",
    "pre-dose/post-dose", "predose/postdose",
    "trough/peak", "fasting/fed",
    "0h, 2h, 4h", "30min, 60min"
  ],
  "non_alternative_patterns": [
    "and", "both", "all of", "at all visits",
    "see section", "refer to", "per protocol",
    "as per", "defined in"
  ],
  "known_alternatives": {
    "CT / MRI": {
      "alternatives": ["CT scan", "MRI"],
      "type": "mutually_exclusive",
      "domain": "MI"
    },
    "CT or MRI": {
      "alternatives": ["CT scan", "MRI"],
      "type": "mutually_exclusive",
      "domain": "MI"
    },
    "blood / urine sample": {
      "alternatives": ["Blood sample", "Urine sample"],
      "type": "mutually_exclusive",
      "domain": "BS"
    },
    "serum or urine pregnancy test": {
      "alternatives": ["Serum pregnancy test", "Urine pregnancy test"],
      "type": "mutually_exclusive",
      "domain": "LB"
    }
  },
  "alternative_type_indicators": {
    "mutually_exclusive": ["or", "/", "either", "one of"],
    "discretionary": ["if indicated", "at discretion", "as needed", "optional"],
    "conditional": ["if", "for", "when", "unless"],
    "preferred_with_fallback": ["preferred", "if unavailable", "alternatively"]
  }
}
```

### config/alternative_codes.json

```json
{
  "_metadata": {
    "description": "CDISC codes for alternative resolution conditions",
    "source": "NCI EVS Thesaurus",
    "version": "1.0.0"
  },
  "alternative_condition_type": {
    "code": "C98772",
    "decode": "Alternative Selection Condition",
    "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
    "codeSystemVersion": "24.12"
  },
  "mutually_exclusive_marker": {
    "code": "C98773",
    "decode": "Mutually Exclusive Alternative",
    "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl"
  },
  "discretionary_marker": {
    "code": "C98774",
    "decode": "Investigator Discretion Alternative",
    "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl"
  }
}
```

---

## 8. LLM Prompt Design

### prompts/alternative_resolution.txt

```
You are a clinical trial protocol expert specializing in Schedule of Assessments (SOA) interpretation.

## Task

Analyze each activity to determine if it contains alternative choice points that need resolution.

## Context

Clinical protocols often present activities with alternatives:
- "CT scan or MRI" → Imaging modality choice
- "Blood / urine sample" → Specimen type choice
- "ECG (or Holter if indicated)" → Conditional alternative

Your task is to:
1. Identify if the activity contains a genuine alternative
2. Classify the alternative type
3. Extract the individual options
4. Recommend how to resolve it

## Activities to Analyze

{activities_json}

## Alternative Types

| Type | Description | Example |
|------|-------------|---------|
| MUTUALLY_EXCLUSIVE | Only ONE option performed | "CT or MRI" |
| DISCRETIONARY | Site/investigator chooses | "Labs if clinically indicated" |
| CONDITIONAL | Based on patient state | "Pregnancy test (females only)" |
| PREFERRED_WITH_FALLBACK | One preferred, other if unavailable | "CT preferred, MRI if unavailable" |

## What is NOT an Alternative

- **Timing patterns**: "BI/EOI", "pre-dose/post-dose" (Stage 7 handles these)
- **Both required**: "Test A and Test B"
- **References**: "Test A / see Section X"
- **Formatting**: Slashes used for formatting, not choice

## Response Format

Return a JSON object where each key is the activity ID:

```json
{{
  "ACT-001": {{
    "activityName": "CT scan or MRI",
    "isAlternative": true,
    "alternativeType": "MUTUALLY_EXCLUSIVE",
    "alternatives": [
      {{"name": "CT scan", "order": 1, "confidence": 0.95}},
      {{"name": "MRI", "order": 2, "confidence": 0.95}}
    ],
    "recommendedResolution": "expand",
    "confidence": 0.95,
    "rationale": "Explicit OR between two imaging modalities - mutually exclusive choice"
  }},
  "ACT-002": {{
    "activityName": "Complete blood count and chemistry",
    "isAlternative": false,
    "alternativeType": null,
    "alternatives": [],
    "recommendedResolution": "keep",
    "confidence": 1.0,
    "rationale": "Both tests required - 'and' indicates not an alternative"
  }},
  "ACT-003": {{
    "activityName": "BI/EOI",
    "isAlternative": false,
    "alternativeType": null,
    "alternatives": [],
    "recommendedResolution": "keep",
    "confidence": 1.0,
    "rationale": "Timing pattern (Before Infusion/End of Infusion) - handled by Stage 7"
  }}
}}
```

## Resolution Recommendations

| Resolution | When to Use |
|------------|-------------|
| expand | Mutually exclusive alternatives with high confidence |
| condition | Alternatives with clear conditional logic |
| decision | Discretionary alternatives requiring clinical judgment |
| keep | Not an alternative OR timing pattern |
| review | Ambiguous, low confidence, or complex scenario |

## Confidence Scoring

- **0.95-1.0**: Clear pattern, explicit markers ("or", "/")
- **0.85-0.94**: Standard pattern, context confirms
- **0.70-0.84**: Possible alternative, some ambiguity
- **<0.70**: Uncertain, recommend review

## Critical Requirements

1. Every activity in input MUST have an entry in output
2. Return ONLY valid JSON - no markdown, no extra text
3. NEVER mark timing patterns (BI/EOI, pre/post-dose) as alternatives
4. NEVER mark "A and B" as alternatives (both required)
5. For ambiguous cases, set recommendedResolution: "review"

Analyze ALL {activity_count} activities now.
```

---

## 9. Integration with Other Stages

### Relationship to Stage 6 (Conditional Expansion)

Stage 4 may create Conditions for conditional alternatives. These integrate with Stage 6:
- Stage 4: Creates `COND-ALT-*` conditions for alternative selection
- Stage 6: Creates `COND-*` conditions from footnotes
- Both use same Condition/ConditionAssignment structure

### Relationship to Stage 7 (Timing Distribution)

Stage 4 must NOT expand timing patterns:
- "BI/EOI" → Skip (Stage 7 handles)
- "pre-dose/post-dose" → Skip (Stage 7 handles)
- "CT / MRI" → Expand (Stage 4 handles)

Pattern registry includes `timing_patterns` list to filter these.

### Relationship to Stage 12 (USDM Compliance)

Stage 12 validates Stage 4 output:
- Referential integrity of new activity/SAI IDs
- Condition/ConditionAssignment linkages
- Code object compliance

---

## 10. Implementation Tasks

| # | Task | Estimated Time |
|---|------|----------------|
| 1 | Create `models/alternative_expansion.py` with dataclasses | 1.5h |
| 2 | Create `config/alternative_patterns.json` | 30m |
| 3 | Create `config/alternative_codes.json` | 30m |
| 4 | Create `prompts/alternative_resolution.txt` | 45m |
| 5 | Implement `AlternativePatternRegistry` class | 45m |
| 6 | Implement `AlternativeResolver` core class | 2h |
| 7 | Implement LLM batch analysis with caching | 1h |
| 8 | Implement expansion logic for each alternative type | 1.5h |
| 9 | Implement SAI duplication and condition linkage | 1h |
| 10 | Implement `apply_resolutions_to_usdm()` | 1h |
| 11 | Add Azure OpenAI fallback | 30m |
| 12 | Update `interpretation/__init__.py` exports | 15m |
| 13 | Update `models/__init__.py` exports | 15m |
| 14 | Create unit tests (25+ test cases) | 2h |
| 15 | Create integration tests (Stage 4→6→12) | 1h |

**Total Estimated Time**: ~14 hours

---

## 11. Test Cases

### Unit Tests

1. **AlternativeType enum values**
2. **AlternativeDecision creation and serialization**
3. **AlternativeExpansion creation**
4. **Stage4Result metrics tracking**
5. **PatternRegistry: is_timing_pattern()**
6. **PatternRegistry: is_non_alternative()**
7. **PatternRegistry: get_known_alternatives()**
8. **Resolver: _extract_candidate_activities()**
9. **Resolver: _should_analyze_activity()**
10. **Resolver: _generate_activity_id()**
11. **Resolver: _generate_sai_id()**
12. **Resolver: _create_alternative_condition()**
13. **Resolver: _expand_mutually_exclusive()**
14. **Resolver: _create_discretionary_decision()**
15. **Cache key generation**
16. **LLM response parsing**
17. **Validation discrepancy detection**
18. **Provenance metadata structure**

### Integration Tests

1. **Stage 4 alone: simple OR alternative**
2. **Stage 4 alone: slash notation**
3. **Stage 4 alone: conditional alternative**
4. **Stage 4 alone: timing pattern (should skip)**
5. **Stage 4 alone: "and" pattern (should skip)**
6. **Stage 4 → Stage 12: USDM compliance**
7. **Stage 4 → Stage 6 → Stage 12: condition integration**
8. **Full pipeline: realistic protocol**

---

## 12. Validation Checklist

Before marking Stage 4 complete, verify:

- [ ] All alternative types handled (MUTUALLY_EXCLUSIVE, DISCRETIONARY, CONDITIONAL, PREFERRED_WITH_FALLBACK)
- [ ] Timing patterns correctly filtered out (BI/EOI, pre/post-dose)
- [ ] "And" patterns correctly NOT expanded
- [ ] New activities have proper IDs (ACT-XXX-A, ACT-XXX-B)
- [ ] New SAIs reference correct expanded activities
- [ ] Conditions created with USDM 4.0 Code objects
- [ ] ConditionAssignments link SAIs to Conditions
- [ ] SAI.defaultConditionId set correctly
- [ ] Full provenance in `_alternativeResolution` metadata
- [ ] Two-level caching works (memory + disk)
- [ ] Azure OpenAI fallback functional
- [ ] All unit tests pass
- [ ] Integration tests pass
- [ ] Stage 12 compliance check passes

---

## 13. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Over-expansion (false positives) | Strict pattern filtering; conservative confidence thresholds |
| Under-expansion (missed alternatives) | LLM-first approach catches context-dependent cases |
| Timing pattern confusion | Explicit timing_patterns list in config |
| Broken referential integrity | Validate all IDs before applying to USDM |
| Performance with many activities | Batch processing; caching; max 20 per LLM call |

---

## 14. Files to Create

| File | Purpose |
|------|---------|
| `models/alternative_expansion.py` | Data models |
| `config/alternative_patterns.json` | Pattern registry |
| `config/alternative_codes.json` | CDISC codes |
| `prompts/alternative_resolution.txt` | LLM prompt |
| `interpretation/stage4_alternative_resolution.py` | Main implementation |
| `tests/test_stage4_alternative_resolution.py` | Unit tests |
| `tests/test_stage4_integration.py` | Integration tests |

---

**Ready for Implementation**

This design follows the established patterns from Stages 6, 7, and 8:
- LLM-first architecture
- Batch processing with caching
- Confidence-based classification
- USDM 4.0 compliant output
- Full provenance tracking
- Pattern registry for validation (not routing)
