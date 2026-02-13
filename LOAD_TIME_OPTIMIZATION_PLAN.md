# SOA Analysis Page - Load Time Optimization Plan

## Current State

**Total Load Time:** 5-15 seconds

| Operation | Current Time | Bottleneck |
|-----------|--------------|------------|
| Check job status | 100-300ms | Sequential API call |
| Fetch SOA results | 1-5s | Large JSONB from PostgreSQL |
| Transform data (JS) | 100-500ms | CPU-bound in browser |
| Fetch PDF | 2-10s | Large binary from PostgreSQL |
| Render PDF | 200-800ms | Browser rendering |

**Root Causes:**
1. Sequential operations (each waits for previous)
2. No compression on responses
3. Entire PDF loaded before streaming to browser
4. PDF viewer JS loads before needed

---

## Optimization Plan (No Local Caching)

### Priority 1: GZip Compression

**Impact:** 30-50% faster data transfer
**Effort:** Very Low (1 line of code)
**File:** `backend_vNext/app/main.py`

**Implementation:**
```python
from fastapi.middleware.gzip import GZipMiddleware

# Add after app = FastAPI(...)
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

**What it does:**
- Compresses all responses > 1KB before sending
- Browser decompresses automatically
- 10MB response → ~4MB transfer
- No storage, just compression during transfer

---

### Priority 2: Parallel Loading (Frontend)

**Impact:** Saves 1-3 seconds
**Effort:** Low
**File:** `frontend-vNext/client/src/pages/SOAAnalysisPage.tsx`

**Current Code (Sequential):**
```typescript
// In startSOAExtraction() - around line 1631
const latestJob = await api.soa.getLatestJob(studyId);
if (latestJob && latestJob.status === 'completed') {
  const results = await api.soa.getResults(latestJob.id);
  await loadSOAResults(results);
}
// PDF only starts loading after this completes
```

**Optimized Code (Parallel):**
```typescript
// Create a ref to track if PDF should start loading
const [shouldLoadPdf, setShouldLoadPdf] = useState(false);

// In useEffect, set PDF loading immediately
useEffect(() => {
  if (studyId) {
    setShouldLoadPdf(true);  // PDF starts loading immediately
    startSOAExtraction();     // Data fetching starts in parallel
  }
}, [studyId]);

// In JSX, PDF Document loads as soon as shouldLoadPdf is true
// instead of waiting for extraction data
```

**Alternative - Promise.all approach:**
```typescript
const startSOAExtraction = async () => {
  if (!studyId) return;

  try {
    // Start both operations in parallel
    const jobPromise = api.soa.getLatestJob(studyId);

    // PDF component is already rendering and loading due to pdfUrl being set
    // So we just need to ensure data fetching doesn't block

    const latestJob = await jobPromise;

    if (latestJob?.status === 'completed') {
      const results = await api.soa.getResults(latestJob.id);
      await loadSOAResults(results);
    }
  } catch (error) {
    console.error('Error:', error);
  }
};
```

---

### Priority 3: Streaming PDF Response (Backend)

**Impact:** Progressive loading, better UX for large PDFs
**Effort:** Medium
**File:** `backend_vNext/app/routers/protocol.py`

**Current Code:**
```python
@router.get("/protocols/{protocol_id}/pdf/annotated")
async def get_annotated_pdf(protocol_id: str, db: Session = Depends(get_db)):
    # Loads entire PDF into memory first
    result = db.query(ExtractionOutput).filter(...).first()
    return Response(
        content=result.file_data,  # Entire file in memory
        media_type="application/pdf"
    )
```

**Optimized Code:**
```python
from fastapi.responses import StreamingResponse
import io

@router.get("/protocols/{protocol_id}/pdf/annotated")
async def get_annotated_pdf(protocol_id: str, db: Session = Depends(get_db)):
    result = db.query(ExtractionOutput).filter(...).first()

    if not result or not result.file_data:
        raise HTTPException(status_code=404, detail="PDF not found")

    # Stream the PDF in chunks
    def iter_file():
        chunk_size = 64 * 1024  # 64KB chunks
        file_like = io.BytesIO(result.file_data)
        while chunk := file_like.read(chunk_size):
            yield chunk

    return StreamingResponse(
        iter_file(),
        media_type="application/pdf",
        headers={
            "Content-Length": str(len(result.file_data)),
            "Content-Disposition": f"inline; filename=protocol_{protocol_id}.pdf"
        }
    )
```

**What it does:**
- Sends PDF in 64KB chunks
- Browser can start rendering before full download
- Reduces memory usage on server

---

### Priority 4: Lazy Load PDF Viewer (Frontend)

**Impact:** Saves 500ms-1s initial load
**Effort:** Low
**File:** `frontend-vNext/client/src/pages/SOAAnalysisPage.tsx`

**Current Code:**
```typescript
import { Document, Page, pdfjs } from 'react-pdf';
// PDF viewer JS loads immediately with page
```

**Optimized Code:**
```typescript
import { lazy, Suspense } from 'react';

