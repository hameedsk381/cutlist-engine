"""SketchUp direct reader: judging parts, the check page and the send route.

The payloads below have the shape the Ruby extension sends. The extension
itself has not been run (no SketchUp or Ruby here); these tests cover
everything the server does with what it sends.
"""
from __future__ import annotations

import pytest

from cutlist_engine import skp
from cutlist_engine.saas.worker import process_claimed_job

from test_saas import _auth, _signup, client  # noqa: F401 - pytest fixture


def part(name="", dims=(720, 560, 18), **extra):
    return {"name": name, "definition": extra.pop("definition", "Component#1"), "path": "Model",
            "tag": extra.pop("tag", "Layer0"), "material": extra.pop("material", ""),
            "dims": list(dims), "fill": extra.pop("fill", 1.0), "hidden": extra.pop("hidden", False), **extra}


def cabinet():
    return {"model": "Base unit", "parts": [
        part("Left side", (720, 560, 18)), part("Right side", (720, 560, 18)),
        part("Bottom", (564, 560, 17.9)), part("Top rail", (564, 100, 18)),
        part("Back", (684, 564, 6.0), material="Hardboard 6mm"),
        part("Shelf", (564, 534, 18)),
    ]}


def test_clean_cabinet_is_ready_and_sizes_are_kept_exactly():
    report = skp.analyse(cabinet())
    assert report.ready and len(report.panels) == 6 and report.excluded == []
    sizes = sorted((p.length, p.width, p.thickness) for p in report.panels)
    assert (564.0, 560.0, 18.0) in sizes          # 17.9 mm drawn is read as the 18 mm board
    assert (684.0, 564.0, 6.0) in sizes
    assert not [i for i in report.issues if i["level"] == "stop"]


def test_dimension_order_and_axes_do_not_matter():
    a = skp.analyse({"parts": [part("Side", (18, 2100, 600))]}).panels[0]
    b = skp.analyse({"parts": [part("Side", (600, 18, 2100))]}).panels[0]
    assert (a.length, a.width, a.thickness) == (b.length, b.width, b.thickness) == (2100.0, 600.0, 18.0)


@pytest.mark.parametrize("name,kwargs,why", [
    ("Door Handle", {}, "hardware"),
    ("Pull", {"dims": (128, 12, 12)}, "hardware"),
    ("Mirror", {"dims": (1500, 600, 5)}, "hardware"),
    ("Brass thing", {"tag": "Hardware"}, "hardware"),
    ("Leg", {"dims": (150, 50, 50)}, "hardware"),
    ("Paper", {"dims": (700, 500, 0.5)}, "no thickness"),
    ("Timber post", {"dims": (900, 100, 90)}, "not sheet material"),
    ("Trim", {"dims": (700, 30, 18)}, "smaller than"),
])
def test_non_boards_are_left_out_with_a_reason(name, kwargs, why):
    report = skp.analyse({"parts": [part("Side", (720, 560, 18)), part(name, **kwargs)]})
    assert len(report.panels) == 1
    assert why in report.excluded[0]["reason"]


def test_hardware_words_match_whole_words_only():
    report = skp.analyse({"parts": [part("Chandelier shelf"), part("HingeCover"), part("Kneeboard")]})
    assert [p.name for p in report.panels] == ["Chandelier shelf", "Kneeboard"]


def test_hidden_parts_are_ignored_and_counted():
    report = skp.analyse({"parts": [part("Side"), part("Ghost", hidden=True)]})
    assert len(report.panels) == 1 and report.hidden == 1
    assert any(i["title"] == "Hidden parts ignored" for i in report.issues)


def test_modelling_problems_are_reported_with_the_part_names():
    report = skp.analyse({"parts": [
        part("Side"),
        part("", (600, 400, 18), definition="Component#4"),                      # unnamed
        part("Odd", (600, 400, 17.2)),                                           # not a stock thickness
        part("Wrong", (600, 400, 18), material="Ply 12mm"),                      # material disagrees
        part("Curve", (600, 400, 18), fill=0.4),                                 # shaped
        part("Notched", (600, 400, 18), fill=0.9),                               # cutouts
        part("Sheet", (600, 400, 0.8)),                                          # surface
    ]})
    by_title = {i["title"]: i for i in report.issues}
    assert by_title["Boards without a name"]["names"] == ["Unnamed 600 x 400"]
    assert "Odd (17.2 mm)" in by_title["Not a common board thickness"]["names"]
    assert "material 12 mm, drawn 18 mm" in by_title["Material does not match the drawn thickness"]["names"][0]
    assert by_title["Shaped or curved boards"]["names"] == ["Curve"]
    assert by_title["Boards with notches or holes"]["names"] == ["Notched"]
    assert by_title["Flat surfaces without thickness"]["names"] == ["Sheet"]
    assert [i["level"] for i in report.issues] == sorted((i["level"] for i in report.issues), key=["stop", "warn", "info"].index)


