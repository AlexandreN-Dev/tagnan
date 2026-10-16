"""Tagnan in the notification area: his icon at his grade and his status in its tooltip. A right
click opens his menu (tagnan/ui/menu.py), as a right click on him does; a left click, his
progress (on macOS, where the menu bar knows only one click, his menu)."""

import sys
from functools import lru_cache

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QCursor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QSystemTrayIcon

from tagnan import art
from tagnan.ui.controller import Controller
from tagnan.ui.images import render_svg
from tagnan.ui.menu import Menu


@lru_cache(maxsize=6)
def figure_icon(stage: int) -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64):
        if stage == 0:  # the inkwell has an icon of its own, drawn to read that small
            icon.addPixmap(QPixmap.fromImage(render_svg(art.icon_svg(), size, size)))
            continue
        # The figure is taller than wide: keep its proportions, centred in a square.
        image = render_svg(art.still_svg(stage, glow=False), round(size * 120 / 140), size)
        square = QPixmap(size, size)
        square.fill(Qt.GlobalColor.transparent)
        painter = QPainter(square)
        painter.drawImage((size - image.width()) // 2, 0, image)
        painter.end()
        icon.addPixmap(square)
    return icon


class Tray(QObject):
    def __init__(self, controller: Controller, menu: Menu) -> None:
        super().__init__()
        self._controller = controller
        self._menu = menu
        self.icon: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.icon = QSystemTrayIcon(figure_icon(controller.stage))
            self.icon.activated.connect(self._activated)
            self.icon.show()
        controller.stageChanged.connect(self._restyle)
        controller.statusChanged.connect(self._restyle)
        self._restyle()

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        menu_click = reason == QSystemTrayIcon.ActivationReason.Context or (
            sys.platform == "darwin" and reason == QSystemTrayIcon.ActivationReason.Trigger
        )
        if menu_click:
            at = QCursor.pos()
            self._menu.openAt(at.x(), at.y())
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._controller.showStats()

    def tooltip(self) -> str:
        paused = bool(self._controller.paused)
        return str(self._controller.status) + (" · on a break" if paused else "")

    def _restyle(self) -> None:
        if self.icon is not None:
            self.icon.setIcon(figure_icon(self._controller.stage))
            self.icon.setToolTip(self.tooltip())
