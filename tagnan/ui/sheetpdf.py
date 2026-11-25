"""A study sheet drawn into a one-page A4 PDF, as docs/mockup.html shows it (look A, cards on
white): the brain's words (tagnan.studysheet), his colours and faces, his figure. Qt alone draws
it (QPdfWriter, QtSvg): no other dependency. Saved in Downloads, never over another file.

The page is laid out in CSS pixels (794 x 1123, A4 at 96 dpi), as the mockup's; lines are set
one by one, at the mockup's line heights.
"""

import logging
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, QMarginsF, QPointF, QRectF, QStandardPaths, Qt, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QPageSize,
    QPaintDevice,
    QPainter,
    QPdfWriter,
    QPen,
)
from PySide6.QtSvg import QSvgRenderer

from tagnan import art, studysheet

logger = logging.getLogger(__name__)

W, H = 794.0, 1123.0
SIDE = 56.0  # the page's side margins
BODY_W = W - 2 * SIDE
FOOT_H = 58.0
GAP = 24.0  # between the blocks of the body

PAPER, INK, MUTED, LINE, CARD = "#FFFFFF", "#1B2232", "#5B6478", "#E6EAF0", "#F3F6FB"
GOLD, CORAL, CORAL_SOFT, MINT = "#F2C14E", "#EF6351", "#FFE8E3", "#16A374"
HUES = ("#3B82F6", "#8B6CF0", "#F0A92E", "#16A374")  # the steps' and the terms' colours
SIDE_L, SIDE_R, SAY, SAY_INK, TRAP_INK = "#FFF0EC", "#E6F7EF", "#E6F7EF", "#0C5B42", "#9B2C22"
TAGLINE = "#DFE8F8"

BODY_FACES = ["Segoe UI", "Helvetica Neue", "Helvetica", "Arial"]
DISPLAY_FACES = ["Georgia", "Times New Roman"]


def font(px: float, weight: int = 400, italic: bool = False, display: bool = False) -> QFont:
    f = QFont()
    f.setFamilies(DISPLAY_FACES if display else BODY_FACES)
    f.setPointSizeF(px * 0.75)  # at 96 dpi, as the page is drawn
    f.setWeight(QFont.Weight(weight))
    f.setItalic(italic)
    return f


def spaced(f: QFont, px: float) -> QFont:
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, px)
    return f


@dataclass
class Text:
    """Lines set at a CSS line height."""

    lines: list[str]
    font: QFont
    line_height: float
    width: float  # the widest line

    @property
    def height(self) -> float:
        return len(self.lines) * self.line_height


