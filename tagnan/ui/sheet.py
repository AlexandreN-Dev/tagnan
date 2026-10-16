"""The reference sheet: every grade at rest, then every expression of one grade, rendered by QtSvg
from tagnan.art (the window's own pieces). Works offscreen, in WSL or on Windows.

    uv run python -m tagnan.ui.sheet build/sheet.png [--grade 5] [--light]
"""

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from tagnan import art

CELL_W, CELL_H = 220, 256


def render(svg: str, width: int, height: int, background: QColor | None = None) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(background or QColor(0, 0, 0, 0))
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    if not renderer.isValid():
        raise ValueError("SVG invalide")
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, width, height))
    painter.end()
    return image


def sheet(grade: int, background: QColor) -> QImage:
    rows = [
        [art.still_svg(stage) for stage in range(6)],
        [art.still_svg(grade, e) for e in art.EXPRESSIONS[1:]],
    ]
    image = QImage(CELL_W * 6, CELL_H * len(rows), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(background)
    painter = QPainter(image)
    for r, row in enumerate(rows):
        for c, svg in enumerate(row):
            painter.drawImage(c * CELL_W, r * CELL_H, render(svg, CELL_W, CELL_H))
    painter.end()
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description="Tagnan's reference sheet")
    parser.add_argument("out", type=Path)
    parser.add_argument("--grade", type=int, default=5, choices=range(6))
    parser.add_argument("--light", action="store_true", help="fond clair")
    args = parser.parse_args()
    app = QGuiApplication(sys.argv[:1])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    background = QColor("#E4E8F0" if args.light else "#1D2433")
    ok = sheet(args.grade, background).save(str(args.out))
    del app
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
