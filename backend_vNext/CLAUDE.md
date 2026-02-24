# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Self-contained clinical trial protocol extraction backend (v4.0). Extracts structured USDM 4.0 JSON from protocol PDFs using two-phase LLM extraction with five-dimensional quality scoring.

**Python**: 3.10+ (use existing `venv/`)
**API**: FastAPI on port 8080
**Modules**: 17 extraction modules in 3 waves (1 Wave 0 + 11 Wave 1 + 4 Wave 2 + SOA)

## Quick Reference

```bash
source venv/bin/activate              # REQUIRED first
python run.py                          # Start API server
python scripts/main.py --pdf <file>    # CLI extraction
python init_schema.py                  # Initialize database
```

## Testing

```bash
python -m pytest soa_analyzer/tests/ -v                              # All SOA tests
python -m pytest soa_analyzer/tests/ -k "test_name" -v               # By name
python -m pytest soa_analyzer/tests/test_stage7_timing_distribution.py -v  # Single file
```

## Critical Constraints

- **Self-Contained**: ALL code in `backend_vNext/`
- **No External Imports**: Do NOT import from parent directories
- **Virtual Environment**: ALWAYS activate `venv/` before running
- **Database Schema**: All tables use `backend_vnext` PostgreSQL schema
- **Prompts in Files**: ALL prompts in `prompts/*.txt`, never hardcoded
- **Logs in tmp/**: ALL logs go to `./tmp/`

## Key Files

| Purpose | Location |
|---------|----------|
| API entry | `app/main.py` |
| CLI entry | `scripts/main.py` |
| Two-phase extractor | `app/services/two_phase_extractor.py` |
| Module registry | `app/module_registry.py` |
| Quality checker | `app/utils/quality_checker.py` |
| Module config | `config.yaml` |
| JSON Schemas | `schemas/*.json` |
| Prompts | `prompts/*_pass1_values.txt`, `prompts/*_pass2_provenance.txt` |
| SOA pipeline | `soa_analyzer/soa_extraction_pipeline.py` |
| SOA interpretation | `soa_analyzer/interpretation/stage*.py` |
| Eligibility pipeline | `eligibility_analyzer/eligibility_extraction_pipeline.py` |
| Eligibility interpretation | `eligibility_analyzer/interpretation/stage*.py` |

## Adding New Modules

1. Create `schemas/{module}_schema.json`
2. Create `prompts/{module}_pass1_values.txt`
3. Create `prompts/{module}_pass2_provenance.txt`
4. Register in `app/module_registry.py`
5. Add to `config.yaml` with wave/priority

## Detailed Documentation

See root `CLAUDE.md` for full architecture, or `SYSTEM_DESIGN_vNEXT.md` for comprehensive details.
