# Clinical Protocol Digitalization Platform

## Overview

Clinical trial protocol digitalization system that extracts structured USDM 4.0 compliant JSON from protocol PDFs using LLM-powered extraction pipelines. Monorepo with a React+Express frontend and a FastAPI backend.

## Project Structure

- `frontend-vNext/` - React + Express frontend (TypeScript, Vite, port 5000)
- `backend_vNext/` - FastAPI backend for PDF extraction (Python, port 8080)

## Running the Application

The frontend runs via the "Start application" workflow:
```bash
cd frontend-vNext && npm run dev
```
This starts an Express server on port 5000 that serves the React frontend with Vite HMR in development.

## Key Technologies

- **Frontend**: React 19, TypeScript, Vite, Express.js (BFF), Tailwind CSS, shadcn/ui, Drizzle ORM
- **Backend**: FastAPI, Python (separate service, not always needed)
- **Database**: PostgreSQL with Drizzle ORM (schema: `backend_vnext`)
- **Build**: esbuild (server) + Vite (client)

## Database

Uses PostgreSQL with Drizzle ORM. All tables live in the `backend_vnext` schema.
- `usdm_documents` - Stores extracted USDM JSON documents
- `usdm_edit_audit` - Tracks field edit history

Schema management: `cd frontend-vNext && npx drizzle-kit push`

## Deployment

- Build: `cd frontend-vNext && npm run build`
- Start: `cd frontend-vNext && npm run start`
- Target: autoscale

## User Preferences

Preferred communication style: Simple, everyday language.
