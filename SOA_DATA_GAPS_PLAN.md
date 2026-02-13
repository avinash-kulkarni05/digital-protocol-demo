# SOA Analysis Page - Data Gaps Implementation Plan

## Overview

The backend extracts ~100% of SOA data, but the frontend only displays ~60%. This plan covers adding the missing data displays.

---

## Current Display Status

### What IS Displayed:

| Area | Data Shown |
|------|------------|
| **Summary Cards** | Visits count, Activities count, SAIs count, Confidence % |
| **Grid Tab** | X/O markers, footnote superscripts |
| **Visits Tab** | Visit names, day numbers, timing windows |
| **Footnotes Tab** | Marker, full text, category, EDC impact |

### What IS NOT Displayed (The Gaps):

| Gap | Data Available In | Priority |
|-----|-------------------|----------|
| Footnotes count | `extractionSummary.totalFootnotes` | High |
| Grid legend | `matrix.legend` | High |
| CDISC domain badges | `activities[].category` | High |
| Quality report (5D scores) | `quality_report` | High |
| Footnote-to-element mapping | `footnotes[].appliesTo` | Medium |
| Provenance page numbers | `provenance.pageNumber` | Medium |
| Visit type classification | `visits[].visitType` | Medium |
| Table metadata | `tableId`, `tableName`, `pageRange` | Low |

---

## Implementation Plan

### Gap 1: Add Footnotes Count to Summary Cards

**File:** `frontend-vNext/client/src/pages/SOAAnalysisPage.tsx`

**Current Code (around line 1720-1760):**
```tsx
{/* Summary Cards - currently 4 cards */}
<SummaryCard icon={Calendar} label="Visits" value={extraction.tables[0]?.visits?.length || 0} />
<SummaryCard icon={ListChecks} label="Activities" value={extraction.tables[0]?.activities?.length || 0} />
<SummaryCard icon={Grid3X3} label="SAIs" value={totalSAIs} />
<SummaryCard icon={CheckCircle2} label="Confidence" value={`${confidence}%`} />
```

**Add 5th Card:**
```tsx
<SummaryCard
  icon={FileText}
  label="Footnotes"
  value={extraction.tables[0]?.footnotes?.length || 0}
/>
```

---

### Gap 2: Add Grid Legend Below SOA Grid

**File:** `frontend-vNext/client/src/pages/SOAAnalysisPage.tsx`

**Add after SOATableGrid component (around line 1800):**
```tsx
{/* Grid Legend */}
<div className="flex items-center gap-6 mt-4 px-4 py-2 bg-gray-50 rounded-lg text-sm text-gray-600">
  <div className="flex items-center gap-2">
    <span className="font-mono font-bold text-green-600">X</span>
    <span>Required</span>
  </div>
  <div className="flex items-center gap-2">
    <span className="font-mono font-bold text-blue-600">O</span>
    <span>Optional / Conditional</span>
  </div>
  <div className="flex items-center gap-2">
    <span className="font-mono text-gray-400">-</span>
    <span>Not Scheduled</span>
  </div>
</div>
```

---

### Gap 3: Add CDISC Domain Badges to Activities

**File:** `frontend-vNext/client/src/pages/SOAAnalysisPage.tsx`

**Find activity row rendering (SOATableGrid or inline):**

**Current:** Shows activity name only
```tsx
<span>{activity.name}</span>
```

**Add domain badge:**
```tsx
<div className="flex items-center gap-2">
  <span>{activity.name}</span>
  {activity.category && (
    <Badge
      variant="outline"
      className={cn(
        "text-xs px-1.5 py-0.5",
        activity.category === 'VS' && "bg-red-50 text-red-700 border-red-200",
        activity.category === 'LB' && "bg-blue-50 text-blue-700 border-blue-200",
        activity.category === 'EG' && "bg-purple-50 text-purple-700 border-purple-200",
        activity.category === 'PE' && "bg-green-50 text-green-700 border-green-200",
        activity.category === 'DA' && "bg-yellow-50 text-yellow-700 border-yellow-200",
      )}
    >
      {activity.category}
    </Badge>
  )}
</div>
```

