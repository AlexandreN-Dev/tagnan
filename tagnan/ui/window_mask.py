"""Input mask of the window: only Tagnan and his bubble take clicks, the rest goes through
(Dartt's window mask, for several rectangles)."""

from PySide6.QtCore import QObject, QRect, Slot
from PySide6.QtGui import QRegion, QWindow


class WindowMask(QObject):
    def __init__(self) -> None:
        super().__init__()
        self._window: QWindow | None = None
        self._region = QRegion()

    def attach(self, window: QWindow) -> None:
        self._window = window
        self._apply()

    @Slot("QVariantList")
    def setRects(self, rects: list[list[float]]) -> None:
        region = QRegion()
        for x, y, width, height in rects:
            region = region.united(QRegion(QRect(round(x), round(y), round(width), round(height))))
        self._region = region
        self._apply()

    def _apply(self) -> None:
        if self._window is not None and not self._region.isEmpty():
            self._window.setMask(self._region)
