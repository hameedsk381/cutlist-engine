"""SaaS API routes: auth, projects, jobs, downloads."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..parsers import load_model
from ..pipeline import ProcessConfig
from .models import Job, Project, User
from .queue import enqueue
from .security import (
    create_access_token,
    get_current_user,
    get_db,
    hash_password,
    verify_password,
)
from .storage import ALLOWED_SUFFIXES, safe_resolve, save_model

router = APIRouter()

MAX_UPLOAD_MB = float(os.environ.get("CUTLIST_MAX_UPLOAD_MB", "100"))
MAX_TRIANGLES = int(os.environ.get("CUTLIST_MAX_TRIANGLES", "500000"))
MONTHLY_JOB_LIMIT = int(os.environ.get("CUTLIST_MONTHLY_JOB_LIMIT", "50"))

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _user_payload(user: User) -> dict:
    return {"id": user.id, "email": user.email, "plan": user.plan}


@router.post("/auth/signup", status_code=201)
def signup(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(422, "Enter a valid email address")
    if len(password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"token": create_access_token(user.id), "user": _user_payload(user)}


@router.post("/auth/login")
def login(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return {"token": create_access_token(user.id), "user": _user_payload(user)}


@router.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return _user_payload(user)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def _validate_config(
    sheet_width: float, sheet_height: float, thickness: float, kerf: float,
    min_part_length: float, min_part_width: float, min_confidence: float, sheet_cost: float,
) -> None:
    values = dict(
        sheet_width=sheet_width, sheet_height=sheet_height, thickness=thickness,
        kerf=kerf, min_part_length=min_part_length, min_part_width=min_part_width,
        min_confidence=min_confidence, sheet_cost=sheet_cost,
    )
    bad = [k for k, v in values.items() if v <= 0]
    if bad:
        raise HTTPException(422, f"These values must be positive: {', '.join(bad)}")


def _project_payload(project: Project, db: Session, include_result: bool = False) -> dict:
    job = (
        db.query(Job)
        .filter(Job.project_id == project.id)
        .order_by(Job.created_at.desc(), Job.id.desc())
        .first()
    )
    payload: dict = {
        "id": project.id,
        "name": project.name,
        "original_filename": project.original_filename,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "job": _job_payload(job) if job else None,
    }
    if include_result and job is not None and job.status == "done" and job.result_json:
        payload["result"] = json.loads(job.result_json)
    return payload


def _job_payload(job: Job) -> dict:
    artifacts = None
    gated = False
    if job.artifacts_json:
        parsed = json.loads(job.artifacts_json)
        gated = bool(parsed.get("gated"))
        artifacts = parsed.get("artifacts")
    return {
        "id": job.id,
        "status": job.status,
        "error": job.error,
        "gated": gated,
        "artifacts": artifacts,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def _owned_project(project_id: int, user: User, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(404, "Project not found")
    return project


@router.post("/api/projects", status_code=201)
async def create_project(
    file: UploadFile = File(...),
    name: str = Form("Untitled project"),
    sheet_width: float = Form(2440.0),
    sheet_height: float = Form(1220.0),
    thickness: float = Form(18.0),
    kerf: float = Form(3.0),
    min_part_length: float = Form(50.0),
    min_part_width: float = Form(50.0),
    min_confidence: float = Form(0.6),
    sheet_cost: float = Form(3500.0),
    currency: str = Form("INR"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_config(sheet_width, sheet_height, thickness, kerf,
                     min_part_length, min_part_width, min_confidence, sheet_cost)

    # Free-plan monthly quota (Razorpay plans lift this in M2).
    # Calendar month start computed in Python — portable across dialects.
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = (
        db.query(func.count(Job.id))
        .join(Project)
        .filter(Project.user_id == user.id, Job.created_at >= month_start)
        .scalar()
        or 0
    )
    if used >= MONTHLY_JOB_LIMIT:
        raise HTTPException(402, f"Monthly limit of {MONTHLY_JOB_LIMIT} jobs reached — upgrade to continue")

    filename = file.filename or "model"
    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {MAX_UPLOAD_MB:.0f} MB")

    # Validate before persisting anything — a rejected upload must not leave
    # a project row behind.
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(422, f"Unsupported file type '{suffix}'. Allowed: {sorted(ALLOWED_SUFFIXES)}")

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        try:
            triangles = load_model(tmp_path)
        except Exception as exc:
            raise HTTPException(422, f"Could not parse this model: {exc}") from exc
        if len(triangles) > MAX_TRIANGLES:
            raise HTTPException(
                413, f"Model has {len(triangles):,} triangles — limit is {MAX_TRIANGLES:,}"
            )
    finally:
        tmp_path.unlink(missing_ok=True)

    project = Project(
        user_id=user.id,
        name=name.strip() or "Untitled project",
        original_filename=filename,
        config_json=json.dumps({
            "sheet_width": sheet_width,
            "sheet_height": sheet_height,
            "material_thickness": thickness,
            "kerf": kerf,
            "min_part_length": min_part_length,
            "min_part_width": min_part_width,
            "min_confidence": min_confidence,
            "sheet_cost": sheet_cost,
            "currency": currency,
        }),
    )
    db.add(project)
    db.flush()  # assigns project.id so storage paths can be built
    model_path = save_model(project.id, filename, content)
    project.model_path = str(model_path)
    db.commit()
    db.refresh(project)

    job = enqueue(project.id)
    return {"project": _project_payload(project, db), "job_id": job.id}


@router.get("/api/projects")
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    projects = (
        db.query(Project)
        .filter(Project.user_id == user.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    return [_project_payload(p, db) for p in projects]


@router.get("/api/projects/{project_id}")
def get_project(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _owned_project(project_id, user, db)
    return _project_payload(project, db, include_result=True)


@router.post("/api/projects/{project_id}/jobs", status_code=201)
def rerun_project(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _owned_project(project_id, user, db)
    job = enqueue(project.id)
    return {"job_id": job.id}


@router.get("/api/projects/{project_id}/download/{filename:path}")
def download_artifact(
    project_id: int, filename: str,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _owned_project(project_id, user, db)
    try:
        path = safe_resolve(project_id, filename)
    except ValueError:
        raise HTTPException(400, "Invalid path")
    if not path.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=path.name)
