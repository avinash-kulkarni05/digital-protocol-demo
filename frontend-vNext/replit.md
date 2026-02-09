# Clinical Data Review Platform

## Overview

This is an AI-driven clinical trial protocol data extraction and review platform. The application enables reviewers to examine clinical trial protocol documents that have been processed through an AI extraction pipeline. It displays structured USDM (Unified Study Data Model) data extracted from clinical trial protocols, provides AI-generated insights, and allows reviewers to approve, flag, or reject individual data fields.

The platform is built as a full-stack web application with a React frontend and Express backend, designed to streamline the review process for clinical trial documentation by combining AI extraction, structured data visualization, and manual review workflows.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture

**Framework**: React with TypeScript using Vite as the build tool

**UI Components**: Built on shadcn/ui component library with Radix UI primitives
- Provides a comprehensive design system with Apple-inspired aesthetics
- Uses Tailwind CSS for styling with custom theme variables
- Component library includes 50+ UI components (buttons, cards, dialogs, etc.)

**Routing**: wouter for client-side routing
- Lightweight alternative to React Router
- Main routes: Dashboard (`/`) and Review pages (`/review/:section`)

**State Management**: TanStack Query (React Query)
- Handles server state, caching, and data fetching
- Custom hooks in `client/src/lib/queries.ts` abstract API interactions
- Centralized query client configuration for consistent behavior

**Data Visualization**: 
- Custom visualization components for clinical trial data
- AI-generated insights with gauge charts and metrics
- PDF viewer integration using react-pdf for source document review

**Key Design Patterns**:
- Recursive data rendering for complex nested USDM structures
- Specialized components for different data types (arms, endpoints, eligibility criteria)
- Split-view architecture (data panel + PDF viewer) for side-by-side review
- Toggle between "Insights" mode (AI summaries) and "Review" mode (detailed field review)

### Backend Architecture

**Framework**: Express.js with TypeScript

**Build System**: 
- Custom build script using esbuild for server bundling
- Vite for client-side bundling
- Production builds bundle server dependencies to reduce cold start times

**API Design**: RESTful endpoints
- `/api/documents/:studyId` - Fetch USDM documents
- `/api/reviews/:documentId` - Manage field reviews
- `/api/reviews/:documentId/section/:section` - Section-specific reviews

**Data Access Layer**: Storage abstraction pattern
- `IStorage` interface in `server/storage.ts` defines data operations
- `DatabaseStorage` implementation uses Drizzle ORM
- Allows for easy swapping of storage backends

**Development Mode**: 
- Vite middleware integration for HMR (Hot Module Replacement)
- Custom Vite plugin for meta image updates based on deployment URL

### Data Storage Solutions

**Database**: PostgreSQL via Drizzle ORM

**Schema Design** (`shared/schema.ts`):
- `usdm_documents` table: Stores extracted clinical trial data
  - JSONB column for flexible USDM data structure
  - Study metadata (ID, title, source document URL)
- `field_reviews` table: Tracks review status of individual fields
  - Links to documents via foreign key
  - Status enum: pending, approved, rejected, flagged
  - Stores section, field path, reviewer notes, and timestamps

**ORM Choice Rationale**:
- Drizzle provides type-safe database access
- Supports PostgreSQL-specific features (JSONB, enums)
- Migration system via drizzle-kit
- Zod integration for runtime validation

**Data Migration**: 
- Migrations stored in `./migrations` directory
- Schema defined in shared code accessible to both client and server
- `db:push` script for schema synchronization

### Authentication and Authorization

**Current State**: No authentication system implemented

**Session Management**: Package dependencies suggest planned implementation
- `express-session` and `connect-pg-simple` for PostgreSQL-backed sessions
- `passport` and `passport-local` for authentication strategy
- Session store not yet configured in codebase

**Future Considerations**: Authentication will likely be added to restrict access to clinical trial data and track reviewers

### External Dependencies

**AI Integration**: Google Gemini (Generative AI)
- Service: `@google/genai` SDK
- Configuration via environment variables:
  - `AI_INTEGRATIONS_GEMINI_API_KEY`
  - `AI_INTEGRATIONS_GEMINI_BASE_URL`
- Model: `gemini-2.5-flash` for insight generation
- Features:
  - Domain-specific insight generation
  - Data summarization
  - Visualization recommendations
- Retry logic with exponential backoff for rate limiting

**Database**: PostgreSQL
- Connection string via `DATABASE_URL` environment variable
- Used through node-postgres (`pg`) driver
- Connection pooling enabled

**PDF Processing**: pdfjs (react-pdf)
- Client-side PDF rendering for protocol document viewing
- Worker-based architecture for performance
- Supports page navigation and zoom controls

**Replit Platform Integration**:
- Custom Vite plugins for Replit-specific features:
  - `@replit/vite-plugin-cartographer` - Development tooling
  - `@replit/vite-plugin-dev-banner` - Development environment indicator
  - `@replit/vite-plugin-runtime-error-modal` - Enhanced error reporting
- Meta image plugin for OpenGraph image URLs on deployed instances

**Additional Third-Party Services** (prepared but not actively used):
- Stripe integration (payment processing)
- Nodemailer (email functionality)
- OpenAI SDK (alternative AI provider)

**Development Tools**:
- TypeScript for type safety across full stack
- ESLint configuration implied by tsconfig
- PostCSS with Tailwind for CSS processing