class Page:
    """Measures and draws on the PDF; with draw False, measures only (to fit the page)."""

    def __init__(self, painter: QPainter, device: QPaintDevice, stage: int) -> None:
        self.p = painter
        self.device = device
        self.stage = stage
        self.draw = True

    def metrics(self, f: QFont) -> QFontMetricsF:
        return QFontMetricsF(f, self.device)

    def wrap(self, words: Sequence[str], m: QFontMetricsF, width: float) -> list[str]:
        """The words on as few lines as `width` allows, a word too long for a line cut where
        it must."""
        lines: list[str] = []
        for word in words:
            if lines and m.horizontalAdvance(f"{lines[-1]} {word}") <= width:
                lines[-1] = f"{lines[-1]} {word}"
                continue
            while len(word) > 1 and m.horizontalAdvance(word) > width:
                cut = len(word) - 1
                while cut > 1 and m.horizontalAdvance(word[:cut]) > width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            lines.append(word)
        return lines or [""]

    def set(self, text: str, f: QFont, width: float, line_height: float) -> Text:
        """The text wrapped at `width`, its lines as even as that many lines can be, so that
        no word stands alone on the last one. Evened out only to be drawn: that keeps the
        number of lines, which is all that measuring counts."""
        m = self.metrics(f)
        words = text.split()
        lines = self.wrap(words, m, width)
        if self.draw and len(lines) > 1:
            # Never narrower than its longest word: evening lines out cuts no word.
            narrow = min(width, max(m.horizontalAdvance(word) for word in words))
            wide = width
            while wide - narrow > 0.5:
                middle = (narrow + wide) / 2
                if len(self.wrap(words, m, middle)) > len(lines):
                    narrow = middle
                else:
                    wide = middle
            lines = self.wrap(words, m, wide)
        widest = max(m.horizontalAdvance(line) for line in lines)
        return Text(lines, f, line_height, widest)

    def fit(
        self, text: str, px: float, smallest: float, width: float, ratio: float, **face: Any
    ) -> Text:
        """On one line if it can be, from px down to `smallest`; wrapped otherwise."""
        size = px
        while True:
            t = self.set(text, font(size, **face), width, size * ratio)
            if len(t.lines) == 1 or size - 1 < smallest:
                return t
            size -= 1

    def write(
        self, t: Text, x: float, y: float, colour: str, align: str = "left", width: float = 0
    ) -> None:
        if not self.draw:
            return
        m = self.metrics(t.font)
        self.p.setFont(t.font)
        self.p.setPen(QColor(colour))
        for i, line in enumerate(t.lines):
            top = y + i * t.line_height
            baseline = top + (t.line_height - (m.ascent() + m.descent())) / 2 + m.ascent()
            left = x
            if align == "center":
                left = x + (width - m.horizontalAdvance(line)) / 2
            self.p.drawText(QPointF(left, baseline), line)

    def box(self, rect: QRectF, radius: float, fill: str, pen: QPen | None = None) -> None:
        if not self.draw:
            return
        self.p.setPen(pen or Qt.PenStyle.NoPen)
        self.p.setBrush(QColor(fill))
        self.p.drawRoundedRect(rect, radius, radius)

    def circle(self, cx: float, cy: float, r: float, fill: str) -> None:
        self.box(QRectF(cx - r, cy - r, 2 * r, 2 * r), r, fill)

    def icon(self, path: str, rect: QRectF, colour: str = "#FFFFFF", stroke: float = 2.2) -> None:
        self.svg(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="{stroke}"'
            ' stroke-linecap="round" stroke-linejoin="round"/></svg>',
            rect,
        )

    def svg(self, svg: str, rect: QRectF) -> None:
        if self.draw:
            QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(self.p, rect)


def heading(page: Page, text: str, y: float) -> float:
    t = page.set(text.upper(), spaced(font(13, 700), 1.56), BODY_W, 13)
    page.write(t, SIDE, y, MUTED)
    return y + 13 + 14


def hero(page: Page, sheet: dict[str, Any], meta: dict[str, Any]) -> float:
    """The band at the top: where it comes from, the title, the whole idea in one line."""
    tagline = page.set(sheet["tagline"], font(20), 470, 28)
    title = page.fit(sheet["title"], 56, 40, 600, 1.04, weight=700)
    title.font = spaced(title.font, -0.02 * title.font.pointSizeF() / 0.75)
    height = 48 + 24 + 18 + title.height + 16 + tagline.height + 40
    if page.draw:
        p = page.p
        band = QLinearGradient(0, 0, W, height)
        for at, colour in ((0.0, "#213D7C"), (0.58, "#2E57A8"), (1.0, "#4A72CC")):
            band.setColorAt(at, QColor(colour))
        p.save()
        p.setClipRect(QRectF(0, 0, W, height))
        p.fillRect(QRectF(0, 0, W, height), band)
        page.circle(W - 60, height, 150, CORAL)
        page.circle(W - 210, 12, 60, GOLD)
        page.circle(W - 208, height - 56, 26, MINT)
        p.restore()
    x = SIDE
    for word in (meta["course"], meta["where"]):
        chip = page.set(word, spaced(font(12, 600), 0.24), W, 12)
        if page.draw:
            fill = QColor(255, 255, 255, 41)
            page.p.setPen(Qt.PenStyle.NoPen)
            page.p.setBrush(fill)
            page.p.drawRoundedRect(QRectF(x, 48, chip.width + 22, 24), 12, 12)
        page.write(chip, x + 11, 54, "#FFFFFF")
        x += chip.width + 22 + 8
    page.write(title, SIDE, 90, "#FFFFFF")
    page.write(tagline, SIDE, 90 + title.height + 16, TAGLINE)
    return height


