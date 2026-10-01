"""UPI collect request (Paytm / Google Pay / PhonePe) with escalation logic.

Generates a UPI deeplink the household taps to approve the weekly grocery cart.
Live integration is stubbed; the escalation state (reminders, second-miss voice
conversation) is real and drives the orchestrator's unhappy path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import quote

from .config import PaymentSettings, get_settings


@dataclass
class CollectRequest:
    household_id: str
    amount_inr: int
    note: str
    deeplink: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    authorized: bool = False
    reminders_sent: int = 0


class PaymentService:
    def __init__(self, settings: PaymentSettings | None = None) -> None:
        self.settings = settings or get_settings().payment
        # household id -> list of this month's collect requests (for escalation)
        self._history: dict[str, list[CollectRequest]] = {}

    def create_collect(self, household_id: str, amount_inr: int, note: str) -> CollectRequest:
        payee = self.settings.merchant_id or "mealyn@upi"
        deeplink = (
            f"upi://pay?pa={quote(payee)}&pn=Mealyn"
            f"&am={amount_inr}&cu=INR&tn={quote(note)}"
        )
        req = CollectRequest(household_id, amount_inr, note, deeplink)
        self._history.setdefault(household_id, []).append(req)
        return req

    def misses_this_month(self, household_id: str) -> int:
        now = datetime.utcnow()
        return sum(
            1
            for r in self._history.get(household_id, [])
            if not r.authorized
            and r.created_at.year == now.year
            and r.created_at.month == now.month
        )

    def escalation_action(self, household_id: str) -> str:
        """What to do on a payment miss (SOP: first = reminder, second = voice convo)."""
        return "voice_cart_edit" if self.misses_this_month(household_id) >= 2 else "reminder"
