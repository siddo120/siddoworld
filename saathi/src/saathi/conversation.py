"""Patient-facing conversation handling after a report has been explained.

Implements the hard boundaries from Q1:
  - Scenario 12: "talk to a human" is always honored immediately.
  - Scenario 8:  medical-advice questions are declined, with an offer to connect.
  - Scenario 9:  a dispute gets exactly one recheck, then defers to a doctor
                 (never an open-ended loop).

Intent detection is deterministic keyword matching so the boundaries don't
depend on model behaviour. The LLM is not in this path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .corpus import Corpus, get_corpus
from .models import ReportClassification, Tier
from .retrieval import Retriever, get_retriever

# Minimum retrieval score for a follow-up answer to count as "in the approved
# library". Below this, the AI hands off rather than guess. Tuned so on-topic
# questions (~0.26+) answer and off-topic ones (~0.17-) hand off.
ANSWER_THRESHOLD = 0.22


class Intent(str, Enum):
    REQUEST_HUMAN = "request_human"
    MEDICAL_ADVICE = "medical_advice"
    DISPUTE = "dispute"
    BOOKING = "booking"
    GENERAL = "general"


_HUMAN_KW = ["talk to a human", "speak to a human", "talk to someone", "real person",
             "speak to someone", "human agent", "call me", "talk to a person", "customer care"]
_ADVICE_KW = ["should i", "shall i", "stop my", "stop taking", "medication", "medicine",
              "what do i do", "what should", "treatment", "cure", "dosage", "dose", "prescribe", "diet plan"]
_DISPUTE_KW = ["wrong", "not right", "incorrect", "mistake", "disagree", "are you sure",
               "doesn't seem", "dont think", "don't think", "double check", "recheck", "that's not"]
_BOOKING_KW = ["book", "appointment", "schedule", "consult"]


def detect_intent(message: str) -> Intent:
    m = message.lower()
    if any(k in m for k in _HUMAN_KW):
        return Intent.REQUEST_HUMAN
    if any(k in m for k in _ADVICE_KW):
        return Intent.MEDICAL_ADVICE
    if any(k in m for k in _DISPUTE_KW):
        return Intent.DISPUTE
    if any(k in m for k in _BOOKING_KW):
        return Intent.BOOKING
    return Intent.GENERAL


@dataclass
class Reply:
    text: str
    intent: Intent
    escalated: bool = False       # handed to a human
    offered_doctor: bool = False
    from_library: bool = False            # answered from an approved snippet
    retrieved_ids: list[str] = field(default_factory=list)


@dataclass
class ConversationSession:
    """Holds the context needed to answer follow-ups about one report."""

    patient_name: str
    classification: Optional[ReportClassification] = None
    corpus: Corpus = field(default_factory=get_corpus)
    retriever: Retriever = field(default_factory=get_retriever)
    recheck_used: bool = False
    handed_off: bool = False

    @property
    def _report_analytes(self) -> list[str]:
        return [a.analyte for a in self.classification.analytes] if self.classification else []

    @property
    def _conv(self) -> dict:
        return self.corpus.templates["conversation"]

    def _recheck_summary(self) -> str:
        """Deterministic restatement of what the rules found, for a dispute recheck."""
        if not self.classification:
            return "I don't have your report open right now."
        flagged = self.classification.flagged
        if not flagged:
            return "I re-ran the check and every value is still within its usual range."
        bits = []
        for a in flagged:
            if a.low is not None and a.high is not None:
                bits.append(f"{a.analyte} is {a.value} {a.unit} against a usual range of {a.low}–{a.high}")
            else:
                bits.append(f"{a.analyte} is flagged for review")
        return "I re-ran the check: " + "; ".join(bits) + "."

    def handle(self, message: str) -> Reply:
        intent = detect_intent(message)
        conv = self._conv

        if self.handed_off:
            # Once handed off, the assistant stays out of the way.
            return Reply(conv["human_handoff"], Intent.REQUEST_HUMAN, escalated=True)

        if intent == Intent.REQUEST_HUMAN:
            self.handed_off = True
            return Reply(conv["human_handoff"], intent, escalated=True)

        if intent == Intent.MEDICAL_ADVICE:
            return Reply(conv["medical_advice_refusal"], intent, offered_doctor=True)

        if intent == Intent.DISPUTE:
            if not self.recheck_used:
                self.recheck_used = True
                text = conv["dispute_recheck"].format(recheck_result=self._recheck_summary())
                return Reply(text, intent, offered_doctor=True)
            # Second dispute: stop the loop, defer to a doctor.
            return Reply(conv["dispute_exhausted"], intent, offered_doctor=True)

        if intent == Intent.BOOKING:
            return Reply(
                "Happy to help — I'll pass this to our booking team and they'll reach out with available slots. 🗓️",
                intent,
            )

        # General follow-up: answer ONLY from the approved library (RAG), else
        # hand to a person. The AI never composes its own medical wording.
        return self._answer_from_library(message, conv)

    def _answer_from_library(self, message: str, conv: dict) -> Reply:
        hits = self.retriever.search(message, boost_analytes=self._report_analytes, k=2)
        if hits and hits[0].score >= ANSWER_THRESHOLD:
            answer = hits[0].text
            # Add a second snippet only if it is also clearly relevant.
            if len(hits) > 1 and hits[1].score >= ANSWER_THRESHOLD:
                answer = answer + " " + hits[1].text
            used = [h.id for h in hits if h.score >= ANSWER_THRESHOLD]
            text = conv["library_answer"].format(answer=answer)
            return Reply(text, Intent.GENERAL, from_library=True, retrieved_ids=used)
        # Nothing approved matched -> decline and offer a person, never guess.
        return Reply(conv["no_library_answer"], Intent.GENERAL, offered_doctor=True)
