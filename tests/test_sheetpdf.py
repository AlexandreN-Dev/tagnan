import os
import re
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from tagnan import studysheet
from tagnan.ui import sheetpdf
from tests.conftest import sheet_data

META = {
    "course": "AWS Certified AI Practitioner",
    "where": "Domain 3",
    "source": "Amazon Bedrock User Guide, Knowledge Bases",
    "date": "25 November 2026",
    "stage": 2,
}


@pytest.fixture(scope="module", autouse=True)
def qt_app() -> QApplication:
    app = QApplication.instance() or QApplication([])  # as tests/test_ui.py has it
    assert isinstance(app, QApplication)
    return app


def pages(path: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page(?!s)", path.read_bytes()))


def setting() -> sheetpdf.Page:
    """A page to set words on: nothing is painted."""
    return sheetpdf.Page(QPainter(), QImage(8, 8, QImage.Format.Format_ARGB32), 0)


def drawn(sheet: dict[str, Any]) -> QImage:
    """The page as a picture, a pixel for a CSS pixel."""
    image = QImage(794, 1123, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    sheetpdf.draw(painter, image, sheet, META)
    painter.end()
    return image


def above_the_footer(image: QImage) -> bool:
    """Whether the band above the footer's line stayed paper white: nothing ran into it."""
    footer_line = round(sheetpdf.H - sheetpdf.FOOT_H)
    return all(
        image.pixelColor(x, y) == QColor("white")
        for x in range(0, 794, 7)
        for y in range(footer_line - 12, footer_line - 2)
    )


# Long words, as a course's own are: the worst a sheet's words can do to a page.
LONG = [
    "knowledge",
    "retrieval",
    "embedding",
    "guardrails",
    "foundation",
    "inference",
    "evaluation",
    "responsible",
    "governance",
    "orchestration",
]


def wordy(count: int, start: int = 0) -> str:
    return " ".join(LONG[(start + i) % len(LONG)] for i in range(count))


def fullest_sheet() -> dict[str, Any]:
    """Every block filled, every field at the most words tagnan.studysheet lets through."""
    most = studysheet.MAX_WORDS

    def side(i: int) -> dict[str, str]:
        return {"name": wordy(most["side"], i), "what": wordy(most["what"], i + 2), "icon": "gear"}

    def cell(good: bool, i: int) -> dict[str, Any]:
        return {"good": good, "text": wordy(most["cell"], i)}

    return studysheet.clean(
        {
            "title": wordy(most["title"]),
            "tagline": wordy(most["tagline"], 3),
            "versus": {
                "left": side(0),
                "right": side(4),
                "rows": [
                    {
                        "label": wordy(most["label"], i),
                        "left": cell(True, i),
                        "right": cell(False, i + 5),
                    }
                    for i in range(studysheet.MAX_ROWS)
                ],
            },
            "steps": {
                "title": wordy(most["steps"]),
                "list": [
                    {
                        "name": wordy(most["step"], i),
                        "what": wordy(most["what"], i + 1),
                        "icon": "gear",
                    }
                    for i in range(studysheet.MAX_STEPS)
                ],
            },
            "terms": [
                {"name": wordy(most["term"], i), "what": wordy(most["definition"], i + 2)}
                for i in range(studysheet.MAX_TERMS)
            ],
            "trap": wordy(most["trap"], 1),
            "remember": wordy(most["remember"], 6),
        }
    )


def test_a_sheet_is_one_a4_page_in_the_folder(tmp_path: Path) -> None:
    path = sheetpdf.write(studysheet.clean(sheet_data()), META, tmp_path)
    assert path == tmp_path / "Tagnan – RAG or fine-tuning.pdf"
    assert path.read_bytes().startswith(b"%PDF")
    assert pages(path) == 1
    again = sheetpdf.write(studysheet.clean(sheet_data()), META, tmp_path)
    assert again.name == "Tagnan – RAG or fine-tuning (2).pdf"
    assert path.exists()  # never written over
    assert sorted(p.name for p in tmp_path.iterdir()) == [again.name, path.name]


@pytest.mark.parametrize("left_out", ["versus", "steps", "terms"])
def test_a_sheet_without_a_block_still_draws(tmp_path: Path, left_out: str) -> None:
    sheet = studysheet.clean(sheet_data())
    sheet[left_out] = [] if left_out == "terms" else {}
    assert pages(sheetpdf.write(sheet, META, tmp_path)) == 1


def test_a_failure_leaves_no_half_written_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(sheet: dict[str, object], meta: dict[str, object], path: Path) -> None:
        path.write_bytes(b"%PDF half")
        raise OSError("disk full")

    monkeypatch.setattr(sheetpdf, "render", broken)
    with pytest.raises(OSError, match="disk full"):
        sheetpdf.write(studysheet.clean(sheet_data()), META, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_too_long_a_sheet_shrinks_to_stay_above_the_footer() -> None:
    data = sheet_data(title="Amazon Bedrock Guardrails against every denied topic")
    for term in data["terms"]:
        term["what"] = "A definition long enough to take four or five lines in its little card."
    assert above_the_footer(drawn(studysheet.clean(data)))


def test_the_fullest_sheet_stays_above_the_footer() -> None:
    sheet = fullest_sheet()
    assert above_the_footer(drawn(sheet))
    # And it takes no less than the smallest scale a body may have.
    page = setting()
    page.draw = False
    top = sheetpdf.hero(page, sheet, META) + 32
    assert (
        sheetpdf.fitting(page, sheet, sheetpdf.H - sheetpdf.FOOT_H - 24 - top) > sheetpdf.SMALLEST
    )


def test_a_body_set_smaller_keeps_the_pages_margins() -> None:
    image = drawn(fullest_sheet())
    # The comparison's two cards, wherever the body starts: their fills reach the margins.
    left, right = QColor(sheetpdf.SIDE_L), QColor(sheetpdf.SIDE_R)
    rows = [[image.pixelColor(x, y) for x in range(794)] for y in range(330, 1040, 3)]
    first = min(row.index(left) for row in rows if left in row)
    last = max(793 - row[::-1].index(right) for row in rows if right in row)
    assert abs(first - sheetpdf.SIDE) <= 1.5
    assert abs(last - (sheetpdf.W - sheetpdf.SIDE)) <= 1.5


def test_a_sheet_that_fits_is_drawn_at_full_size() -> None:
    sheet = studysheet.clean(sheet_data())
    sheet["steps"] = {}  # room to spare, whatever the faces at hand
    image = drawn(sheet)
    left = QColor(sheetpdf.SIDE_L)
    tall = sum(any(image.pixelColor(x, y) == left for x in range(60, 330, 6)) for y in range(1123))
    assert abs(tall - (18 + 64 + 3 * 50 + 8)) <= 1  # the comparison's card, as the mockup's


def test_a_long_title_takes_two_lines_at_most() -> None:
    page = setting()
    assert len(sheetpdf.headline(page, "RAG or fine-tuning?").lines) == 1
    long = sheetpdf.headline(page, "Amazon Bedrock Guardrails against every denied topic")
    assert len(long.lines) == 2
    assert 32 * 0.75 <= long.font.pointSizeF() <= 40 * 0.75


def test_a_long_tagline_is_set_smaller() -> None:
    page = setting()
    short = sheetpdf.tagline(page, "Facts that change every week? Hand the model the pages.")
    assert short.font.pointSizeF() == 20 * 0.75
    long = sheetpdf.tagline(page, wordy(studysheet.MAX_WORDS["tagline"]))
    assert long.font.pointSizeF() == 16 * 0.75


def test_no_word_is_left_alone_on_a_last_line() -> None:
    page = setting()
    font = sheetpdf.font(40, 700)
    metrics = page.metrics(font)
    title = "Bedrock Guardrails: Denied Topics"
    # Room for all but its last word: taken as they come, "Topics" would stand alone.
    width = metrics.horizontalAdvance(title) - 10
    assert page.wrap(title.split(), metrics, width) == ["Bedrock Guardrails: Denied", "Topics"]
    assert page.set(title, font, width, 42).lines == ["Bedrock Guardrails:", "Denied Topics"]


def test_evening_lines_out_cuts_no_word() -> None:
    page = setting()
    label = page.set("KNOWLEDGE RETRIEVAL EMBEDDING", sheetpdf.font(11, 700), 104, 12.65)
    assert label.lines == ["KNOWLEDGE", "RETRIEVAL", "EMBEDDING"]


def test_a_word_too_long_for_a_line_is_cut() -> None:
    page = setting()
    long = "pneumonoultramicroscopic" * 2
    text = page.set(f"a {long}", sheetpdf.font(14), 120, 19)
    assert len(text.lines) > 2
    assert "".join(text.lines) == f"a{long}"
    assert text.width <= 120


def test_words_that_go_together_are_set_at_one_size() -> None:
    page = setting()
    long = "Measures bias, explains predictions, cites its passages"
    together = page.fit(["Not its job", long], 16.5, 14.5, 209, 1.2, weight=600)
    # The long one cannot hold on a line: both are set at the smallest size, the short one too.
    assert {t.font.pointSizeF() for t in together} == {14.5 * 0.75}
    assert len(together[0].lines) == 1
    assert len(together[1].lines) > 1
    short = page.fit(["Not its job", "Not filtered"], 16.5, 14.5, 209, 1.2, weight=600)
    assert {t.font.pointSizeF() for t in short} == {16.5 * 0.75}


def test_a_side_gets_a_taller_head_for_words_on_two_lines() -> None:
    page = setting()
    page.draw = False
    versus = studysheet.clean(sheet_data())["versus"]
    as_drawn = sheetpdf.versus(page, versus, 0.0)
    assert as_drawn == 18 + 64 + 3 * 50 + 8  # the mockup's card
    versus["left"]["what"] = "retrieves your documents first, answers afterwards"
    assert sheetpdf.versus(page, versus, 0.0) > as_drawn
