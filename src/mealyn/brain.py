"""The Mealyn reasoning brain — the Gnani Evon role, implemented on Claude.

Every method returns plain Python the orchestrator can act on. When no
``ANTHROPIC_API_KEY`` is configured, each method falls back to a deterministic
stub so the whole agent still runs offline.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date

from .config import Settings, get_settings
from .prompts import (
    EDIT_PREFERENCE_TASK,
    INTENT_TASK,
    MEAL_PLAN_TASK,
    ONBOARDING_PARSE_TASK,
    SYSTEM_PROMPT,
)

log = logging.getLogger("mealyn.brain")

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response."""
    match = _JSON_RE.search(text)
    if not match:
        raise ValueError(f"no JSON object in response: {text[:200]!r}")
    return json.loads(match.group(0))


class Brain:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = None
        if self.settings.brain_live:
            import anthropic  # imported lazily so stub mode needs no package install

            self._client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)

    @property
    def live(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------------ #
    # Low-level completion
    # ------------------------------------------------------------------ #
    def _complete_json(self, task: str, *, max_tokens: int = 4000) -> dict:
        assert self._client is not None
        response = self._client.messages.create(
            model=self.settings.model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": task}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        return _extract_json(text)

    # ------------------------------------------------------------------ #
    # Capabilities
    # ------------------------------------------------------------------ #
    def generate_meal_plan(
        self,
        *,
        days: int,
        week_start: date,
        size: int,
        diet: str,
        budget: int,
        cuisines: list[str],
        fasting: list[str],
        religion: str,
        skill: int,
        pantry: list[str],
        preferences: list[str],
        festivals: list[str],
    ) -> dict:
        if not self.live:
            return self._stub_plan(days)
        task = MEAL_PLAN_TASK.format(
            days=days,
            week_start=week_start.isoformat(),
            size=size,
            diet=diet,
            budget=budget,
            cuisines=", ".join(cuisines) or "any",
            fasting=", ".join(fasting) or "none",
            religion=religion or "unspecified",
            skill=skill,
            pantry=", ".join(pantry) or "empty",
            preferences="\n".join(f"- {p}" for p in preferences) or "- none yet",
            festivals=", ".join(festivals) or "none",
        )
        try:
            return self._complete_json(task)
        except Exception:  # noqa: BLE001 — never crash the loop on a bad completion
            log.exception("meal plan generation failed; using stub")
            return self._stub_plan(days)

    def classify_intent(self, *, dish: str, transcript: str) -> dict:
        if not self.live:
            return self._stub_intent(transcript)
        task = INTENT_TASK.format(dish=dish, transcript=transcript)
        try:
            return self._complete_json(task, max_tokens=500)
        except Exception:  # noqa: BLE001
            log.exception("intent classification failed; using stub")
            return self._stub_intent(transcript)

    def parse_onboarding_answer(
        self, *, step: int, question: str, field: str, transcript: str
    ) -> dict:
        if not self.live:
            return {"value": transcript.strip(), "confidence": 0.5, "reask": False}
        task = ONBOARDING_PARSE_TASK.format(
            step=step, question=question, field=field, transcript=transcript
        )
        try:
            return self._complete_json(task, max_tokens=500)
        except Exception:  # noqa: BLE001
            log.exception("onboarding parse failed; passing transcript through")
            return {"value": transcript.strip(), "confidence": 0.3, "reask": False}

    def extract_preferences(self, *, transcript: str) -> list[dict]:
        if not self.live:
            return []
        task = EDIT_PREFERENCE_TASK.format(transcript=transcript)
        try:
            return self._complete_json(task, max_tokens=800).get("signals", [])
        except Exception:  # noqa: BLE001
            log.exception("preference extraction failed")
            return []

    # ------------------------------------------------------------------ #
    # Deterministic stubs (used when no API key is present)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _stub_plan(days: int) -> dict:
        cuisine = "North Indian"
        menu = [
            ("Dal tadka with jeera rice", ["toor dal", "rice", "cumin", "ghee"], 25, cuisine),
            ("Aloo gobi with roti", ["potato", "cauliflower", "atta", "spices"], 30, cuisine),
            ("Rajma chawal", ["kidney beans", "rice", "onion", "tomato"], 35, cuisine),
            ("Vegetable pulao with raita", ["rice", "mixed veg", "curd"], 30, cuisine),
            ("Palak paneer with roti", ["spinach", "paneer", "atta"], 30, cuisine),
            ("Chole with rice", ["chickpeas", "rice", "onion", "tomato"], 35, cuisine),
        ]
        dishes = []
        total = 0
        for i in range(days):
            name, ings, mins, cuisine = menu[i % len(menu)]
            dishes.append(
                {
                    "name": name,
                    "day_offset": i,
                    "ingredients": ings,
                    "est_minutes": mins,
                    "cuisine": cuisine,
                }
            )
            total += 450
        return {
            "dishes": dishes,
            "estimated_cart_total_inr": total,
            "notes": "Stub plan (no ANTHROPIC_API_KEY set).",
        }

    @staticmethod
    def _stub_intent(transcript: str) -> dict:
        t = transcript.lower()
        # Order matters: a skip phrase ("aaj nahi bana") can also contain "bana".
        if any(w in t for w in ("instead", "ki jagah", "substitut", "replace")):
            return {"intent": "SUBSTITUTE", "substitute_name": "", "confidence": 0.4}
        if any(w in t for w in ("not", "skip", "nahi", "didn't", "couldn't", "no time")):
            return {"intent": "SKIP", "substitute_name": "", "confidence": 0.5}
        if any(w in t for w in ("banaya", "bana", "khaya", "made", "done", "ho gaya", "cooked")):
            return {"intent": "COMPLETE", "substitute_name": "", "confidence": 0.6}
        if t.strip():
            return {"intent": "COMPLETE", "substitute_name": "", "confidence": 0.5}
        return {"intent": "UNCLEAR", "substitute_name": "", "confidence": 0.2}
