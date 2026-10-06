"""Explanation layer: turn a classified report into a WhatsApp message.

Flow: pick the pre-approved template for the tier -> render the deterministic
version (lines + retrieved grounding) -> hand template, grounding and guardrails
to the LLM provider to phrase. The mock returns the deterministic rendering
unchanged; a real provider rephrases within the same frame. Either way the tier,
the numbers and the escalation behaviour come from the rules, not the model.
"""
from __future__ import annotations

from typing import Optional

from .corpus import Corpus, get_corpus
from .llm import LLMProvider, get_provider
from .models import AnalyteClassification, ReportClassification, Tier
from .retrieval import Retriever, get_retriever

SYSTEM_GUARDRAILS = (
    "You are a lab-report explainer for Dr Lal PathLabs on WhatsApp. "
    "You may only rephrase the approved draft and the grounding snippets provided. "
    "Never add a diagnosis, never suggest treatment or medication, never change which "
    "values are flagged or how serious they are, and never invent numbers. "
    "Keep it warm, plain and under ~120 words."
)


def _fmt(template: str, **kw) -> str:
    class _Safe(dict):
        def __missing__(self, key):  # leave unknown placeholders intact
            return "{" + key + "}"

    return template.format_map(_Safe(**kw))


def _range_str(a: AnalyteClassification) -> str:
    """Natural-language reference band, handling one-sided ranges."""
    low, high = a.low, a.high
    low_zero = low is None or low == 0
    if low_zero and high is not None:
        return f"under {high:g}"
    if high is None and low is not None:
        return f"over {low:g}"
    if low is not None and high is not None:
        return f"{low:g}–{high:g}"
    return "the usual range"


def _line(corpus: Corpus, a: AnalyteClassification) -> str:
    fmts = corpus.templates["line_formats"]
    common = dict(analyte=a.analyte, value=a.value, unit=a.unit, range=_range_str(a), direction=a.direction)
    if a.tier == Tier.NORMAL:
        return _fmt(fmts["normal_line"], **common)
    if a.tier == Tier.BORDERLINE:
        return _fmt(fmts["borderline_line"], **common)
    if a.tier == Tier.CRITICAL:
        return _fmt(fmts["critical_line"], **common)
    return _fmt(fmts["abnormal_line"], **common)


def _top_specialist(corpus: Corpus, flagged: list[AnalyteClassification]) -> str:
    # Specialist of the most severe flagged analyte (abnormal before borderline).
    order = {Tier.ABNORMAL: 0, Tier.BORDERLINE: 1}
    ranked = sorted(flagged, key=lambda a: order.get(a.tier, 2))
    for a in ranked:
        return corpus.specialist_for(a.analyte)
    return "your physician"


class Explainer:
    def __init__(
        self,
        corpus: Optional[Corpus] = None,
        retriever: Optional[Retriever] = None,
        provider: Optional[LLMProvider] = None,
    ) -> None:
        self.corpus = corpus or get_corpus()
        self.retriever = retriever or get_retriever()
        self.provider = provider or get_provider()

    def build(self, rc: ReportClassification, patient_name: str, panel: str) -> tuple[str, list[str]]:
        """Return (message_text, retrieved_snippet_ids)."""
        tmpl = self.corpus.templates["tier_templates"]
        tier = rc.overall_tier
        flagged = rc.flagged

        # Critical / grey-zone / uncovered: fixed, detail-free messages.
        if tier in (Tier.CRITICAL, Tier.GREY_ZONE, Tier.UNCOVERED):
            t = tmpl[tier.value]
            parts = [
                _fmt(t["headline"], patient_name=patient_name, panel=panel),
                _fmt(t["body"], patient_name=patient_name, panel=panel),
            ]
            if t.get("closing"):
                parts.append(_fmt(t["closing"], patient_name=patient_name, panel=panel))
            fallback = "\n\n".join(p for p in parts if p)
            return self._phrase(tier, fallback, grounding="", flagged=flagged), []

        # Normal / borderline / abnormal: render lines + grounding.
        retrieved = self.retriever.retrieve([a.analyte for a in (flagged or rc.analytes)], tier, k=3)
        grounding = " ".join(s.text for s in retrieved)
        specialist = _top_specialist(self.corpus, flagged) if flagged else "your physician"

        if tier == Tier.NORMAL:
            t = tmpl["normal"]
            lines = "\n".join(_line(self.corpus, a) for a in rc.analytes)
            body = _fmt(t["body"], normal_lines=lines)
        else:
            t = tmpl[tier.value]
            lines = "\n".join(_line(self.corpus, a) for a in flagged)
            body = _fmt(t["body"], flagged_lines=lines, grounding=grounding, specialist=specialist)

        parts = [
            _fmt(t["headline"], patient_name=patient_name, panel=panel),
            body,
            _fmt(t.get("closing", ""), patient_name=patient_name, panel=panel, specialist=specialist),
        ]
        fallback = "\n\n".join(p.strip() for p in parts if p and p.strip())
        text = self._phrase(tier, fallback, grounding=grounding, flagged=flagged)
        return text, [s.id for s in retrieved]

    def _phrase(self, tier: Tier, fallback: str, grounding: str, flagged) -> str:
        prompt = (
            f"Approved draft to phrase (tier: {tier.value}):\n{fallback}\n\n"
            f"Grounding snippets (do not contradict):\n{grounding or '(none)'}\n\n"
            "Rewrite the approved draft to sound natural on WhatsApp. Keep every flagged "
            "value, the range and the escalation exactly as given. Do not add advice."
        )
        return self.provider.draft(SYSTEM_GUARDRAILS, prompt, fallback=fallback)
