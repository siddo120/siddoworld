"""CLI demo: run every sample report through the engine and print the result.

    python -m saathi.demo              # run all sample reports
    python -m saathi.demo RPT-1004     # run one
"""
from __future__ import annotations

import sys

from .corpus import get_corpus
from .engine import Engine, parse_report

BADGE = {
    "normal": "\U0001f7e2 NORMAL",
    "borderline": "\U0001f7e1 BORDERLINE",
    "abnormal": "\U0001f7e0 ABNORMAL",
    "critical": "\U0001f534 CRITICAL",
    "grey_zone": "⚪ GREY-ZONE",
    "uncovered": "⚪ UNCOVERED",
}


def run(report_id: str | None = None) -> None:
    corpus = get_corpus()
    engine = Engine(corpus=corpus)
    reports = corpus.sample_reports()
    if report_id:
        reports = [r for r in reports if r["report_id"] == report_id]
        if not reports:
            print(f"No sample report {report_id}")
            return

    for data in reports:
        report = parse_report(data)
        msg = engine.ingest(report)
        print("=" * 72)
        print(f"{report.report_id}  |  {data.get('scenario', '')}")
        print(f"Patient: {report.patient.name}, {report.patient.age}/{report.patient.sex}  |  Panel: {report.panel}")
        print(f"Tier: {BADGE.get(msg.tier.value, msg.tier.value)}   Action: {msg.action.value}   Band: {msg.decision.band.value}")
        print(f"Why:  {msg.decision.reason}")
        if msg.decision.sla_minutes:
            print(f"SLA:  human call within {msg.decision.sla_minutes} min")
        if msg.retrieved_ids:
            print(f"RAG:  retrieved {msg.retrieved_ids}")
        print("-" * 72)
        print(msg.text)
        print()


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else None)
