"""DB-backed job queue.

M1 uses a single worker process polling the jobs table — no Redis required.
The claim is atomic enough for one worker; swap for Celery/RQ or add
SELECT ... FOR UPDATE SKIP LOCKED when scaling to multiple workers.
"""
from __future__ import annotations

from .db import SessionLocal
from .models import Job, utcnow


def enqueue(project_id: int) -> Job:
    with SessionLocal() as db:
        job = Job(project_id=project_id, status="queued")
        db.add(job)
        db.commit()
        db.refresh(job)
        return job


def claim_next_job() -> int | None:
    """Mark the oldest queued job as processing and return its id."""
    with SessionLocal() as db:
        job = (
            db.query(Job)
            .filter(Job.status == "queued")
            .order_by(Job.created_at.asc(), Job.id.asc())
            .first()
        )
        if job is None:
            return None
        job.status = "processing"
        job.started_at = utcnow()
        db.commit()
        return job.id


def fail_job(job_id: int, error: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is not None:
            job.status = "failed"
            job.error = error[:2000]
            job.finished_at = utcnow()
            db.commit()


def finish_job(job_id: int, result_json: str, artifacts_json: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is not None:
            job.status = "done"
            job.result_json = result_json
            job.artifacts_json = artifacts_json
            job.finished_at = utcnow()
            db.commit()


def recover_stale_jobs() -> int:
    """Requeue jobs left 'processing' by a crashed worker."""
    with SessionLocal() as db:
        stale = db.query(Job).filter(Job.status == "processing").all()
        for job in stale:
            job.status = "queued"
            job.started_at = None
        db.commit()
        return len(stale)
