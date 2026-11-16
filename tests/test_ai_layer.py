"""The AI layer, tested with a scripted stand-in for the AI provider.

No test here calls a real model. They check the parts that are ours: what is
sent to the model, and that whatever comes back is validated in code before it
can touch a plan.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from cutlist_engine import ai
from cutlist_engine.assistant import is_generic_name, plan_facts, resolve_actions
from cutlist_engine.furniture import clean_params, parse_spec, sentence_from_params

from test_saas import _auth, _described_project, _signup, client  # noqa: F401 - pytest fixture


class FakeProvider:
    """Stands in for the Groq client. `answers` are returned in order."""

    def __init__(self, *answers: str, speech: str = ""):
        self.answers = list(answers)
        self.speech = speech
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._speech))

    def _chat(self, **kwargs):
        self.requests.append(kwargs)
        content = self.answers.pop(0) if self.answers else "{}"
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    def _speech(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(text=self.speech)


@pytest.fixture()
def provider(monkeypatch):
    def install(*answers: str, speech: str = "") -> FakeProvider:
        fake = FakeProvider(*answers, speech=speech)
        monkeypatch.setattr(ai, "_client", lambda: fake)
        monkeypatch.setattr(ai, "llm_available", lambda: True)
        return fake
    return install


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

def test_models_come_from_the_environment(monkeypatch, provider):
    fake = provider('{"height": 2100}')
    monkeypatch.setenv("CUTLIST_AI_MODEL", "some/new-model")
    ai.extract_furniture_params("wardrobe")
    assert fake.requests[0]["model"] == "some/new-model"
    monkeypatch.delenv("CUTLIST_AI_MODEL")
    assert ai.text_model() == ai.DEFAULT_TEXT_MODEL


def test_provider_failure_becomes_a_plain_error(monkeypatch):
    def broken():
        def create(**_):
            raise ConnectionError("socket closed")
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(ai, "_client", broken)
    with pytest.raises(ai.AIError, match="did not answer"):
        ai.extract_furniture_params("wardrobe")


# ---------------------------------------------------------------------------
# Describe in any language
# ---------------------------------------------------------------------------

def test_hindi_description_uses_the_model_for_parameters_only():
    asked = []

    def model(text):
        asked.append(text)
        return {"kind": "wardrobe", "height": 2133.6, "width": 1219.2, "depth": 609.6, "shelves": 4, "shutters": 2}

    spec = parse_spec("अलमारी 7 फुट ऊंची, 4 फुट चौड़ी, 2 फुट गहरी, 4 खाने, 2 पल्ले", llm_extract=model)
    assert asked, "the model should be asked when the rules cannot read the text"
    assert (spec.kind, spec.shelves, spec.shutters) == ("wardrobe", 4, 2)
    assert (spec.height, spec.width, spec.depth) == (2133.6, 1219.2, 609.6)
    assert any("AI read these sizes" in note for note in spec.notes)


def test_clear_english_never_calls_the_model():
    def model(_):
        raise AssertionError("the model must not be called for text the rules can read")

    spec = parse_spec("Wardrobe 2100 high, 1200 wide, 600 deep, 2 shutters, 4 shelves", llm_extract=model)
    assert spec.height == 2100 and not any("AI read" in note for note in spec.notes)


def test_rule_read_sizes_win_over_the_model():
    spec = parse_spec(
        "almirah जैसा 2100 high, 1200 wide, 600 deep",
        llm_extract=lambda _: {"height": 999, "width": 999, "depth": 999, "shelves": 3},
    )
    assert (spec.height, spec.width, spec.depth) == (2100, 1200, 600)
    assert spec.shelves == 3  # only the count the rules could not read is taken


def test_malformed_model_parameters_are_dropped():
    cleaned = clean_params({
        "kind": "spaceship", "height": "2100", "width": -5, "depth": 600,
        "shelves": 4.5, "shutters": 400, "drawers": True, "partitions": 2.0,
    })
    assert cleaned == {"depth": 600.0, "partitions": 2}

    # A model that returns nonsense leaves the normal "give the sizes" error.
    with pytest.raises(ValueError, match="height, width"):
        parse_spec("कुछ बनाओ 600 deep", llm_extract=lambda _: {"height": "tall", "width": None})


def test_sketch_parameters_round_trip_through_the_rule_parser():
    sentence, missing = sentence_from_params({
        "kind": "base_cabinet", "height": 720, "width": 600, "depth": 560,
        "shelves": 1, "shutters": 1, "drawers": 0, "thickness": 18,
    })
    assert missing == []
    spec = parse_spec(sentence)
    assert (spec.kind, spec.height, spec.width, spec.depth) == ("base_cabinet", 720, 600, 560)
    assert (spec.shelves, spec.shutters, spec.drawers) == (1, 1, 0)

    sentence, missing = sentence_from_params({"kind": "wardrobe", "height": 2100})
    assert missing == ["width", "depth"] and sentence == "Wardrobe 2100 high"


# ---------------------------------------------------------------------------
# Sketch photo and voice
# ---------------------------------------------------------------------------

def test_sketch_is_sent_to_the_vision_model_as_an_image(provider):
    fake = provider('{"readable": true, "kind": "loft", "height": 600, "width": 1800, "depth": 550}')
    params = ai.read_sketch(b"\x89PNG fake", "image/png")
    assert params["width"] == 1800
    request = fake.requests[0]
    assert request["model"] == ai.vision_model()
    image = request["messages"][1]["content"][1]["image_url"]["url"]
    assert image.startswith("data:image/png;base64,")


def test_sketch_rejects_wrong_files_before_any_model_call(provider):
    fake = provider()
    with pytest.raises(ValueError, match="JPG, PNG"):
        ai.read_sketch(b"%PDF", "application/pdf")
    with pytest.raises(ValueError, match="larger than"):
        ai.read_sketch(b"x" * (ai.MAX_IMAGE_BYTES + 1), "image/jpeg")
    assert fake.requests == []


def test_transcribe_returns_text(provider):
    fake = provider(speech="  wardrobe saat foot unchi  ")
    assert ai.transcribe(b"audio-bytes", "note.webm") == "wardrobe saat foot unchi"
    assert fake.requests[0]["model"] == ai.speech_model()
    assert "language" not in fake.requests[0]  # detected unless the caller names one


# ---------------------------------------------------------------------------
# Plan facts and proposed changes
# ---------------------------------------------------------------------------

SUMMARY = {
    "boards": [
        {"id": "b1", "thickness": 18, "edge_band": [0, 0, 0, 0]},
        {"id": "b2", "thickness": 18, "edge_band": [0, 0, 0, 0]},
        {"id": "b3", "thickness": 18, "edge_band": [0, 0, 0, 2]},
        {"id": "b4", "thickness": 6, "edge_band": [0, 0, 0, 0]},
    ],
    "cutlist": [
        {"id": "c1", "quantity": 2, "labels": ["Side", "Side"], "board_ids": ["b1", "b2"], "length": 1800, "width": 300, "thickness": 18},
        {"id": "c2", "quantity": 1, "labels": ["Shelf"], "board_ids": ["b3"], "length": 964, "width": 280, "thickness": 18},
        {"id": "c3", "quantity": 1, "labels": ["Part 4"], "board_ids": ["b4"], "length": 1789, "width": 789, "thickness": 6},
    ],
    "sheets": [
        {"sheet_id": 1, "width": 2440, "height": 1220, "sheet_cost": 3000, "used_area": 1349920,
         "utilization_percent": 45.3, "parts": [{"board_id": "b1"}, {"board_id": "b2"}, {"board_id": "b3"}]},
        {"sheet_id": 2, "width": 2440, "height": 1220, "sheet_cost": 3000, "used_area": 1411521,
         "utilization_percent": 28.0, "parts": [{"board_id": "b4"}]},
    ],
    "material_summary": {"sheet_count": 2, "total_material_cost": 6000, "currency": "INR",
                         "utilization_percent": 46.4, "waste_percent": 53.6, "reusable_offcut_area": 1.1},
    "edge_banding": {"total_m": 0.96, "by_thickness": [{"thickness": 2, "metres": 0.96}], "banded_parts": 1},
}


def test_plan_facts_number_the_rows_and_state_computed_observations():
    facts = plan_facts(SUMMARY)
    assert "1. 2 x Side, 1800 x 300 x 18, tape: none" in facts
    assert "2. 1 x Shelf, 964 x 280 x 18, tape: 2 mm on the front edge" in facts
    assert "2 sheets (1 x 18 mm, 1 x 6 mm)" in facts
    assert "Sheet 2 is only 28% used" in facts
    assert "Shelf is 964 mm long" in facts          # over the 900 mm span rule
    assert "3 copies: at least 2" in facts          # 3 x 1.35 m2 of 18 mm needs two sheets
    assert "QUOTE: none saved." in facts


def test_edge_band_proposal_becomes_exact_settings_per_board():
    proposals = resolve_actions(
        [{"type": "edge_band", "rows": [1], "edges": "long", "tape_mm": 0.5}], SUMMARY,
        current_overrides={"b3": {"edge_band": [0, 0, 0, 2]}},
    )
    assert len(proposals) == 1 and proposals[0]["type"] == "overrides"
    assert proposals[0]["overrides"] == {
        "b3": {"edge_band": [0, 0, 0, 2]},            # existing setting kept
        "b1": {"edge_band": [0, 0.5, 0, 0.5]},
        "b2": {"edge_band": [0, 0.5, 0, 0.5]},
    }
    assert proposals[0]["title"] == "0.5 mm tape on both long edges of 2 parts"


def test_rename_and_quote_proposals():
    proposals = resolve_actions(
        [
            {"type": "rename", "row": 3, "name": "  Back   panel "},
            {"type": "quote", "labour": 5000, "margin_percent": 15, "customer": "Mrs Rao"},
        ],
        SUMMARY, current_quote={"hardware": 800, "labour": 100},
    )
    by_type = {p["type"]: p for p in proposals}
    assert by_type["overrides"]["overrides"] == {"b4": {"label": "Back panel"}}
    assert by_type["quote"]["quote"] == {"hardware": 800, "labour": 5000.0, "margin_percent": 15.0, "customer": "Mrs Rao"}


@pytest.mark.parametrize("action", [
    {"type": "edge_band", "rows": [99], "edges": "front", "tape_mm": 2},       # no such row
    {"type": "edge_band", "rows": "all", "edges": "diagonal", "tape_mm": 2},   # no such edge
    {"type": "edge_band", "rows": "all", "edges": "all", "tape_mm": 40},       # absurd tape
    {"type": "rename", "row": 1, "name": ""},
    {"type": "quote", "labour": -500, "margin_percent": 9000},
    {"type": "resize", "row": 1, "length": 10},                                # not an allowed action
    {"type": "delete_project"},
])
def test_bad_or_unknown_proposals_are_dropped(action):
    assert resolve_actions([action], SUMMARY) == []


def test_generic_names_are_recognised():
    assert all(is_generic_name(n) for n in ("Part 4", "Mesh", "object_12", "Group#3", "", "17"))
    assert not any(is_generic_name(n) for n in ("Left side", "Shelf 2", "Back"))


def test_assistant_survives_a_model_that_ignores_the_json_contract(provider):
    provider("Sorry, here is plain text.")
    assert ai.assistant("hi", "FACTS") == {"reply": "Sorry, here is plain text.", "actions": []}
    provider('```json\n{"reply": "ok", "actions": ["junk", {"type": "quote", "labour": 1}]}\n```')
    assert ai.assistant("hi", "FACTS") == {"reply": "ok", "actions": [{"type": "quote", "labour": 1}]}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def test_ai_routes_say_so_when_ai_is_off(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ai, "llm_available", lambda: False)
    token = _signup(client, "off@example.com")["token"]
    assert client.get("/api/tools/ai", headers=_auth(token)).json() == {"available": False}
    r = client.post("/api/tools/ai/sketch", files={"file": ("s.png", b"x", "image/png")}, headers=_auth(token))
    assert r.status_code == 503
    assert client.get("/api/tools/ai").status_code == 401


def test_assistant_route_answers_and_proposes_without_changing_anything(client, provider):  # noqa: F811
    token = _signup(client, "assistant@example.com")["token"]
    project = _described_project(client, token)
    fake = provider(json.dumps({
        "reply": "I can put 2 mm tape on the front edges and set your quote.",
        "actions": [
            {"type": "edge_band", "rows": "all", "edges": "front", "tape_mm": 2},
            {"type": "quote", "labour": 2000, "margin_percent": 20},
            {"type": "resize", "row": 1, "length": 5},
        ],
    }))

    r = client.post(
        f"/api/projects/{project['id']}/ai/chat",
        json={"message": "tape the fronts, labour 2000, 20% margin", "language": "hi"},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"].startswith("I can put")
    assert [p["type"] for p in body["proposals"]] == ["overrides", "quote"]
    assert body["proposals"][1]["quote"]["margin_percent"] == 20

    # The model was given computed facts and told the reply language.
    system, facts = (m["content"] for m in fake.requests[0]["messages"][:2])
    assert "Hindi" in system and "PARTS (row." in facts and "SUMMARY: 2 sheets" in facts

    # Nothing was saved: the plan and settings are as they were.
    after = client.get(f"/api/projects/{project['id']}", headers=_auth(token)).json()
    assert after["settings"] == {"overrides": {}, "quote": None}

    # Applying a proposal is the ordinary settings call.
    r = client.put(
        f"/api/projects/{project['id']}/settings",
        json={"overrides": body["proposals"][0]["overrides"]}, headers=_auth(token),
    )
    assert r.status_code == 200 and r.json()["rerun"] is True


def test_assistant_route_is_private_and_needs_a_plan(client, provider):  # noqa: F811
    provider('{"reply": "x", "actions": []}')
    owner = _signup(client, "owner@example.com")["token"]
    other = _signup(client, "other@example.com")["token"]
    project = _described_project(client, owner)
    url = f"/api/projects/{project['id']}/ai/chat"
    assert client.post(url, json={"message": "hi"}, headers=_auth(other)).status_code == 404
    assert client.post(url, json={"message": "  "}, headers=_auth(owner)).status_code == 400
    assert client.post(url, json={"message": "hi"}).status_code == 401


def test_daily_allowance(client, provider, monkeypatch):  # noqa: F811
    from cutlist_engine.saas import ai_routes

    monkeypatch.setattr(ai_routes, "AI_DAILY_LIMIT", 1)
    ai_routes._usage.clear()
    provider(speech="wardrobe 2100 high")
    token = _signup(client, "limit@example.com")["token"]
    send = lambda: client.post(  # noqa: E731
        "/api/tools/ai/transcribe", files={"file": ("n.webm", b"abc", "audio/webm")}, headers=_auth(token),
    )
    first = send()
    assert first.status_code == 200 and first.json() == {"text": "wardrobe 2100 high"}
    assert send().status_code == 429


def test_sketch_route_returns_a_sentence_to_check(client, provider):  # noqa: F811
    from cutlist_engine.saas import ai_routes

    ai_routes._usage.clear()
    token = _signup(client, "sketch@example.com")["token"]
    provider('{"readable": true, "kind": "wardrobe", "height": 2100, "width": 1200, "shelves": 4, "shutters": 2}')
    r = client.post("/api/tools/ai/sketch", files={"file": ("s.jpg", b"jpeg", "image/jpeg")}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json() == {"description": "Wardrobe 2100 high, 1200 wide, 4 shelves, 2 shutters", "missing": ["depth"]}

    provider('{"readable": false}')
    r = client.post("/api/tools/ai/sketch", files={"file": ("s.jpg", b"jpeg", "image/jpeg")}, headers=_auth(token))
    assert r.status_code == 422 and "could not read sizes" in r.json()["detail"]
