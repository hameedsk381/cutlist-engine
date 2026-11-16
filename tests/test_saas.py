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
