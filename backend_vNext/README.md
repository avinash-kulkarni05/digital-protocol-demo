# Protocol Digitalization Backend (vNext)

AI-powered clinical trial protocol extraction system that transforms PDF protocols into structured USDM 4.0 compliant JSON using a 17-module LLM extraction pipeline.

## Features

- **Two-Phase Extraction**: Pass 1 extracts values, Pass 2 adds PDF provenance citations
- **Five-Dimensional Quality**: Accuracy, Completeness, Compliance, Provenance, Terminology scoring
- **17 Extraction Modules**: Organized in 3 waves with dependency management
- **100% Provenance Coverage**: Every extracted value linked to PDF source
- **CDISC CT Compliance**: NCI Thesaurus code validation and auto-correction
- **REST API**: FastAPI-based API with SSE for real-time progress
- **Process-Based Extraction**: Long-running extractions run in separate processes

## Quick Start

```bash
# 1. Activate virtual environment
cd backend_vNext
source venv/bin/activate

# 2. Set environment variables
export GEMINI_API_KEY=your_key
export DATABASE_URL=postgresql://...

# 3. Initialize database
python init_schema.py

# 4. Start API server
python run.py
# Server runs at http://localhost:8080
```

## API Usage

```bash
# Upload protocol PDF
curl -X POST http://localhost:8080/api/v1/protocols/upload \
  -F "file=@protocol.pdf"

# Start extraction (returns job_id)
curl -X POST http://localhost:8080/api/v1/protocols/{protocol_id}/extract \
  -H "Content-Type: application/json" \
  -d '{"resume": false}'

# Check job status
curl http://localhost:8080/api/v1/jobs/{job_id}

# Get extraction results
curl http://localhost:8080/api/v1/jobs/{job_id}/results
```

## CLI Usage

```bash
# Run extraction via CLI
python scripts/main.py --pdf /path/to/protocol.pdf

# Show enabled modules
python scripts/main.py --show-agents
```

## Project Structure

```
backend_vNext/
├── app/                      # FastAPI application
│   ├── main.py              # Application entry point
│   ├── config.py            # Configuration settings
│   ├── db.py                # Database models
│   ├── module_registry.py   # 17 extraction modules
│   ├── routers/             # API endpoints
│   │   ├── protocol.py      # Upload, extraction
│   │   └── jobs.py          # Status, results, SSE
│   ├── services/            # Core services
│   │   ├── extraction_worker.py    # Process-based extraction
│   │   ├── two_phase_extractor.py  # Pass 1 + Pass 2
│   │   └── sequential_orchestrator.py
│   └── utils/               # Utilities
│       ├── quality_checker.py
│       └── cdisc_validator.py
├── soa_analyzer/            # Schedule of Assessments module
│   ├── interpretation/      # 12-stage pipeline
│   └── tests/               # Test suite
├── eligibility_analyzer/    # Eligibility criteria module
├── schemas/                 # JSON schemas (17)
├── prompts/                 # LLM prompts (Pass 1 + Pass 2)
├── config/                  # CDISC codelists
└── config.yaml             # Module configuration
```

## Extraction Modules

| Wave | Module | Description |
|------|--------|-------------|
| 0 | study_metadata | Study identification, phase, design |
| 1 | arms_design | Treatment arms, cohorts |
| 1 | endpoints_estimands_sap | Endpoints, statistical analysis |
| 1 | adverse_events | AE/SAE definitions |
| 1 | safety_decision_points | Dose modifications |
| 1 | concomitant_medications | Allowed/prohibited meds |
| 1 | biospecimen_handling | Sample collection |
| 1 | laboratory_specifications | Lab tests |
| 1 | informed_consent | ICF elements |
| 1 | pro_specifications | PRO/COA instruments |
| 1 | data_management | EDC, data standards |
| 1 | site_operations_logistics | Site setup |
| 2 | quality_management | Monitoring, RBQM |
| 2 | withdrawal_procedures | Discontinuation |
| 2 | imaging_central_reading | Imaging (oncology) |
| 2 | pkpd_sampling | PK/PD schedules |

## Documentation

- [CLAUDE.md](CLAUDE.md) - Claude Code guidance and API reference
- [SYSTEM_DESIGN_vNEXT.md](SYSTEM_DESIGN_vNEXT.md) - Architecture details

## Requirements

- Python 3.10+
- PostgreSQL database
- Google Gemini API key
- (Optional) Anthropic API key for SOA extraction

## License

Proprietary - Saama Technologies