// Lazy load the PDF components
const PDFDocument = lazy(() =>
  import('react-pdf').then(module => ({ default: module.Document }))
);
const PDFPage = lazy(() =>
  import('react-pdf').then(module => ({ default: module.Page }))
);

// In JSX:
<Suspense fallback={<div className="flex items-center justify-center h-full">
  <Loader2 className="w-8 h-8 animate-spin" />
  <span className="ml-2">Loading PDF viewer...</span>
</div>}>
  <PDFDocument file={pdfUrl} onLoadSuccess={onDocumentLoadSuccess}>
    <PDFPage pageNumber={pageNumber} scale={scale} />
  </PDFDocument>
</Suspense>
```

**What it does:**
- PDF viewer JavaScript (~500KB) loads in background
- Main page becomes interactive faster
- PDF appears when both JS and PDF file are ready

---

### Priority 5: Database Indexes (Backend)

**Impact:** Faster queries (10-50ms improvement)
**Effort:** Low
**File:** New migration or `backend_vNext/init_schema.py`

**SQL to add:**
```sql
-- Check if these indexes exist, add if missing
CREATE INDEX IF NOT EXISTS idx_soa_jobs_protocol_status
  ON backend_vnext.soa_jobs(protocol_id, status);

CREATE INDEX IF NOT EXISTS idx_soa_jobs_protocol_created
  ON backend_vnext.soa_jobs(protocol_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_extraction_outputs_protocol_type
  ON backend_vnext.extraction_outputs(protocol_id, file_type);

CREATE INDEX IF NOT EXISTS idx_protocols_id
  ON backend_vnext.protocols(id);
```

**What it does:**
- Speeds up "find latest job for protocol" query
- Speeds up "find annotated PDF" query
- Minimal impact but good practice

---

### Priority 6: Paginate SOA Results (Optional - For Large Protocols)

**Impact:** High for protocols with 100+ activities
**Effort:** Medium-High
**Files:**
- `backend_vNext/app/routers/soa.py`
- `frontend-vNext/client/src/pages/SOAAnalysisPage.tsx`
- `frontend-vNext/client/src/lib/api.ts`

**Backend Changes:**
```python
@router.get("/soa/jobs/{job_id}/results")
async def get_soa_results(
    job_id: str,
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    job = db.query(SOAJob).filter(SOAJob.id == job_id).first()

    # Return summary immediately, paginate activities
    return {
        "job_id": job.id,
        "status": job.status,
        "summary": {
            "totalVisits": len(job.usdm_data.get("visits", [])),
            "totalActivities": len(job.usdm_data.get("activities", [])),
        },
        "visits": job.usdm_data.get("visits", []),  # Usually small
        "activities": paginate(job.usdm_data.get("activities", []), page, limit),
        "hasMore": has_more_pages(job.usdm_data.get("activities", []), page, limit),
        "quality_report": job.quality_report,
    }
```

**Frontend Changes:**
```typescript
// Load more activities as user scrolls
const [activities, setActivities] = useState([]);
const [page, setPage] = useState(1);
const [hasMore, setHasMore] = useState(true);

const loadMoreActivities = async () => {
  if (!hasMore) return;
  const results = await api.soa.getResults(jobId, page + 1);
  setActivities(prev => [...prev, ...results.activities]);
  setPage(p => p + 1);
  setHasMore(results.hasMore);
};

// Use intersection observer for infinite scroll
```

---

## Implementation Order

| Step | Optimization | Time to Implement | Expected Improvement |
|------|--------------|-------------------|---------------------|
| 1 | GZip Compression | 5 minutes | 30-50% faster transfer |
| 2 | Parallel Loading | 30 minutes | 1-3s saved |
| 3 | Lazy Load PDF Viewer | 20 minutes | 0.5-1s saved |
| 4 | Streaming PDF | 1 hour | Better UX for large PDFs |
| 5 | Database Indexes | 15 minutes | 10-50ms per query |
| 6 | Pagination | 2-3 hours | Significant for large protocols |

---

## Expected Results

**Before Optimization:**
- First load: 5-15 seconds
- Repeat load: 5-15 seconds (same)

**After Optimization (Steps 1-4):**
- First load: 3-8 seconds
- Perceived performance: Much faster (skeleton + parallel)

**Key Metrics to Measure:**
1. Time to First Contentful Paint (FCP)
2. Time to Interactive (TTI)
3. Total page load time
4. PDF render start time

---

## Files to Modify Summary

| File | Changes |
|------|---------|
| `backend_vNext/app/main.py` | Add GZip middleware |
| `backend_vNext/app/routers/protocol.py` | Streaming PDF response |
| `frontend-vNext/client/src/pages/SOAAnalysisPage.tsx` | Parallel loading, lazy PDF viewer |
| `backend_vNext/init_schema.py` or migration | Database indexes |

---

## Notes

- No local caching implemented (per requirement)
- All optimizations work on every page load
- No data stored in browser cache or memory
- Focus is on reducing database and network time
