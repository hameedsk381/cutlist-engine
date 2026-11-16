# Competitive Landscape — CutList vs the market

*Researched 2026-11-16. Prices/features as reported by vendors and roundup articles at that date; verify before quoting externally.*

CutList competes in three tiers. We sit in the gap between them: the only tool
that goes **from a sentence or a 3D model straight to CNC-ready files**, as a
multi-user SaaS, with a self-host option.

---

## Tier 1 — Pure sheet optimizers (parts list in → nested layout out)

| Tool | Free tier | Paid | Weak spots |
|---|---|---|---|
| **CutList Optimizer** (biggest name; 1M+ Android downloads) | 5 calculations **per day** | €15–25/mo (Silver/Gold), $4.90 3-day pass | No DXF, no 3D, no 1D |
| **OptiCutter** | 5 stocks / 20 part sizes / 500 parts | €9–19/mo; API €99/mo | No 3D, no offcut library across projects |
| **CutPlan** | 30 calcs/mo, watermarked PDF | $29/mo Pro; $9/22/32 project packs | DXF paywalled; free tier capped |
| **Cutlistor** | 3 PDF exports/day, **20-row cap** | $12–25/mo; Team $99/mo | Rows capped, no save on free |
| **Cutlistlab** | Free, no daily cap, no signup | — | Newer, low awareness |
| **MaxCut** | Free Community edition (Windows) | $20/mo per device | Windows only |
| **CutList Plus fx** | Trial | $89 / $249 / $499 one-time | Windows only; DXF only in $499 edition |

## Tier 2 — 3D model → cut list (our direct lane)

| Tool | Input | Output | Catch |
|---|---|---|---|
| **Cutlistor** | glTF / GLB / Collada | PDF; DXF on paid | 3 imports/mo free |
| **Cutlistr** | OBJ + SketchUp extension | DXF/CSV; AI edge-banding detection | OBJ only |
| **Cutlist Evolution** | STEP / OBJ / STL / PLY / glTF / 3MF; **true-shape nesting** (Rust engine, 2026 rebuild) | DXF / SVG / G-code + **SmartCut API** | 40 parts on free |
| **StepNest** ⚠️ | STEP assemblies | G-code for **7 controllers** (GRBL, Mach3/4, LinuxCNC, Fanuc, Masso…); runs fully in-browser (WASM), free, no signup | Newer, low awareness; no accounts/SaaS |
| **step2gcode** | STEP + DXF + SVG in one pass | G-code | Free but no SaaS features |
| **Nestpact** | DXF + 3D solids | Nested DXF + G-code (laser/plasma/router) | Laser/plasma focused |
| **j-phi cutlist** | Onshape / SketchUp | PDF; free, offline | Niche, no nesting API |

## Tier 3 — Pro cabinet/CAD suites (ceiling, not peers)

- **SketchList 3D** — design + cut list + optimizer. $79.99/mo, $599.99/yr, $999.99 one-time.
- **PolyBoard + OptiCut** — $645–3,795 lifetime.
- **Cabinet Vision / Mozaik** — $4,000+; factories with beam saws. Not our segment (yet).

---

## Where CutList wins

1. **Natural language → parts.** "Wardrobe 2100 high, 1200 wide, 2 shutters,
   4 shelves" becomes a parts list. Nobody else does this — every competitor
   requires a CAD model or manual entry. Lead the landing page with it.
2. **Full output stack in one click** — CSV, DXF, G-code, labels, HTML sheet
   layout. Most Tier-1 tools cannot write G-code at all.
3. **Most generous free plan** — 50 jobs/mo, no part cap, all formats. vs
   CutPlan's 30 calcs/mo and Cutlistor's 20 rows.
4. **Only SaaS with share links + API keys.** No competitor has a public
   client-facing quote page or programmatic access below $99/mo (OptiCutter's
   API is €99/mo).
5. **Self-hostable** (`docker compose up`) — unique in this space; answers the
   "your files in someone's cloud" objection.
6. **India-native** — ₹ pricing, 8×4 / 7×4 / 6×4 ft sheet defaults, INR cost
   reports. Global tools are €/$ with no Indian market awareness.

## Where we're behind (roadmap candidates)

1. **1D/linear nesting** (lumber, pipe, bar) — OptiCutter and Cutlistor both
   ship it. *Candidate for M4+.*
2. **Offcut inventory across projects** — CutPlan and cutlistlab save remnant
   sheets and reuse them next job. Ours reports reusable offcuts but does not
   carry them forward. *High perceived value; strong retention hook.*
3. **True-shape irregular nesting depth** — Cutlist Evolution nests curved
   outlines natively. We support non-rectangular panels, but this is their
   flagship story.
4. **"No upload" privacy** — StepNest processes in-browser via WASM. Counter
   with the self-host option; consider publishing that story loudly.
5. **SketchUp extension awareness** — we have one in-repo; OpenCutList's is
   GPL and well known. Publish and list ours in the SketchUp extension
   directory.

## Pricing anchor for M2 (Razorpay)

Global competitors charge $9–29/mo. For India anchor:

- **Free** — 50 jobs/mo, unlimited parts, all formats (current).
- **Pro** — **₹499/mo** (~$6) — undercuts CutPlan Pro ($29) by ~80% while
  adding what none of them have: share links, API keys, G-code, priority
  queue. Annual: ₹4,990 (~2 months free).
- Positioning line: *"The only tool that turns a sentence or a 3D model into
  CNC-ready files — free."*

Risk to watch: CutList Optimizer's free cap (5/day) is its biggest complaint;
our 50 jobs/mo is a deliberate wedge. Do not shrink it — it is the top of the
funnel.
