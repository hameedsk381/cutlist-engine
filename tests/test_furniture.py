"""Description -> parts: sizes come from carcass rules in code, never from an LLM."""
from pathlib import Path

import pytest

from cutlist_engine.boards import extract_boards
from cutlist_engine.furniture import build_parts, describe_to_model, parse_spec
from cutlist_engine.parsers import load_obj

WARDROBE = "Wardrobe 2100 high, 1200 wide, 600 deep, 2 shutters, 4 shelves"


def sizes(parts):
    return {p.name: (p.length, p.width, p.thickness) for p in parts}


def test_parse_reads_kind_size_and_counts():
    spec = parse_spec(WARDROBE)

    assert (spec.kind, spec.height, spec.width, spec.depth) == ("wardrobe", 2100, 1200, 600)
    assert (spec.shelves, spec.shutters, spec.plinth) == (4, 2, 75)


def test_parse_handles_units_word_order_and_number_words():
    spec = parse_spec("Open bookshelf, height 6 ft, width 80 cm, depth 300, five shelves")

    assert spec.kind == "bookshelf"
    assert spec.height == pytest.approx(1828.8)
    assert (spec.width, spec.depth, spec.shelves, spec.shutters) == (800, 300, 5, 0)


def test_parse_reads_bare_triple_as_height_width_depth_and_says_so():
    spec = parse_spec("kitchen base unit 720 x 600 x 560 with 1 shelf and 1 shutter")

    assert (spec.kind, spec.height, spec.width, spec.depth) == ("base_cabinet", 720, 600, 560)
    assert any("height x width x depth" in note for note in spec.notes)


def test_parse_asks_for_missing_size_in_plain_language():
    with pytest.raises(ValueError, match="depth"):
        parse_spec("wardrobe 2100 high and 1200 wide")


def test_parse_rejects_implausible_sizes():
    with pytest.raises(ValueError, match="do not look right"):
        parse_spec("wardrobe 21 high, 12 wide, 6 deep")


def test_llm_is_only_asked_for_parameters_the_rules_missed():
    asked = []

    def fake_llm(text):
        asked.append(text)
        return {"depth": 550, "height": 9999, "kind": "wardrobe"}

    spec = parse_spec("storage 2000 high 900 wide", llm_extract=fake_llm)

    assert asked and spec.depth == 550
    assert spec.height == 2000  # a size the rules found is never overridden
    assert spec.kind == "wardrobe"


def test_wardrobe_parts_follow_the_carcass_rules():
    parts, notes = build_parts(parse_spec(WARDROBE))

    got = sizes(parts)
    assert got["Left side"] == got["Right side"] == (2100, 600, 18)
    assert got["Top"] == got["Bottom"] == (1164, 600, 18)
    assert got["Skirting"] == (1164, 75, 18)
    assert got["Back"] == (1989, 1164, 6)
    assert got["Partition"] == (1989, 594, 18)
    assert [got[f"Shelf {i}"] for i in range(1, 5)] == [(574, 573, 18)] * 4
    assert got["Shutter 1"] == got["Shutter 2"] == (2019, 595, 18)
    assert len(parts) == 13
    assert any("partition" in note for note in notes)


def test_generated_model_extracts_to_exactly_the_same_parts(tmp_path: Path):
    model = describe_to_model(WARDROBE)
    path = tmp_path / model["filename"]
    path.write_text(model["obj"], encoding="utf-8")

    extraction = extract_boards(load_obj(path), expected_thickness=18)

    extracted = sorted((b.source_objects[0], b.length, b.width, b.thickness) for b in extraction.boards)
    planned = sorted((p["name"], p["length"], p["width"], p["thickness"]) for p in model["parts"])
    assert extracted == planned
    assert extraction.report.confidence == 1.0
    assert extraction.report.skipped_parts == ()


def test_too_many_shelves_is_refused():
    with pytest.raises(ValueError, match="Too many shelves"):
        build_parts(parse_spec("bookshelf 400 high, 600 wide, 300 deep, 12 shelves"))
