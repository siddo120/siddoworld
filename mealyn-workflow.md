# Mealyn — Workflow Description (for "Describe Your Workflow")

Paste the text between the lines into the workflow box, then click
**Generate Workflow**. It is ~3,300 characters (under the 5,000 limit).

---

Mealyn is a voice-only WhatsApp meal-planning and grocery agent for Indian households that employ a domestic cook. All user interaction is WhatsApp voice notes using gnani_prisma (speech-to-text), gnani_timbre (text-to-speech), and gnani_evon (reasoning). Two users — the household owner and the cook — on separate numbers via whatsapp.

Onboarding: Collect 12 answers from the household over voice notes; transcribe with gnani_prisma, parse with gnani_evon, and lock the profile (household size, diet, budget, cuisine, fasting and religious calendar, cook name and number). Register the cook on their own number; send a voice note and capture their language and dialect from the reply.

Every Sunday morning: Use gnani_evon to generate a 5-6 day meal plan constrained by diet, cook skill ceiling, pantry state, budget, and upcoming festivals (cross-check national and religious holidays). Build the Blinkit or Zepto cart and compute the total. If the cart is over budget by more than 15 percent, offer voice substitutions before presenting it. Send the household a voice plan summary and a UPI collect request via paytm, google_pay, or phonepe. When the household approves payment, place the Blinkit order; Delhivery handles dispatch and tracking. Seed the virtual pantry from the first order. If payment is not authorized, send a voice reminder; on a second miss in the same month, open a voice conversation with cart editing and escalate to the household user.

Every day at 7 AM: Send the cook a voice note with today's dish via gnani_timbre and whatsapp. The night before any new dish, send a step-by-step recipe voice note.

Every evening: When the cook sends a voice note, transcribe with gnani_prisma and classify intent with gnani_evon as COMPLETE, SKIP, or SUBSTITUTE; mark the dish and subtract the ingredients of completed dishes from the pantry. If the cook misses 3 consecutive reports, regenerate the mid-week plan and send a structured voice feedback request. If the cook misses 2 consecutive reports, ask the household whether the cook is available, mark the day untracked, and exclude it from KPIs.

Every Wednesday: Calculate the day-indexed completion percentage (each dish checked against its intended date plus or minus 24 hours, counting only days with a cook report); target above 60 percent. If completion is below 40 percent for 3 days, run a mid-week check-in and offer plan simplification. Run a proactive consumption check and an OAuth delta check (total Blinkit orders minus Mealyn-placed orders) to detect unplanned self-ordering.

Every 2 weeks: Ask the cook via voice note to confirm what is physically in the kitchen, and reset the pantry model to ground truth.

Preference learning: Log every edit, deletion, or voice complaint at 4 levels — ingredient, dish, cuisine, complexity — each with a confidence score and recency weight; voice notes with explicit reasons get double weight. One deletion is a weak signal; three is a strong signal. If plan edits are frequent, confirm with the household before regenerating.

The following Sunday: If completion was good, generate the Week 2 plan with updated preferences and present it for approval; a second approval without major edits is the key retention signal, and the loop restarts.

Human-in-the-loop: Escalate to the household user for payment-not-authorized, frequent plan edits, budget overrun, cook no-show, or pantry conflicts. Escalation chain is household_user then support_team. Confirm all consequential actions (payment, order placement, plan changes) by voice before executing, and never invent pantry contents, order status, or cook reports. Output structured JSON with daily and weekly summaries.

---
