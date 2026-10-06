"""Routing / escalation: turn a classification into an action decision.

Mirrors Q1 (who handles what) and Q4 (confidence bands). Critical is *never*
confidence-gated: it always escalates to a mandatory human call within 30
minutes. Everything else is placed in a band that decides whether the AI sends
autonomously, drafts for a human spot-check, or hands straight to a person.
"""
from __future__ import annotations

from typing import Optional

from .corpus import Corpus, get_corpus
from .models import Action, Band, Decision, ReportClassification, Tier

CRITICAL_SLA_MINUTES = 30


def route(rc: ReportClassification, corpus: Optional[Corpus] = None) -> Decision:
    corpus = corpus or get_corpus()
    tier = rc.overall_tier

    if tier == Tier.CRITICAL:
        return Decision(
            action=Action.ESCALATE_CRITICAL,
            band=Band.LOW,  # humans own this regardless of model confidence
            reason="Critical value present — mandatory human call, never AI-only.",
            sla_minutes=CRITICAL_SLA_MINUTES,
        )

    if tier == Tier.GREY_ZONE:
        reason = "Two or more significantly abnormal values — combining them is diagnostic reasoning, routed for review." \
            if "multiple_abnormal" in rc.flags else \
            "Result could not be confidently classified — routed to the grey-zone queue."
        return Decision(action=Action.HUMAN_REVIEW, band=Band.LOW, reason=reason)

    if tier == Tier.UNCOVERED:
        return Decision(
            action=Action.HUMAN_REVIEW,
            band=Band.LOW,
            reason="Report contains a test outside the trained rule set — expert review required.",
        )

    # Normal / borderline / abnormal are AI-handleable. Specialist comes from
    # the most severe flagged analyte, for the abnormal nudge.
    specialist = ""
    if rc.flagged:
        specialist = corpus.specialist_for(rc.flagged[0].analyte)

    if tier == Tier.NORMAL:
        return Decision(Action.AI_AUTONOMOUS, Band.HIGH, "All values in range — AI confirms normal.", specialist)
    if tier == Tier.BORDERLINE:
        return Decision(Action.AI_AUTONOMOUS, Band.HIGH, "Borderline only — pre-approved template tier, AI handles.", specialist)
    # abnormal, non-critical
    return Decision(
        Action.AI_AUTONOMOUS,
        Band.MEDIUM,
        "Abnormal but non-critical — AI explains and names a specialist category; medium band is spot-checked during soft launch.",
        specialist,
    )
