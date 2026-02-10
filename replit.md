# Clinical Protocol Digitalization Platform

## Overview

Clinical trial protocol digitalization system that extracts structured USDM 4.0 compliant JSON from protocol PDFs using LLM-powered extraction pipelines. Monorepo with a React+Express frontend and a FastAPI backend.

## Project Structure

- `frontend-vNext/` - React + Express frontend (TypeScript, Vite, port 5000)
- `backend_vNext/` - FastAPI backend for PDF extraction (Python, port 8080)

## Running the Application

Two workflows run concurrently:

1. **Start application** (frontend): `cd frontend-vNext && npm run dev`
   - Express server on port 5000 serving React frontend with Vite HMR
   - Proxies `/api/backend/*` requests to Python backend (`/api/v1/*` on port 8080)

2. **Python Backend**: `cd backend_vNext && python run.py --host 0.0.0.0 --port 8080`
   - FastAPI server for extraction, SOA analysis, eligibility features
   - Requires `GEMINI_API_KEY` secret for LLM-powered extraction

## Architecture

- Frontend routes `/api/backend/*` are proxied via `http-proxy-middleware` to `http://127.0.0.1:8080/api/v1/*`
- Protocol uploads go through Express (`/api/protocols/upload`) and save PDFs to `frontend-vNext/attached_assets/`
- Upload also registers protocol with Python backend (`POST /api/v1/protocols/upload`) for extraction support
- Document CRUD is handled by Express routes with Drizzle ORM
- Extraction, SOA, and eligibility features are handled by the Python FastAPI backend
- Protocol identification uses `studyId` (filename without .pdf extension) throughout the system
- Python backend endpoints accept both UUID and studyId string for protocol identification
- After extraction completes, USDM JSON is fetched from Python backend and synced to Drizzle via `PUT /api/documents/:studyId/usdm`
- Document list endpoint enriches documents with extraction status from Python backend

## Key Technologies

- **Frontend**: React 19, TypeScript, Vite, Express.js (BFF), Tailwind CSS, shadcn/ui, Drizzle ORM
- **Backend**: FastAPI, Python 3.11, SQLAlchemy, Google Gemini API
- **Database**: PostgreSQL with Drizzle ORM (frontend) + SQLAlchemy (backend), schema: `backend_vnext`
- **Build**: esbuild (server) + Vite (client)

## Database

Uses PostgreSQL. All tables live in the `backend_vnext` schema.

Frontend tables (Drizzle ORM):
- `usdm_documents` - Stores extracted USDM JSON documents
- `usdm_edit_audit` - Tracks field edit history

Backend tables (SQLAlchemy):
- `protocols` - Uploaded protocol PDFs with Gemini cache
- `jobs` - Extraction job tracking
- `module_results` - Per-module extraction results
- `job_events` - Job events for SSE streaming
- `extraction_outputs` - Extraction output files
- `extraction_cache` - DB-backed extraction cache
- `soa_jobs` - SOA extraction jobs
- `soa_table_results` - Per-table SOA results
- `soa_edit_audit` - SOA field edit audit trail
- `soa_merge_plans` - SOA merge plans
- `soa_merge_group_results` - SOA merge group results
- `eligibility_jobs` - Eligibility extraction jobs

Schema management:
- Frontend: `cd frontend-vNext && npx drizzle-kit push`
- Backend: Auto-initialized on startup via `init_schema()`

## Deployment

- Build: `cd frontend-vNext && npm run build && python scripts/migrate_to_production.py`
- Start: Both Python backend and Node.js frontend run concurrently
- Target: autoscale
- Data migration: `scripts/migrate_to_production.py` copies dev DB data to production during build
  - Primary: Direct DB-to-DB copy via `DEV_DATABASE_URL` -> `DATABASE_URL`
  - Fallback: Pickle dump file (`scripts/dev_data_dump.pkl`) if dev DB unreachable
  - Export: Run `python scripts/export_dev_data.py` to create pickle dump before deploy

## Required Secrets

- `GEMINI_API_KEY` - Google Gemini API key for LLM extraction
- `DATABASE_URL` - PostgreSQL connection (auto-provided by Replit)
- `DEV_DATABASE_URL` - Dev database URL for production data migration

## User Preferences

Preferred communication style: Simple, everyday language.
