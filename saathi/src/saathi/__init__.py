"""Saathi — a RAG-based lab-report assistant prototype for Dr Lal PathLabs.

Deterministic rule engine for classification + a RAG/LLM layer for explanation,
exactly as laid out in the pitch. Import the pieces you need:

    from saathi.engine import Engine, parse_report
    from saathi.rules import classify_report
"""
from .engine import Engine, parse_report
from .models import Action, Band, Tier

__all__ = ["Engine", "parse_report", "Tier", "Action", "Band"]
__version__ = "0.1.0"
