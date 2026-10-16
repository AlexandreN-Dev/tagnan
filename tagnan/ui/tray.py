"""Tagnan in the notification area: his icon at his grade, and his menu (also on a right click
on him)."""

from collections.abc import Callable, Sequence
from functools import lru_cache

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction, QActionGroup, QCursor, QIcon, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from tagnan import art
from tagnan.scheduler import PACES
from tagnan.ui import sounds as calls
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


class KeepOpen(QObject):
    """A click on a choice picks it and leaves its menu open: one hears a sound, then the next,
    and keeps the last. Escape or a click elsewhere closes the menu."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            isinstance(watched, QMenu)
            and isinstance(event, QMouseEvent)
            and event.type() == QEvent.Type.MouseButtonRelease
        ):
            action = watched.actionAt(event.position().toPoint())
            if action is not None and action.isEnabled() and action.isCheckable():
                action.trigger()
                return True
        return super().eventFilter(watched, event)


class Tray(QObject):
    def __init__(self, controller: Controller) -> None:
        super().__init__()
        self._controller = controller
        self._keep_open = KeepOpen(self)
        self.menu = QMenu()
        self._add("A question now", controller.askNow)
        self._add("Progress", controller.showStats)
        self.menu.addSeparator()
        self.paces = self._choices(
            "How often", [(p.key, f"{p.name}\t{p.hint}") for p in PACES], controller.setPace
        )
        self.calls = self._choices(
            "Sound",
            [*calls.CALLS, None, (calls.SILENT, "Silent")],
            controller.setCall,
            listen="Click one to hear it",
        )
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
        controller.prefsChanged.connect(self._restyle)
        controller.menuRequested.connect(lambda: self.menu.popup(QCursor.pos()))
        self._restyle()

    def _add(self, label: str, slot: object) -> QAction:
        action = self.menu.addAction(label)
        action.triggered.connect(slot)
        return action

    def _choices(
        self,
        title: str,
        items: Sequence[tuple[str, str] | None],
        choose: Callable[[str], None],
        listen: str = "",
    ) -> dict[str, QAction]:
        """A submenu of choices, one ticked; None among the items is a separator. With
        `listen`, a hint at its top, and a click keeps it open."""
        submenu = self.menu.addMenu(title)
        group = QActionGroup(submenu)  # exclusive
        if listen:
            submenu.addAction(listen).setEnabled(False)
            submenu.installEventFilter(self._keep_open)
        actions = {}
        for item in items:
            if item is None:
                submenu.addSeparator()
                continue
            key, label = item
            action = submenu.addAction(label)
            action.setCheckable(True)
            group.addAction(action)
            action.triggered.connect(lambda _checked=False, key=key: choose(key))
            actions[key] = action
        return actions

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._controller.showStats()

    def _restyle(self) -> None:
        paused = bool(self._controller.paused)
        self._pause.setText("Change the break…" if paused else "A break…")
        self._resume.setVisible(paused)
        for key, action in self.paces.items():
            action.setChecked(key == str(self._controller.pace))
        for key, action in self.calls.items():
            action.setChecked(key == str(self._controller.call))
        if self.icon is not None:
            self.icon.setIcon(figure_icon(self._controller.stage))
            self.icon.setToolTip(str(self._controller.status) + (" · on a break" if paused else ""))
