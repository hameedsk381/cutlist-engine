import time
from pathlib import Path
from src.cutlist_engine.parsers import load_model
from src.cutlist_engine.pipeline import ProcessConfig
from src.cutlist_engine.geometry import cluster_planes
from src.cutlist_engine.boards import _split_surfaces, _connected_components

def test():
    print("Loading model...")
    triangles = load_model(Path("12356.obj"))
    print(f"Loaded {len(triangles)} triangles")

    usable_triangles = [t for t in triangles if t.area() > 0]
    print(f"Usable triangles: {len(usable_triangles)}")
    
    t0 = time.time()
    planes = cluster_planes(usable_triangles, normal_tolerance=0.999, distance_tolerance=0.5)
    t1 = time.time()
    print(f"Clustered into {len(planes)} planes in {t1 - t0:.2f} seconds")

    t0 = time.time()
    surfaces = _split_surfaces(planes)
    t1 = time.time()
    print(f"Split into {len(surfaces)} surfaces in {t1 - t0:.2f} seconds")

if __name__ == "__main__":
    test()
