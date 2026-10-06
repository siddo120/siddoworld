"""Top-level orchestration: report in, classified + routed + explained out.

    ingest(report):  rules -> router -> RAG explanation  => AssistantMessage
    audit(report):   rules -> router only (no LLM)        => the ground truth
                     used by the random-sample audit in Q2.
"""
from __future__ import annotations

from typing import Optional

from .conversation import ConversationSession
from .corpus import Corpus, get_corpus
from .explain import Explainer
from .models import (
    AnalyteResult,
    AssistantMessage,
    Patient,
    Report,
)
from .router import route


def parse_report(data: dict) -> Report:
    """Build a Report from a plain dict (sample file or API payload)."""
    p = data["patient"]
    patient = Patient(
        name=p.get("name", "there"),
        age=int(p.get("age", 0)),
        sex=p.get("sex", "any"),
        phone=p.get("phone", ""),
        chronic=bool(p.get("chronic", False)),
    )
    results = [
        AnalyteResult(analyte=r["analyte"], value=float(r["value"]), unit=r.get("unit", ""))
        for r in data["results"]
    ]
    return Report(
        report_id=data.get("report_id", "RPT-AD-HOC"),
        patient=patient,
        panel=data.get("panel", "your test"),
        results=results,
        collected_at=data.get("collected_at", ""),
        scenario=data.get("scenario", ""),
    )


class Engine:
    def __init__(self, corpus: Optional[Corpus] = None, explainer: Optional[Explainer] = None) -> None:
        self.corpus = corpus or get_corpus()
        self.explainer = explainer or Explainer(corpus=self.corpus)

    def ingest(self, report: Report) -> AssistantMessage:
        from .rules import classify_report  # local import to avoid cycle at module load

        rc = classify_report(report, self.corpus)
        decision = route(rc, self.corpus)
        text, retrieved = self.explainer.build(rc, report.patient.name, report.panel)
        return AssistantMessage(
            text=text,
            tier=rc.overall_tier,
            action=decision.action,
            classification=rc,
            decision=decision,
            retrieved_ids=retrieved,
            provider=self.explainer.provider.name,
        )

    def audit(self, report: Report) -> dict:
        """Deterministic classification + decision with no LLM phrasing.

        This is what a random-sample audit cross-checks the sent explanation
        against (Q2, detection layer two).
        """
        from .rules import classify_report

        rc = classify_report(report, self.corpus)
        decision = route(rc, self.corpus)
        return {"classification": rc.to_dict(), "decision": decision.to_dict()}

    def session_for(self, report: Report) -> ConversationSession:
        from .rules import classify_report

        rc = classify_report(report, self.corpus)
        return ConversationSession(patient_name=report.patient.name, classification=rc, corpus=self.corpus)
