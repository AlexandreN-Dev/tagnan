"""Tagnan in the notification area: his icon at his grade, and his menu (also on a right click
on him)."""

from functools import lru_cache

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QCursor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from tagnan import art
from tagnan.ui.controller import Controller
from tagnan.ui.images import render_svg


@lru_cache(maxsize=6)
def figure_icon(stage: int) -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64):
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
    def __init__(self, controller: Controller) -> None:
        super().__init__()
        self._controller = controller
        self.menu = QMenu()
        self._add("A question now", controller.askNow)
        self._add("Progress", controller.showStats)
        self.menu.addSeparator()
        self._pause = self._add("A break…", controller.showPause)
        self._resume = self._add("Resume", controller.resume)
        self.menu.addSeparator()
        self._add("Quit Tagnan", controller.quit)
        self.icon: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.icon = QSystemTrayIcon(figure_icon(controller.stage))
            self.icon.setContextMenu(self.menu)
            self.icon.activated.connect(self._activated)
            self.icon.show()
        controller.stageChanged.connect(self._restyle)
        controller.statusChanged.connect(self._restyle)
        controller.menuRequested.connect(lambda: self.menu.popup(QCursor.pos()))
        self._restyle()

    def _add(self, label: str, slot: object) -> QAction:
        action = self.menu.addAction(label)
        action.triggered.connect(slot)
        return action

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._controller.showStats()

    def _restyle(self) -> None:
        paused = bool(self._controller.paused)
        self._pause.setText("Change the break…" if paused else "A break…")
        self._resume.setVisible(paused)
        if self.icon is not None:
            self.icon.setIcon(figure_icon(self._controller.stage))
            self.icon.setToolTip(str(self._controller.status) + (" · on a break" if paused else ""))
