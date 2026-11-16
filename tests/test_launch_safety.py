"""Things a public launch needs: password reset, deleting your data, rate limits, headers."""
from __future__ import annotations

from pathlib import Path

import pytest

from cutlist_engine.saas import emailer, ratelimit
from cutlist_engine.saas.security import create_reset_token
from cutlist_engine.saas.storage import project_dir

from test_saas import _auth, _described_project, _signup, client  # noqa: F401 - pytest fixture

PASSWORD = "workshop123"


@pytest.fixture()
def mailbox(monkeypatch):
    sent = []
    monkeypatch.setattr(emailer, "send_email", lambda to, subject, body: sent.append((to, subject, body)))
    return sent


def _login(client, email, password):  # noqa: F811
    return client.post("/auth/login", data={"email": email, "password": password})


def _reset_link_token(body: str) -> str:
    return body.split("?reset=", 1)[1].split()[0]


def test_forgot_password_emails_a_link_that_works_once(client, mailbox):  # noqa: F811
    _signup(client, "forgot@example.com")
    assert client.post("/auth/forgot", data={"email": "forgot@example.com"}).json() == {"sent": True}
    reset_mail = [m for m in mailbox if "Reset" in m[1]]
    assert len(reset_mail) == 1 and reset_mail[0][0] == "forgot@example.com"
    token = _reset_link_token(reset_mail[0][2])

    done = client.post("/auth/reset", data={"token": token, "password": "a-brand-new-pass"})
    assert done.status_code == 200 and done.json()["token"]
    assert _login(client, "forgot@example.com", "a-brand-new-pass").status_code == 200
    assert _login(client, "forgot@example.com", PASSWORD).status_code == 401

    again = client.post("/auth/reset", data={"token": token, "password": "yet-another-pass"})
    assert again.status_code == 400  # the link worked once


def test_forgot_password_does_not_reveal_who_has_an_account(client, mailbox):  # noqa: F811
    unknown = client.post("/auth/forgot", data={"email": "nobody@example.com"})
    assert unknown.status_code == 200 and unknown.json() == {"sent": True}
    assert mailbox == []


def test_bad_reset_links_and_short_passwords_are_refused(client, mailbox):  # noqa: F811
    assert client.post("/auth/reset", data={"token": "garbage", "password": "long-enough-1"}).status_code == 400
    session = _signup(client, "short@example.com")["token"]
    from cutlist_engine.saas.db import SessionLocal
    from cutlist_engine.saas.models import User

    with SessionLocal() as db:
        token = create_reset_token(db.query(User).filter(User.email == "short@example.com").one())
    assert client.post("/auth/reset", data={"token": token, "password": "short"}).status_code == 422
    # A session token is not a reset token.
    assert client.post("/auth/reset", data={"token": session, "password": "long-enough-1"}).status_code == 400


def test_a_user_can_delete_a_project_and_its_files(client):  # noqa: F811
    token = _signup(client, "del@example.com")["token"]
    project_id = _described_project(client, token)["id"]
    assert project_dir(project_id).exists()
    gone = client.delete(f"/api/projects/{project_id}", headers=_auth(token))
    assert gone.status_code == 200 and gone.json() == {"deleted": True}
    assert not Path(project_dir(project_id)).exists()
    assert client.get(f"/api/projects/{project_id}", headers=_auth(token)).status_code == 404


def test_nobody_can_delete_someone_elses_project(client):  # noqa: F811
    owner = _signup(client, "own@example.com")["token"]
    other = _signup(client, "other@example.com")["token"]
    project_id = _described_project(client, owner)["id"]
    assert client.delete(f"/api/projects/{project_id}", headers=_auth(other)).status_code == 404
    assert client.get(f"/api/projects/{project_id}", headers=_auth(owner)).status_code == 200


def test_a_plan_still_being_made_cannot_be_deleted(client):  # noqa: F811
    token = _signup(client, "busy@example.com")["token"]
    made = client.post(
        "/api/projects/describe",
        data={"description": "Bookshelf 1800 high, 800 wide, 300 deep, 2 shelves"}, headers=_auth(token),
    ).json()["project"]
    # The job has been queued but no worker has run it.
    assert client.delete(f"/api/projects/{made['id']}", headers=_auth(token)).status_code == 409


def test_deleting_an_account_needs_the_password_and_removes_everything(client):  # noqa: F811
    token = _signup(client, "bye@example.com")["token"]
    project_id = _described_project(client, token)["id"]
    headers = _auth(token)
    assert client.request("DELETE", "/auth/me", data={"password": "wrong-password"}, headers=headers).status_code == 403
    assert client.request("DELETE", "/auth/me", data={"password": PASSWORD}, headers=headers).json() == {"deleted": True}
    assert not project_dir(project_id).exists()
    assert _login(client, "bye@example.com", PASSWORD).status_code == 401
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_sign_in_is_rate_limited_per_address(client, monkeypatch):  # noqa: F811
    monkeypatch.setenv("CUTLIST_RATE_LIMIT", "on")
    ratelimit.reset()
    _signup(client, "rl@example.com")
    codes = [_login(client, "rl@example.com", "wrong-password").status_code for _ in range(10)]
    assert codes == [401] * 10
    blocked = _login(client, "rl@example.com", "wrong-password")
    assert blocked.status_code == 429 and "Too many" in blocked.json()["detail"]
    assert blocked.headers["retry-after"]
    ratelimit.reset()


def test_security_headers_are_on_every_response(client):  # noqa: F811
    response = client.get("/healthz")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert "microphone=(self)" in response.headers["permissions-policy"]
    assert "strict-transport-security" not in response.headers
    secure = client.get("/healthz", headers={"x-forwarded-proto": "https"})
    assert "max-age" in secure.headers["strict-transport-security"]


def test_users_behind_a_proxy_are_counted_separately(monkeypatch):
    from types import SimpleNamespace

    def request(host, forwarded=None):
        headers = {"x-forwarded-for": forwarded} if forwarded else {}
        return SimpleNamespace(client=SimpleNamespace(host=host), headers=headers)

    monkeypatch.delenv("CUTLIST_TRUST_PROXY", raising=False)
    # A proxy on the same host or network: the address it added (last) is the client.
    assert ratelimit.client_address(request("127.0.0.1", "9.9.9.9, 203.0.113.7")) == "203.0.113.7"
    assert ratelimit.client_address(request("172.18.0.1", "203.0.113.8")) == "203.0.113.8"
    # A public address cannot name someone else.
    assert ratelimit.client_address(request("8.8.8.8", "203.0.113.9")) == "8.8.8.8"
    assert ratelimit.client_address(request("127.0.0.1")) == "127.0.0.1"
    monkeypatch.setenv("CUTLIST_TRUST_PROXY", "0")
    assert ratelimit.client_address(request("127.0.0.1", "203.0.113.7")) == "127.0.0.1"
    monkeypatch.setenv("CUTLIST_TRUST_PROXY", "1")
    assert ratelimit.client_address(request("8.8.8.8", "203.0.113.7")) == "203.0.113.7"
