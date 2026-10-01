"""Domain model: the entities and enums Mealyn reasons over."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Diet(StrEnum):
    VEG = "vegetarian"
    NONVEG = "non_vegetarian"
    EGGETARIAN = "eggetarian"
    VEGAN = "vegan"
    JAIN = "jain"


class Actor(StrEnum):
    HOUSEHOLD = "household"
    COOK = "cook"


class ConversationState(StrEnum):
    """Where a household is in the Mealyn lifecycle (the state machine)."""

    NEW = "new"
    ONBOARDING = "onboarding"            # answering the 12 setup questions
    AWAITING_COOK_CONFIRM = "awaiting_cook_confirm"
    ACTIVE = "active"                    # steady-state weekly/daily loop
    AWAITING_PLAN_APPROVAL = "awaiting_plan_approval"
    AWAITING_PAYMENT = "awaiting_payment"
    PAUSED = "paused"


class DishStatus(StrEnum):
    PLANNED = "planned"
    COMPLETE = "complete"
    SKIP = "skip"
    SUBSTITUTE = "substitute"
    UNTRACKED = "untracked"


class CookIntent(StrEnum):
    """What the cook's evening voice note means."""

    COMPLETE = "COMPLETE"
    SKIP = "SKIP"
    SUBSTITUTE = "SUBSTITUTE"
    UNCLEAR = "UNCLEAR"


class PreferenceLevel(StrEnum):
    INGREDIENT = "ingredient"
    DISH = "dish"
    CUISINE = "cuisine"
    COMPLEXITY = "complexity"


# --------------------------------------------------------------------------- #
# Entities
# --------------------------------------------------------------------------- #
class Cook(BaseModel):
    name: str
    phone: str
    language: str = "hi"
    dialect: str = ""
    skill_ceiling: int = 3            # 1 (basic) .. 5 (advanced)
    confirmed: bool = False


class Household(BaseModel):
    id: str                           # the household's WhatsApp number
    size: int = 2
    diet: Diet = Diet.VEG
    weekly_budget_inr: int = 3000
    cuisines: list[str] = Field(default_factory=lambda: ["North Indian"])
    fasting_days: list[str] = Field(default_factory=list)
    religion: str = ""
    cook: Cook | None = None
    state: ConversationState = ConversationState.NEW
    onboarding_step: int = 0          # 0..12
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Dish(BaseModel):
    name: str
    day: date
    ingredients: list[str] = Field(default_factory=list)
    est_minutes: int = 30
    cuisine: str = ""
    status: DishStatus = DishStatus.PLANNED
    reported_at: datetime | None = None


class MealPlan(BaseModel):
    household_id: str
    week_start: date
    dishes: list[Dish] = Field(default_factory=list)
    cart_total_inr: int = 0
    approved: bool = False
    paid: bool = False


class PantryItem(BaseModel):
    name: str
    quantity: float = 1.0
    unit: str = "unit"


class PreferenceSignal(BaseModel):
    level: PreferenceLevel
    value: str                        # e.g. "bitter gourd", "curry on weekdays"
    polarity: int = -1                # -1 avoid, +1 prefer
    confidence: float = 0.3
    recency_weight: float = 1.0
    reason: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CookReport(BaseModel):
    household_id: str
    dish_name: str
    intent: CookIntent
    substitute_name: str = ""
    raw_transcript: str = ""
    received_at: datetime = Field(default_factory=datetime.utcnow)
