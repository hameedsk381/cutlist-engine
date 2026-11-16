# Cutlist Engine - SketchUp plugin

A minimal Ruby plugin that exports the active model (or selection) to a clean
OBJ file and optionally runs the `cutlist-engine` CLI on it.

## Install

Copy `cutlist_engine_loader.rb` into your SketchUp Plugins folder:

- Windows: `%AppData%\SketchUp\SketchUp 2024\SketchUp\Plugins\`
- macOS:   `~/Library/Application Support/SketchUp 2024/SketchUp/Plugins/`

Restart SketchUp. A new menu appears under **Extensions -> Cutlist Engine**.

## Send straight to CutList (recommended)

1. In the CutList web app, open **API keys** and create a key.
2. In SketchUp, run **Extensions -> Cutlist Engine -> CutList connection...**
   and enter your server address (for example `https://cutlist.example.com`, or
   `http://localhost:8000` when self-hosting) and the API key.
3. Run **Extensions -> Cutlist Engine -> Send to CutList**. The selection (or
   the whole model if nothing is selected) is uploaded as a new project and
   your browser opens on the project list.

The key is stored in SketchUp's preferences on this computer. **Status: untested.** This path was written against the SketchUp Ruby API
and Ruby's `net/http`, but it has not been run in SketchUp or in Ruby yet.
Try it on a small model first.

## Use offline with the CLI

1. Model each plywood board as a **closed solid group** with the correct
   thickness (18 mm by default). Hide hardware, screws and decorative geometry.
2. (Optional) Select only the parts you want to export.
3. Run **Extensions -> Cutlist Engine -> Export and run cutlist-engine**.
4. Open `report.json`, `cutlist.csv`, `sheet_layout.html`, `labels.html` and
   the per-sheet `dxf/` files in the output folder.

## Per-part overrides

Name your SketchUp groups/components meaningfully (e.g. `back_panel_left`).
The engine keys overrides off these names. Example `overrides.json`:

```json
{
  "back_panel_left": { "grain_locked": true, "priority": "visible" },
  "shelf_pin":       { "material": "veneer_oak_18", "edge_band": [2, 0, 2, 0] }
}
```

Pass with `--overrides overrides.json` on the CLI.
