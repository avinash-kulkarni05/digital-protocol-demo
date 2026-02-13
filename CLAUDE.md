# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

```bash
# Backend (most common)
cd backend_vNext && source venv/bin/activate
python run.py                              # API server (port 8080)
python scripts/main.py --pdf /path/to.pdf  # Full extraction pipeline

# Frontend
cd frontend-vNext && npm run dev           # Dev server (port 5000)
```

## Project Overview

Clinical trial protocol digitalization system that extracts structured USDM 4.0 compliant JSON from protocol PDFs using LLM-powered extraction pipelines.

**Monorepo Structure:**
- `backend_vNext/` - FastAPI backend (v4.0 architecture) - **Active Development**
- `frontend-vNext/` - React + Express frontend with review UI
- `.archive/` - Legacy pipeline code - **DO NOT USE**

## Essential Commands

### Backend (backend_vNext/)

```bash
cd backend_vNext
source venv/bin/activate  # REQUIRED - always activate first

# API Server
python run.py                              # Start on port 8080

# CLI Extraction
python scripts/main.py --pdf /path/to/protocol.pdf
python scripts/main.py --pdf /path/to/protocol.pdf --no-cache
python scripts/main.py --show-agents

# Database
python init_schema.py                      # Initialize schema

# SOA Extraction (standalone or integrated)
python soa_analyzer/soa_extraction_pipeline.py /path/to/protocol.pdf
python soa_analyzer/soa_extraction_pipeline.py /path/to/protocol.pdf --extraction-outputs /path/to/usdm.json
python soa_analyzer/soa_extraction_pipeline.py /path/to/protocol.pdf --no-interpretation  # Raw extraction only

# Eligibility Extraction (standalone)
python eligibility_analyzer/eligibility_extraction_pipeline.py /path/to/protocol.pdf

# Combine Outputs (main + SOA + eligibility)
python app/services/usdm_combiner.py --main /path/to/usdm_4.0.json --soa /path/to/soa_usdm_draft.json --eligibility /path/to/eligibility.json
```

### Testing

```bash
cd backend_vNext && source venv/bin/activate

# SOA module tests
python -m pytest soa_analyzer/tests/ -v                                    # All SOA tests
python -m pytest soa_analyzer/tests/test_stage7_timing_distribution.py -v  # Single file
python -m pytest soa_analyzer/tests/ -k "test_bi_eoi_expansion" -v         # By name
python -m pytest soa_analyzer/tests/test_stage8_cycle_expansion.py::test_explicit_range_expansion -v  # Single function

# Eligibility module tests
python -m pytest eligibility_analyzer/tests/ -v                            # All eligibility tests
python -m pytest eligibility_analyzer/feasibility/tests/ -v                # Feasibility tests
```

### Frontend (frontend-vNext/)

```bash
cd frontend-vNext
npm run dev          # Dev server (port 5000)
npm run build        # Production build (esbuild + vite)
npm run start        # Production server (port 5000)
npm run check        # TypeScript check
npm run db:push      # Sync Drizzle schema to PostgreSQL
```

## Architecture

### Database-First PDF Storage

**PDFs are stored as binary data in PostgreSQL** (not on filesystem):
- Upload endpoint stores file binary in `protocols.file_data` column (BYTEA)
- Frontend/backend retrieve PDFs via `GET /protocols/{id}/pdf` endpoint
- No filesystem dependencies - fully stateless backend deployment
- Automatic deduplication via SHA-256 hash

### Two-Phase Extraction Pipeline

1. **Pass 1**: Extract values using `prompts/*_pass1_values.txt`
2. **Pass 2**: Add PDF citations using `prompts/*_pass2_provenance.txt`
3. **Post-Processing**: Auto-correct CDISC codes, truncate snippets to 500 chars
4. **Quality Evaluation**: 5D scoring (Accuracy/Completeness/USDM Adherence/Provenance/Terminology)

### Wave-Based Module Execution

Controlled via `config.yaml` (17 extraction modules):

