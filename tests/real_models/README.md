# Real-model accuracy library

Every folder here is one design with a cut list that was checked by hand.
`tests/test_real_models.py` runs each model file through the engine and fails
if any part is missing, extra, or more than 0.5 mm off.

## Add a model

1. Make a folder, for example `tests/real_models/sketchup_wardrobe_2100/`.
2. Export the design from your CAD program into it as `model.obj`, `model.dae`,
   `model.glb`, `model.stl` or `model.dxf`. Several formats of the same design
   can sit side by side; each is tested.
3. Write `expected.json` **from the drawing, not from this engine's output**:

```json
{
  "thickness": 18,
  "parts": [
    { "name": "Left side", "length": 2100, "width": 600, "thickness": 18 },
    { "name": "Back", "length": 1989, "width": 1164, "thickness": 6 }
  ],
  "not_panels": ["Handle"]
}
```

`name` must match the group or component name in the model (underscores and
spaces are treated the same). `not_panels` lists hardware the engine should
leave out and report.

## What is here now

- `blender_base_cabinet/` — a kitchen base unit built and exported by Blender
  5.2 (OBJ, GLB, STL). It has a rotated parent, unapplied object scale, a 6 mm
  back, a notched end panel and a round handle. It tests the file readers
  against a real exporter, but it is not a substitute for real SketchUp or
  Fusion models drawn by a designer. Those are still needed.
