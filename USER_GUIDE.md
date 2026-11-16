# Cutlist Engine User Guide

This guide covers the end-to-end workflow for turning CAD exports or furniture descriptions into reviewed cutlists, sheet layouts, DXF files, G-code, and shop-floor labels.

## 1. What the Engine Does

Cutlist Engine extracts manufacturable plywood panels from 3D model exports, groups matching parts, nests them onto sheet stock, and emits manufacturing artifacts.

Outputs can include:

- `report.json`: full extraction, model quality, material, and waste report.
- `cutlist.csv`: grouped part list for spreadsheets and purchasing.
- `sheet_layout.html`: visual sheet layout for review and printing.
- `labels.html`: printable part labels.
- `dxf/sheet_*.dxf`: layered CAD/CAM sheet files.
- `gcode/sheet_*.nc`: RS-274 G-code when enabled.

## 2. Supported Inputs

Use millimeter-scale geometry.

- `.obj`: common SketchUp, Blender, Rhino, Fusion export.
- `.stl`: ASCII or binary mesh.
- `.dae`: Collada with node names and transforms.
- `.glb` / `.gltf`: glTF 2.0 (export as a single `.glb`; a `.gltf` with a separate `.bin` is not accepted).
- `.dxf`: 3DFACE, MESH, and POLYFACE MESH entities.
- `.json`: mesh triangle format for integrations and tests.

The engine reads geometry, not design intent. The cleaner the model, the cleaner the output.

**Using SketchUp?** Read [docs/SKETCHUP_GUIDE.md](docs/SKETCHUP_GUIDE.md): how to model
boards so they can be cut, the SketchUp extension's check screen and every message it
shows, exporting by file, and troubleshooting.

## 3. Model Preparation Checklist

Before export:

- Model every panel as a closed solid with real thickness.
- Hide screws, hinges, handles, dowels, reference lines, hardware, and decorative geometry.
- Keep panels planar when they are meant to be sheet goods.
- Name groups/components clearly, such as `left_side`, `drawer_front_top`, or `back_panel`.
- Export in millimeters or scale the model to millimeters before processing.
- Use consistent material thickness across panels unless you plan to use materials/overrides.

Avoid:

- Single flat faces without thickness.
- Decorative meshes mixed with panels.
- Overlapping duplicate panels.
- Curved organic meshes unless they are real panels to cut.
- Tiny hardware that can be mistaken for micro-parts.

## 4. Quick Upload Workflow

Use the main page for quick extraction and layout review.

1. Start the server:

   ```powershell
   $env:PYTHONPATH = "src"
   python -m uvicorn cutlist_engine.server:app --port 8000
   ```

2. Open `http://localhost:8000/`.
3. Drop a supported model file into the upload box.
4. Set:
   - Sheet width and height.
   - Material thickness.
   - Saw kerf.
5. Click `Generate Cutlist`.
6. Review:
   - Sheet count.
   - Waste percentage.
   - Reusable offcuts.
   - Cutlist table.
   - Sheet layout preview.

The quick page is best for estimates and fast visual checks. Use the operator review workflow before cutting real stock.

### Cutting order (panel saw)

Under the sheet drawing, **Cutting order** lists the straight edge-to-edge saw cuts that turn each sheet into its parts, in the order to make them:

- Cuts are grouped into stages. Stage 1 is across the whole sheet; later stages cut the strips and pieces those make.
- Each step names the piece in your hands (for example `2135 × 516`) and how far from its top or left edge to cut. Distances are to the near side of the blade; the blade (the kerf) cuts into the gap beyond.
- "Trim the waste" steps remove leftover edge material. One trim serves every part in the piece.
- A step ends with the parts it finishes (`part #4 done`), using the numbers in the parts list.
- Tick **Show the cut lines on the sheet** to draw the cuts, numbered, over the drawing. Click a step to highlight its line. The printed plan lists the steps under each sheet.

Projects planned before this feature have no cutting order. Press the re-run button on the project to get one. A sheet that cannot be cut with straight cuts says so instead of showing steps; the nesting does not produce such sheets today.

## 5. Operator Review Workflow

Use `/review` for production jobs.

1. Open `http://localhost:8000/review`.
2. Upload a model.
3. Enter:
   - Material thickness.
   - Kerf.
   - Sheet width and height.
   - Sheet cost.
   - Minimum sliver size.
4. Click `Extract boards`.
5. Review each detected board:
   - Check dimensions.
   - Check confidence.
   - Inspect polygon thumbnails.
   - Rename parts when useful.
   - Reject false positives.
6. Proceed to machine setup.
7. Configure G-code settings if needed.
8. Generate artifacts.
9. Download only the artifacts needed for the job.

Keyboard shortcuts in review:

- `A`: accept all.
- `R`: reject all.
- `/`: focus search.
- `Enter`: proceed.

## 6. Understanding Model Confidence

The model-quality gate protects against misleading cutlists.

The engine lowers confidence when:

