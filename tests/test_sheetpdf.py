import os
import re
from pathlib import Path

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
    sheet = studysheet.clean(data)
    image = QImage(794, 1123, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    sheetpdf.draw(painter, image, sheet, META)
    painter.end()
    # The band above the footer's line stays paper white: nothing ran into it.
    footer_line = round(sheetpdf.H - sheetpdf.FOOT_H)
    for x in range(0, 794, 7):
        for y in range(footer_line - 12, footer_line - 2):
            assert image.pixelColor(x, y) == QColor("white"), (x, y)
