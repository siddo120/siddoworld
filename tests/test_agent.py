"""Smoke tests for the Mealyn agent, all in stub mode (no credentials needed)."""

from __future__ import annotations

from datetime import date, datetime, time

from mealyn.domain import ConversationState, CookIntent, DishStatus
from mealyn.festival import festivals_between
from mealyn.kpi import day_indexed_completion
from mealyn.orchestrator import Orchestrator
from mealyn.store import Store

HOUSEHOLD = "910000000001"
COOK = "910000000002"

ANSWERS = [
    "four", "vegetarian", "3000 rupees", "North Indian", "Thursday", "Hindu",
    "no peanuts", "medium", "rajma", "Ramu", COOK, "intermediate",
]


def _onboard() -> Orchestrator:
    orch = Orchestrator(store=Store())
    orch.handle_text(HOUSEHOLD, "hi")
    for ans in ANSWERS:
        orch.handle_text(HOUSEHOLD, ans)
    return orch


def test_onboarding_locks_profile_and_registers_cook():
    orch = _onboard()
    hh = orch.store.get_household(HOUSEHOLD)
    assert hh.size == 4
    assert hh.diet.value == "vegetarian"
    assert hh.weekly_budget_inr == 3000
    assert hh.cook is not None and hh.cook.phone == COOK
    # cook is routable
    assert orch.store.household_for_cook(COOK) is hh
    # a plan was generated and is awaiting approval
    assert hh.state == ConversationState.AWAITING_PLAN_APPROVAL
    assert orch.store.get_plan(HOUSEHOLD) is not None


def test_happy_path_to_active_and_pantry_seeded():
    orch = _onboard()
    orch.handle_text(COOK, "Hindi theek hai")       # cook confirms
    orch.handle_text(HOUSEHOLD, "approve")          # approve plan
    orch.handle_text(HOUSEHOLD, "paid")             # approve payment
    hh = orch.store.get_household(HOUSEHOLD)
    assert hh.state == ConversationState.ACTIVE
    assert orch.store.get_plan(HOUSEHOLD).paid is True
    assert len(orch.store.pantry[HOUSEHOLD]) > 0    # seeded from the order


def test_cook_report_marks_dish_and_consumes_pantry():
    orch = _onboard()
    orch.handle_text(COOK, "ok")
    orch.handle_text(HOUSEHOLD, "approve")
    orch.handle_text(HOUSEHOLD, "paid")
    plan = orch.store.get_plan(HOUSEHOLD)
    dish = plan.dishes[0]
    before = sum(p.quantity for p in orch.store.pantry[HOUSEHOLD])
    # drive a COMPLETE report for that dish's day
    result = orch.brain.classify_intent(dish=dish.name, transcript="banaya, sab khaya")
    assert result["intent"] == CookIntent.COMPLETE.value
    dish.status = DishStatus.COMPLETE
    dish.reported_at = datetime.combine(dish.day, time(19, 0))
    orch.store.consume(HOUSEHOLD, dish.ingredients)
    after = sum(p.quantity for p in orch.store.pantry[HOUSEHOLD])
    assert after < before


def test_kpi_excludes_untracked_days():
    orch = _onboard()
    orch.handle_text(HOUSEHOLD, "approve")
    orch.handle_text(HOUSEHOLD, "paid")
    plan = orch.store.get_plan(HOUSEHOLD)
    d0, d1 = plan.dishes[0], plan.dishes[1]
    # one reported complete, one never reported (untracked -> excluded)
    d0.status = DishStatus.COMPLETE
    d0.reported_at = datetime.combine(d0.day, time(19, 0))
    res = day_indexed_completion(plan, as_of=d1.day)
    assert res.tracked_days == 1          # only the reported day counts
    assert res.percentage == 100.0


def test_festival_calendar_is_religion_aware():
    diwali = festivals_between(date(2026, 10, 18), 6, religion="hindu")
    assert any("Diwali" in f for f in diwali)
    none_for_christian = festivals_between(date(2026, 10, 18), 6, religion="christian")
    assert not any("Diwali" in f for f in none_for_christian)