- Opposite faces do not pair cleanly.
- Surfaces are unmatched.
- Thickness is inconsistent.
- Micro-parts are discarded.
- Too few surfaces become boards.

If the job is gated, fix the model first. Use force only when a skilled operator has manually verified that the extracted geometry is correct.

## 7. Sheet and Kerf Settings

Sheet size should match real stock, for example:

- 2440 x 1220 mm.
- 3050 x 1525 mm.
- Custom vendor sheet sizes.

Kerf is the cutter or blade width. The engine offsets cut paths by half the kerf so the finished part size is correct.

Typical starting values:

- Panel saw: 3.0 mm.
- Scoring saw: 3.2 mm.
- CNC router: 1.5 to 6.0 mm depending on bit.

Always calibrate kerf on the actual machine.

## 8. DXF Output

DXF files are written per sheet and include layers:

- `SHEET`: sheet boundary.
- `PART`: outer cut path.
- `PART_FINISH`: finished outline when kerf is used.
- `HOLE`: interior cutout path.
- `HOLE_FINISH`: finished cutout outline when kerf is used.
- `OFFCUT_REUSE`: reusable offcut areas.
- `OFFCUT_SCRAP`: scrap offcuts.
- `LABEL`: part labels and annotations.
- `GRAIN`: grain direction arrows.

Load DXF files into your CAD/CAM package and verify scale, origin, layers, and tool compensation before cutting.

## 9. G-code Output

G-code is generated from the reviewed session when enabled.

Default output:

- Metric units.
- Absolute coordinates.
- XY plane.
- Safe Z retract.
- Spindle start when RPM is greater than zero.
- Multi-pass cutting.
- Interior holes before outer perimeters.

Important settings:

- Feed rate: lateral cutting speed.
- Plunge rate: Z feed speed.
- Spindle RPM: set to `0` for workflows that should suppress spindle commands.
- Cut depth: total negative Z depth.
- Pass depth: maximum depth per pass.
- Safe Z: travel height above stock.

Before shop use:

- Air-cut the program.
- Confirm work offset.
- Confirm units.
- Confirm Z-zero convention.
- Confirm clamp clearance.
- Confirm tool diameter and kerf assumptions.

## 10. Grain, Priority, Materials, and Overrides

The CLI supports sidecar JSON files for production control.

Overrides can set:

- `grain_locked`
- `priority`
- `edge_band`
- `material`
- `label`

Materials can set:

- Thickness.
- Sheet size.
- Sheet cost.
- Currency.
- Default grain lock.

Review files can accept, reject, or rename detected boards outside the UI.

Example:

```json
{
  "panel_001": {
    "grain_locked": true,
    "priority": "visible",
    "edge_band": [2, 0, 2, 0],
    "material": "veneer_oak_18",
    "label": "Left Side"
  }
}
```

## 11. CLI Workflow

Install locally:

```powershell
python -m pip install -e .
```

Run a basic job:

```powershell
cutlist-engine input.obj --output-dir out
```

Run with production settings:

```powershell
cutlist-engine input.obj --output-dir out `
  --sheet-width 2440 `
  --sheet-height 1220 `
  --thickness 18 `
  --kerf 3.2 `
  --sheet-cost 55 `
  --overrides overrides.json `
  --materials materials.json `
  --review review.json `
  --gcode
```

## 12. API Deployment Controls

For production API use, configure:

- `CUTLIST_API_TOKEN`: enables bearer-token auth for `/api/*`.
- `CUTLIST_MAX_UPLOAD_MB`: upload size limit.
- `CUTLIST_MAX_TRIANGLES`: geometry complexity limit.
- `CUTLIST_SESSION_DIR`: persisted session/artifact directory.
- `CUTLIST_SESSION_TTL_HOURS`: stale session cleanup window.

Run behind HTTPS in production. Preserve `CUTLIST_SESSION_DIR` if users need sessions and downloads to survive process restarts.

Health endpoint:

```text
GET /healthz
```

## 13. Troubleshooting

No boards extracted:

- The model may contain flat faces without thickness.
- The expected thickness may be wrong.
- Decorative geometry may dominate the model.

Too many false boards:

- Hide hardware and tiny details.
- Increase minimum sliver size.
- Reject bad detections in `/review`.

Wrong dimensions:

- Check model units.
- Confirm export scale.
- Verify material thickness.

DXF or G-code looks wrong in CAM:

- Check units.
- Check origin.
- Check layer visibility.
- Confirm whether the CAM software applies its own tool compensation.

High waste:

- Try alternate sheet sizes.
- Review grain locks.
- Check whether hidden parts can rotate.
- Review reusable offcuts.

## 14. Production Safety Checklist

Before cutting:

- Model confidence passed or was manually approved.
- Every extracted board was reviewed.
- False positives were rejected.
- Material thickness matches stock.
- Kerf matches the machine/tool.
- Sheet dimensions match stock.
- G-code was simulated or air-cut.
- Machine zero and clamps were verified.
- Operator accepted final artifacts.

The engine can automate extraction and layout, but the final manufacturing release should remain an operator-approved step.
