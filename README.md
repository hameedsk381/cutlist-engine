# CAD-to-Cutlist Engine

Production-grade plywood cutting plans from 3D furniture models.

Take a SketchUp / Fusion / Rhino / Blender export, get back: a deduped cutlist,
nested sheet layouts, CNC-ready DXFs, printable shop-floor labels, cost
breakdown, sheet-size comparison, grain-aware nesting, and a model-quality
gate that refuses to ship a bad cutlist.

## What you get per run

- `report.json` - extraction, waste, sheet, strategy, model-fix, per-material data
- `cutlist.csv` - parts with material, finished size, cut size, edge band, grain
- `sheet_layout.html` - visual cutting plan with metrics, alerts and sheet-size table
- `labels.html` - printable A4 cards (2-up), one per part with grain arrow + edge band
- `dxf/sheet_NN_<material>.dxf` - layered, labeled DXF for CNC nesting / sawing
- `gcode/sheet_NN_<material>.nc` - kerf-compensated RS-274 G-code, multi-pass plunge,
  GRBL / Mach3 / LinuxCNC / Fanuc / Haas / Acorn compatible (with `--gcode`)

## Install

```powershell
python -m pip install -e .
```

## Docker (production)

```bash
cp .env.example .env   # set CUTLIST_API_TOKEN (+ GROQ_API_KEY for AI)
docker compose up -d --build
curl http://localhost:8000/healthz
```

One container serves the review SPA, API and artifacts; sessions persist on a
named volume. See [docs/PRODUCTION.md](docs/PRODUCTION.md) for TLS, env vars,
backups and scaling notes.

## SaaS mode (multi-user)

Beyond the single-operator setup above, the engine ships with a SaaS control
plane (`src/cutlist_engine/saas/`): user accounts (JWT, bcrypt), per-user
projects, and a DB-backed async job queue with a separate worker process.

| Route | What |
|---|---|
| `POST /auth/signup` · `POST /auth/login` | email + password → JWT |
| `GET  /auth/me` | current account (incl. `email_verified`) |
| `GET  /auth/verify/{token}` · `POST /auth/resend-verification` | email confirmation (non-blocking; logs the link when SMTP is unset) |
| `POST /auth/api-keys` · `GET /auth/api-keys` · `DELETE /auth/api-keys/{id}` | API keys for CNC shops (`ckl_…`, sha256-hashed, shown once) |
| `POST /api/projects` | upload model + config → project + queued job |
| `GET  /api/projects` | list your projects (with latest job status) |
| `GET  /api/projects/{id}` | project detail incl. result + artifacts when done |
| `POST /api/projects/{id}/jobs` | re-run processing |
| `POST /api/projects/{id}/share` · `DELETE …/share` | create / revoke a public read-only quote link |
| `GET  /share/{token}` | public, printable cutting-plan page (no auth, no JS) |
| `POST /api/projects/{id}/offcuts` | save a finished plan's reusable leftovers to your shelf |
| `GET  /api/offcuts` · `DELETE /api/offcuts/{id}` | list / discard shelf pieces (reserved pieces cannot be deleted) |
| `GET  /api/projects/{id}/download/{file}` | download any artifact (auth-scoped) |

API keys authenticate like sessions: `Authorization: Bearer ckl_…` works on
every project route, so shop software can pull plans without a browser.

### Offcut carry-over

Tick **"Use my offcut shelf"** when creating a project and the engine nests
parts onto leftover pieces from earlier plans first (matched by thickness,
biggest first). Offcut pieces are free — they cost nothing and shrink the
"buy" list; the plan marks those sheets and the dashboard shows what was
actually bought. Lifecycle: saving offcuts from a finished plan puts them on
the shelf (`available`); creating a project with the shelf on reserves them;
a successful job marks them `used`, a failed one puts them back.

Run it:

```bash
# dev — SQLite + in-repo storage, then run the worker in another terminal
python -m uvicorn cutlist_engine.server:app --port 8000
python -m cutlist_engine.saas.worker

# production — docker compose brings up Postgres + API + worker
docker compose up -d --build
```

Key env vars: `CUTLIST_DATABASE_URL` (SQLite default / Postgres in compose),
`CUTLIST_JWT_SECRET` (**required in production**), `CUTLIST_STORAGE_DIR`,
`CUTLIST_MONTHLY_JOB_LIMIT` (free-plan quota), `CUTLIST_SMTP_HOST`/`CUTLIST_SMTP_PORT`/`CUTLIST_SMTP_USER`/
`CUTLIST_SMTP_PASSWORD`/`CUTLIST_SMTP_FROM` (verification email; without them
the link is logged instead), and `CUTLIST_APP_URL` (public base URL used in
email links). The worker requeues jobs left `processing` by a crashed run.

