"""A click anywhere else closes the bubble, as « Close » does.

The bubble never takes the keyboard, so Windows does not tell it when one clicks elsewhere:
while a bubble that may close is up, the mouse buttons are looked at a few times a second, and
a press outside Tagnan's windows closes it. Nothing is watched otherwise.
"""

from collections.abc import Callable

from PySide6.QtCore import QObject, QPoint, QTimer, Signal
from PySide6.QtGui import QCursor

from tagnan.ui import desktop

INTERVAL_MS = 40  # a click lasts about 100 ms: none is missed


class OutsideClicks(QObject):
    clickedOutside = Signal()

    def __init__(
        self,
        inside: Callable[[QPoint], bool],
        pressed: Callable[[], bool] = desktop.mouse_down,
        cursor: Callable[[], QPoint] = QCursor.pos,
    ) -> None:
        super().__init__()
        self._inside = inside
        self._pressed = pressed
        self._cursor = cursor
        self._was_down = False
        self._timer = QTimer(self)
        self._timer.setInterval(INTERVAL_MS)
        self._timer.timeout.connect(self.poll)

    def watch(self, on: bool) -> None:
        if on and not self._timer.isActive():
            # A button already down (the click that opened the bubble) does not count.
            self._was_down = self._pressed()
            self._timer.start()
        elif not on:
            self._timer.stop()

    @property
    def watching(self) -> bool:
        return self._timer.isActive()

    def poll(self) -> None:
        down = self._pressed()
        if down and not self._was_down and not self._inside(self._cursor()):
            self.clickedOutside.emit()
        self._was_down = down
