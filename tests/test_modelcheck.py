"""Modelling problems: found by code, explained by AI, never invented."""
from __future__ import annotations

import json

from cutlist_engine import ai
from cutlist_engine.modelcheck import find_problems, problems_as_facts

from test_ai_layer import provider  # noqa: F401 - pytest fixture


def _board(i, thickness=18.0, label=None, length=600.0, width=400.0):
    return {"id": f"part_{i:03d}", "label": label or f"Component {i}", "length": length,
            "width": width, "thickness": thickness}


def _summary(**over):
    base = {
        "boards": [_board(i) for i in range(10)],
        "extraction_report": {"skipped_parts": [], "solid_part_count": 10, "inferred_board_count": 0},
        "model_fix_report": {"passes_gate": True, "confidence": 0.95, "confidence_threshold": 0.7},
        "material_summary": {"sheet_count": 2, "utilization_percent": 70.0},
        "oversize_parts": [],
    }
    base.update(over)
    return base


def _codes(problems):
    return [item["code"] for item in problems["items"]]


def test_a_clean_model_has_no_problems():
    named = [_board(i, label=f"Shelf {i}") for i in range(10)]
    assert find_problems(_summary(boards=named)) == {"severity": "none", "items": []}


def test_the_messy_model_is_described_with_its_own_numbers():
    boards = [_board(i, thickness=t) for i, t in enumerate([4, 8, 10, 18, 20, 26, 40, 45, 50, 18])]
    skipped = [f"Handle {i} (not a flat panel)" for i in range(6)]
    problems = find_problems(_summary(
        boards=boards,
        extraction_report={"skipped_parts": skipped, "solid_part_count": 16, "inferred_board_count": 4},
        material_summary={"sheet_count": 9, "utilization_percent": 29.0},
    ))
    assert problems["severity"] in {"medium", "high"}
    assert {"skipped_solids", "many_thicknesses", "low_use", "inferred", "unnamed"} <= set(_codes(problems))
    by_code = {i["code"]: i for i in problems["items"]}
    assert "6 solid part" in by_code["skipped_solids"]["detail"]
    assert "Handle 1" in by_code["skipped_solids"]["detail"] and "not a flat panel" not in by_code["skipped_solids"]["detail"]
    assert "9 sheets" in by_code["low_use"]["detail"] and "29%" in by_code["low_use"]["detail"]
    assert all(item["fix"] for item in problems["items"])


def test_parts_bigger_than_the_sheet_and_a_failed_gate_are_high():
    problems = find_problems(_summary(
        oversize_parts=[{"length": 2550.0, "width": 52.0, "thickness": 7.0}],
        model_fix_report={"passes_gate": False, "confidence": 0.4, "confidence_threshold": 0.7},
    ))
    assert problems["severity"] == "high"
    assert {"oversize", "low_confidence"} <= set(_codes(problems))
    assert "2550 x 52" in next(i for i in problems["items"] if i["code"] == "oversize")["detail"]


def test_a_few_skipped_parts_in_a_big_model_are_not_a_problem():
    skipped = ["Handle 1", "Handle 2", "Leg 1"]
    problems = find_problems(_summary(
        boards=[_board(i, label=f"Panel {i}") for i in range(30)],
        extraction_report={"skipped_parts": skipped, "solid_part_count": 33, "inferred_board_count": 0},
    ))
    assert "skipped_solids" not in _codes(problems)


FACTS = problems_as_facts(
    {"items": [{"severity": "medium", "title": "Sheets are mostly empty",
                "detail": "9 sheets are planned but only 29% of their area is used."}]},
    "kitchen.skp",
)


def test_facts_are_plain_lines_with_the_file_name():
    assert FACTS.startswith("File: kitchen.skp") and "9 sheets" in FACTS


def test_ai_explains_the_problems(provider):
    fake = provider(json.dumps({
        "headline": "Most of your sheets are nearly empty.",
        "explanation": "9 sheets are planned, but only 29% is used. Probably extra pieces are counted as boards.",
        "steps": ["Hide handles and decoration, then export again."],
    }))
    result = ai.explain_model_problems(FACTS)
    assert result["headline"].startswith("Most of your sheets")
    assert result["steps"] == ["Hide handles and decoration, then export again."]
    sent = fake.requests[0]["messages"]
    assert "kitchen.skp" in sent[1]["content"] and "29%" in sent[1]["content"]


def test_an_answer_with_an_invented_number_is_thrown_away(provider):
    provider(json.dumps({
        "headline": "Sheets are empty.",
        "explanation": "9 sheets are planned and only 29% is used, so you will waste 12 sheets of money.",
        "steps": [],
    }))
    assert ai.explain_model_problems(FACTS) is None


def test_a_malformed_or_missing_answer_gives_none(provider):
    provider("not json at all")
    assert ai.explain_model_problems(FACTS) is None
    provider(json.dumps({"headline": "", "explanation": "x"}))
    assert ai.explain_model_problems(FACTS) is None


def test_no_ai_and_no_facts_give_none(monkeypatch):
    monkeypatch.setattr(ai, "llm_available", lambda: False)
    assert ai.explain_model_problems(FACTS) is None
    monkeypatch.setattr(ai, "llm_available", lambda: True)
    assert ai.explain_model_problems("  ") is None


def test_the_serialised_plan_carries_the_problems():
    from pathlib import Path
    import tempfile

    from cutlist_engine.furniture import describe_to_model
    from cutlist_engine.parsers import load_model
    from cutlist_engine.pipeline import ProcessConfig, process_triangles
    from cutlist_engine.server import _serialize_result

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "m.obj"
        path.write_text(describe_to_model("Kitchen base unit 720 high, 600 wide, 560 deep, 1 shelf, 1 shutter")["obj"])
        payload = _serialize_result(process_triangles(load_model(path), ProcessConfig()))
    assert set(payload["model_problems"]) == {"severity", "items"}
