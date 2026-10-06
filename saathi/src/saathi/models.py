"""Core domain models for the Saathi report assistant.

These are plain dataclasses shared by every layer. Keeping them dependency-free
means the rule engine, RAG layer and server all speak the same vocabulary.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Tier(str, Enum):
    """Severity tier assigned by the deterministic rule engine.

    Ordered by severity via ``RANK`` below. The LLM never produces a Tier;
    it only phrases an explanation for a tier the rules already decided.
    """

    NORMAL = "normal"
    BORDERLINE = "borderline"
    ABNORMAL = "abnormal"
    CRITICAL = "critical"
    GREY_ZONE = "grey_zone"
    UNCOVERED = "uncovered"


# Higher rank = more severe / takes precedence when summarising a report.
TIER_RANK = {
    Tier.NORMAL: 0,
    Tier.BORDERLINE: 1,
    Tier.ABNORMAL: 2,
    Tier.GREY_ZONE: 3,
    Tier.UNCOVERED: 3,
    Tier.CRITICAL: 4,
}


class Action(str, Enum):
    """What the router decides should happen with a classified report."""

    AI_AUTONOMOUS = "ai_autonomous"          # AI sends explanation directly
    AI_SPOT_CHECK = "ai_spot_check"          # AI drafts, human approves before send
    ESCALATE_CRITICAL = "escalate_critical"  # mandatory human call <=30 min
    HUMAN_REVIEW = "human_review"            # grey-zone / uncovered queue


class Band(str, Enum):
    """Confidence band from Q4 that gates how autonomously the AI may act."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Patient:
    name: str
    age: int
    sex: str  # "M", "F" or "any"
    phone: str = ""
    chronic: bool = False

    @property
    def sex_norm(self) -> str:
        s = (self.sex or "").strip().upper()
        return s if s in ("M", "F") else "ANY"


@dataclass
class AnalyteResult:
    analyte: str
    value: float
    unit: str = ""


@dataclass
class Report:
    report_id: str
    patient: Patient
    panel: str
    results: list[AnalyteResult]
    collected_at: str = ""
    scenario: str = ""


@dataclass
class AnalyteClassification:
    analyte: str
    value: float
    unit: str
    tier: Tier
    low: Optional[float] = None
    high: Optional[float] = None
    direction: str = ""   # "above" / "below" / ""
    reason: str = ""      # human-readable audit note (deterministic)
    matched_range: Optional[dict] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tier"] = self.tier.value
        return d


@dataclass
class ReportClassification:
    report_id: str
    overall_tier: Tier
    analytes: list[AnalyteClassification]
    flags: list[str] = field(default_factory=list)  # e.g. "multiple_abnormal"

    @property
    def flagged(self) -> list[AnalyteClassification]:
        return [a for a in self.analytes if a.tier != Tier.NORMAL]

    def tier_count(self, tier: Tier) -> int:
        return sum(1 for a in self.analytes if a.tier == tier)

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "overall_tier": self.overall_tier.value,
            "analytes": [a.to_dict() for a in self.analytes],
            "flags": list(self.flags),
        }


@dataclass
class Decision:
    """The router's output: what to do and why, fully auditable."""

    action: Action
    band: Band
    reason: str
    specialist: str = ""
    sla_minutes: Optional[int] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.value
        d["band"] = self.band.value
        return d


@dataclass
class AssistantMessage:
    """A single outbound WhatsApp-style message plus the audit trail behind it."""

    text: str
    tier: Tier
    action: Action
    classification: ReportClassification
    decision: Decision
    retrieved_ids: list[str] = field(default_factory=list)
    provider: str = "mock"

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "tier": self.tier.value,
            "action": self.action.value,
            "classification": self.classification.to_dict(),
            "decision": self.decision.to_dict(),
            "retrieved_ids": list(self.retrieved_ids),
            "provider": self.provider,
        }
