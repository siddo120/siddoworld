"""The Mealyn orchestrator — the conversational state machine and agent loop.

It routes every inbound WhatsApp message (household or cook), advances onboarding,
generates and offers weekly plans, drives payment, sends the daily cook briefing,
classifies the cook's evening report, updates the pantry and preference model, and
runs the mid-week KPI checkpoint. External rails are injected so the whole thing
runs offline in stub mode.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from .brain import Brain
from .domain import (
    ConversationState,
    Cook,
    CookIntent,
    CookReport,
    Diet,
    Dish,
    DishStatus,
    Household,
    MealPlan,
    PantryItem,
    PreferenceLevel,
    PreferenceSignal,
)
from .festival import festivals_between
from .kpi import day_indexed_completion
from .payment import PaymentService
from .store import STORE, Store
from .voice import VoicePipeline
from .whatsapp import InboundMessage, WhatsAppClient

log = logging.getLogger("mealyn.orchestrator")

PLAN_DAYS = 6

# (field, question) — the 12 onboarding questions that lock the household profile.
ONBOARDING_QUESTIONS: list[tuple[str, str]] = [
    ("size", "How many people are we cooking for at home?"),
    ("diet", "Is the household vegetarian, non-vegetarian, eggetarian, vegan, or Jain?"),
    ("weekly_budget_inr", "What is your weekly grocery budget in rupees?"),
    ("cuisines", "Which cuisines do you enjoy most? For example North Indian, South Indian."),
    ("fasting_days", "Are there any weekly fasting days? For example Tuesday or Thursday."),
    ("religion", "Which festivals should I keep in mind? You can tell me your tradition."),
    ("allergies", "Any allergies or ingredients to always avoid?"),
    ("spice_level", "How spicy do you like your food — mild, medium, or hot?"),
    ("favourite_dishes", "Any favourite dishes you'd like to see often?"),
    ("cook_name", "What is your cook's name?"),
    ("cook_phone", "What is your cook's WhatsApp number?"),
    ("cook_skill", "How experienced is your cook — beginner, intermediate, or advanced?"),
]

_DIET_WORDS = {
    "veg": Diet.VEG, "vegetarian": Diet.VEG,
    "non": Diet.NONVEG, "nonveg": Diet.NONVEG, "non-vegetarian": Diet.NONVEG,
    "egg": Diet.EGGETARIAN, "eggetarian": Diet.EGGETARIAN,
    "vegan": Diet.VEGAN, "jain": Diet.JAIN,
}
_SKILL_WORDS = {"beginner": 2, "intermediate": 3, "advanced": 4}


class Orchestrator:
    def __init__(
        self,
        store: Store | None = None,
        brain: Brain | None = None,
        whatsapp: WhatsAppClient | None = None,
        voice: VoicePipeline | None = None,
        payment: PaymentService | None = None,
    ) -> None:
        self.store = store or STORE
        self.brain = brain or Brain()
        self.whatsapp = whatsapp or WhatsAppClient()
        self.voice = voice or VoicePipeline()
        self.payment = payment or PaymentService()

    # ------------------------------------------------------------------ #
    # Inbound entry points
    # ------------------------------------------------------------------ #
    def handle_inbound(self, msg: InboundMessage) -> None:
        """Entry for a raw WhatsApp message: transcribe audio, then dispatch."""
        if msg.kind == "audio":
            audio = self.whatsapp.download_media(msg.media_id)
            text = self.voice.transcribe(audio)
        elif msg.kind == "text":
            text = msg.text
        else:
            self._say(msg.from_number, "Please send me a voice note and I'll help.")
            return
        self.handle_text(msg.from_number, text)

    def handle_text(self, from_number: str, text: str) -> None:
        """Dispatch a (possibly transcribed) message to household or cook flow."""
        cook_household = self.store.household_for_cook(from_number)
        if cook_household is not None:
            self._handle_cook_message(cook_household, text)
            return
        household = self.store.get_household(from_number) or Household(id=from_number)
        self.store.save_household(household)
        self._handle_household_message(household, text)

    # ------------------------------------------------------------------ #
    # Household flow
    # ------------------------------------------------------------------ #
    def _handle_household_message(self, hh: Household, text: str) -> None:
        if hh.state in (ConversationState.NEW, ConversationState.ONBOARDING):
            self._advance_onboarding(hh, text)
            return
        if hh.state == ConversationState.AWAITING_PLAN_APPROVAL:
            self._handle_plan_response(hh, text)
            return
        if hh.state == ConversationState.AWAITING_PAYMENT:
            self._handle_payment_response(hh, text)
            return
        # Active steady state: treat free-form input as a plan edit / preference.
        self._capture_preference(hh, text)
        self._say(hh.id, "Got it — I've noted that and will use it in your next plan.")

    def _advance_onboarding(self, hh: Household, text: str) -> None:
        if hh.state == ConversationState.NEW:
            hh.state = ConversationState.ONBOARDING
            hh.onboarding_step = 0
            self._say(hh.id, "Welcome to Mealyn! I'll ask a few quick questions.")
            self._ask_onboarding(hh)
            return

        field, question = ONBOARDING_QUESTIONS[hh.onboarding_step]
        parsed = self.brain.parse_onboarding_answer(
            step=hh.onboarding_step + 1, question=question, field=field, transcript=text
        )
        if parsed.get("reask"):
            self._say(hh.id, f"Sorry, could you repeat? {question}")
            return
        self._apply_onboarding_field(hh, field, parsed.get("value"))
        hh.onboarding_step += 1
        self.store.save_household(hh)

        if hh.onboarding_step < len(ONBOARDING_QUESTIONS):
            self._ask_onboarding(hh)
        else:
            self._finish_onboarding(hh)

    def _ask_onboarding(self, hh: Household) -> None:
        _, question = ONBOARDING_QUESTIONS[hh.onboarding_step]
        self._say(hh.id, f"({hh.onboarding_step + 1}/12) {question}")

    def _apply_onboarding_field(self, hh: Household, field: str, value) -> None:
        try:
            if field == "size":
                hh.size = int(_first_int(value, hh.size))
            elif field == "diet":
                hh.diet = _parse_diet(value, hh.diet)
            elif field == "weekly_budget_inr":
                hh.weekly_budget_inr = int(_first_int(value, hh.weekly_budget_inr))
            elif field == "cuisines":
                hh.cuisines = _as_list(value) or hh.cuisines
            elif field == "fasting_days":
                hh.fasting_days = _as_list(value)
            elif field == "religion":
                hh.religion = str(value or "").strip()
            elif field in ("allergies", "spice_level", "favourite_dishes"):
                self._capture_preference(hh, f"{field}: {value}")
            elif field == "cook_name":
                hh.cook = Cook(name=str(value or "Cook"), phone="")
            elif field == "cook_phone":
                phone = _digits(str(value or ""))
                if hh.cook:
                    hh.cook.phone = phone
            elif field == "cook_skill":
                if hh.cook:
                    hh.cook.skill_ceiling = _parse_skill(value, hh.cook.skill_ceiling)
        except Exception:  # noqa: BLE001 — bad parse shouldn't abort onboarding
            log.exception("could not apply onboarding field %s=%r", field, value)

    def _finish_onboarding(self, hh: Household) -> None:
        hh.state = ConversationState.AWAITING_COOK_CONFIRM
        self.store.save_household(hh)
        if hh.cook and hh.cook.phone:
            self.store.save_household(hh)  # registers cook in the index
            self._say(
                hh.cook.phone,
                f"Namaste {hh.cook.name}! This is Mealyn. I'll send you each day's "
                f"dish as a voice note. Please reply with a voice note to confirm your "
                f"language.",
            )
        self._say(
            hh.id,
            "All set! I've messaged your cook. I'll send your first weekly plan now.",
        )
        self.generate_and_offer_plan(hh.id)

    def _handle_plan_response(self, hh: Household, text: str) -> None:
        lowered = text.lower()
        if any(w in lowered for w in ("approve", "ok", "yes", "haan", "go ahead", "confirm")):
            plan = self.store.get_plan(hh.id)
            if plan:
                plan.approved = True
                self.store.save_plan(plan)
            self._request_payment(hh)
        else:
            # An edit: learn from it, regenerate.
            self._capture_preference(hh, text)
            self._say(hh.id, "Understood — updating the plan with that change.")
            self.generate_and_offer_plan(hh.id)

    def _handle_payment_response(self, hh: Household, text: str) -> None:
        lowered = text.lower()
        plan = self.store.get_plan(hh.id)
        if plan and any(w in lowered for w in ("paid", "done", "approved", "yes", "haan")):
            plan.paid = True
            self.store.save_plan(plan)
            self._seed_pantry_from_plan(plan)
            hh.state = ConversationState.ACTIVE
            self.store.save_household(hh)
            self._say(
                hh.id,
                "Payment received — your groceries are on the way via Delhivery. "
                "I'll brief your cook every morning.",
            )
        else:
            action = self.payment.escalation_action(hh.id)
            if action == "voice_cart_edit":
                self._say(
                    hh.id,
                    "No payment yet this is the second time this month. Tell me by "
                    "voice if you'd like to trim the cart and I'll adjust it.",
                )
            else:
                self._say(hh.id, "Just a reminder to approve the grocery payment when you can.")

    # ------------------------------------------------------------------ #
    # Weekly planning + payment
    # ------------------------------------------------------------------ #
    def generate_and_offer_plan(
        self, household_id: str, week_start: date | None = None
    ) -> MealPlan:
        hh = self.store.get_household(household_id)
        if hh is None:
            raise ValueError(f"unknown household {household_id}")
        week_start = week_start or _next_monday()
        skill = hh.cook.skill_ceiling if hh.cook else 3
        result = self.brain.generate_meal_plan(
            days=PLAN_DAYS,
            week_start=week_start,
            size=hh.size,
            diet=hh.diet.value,
            budget=hh.weekly_budget_inr,
            cuisines=hh.cuisines,
            fasting=hh.fasting_days,
            religion=hh.religion,
            skill=skill,
            pantry=[p.name for p in self.store.pantry[household_id]],
            preferences=self.store.preference_summaries(household_id),
            festivals=festivals_between(week_start, PLAN_DAYS, hh.religion),
        )
        dishes = [
            Dish(
                name=d["name"],
                day=week_start + timedelta(days=int(d.get("day_offset", i))),
                ingredients=d.get("ingredients", []),
                est_minutes=int(d.get("est_minutes", 30)),
                cuisine=d.get("cuisine", ""),
            )
            for i, d in enumerate(result.get("dishes", []))
        ]
        total = int(result.get("estimated_cart_total_inr", 0))
        total = self._apply_budget_guard(hh, total)
        plan = MealPlan(
            household_id=household_id, week_start=week_start, dishes=dishes, cart_total_inr=total
        )
        self.store.save_plan(plan)
        hh.state = ConversationState.AWAITING_PLAN_APPROVAL
        self.store.save_household(hh)
        self._say(household_id, self._format_plan(plan))
        return plan

    def _apply_budget_guard(self, hh: Household, total: int) -> int:
        if total > hh.weekly_budget_inr * 1.15:
            self._say(
                hh.id,
                f"Heads up: this cart (Rs {total}) is over your Rs {hh.weekly_budget_inr} "
                f"budget. I'll suggest lighter swaps — tell me if you'd rather keep it.",
            )
        return total

    def _request_payment(self, hh: Household) -> None:
        plan = self.store.get_plan(hh.id)
        if not plan:
            return
        req = self.payment.create_collect(hh.id, plan.cart_total_inr, "Mealyn weekly groceries")
        hh.state = ConversationState.AWAITING_PAYMENT
        self.store.save_household(hh)
        self._say(
            hh.id,
            f"Great! Your grocery total is Rs {plan.cart_total_inr}. "
            f"Approve the UPI request to place the order: {req.deeplink}",
        )

    def _seed_pantry_from_plan(self, plan: MealPlan) -> None:
        names: set[str] = set()
        for dish in plan.dishes:
            names.update(i.lower() for i in dish.ingredients)
        self.store.seed_pantry(
            plan.household_id, [PantryItem(name=n, quantity=1.0) for n in sorted(names)]
        )

    # ------------------------------------------------------------------ #
    # Daily cook loop
    # ------------------------------------------------------------------ #
    def send_daily_briefing(self, household_id: str, on: date | None = None) -> None:
        hh = self.store.get_household(household_id)
        plan = self.store.get_plan(household_id)
        if not hh or not hh.cook or not plan:
            return
        on = on or date.today()
        dish = next((d for d in plan.dishes if d.day == on), None)
        if dish is None:
            return
        self._say(
            hh.cook.phone,
            f"Good morning {hh.cook.name}! Today's dish is {dish.name} "
            f"(about {dish.est_minutes} minutes). Send me a voice note tonight to "
            f"tell me how it went.",
        )

    def _handle_cook_message(self, hh: Household, text: str) -> None:
        if hh.cook and not hh.cook.confirmed:
            hh.cook.confirmed = True
            self.store.save_household(hh)
            self._say(hh.cook.phone, "Thank you! You're all set. Talk to you each morning.")
            return
        plan = self.store.get_plan(hh.id)
        today = date.today()
        dish = next((d for d in (plan.dishes if plan else []) if d.day == today), None)
        dish_name = dish.name if dish else "today's dish"
        result = self.brain.classify_intent(dish=dish_name, transcript=text)
        intent = CookIntent(result.get("intent", "UNCLEAR"))
        self.store.add_report(
            CookReport(
                household_id=hh.id,
                dish_name=dish_name,
                intent=intent,
                substitute_name=result.get("substitute_name", ""),
                raw_transcript=text,
            )
        )
        if dish is not None:
            dish.reported_at = datetime.utcnow()
            if intent == CookIntent.COMPLETE:
                dish.status = DishStatus.COMPLETE
                self.store.consume(hh.id, dish.ingredients)
            elif intent == CookIntent.SKIP:
                dish.status = DishStatus.SKIP
            elif intent == CookIntent.SUBSTITUTE:
                dish.status = DishStatus.SUBSTITUTE
            self.store.save_plan(plan)
        self._say(hh.cook.phone, "Got it, thank you! Noted for today.")

    # ------------------------------------------------------------------ #
    # KPI checkpoint (Wednesday)
    # ------------------------------------------------------------------ #
    def run_kpi_checkpoint(self, household_id: str, as_of: date | None = None) -> float:
        plan = self.store.get_plan(household_id)
        hh = self.store.get_household(household_id)
        if not plan or not hh:
            return 0.0
        as_of = as_of or date.today()
        result = day_indexed_completion(plan, as_of)
        if result.below_target:
            self._say(
                household_id,
                f"Quick check-in: completion is {result.percentage:.0f}% so far. "
                f"Would you like me to simplify the rest of the week?",
            )
        return result.percentage

    # ------------------------------------------------------------------ #
    # Preferences
    # ------------------------------------------------------------------ #
    def _capture_preference(self, hh: Household, text: str) -> None:
        signals = self.brain.extract_preferences(transcript=text)
        for s in signals:
            try:
                self.store.add_preference(
                    hh.id,
                    PreferenceSignal(
                        level=PreferenceLevel(s.get("level", "dish")),
                        value=str(s.get("value", "")).strip(),
                        polarity=int(s.get("polarity", -1)),
                        confidence=0.6 if s.get("reason") else 0.3,
                        reason=str(s.get("reason", "")),
                    ),
                )
            except Exception:  # noqa: BLE001
                log.exception("could not store preference signal %r", s)

    # ------------------------------------------------------------------ #
    # Output
    # ------------------------------------------------------------------ #
    def _say(self, to: str, text: str, language: str = "hi") -> None:
        """Voice-first reply: send text, and a voice note too when rails are live."""
        self.whatsapp.send_text(to, text)
        if self.whatsapp.live and self.voice.live:
            audio = self.voice.synthesize(text, language=language)
            media_id = self.whatsapp.upload_media(audio)
            self.whatsapp.send_voice(to, media_id)

    @staticmethod
    def _format_plan(plan: MealPlan) -> str:
        lines = [f"Here's your plan for the week of {plan.week_start.isoformat()}:"]
        for d in plan.dishes:
            lines.append(f"- {d.day.strftime('%a')}: {d.name} ({d.est_minutes} min)")
        lines.append(f"Grocery total: Rs {plan.cart_total_inr}.")
        lines.append("Say 'approve' to order, or tell me any changes.")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Small parsing helpers
# --------------------------------------------------------------------------- #
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _first_int(value, default: int) -> int:
    import re

    if isinstance(value, int):
        return value
    text = str(value).lower()
    m = re.search(r"\d+", text)
    if m:
        return int(m.group(0))
    # Word numbers, with Indian/English multipliers ("three thousand" -> 3000).
    base = next((n for w, n in _NUMBER_WORDS.items() if re.search(rf"\b{w}\b", text)), None)
    multiplier = 1
    if any(w in text for w in ("thousand", "hazaar", "hajar")):
        multiplier = 1000
    elif "lakh" in text:
        multiplier = 100_000
    if base is not None or multiplier > 1:
        return (base or 1) * multiplier
    return default


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    parts = str(value or "").replace(" and ", ",").split(",")
    return [p.strip() for p in parts if p.strip() and p.strip().lower() != "none"]


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _parse_diet(value, default: Diet) -> Diet:
    text = str(value or "").lower()
    for word, diet in _DIET_WORDS.items():
        if word in text:
            return diet
    return default


def _parse_skill(value, default: int) -> int:
    text = str(value or "").lower()
    for word, lvl in _SKILL_WORDS.items():
        if word in text:
            return lvl
    return _first_int(value, default)


def _next_monday(today: date | None = None) -> date:
    today = today or date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)
