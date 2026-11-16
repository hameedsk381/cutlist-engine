# Competitive Landscape — CutList vs the market

*Researched 2026-11-16. Prices/features as reported by vendors and roundup articles at that date; verify before quoting externally.*

*Our own claims were checked against the code on 2026-11-16, including the
describe, glTF, 1D and SketchUp work done that day (uncommitted at time of writing). Each one below is marked **Shipped**, **Partial** or **Not built**.*

CutList competes in three tiers. We sit in the gap between them: **3D model →
reviewed cut list → CNC-ready files**, as a multi-user SaaS with a self-host
option and offcut reuse. A sentence now takes the same route for carcass
furniture (see win 1).

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
| **OpenCutList** ⚠️ | Runs inside SketchUp (no export step) | Parts list + cutting diagrams; free, GPL | SketchUp only; no SaaS, sharing or G-code. *Not re-researched for this doc — confirm features before quoting.* |

OpenCutList is the default choice for SketchUp users, who are our core
audience. Any pitch to them has to answer "why not OpenCutList?" — today the
answer is CNC files, share links, offcut reuse and cost reports.

## Tier 3 — Pro cabinet/CAD suites (ceiling, not peers)

- **SketchList 3D** — design + cut list + optimizer. $79.99/mo, $599.99/yr, $999.99 one-time.
- **PolyBoard + OptiCut** — $645–3,795 lifetime.
- **Cabinet Vision / Mozaik** — $4,000+; factories with beam saws. Not our segment (yet).

---

## Where CutList wins

1. **Natural language → parts → CNC files.** — *Shipped (carcass furniture).*
   "Wardrobe 2100 high, 1200 wide, 2 shutters, 4 shelves" becomes a real 3D
   model that runs through the normal pipeline: review, DXF, G-code, labels,
   saved project, share link. Nobody else does this.
   - Sizes are computed in code from fixed carcass rules; the rules used are
     shown to the user. No LLM arithmetic. Works with no AI key at all.
   - Covers wardrobes, tall units, base/wall cabinets, lofts and bookshelves
     with shelves, partitions, shutters, skirting and drawers (boxes sized for
     telescopic channels), plus suggested hinge and channel counts. There is
     one joinery style (top and bottom between the sides, inset back).
   - Available in the web app, the SaaS API (`/api/projects/describe`) and
     with API keys.
2. **Full output stack in one click** — *Shipped for 3D uploads.* CSV, DXF,
   G-code, labels, HTML sheet layout. Most Tier-1 tools cannot write G-code at
   all. Ours is one generic dialect with no tabs/bridges and no tool-diameter
   setting, so it is weaker than StepNest's seven controller profiles.
3. **Most generous free plan** — *Shipped.* 50 jobs/mo, no part cap, all
   formats. vs CutPlan's 30 calcs/mo and Cutlistor's 20 rows. There is no paid
   plan yet: the limit message says "upgrade to continue" with nothing to
   upgrade to.
4. **SaaS with share links + API keys** — *Shipped.* Public read-only quote
   page and API keys on the free plan. No competitor has programmatic access
   below $99/mo (OptiCutter's API is €99/mo).
5. **Self-hostable** (`docker compose up`) — *Shipped.* Unique in this space;
   answers the "your files in someone's cloud" objection. There is also a
   Tauri desktop app in `desktop/`.
6. **India-native** — *Shipped.* ₹ pricing, 8×4 / 7×4 / 6×4 ft sheet defaults,
   INR cost reports. Global tools are €/$ with no Indian market awareness.
8. **Edge banding in the web app** — *Shipped.* Per-part tape choice, cut
   sizes reduced by the tape thickness, and a tape total in metres. (An
   earlier version enlarged the cut size instead; that was a bug and is fixed.)
9. **Client quote** — *Shipped.* Labour, hardware, tape and margin on top of
   material cost. The shared link shows the customer the total and hides the
   workshop's costs and margin.
10. **Hindi interface** — *Shipped, unreviewed.* English / हिन्दी switch across
    the main screens. No global rival offers this. The Hindi needs a
    native-speaker review, and descriptions are still typed in English.
7. **Offcut carry-over across projects** — *Shipped (M4, commit `7eb3ac7`).*
   Save leftover pieces, reserve them, and nest the next job on them before
   opening a new sheet. Matches CutPlan and cutlistlab; strong retention hook.

## Where we're behind (roadmap candidates)

1. **Input formats** — *Partial.* glTF / GLB import is shipped alongside
   OBJ, STL, DAE and mesh DXF. **STEP is written but unverified**: it is an
   optional add-on (`pip install -e .[step]`, the OpenCascade kernel) and has
   not yet been run against the kernel. It is not in the default Docker image
   or desktop app, and it does not read STEP part names. STEP is what Fusion,
   SolidWorks and Onshape export, so finish and verify this.
2. **True-shape nesting** — *Not built.* Shaped parts keep their real outline
   in DXF and G-code, but nesting places every part by its bounding rectangle.
   Cutlist Evolution nests curved outlines natively; this is their flagship
   story and a real gap, not a matter of depth.
3. **Part extraction accuracy** — *Test library started, designer models still
   needed.* `tests/real_models/` runs real Blender exports (OBJ, GLB, STL) of
   a cabinet with a rotated parent, unapplied scale, a 6 mm back, a notched
   panel and a handle, and every part reads exactly. No SketchUp or Fusion
   model drawn by a real designer is in it yet; add those before any accuracy
   claim.
4. **SketchUp extension** — *Written, untested.* "Send to CutList" uploads
   the model to a hosted or self-hosted server with an API key. It has not
   been run inside SketchUp yet. Test it, package it as an `.rbz`, then list
   it in the SketchUp extension directory. OpenCutList's is GPL and well known.
5. **1D/linear nesting** (lumber, pipe, bar) — *Shipped.* Engine,
   `POST /api/tools/linear` and a "Cut lengths" screen (kerf, saved leftovers,
   cost, printable bar diagrams).
6. **"No upload" privacy** — StepNest processes in-browser via WASM. Counter
   with the self-host option and the desktop app; consider publishing that
   story loudly.

## Pricing anchor (no payment code yet)

There is no billing integration in the repo; `User.plan` exists but nothing
sets it. The numbers below are a proposal, not a shipped plan.

Global competitors charge $9–29/mo. For India anchor:

- **Free** — 50 jobs/mo, unlimited parts, all formats (current).
- **Pro** — **₹499/mo** (~$6) — undercuts CutPlan Pro ($29) by ~80%. Share
  links, API keys and G-code are already free, so Pro needs its own reasons:
  higher job limit, priority queue, and whatever ships next (STEP import,
  true-shape nesting). Annual: ₹4,990 (~2 months free).
- Positioning line: *"The only tool that turns a sentence or a 3D model
  into CNC-ready files — free."* True for carcass furniture (wardrobes,
  cabinets, shelves, drawers). Note Flatma also does text to furniture, so
  the claim rests on the CNC output, not on the idea.

Risk to watch: CutList Optimizer's free cap (5/day) is its biggest complaint;
our 50 jobs/mo is a deliberate wedge. Do not shrink it — it is the top of the
funnel.
