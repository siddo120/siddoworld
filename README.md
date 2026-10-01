# Mealyn

AI meal-planning and grocery agent for Indian urban households that employ a
domestic cook. Mealyn lives entirely on **WhatsApp** — both the household and the
cook interact through voice notes — and uses **Claude** as its reasoning brain
(the "Evon" role in the original design).

It coordinates three things that normally fall apart on their own:

- **Planning** — a weekly, diet-aware, cook-skill-aware, budget-aware menu.
- **Ordering** — a Blinkit/Zepto cart paid via a single UPI collect request.
- **Execution** — a morning voice briefing for the cook and an evening report back.

This repo is a **runnable Python app**. The WhatsApp side is real (Meta Cloud API
webhook, text + voice notes); every other rail (Claude, Gnani voice, UPI payment)
degrades to a clean **stub** when its credentials are absent, so the whole agent
loop runs offline for development.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the full agent loop offline (onboarding → plan → pay → cook loop → KPI)
python -m mealyn.demo

# Run the WhatsApp webhook server
uvicorn mealyn.app:app --reload        # GET/POST /webhook, GET /health

# Tests + lint
pytest
ruff check src tests
```

Copy `.env.example` to `.env` and fill in credentials to leave stub mode. The one
that matters most is `ANTHROPIC_API_KEY` — it turns the planning and voice-note
understanding from deterministic stubs into real reasoning (`claude-opus-5-5`).

## How it maps to the design

| Rail / piece | Where | Status |
|---|---|---|
| WhatsApp (text + voice notes) | `whatsapp.py`, `app.py` | Real Cloud API; stub-logs without a token |
| Reasoning brain (Evon) | `brain.py`, `prompts.py` | Claude; deterministic stub without a key |
| Voice STT/TTS (Gnani Prisma/Timbre) | `voice.py` | Interface real; HTTP calls stubbed |
| UPI collect + escalation | `payment.py` | Deeplink + escalation logic; live call stubbed |
| Conversational state machine | `orchestrator.py` | Full |
| Meal planner | `orchestrator.py` + `brain.py` | Full |
| Virtual pantry | `store.py`, `orchestrator.py` | Full |
| Preference learning (4 layers) | `domain.py`, `store.py`, `brain.py` | Full |
| Festival / fasting calendar | `festival.py` | Full (static table) |
| KPI engine (day-indexed completion) | `kpi.py` | Full |

## Agent flow (happy path)

1. Household messages Mealyn → **12 onboarding questions** lock the profile, and
   the cook is registered on their own number.
2. Mealyn generates a **6-day plan** (diet, cook skill, pantry, budget, festivals),
   presents it, and sends a **UPI collect** request for the grocery total.
3. On approval the order is placed and the **virtual pantry** is seeded.
4. Each morning the cook gets a **voice briefing**; each evening their voice note is
   transcribed and classified as **COMPLETE / SKIP / SUBSTITUTE**, updating the
   plan and consuming pantry stock.
5. Mid-week, Mealyn computes **day-indexed completion %** and offers to simplify if
   it's low. The loop restarts the next week with updated preferences.

## Pointing real WhatsApp at it

1. Deploy the server and expose `/webhook` over HTTPS (ngrok works for testing).
2. In the Meta WhatsApp Cloud API dashboard, set the webhook URL and the verify
   token (`MEALYN_WHATSAPP__VERIFY_TOKEN`) — the `GET /webhook` handshake echoes
   the challenge.
3. Set `MEALYN_WHATSAPP__TOKEN` and `MEALYN_WHATSAPP__PHONE_NUMBER_ID`; outbound
   replies then go out as real messages (and voice notes, once Gnani is wired).

See `mealyn-sop.md` for the full end-to-end SOP and the 9 unhappy-path scenarios.