## Run

```powershell
cutlist-engine input.obj --output-dir out
```

```powershell
cutlist-engine input.obj --output-dir out `
    --sheet-cost 55 `
    --candidate-sheet-sizes "2440x1220@55,3050x1525@90" `
    --kerf 3.2 `
    --grain-locked `
    --overrides overrides_example.json `
    --materials materials_example.json `
    --review review_example.json
```

## Production features

### Model-quality gate
The engine refuses to emit a misleading cutlist when the model is not
production-ready. It prints exactly what to fix:

```
GATED: confidence 12.2% < min 60%
  issue: 1076 planar surfaces could not be paired into boards
  issue: 43 micro-parts smaller than 50 mm were discarded as mesh noise
  fix:   In SketchUp, ensure every panel is a closed solid group with the correct thickness.
  fix:   Hide hardware, screws, dowels and decorative geometry before export.
```

Override with `--force` for advanced workflows.

### Per-part overrides
JSON keyed by board id OR SketchUp object name:

```json
{
  "back_panel_left": { "grain_locked": true, "priority": "visible",
                       "edge_band": [2, 0, 2, 0], "material": "veneer_oak_18" }
}
```

Fields: `grain_locked`, `priority` (`visible|normal|hidden`),
`edge_band` `[top, right, bottom, left]` mm, `material`, `label`.

### Materials registry
Each material has its own thickness, sheet size, cost and grain default.
Boards are routed by material name and nested on dedicated sheets.

```json
{
  "veneer_oak_18": { "thickness": 18, "sheet_width": 2440, "sheet_height": 1220,
                     "sheet_cost": 145, "grain_locked_default": true },
  "mdf_18":        { "thickness": 18, "sheet_width": 2440, "sheet_height": 1220,
                     "sheet_cost": 38 }
}
```

### Operator review
Accept, reject, or rename detected boards before cutting:

```json
{
  "panel_005": { "accepted": false, "reason": "Decorative trim, not a panel" },
  "panel_007": { "accepted": true,  "rename": "Drawer front A" }
}
```

### Grain direction
Globally with `--grain-locked`, per-part via overrides, or per-material via
`grain_locked_default`. Grain-locked boards never rotate 90 deg during nesting,
so veneer / laminate runs preserve direction.

### Edge banding
*Changed:* banding now **reduces** the cut size (a 600 mm finished panel with
2 mm tape on both ends is cut at 596 mm). Earlier versions enlarged it, which
produced oversize parts.

`edge_band: [top, right, bottom, left]` (mm) on the FINISHED panel: top/bottom
are the two short edges, left/right the two long edges. The engine takes the
tape thickness off the cut size so the part hits the finished dimension after
banding, and reports the metres of tape needed per thickness.

### Cost reporting & sheet-size simulation
Pass alternative sheet sizes; the cheapest by total cost wins, and the comparison
appears in the HTML report and the CLI output:

```
Sheet size comparison (cheapest first):
     1525x1525  sheets=1   util= 67.9%  total=USD 45.00   <-- chosen
     2440x1220  sheets=1   util= 53.1%  total=USD 55.00
     3050x1525  sheets=1   util= 34.0%  total=USD 90.00
```

### Cut sequence
Parts on each sheet are ordered top-to-bottom then left-to-right - the natural
order for a panel saw or CNC router.

### Priority
`visible` parts are placed before `normal`, before `hidden`, so the cleanest
sheet area goes to the parts the customer will see.

### CNC-ready DXF
One DXF per sheet with layered geometry that loads in Fusion, AutoCAD,
LibreCAD, VCarve, Aspire, EnRoute and any CAM nesting tool:

- `SHEET` - sheet boundary
- `PART` - closed cut polyline (kerf-inclusive)
- `PART_FINISH` - kerf-inset finished outline
- `OFFCUT_REUSE` / `OFFCUT_SCRAP` - dashed offcut polylines
- `LABEL` - id, dimensions, material, edge-band annotation
- `GRAIN` - directional arrow on grain-locked parts

### SketchUp plugin
User guide for SketchUp users: [docs/SKETCHUP_GUIDE.md](docs/SKETCHUP_GUIDE.md).
`sketchup_plugin/cutlist_engine_loader.rb` adds an Extensions menu. **Check and
send to CutList** reads each board's size directly from SketchUp (no mesh
export), shows what it found and what to fix in the model, then sends it:
`POST /api/tools/skp/check` judges the parts, `POST /api/projects/skp` makes the
project (both take an API key). The menu also exports OBJ and runs the CLI.
The server half is tested (`tests/test_skp.py`); **the Ruby has not been run in
SketchUp.** See `sketchup_plugin/README.md`.

## Describe it instead of drawing it

`POST /api/describe` (and `POST /api/projects/describe` for signed-in users and
API keys) turns a sentence such as *"Wardrobe 2100 high, 1200 wide, 600 deep,
2 shutters, 4 shelves"* into a real 3D model, which then runs through the same
pipeline as an upload: review, DXF, G-code, labels, share link.

Every panel size is computed in code from fixed carcass rules in
`furniture.py`, and the rules used are returned as `notes`. No language model
does arithmetic. If `GROQ_API_KEY` is set, an LLM is used only as a fallback to
read the overall size and counts out of unusual wording or another language. Drawers are worked
out as boxes for side-mounted telescopic channels, and hinge and channel
counts are suggested.

## 1D nesting (timber, beading, pipe, profiles)

`POST /api/tools/linear` (signed-in users and API keys; `/api/linear` on a single-operator install) packs a list of lengths onto stock bars with kerf, end trim
and saved leftovers:

```json
{ "pieces": [{ "label": "rail", "length": 1000, "quantity": 3 }],
  "stock_length": 3000, "kerf": 3, "leftovers": [800], "stock_cost": 250 }
