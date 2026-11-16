"""Routes for the SketchUp extension's direct reader: check, then send.

Both take the same JSON body (see `cutlist_engine/skp.py`) and need an API key
or sign-in. Neither changes anything until the second one, which makes a project.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import skp
from .models import User
from .routes import _create_project_from_content
from .security import get_current_user, get_db

router = APIRouter()

_SETTING_DEFAULTS = {
    "sheet_width": 2440.0, "sheet_height": 1220.0, "kerf": 3.0,
    "min_part_length": 50.0, "min_part_width": 50.0, "min_confidence": 0.6, "sheet_cost": 3500.0,
}


def _analyse(payload: Any) -> skp.Report:
    try:
        return skp.analyse(payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/api/tools/skp/check")
def check_sketchup_parts(payload: dict, user: User = Depends(get_current_user)):
    """Judge the parts without creating anything. Returns the report and a page to show."""
    report = _analyse(payload)
    return {"report": report.to_dict(), "html": skp.render_check_page(report, interactive=bool(payload.get("interactive")))}


@router.post("/api/projects/skp", status_code=201)
def create_project_from_sketchup(
    payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Make a project from the parts read in SketchUp. Refused when nothing is a board."""
    report = _analyse(payload)
    if not report.ready:
        raise HTTPException(
            422, "No boards were found in the selection. Run the check in SketchUp to see why.",
        )
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    values: dict[str, float] = {}
    for key, default in _SETTING_DEFAULTS.items():
        raw = settings.get(key, default)
        try:
            values[key] = float(raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, f"'{key}' must be a number.") from exc
    model = skp.build_model(report)
    created = _create_project_from_content(
        model["filename"], model["obj"].encode("utf-8"), str(payload.get("name") or model["title"]),
        values["sheet_width"], values["sheet_height"], float(settings.get("thickness") or model["thickness"]),
        values["kerf"], values["min_part_length"], values["min_part_width"], values["min_confidence"],
        values["sheet_cost"], str(settings.get("currency") or "INR"), False, user, db,
    )
    created["report"] = report.to_dict()
    return created
