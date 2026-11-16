"""Per-project on-disk storage for uploaded models and generated artifacts."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

STORAGE_ROOT = Path(os.environ.get("CUTLIST_STORAGE_DIR", "data/storage"))

ALLOWED_SUFFIXES = {".json", ".dxf", ".obj", ".stl", ".dae"}


def project_dir(project_id: int | str) -> Path:
    return STORAGE_ROOT / "projects" / str(project_id)


def save_model(project_id: int, filename: str, content: bytes) -> Path:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"Unsupported file type '{suffix}'. Allowed: {sorted(ALLOWED_SUFFIXES)}")
    pdir = project_dir(project_id)
    pdir.mkdir(parents=True, exist_ok=True)
    dest = pdir / f"model{suffix}"
    dest.write_bytes(content)
    return dest.resolve()  # absolute: the worker may run with a different cwd


def artifacts_dir(project_id: int) -> Path:
    return project_dir(project_id) / "artifacts"


def reset_artifacts(project_id: int) -> Path:
    adir = artifacts_dir(project_id)
    if adir.exists():
        shutil.rmtree(adir)
    adir.mkdir(parents=True, exist_ok=True)
    return adir


def safe_resolve(project_id: int, relative: str) -> Path:
    """Resolve a path inside a project dir, refusing escapes."""
    root = project_dir(project_id).resolve()
    candidate = (root / relative).resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError("Path escapes project directory")
    return candidate