**Domain color mapping:**
| Domain | Color | Description |
|--------|-------|-------------|
| VS | Red | Vital Signs |
| LB | Blue | Laboratory |
| EG | Purple | ECG |
| PE | Green | Physical Exam |
| DA | Yellow | Drug Administration |
| AE | Orange | Adverse Events |
| CM | Teal | Concomitant Meds |

---

### Gap 4: Add Quality Report Panel

**File:** `frontend-vNext/client/src/pages/SOAAnalysisPage.tsx`

**Add collapsible quality panel below summary cards:**
```tsx
{/* Quality Report Panel */}
{extraction.qualityReport && (
  <Collapsible className="mt-4">
    <CollapsibleTrigger className="flex items-center gap-2 text-sm font-medium text-gray-700 hover:text-gray-900">
      <ChevronDown className="w-4 h-4" />
      Quality Report ({extraction.qualityReport.overallScore}%)
    </CollapsibleTrigger>
    <CollapsibleContent className="mt-2 p-4 bg-gray-50 rounded-lg">
      <div className="space-y-3">
        {/* Accuracy */}
        <div className="flex items-center gap-3">
          <span className="w-32 text-sm text-gray-600">Accuracy</span>
          <Progress
            value={extraction.qualityReport.accuracy}
            className="flex-1 h-2"
          />
          <span className="w-12 text-sm font-medium">
            {extraction.qualityReport.accuracy}%
          </span>
        </div>

        {/* Completeness */}
        <div className="flex items-center gap-3">
          <span className="w-32 text-sm text-gray-600">Completeness</span>
          <Progress
            value={extraction.qualityReport.completeness}
            className="flex-1 h-2"
          />
          <span className="w-12 text-sm font-medium">
            {extraction.qualityReport.completeness}%
          </span>
        </div>

        {/* USDM Adherence */}
        <div className="flex items-center gap-3">
          <span className="w-32 text-sm text-gray-600">USDM Adherence</span>
          <Progress
            value={extraction.qualityReport.usdmAdherence}
            className="flex-1 h-2"
          />
          <span className="w-12 text-sm font-medium">
            {extraction.qualityReport.usdmAdherence}%
          </span>
        </div>

        {/* Provenance */}
        <div className="flex items-center gap-3">
          <span className="w-32 text-sm text-gray-600">Provenance</span>
          <Progress
            value={extraction.qualityReport.provenance}
            className="flex-1 h-2"
          />
          <span className="w-12 text-sm font-medium">
            {extraction.qualityReport.provenance}%
          </span>
        </div>

        {/* Terminology */}
        <div className="flex items-center gap-3">
          <span className="w-32 text-sm text-gray-600">Terminology</span>
          <Progress
            value={extraction.qualityReport.terminology}
            className="flex-1 h-2"
          />
          <span className="w-12 text-sm font-medium">
            {extraction.qualityReport.terminology}%
          </span>
        </div>
      </div>
    </CollapsibleContent>
  </Collapsible>
)}
```

**Also update loadSOAResults to include quality_report:**
```typescript
// In loadSOAResults function
const loadSOAResults = async (results: any) => {
  // ... existing code ...

  // Add quality report to extraction state
  setExtraction({
    ...transformedData,
    qualityReport: results.quality_report ? {
      overallScore: results.quality_report.overall_score || 0,
      accuracy: results.quality_report.dimensions?.accuracy?.score || 0,
      completeness: results.quality_report.dimensions?.completeness?.score || 0,
      usdmAdherence: results.quality_report.dimensions?.usdm_adherence?.score || 0,
      provenance: results.quality_report.dimensions?.provenance?.score || 0,
      terminology: results.quality_report.dimensions?.terminology?.score || 0,
    } : null
  });
};
```

---

### Gap 5: Footnote-to-Element Mapping

**File:** `frontend-vNext/client/src/pages/SOAAnalysisPage.tsx`

