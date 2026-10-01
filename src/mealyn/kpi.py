"""KPI engine — the leading indicators from the Mealyn SOP.

- Day-indexed completion %: each dish checked against its intended date +/- 24h,
  counting only days a cook report was received. Target > 60% by Wednesday.
- Low-completion detection for the mid-week check-in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .domain import DishStatus, MealPlan


@dataclass
class CompletionResult:
    tracked_days: int        # days a cook report was received
    completed: int           # of those, how many were COMPLETE on time
    percentage: float        # completed / tracked_days * 100 (0 if no tracked days)

    @property
    def below_target(self) -> bool:
        return self.tracked_days > 0 and self.percentage < 60.0


def day_indexed_completion(plan: MealPlan, as_of: date) -> CompletionResult:
    """Completion over dishes whose intended day is on or before ``as_of``."""
    tracked = 0
    completed = 0
    for dish in plan.dishes:
        if dish.day > as_of:
            continue
        if dish.status == DishStatus.UNTRACKED or dish.reported_at is None:
            continue  # no cook report that day -> excluded from the denominator
        tracked += 1
        if dish.status == DishStatus.COMPLETE:
            completed += 1
    pct = (completed / tracked * 100.0) if tracked else 0.0
    return CompletionResult(tracked_days=tracked, completed=completed, percentage=pct)
