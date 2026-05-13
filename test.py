import time
from pathlib import Path
from src.cutlist_engine.parsers import load_model
from src.cutlist_engine.pipeline import ProcessConfig, process_triangles

def test():
    print("Loading model...")
    t0 = time.time()
    try:
        triangles = load_model(Path("12356.obj"))
    except Exception as e:
        print(f"Error loading model: {e}")
        return
    t1 = time.time()
    print(f"Loaded {len(triangles)} triangles in {t1 - t0:.2f} seconds")

    config = ProcessConfig(
        sheet_width=2440.0,
        sheet_height=1220.0,
        material_thickness=18.0,
        thickness_tolerance=0.5,
        kerf=3.0,
        min_reusable_offcut_width=300.0,
        min_reusable_offcut_height=300.0,
        sheet_cost=3500.0,
        currency="INR",
    )

    print("Processing triangles...")
    t0 = time.time()
    result = process_triangles(triangles, config)
    t1 = time.time()
    print(f"Processed in {t1 - t0:.2f} seconds")
    print(f"Found {len(result.boards)} boards")
    print(f"Extraction Report: {result.extraction_report}")
    print(f"Model Fix Report: {result.model_fix_report}")
    if result.boards:
        for b in result.boards:
            print(f"  Board {b.id}: {b.length:.1f}x{b.width:.1f}x{b.thickness} conf={b.confidence} label={b.label}")
    else:
        print("  No boards survived filtering (confidence + sliver filters applied)")

if __name__ == "__main__":
    test()

