# Dream11 AI Commercial Engine — Demo MVP

A working, interactive demo of the product described in the PRD *"Dream11 AI
Commercial Engine — PRD & Unit Economics."* It is **one AI matching/optimization
engine driving two revenue surfaces**, plus the unit-economics model that makes the
case to the CFO.

Everything runs client-side in a single file — open `index.html` in any browser.
No build step, no server, no dependencies.

```bash
# from the repo root
open dream11-demo/index.html          # macOS
xdg-open dream11-demo/index.html      # Linux
# or just double-click the file
```

## What's in it (and why — the PRD's priority order)

| Tab | What it demonstrates | PRD section |
|-----|----------------------|-------------|
| **The bet** | Value proposition + the "one engine, two surfaces" thesis | §1, §2 |
| **League sponsorships** (Surface A) | The *proven* bet — scoring engine → cohort → auto-creative → consent → brand dashboard | §3 Surface A |
| **Ad-yield** (Surface B) | The *benchmark-backed* bet — performance analysis → recommendations → before/after ROI | §3 Surface B |
| **Unit economics** | The number the CFO asked for — live Season-1 P&L + the honest scale check | §4 |

Surface A leads because the PRD prioritizes it: it has the real 2.5× pilot proof and
protects private leagues (the asset Community said users won't give up).

## The engines are real

The matching and optimization logic actually runs — it is not a slideshow:

- **League scoring** (`scoreLeague`) ranks a population of 640 synthetic private
  leagues on brand-fit from four weighted signals — **affinity (0.40) · engagement
  (0.25) · size (0.20) · region (0.15)** — with a cold-start discount for leagues
  under two weeks old (the "where it breaks" caveat from the PRD). Pick a different
  brand and the whole ranking, cohort, and creative regenerate.
- **Ad-yield optimization** (`analyzeAdv`) scores every creator × segment ×
  match-moment combination from an advertiser's history, then reallocates the same
  budget toward the best combinations and reports the yield lift.
- **Unit economics** recomputes the full P&L live from six draggable assumptions.
  Defaults reproduce the PRD's Season-1 figures: **₹5.15cr net new profit at ~95%
  margin**, inside the PRD's stated ₹4.7–7.3cr / 93–96% range.

## Honest about the data

- League and advertiser data is **synthetic and illustrative**, generated from a
  fixed seed so the demo is identical on every load.
- Brand names (FinVest, Luxe Pay, PlayZone, ChargeUp, QuickBite, LearnLadder,
  DriveNow) are **fictional stand-ins** for the brand archetypes a real sponsor would
  fall into — no real company is implied or endorsed.
- The **economics defaults are the PRD's real case figures**; drag the sliders to
  pressure-test them, which is exactly what §4.7's open questions are for.

## File layout

```
dream11-demo/
├── index.html   # the entire app — HTML, CSS, engine logic, and UI
└── README.md    # this file
```
