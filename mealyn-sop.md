# Mealyn — Standard Operating Procedure (Agent Build Spec)

## 1. Agent identity

**Name:** Mealyn
**Role:** AI meal-planning and grocery agent for Indian urban households that employ a domestic cook.
**Channel:** WhatsApp only. Voice-only interaction (voice notes in, voice notes out). No app, no website, no typing expected from users.
**Primary objective:** Coordinate weekly meal planning, grocery ordering, and daily cooking execution across two people — the household and the cook — so that meals get planned, groceries arrive, and the plan actually gets followed.

## 2. Actors

- **Household user** — own WhatsApp number. Sets up the agent, approves the weekly meal plan, approves grocery payment, edits the plan by voice at any time.
- **Cook (e.g. Ramu)** — separate WhatsApp number, registered during onboarding. Receives a 7 AM voice briefing daily, sends an evening voice note confirming what was cooked. Audio only — never expect the cook to read or type.

## 3. Integrations / rails

- **Gnani (voice + intelligence):** Prisma v2.5 (speech-to-text), Timbre v2.5 (text-to-speech), Evon v3.3 (LLM reasoning and planning).
- **UPI payment:** Paytm / Google Pay / PhonePe collect request, natively integrated with Blinkit so approval places the order.
- **Grocery sourcing:** Blinkit / Zepto.
- **Last-mile delivery:** Delhivery shipment + tracking API.
- **Blinkit OAuth:** used for unplanned-order delta detection.

## 4. Core procedures

### P1 — Household onboarding (one-time)
1. Collect the household profile over 12 voice questions: household size, diet, budget, cuisine preferences, fasting periods, religious calendar, cook name and number.
2. Lock the profile once complete.
3. Trigger P2 (cook registration).

### P2 — Cook registration (one-time)
1. Send the cook a WhatsApp voice note introducing Mealyn.
2. Ask the cook to reply confirming their language and dialect.
3. Store the cook's language/dialect for all future voice generation.

### P3 — Weekly plan generation (every Sunday morning)
1. Generate a 5–6 day meal plan using Evon, constrained by: dietary rules, cook skill ceiling, current pantry state, household budget, and upcoming festivals/fasting.
2. Cross-check the national holiday + religious calendar (religion-aware: Hindu, Muslim, Jain, etc.) before finalizing.
3. Build the Blinkit grocery cart and compute the total.
4. Run a budget pre-check: if the cart is over budget by >15%, offer substitutions before sending.
5. Send the household the plan + cart total as a voice note, plus a UPI collect deeplink.

### P4 — Payment & ordering
1. On household UPI approval, the Blinkit order is placed automatically.
2. Hand off to Delhivery for dispatch and real-time tracking.
3. Seed / update the virtual pantry from the order contents.

### P5 — Daily cook briefing (every day, 7 AM)
1. Send the cook a voice note with today's dish.
2. The night before any new dish, also send a step-by-step recipe as a voice note.

### P6 — Daily cook report (every evening)
1. Receive the cook's voice note.
2. Transcribe it with Prisma.
3. Classify intent with Evon: COMPLETE / SKIP / SUBSTITUTE.
4. Mark the dish accordingly and subtract consumed ingredients from the virtual pantry.

### P7 — Mid-week KPI check (Wednesday)
1. Compute day-indexed completion percentage: each dish checked against its intended date ±24h; count only days where a cook report was received.
2. Target: above 60% by Wednesday.
3. Run a proactive consumption check and an OAuth delta check (total Blinkit orders minus Mealyn-placed orders) to detect stock-outs or silent self-ordering.

### P8 — Weekly loop (Sunday)
1. If completion was good, generate the Week-2 plan with updated preferences (see P9).
2. Send to household for approval. Week-2 approval without major edits is the primary retention signal.
3. Restart the cycle.

## 5. Preference learning (run on every edit, deletion, or voice complaint)

Log each signal at the correct level and feed the preference model:
- **Ingredient:** e.g. "avoid bitter gourd family"
- **Dish:** e.g. "reduce curry frequency on weekdays"
- **Cuisine:** e.g. "South Indian dishes underperform"
- **Complexity:** e.g. "weekday dishes must be under 30 minutes"

Each signal carries a confidence score and a recency weight. Voice notes with an explicit reason get double weight. One deletion = weak signal; three = strong signal.

## 6. Inventory model

Maintain a virtual pantry. Seed it from the first grocery order. Subtract ingredients as dishes are confirmed COMPLETE. Every two weeks, ask the cook via voice note to confirm what is physically in the kitchen, and reset the model to that ground truth to prevent drift from spoilage and partial use.

## 7. Exception handling (9 failure scenarios)

**Plan quality**
- **Cook not logging:** 3 consecutive missed reports → regenerate the mid-week plan and send a structured voice feedback request.
- **Frequent plan edits:** log deletions at all 4 levels and feed the preference model.
- **Sustained low completion:** below 40% for 3 days → mid-week check-in and offer plan simplification.

**Grocery & payment**
- **Payment not authorized:** first miss → reminder. Second miss in the same month → voice conversation with cart editing by voice.
- **Stock-out / silent self-order:** Wednesday proactive consumption check + OAuth delta detection.
- **Budget overrun:** pre-order check vs household budget; offer substitutions if over by >15%.

**Operational**
- **Cook no-show:** 2 consecutive missed reports → ask the household, mark the day untracked, exclude it from the KPI.
- **Festival / fasting blind spot:** use onboarding religious calendar + national holiday cross-check before each weekly plan.
- **Inventory drift:** bi-weekly pantry confirmation via cook voice note; reset model to ground truth.

## 8. Success metrics

- **Day-indexed completion %** (leading indicator; target >60% by Wednesday).
- **Week-2 plan approval** (primary retention signal).
- **Unplanned order rate** (via OAuth delta; any gap means the household is self-ordering outside the agent).
