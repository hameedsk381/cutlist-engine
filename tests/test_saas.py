"""SaaS control plane tests: auth, projects, job queue, worker, downloads."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CUTLIST_DATABASE_URL", "sqlite:///./tests/_tmp_out/saas_test.db")
os.environ.setdefault("CUTLIST_STORAGE_DIR", "tests/_tmp_out/saas_storage")
os.environ.setdefault("CUTLIST_MONTHLY_JOB_LIMIT", "5")

from cutlist_engine.saas import db as saas_db  # noqa: E402
from cutlist_engine.saas.db import Base  # noqa: E402
from cutlist_engine.saas.worker import process_claimed_job  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Fresh DB + storage per test
    saas_db.engine.dispose()
    Path("tests/_tmp_out/saas_test.db").unlink(missing_ok=True)
    Base.metadata.drop_all(saas_db.engine)
    Base.metadata.create_all(saas_db.engine)

    import cutlist_engine.server as server

    with TestClient(server.app) as c:
        yield c


MESH = json.dumps({
    "triangles": [
        [[0, 0, 0], [720, 0, 0], [720, 450, 0]],
        [[0, 0, 0], [720, 450, 0], [0, 450, 0]],
        [[0, 0, 18], [720, 0, 18], [720, 450, 18]],
        [[0, 0, 18], [720, 450, 18], [0, 450, 18]],
        [[0, 0, 0], [720, 0, 0], [720, 0, 18]],
        [[0, 0, 0], [720, 0, 18], [0, 0, 18]],
        [[720, 0, 0], [720, 450, 0], [720, 450, 18]],
        [[720, 0, 0], [720, 450, 18], [720, 0, 18]],
        [[0, 450, 0], [720, 450, 0], [720, 450, 18]],
        [[0, 450, 0], [720, 450, 18], [0, 450, 18]],
        [[0, 0, 0], [0, 450, 0], [0, 450, 18]],
        [[0, 0, 0], [0, 450, 18], [0, 0, 18]],
    ]
})


def _signup(client: TestClient, email: str, password: str = "workshop123") -> dict:
    r = client.post("/auth/signup", data={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_project(client: TestClient, token: str, name: str = "Kitchen") -> dict:
    r = client.post(
        "/api/projects",
        data={"name": name, "sheet_width": 2440, "sheet_height": 1220,
              "thickness": 18, "kerf": 3.0},
        files={"file": ("cabinet.json", MESH.encode(), "application/json")},
        headers=_auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_signup_login_and_me(client):
    data = _signup(client, "carpenter@example.com")

    r = client.get("/auth/me", headers=_auth(data["token"]))
    assert r.status_code == 200
    assert r.json()["email"] == "carpenter@example.com"
    assert r.json()["plan"] == "free"

    # login returns a token that also works
    r = client.post("/auth/login", data={"email": "carpenter@example.com", "password": "workshop123"})
    assert r.status_code == 200
    assert client.get("/auth/me", headers=_auth(r.json()["token"])).status_code == 200

    # wrong password rejected
    assert client.post(
        "/auth/login", data={"email": "carpenter@example.com", "password": "wrong-pass"}
    ).status_code == 401


def test_signup_validation(client):
    assert client.post("/auth/signup", data={"email": "nope", "password": "workshop123"}).status_code == 422
    assert client.post("/auth/signup", data={"email": "a@b.com", "password": "short"}).status_code == 422
    _signup(client, "dup@example.com")
    assert client.post("/auth/signup", data={"email": "dup@example.com", "password": "workshop123"}).status_code == 409


def test_requires_auth(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/projects/1").status_code == 401


def test_project_create_and_worker_processes_job(client):
    data = _signup(client, "maker@example.com")
    token = data["token"]

    payload = _create_project(client, token)
    project = payload["project"]
    assert project["name"] == "Kitchen"
    assert project["job"]["status"] == "queued"

    # Simulate the worker picking it up
    process_claimed_job(project["job"]["id"])

    r = client.get(f"/api/projects/{project['id']}", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    job = body["job"]
    assert job["status"] == "done", job.get("error")
    names = [a["name"] for a in job["artifacts"]]
    assert "report.json" in names
    assert "cutlist.csv" in names
    assert "sheet_layout.html" in names
    assert any(n.startswith("dxf/") for n in names)
    # summary matches the /api/process shape
    assert "boards" in body["result"]
    assert "sheets" in body["result"]


def test_project_isolation_between_users(client):
    a = _signup(client, "alice@example.com")
    b = _signup(client, "bob@example.com")
    created = _create_project(client, a["token"])

    # Bob cannot see Alice's project
    assert client.get(f"/api/projects/{created['project']['id']}", headers=_auth(b["token"])).status_code == 404
    # Bob's list is empty
    assert client.get("/api/projects", headers=_auth(b["token"])).json() == []


def test_download_artifact_requires_and_allows_auth(client):
    data = _signup(client, "dl@example.com")
    token = data["token"]
    created = _create_project(client, token)
    process_claimed_job(created["project"]["job"]["id"])

    url = f"/api/projects/{created['project']['id']}/download/artifacts/report.json"
    assert client.get(url).status_code == 401
    r = client.get(url, headers=_auth(token))
    assert r.status_code == 200
    report = json.loads(r.content)
    assert "boards" in report or "sheets" in report

    # path traversal blocked at the storage layer (httpx normalizes ../ in
    # URLs client-side, so test safe_resolve directly)
    from cutlist_engine.saas.storage import safe_resolve

    with pytest.raises(ValueError):
        safe_resolve(created["project"]["id"], "../../users/db")
    with pytest.raises(ValueError):
        safe_resolve(created["project"]["id"], "C:/Windows/system32/config")
    assert safe_resolve(created["project"]["id"], "artifacts/report.json").is_file()


def test_monthly_quota(client):
    data = _signup(client, "quota@example.com")
    token = data["token"]
    for _ in range(5):  # CUTLIST_MONTHLY_JOB_LIMIT=5
        _create_project(client, token)
    r = client.post(
        "/api/projects",
        data={"name": "one too many"},
        files={"file": ("cabinet.json", MESH.encode(), "application/json")},
        headers=_auth(token),
    )
    assert r.status_code == 402


def test_rejected_file_type(client):
    data = _signup(client, "badfile@example.com")
    r = client.post(
        "/api/projects",
        data={"name": "bad"},
        files={"file": ("virus.exe", b"MZ", "application/octet-stream")},
        headers=_auth(data["token"]),
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# M3: email verification, API keys, shareable links
# ---------------------------------------------------------------------------

def _user_by_email(email: str):
    from cutlist_engine.saas.models import User

    with saas_db.SessionLocal() as db:
        return db.query(User).filter(User.email == email).first()


def test_email_verification_flow(client):
    data = _signup(client, "verify@example.com")
    assert data["user"]["email_verified"] is False

    user = _user_by_email("verify@example.com")
    assert user.verification_token  # issued at signup

    # unverified /me still works (verification is non-blocking)
    r = client.get("/auth/me", headers=_auth(data["token"]))
    assert r.json()["email_verified"] is False

    # bad token → 400
    assert client.get("/auth/verify/deadbeef").status_code == 400

    # good token → verified page, token cleared
    r = client.get(f"/auth/verify/{user.verification_token}")
    assert r.status_code == 200
    assert "verified" in r.text.lower()

    assert client.get(f"/auth/verify/{user.verification_token}").status_code == 400  # single-use
    assert client.get("/auth/me", headers=_auth(data["token"])).json()["email_verified"] is True

    # resend on an already-verified account does nothing
    r = client.post("/auth/resend-verification", headers=_auth(data["token"]))
    assert r.json() == {"verified": True}


def test_resend_verification_issues_new_token(client):
    data = _signup(client, "resend@example.com")
    old = _user_by_email("resend@example.com").verification_token

    r = client.post("/auth/resend-verification", headers=_auth(data["token"]))
    assert r.status_code == 200
    assert r.json() == {"verified": False, "sent": True}

    new = _user_by_email("resend@example.com").verification_token
    assert new and new != old
    assert client.get(f"/auth/verify/{new}").status_code == 200


def test_api_key_lifecycle(client):
    data = _signup(client, "keys@example.com")
    token = data["token"]

    r = client.post("/auth/api-keys", data={"name": "CNC router"}, headers=_auth(token))
    assert r.status_code == 201
    key = r.json()
    assert key["name"] == "CNC router"
    assert key["key"].startswith("ckl_")
    assert key["key_prefix"] == key["key"][:12]
    assert len(key["key"]) > 24

    # the raw key works as a Bearer alternative to JWT
    r = client.get("/api/projects", headers=_auth(key["key"]))
    assert r.status_code == 200
    assert client.get("/auth/me", headers=_auth(key["key"])).json()["email"] == "keys@example.com"

    # last_used_at is stamped
    listed = client.get("/auth/api-keys", headers=_auth(token)).json()
    assert len(listed) == 1
    assert listed[0]["key_prefix"] == key["key_prefix"]
    assert "key" not in listed[0]  # raw key never listed again
    assert listed[0]["last_used_at"] is not None

    # revocation kills access
    assert client.delete(f"/auth/api-keys/{key['id']}", headers=_auth(token)).status_code == 200
    assert client.get("/api/projects", headers=_auth(key["key"])).status_code == 401

    # junk keys are rejected
    assert client.get("/api/projects", headers=_auth("ckl_not_a_real_key")).status_code == 401


def test_share_link_public_readonly(client):
    data = _signup(client, "sharer@example.com")
    token = data["token"]
    created = _create_project(client, token, name="Fancy wardrobe")
    pid = created["project"]["id"]

    # share before any result exists
    r = client.post(f"/api/projects/{pid}/share", headers=_auth(token))
    assert r.status_code == 200
    share_url = r.json()["share_url"]
    assert share_url.startswith("/share/")

    # public page renders without auth, shows the "still being prepared" state
    r = client.get(share_url)
    assert r.status_code == 200
    assert "Fancy wardrobe" in r.text
    assert "being prepared" in r.text

    # another user's project cannot be shared by a stranger
    other = _signup(client, "stranger@example.com")
    assert client.post(f"/api/projects/{pid}/share", headers=_auth(other["token"])).status_code == 404

    # run the job, then the page shows real numbers
    process_claimed_job(created["project"]["job"]["id"])
    r = client.get(share_url)
    assert r.status_code == 200
    assert "Parts list" in r.text

    # unsharing kills the link
    assert client.delete(f"/api/projects/{pid}/share", headers=_auth(token)).status_code == 200
    assert client.get(share_url).status_code == 404


def test_share_token_is_reused_not_regenerated(client):
    data = _signup(client, "reuse@example.com")
    token = data["token"]
    pid = _create_project(client, token)["project"]["id"]

    first = client.post(f"/api/projects/{pid}/share", headers=_auth(token)).json()["share_url"]
    second = client.post(f"/api/projects/{pid}/share", headers=_auth(token)).json()["share_url"]
    assert first == second


def test_legacy_shared_token_does_not_block_saas_routes(client, monkeypatch):
    """In production CUTLIST_API_TOKEN is set; SaaS JWTs must still work."""
    import cutlist_engine.server as server

    monkeypatch.setattr(server, "API_TOKEN", "shared-workshop-token")

    data = _signup(client, "prod@example.com")
    token = data["token"]

    # SaaS routes accept the user's JWT even with the legacy token configured
    assert client.get("/api/projects", headers=_auth(token)).status_code == 200
    created = _create_project(client, token)

    # ...and an API key works too
    key = client.post("/auth/api-keys", headers=_auth(token)).json()["key"]
    assert client.get("/api/projects", headers=_auth(key)).status_code == 200

    # the share page stays public
    share = client.post(f"/api/projects/{created['project']['id']}/share", headers=_auth(token)).json()["share_url"]
    assert client.get(share).status_code == 200

    # legacy single-operator routes still require the shared token
    assert client.post("/api/extract").status_code == 401


# ---------------------------------------------------------------------------
# M4: offcut shelf (save leftovers → reuse them in the next project)
# ---------------------------------------------------------------------------

def test_offcut_save_list_delete(client):
    data = _signup(client, "shelf@example.com")
    token = data["token"]
    created = _create_project(client, token)
    process_claimed_job(created["project"]["job"]["id"])
    pid = created["project"]["id"]

    # nothing on the shelf yet
    r = client.get("/api/offcuts", headers=_auth(token))
    assert r.json() == {"offcuts": [], "count": 0, "total_area_m2": 0}

    # demo mesh: 5 parts on 1 sheet → reusable offcuts exist
    r = client.post(f"/api/projects/{pid}/offcuts", headers=_auth(token))
    assert r.status_code == 201
    saved = r.json()["saved"]
    assert saved > 0

    listed = client.get("/api/offcuts", headers=_auth(token)).json()
    assert listed["count"] == saved
    assert listed["total_area_m2"] > 0
    piece = listed["offcuts"][0]
    assert piece["status"] == "available"
    assert piece["thickness"] == 18.0
    assert piece["length"] >= 300 and piece["width"] >= 300  # reusable threshold

    # a stranger cannot see or touch them
    other = _signup(client, "other-shelf@example.com")
    assert client.get("/api/offcuts", headers=_auth(other["token"])).json()["count"] == 0
    assert client.delete(f"/api/offcuts/{piece['id']}", headers=_auth(other["token"])).status_code == 404

    # owner deletes it
    assert client.delete(f"/api/offcuts/{piece['id']}", headers=_auth(token)).status_code == 200
    assert client.get("/api/offcuts", headers=_auth(token)).json()["count"] == saved - 1


def test_offcut_save_requires_finished_plan(client):
    data = _signup(client, "nofinish@example.com")
    token = data["token"]
    created = _create_project(client, token)  # not processed
    r = client.post(f"/api/projects/{created['project']['id']}/offcuts", headers=_auth(token))
    assert r.status_code == 409


def test_offcut_used_offcuts_marked_used_after_job(client):
    from cutlist_engine.saas.models import OffcutStock, Project

    data = _signup(client, "carry2@example.com")
    token = data["token"]

    first = _create_project(client, token)
    process_claimed_job(first["project"]["job"]["id"])
    client.post(f"/api/projects/{first['project']['id']}/offcuts", headers=_auth(token))

    r = client.post(
        "/api/projects",
        data={"name": "carry project", "use_offcuts": "true"},
        files={"file": ("cabinet.json", MESH.encode(), "application/json")},
        headers=_auth(token),
    )
    assert r.status_code == 201
    project_id = r.json()["project"]["id"]

    # config carries the offcut stock into the engine
    with saas_db.SessionLocal() as db:
        project = db.get(Project, project_id)
        config = json.loads(project.config_json)
        assert len(config["offcut_stock"]) > 0
        assert all(len(entry) == 3 for entry in config["offcut_stock"])

    # run the worker: success marks the reserved pieces 'used'
    process_claimed_job(r.json()["job_id"])
    with saas_db.SessionLocal() as db:
        statuses = {
            o.status for o in db.query(OffcutStock).filter(OffcutStock.project_id == project_id)
        }
        assert statuses == {"used"}

    # the plan itself shows an offcut-stock sheet (cost 0)
    detail = client.get(f"/api/projects/{project_id}", headers=_auth(token)).json()
    sheets = detail["result"]["sheets"]
    assert any(s.get("is_offcut_stock") for s in sheets)
    assert detail["result"]["material_summary"]["total_material_cost"] < 3500

    # the shelf is empty of available pieces
    listed = client.get("/api/offcuts", headers=_auth(token)).json()
    assert listed["count"] == 0


def test_offcut_released_when_job_fails(client):
    from cutlist_engine.saas.models import OffcutStock, Project as ProjectModel

    data = _signup(client, "release@example.com")
    token = data["token"]

    first = _create_project(client, token)
    process_claimed_job(first["project"]["job"]["id"])
    client.post(f"/api/projects/{first['project']['id']}/offcuts", headers=_auth(token))

    # new project claims the shelf, then its job fails — pieces go back
    r = client.post(
        "/api/projects",
        data={"name": "fail later", "use_offcuts": "true"},
        files={"file": ("cabinet.json", MESH.encode(), "application/json")},
        headers=_auth(token),
    )
    assert r.status_code == 201
    project_id = r.json()["job_id"] and r.json()["project"]["id"]

    with saas_db.SessionLocal() as db:
        project = db.get(ProjectModel, project_id)
        model_path = project.model_path

    # corrupt the stored model so the worker fails
    Path(model_path).write_text("not a model at all")
    process_claimed_job(r.json()["job_id"])

    with saas_db.SessionLocal() as db:
        statuses = {
            o.status for o in db.query(OffcutStock).filter(OffcutStock.user_id == data["user"]["id"])
        }
        assert statuses == {"available"}

    # and the shelf shows them again
    listed = client.get("/api/offcuts", headers=_auth(token)).json()
    assert listed["count"] > 0


# ---------------------------------------------------------------------------
# Describe -> project (sizes computed in code, full CNC outputs)
# ---------------------------------------------------------------------------

def test_described_project_gets_cnc_files_and_exact_parts(client):
    token = _signup(client, "describe@example.com")["token"]

    r = client.post(
        "/api/projects/describe",
        data={"description": "Wardrobe 2100 high, 1200 wide, 600 deep, 2 shutters, 4 shelves"},
        headers=_auth(token),
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["project"]["name"] == "Wardrobe 2100 x 1200 x 600"
    assert len(created["parts"]) == 13
    assert created["notes"]

    process_claimed_job(created["project"]["job"]["id"])

    body = client.get(f"/api/projects/{created['project']['id']}", headers=_auth(token)).json()
    assert body["job"]["status"] == "done", body["job"].get("error")
    assert body["job"]["gated"] is False
    names = [a["name"] for a in body["job"]["artifacts"]]
    assert "cutlist.csv" in names and "labels.html" in names
    assert any(n.startswith("dxf/") for n in names)
    assert any(n.startswith("gcode/") for n in names)

    planned = sorted((p["length"], p["width"], p["thickness"]) for p in created["parts"])
    cut = sorted((b["length"], b["width"], b["thickness"]) for b in body["result"]["boards"])
    assert cut == planned


def test_describe_without_sizes_is_rejected_and_leaves_no_project(client):
    token = _signup(client, "vague@example.com")["token"]

    r = client.post("/api/projects/describe", data={"description": "a nice wardrobe"}, headers=_auth(token))

    assert r.status_code == 422
    assert "height" in r.json()["detail"]
    assert client.get("/api/projects", headers=_auth(token)).json() == []


def test_legacy_describe_returns_a_model_file(client):
    r = client.post("/api/describe", json={"description": "bookshelf 1800 high 800 wide 300 deep 5 shelves"})

    assert r.status_code == 200, r.text
    model = r.json()
    assert model["filename"].endswith(".obj")
    assert model["obj"].count("\no ") == len(model["parts"])


def test_linear_nesting_endpoint(client):
    r = client.post("/api/linear", json={
        "pieces": [{"label": "rail", "length": 1000, "quantity": 3}],
        "stock_length": 3000, "kerf": 3, "stock_cost": 250,
    })

    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["new_bar_count"] == 2 and plan["total_cost"] == 500
    assert plan["bars"][0]["cuts"][0] == {"label": "rail", "length": 1000.0}

    too_long = client.post("/api/linear", json={"pieces": [{"label": "x", "length": 5000}], "stock_length": 3000})
    assert too_long.status_code == 422 and "'x'" in too_long.json()["detail"]


def test_saas_routes_work_when_the_shared_token_is_set(client, monkeypatch):
    """Offcuts and tools authenticate per user, so the legacy shared token must not block them."""
    import cutlist_engine.server as server

    monkeypatch.setattr(server, "API_TOKEN", "workshop-secret")
    token = _signup(client, "tools@example.com")["token"]

    assert client.get("/api/offcuts", headers=_auth(token)).status_code == 200
    r = client.post(
        "/api/tools/linear",
        json={"pieces": [{"label": "rail", "length": 1000, "quantity": 3}], "stock_length": 3000},
        headers=_auth(token),
    )
    assert r.status_code == 200 and r.json()["new_bar_count"] == 2
    assert client.post("/api/tools/linear", json={"pieces": []}).status_code == 401
    # Legacy routes stay behind the shared token.
    assert client.post("/api/linear", json={"pieces": []}).status_code == 401


# ---------------------------------------------------------------------------
# Edge banding settings and client quote
# ---------------------------------------------------------------------------

def _described_project(client, token):
    r = client.post(
        "/api/projects/describe",
        data={"description": "Bookshelf 1800 high, 800 wide, 300 deep, 2 shelves", "sheet_cost": 3000},
        headers=_auth(token),
    )
    assert r.status_code == 201, r.text
    project = r.json()["project"]
    process_claimed_job(project["job"]["id"])
    return client.get(f"/api/projects/{project['id']}", headers=_auth(token)).json()


def test_edge_banding_setting_reruns_plan_and_reports_tape(client):
    token = _signup(client, "banding@example.com")["token"]
    body = _described_project(client, token)
    side = next(b for b in body["result"]["boards"] if b["label"] == "Left side")
    assert body["result"]["edge_banding"]["total_m"] == 0

    # 2 mm tape on one long edge (the front) of the left side.
    r = client.put(
        f"/api/projects/{body['id']}/settings",
        json={"overrides": {side["id"]: {"edge_band": [0, 0, 0, 2]}}},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["rerun"] is True
    process_claimed_job(r.json()["job_id"])

    after = client.get(f"/api/projects/{body['id']}", headers=_auth(token)).json()
    banded = next(b for b in after["result"]["boards"] if b["label"] == "Left side")
    assert (banded["length"], banded["width"]) == (1800, 298)          # cut 2 mm narrower
    assert (banded["finished_length"], banded["finished_width"]) == (1800, 300)
    assert after["result"]["edge_banding"] == {
        "total_m": 1.8, "by_thickness": [{"thickness": 2.0, "metres": 1.8}], "banded_parts": 1,
    }
    assert after["settings"]["overrides"] == {side["id"]: {"edge_band": [0.0, 0.0, 0.0, 2.0]}}

    # Saving the same settings again does not queue another run.
    again = client.put(
        f"/api/projects/{body['id']}/settings",
        json={"overrides": {side["id"]: {"edge_band": [0, 0, 0, 2]}}},
        headers=_auth(token),
    )
    assert again.json()["rerun"] is False


def test_bad_edge_banding_is_rejected(client):
    token = _signup(client, "badband@example.com")["token"]
    body = _described_project(client, token)

    r = client.put(
        f"/api/projects/{body['id']}/settings",
        json={"overrides": {"panel_001": {"edge_band": [0, 0, 99, 0]}}},
        headers=_auth(token),
    )
    assert r.status_code == 422 and "between 0 and 5" in r.json()["detail"]


def test_quote_totals_and_share_page_hides_costs(client):
    token = _signup(client, "quote@example.com")["token"]
    body = _described_project(client, token)
    material = body["result"]["material_summary"]["total_material_cost"]
    assert material == 6000  # one 18 mm sheet and one 6 mm sheet for the back

    r = client.put(
        f"/api/projects/{body['id']}/settings",
        json={"quote": {"labour": 2000, "hardware": 500, "margin_percent": 20, "customer": "Mrs Rao"}},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["rerun"] is False
    totals = r.json()["project"]["quote_totals"]
    assert totals["subtotal"] == 8500 and totals["margin"] == 1700 and totals["total"] == 10200

    share = client.post(f"/api/projects/{body['id']}/share", headers=_auth(token)).json()["share_url"]
    page = client.get(share).text
    assert "Quote total" in page and "10,200" in page and "Mrs Rao" in page
    assert "Material cost" not in page and "6,000" not in page and "1,700" not in page

    # Removing the quote brings the plain material view back.
    client.put(f"/api/projects/{body['id']}/settings", json={"quote": None}, headers=_auth(token))
    assert "Material cost" in client.get(share).text


def test_quote_rejects_bad_margin(client):
    token = _signup(client, "margin@example.com")["token"]
    body = _described_project(client, token)

    r = client.put(f"/api/projects/{body['id']}/settings", json={"quote": {"margin_percent": -5}}, headers=_auth(token))
    assert r.status_code == 422
