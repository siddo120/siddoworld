"""Loading and indexing of the synthetic corpus.

Holds the reference ranges (the rulebook), the RAG knowledge base, the
pre-approved templates, and the sample reports. All of it is data; none of it
makes decisions. The one piece of logic here is resolving an analyte name (and
its aliases) plus patient age/sex to the right reference range row.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .models import Patient

DATA_DIR = Path(__file__).parent / "data"


def _load(name: str) -> dict:
    with open(DATA_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


class Corpus:
    def __init__(self) -> None:
        self.reference = _load("reference_ranges.json")
        self.knowledge = _load("knowledge_base.json")
        self.templates = _load("templates.json")
        self.samples = _load("sample_reports.json")

        # Build an alias -> canonical analyte map for name resolution.
        self._alias_map: dict[str, dict] = {}
        for entry in self.reference["analytes"]:
            names = [entry["analyte"], *entry.get("aliases", [])]
            for n in names:
                self._alias_map[n.strip().lower()] = entry

    def resolve_analyte(self, name: str) -> Optional[dict]:
        """Return the reference entry for an analyte name or alias, or None."""
        return self._alias_map.get(name.strip().lower())

    def reference_range(self, name: str, patient: Patient) -> Optional[dict]:
        """Pick the age/sex-appropriate reference row for this analyte.

        Returns a dict augmented with analyte metadata (unit, specialist...),
        or None when the analyte is not in the rule set at all.
        """
        entry = self.resolve_analyte(name)
        if not entry:
            return None

        sex = patient.sex_norm
        candidates = []
        for rng in entry["ranges"]:
            rng_sex = rng.get("sex", "any").upper()
            if rng_sex not in ("ANY", sex):
                continue
            if not (rng.get("age_min", 0) <= patient.age <= rng.get("age_max", 200)):
                continue
            candidates.append((rng_sex, rng))

        if not candidates:
            return None
        # Prefer a sex-specific row over an "any" row when both match.
        candidates.sort(key=lambda c: 0 if c[0] != "ANY" else 1)
        chosen = candidates[0][1]
        return {
            "analyte": entry["analyte"],
            "unit": entry.get("unit", ""),
            "category": entry.get("category", ""),
            "specialist": entry.get("specialist", "your physician"),
            **chosen,
        }

    def specialist_for(self, name: str) -> str:
        entry = self.resolve_analyte(name)
        return entry.get("specialist", "your physician") if entry else "your physician"

    def sample_reports(self) -> list[dict]:
        return self.samples["reports"]

    def sample_report(self, report_id: str) -> Optional[dict]:
        for r in self.sample_reports():
            if r["report_id"] == report_id:
                return r
        return None


@lru_cache(maxsize=1)
def get_corpus() -> Corpus:
    """Process-wide singleton so files are read once."""
    return Corpus()
