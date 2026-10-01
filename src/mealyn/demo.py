"""End-to-end offline demo of the Mealyn agent loop.

Runs the whole happy path against the stub rails (no credentials needed):
onboarding -> cook registration -> weekly plan -> approval -> payment ->
daily briefing -> cook report -> KPI checkpoint. Every "sent" message is logged.

Run: ``python -m mealyn.demo``
"""

from __future__ import annotations

import logging
from datetime import date

from .orchestrator import ONBOARDING_QUESTIONS, Orchestrator
from .store import Store

logging.basicConfig(level=logging.INFO, format="%(message)s")

HOUSEHOLD = "919000000001"
COOK = "919000000002"

ANSWERS = [
    "We are four people",            # size
    "Vegetarian",                    # diet
    "Three thousand rupees",         # budget
    "North Indian and South Indian",  # cuisines
    "Thursday",                      # fasting
    "Hindu",                         # religion
    "No peanuts please",             # allergies
    "Medium spicy",                  # spice
    "We love rajma and dosa",        # favourites
    "Ramu",                          # cook name
    COOK,                            # cook phone
    "Intermediate",                  # cook skill
]


def main() -> None:
    orch = Orchestrator(store=Store())  # fresh store for a clean demo

    print("\n=== 1. Household says hello (onboarding starts) ===")
    orch.handle_text(HOUSEHOLD, "Hi")

    print("\n=== 2. Household answers the 12 questions ===")
    for field_answer, (_field, _q) in zip(ANSWERS, ONBOARDING_QUESTIONS, strict=True):
        orch.handle_text(HOUSEHOLD, field_answer)

    print("\n=== 3. Cook confirms language (voice note) ===")
    orch.handle_text(COOK, "Haan ji, Hindi theek hai")

    print("\n=== 4. Household approves the plan ===")
    orch.handle_text(HOUSEHOLD, "Approve")

    print("\n=== 5. Household approves payment ===")
    orch.handle_text(HOUSEHOLD, "Paid")

    print("\n=== 6. Daily briefing for the first two planned days ===")
    plan = orch.store.get_plan(HOUSEHOLD)
    first_days = sorted({d.day for d in plan.dishes})[:2]
    for day in first_days:
        orch.send_daily_briefing(HOUSEHOLD, on=day)
        orch.store.save_household(orch.store.get_household(HOUSEHOLD))

    print("\n=== 7. Cook reports back (COMPLETE, then SKIP) ===")
    # Simulate reports landing on their respective days by reporting as-of each day.
    _report_on_day(orch, first_days[0], "Dal banaya, sab ne khaya")  # complete
    _report_on_day(orch, first_days[1], "Aaj nahi bana, time nahi mila")  # skip

    print("\n=== 8. Wednesday KPI checkpoint ===")
    pct = orch.run_kpi_checkpoint(HOUSEHOLD, as_of=first_days[-1])
    print(f"\nDay-indexed completion so far: {pct:.0f}%")


def _report_on_day(orch: Orchestrator, day: date, transcript: str) -> None:
    """Mark the given day's dish as reported by driving the cook handler for that day."""
    plan = orch.store.get_plan(HOUSEHOLD)
    dish = next((d for d in plan.dishes if d.day == day), None)
    if dish is None:
        return
    result = orch.brain.classify_intent(dish=dish.name, transcript=transcript)
    from .domain import CookIntent, CookReport, DishStatus

    intent = CookIntent(result.get("intent", "UNCLEAR"))
    dish.reported_at = _as_dt(day)
    dish.status = {
        CookIntent.COMPLETE: DishStatus.COMPLETE,
        CookIntent.SKIP: DishStatus.SKIP,
        CookIntent.SUBSTITUTE: DishStatus.SUBSTITUTE,
    }.get(intent, DishStatus.PLANNED)
    if intent == CookIntent.COMPLETE:
        orch.store.consume(HOUSEHOLD, dish.ingredients)
    orch.store.add_report(
        CookReport(
            household_id=HOUSEHOLD,
            dish_name=dish.name,
            intent=intent,
            raw_transcript=transcript,
        )
    )
    orch.store.save_plan(plan)
    print(f"  [{day.strftime('%a')}] '{dish.name}' -> {intent.value}")


def _as_dt(day: date):
    from datetime import datetime, time

    return datetime.combine(day, time(19, 0))


if __name__ == "__main__":
    main()
