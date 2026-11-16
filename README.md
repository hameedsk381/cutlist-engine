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
`edge_band: [top, right, bottom, left]` (mm) on the FINISHED panel. The engine
adds the band thickness to the cut size so the saw produces a part that hits
the finished dimension after banding.

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
`sketchup_plugin/cutlist_engine_loader.rb` adds an Extensions menu that
exports the active selection to OBJ (mm units) and runs the CLI.

## Input formats

- `OBJ`, `STL` (binary + ASCII), `DAE` (Collada with node names + transforms)
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