def versus(page: Page, v: dict[str, Any], y: float) -> float:
    """Two sides compared, row by row, a label between them."""
    side_w, mid_w = (BODY_W - 112) / 2, 112.0
    rows = v["rows"]
    texts = {
        k: [page.fit(r[k]["text"], 16.5, 13, side_w - 76, 1.2, weight=600) for r in rows]
        for k in ("left", "right")
    }
    row_h = max(50.0, *(t.height + 14 for k in texts for t in texts[k]))
    height = 18 + 64 + len(rows) * row_h + 8
    for k, x, fill, hue in (
        ("left", SIDE, SIDE_L, CORAL),
        ("right", SIDE + side_w + mid_w, SIDE_R, MINT),
    ):
        page.box(QRectF(x, y, side_w, height), 22, fill)
        page.box(QRectF(x + 20, y + 24, 52, 52), 16, hue)
        page.icon(studysheet.ICONS[v[k]["icon"]], QRectF(x + 32, y + 36, 28, 28))
        name = page.fit(v[k]["name"], 24, 16, side_w - 106, 1.1, weight=700)
        what = page.set(v[k]["what"], font(15, italic=True, display=True), side_w - 106, 18)
        top = y + 18 + (64 - name.height - 3 - what.height) / 2
        page.write(name, x + 86, top, INK)
        page.write(what, x + 86, top + name.height + 3, MUTED)
        for i, row in enumerate(rows):
            row_y = y + 18 + 64 + i * row_h
            if page.draw:
                pen = QPen(QColor(27, 34, 50, 41), 1, Qt.PenStyle.CustomDashLine)
                pen.setDashPattern([3, 3])
                page.p.setPen(pen)
                page.p.drawLine(QPointF(x + 20, row_y), QPointF(x + side_w - 20, row_y))
            good = row[k]["good"]
            page.circle(x + 32, row_y + row_h / 2, 12, MINT if good else CORAL)
            page.icon(
                studysheet.MARKS["yes" if good else "no"],
                QRectF(x + 25, row_y + row_h / 2 - 7, 14, 14),
                stroke=3,
            )
            t = texts[k][i]
            page.write(t, x + 56, row_y + (row_h - t.height) / 2, INK)
    mid_x = SIDE + side_w
    page.circle(mid_x + mid_w / 2, y + 18 + 32, 25, INK)
    vs = page.set("vs", font(16, 800), mid_w, 16)
    page.write(vs, mid_x, y + 18 + 24, "#FFFFFF", "center", mid_w)
    for i, row in enumerate(rows):
        label = page.set(row["label"].upper(), spaced(font(11, 700), 0.88), mid_w - 8, 12.65)
        page.write(
            label,
            mid_x + 4,
            y + 18 + 64 + i * row_h + (row_h - label.height) / 2,
            MUTED,
            "center",
            mid_w - 8,
        )
    return y + height