| Wave | Modules | Behavior |
|------|---------|----------|
| **0** | `study_metadata` | Foundation - blocks until complete |
| **1** | 11 core modules | Run in parallel after Wave 0 |
| **2** | 4 dependent modules | Run after Wave 1 |
| **SOA/Eligibility** | Specialized analyzers | Can run standalone or integrated |

### Five-Dimensional Quality Framework

| Dimension | Weight | Threshold |
|-----------|--------|-----------|
| Accuracy | 25% | 95% |
| Completeness | 20% | 90% |
| USDM Adherence | 20% | 90% |
| Provenance | 20% | 95% |
| Terminology | 15% | 90% |

**Surgical Retry**: When quality fails, only re-extract failing fields (not entire output).

### SOA Interpretation Pipeline (12 Stages)

Located in `backend_vNext/soa_analyzer/interpretation/`.

**Execution Order**: `[1,2,3,4,5,6,7,8,9,12,11,10]` - Stage 12 runs before 11 to ensure Code objects are expanded before schedule generation.

**Critical Stages:**
- **Stage 1**: Domain Categorization - Maps activities to CDISC domains (LB, VS, EG, PE)
- **Stage 2**: Activity Expansion - Protocol-driven decomposition (uses Gemini PDF search)
- **Stage 7**: Timing Distribution - Expands BI/EOI, pre/post-dose to atomic SAIs
- **Stage 8**: Cycle Expansion - Handles cycle patterns with **triple-LLM fallback** (Gemini → Azure → Claude)
- **Stage 12**: USDM Compliance - Expands Code objects to 6-field format

Entry point: `soa_analyzer/soa_extraction_pipeline.py`

### Eligibility Analyzer

Located in `backend_vNext/eligibility_analyzer/`. Disease-aware extraction of inclusion/exclusion criteria with ATHENA concept mapping.

Entry point: `eligibility_analyzer/eligibility_extraction_pipeline.py`

### PDF Annotation

Enabled by default in `config.yaml`. Highlights provenance text snippets in source PDFs with yellow highlighting, producing annotated PDFs alongside extraction results.

### Frontend Architecture

- **Framework**: React 19 + TypeScript + Vite
- **UI**: shadcn/ui with Radix UI primitives + Tailwind CSS
- **Backend**: Express.js (BFF pattern)
- **State**: TanStack Query (React Query) with optimistic updates
- **Database**: Drizzle ORM with PostgreSQL (schema: `backend_vnext`)
- **Routing**: wouter

Split-view architecture: structured data panel + PDF viewer for side-by-side review.

**Key Frontend Tables** (`shared/schema.ts`):
- `usdm_documents` - Stores extracted USDM JSON with study metadata
- `usdm_edit_audit` - Tracks field edits with full USDM snapshots (before/after)

**Field Editing Pattern**:
- `PATCH /api/documents/:id/field` - Updates field via PostgreSQL `jsonb_set()`
- Optimistic updates via TanStack Query for responsive UI
- Full audit trail with original/updated USDM snapshots

## Environment Variables

Required in `.env` at project root:

```bash
DATABASE_URL=postgresql://...        # NeonDB PostgreSQL
GEMINI_API_KEY=...                   # Google Gemini (primary LLM)
ANTHROPIC_API_KEY=...                # Claude (SOA interpretation, Stage 8 fallback)
LANDINGAI_API_KEY=...                # LandingAI (SOA table extraction at 7x zoom)

# Optional (Azure OpenAI - Stage 8 fallback)
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_DEPLOYMENT=...
AZURE_OPENAI_API_VERSION=...

# Optional SOA settings
USE_CLAUDE_PRIMARY=false             # Set 'true' to use Claude as primary in Stage 8
```

## Key Development Patterns

### Provenance Structure

All extracted values include PDF citations:

```json
{
  "therapeuticArea": {
    "value": "Oncology",
    "provenance": {
      "page_number": 53,
      "text_snippet": "Lung cancer is the most common..."
    }
  }
}
```

