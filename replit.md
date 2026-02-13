# Clinical Trial Protocol Digitalization Platform

## Overview

This is a clinical trial protocol digitalization system that extracts structured USDM 4.0 (Unified Study Data Model) compliant JSON from protocol PDFs using LLM-powered extraction pipelines. The platform enables clinical trial reviewers to upload protocol PDFs, run AI-powered extraction across 17+ specialized modules, and review the structured output with side-by-side PDF source verification.

The monorepo contains two main components:
- **`backend_vNext/`** — Python/FastAPI backend that handles PDF processing, LLM extraction, and data persistence
- **`frontend-vNext/`** — React/Express frontend with a review UI for examining extracted clinical trial data

There is also an `.archive/` directory containing legacy code that should not be used.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture (`backend_vNext/`)

**Framework**: FastAPI (Python 3.10+) running on port 8080 via Uvicorn

**Core Design Pattern — Two-Phase LLM Extraction**:
- **Pass 1**: Extract structured values from the protocol PDF using LLM prompts
- **Pass 2**: Add provenance (exact page numbers, section numbers, and text snippets from the PDF) to every extracted value
- This two-phase approach ensures 100% provenance coverage — every extracted data point links back to its PDF source

**17 Extraction Modules** organized in 3 execution waves:
- Each module has dedicated prompt files (`prompts/*_pass1_values.txt` and `prompts/*_pass2_provenance.txt`)
- Each module has a JSON schema (`schemas/*.json`)
- Module configuration and enable/disable status controlled via `config.yaml`
- Modules cover: arms/design, endpoints/estimands, adverse events, eligibility criteria, concomitant medications, laboratory specs, PK/PD sampling, imaging, biospecimen handling, PRO specifications, data management, quality management, safety decision points, informed consent, and Schedule of Activities (SOA)

**Five-Dimensional Quality Scoring**: Every extraction is scored on accuracy, completeness, USDM schema adherence, provenance coverage, and CDISC terminology compliance. Failed extractions retry with detailed error feedback.

**Specialized Sub-Pipelines**:
- **SOA Analyzer** (`soa_analyzer/`): Multi-stage pipeline for extracting Schedule of Activities tables from PDFs, including grid extraction, interpretation, and timing distribution
- **Eligibility Analyzer** (`eligibility_analyzer/`): Dedicated pipeline with section detection, criteria extraction, atomic decomposition, and OMOP concept mapping

**Process-Based Extraction**: Long-running extractions run in separate processes. The API supports SSE (Server-Sent Events) for real-time progress streaming to the frontend.

**Database**: PostgreSQL (via SQLAlchemy ORM) with all tables in an isolated `backend_vnext` schema. Tables include `protocols` (with PDF binary storage via BYTEA), extraction jobs, and module results. The schema is initialized via `init_schema.py`.

**Key Backend Files**:
| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app entry point, CORS, middleware, route registration |
| `run.py` | Uvicorn launcher (port 8080) |
| `scripts/main.py` | CLI entry point for running extraction without the API |
| `app/services/two_phase_extractor.py` | Core two-phase extraction engine |
| `app/module_registry.py` | Registry of all 17 modules with schemas, prompts, dependencies |
| `app/utils/quality_checker.py` | Five-dimensional quality scoring |
| `app/db.py` | SQLAlchemy models (Protocol, Job, etc.) |
| `app/config.py` | Pydantic settings loaded from parent `.env` |
| `config.yaml` | Module enable/disable and configuration |

### Frontend Architecture (`frontend-vNext/`)

**Framework**: React with TypeScript, built with Vite (dev server on port 5000)

**UI Layer**: shadcn/ui component library with Radix UI primitives, styled with Tailwind CSS. Includes 50+ UI components following an Apple-inspired design system.

**Routing**: wouter (lightweight client-side router). Main routes are Dashboard (`/`) and Review pages (`/review/:section`).

**State Management**: TanStack Query (React Query) for server state, caching, and API data fetching. Custom hooks abstract API interactions.

**Key Frontend Features**:
- Split-view architecture: data panel + PDF viewer for side-by-side review
- Toggle between "Insights" mode (AI summaries) and "Review" mode (detailed field review)
- Recursive data rendering for complex nested USDM structures
- 15+ specialized view modules for different data types (arms, endpoints, eligibility, safety, SOA grid, etc.)
- SOA Analysis page with grid visualization, visit/activity/footnote tabs

**Backend-for-Frontend**: Express.js server (`server/`) that serves the built React app and proxies API requests. Uses esbuild for server bundling.

**Database (Frontend)**: Drizzle ORM with PostgreSQL. Schema defined in `shared/schema.ts`. The frontend has its own Drizzle config but may share the same PostgreSQL instance. Session storage uses `connect-pg-simple`.

### Communication Between Frontend and Backend

The React frontend communicates with the FastAPI backend via REST API calls:
- Upload PDFs → `POST /api/v1/protocols/upload`
- Start extraction → `POST /api/v1/protocols/{id}/extract`
- Poll job status → `GET /api/v1/jobs/{id}`
- Get results → `GET /api/v1/jobs/{id}/results`
- SSE for real-time progress streaming during extraction

## External Dependencies

### LLM APIs (Primary — used for extraction)
- **Google Gemini** (`google-generativeai`): Primary LLM for extraction. Uses Gemini File API for direct PDF upload and vision-based analysis. Requires `GEMINI_API_KEY`.
- **Azure OpenAI** (`openai`): Fallback LLM (gpt-5-mini) when Gemini fails
- **Anthropic Claude** (`anthropic`): Used in eligibility extraction pipeline

### Database
- **PostgreSQL** (NeonDB): Primary data store. Connection via `DATABASE_URL` env var. Backend uses SQLAlchemy with `psycopg2-binary`. Frontend uses Drizzle ORM. Backend tables live in `backend_vnext` schema.

### Task Queue (configured but optional)
- **Celery** with **Redis** broker: Configured for background job processing (`app/celery_app.py`), though the primary mode uses process-based extraction

### PDF Processing
- **PyMuPDF** (`fitz`): PDF text extraction and manipulation
- **Pillow**: Image processing for PDF pages
- **agentic-doc**: Additional document processing
- **react-pdf**: Frontend PDF rendering

### Clinical Standards
- **CDISC Controlled Terminology**: NCI Thesaurus codes for validation (`config/cdisc_codelists.json`, `config/cdisc_concepts.json`)
- **USDM 4.0**: TransCelerate Digital Data Flow standard — the target output schema
- **OMOP**: Used in eligibility criteria concept mapping

### Text Matching
- **RapidFuzz**: Fuzzy text matching for provenance verification

### Environment Configuration
- All secrets stored in `.env` at project root (parent of both `backend_vNext` and `frontend-vNext`)
- Required env vars: `DATABASE_URL`, `GEMINI_API_KEY`
- Optional: `REDIS_URL`, Azure OpenAI credentials, Anthropic API key