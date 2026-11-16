"""Studio details for the client quote, and the quote as a PDF."""
from __future__ import annotations

import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from .brand import load_brand, logo_path, normalise_brand, save_logo
from .models import User
from .quote import quote_totals
from .quote_pdf import build_quote_pdf
from .routes import _latest_done_job, _owned_project
from .security import get_current_user, get_db

router = APIRouter()


def _brand_payload(user: User) -> dict:
    return {**load_brand(user), "has_logo": logo_path(user.id).exists()}


@router.get("/api/brand")
def get_brand(user: User = Depends(get_current_user)):
    return _brand_payload(user)


@router.put("/api/brand")
def put_brand(payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        brand = normalise_brand(payload, load_brand(user))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    user.brand_json = json.dumps(brand)
    db.commit()
    return _brand_payload(user)


@router.post("/api/brand/logo")
async def upload_logo(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    try:
        save_logo(user.id, await file.read())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _brand_payload(user)


@router.get("/api/brand/logo")
def get_logo(user: User = Depends(get_current_user)):
    path = logo_path(user.id)
    if not path.exists():
        raise HTTPException(404, "No logo saved")
    return FileResponse(path, media_type="image/png")


@router.delete("/api/brand/logo")
def delete_logo(user: User = Depends(get_current_user)):
    logo_path(user.id).unlink(missing_ok=True)
    return _brand_payload(user)


@router.get("/api/projects/{project_id}/quote.pdf")
def quote_pdf(
    project_id: int, parts: bool = False,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """The saved quote as a branded PDF for the client. `parts=true` adds the parts list."""
    project = _owned_project(project_id, user, db)
    job = _latest_done_job(project, db)
    if job is None or not job.result_json:
        raise HTTPException(409, "The cutting plan is not ready yet.")
    config = json.loads(project.config_json or "{}")
    quote = config.get("quote")
    if not quote:
        raise HTTPException(409, "Save a quote first (labour, hardware, margin) so there is a price to print.")
    summary = json.loads(job.result_json)
    totals = quote_totals(summary, quote)
    path = logo_path(user.id)
    try:
        pdf = build_quote_pdf(
            project_name=project.name, quote_number=f"Q-{project.id:04d}", created_at=project.created_at,
            summary=summary, totals=totals, quote=quote, brand=load_brand(user),
            logo_png=path.read_bytes() if path.exists() else None, include_parts=parts, now=datetime.now(),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", f"{project.name}-quote").strip("-") or "quote"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
