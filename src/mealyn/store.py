"""In-memory persistence.

A single process-wide ``Store`` holds households, plans, pantries, preference
signals, and cook reports. Swap the dict backends for a database later; the
orchestrator only touches this interface.
"""

from __future__ import annotations

from collections import defaultdict

from .domain import (
    CookReport,
    Household,
    MealPlan,
    PantryItem,
    PreferenceSignal,
)


class Store:
    def __init__(self) -> None:
        self.households: dict[str, Household] = {}
        self.plans: dict[str, MealPlan] = {}                       # by household id
        self.pantry: dict[str, list[PantryItem]] = defaultdict(list)
        self.preferences: dict[str, list[PreferenceSignal]] = defaultdict(list)
        self.reports: dict[str, list[CookReport]] = defaultdict(list)
        # cook phone -> household id, so inbound cook messages route home
        self.cook_index: dict[str, str] = {}

    # households --------------------------------------------------------- #
    def get_household(self, household_id: str) -> Household | None:
        return self.households.get(household_id)

    def save_household(self, household: Household) -> None:
        self.households[household.id] = household
        if household.cook and household.cook.phone:
            self.cook_index[household.cook.phone] = household.id

    def household_for_cook(self, cook_phone: str) -> Household | None:
        hid = self.cook_index.get(cook_phone)
        return self.households.get(hid) if hid else None

    # plans -------------------------------------------------------------- #
    def get_plan(self, household_id: str) -> MealPlan | None:
        return self.plans.get(household_id)

    def save_plan(self, plan: MealPlan) -> None:
        self.plans[plan.household_id] = plan

    # pantry ------------------------------------------------------------- #
    def seed_pantry(self, household_id: str, items: list[PantryItem]) -> None:
        self.pantry[household_id] = items

    def consume(self, household_id: str, ingredients: list[str]) -> None:
        names = {i.lower() for i in ingredients}
        for item in self.pantry[household_id]:
            if item.name.lower() in names:
                item.quantity = max(0.0, item.quantity - 1.0)

    # preferences -------------------------------------------------------- #
    def add_preference(self, household_id: str, signal: PreferenceSignal) -> None:
        self.preferences[household_id].append(signal)

    def preference_summaries(self, household_id: str) -> list[str]:
        out = []
        for s in sorted(
            self.preferences[household_id],
            key=lambda x: x.confidence * x.recency_weight,
            reverse=True,
        ):
            verb = "avoid" if s.polarity < 0 else "prefer"
            out.append(f"{verb} {s.value} ({s.level.value}, conf {s.confidence:.1f})")
        return out

    # reports ------------------------------------------------------------ #
    def add_report(self, report: CookReport) -> None:
        self.reports[report.household_id].append(report)


STORE = Store()