```

In the web app it is the **Cut lengths** button on the projects page.

## Edge banding and client quotes in the web app

On a finished plan, **Edge banding** sets tape per part (front edge, both
long edges, or all four) and re-runs the plan with the reduced cut sizes and
a tape total. **Quote for your customer** adds labour, hardware, tape price
and margin; the shared link then shows the quote total and hides your costs.
Both are saved with `PUT /api/projects/{id}/settings`.

## AI layer

Set `GROQ_API_KEY` to switch it on. Without a key the app works as before and
the AI buttons are hidden. All model calls go through `src/cutlist_engine/ai.py`.

The rule: **a model reads and writes language, code does the arithmetic.**
No model output is ever used as a panel size, sheet count, tape length or
price.

| Where | What the model does | What code does |
|---|---|---|
| Describe box | Reads height, width, depth and counts from text in any language (Hindi, Hinglish, Telugu...) when the English rules cannot | Validates every value (`clean_params`), then the carcass rules compute all panels |
| "Say it" | Turns a voice note into text in the describe box | Nothing is submitted until the person has read it |
| "Photo of a sketch" | Reads the overall size and counts from a photo of a drawing | Writes them as a sentence the person checks; lists any size it could not read |
| "Ask AI" on a plan | Answers from facts computed by the software, and proposes edge banding, part names or quote amounts | `assistant.py` validates each proposal; it is saved only when the person presses Apply, through the normal settings route |
| Tips, unnamed parts | Writes tips; names parts called `Part 3` or `Mesh` | Names given by the designer are never replaced |

Routes (signed-in users and API keys): `GET /api/tools/ai`,
`POST /api/tools/ai/transcribe`, `POST /api/tools/ai/sketch`,
`POST /api/projects/{id}/ai/chat`.

**Status.** The code paths are covered by `tests/test_ai_layer.py` using a
scripted stand-in for the provider, and the web flows were checked in a browser
the same way. **No call has been made to a real model with these prompts**, so
answer quality, Hindi replies, sketch reading and speech accuracy are
unmeasured. Model ids were taken from Groq's documentation in November 2026;
they are settings (`CUTLIST_AI_MODEL`, `CUTLIST_AI_VISION_MODEL`,
`CUTLIST_AI_SPEECH_MODEL`) because providers retire models. The previous
hard-coded model had been retired, which had silently switched off every AI
feature.

## Languages

The web app has an English / हिन्दी switch (top of the projects page). Text
lives in `frontend/src/i18n.ts`, keyed by the English string, so anything not
yet translated shows in English. The Hindi was written without a
native-speaker review; have one done before promoting it. Furniture
descriptions can be typed or spoken in any language when AI is switched on
(see "AI layer"); without it they must be in English.

## Accuracy library

`tests/real_models/` holds real exporter files with hand-checked cut lists,
and `tests/test_real_models.py` fails if any part is missing, extra or more
than 0.5 mm off. See `tests/real_models/README.md` to add your own SketchUp or
Fusion exports; that is the most valuable test you can add.

## Input formats

- `OBJ`, `STL` (binary + ASCII), `DAE` (Collada with node names + transforms)
- `GLB` / self-contained `glTF` 2.0 (node names + transforms; metres converted to mm)
- `STEP` / `STP` — optional, needs the CAD kernel: `pip install -e .[step]`.
  **Status: written but not yet run against the kernel.** Each solid becomes one part
  (named `Part 1`, `Part 2`, ...; STEP part names are not read yet). Without the
  kernel, STEP uploads are refused with a message saying how to enable them.
- `DXF` (3DFACE, MESH and POLYFACE MESH entities, optional via `pip install -e .[cad]`)
- mesh `JSON` for tests and integrations:
  ```json
  { "triangles": [[[0,0,0],[720,0,0],[720,450,0]], ...] }
  ```

## Run tests

```powershell
python -m pytest
```

46 tests cover extraction, nesting, kerf, grain, slivers, confidence gate,
overrides, edge banding, multi-material, review, cut sequence, DXF and labels.

## User guide

See [USER_GUIDE.md](USER_GUIDE.md) for the complete operator, CLI, API, and production handoff guide.

## Production guidance

- Model each board as a closed solid with accurate thickness.
- Hide screws, dowels, hardware and decorative geometry before export.
- Name SketchUp groups/components meaningfully so overrides survive across runs.
- Calibrate `--kerf` to your blade (3.0 mm panel saw, 3.2 mm scoring, 1.5 mm CNC).
- Set `--min-reusable-offcut-width/height` to match your stock-tracking rules.

## Architecture

```
parsers.py     OBJ/STL/DAE/DXF/JSON -> Triangle stream
geometry.py    plane clustering, contour extraction
boards.py      per-part board extraction (closed solids measured directly,
               loose faces paired as a fallback), dedup -> CutlistItem