def steps(page: Page, s: dict[str, Any], y: float) -> float:
    """How it works: numbered circles in a row, dashes between them."""
    y = heading(page, s["title"], y)
    count = len(s["list"])
    col = (BODY_W - 12 * (count - 1)) / count
    names = [page.fit(x["name"], 18, 14, col, 1.1, weight=700) for x in s["list"]]
    whats = [page.set(x["what"], font(14), col, 18.9) for x in s["list"]]
    if page.draw:
        pen = QPen(QColor("#C9D2E2"), 3, Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([3, 7 / 3])
        page.p.setPen(pen)
        first, last = SIDE + col / 2, SIDE + col * (count - 1) + 12 * (count - 1) + col / 2
        page.p.drawLine(QPointF(first, y + 32), QPointF(last, y + 32))
    for i, step in enumerate(s["list"]):
        cx = SIDE + i * (col + 12) + col / 2
        page.circle(cx, y + 32, 38, PAPER)
        page.circle(cx, y + 32, 32, HUES[i % len(HUES)])
        page.icon(studysheet.ICONS[step["icon"]], QRectF(cx - 14, y + 18, 28, 28))
        page.circle(cx + 24, y + 8, 15, PAPER)
        page.circle(cx + 24, y + 8, 12, INK)
        number = page.set(str(i + 1), font(12, 800), 24, 24)
        page.write(number, cx + 12, y - 4, "#FFFFFF", "center", 24)
        page.write(names[i], cx - col / 2, y + 64 + 12, INK, "center", col)
        page.write(whats[i], cx - col / 2, y + 64 + 12 + names[i].height + 6, MUTED, "center", col)
    tallest = max(n.height + 6 + w.height for n, w in zip(names, whats, strict=True))
    return y + 64 + 12 + tallest


def terms(page: Page, items: list[dict[str, str]], y: float) -> float:
    """Words to know, a card each."""
    y = heading(page, "Words to know", y)
    count = len(items)
    card = (BODY_W - 14 * (count - 1)) / count
    names = [page.set(t["name"], font(16, 700), card - 54, 19.2) for t in items]
    whats = [page.set(t["what"], font(14), card - 36, 19.6) for t in items]
    height = 16 + max(n.height + 7 + w.height for n, w in zip(names, whats, strict=True)) + 18
    for i in range(count):
        x = SIDE + i * (card + 14)
        page.box(QRectF(x, y, card, height), 18, CARD)
        page.box(QRectF(x + 18, y + 16 + (19.2 - 10) / 2, 10, 10), 3, HUES[i % len(HUES)])
        page.write(names[i], x + 36, y + 16, INK)
        page.write(whats[i], x + 18, y + 16 + names[i].height + 7, MUTED)
    return y + height


def ending(page: Page, sheet: dict[str, Any], y: float) -> float:
    """The trap, askew, and a way to remember it, said by Tagnan."""
    trap_w = (BODY_W - 22) * 0.9 / 2.2
    say_x = SIDE + trap_w + 22
    figure_w, figure_h = 108.0, 108.0 * 176 / 150
    say_w = BODY_W - trap_w - 22 - 6 - figure_w
    key = spaced(font(12.5, 800), 1.5)
    trap = page.set(sheet["trap"], font(16, 600), trap_w - 45, 22.4)
    trap_h = 16 + 18 + 10 + trap.height + 18 + 5
    said = page.set(sheet["remember"], font(18, 700, italic=True, display=True), say_w - 40, 23.4)
    say_h = 16 + 12.5 + 9 + said.height + 18
    height = max(trap_h, say_h + 30, figure_h)
    bottom = y + height
    if sheet["trap"]:
        top = bottom - trap_h
        if page.draw:
            page.p.save()
            page.p.translate(SIDE + trap_w / 2, top + trap_h / 2)
            page.p.rotate(-1.5)
            page.p.translate(-(SIDE + trap_w / 2), -(top + trap_h / 2))
        page.box(
            QRectF(SIDE + 1.25, top + 1.25, trap_w - 2.5, trap_h - 2.5),
            20,
            CORAL_SOFT,
            QPen(QColor(CORAL), 2.5),
        )
        page.icon(studysheet.MARKS["trap"], QRectF(SIDE + 22, top + 18, 18, 18), CORAL, 2.4)
        page.write(page.set("THE TRAP", key, trap_w, 18), SIDE + 48, top + 18, CORAL)
        page.write(trap, SIDE + 22, top + 18 + 18 + 10, TRAP_INK)
        if page.draw:
            page.p.restore()
    if sheet["remember"]:
        top = bottom - 30 - say_h
        page.box(QRectF(say_x, top, say_w, say_h), 20, SAY)
        if page.draw:
            page.p.save()
            page.p.translate(say_x + say_w, bottom - 30 - 26 - 9)
            page.p.rotate(45)
            page.box(QRectF(-9, -9, 18, 18), 3, SAY)
            page.p.restore()
        page.write(page.set("REMEMBER", key, say_w, 12.5), say_x + 20, top + 16, MINT)
        page.write(said, say_x + 20, top + 16 + 12.5 + 9, SAY_INK)
    page.svg(
        art.still_svg(page.stage, "happy", glow=False),
        QRectF(SIDE + BODY_W - figure_w, bottom - figure_h, figure_w, figure_h),
    )
    return bottom


def blocks(sheet: dict[str, Any]) -> int:
    ending = 1 if sheet["trap"] or sheet["remember"] else 0
    return sum(map(bool, (sheet["versus"], sheet["steps"], sheet["terms"]))) + ending


def body(page: Page, sheet: dict[str, Any], y: float, gap: float = GAP) -> float:
    if sheet["versus"]:
        y = versus(page, sheet["versus"], y) + gap
    if sheet["steps"]:
        y = steps(page, sheet["steps"], y) + gap
    if sheet["terms"]:
        y = terms(page, sheet["terms"], y) + gap
    if sheet["trap"] or sheet["remember"]:
        y = ending(page, sheet, y) + gap
    return y - gap


def footer(page: Page, meta: dict[str, Any]) -> None:
    top = H - FOOT_H
    if page.draw:
        page.p.setPen(QPen(QColor(LINE), 1))
        page.p.drawLine(QPointF(0, top), QPointF(W, top))
    plain, strong = font(12.5), font(12.5, 600)
    lead = page.set("Read again:", plain, W, 18)
    page.write(lead, SIDE, top + 16, MUTED)
    sign = page.set(f"Tagnan · {meta['date']} · 1 / 1", plain, W, 18)
    page.write(sign, W - SIDE - sign.width, top + 16, MUTED)
    # What to read again, cut short rather than run into his signature.
    room = W - 2 * SIDE - lead.width - 5 - sign.width - 26 - 16
    said = page.metrics(strong).elidedText(
        meta["source"] or "your course", Qt.TextElideMode.ElideRight, room
    )
    page.write(Text([said], strong, 18, room), SIDE + lead.width + 5, top + 16, INK)
    page.svg(art.icon_svg(page.stage), QRectF(W - SIDE - sign.width - 26, top + 16, 18, 18))


def draw(
    painter: QPainter, device: QPaintDevice, sheet: dict[str, Any], meta: dict[str, Any]
) -> None:
    """The whole page, in CSS pixels. A body too long for the page shrinks, never below 75 %;
    a short one spreads its blocks over the room left."""
    page = Page(painter, device, int(meta.get("stage", 0)))
    page.draw = False
    top = hero(page, sheet, meta) + 32
    needed = body(page, sheet, top) - top
    room = H - FOOT_H - 24 - top
    scale = max(0.75, min(1.0, room / needed)) if needed > 0 else 1.0
    gap = GAP + max(0.0, min(40.0, (room - needed) / (blocks(sheet) + 1)))
    page.draw = True
    painter.fillRect(QRectF(0, 0, W, H), QColor(PAPER))
    hero(page, sheet, meta)
    painter.save()
    painter.translate(W / 2, top)
    painter.scale(scale, scale)
    painter.translate(-W / 2, -top)
    body(page, sheet, top + gap - GAP, gap)
    painter.restore()
    footer(page, meta)


def render(sheet: dict[str, Any], meta: dict[str, Any], path: Path) -> None:
    """The sheet as a one-page A4 PDF at `path`."""
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0))
    writer.setResolution(96)
    writer.setTitle(sheet["title"])
    writer.setCreator("Tagnan")
    painter = QPainter(writer)
    if not painter.isActive():
        raise OSError(f"cannot write {path}")
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(writer.width() / W, writer.height() / H)
        draw(painter, writer, sheet, meta)
    finally:
        painter.end()