**In Footnotes tab, expand each footnote to show what it applies to:**
```tsx
{footnotes.map((footnote) => (
  <div key={footnote.id} className="p-4 border rounded-lg">
    {/* Existing footnote display */}
    <div className="flex items-start gap-2">
      <Badge variant="outline">{footnote.marker}</Badge>
      <p className="text-sm">{footnote.text}</p>
    </div>

    {/* NEW: Show what this footnote applies to */}
    {footnote.appliesTo && footnote.appliesTo.length > 0 && (
      <div className="mt-2 pt-2 border-t">
        <span className="text-xs text-gray-500">Applies to:</span>
        <div className="flex flex-wrap gap-1 mt-1">
          {footnote.appliesTo.map((ref, idx) => (
            <Badge key={idx} variant="secondary" className="text-xs">
              {ref.visitName || ref.activityName || `Row ${ref.row}, Col ${ref.col}`}
            </Badge>
          ))}
        </div>
      </div>
    )}
  </div>
))}
```

---

### Gap 6: Visit Type Badges

**File:** `frontend-vNext/client/src/pages/SOAAnalysisPage.tsx`

**In Visits timeline, add explicit type badge:**
```tsx
{visits.map((visit) => (
  <div key={visit.id} className="p-3 border rounded-lg">
    <div className="flex items-center gap-2">
      <span className="font-medium">{visit.name}</span>
      {visit.visitType && (
        <Badge
          variant="outline"
          className={cn(
            "text-xs",
            visit.visitType === 'Screening' && "bg-amber-50 text-amber-700",
            visit.visitType === 'Treatment' && "bg-blue-50 text-blue-700",
            visit.visitType === 'Follow-up' && "bg-green-50 text-green-700",
            visit.visitType === 'EOT' && "bg-red-50 text-red-700",
          )}
        >
          {visit.visitType}
        </Badge>
      )}
    </div>
    <span className="text-sm text-gray-500">Day {visit.day}</span>
  </div>
))}
```

---

## Implementation Order

| Step | Gap | Effort | Impact |
|------|-----|--------|--------|
| 1 | Footnotes count card | 5 min | Shows total footnotes |
| 2 | Grid legend | 10 min | Users understand X/O meaning |
| 3 | Domain badges | 30 min | Shows CDISC categorization |
| 4 | Quality report panel | 45 min | Shows extraction quality |
| 5 | Footnote mapping | 30 min | Shows footnote relationships |
| 6 | Visit type badges | 15 min | Explicit visit classification |

**Total estimated time:** ~2-3 hours

---

## Files to Modify

| File | Changes |
|------|---------|
| `frontend-vNext/client/src/pages/SOAAnalysisPage.tsx` | All gap implementations |

**No new files needed** - all changes go into the existing SOAAnalysisPage.tsx file.

---

## Data Already Available

All data is returned by the existing API endpoint:

**Endpoint:** `GET /api/v1/soa/jobs/{job_id}/results`

**Response structure:**
```json
{
  "extraction_review": {
    "extractionSummary": {
      "totalVisits": 24,
      "totalActivities": 47,
      "totalSAIs": 263,
      "totalFootnotes": 8,      // ← Gap 1
      "confidence": 94
    },
    "tables": [{
      "matrix": {
        "legend": { "X": "Required", "O": "Optional" }  // ← Gap 2
      },
      "visits": [{
        "name": "Screening",
        "visitType": "Screening",  // ← Gap 6
        "day": -28
      }],
      "activities": [{
        "name": "Vital Signs",
        "category": "VS",          // ← Gap 3
        "cdashDomain": "VS"
      }],
      "footnotes": [{
        "marker": "a",
        "text": "...",
        "appliesTo": [...]         // ← Gap 5
      }]
    }]
  },
  "quality_report": {              // ← Gap 4
    "overall_score": 92,
    "dimensions": {
      "accuracy": { "score": 95 },
      "completeness": { "score": 90 },
      "usdm_adherence": { "score": 88 },
      "provenance": { "score": 96 },
      "terminology": { "score": 91 }
    }
  }
}
```

---

## Notes

- All implementations modify `SOAAnalysisPage.tsx` only
- No backend changes required - data already returned
- No new component files needed (inline additions)
- Test with existing extracted protocols to verify data structure
