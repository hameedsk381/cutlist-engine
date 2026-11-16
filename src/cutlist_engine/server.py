"""HTTP API for the cutlist engine.

Core flows:
  1. POST /api/process       — one-shot upload + full report (used by ui/index.html)
  2. POST /api/extract       — upload + extract; returns boards for operator review
  3. POST /api/finalize/{id} — apply review decisions, regenerate everything

AI flows (Groq):
  4. POST /api/ai/label      — auto-name parts from session context
  5. POST /api/describe      — description → generated 3D model (sizes computed in code)
  6. POST /api/ai/chat       — context-aware workshop assistant
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Manual .env loading to avoid dependency on python-dotenv.
# Set CUTLIST_NO_DOTENV=1 to disable (the desktop sidecar does this — the
# local engine must not inherit a deployment's API token).
env_loaded = False
if os.environ.get("CUTLIST_NO_DOTENV") != "1":
    possible_env_paths = [
        Path(__file__).resolve().parent / ".env",                # c:\...\src\cutlist_engine\.env
        Path(__file__).resolve().parent.parent.parent / ".env",  # c:\...\.env
    ]

    for env_path in possible_env_paths:
        print(f"DEBUG: Looking for .env at {env_path}")
        if env_path.exists():
            print(f"DEBUG: .env found at {env_path}, loading...")
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()
                    print(f"DEBUG: Loaded {k.strip()}")
            env_loaded = True
            break

    if not env_loaded:
        print("DEBUG: .env not found in any expected location")

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .dxf_export import write_sheets_dxf_zip
from .gcode_export import GCodeConfig, write_sheets_gcode
from .models import ReviewDecision
from .saas.db import init_db
from .saas.routes import router as saas_router
from .saas.ai_routes import router as saas_ai_router
from .saas.skp_routes import router as saas_skp_router
from .outputs import (
    write_cutlist_csv,
    write_json_report,
    write_label_sheet_html,
    write_sheet_layout_html,
)
from .furniture import describe_to_model
from .parsers import load_model
from .pipeline import ProcessConfig, edge_banding_summary, process_triangles
from . import ai as ai_module

logger = logging.getLogger(__name__)


SESSIONS_DIR = Path(os.environ.get("CUTLIST_SESSION_DIR", str(Path(tempfile.gettempdir()) / "cutlist_engine_sessions")))
SESSIONS_DIR.mkdir(exist_ok=True)
MAX_UPLOAD_BYTES = int(float(os.environ.get("CUTLIST_MAX_UPLOAD_MB", "500")) * 1024 * 1024)
MAX_TRIANGLES = int(os.environ.get("CUTLIST_MAX_TRIANGLES", "2000000"))
SESSION_TTL_SECONDS = int(float(os.environ.get("CUTLIST_SESSION_TTL_HOURS", "168")) * 3600)
API_TOKEN = os.environ.get("CUTLIST_API_TOKEN", "").strip()
ALLOWED_SUFFIXES = {".json", ".dxf", ".obj", ".stl", ".dae", ".glb", ".gltf", ".step", ".stp"}


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    init_db()  # SaaS tables (users/projects/jobs) — no-op if already created
    _cleanup_expired_sessions()
    yield


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Cutlist Engine API", version="1.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SaaS control plane: /auth/*, /api/projects, /api/projects/{id}/*
app.include_router(saas_router)
app.include_router(saas_ai_router)
app.include_router(saas_skp_router)

FRONTEND_DIR = Path(
    os.environ.get(
        "CUTLIST_FRONTEND_DIR",
        str(Path(__file__).parent.parent.parent / "frontend" / "dist"),
    )
)

# In-memory session cache backed by per-session metadata on disk.
_SESSIONS: dict[str, dict[str, Any]] = {}

# Chat history per session
_CHAT_HISTORY: dict[str, list[dict[str, str]]] = {}
_SESSION_LOCKS: dict[str, threading.Lock] = {}


# Routes that authenticate per user (JWT or API key) rather than with the
# shared workshop token.
_SAAS_PATHS = {"/api/projects", "/api/offcuts"}
_SAAS_PREFIXES = ("/api/projects/", "/api/offcuts/", "/api/tools/")


@app.middleware("http")
async def _api_token_middleware(request: Request, call_next):
    path = request.url.path
    # The shared workshop token guards the legacy single-operator routes only.
    # SaaS routes authenticate with per-user JWTs or API keys,
    # so they must not be blocked here.
    is_saas_route = path in _SAAS_PATHS or path.startswith(_SAAS_PREFIXES)
    if API_TOKEN and path.startswith("/api/") and not is_saas_route:
        expected = f"Bearer {API_TOKEN}"
        if request.headers.get("authorization") != expected:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": app.version,
        "max_upload_mb": round(MAX_UPLOAD_BYTES / 1024 / 1024, 2),
        "max_triangles": MAX_TRIANGLES,
        "session_ttl_hours": round(SESSION_TTL_SECONDS / 3600, 2),
        "session_dir": str(SESSIONS_DIR),
        "auth_enabled": bool(API_TOKEN),
    }


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
# One-shot processing (legacy)
# ---------------------------------------------------------------------------

@app.post("/api/process")
async def api_process(
    file: UploadFile = File(...),
    sheet_width: float = Form(2440.0),
    sheet_height: float = Form(1220.0),
    thickness: float = Form(18.0),
    thickness_tolerance: float = Form(0.5),
    kerf: float = Form(3.0),
    min_reusable_width: float = Form(300.0),
    min_reusable_height: float = Form(300.0),
):
    _validate_positive_values(
        sheet_width=sheet_width,
        sheet_height=sheet_height,
        thickness=thickness,
        thickness_tolerance=thickness_tolerance,
        kerf=kerf,
        min_reusable_width=min_reusable_width,
        min_reusable_height=min_reusable_height,
    )
    triangles = await _load_uploaded_mesh(file)
    config = ProcessConfig(
        sheet_width=sheet_width,
        sheet_height=sheet_height,
        material_thickness=thickness,
        thickness_tolerance=thickness_tolerance,
        kerf=kerf,
        min_reusable_offcut_width=min_reusable_width,
        min_reusable_offcut_height=min_reusable_height,
    )
    result = process_triangles(triangles, config)
    serialized = _serialize_result(result)
    
    # Name parts the model left unnamed. Names the designer gave are kept.
    labels = _ai_names_for_unnamed(serialized["boards"])
    for board in serialized["boards"]:
        if board["id"] in labels:
            board["label"] = labels[board["id"]]
    for item in serialized["cutlist"]:
        named = [labels[b] for b in item.get("board_ids", []) if b in labels]
        if named:
            item["labels"] = named

    # Add AI advice to one-shot process
    try:
        serialized["ai_advice"] = ai_module.suggest_improvements(serialized)
    except Exception:
        serialized["ai_advice"] = None
        
    return serialized


# ---------------------------------------------------------------------------
# Extract -> review -> finalize flow
# ---------------------------------------------------------------------------


@app.post("/api/extract")
async def api_extract(
    file: UploadFile = File(...),
    sheet_width: float = Form(2440.0),
    sheet_height: float = Form(1220.0),
    thickness: float = Form(18.0),
    kerf: float = Form(3.0),
    min_part_length: float = Form(50.0),
    min_part_width: float = Form(50.0),
    min_confidence: float = Form(0.6),
    sheet_cost: float = Form(3500.0), # Avg price for good 18mm Plywood in INR
    currency: str = Form("INR"),
):
    _validate_positive_values(
        sheet_width=sheet_width,
        sheet_height=sheet_height,
        thickness=thickness,
        kerf=kerf,
        min_part_length=min_part_length,
        min_part_width=min_part_width,
        min_confidence=min_confidence,
        sheet_cost=sheet_cost,
    )
    triangles = await _load_uploaded_mesh(file)
    base_config = ProcessConfig(
        sheet_width=sheet_width,
        sheet_height=sheet_height,
        material_thickness=thickness,
        kerf=kerf,
        min_part_length=0.0,  # Show all for review
        min_part_width=0.0,   # Show all for review
        min_confidence=min_confidence,
        min_board_confidence=0.0,  # Show ALL boards for operator review; confidence filter applies at finalize
        sheet_cost=sheet_cost,
        currency=currency,
    )
    result = process_triangles(triangles, base_config)

    session_id = uuid.uuid4().hex
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(exist_ok=True)

    session = {
        "triangles": triangles,
        "config_kwargs": {
            "sheet_width": sheet_width,
            "sheet_height": sheet_height,
            "material_thickness": thickness,
            "kerf": kerf,
            "min_part_length": min_part_length,
            "min_part_width": min_part_width,
            "min_confidence": min_confidence,
            "sheet_cost": sheet_cost,
            "currency": currency,
        },
        "out_dir": session_dir,
        "original_filename": file.filename or "model",
    }
    _SESSIONS[session_id] = session
    _save_session(session_id, session)

    # Name parts the model left unnamed. Names the designer gave are kept.
    labels = _ai_names_for_unnamed([_board_payload(b) for b in result.boards])
    for board in result.boards:
        if board.id in labels:
            board.label = labels[board.id]

    boards_payload = []
    for board in result.boards:
        boards_payload.append({
            "id": board.id,
            "label": board.label or (board.source_objects[0] if board.source_objects else board.id),
            "length": round(board.length, 2),
            "width": round(board.width, 2),
            "thickness": board.thickness,
            "confidence": board.confidence,
            "source_objects": list(board.source_objects),
            "warnings": list(board.warnings),
            "contour": [(p.x, p.y) for p in board.contour],
            "holes": [[(p.x, p.y) for p in hole] for hole in board.holes],
            "is_rectangular": _is_rectangular(board.contour),
        })

    return {
        "session_id": session_id,
        "extraction_report": asdict(result.extraction_report),
        "model_fix_report": asdict(result.model_fix_report) if result.model_fix_report else None,
        "boards": boards_payload,
    }


@app.post("/api/finalize/{session_id}")
async def api_finalize(session_id: str, payload: dict[str, Any]):
    session = _get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    review_in = payload.get("review", {}) or {}
    overrides_in = payload.get("overrides", {}) or {}
    emit_gcode = bool(payload.get("emit_gcode", True))
    gcode_settings = payload.get("gcode", {}) or {}
    force = bool(payload.get("force", False))

    review = {
        bid: ReviewDecision(
            accepted=bool(d.get("accepted", True)),
            rename=str(d.get("rename", "")),
            reason=str(d.get("reason", "")),
        )
        for bid, d in review_in.items()
    }

    config = ProcessConfig(
        **session["config_kwargs"],
        overrides=overrides_in,
        review=review,
    )
    result = process_triangles(session["triangles"], config)

    out_dir: Path = session["out_dir"]
    fix = result.model_fix_report
    gated = fix is not None and not fix.passes_gate and not force
    gcfg: GCodeConfig | None = None
    if not gated and emit_gcode and result.sheets:
        _validate_positive_values(
            feed_rate=float(gcode_settings.get("feed_rate", 2500.0)),
            plunge_rate=float(gcode_settings.get("plunge_rate", 800.0)),
            cut_depth=float(gcode_settings.get("cut_depth", 18.5)),
            pass_depth=float(gcode_settings.get("pass_depth", 6.0)),
            safe_z=float(gcode_settings.get("safe_z", 15.0)),
            clearance_z=float(gcode_settings.get("clearance_z", 2.0)),
        )
        gcfg = GCodeConfig(
            feed_rate=float(gcode_settings.get("feed_rate", 2500.0)),
            plunge_rate=float(gcode_settings.get("plunge_rate", 800.0)),
            spindle_rpm=int(gcode_settings.get("spindle_rpm", 18000)),
            cut_depth=float(gcode_settings.get("cut_depth", 18.5)),
            pass_depth=float(gcode_settings.get("pass_depth", 6.0)),
            safe_z=float(gcode_settings.get("safe_z", 15.0)),
            clearance_z=float(gcode_settings.get("clearance_z", 2.0)),
            units=str(gcode_settings.get("units", "mm")),
        )
    artifacts: list[dict[str, str]] = [
        {"name": "report.json", "url": f"/api/download/{session_id}/report.json"},
        {"name": "sheet_layout.html", "url": f"/api/download/{session_id}/sheet_layout.html"},
    ]

    with _session_lock(session_id):
        # Wipe and re-emit so re-finalizing on the same session is clean.
        for child in out_dir.iterdir():
            if child.name == "session.json":
                continue
            if child.is_file():
                child.unlink()
            else:
                shutil.rmtree(child)

        write_json_report(
            out_dir / "report.json",
            result.boards, result.cutlist, result.sheets,
            result.extraction_report, result.material_summary,
            result.waste_optimization_report, result.model_fix_report,
            result.sheet_size_options,
        )
        write_sheet_layout_html(
            out_dir / "sheet_layout.html",
            result.sheets, result.material_summary, result.boards,
            result.model_fix_report, result.sheet_size_options,
        )

        if not gated:
            write_cutlist_csv(out_dir / "cutlist.csv", result.cutlist)
            write_label_sheet_html(out_dir / "labels.html", result.cutlist, result.sheets)
            artifacts.append({"name": "cutlist.csv", "url": f"/api/download/{session_id}/cutlist.csv"})
            artifacts.append({"name": "labels.html", "url": f"/api/download/{session_id}/labels.html"})

            if result.sheets:
                dxf_paths = write_sheets_dxf_zip(out_dir / "dxf", result.sheets, result.boards,
                                                  kerf=session["config_kwargs"]["kerf"])
                for p in dxf_paths:
                    artifacts.append({"name": f"dxf/{p.name}", "url": f"/api/download/{session_id}/dxf/{p.name}"})

                if gcfg:
                    gcode_paths = write_sheets_gcode(out_dir / "gcode", result.sheets, result.boards,
                                                      kerf=session["config_kwargs"]["kerf"], config=gcfg)
                    for p in gcode_paths:
                        artifacts.append({"name": f"gcode/{p.name}", "url": f"/api/download/{session_id}/gcode/{p.name}"})

    summary = _serialize_result(result)
    try:
        summary["ai_advice"] = ai_module.suggest_improvements(summary)
    except Exception:
        summary["ai_advice"] = None

    return {
        "gated": gated,
        "artifacts": artifacts,
        "summary": summary,
    }


@app.get("/api/download/{session_id}/{filename:path}")
async def api_download(session_id: str, filename: str):
    session = _get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    file_path = session["out_dir"] / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    # Resolve and ensure path stays within session dir (path-traversal defense).
    resolved = file_path.resolve()
    if session["out_dir"].resolve() not in resolved.parents and resolved != session["out_dir"].resolve():
        raise HTTPException(status_code=400, detail="Invalid path")
    return FileResponse(resolved, filename=Path(filename).name)


# ---------------------------------------------------------------------------
# AI endpoints
# ---------------------------------------------------------------------------


def _ai_names_for_unnamed(boards: list[dict[str, Any]]) -> dict[str, str]:
    """AI names for boards whose name is generic (Part 3, Mesh). Empty when AI is off."""
    from .assistant import is_generic_name

    unnamed = [b for b in boards if is_generic_name(str(b.get("label") or ""))]
    if not unnamed or not ai_module.llm_available():
        return {}
    try:
        return ai_module.label_parts(unnamed)
    except Exception as exc:  # noqa: BLE001 - naming is a nicety, never block a plan on it
        logger.warning("AI naming skipped: %s", exc)
        return {}


@app.post("/api/ai/label")
async def api_ai_label(payload: dict[str, Any]):
    """Auto-name parts using AI. Accepts {session_id} or {boards: [...]}."""
    boards_data = payload.get("boards")

    if not boards_data:
        session_id = payload.get("session_id", "")
        session = _get_session(session_id)
        if not session:
            raise HTTPException(status_code=400, detail="Provide boards array or valid session_id")
        # Re-run pipeline to get boards
        config = ProcessConfig(**session["config_kwargs"])
        result = process_triangles(session["triangles"], config)
        boards_data = [_board_payload(b) for b in result.boards]

    try:
        labels = ai_module.label_parts(boards_data)
        return {"labels": labels}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI labeling failed: {e}")


@app.post("/api/describe")
async def api_describe(payload: dict[str, Any]):
    """Turn a furniture description into a 3D model file.

    Sizes are computed in code from carcass rules (see furniture.py). The
    returned OBJ is uploaded like any other model, so a described job gets the
    same review step, DXF, G-code and labels as an uploaded one.
    """
    description = str(payload.get("description", "")).strip()
    if not description:
        raise HTTPException(status_code=400, detail="description is required")
    thickness = float(payload.get("thickness", 18.0))
    _validate_positive_values(thickness=thickness)
    try:
        return describe_to_model(
            description,
            thickness=thickness,
            llm_extract=ai_module.extract_furniture_params if ai_module.llm_available() else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/api/linear")
async def api_linear(payload: dict[str, Any]):
    """1D nesting: cut a list of lengths (timber, beading, pipe) from stock bars.

    Body: {"pieces": [{"label", "length", "quantity"}], "stock_length": mm,
           "kerf"?, "end_trim"?, "leftovers"?: [mm], "stock_cost"?, "min_reusable_leftover"?}
    Signed-in users and API keys use /api/tools/linear instead.
    """
    from .linear import plan_from_payload

    try:
        return plan_from_payload(payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/api/ai/chat")
async def api_ai_chat(payload: dict[str, Any]):
    """Context-aware workshop chat assistant."""
    message = payload.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    session_id = payload.get("session_id", "")

    # Build context from session if available
    context = None
    if session_id:
        session = _get_session(session_id)
        if session:
            config = ProcessConfig(**session["config_kwargs"])
            result = process_triangles(session["triangles"], config)
            context = _serialize_result(result)

    # Or accept context directly from the frontend
    if not context and payload.get("context"):
        context = payload["context"]

    history = _CHAT_HISTORY.get(session_id or "_anon", [])

    try:
        response = ai_module.chat(message, context=context, history=history)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI chat failed: {e}")

    # Store history
    hist_key = session_id or "_anon"
    if hist_key not in _CHAT_HISTORY:
        _CHAT_HISTORY[hist_key] = []
    _CHAT_HISTORY[hist_key].append({"role": "user", "content": message})
    _CHAT_HISTORY[hist_key].append({"role": "assistant", "content": response})
    # Keep last 20 messages
    _CHAT_HISTORY[hist_key] = _CHAT_HISTORY[hist_key][-20:]

    return {"response": response}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_uploaded_mesh(file: UploadFile):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_SUFFIXES))
        raise HTTPException(status_code=415, detail=f"Unsupported file type '{suffix or '<none>'}'. Allowed: {allowed}")

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    actual_size = len(data)
    if actual_size > MAX_UPLOAD_BYTES:
        print(f"DEBUG: Upload too large. Size: {actual_size}, Limit: {MAX_UPLOAD_BYTES}")
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds {MAX_UPLOAD_BYTES / 1024 / 1024:.0f} MB limit (got {actual_size / 1024 / 1024:.1f} MB)",
        )
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        triangles = load_model(tmp_path)
        actual_triangles = len(triangles)
        if actual_triangles > MAX_TRIANGLES:
            print(f"DEBUG: Too many triangles. Count: {actual_triangles}, Limit: {MAX_TRIANGLES}")
            raise HTTPException(
                status_code=413,
                detail=f"Model has {actual_triangles:,} triangles; limit is {MAX_TRIANGLES:,}",
            )
        return triangles
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse model: {e}")
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def _validate_positive_values(**values: float) -> None:
    for name, value in values.items():
        if value < 0 or value != value:
            raise HTTPException(status_code=422, detail=f"{name} must be a non-negative number")
    for name in ("sheet_width", "sheet_height", "thickness", "pass_depth"):
        if name in values and values[name] <= 0:
            raise HTTPException(status_code=422, detail=f"{name} must be greater than zero")


def _safe_session_dir(session_id: str) -> Path:
    if not session_id or any(ch not in "0123456789abcdef" for ch in session_id) or len(session_id) != 32:
        raise HTTPException(status_code=404, detail="Unknown session_id")
    path = (SESSIONS_DIR / session_id).resolve()
    root = SESSIONS_DIR.resolve()
    if root not in path.parents and path != root:
        raise HTTPException(status_code=400, detail="Invalid session path")
    return path


def _session_metadata_path(session_id: str) -> Path:
    return _safe_session_dir(session_id) / "session.json"


def _session_lock(session_id: str) -> threading.Lock:
    if session_id not in _SESSION_LOCKS:
        _SESSION_LOCKS[session_id] = threading.Lock()
    return _SESSION_LOCKS[session_id]


def _save_session(session_id: str, session: dict[str, Any]) -> None:
    session_dir = _safe_session_dir(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "original_filename": session.get("original_filename", "model"),
        "config_kwargs": session["config_kwargs"],
        "triangles": [_triangle_payload(t) for t in session["triangles"]],
    }
    tmp_path = session_dir / "session.json.tmp"
    tmp_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    tmp_path.replace(_session_metadata_path(session_id))


def _get_session(session_id: str) -> dict[str, Any] | None:
    if session_id in _SESSIONS:
        return _SESSIONS[session_id]
    path = _session_metadata_path(session_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        session = {
            "triangles": [_triangle_from_payload(t) for t in payload["triangles"]],
            "config_kwargs": payload["config_kwargs"],
            "out_dir": _safe_session_dir(session_id),
            "original_filename": payload.get("original_filename", "model"),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Session metadata is unreadable: {exc}") from exc
    _SESSIONS[session_id] = session
    return session


def _triangle_payload(triangle) -> dict[str, Any]:
    return {
        "vertices": [triangle.a.as_tuple(), triangle.b.as_tuple(), triangle.c.as_tuple()],
        "source_object": triangle.source_object,
    }


def _triangle_from_payload(payload: dict[str, Any]):
    from .models import Triangle, Vec3

    vertices = [Vec3(float(x), float(y), float(z)) for x, y, z in payload["vertices"]]
    return Triangle(vertices[0], vertices[1], vertices[2], payload.get("source_object"))


def _cleanup_expired_sessions(now: float | None = None) -> int:
    if SESSION_TTL_SECONDS <= 0:
        return 0
    current = now if now is not None else time.time()
    removed = 0
    for child in SESSIONS_DIR.iterdir():
        if not child.is_dir():
            continue
        try:
            age = current - child.stat().st_mtime
            if age > SESSION_TTL_SECONDS:
                shutil.rmtree(child)
                _SESSIONS.pop(child.name, None)
                removed += 1
        except OSError:
            continue
    return removed


def _serialize_result(result) -> dict[str, Any]:
    boards = [_board_payload(b) for b in result.boards]
    boards_map = {b["id"]: b for b in boards}
    return {
        "boards": boards,
        "cutlist": [asdict(c) for c in result.cutlist],
        "sheets": [_sheet_payload(s, boards_map) for s in result.sheets],
        "extraction_report": asdict(result.extraction_report),
        "material_summary": asdict(result.material_summary),
        "waste_optimization_report": asdict(result.waste_optimization_report) if result.waste_optimization_report else None,
        "model_fix_report": asdict(result.model_fix_report) if result.model_fix_report else None,
        "sheet_size_options": [asdict(o) for o in result.sheet_size_options],
        "rejected_boards": [b.id for b in result.rejected_boards],
        "oversize_parts": [_board_payload(b) for b in result.oversize_boards],
        "edge_banding": edge_banding_summary(result.boards),
    }


def _board_payload(board) -> dict[str, Any]:
    return {
        "id": board.id,
        "label": board.label,
        "length": board.length,
        "width": board.width,
        "thickness": board.thickness,
        "area": board.area,
        "material": board.material,
        "priority": board.priority,
        "grain_locked": board.grain_locked,
        "edge_band": list(board.edge_band),
        "finished_length": board.finished_length or board.length,
        "finished_width": board.finished_width or board.width,
        "confidence": board.confidence,
        "source_objects": list(board.source_objects),
        "warnings": list(board.warnings),
        "contour": [(p.x, p.y) for p in board.contour],
        "holes": [[(p.x, p.y) for p in hole] for hole in board.holes],
    }


def _sheet_payload(sheet, boards_map: dict[str, Any] | None = None) -> dict[str, Any]:
    parts_payload = []
    for p in sheet.parts:
        pp = asdict(p)
        if boards_map and p.board_id in boards_map:
            board = boards_map[p.board_id]
            pp["contour"] = board["contour"]
            pp["holes"] = board["holes"]
            pp["priority"] = board["priority"]
            pp["label"] = board["label"]
        parts_payload.append(pp)

    return {
        "sheet_id": sheet.sheet_id,
        "width": sheet.width,
        "height": sheet.height,
        "material": sheet.material,
        "sheet_cost": sheet.sheet_cost,
        "currency": sheet.currency,
        "used_area": sheet.used_area,
        "waste_percent": sheet.waste_percent,
        "utilization_percent": sheet.utilization_percent,
        "parts": parts_payload,
        "offcuts": [asdict(o) for o in sheet.offcuts],
        "is_offcut_stock": sheet.is_offcut_stock,
    }


def _is_rectangular(contour) -> bool:
    if len(contour) != 4:
        return False
    xs = sorted({round(p.x, 1) for p in contour})
    ys = sorted({round(p.y, 1) for p in contour})
    return len(xs) == 2 and len(ys) == 2


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
