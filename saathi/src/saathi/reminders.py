"""Repeat-test reminders for chronic patients (Q1 scenarios 6 & 7).

Deterministic tone selection: a test due soon gets a gentle nudge; an overdue
test gets an escalated one. Cadence tracking caps how many reminders go out so
patients are neither spammed nor forgotten.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .corpus import Corpus, get_corpus

MAX_REMINDERS = 3


@dataclass
class ReminderState:
    patient_name: str
    test: str
    due_date: date
    sent_count: int = 0
    stopped: bool = False
    log: list[str] = field(default_factory=list)


def _parse(d) -> date:
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d))


def build_reminder(state: ReminderState, today: Optional[date] = None, corpus: Optional[Corpus] = None) -> Optional[str]:
    """Return the reminder text to send now, or None if nothing should go out."""
    corpus = corpus or get_corpus()
    today = today or date.today()
    if state.stopped or state.sent_count >= MAX_REMINDERS:
        return None

    tmpl = corpus.templates["reminders"]
    overdue = today > state.due_date
    key = "overdue" if overdue else "due_soon"
    text = tmpl[key].format(
        patient_name=state.patient_name,
        test=state.test,
        due_date=state.due_date.isoformat(),
    )
    state.sent_count += 1
    state.log.append(f"{today.isoformat()}: sent {key} (#{state.sent_count})")
    return text


def handle_reply(state: ReminderState, message: str) -> str:
    """Handle a patient's reply to a reminder (BOOK / STOP / other)."""
    m = message.strip().lower()
    if m == "stop":
        state.stopped = True
        return "No problem — I've paused reminders for this test. Reply BOOK anytime to pick it back up."
    if m == "book" or "book" in m:
        state.stopped = True  # booking satisfies the reminder loop
        return "Great — I'll connect you with our booking team to schedule your repeat test. 🗓️"
    return "Reply BOOK to schedule your repeat test, or STOP to pause these reminders."
