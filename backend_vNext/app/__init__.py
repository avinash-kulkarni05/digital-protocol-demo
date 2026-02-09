"""
Backend vNext - Next-generation protocol extraction pipeline.

This package provides a simplified sequential extraction pipeline with:
- 10 extraction modules (3 combined from original 13)
- Two-phase extraction (Pass 1: values, Pass 2: provenance)
- 100% provenance coverage requirement
- Gemini File API for PDF processing
- PostgreSQL persistence (backend_vnext schema)
"""

__version__ = "1.0.0"
__author__ = "Saama Technologies"
