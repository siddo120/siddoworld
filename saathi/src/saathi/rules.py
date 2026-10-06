"""Deterministic classification engine.

This is the single source of truth for *how serious* a result is. It is plain
arithmetic against reference ranges with zero model involvement, which is what
makes it auditable and testable (Q2 "prevention"). The RAG/LLM layer runs only
*after* this, and only to phrase an explanation.

Per-analyte tiers:
  critical  : value past a hard critical threshold
  normal    : value inside the reference range
  borderline: value just outside the range, within the "mild" band
  abnormal  : value outside the mild band but not critical
  grey_zone : analyte is known but no range matches this age/sex (unsure)
  uncovered : analyte is not in the rule set at all

Report tier precedence: critical > grey_zone > uncovered > abnormal > borderline > normal,
with one extra rule from Q1 scenario 11: two or more significantly abnormal
values escalate the whole report to grey_zone for human review.
"""
from __future__ import annotations

from typing import Optional

from .corpus import Corpus, get_corpus
from .models import (
    AnalyteClassification,
    AnalyteResult,
    Patient,
    Report,
    ReportClassification,
    Tier,
    TIER_RANK,
)

# Fraction of the reference span that counts as "just slightly out" (borderline)
# when a dataset doesn't specify explicit mild bounds.
DEFAULT_MILD_FRACTION = 0.15


def _mild_bounds(rng: dict) -> tuple[Optional[float], Optional[float]]:
    """Resolve the borderline band edges, explicit or derived."""
    low = rng.get("low")
    high = rng.get("high")
    mild_low = rng.get("mild_low")
    mild_high = rng.get("mild_high")
    if low is not None and high is not None:
        span = high - low
        if mild_low is None:
            mild_low = low - DEFAULT_MILD_FRACTION * span
        if mild_high is None:
            mild_high = high + DEFAULT_MILD_FRACTION * span
    return mild_low, mild_high


def classify_analyte(result: AnalyteResult, patient: Patient, corpus: Corpus) -> AnalyteClassification:
    entry = corpus.resolve_analyte(result.analyte)
    if entry is None:
        return AnalyteClassification(
            analyte=result.analyte,
            value=result.value,
            unit=result.unit,
            tier=Tier.UNCOVERED,
            reason="Analyte not present in the rule set; cannot classify.",
        )

    rng = corpus.reference_range(result.analyte, patient)
    if rng is None:
        return AnalyteClassification(
            analyte=entry["analyte"],
            value=result.value,
            unit=result.unit or entry.get("unit", ""),
            tier=Tier.GREY_ZONE,
            reason=f"No reference range matches age {patient.age}/{patient.sex_norm}; needs review.",
        )

    v = result.value
    low = rng.get("low")
    high = rng.get("high")
    crit_low = rng.get("critical_low")
    crit_high = rng.get("critical_high")
    mild_low, mild_high = _mild_bounds(rng)
    unit = rng.get("unit", result.unit)

    direction = ""
    if high is not None and v > high:
        direction = "above"
    elif low is not None and v < low:
        direction = "below"

    # Critical thresholds take precedence over everything.
    if crit_high is not None and v >= crit_high:
        tier, reason = Tier.CRITICAL, f"{v} >= critical high {crit_high}."
    elif crit_low is not None and v <= crit_low:
        tier, reason = Tier.CRITICAL, f"{v} <= critical low {crit_low}."
    elif low is not None and high is not None and low <= v <= high:
        tier, reason = Tier.NORMAL, f"{v} within range {low}-{high}."
    elif (mild_low is not None and mild_low <= v < (low if low is not None else v)) or (
        mild_high is not None and (high if high is not None else v) < v <= mild_high
    ):
        tier, reason = Tier.BORDERLINE, f"{v} just {direction} range {low}-{high} (mild band)."
    else:
        tier, reason = Tier.ABNORMAL, f"{v} {direction} range {low}-{high} beyond the mild band."

    return AnalyteClassification(
        analyte=entry["analyte"],
        value=v,
        unit=unit,
        tier=tier,
        low=low,
        high=high,
        direction=direction,
        reason=reason,
        matched_range=rng,
    )


def classify_report(report: Report, corpus: Optional[Corpus] = None) -> ReportClassification:
    corpus = corpus or get_corpus()
    analytes = [classify_analyte(r, report.patient, corpus) for r in report.results]

    flags: list[str] = []

    # Scenario 11: two or more significantly abnormal values -> human review.
    n_abnormal = sum(1 for a in analytes if a.tier == Tier.ABNORMAL)
    if n_abnormal >= 2:
        flags.append("multiple_abnormal")

    has_critical = any(a.tier == Tier.CRITICAL for a in analytes)
    has_grey = any(a.tier == Tier.GREY_ZONE for a in analytes)
    has_uncovered = any(a.tier == Tier.UNCOVERED for a in analytes)

    if has_critical:
        overall = Tier.CRITICAL
    elif has_grey or ("multiple_abnormal" in flags):
        overall = Tier.GREY_ZONE
    elif has_uncovered:
        overall = Tier.UNCOVERED
    else:
        # Highest remaining per-analyte tier by rank.
        overall = max((a.tier for a in analytes), key=lambda t: TIER_RANK[t], default=Tier.NORMAL)

    return ReportClassification(
        report_id=report.report_id,
        overall_tier=overall,
        analytes=analytes,
        flags=flags,
    )