def test_definition_name_is_used_when_the_instance_has_none():
    panel = skp.analyse({"parts": [part("", definition="Left_side")]}).panels[0]
    assert panel.name == "Left_side" and panel.named


def test_nothing_to_cut_stops_the_send():
    report = skp.analyse({"parts": [part("Handle"), part("Leg")]})
    assert not report.ready and report.issues[0]["level"] == "stop"


@pytest.mark.parametrize("payload", [None, [], {"parts": "x"}, {"parts": [1]}, {"parts": [{"dims": [1, 2]}]},
                                     {"parts": [{"dims": ["a", 1, 2]}]}])
def test_malformed_payloads_are_rejected_in_plain_words(payload):
    with pytest.raises(ValueError):
        skp.analyse(payload)


def test_check_page_escapes_names_and_carries_buttons_only_when_interactive():
    report = skp.analyse({"model": "<b>x</b>", "parts": [part("<script>alert(1)</script>")]})
    page = skp.render_check_page(report, interactive=True)
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page and "&lt;b&gt;x" in page
    assert "sketchup.send_to_cutlist()" in page and " disabled" not in page
    assert "sketchup" not in skp.render_check_page(report)
    blocked = skp.render_check_page(skp.analyse({"parts": [part("Handle")]}), interactive=True)
    assert "id=send disabled" in blocked


def test_model_file_round_trips_through_the_cutting_pipeline(tmp_path):
    from cutlist_engine.boards import extract_boards
    from cutlist_engine.parsers import load_model

    model = skp.build_model(skp.analyse(cabinet()))
    path = tmp_path / model["filename"]
    path.write_text(model["obj"])
    boards = extract_boards(load_model(path), expected_thickness=model["thickness"]).boards
    assert sorted((b.length, b.width, b.thickness) for b in boards) == sorted(
        (p.length, p.width, p.thickness) for p in skp.analyse(cabinet()).panels)
    assert model["thickness"] == 18.0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def test_check_route_changes_nothing_and_returns_a_page(client):  # noqa: F811
    token = _signup(client, "skp-check@example.com")["token"]
    r = client.post("/api/tools/skp/check", json={**cabinet(), "interactive": True}, headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["report"]["ready"] and body["report"]["panel_count"] == 6 and "Send to CutList" in body["html"]
    assert client.get("/api/projects", headers=_auth(token)).json() == []
    assert client.post("/api/tools/skp/check", json=cabinet()).status_code == 401
    assert client.post("/api/tools/skp/check", json={"parts": "x"}, headers=_auth(token)).status_code == 422


def test_send_route_makes_a_project_with_exact_parts(client):  # noqa: F811
    token = _signup(client, "skp-send@example.com")["token"]
    r = client.post("/api/projects/skp", json={**cabinet(), "name": "Kitchen base"}, headers=_auth(token))
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["project"]["name"] == "Kitchen base" and created["report"]["ready"]

    process_claimed_job(created["project"]["job"]["id"])
    detail = client.get(f"/api/projects/{created['project']['id']}", headers=_auth(token)).json()
    cut = sorted((round(c["length"]), round(c["width"]), c["thickness"], c["quantity"]) for c in detail["result"]["cutlist"])
    assert cut == sorted([(720, 560, 18, 2), (564, 560, 18, 1), (564, 534, 18, 1), (564, 100, 18, 1), (684, 564, 6, 1)])
    assert detail["result"]["material_summary"]["sheet_count"] == 2   # 18 mm sheet + 6 mm back


def test_send_route_refuses_when_nothing_is_a_board_and_leaves_no_project(client):  # noqa: F811
    token = _signup(client, "skp-none@example.com")["token"]
    r = client.post("/api/projects/skp", json={"parts": [part("Handle")]}, headers=_auth(token))
    assert r.status_code == 422 and "No boards" in r.json()["detail"]
    assert client.get("/api/projects", headers=_auth(token)).json() == []
    r = client.post("/api/projects/skp", json={**cabinet(), "settings": {"kerf": "wide"}}, headers=_auth(token))
    assert r.status_code == 422 and "kerf" in r.json()["detail"]


def test_sketchup_routes_work_with_an_api_key_when_the_shared_token_is_set(client, monkeypatch):  # noqa: F811
    monkeypatch.setenv("CUTLIST_API_TOKEN", "shared-secret")
    token = _signup(client, "skp-key@example.com")["token"]
    key = client.post("/auth/api-keys", data={"name": "SketchUp"}, headers=_auth(token)).json()["key"]
    assert client.post("/api/tools/skp/check", json=cabinet(), headers=_auth(key)).status_code == 200
    assert client.post("/api/projects/skp", json=cabinet(), headers=_auth(key)).status_code == 201
