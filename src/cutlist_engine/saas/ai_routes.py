"""AI routes for signed-in users: voice, sketch photo and the plan assistant.

Every route is per-user (JWT or API key) and counted against a daily
allowance, because each call costs money at the AI provider.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import ai
from ..assistant import plan_facts, resolve_actions
from ..furniture import clean_params, sentence_from_params
from .models import Job, User
from .quote import normalise_quote, quote_totals
from .routes import _clean_overrides, _owned_project
from .security import get_current_user, get_db

router = APIRouter()

AI_DAILY_LIMIT = int(os.environ.get("CUTLIST_AI_DAILY_LIMIT", "200"))

# In-memory: resets when the server restarts and is per process. It is a
# brake on runaway use, not a billing meter.
_usage: dict[tuple[int, date], int] = {}
_usage_lock = threading.Lock()


def _spend(user: User) -> None:
    """Check AI is on and count one call for this user today."""
    if not ai.llm_available():
        raise HTTPException(503, "AI features are not switched on for this server.")
    today = date.today()
    with _usage_lock:
        for key in [k for k in _usage if k[1] != today]:
            del _usage[key]
        used = _usage.get((user.id, today), 0)
        if used >= AI_DAILY_LIMIT:
            raise HTTPException(429, "You have used today's AI allowance. It resets tomorrow.")
        _usage[(user.id, today)] = used + 1


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ai.AIError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/api/tools/ai")
def ai_status(user: User = Depends(get_current_user)):
    """Tells the web app which AI controls to show."""
    return {"available": ai.llm_available()}


@router.post("/api/tools/ai/transcribe")
async def ai_transcribe(
    file: UploadFile = File(...),
    language: str = Form(""),
    user: User = Depends(get_current_user),
):
    """A short voice note -> text, for the describe box. The user edits it before use."""
    audio = await file.read(ai.MAX_AUDIO_BYTES + 1)
    _spend(user)
    language = language.strip().lower()
    text = _call(
        ai.transcribe, audio, file.filename or "speech.webm",
        language if language.isalpha() and len(language) <= 3 else None,
    )
    if not text:
        raise HTTPException(422, "We could not hear any words. Try again, closer to the microphone.")
    return {"text": text}


@router.post("/api/tools/ai/sketch")
async def ai_sketch(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """A photo of a sketch -> a description sentence the user checks and submits.

    The model only reads the overall size and counts. The sentence then goes
    through the same rule parser and carcass rules as a typed description.
    """
    image = await file.read(ai.MAX_IMAGE_BYTES + 1)
    _spend(user)
    raw = _call(ai.read_sketch, image, (file.content_type or "").lower())
    params = clean_params(raw)
    if raw.get("readable") is False or not any(k in params for k in ("height", "width", "depth")):
        raise HTTPException(
            422, "We could not read sizes from that photo. Take it straight on, in good light, "
                 "with the height, width and depth written clearly.",
        )
    description, missing = sentence_from_params(params)
    return {"description": description, "missing": missing}


@router.post("/api/projects/{project_id}/ai/chat")
def project_assistant(
    project_id: int, payload: dict,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Ask about a finished plan. Returns an answer and proposed changes.

    Nothing is changed here. Each proposal carries complete, validated
    settings; the web app saves one through PUT /settings when the user
    presses Apply.
    """
    project = _owned_project(project_id, user, db)
    message = str(payload.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message is required")
    job = (
        db.query(Job)
        .filter(Job.project_id == project.id, Job.status == "done")
        .order_by(Job.created_at.desc(), Job.id.desc())
        .first()
    )
    if job is None or not job.result_json:
        raise HTTPException(409, "Finish a plan first, then ask about it.")
    summary = json.loads(job.result_json)
    config = json.loads(project.config_json or "{}")
    history = payload.get("history") if isinstance(payload.get("history"), list) else []
    language = payload.get("language") if payload.get("language") in ai.LANGUAGES else "en"

    _spend(user)
    facts = plan_facts(summary, quote_totals(summary, config.get("quote")))
    answer = _call(ai.assistant, message, facts, history, language)

    proposals = []
    for proposal in resolve_actions(
        answer["actions"], summary, config.get("overrides") or {}, config.get("quote"),
    ):
        try:
            if proposal["type"] == "overrides":
                proposal["overrides"] = _clean_overrides(proposal["overrides"])
            else:
                proposal["quote"] = normalise_quote(proposal["quote"])
        except ValueError:
            continue  # the model proposed something the settings rules reject
        proposals.append(proposal)
    return {"reply": answer["reply"], "proposals": proposals}
