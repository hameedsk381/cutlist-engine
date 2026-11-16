"""Job worker: claims queued jobs and runs the cutlist engine on them.

Run as its own process (docker-compose service) or ad hoc:
    python -m cutlist_engine.saas.worker
"""
from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path

from ..dxf_export import write_sheets_dxf_zip
from ..gcode_export import GCodeConfig, write_sheets_gcode
from ..outputs import (
    write_cutlist_csv,
    write_json_report,
    write_label_sheet_html,
    write_sheet_layout_html,
)
from ..parsers import load_model
from ..pipeline import ProcessConfig, process_triangles
from . import queue
from .db import SessionLocal
from .models import Job, OffcutStock, Project
from .serialize import serialize_result
from .storage import reset_artifacts

logger = logging.getLogger("cutlist.worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

POLL_INTERVAL_SECONDS = 2.0


def run_job(project: Project) -> dict:
    """Process a project's model and write all artifacts. Returns job payload."""
    config_kwargs = json.loads(project.config_json or "{}")
    config = ProcessConfig(**config_kwargs)

    triangles = load_model(Path(project.model_path))
    result = process_triangles(triangles, config)

    out_dir = reset_artifacts(project.id)
    fix = result.model_fix_report
    gated = fix is not None and not fix.passes_gate

    artifacts: list[dict[str, str]] = [
        {"name": "report.json", "path": "artifacts/report.json"},
        {"name": "sheet_layout.html", "path": "artifacts/sheet_layout.html"},
    ]

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
        artifacts.append({"name": "cutlist.csv", "path": "artifacts/cutlist.csv"})
        artifacts.append({"name": "labels.html", "path": "artifacts/labels.html"})

        if result.sheets:
            dxf_paths = write_sheets_dxf_zip(
                out_dir / "dxf", result.sheets, result.boards, kerf=config.kerf
            )
            for p in dxf_paths:
                artifacts.append({"name": f"dxf/{p.name}", "path": f"artifacts/dxf/{p.name}"})

            if not gated:  # G-code only when the model passes the quality gate
                gcode_paths = write_sheets_gcode(
                    out_dir / "gcode", result.sheets, result.boards,
                    kerf=config.kerf,
                    config=GCodeConfig(),  # defaults tuned for 18 mm CNC work
                )
                for p in gcode_paths:
                    artifacts.append({"name": f"gcode/{p.name}", "path": f"artifacts/gcode/{p.name}"})

    summary = serialize_result(result)
    try:
        from .. import ai as ai_module
        summary["ai_advice"] = ai_module.suggest_improvements(summary)
    except Exception:
        summary["ai_advice"] = None

    return {
        "gated": gated,
        "artifacts": artifacts,
        "summary": summary,
    }


def _settle_offcuts(db, project_id: int, success: bool) -> None:
    """M4: reserved offcuts become 'used' when the job succeeds, and go back
    to the shelf when it fails."""
    status = "used" if success else "available"
    db.query(OffcutStock).filter(
        OffcutStock.project_id == project_id,
        OffcutStock.status == "reserved",
    ).update({OffcutStock.status: status}, synchronize_session=False)
    if not success:
        db.query(OffcutStock).filter(
            OffcutStock.project_id == project_id,
        ).update({OffcutStock.project_id: None}, synchronize_session=False)
    db.commit()


def process_claimed_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        project = db.get(Project, job.project_id) if job else None
        if job is None or project is None:
            return
        try:
            payload = run_job(project)
        except Exception as exc:  # noqa: BLE001 — any engine failure fails the job
            logger.exception("job %s failed", job_id)
            queue.fail_job(job_id, f"{type(exc).__name__}: {exc}")
            _settle_offcuts(db, project.id, success=False)
            return
        queue.finish_job(
            job_id,
            result_json=json.dumps(payload["summary"]),
            artifacts_json=json.dumps({"gated": payload["gated"], "artifacts": payload["artifacts"]}),
        )
        _settle_offcuts(db, project.id, success=True)
        logger.info("job %s done (%d artifacts)", job_id, len(payload["artifacts"]))


def main() -> None:
    recovered = queue.recover_stale_jobs()
    if recovered:
        logger.info("requeued %d stale job(s) from a previous run", recovered)
    logger.info("worker started — polling for queued jobs")
    try:
        while True:
            job_id = queue.claim_next_job()
            if job_id is None:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue
            process_claimed_job(job_id)
    except KeyboardInterrupt:
        logger.info("worker stopped")


if __name__ == "__main__":
    main()