def downloads() -> Path:
    """The user's Downloads folder, as the system names it."""
    found = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
    return Path(found) if found else Path.home() / "Downloads"


def write(sheet: dict[str, Any], meta: dict[str, Any], folder: Path | None = None) -> Path:
    """Draw the sheet into a new PDF in Downloads (or `folder`), next to nothing it would
    replace: "Tagnan – RAG or fine-tuning.pdf", else "… (2).pdf". Written under a temporary
    name first, so that a failure leaves no half a file."""
    folder = folder or downloads()
    folder.mkdir(parents=True, exist_ok=True)
    path = studysheet.free_path(folder, studysheet.file_name(sheet["title"]))
    partial = path.with_name(path.name + ".part")
    try:
        render(sheet, meta, partial)
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    logger.info("study sheet written: %s", path)
    return path


class Files:
    """Where his study sheets go and how they are shown: Downloads, the system's PDF reader and
    its file manager. The controller's tests give it files of their own."""

    def write(self, sheet: dict[str, Any], meta: dict[str, Any]) -> Path:
        return write(sheet, meta)

    def open(self, path: Path) -> None:
        open_file(path)

    def show(self, path: Path) -> None:
        show_in_folder(path)


def open_file(path: Path) -> None:
    """In the system's PDF reader."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def show_in_folder(path: Path) -> None:
    """Its folder, the file selected: Explorer on Windows, Finder on a Mac."""
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", f"/select,{path}"])  # noqa: S603, S607 - fixed arguments
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])  # noqa: S603, S607 - fixed arguments
            return
    except OSError as error:
        logger.warning("cannot show %s: %s", path, error)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