### CDISC Code Objects

Use 6-field Code objects for terminology compliance:

```json
{
  "code": "C15602",
  "decode": "Phase 3",
  "codeSystem": "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl",
  "codeSystemVersion": "24.12",
  "instanceType": "Code"
}
```

### Adding New Extraction Modules

1. Create JSON Schema: `schemas/{module}_schema.json`
2. Create Pass 1 prompt: `prompts/{module}_pass1_values.txt`
3. Create Pass 2 prompt: `prompts/{module}_pass2_provenance.txt`
4. Register in `app/module_registry.py`
5. Enable in `config.yaml` with wave and priority

## Critical Constraints

| Constraint | Requirement |
|------------|-------------|
| **Python 3.10+** | Required Python version for backend |
| **Self-Contained** | ALL backend code must be in `backend_vNext/` |
| **No External Imports** | Do NOT import from parent directories |
| **Virtual Environment** | ALWAYS activate `venv/` before running Python |
| **Database Schema** | All tables use `backend_vnext` PostgreSQL schema |
| **Prompts in Files** | ALL prompts stored in `prompts/*.txt`, never hardcoded |
| **Logs in tmp/** | ALL log files go to `./tmp/`, never project root |

## Key File Locations

**Backend** (`backend_vNext/`): API entry `app/main.py`, CLI entry `scripts/main.py`, two-phase extractor `app/services/two_phase_extractor.py`, module registry `app/module_registry.py`, quality checker `app/utils/quality_checker.py`, module config `config.yaml`, JSON schemas `schemas/*.json`, LLM prompts `prompts/*_pass{1,2}_*.txt`, SOA pipeline `soa_analyzer/soa_extraction_pipeline.py`, SOA stages `soa_analyzer/interpretation/stage*.py`, eligibility pipeline `eligibility_analyzer/eligibility_extraction_pipeline.py`, USDM combiner `app/services/usdm_combiner.py`

**Frontend** (`frontend-vNext/`): React entry `client/src/main.tsx`, Express entry `server/index.ts`, API routes `server/routes.ts`, storage layer `server/storage.ts`, Drizzle schema `shared/schema.ts`, view components `client/src/pages/`, query hooks `client/src/lib/queries.ts`, API client `client/src/lib/api.ts`

## REST API

- **Backend API** (port 8080): Routes defined in `backend_vNext/app/routers/` — protocol upload/retrieval, extraction jobs, SSE progress. Base URL: `http://localhost:8080/api/v1`
- **Frontend Express API** (port 5000): Routes defined in `frontend-vNext/server/routes.ts` — USDM document CRUD, field editing with audit trail, edit history

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Module disabled | Set `enabled: true` in `config.yaml` |
| Low quality scores | Check `*_quality_report.json` for specific issues |
| API timeout | Extraction runs in separate process; poll `/jobs/{id}` |
| Cache issues | `rm -rf .cache/` |
| SOA cache issues | `rm -rf soa_analyzer/.cache/soa/` |
| Import errors | Ensure venv activated and working from `backend_vNext/` |
| Database errors | Run `python init_schema.py` |
| Frontend TypeScript errors | Run `npm run check` in frontend-vNext/ |
| LLM rate limits | Stage 8 has triple-fallback: Gemini → Azure → Claude |
| Frontend DB auth error | Check `DATABASE_URL` format in `server/db.ts` |
| Field update fails | Ensure `backend_vnext` schema prefix in raw SQL queries |
| Audit insert fails | Ensure `updatedAt: new Date()` is explicitly set |

## Detailed Documentation

- `backend_vNext/SYSTEM_DESIGN_vNEXT.md` - Full system architecture, quality framework, API reference
- `backend_vNext/soa_analyzer/SOA_ANALYSIS_SOLUTION_OVERVIEW.md` - SOA module architecture (12-stage pipeline)
- `frontend-vNext/replit.md` - Frontend architecture details
