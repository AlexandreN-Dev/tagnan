import re
from pathlib import Path

import pytest

from tagnan import studysheet
from tests.conftest import sheet_data


def test_the_brains_words_are_kept_as_they_are() -> None:
    sheet = studysheet.clean(sheet_data())
    assert sheet["title"] == "RAG or fine-tuning?"
    assert sheet["versus"]["left"] == {
        "name": "Fine-tuning",
        "what": "learns by heart",
        "icon": "learn",
    }
    assert sheet["versus"]["rows"][0] == {
        "label": "To update",
        "left": {"good": False, "text": "Retrain: hours, $$$"},
        "right": {"good": True, "text": "Sync: minutes"},
    }
    assert len(sheet["steps"]["list"]) == 4
    assert len(sheet["terms"]) == 3


def test_too_many_words_are_cut_and_markdown_dropped() -> None:
    long = " ".join(f"word{i}" for i in range(40))
    sheet = studysheet.clean(sheet_data(title=f"**{long}**", trap=long))
    assert sheet["title"].endswith("…")
    assert len(sheet["title"].split()) == studysheet.MAX_WORDS["title"]
    assert "*" not in sheet["title"]
    assert len(sheet["trap"].split()) == studysheet.MAX_WORDS["trap"]


def test_a_page_keeps_three_rows_five_steps_three_terms() -> None:
    data = sheet_data()
    data["versus"]["rows"] *= 2
    data["steps"]["list"] *= 2
    data["terms"] *= 2
    sheet = studysheet.clean(data)
    assert len(sheet["versus"]["rows"]) == studysheet.MAX_ROWS
    assert len(sheet["steps"]["list"]) == studysheet.MAX_STEPS
    assert len(sheet["terms"]) == studysheet.MAX_TERMS


def test_a_comparison_or_steps_may_be_left_out_but_not_both() -> None:
    no_steps = studysheet.clean(sheet_data(steps={"title": "", "list": []}))
    assert no_steps["steps"] == {}
    assert no_steps["versus"]["rows"]
    one_row = sheet_data()
    one_row["versus"]["rows"] = one_row["versus"]["rows"][:1]
    assert studysheet.clean(one_row)["versus"] == {}  # a comparison needs two rows
    with pytest.raises(ValueError, match="neither"):
        studysheet.clean(sheet_data(versus={}, steps={}))
    with pytest.raises(ValueError, match="title"):
        studysheet.clean(sheet_data(title=" "))


def test_an_unknown_icon_becomes_an_idea() -> None:
    data = sheet_data()
    data["steps"]["list"][0]["icon"] = "unicorn"
    assert studysheet.clean(data)["steps"]["list"][0]["icon"] == "idea"


def test_every_icon_is_a_path_the_schema_offers() -> None:
    offered = studysheet.SCHEMA["properties"]["versus"]["properties"]["left"]["properties"]["icon"]
    assert offered["enum"] == list(studysheet.ICONS)
    for name, path in {**studysheet.ICONS, **studysheet.MARKS}.items():
        assert re.fullmatch(r"M[\d\s.,\-MmLlHhVvCcSsQqTtAaZz]+", path), name


def test_file_names_are_safe_and_never_overwrite(tmp_path: Path) -> None:
    assert studysheet.file_name("RAG or fine-tuning?") == "Tagnan – RAG or fine-tuning.pdf"
    assert studysheet.file_name('A/B: "tests" <now>.') == "Tagnan – A B tests now.pdf"
    assert studysheet.file_name("...") == "Tagnan – Study sheet.pdf"
    first = studysheet.free_path(tmp_path, "Tagnan – X.pdf")
    assert first.name == "Tagnan – X.pdf"
    first.write_bytes(b"%PDF")
    second = studysheet.free_path(tmp_path, "Tagnan – X.pdf")
    assert second.name == "Tagnan – X (2).pdf"
    second.write_bytes(b"%PDF")
    assert studysheet.free_path(tmp_path, "Tagnan – X.pdf").name == "Tagnan – X (3).pdf"
