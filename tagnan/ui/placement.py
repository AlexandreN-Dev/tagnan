"""Where the bubble goes: beside Tagnan, on the screen he stands on, never off its edges.

Tagnan's window is just his size, so that he can be dragged anywhere; the bubble is a window of
its own, placed here whenever he moves or it changes size.
"""

from dataclasses import dataclass

from PySide6.QtCore import Property, QObject, QPoint, QRect, Signal, Slot
from PySide6.QtGui import QGuiApplication

# The bubble's window overlaps the empty margin of Tagnan's, so that its tail reaches him.
GAP = -22
ABOVE_FEET = 54  # the tail points at his body, this far above his feet
MARGIN = 8  # from the screen's edges


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


def bubble_position(figure: Box, bubble: tuple[int, int], area: Box) -> tuple[int, int, bool]:
    """Top-left corner of the bubble's window, and whether it is on Tagnan's left.

    On his left by default; on his right when the screen ends there; clamped to the screen
    either way (a bubble cut by the screen's edge is no use).
    """
    width, height = bubble
    left = (
        figure.x - GAP - width >= area.x + MARGIN
        or figure.right + GAP + width > area.right - MARGIN
    )
    x = figure.x - GAP - width if left else figure.right + GAP
    y = figure.bottom - ABOVE_FEET - height
    x = max(area.x + MARGIN, min(x, area.right - MARGIN - width))
    y = max(area.y + MARGIN, min(y, area.bottom - MARGIN - height))
    return x, y, left


def screen_area(point: QPoint) -> Box:
    app = QGuiApplication.instance()
    screen = QGuiApplication.screenAt(point) if isinstance(app, QGuiApplication) else None
    screen = screen or QGuiApplication.primaryScreen()
    if screen is None:
        return Box(0, 0, 1920, 1080)
    r: QRect = screen.availableGeometry()
    return Box(r.x(), r.y(), r.width(), r.height())


class Placement(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._x = self._y = 0
        self._left = True

    @Slot(int, int, int, int, int, int)
    def follow(self, fx: int, fy: int, fw: int, fh: int, bw: int, bh: int) -> None:
        """Tagnan's figure on the screen (x, y, width, height), and the bubble window's size."""
        figure = Box(fx, fy, fw, fh)
        area = screen_area(QPoint(fx + fw // 2, fy + fh // 2))
        x, y, left = bubble_position(figure, (bw, bh), area)
        if (x, y, left) != (self._x, self._y, self._left):
            self._x, self._y, self._left = x, y, left
            self.changed.emit()

    @Property(int, notify=changed)
    def bubbleX(self) -> int:
        return self._x

    @Property(int, notify=changed)
    def bubbleY(self) -> int:
        return self._y

    @Property(bool, notify=changed)
    def bubbleLeft(self) -> bool:
        return self._left
