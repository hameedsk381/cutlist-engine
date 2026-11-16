# Cutlist Engine - SketchUp plugin

A minimal Ruby plugin that exports the active model (or selection) to a clean
OBJ file and optionally runs the `cutlist-engine` CLI on it.

## Install

Copy `cutlist_engine_loader.rb` into your SketchUp Plugins folder:

- Windows: `%AppData%\SketchUp\SketchUp 2024\SketchUp\Plugins\`
- macOS:   `~/Library/Application Support/SketchUp 2024/SketchUp/Plugins/`

Restart SketchUp. A new menu appears under **Extensions -> Cutlist Engine**.

## Check and send to CutList (recommended)

This reads each board's size **from SketchUp itself** (its own length, width
and thickness, in the board's own axes) instead of rebuilding boards from an
exported mesh, so rotated parts, units and closed-solid problems do not matter.

1. In the CutList web app, open **API keys** and create a key.
2. In SketchUp, run **Extensions -> Cutlist Engine -> CutList connection...**
   and enter your server address and the API key.
3. Select the furniture (or select nothing to read the whole model) and run
   **Extensions -> Cutlist Engine -> Check and send to CutList**.
4. A window lists the boards found, the parts left out and why, and what to fix
   in the model: unnamed components, flat surfaces, odd thicknesses, material
   names that disagree with the drawing, shaped boards. Fix them and run the
   check again, or press **Send to CutList** to make the project.

How parts are read:

- Every group or component with faces of its own is one part. Parts inside it
  are read separately, so a handle inside a door does not change the door.
- A part is a board when its smallest size is between 2 and 60 mm and it is at
  least 50 mm across. Names or tags with words like handle, hinge, leg, glass,
  mirror or hardware are left out.
- Name components in **Entity Info** (for example "Left side"). Unnamed parts
  are labelled by size.
- Hidden parts and parts on hidden tags are skipped.
- A shaped or notched board is planned as its full rectangle. The real shape
  is not kept.

**Status: untested in SketchUp.** The server half (judging the parts, the check
page, making the project) is covered by tests. The Ruby that measures the model
and opens the window has not been run: there is no SketchUp or Ruby on the
machine it was written on. Try it on a small model first, and tell us what the
check window says; the parts it sends are the only thing the server sees.

## Send as a mesh (older path)

1. In the CutList web app, open **API keys** and create a key.
2. In SketchUp, run **Extensions -> Cutlist Engine -> CutList connection...**
   and enter your server address (for example `https://cutlist.example.com`, or
   `http://localhost:8000` when self-hosting) and the API key.
3. Run **Extensions -> Cutlist Engine -> Send to CutList (as a mesh)**. The selection (or
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
