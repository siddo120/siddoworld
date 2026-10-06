# Saathi — RAG lab-report assistant (prototype)

A working prototype of the WhatsApp-first AI assistant from the *Dr Lal PathLabs*
pitch. It explains lab reports in plain language, routes abnormal/critical results
to humans, and reminds chronic patients about repeat tests — **without ever
diagnosing or giving medical advice.**

> ⚠️ Prototype with **synthetic** data only. Not for clinical use. The reference
> ranges, templates and sample reports are illustrative.

## The core idea (why this is safe)

The pitch's key architectural decision is made literal here:

```
                 ┌─────────────────────┐
  lab report ──▶ │  RULE ENGINE        │  deterministic, no LLM
                 │  (reference ranges) │  → tier: normal / borderline /
                 └──────────┬──────────┘        abnormal / critical /
                            │                    grey-zone / uncovered
                 ┌──────────▼──────────┐
                 │  ROUTER             │  tier → action + confidence band
                 └──────────┬──────────┘
            autonomous ◀────┼────▶ escalate / human review
                            │
                 ┌──────────▼──────────┐
                 │  RAG + LLM          │  retrieve approved snippets, then
                 │  (explanation only) │  phrase — never decides severity
                 └─────────────────────┘
```

**Classification is deterministic; the LLM only phrases an explanation for a tier
the rules already decided.** That's what narrows the failure surface (Q2
"prevention") and makes every decision auditable.

## Run it

No dependencies required to run (pure Python stdlib, 3.10+).

```bash
cd saathi/src
python -m saathi.demo            # run every sample report through the engine
python -m saathi.demo RPT-1004   # one report

python -m saathi.server          # web chat UI at http://127.0.0.1:8000
PORT=9000 python -m saathi.server
```

Open the server URL, pick a sample report, and chat back as the patient. Hit
**"Why?"** to see the audit trail: the per-analyte rule-engine verdict, the
routing decision, and which RAG snippets were retrieved.

Things to try in the chat:
- *"should I stop my medication?"* → declined, offers a doctor (Q1 S8)
- *"are you sure? that seems wrong"* → one recheck, then defers to a doctor (S9)
- *"can I talk to a human"* → immediate handoff (S12)
- type `remind` on a chronic patient → repeat-test reminder (S6/S7)

## Tests

```bash
cd saathi
pip install pytest
pytest
```

23 tests cover the rule engine (every tier, sex-specific ranges, alias
resolution, critical precedence, multi-abnormal → grey-zone), the router,
retrieval scoping, the conversation boundaries, and the reminder cadence.

## Layout

| File | Role |
|------|------|
| `rules.py` | Deterministic classification engine (the safety core) |
| `router.py` | Tier → action + confidence band (Q1 / Q4) |
| `retrieval.py` | Pure-Python TF-IDF retriever over the knowledge base (the "R") |
| `llm.py` | Pluggable provider: deterministic `MockProvider` + `ClaudeProvider` seam |
| `explain.py` | Retrieve → ground → draft the WhatsApp message (the "G") |
| `conversation.py` | Dispute cap, human handoff, advice refusal (Q1 S8/S9/S12) |
| `reminders.py` | Chronic-patient repeat-test reminders (Q1 S6/S7) |
| `engine.py` | Orchestrator: `ingest` (explains) and `audit` (ground truth) |
| `server.py` | stdlib HTTP server + JSON API |
| `web/` | WhatsApp-style chat UI |
| `data/` | Synthetic reference ranges, knowledge base, templates, sample reports |

## Plugging in real Claude

The mock returns the pre-approved template verbatim (safe default). To have
Claude rephrase within the same guardrails:

```bash
export ANTHROPIC_API_KEY=sk-...
export SAATHI_LLM=claude
pip install anthropic
python -m saathi.server
```

The provider is grounded strictly in the template + retrieved snippets, and
falls back to the deterministic rendering on any error — a message always goes
out, and the tier/numbers/escalation never depend on the model.

## What's deliberately out of scope for the prototype

Real LIS integration, the WhatsApp Business API, a DPDPA-compliant India-resident
datastore, and medical-director template sign-off are production concerns from
the pitch (Q3). The architecture leaves clean seams for each.
