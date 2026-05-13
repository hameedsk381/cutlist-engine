"""Debug: test source-object-aware extraction on 12356.obj."""
import time
from pathlib import Path
from collections import Counter
from src.cutlist_engine.parsers import load_model

def debug():
    triangles = load_model(Path("12356.obj"))
    
    # Analyze source objects in the model
    source_objects = Counter(t.source_object for t in triangles)
    print(f"Total triangles: {len(triangles)}")
    print(f"Unique source objects: {len(source_objects)}")
    print("\nSource objects (name: triangle_count):")
    for name, count in source_objects.most_common():
        print(f"  {name}: {count}")

if __name__ == "__main__":
    debug()