nesting.py     MaxRects with priority / grain / kerf / cut-sequence ordering
pipeline.py    overrides, edge-band, multi-material, review, cost
outputs.py     report.json, cutlist.csv, sheet_layout.html, labels.html
dxf_export.py  layered ASCII DXF per sheet (no external deps)
cli.py         single entry point
```

## Web UI - operator review

Start the server:

```powershell
$env:PYTHONPATH = "src"
python -m uvicorn cutlist_engine.server:app --reload --port 8000
```

Then open:

- `http://localhost:8000/`        - one-shot upload + report
- `http://localhost:8000/review`  - **operator review SPA**: upload, inspect each
  detected board (with polygon thumbnail, confidence score, dimensions, warnings),
  accept / reject / rename, then generate the cutlist + DXF + G-code in one click.

API surface:

| route                                  | what                                              |
|---------------------------------------|---------------------------------------------------|
| `POST /api/process`                   | one-shot upload -> full report (legacy)           |
| `POST /api/extract`                   | upload -> session id + boards for review          |
| `POST /api/finalize/{session_id}`     | apply review decisions, emit all artifacts        |
| `GET  /api/download/{session_id}/...` | download any artifact in the session              |

Production deployment controls:

| env var                         | default | purpose                                      |
|---------------------------------|---------|----------------------------------------------|
| `CUTLIST_API_TOKEN`             | unset   | when set, `/api/*` requires `Bearer` auth     |
| `CUTLIST_MAX_UPLOAD_MB`         | `100`   | rejects oversized uploads                     |
| `CUTLIST_MAX_TRIANGLES`         | `500000`| rejects geometry that is too expensive to run |
| `CUTLIST_SESSION_DIR`           | temp dir| persisted review sessions and artifacts       |
| `CUTLIST_SESSION_TTL_HOURS`     | `168`   | removes stale session folders on startup      |

For production, run behind HTTPS and set `CUTLIST_API_TOKEN`. Review sessions
are persisted to disk, so `/api/finalize/{session_id}` and downloads survive
process restarts as long as `CUTLIST_SESSION_DIR` is preserved.

## Non-rectangular panels

The contour extractor walks boundary edges of each face and stitches them into
the true outer polygon, so notches, hinge cutouts and curved fronts are
preserved. Interior holes are retained as separate cut loops. Boards with
non-rectangular geometry or cutouts are tagged with a warning, and the DXF +
G-code follow the real geometry (kerf-offset around the outer shape and each
hole, not just the bounding box).

## G-code

`--gcode` emits one `.nc` file per sheet with:

- Header: `G17 G21 G90 G94 G54`, safe-Z rapid, M3 spindle on
- Per part: rapid to entry, drop to clearance Z, multi-pass plunge contour,
  rapid retract to safe Z
- Footer: M5 spindle off, M30 program end
- Path is **kerf-compensated outward** by `kerf/2` so the cutter centre traces
  a line tangent to the finished part edge

Tunables: `--feed-rate`, `--plunge-rate`, `--spindle-rpm`, `--cut-depth`,
`--pass-depth`, `--safe-z`, `--clearance-z`, `--gcode-units mm|in`.

For a panel saw or laser, set `--spindle-rpm 0` to suppress the M3/M5 lines.

## Roadmap

- v1.2: lead-in / lead-out tabs and bridges in G-code
- v1.2: nesting-aware cut sequence (avoid lifting the offcut sheet)
- v1.2: post-processor profiles per machine (Fanuc / Haas / Mach / GRBL)
