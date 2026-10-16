"""What the window asks of Windows: is now a good time to pop up? Where is he kept?"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# SHQueryUserNotificationState: 5 accepts notifications, 6 quiet time after a first logon.
# The others (locked or screensaver, busy full screen, Direct3D game, presentation) mean later.
WELCOME_STATES = frozenset({5, 6})


def busy() -> bool:
    """True when Windows would hold a notification back: locked session, full-screen
    application or game, presentation. Never on other systems."""
    if sys.platform == "win32":
        import ctypes

        state = ctypes.c_int(0)
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
            return False
        return state.value not in WELCOME_STATES
    return False


# GetAsyncKeyState reads the physical buttons: left and right, swapped or not.
VK_LBUTTON, VK_RBUTTON = 0x01, 0x02


def mouse_down() -> bool:
    """Whether a mouse button is down now, wherever the pointer is. Never on other systems."""
    if sys.platform == "win32":
        import ctypes

        state = ctypes.windll.user32.GetAsyncKeyState
        return bool(state(VK_LBUTTON) & 0x8000 or state(VK_RBUTTON) & 0x8000)
    return False


class Settings:
    """The window's own settings (its place on the screen, his pace, his call), as JSON next to
    the database; without a path, kept in memory only."""

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._data: dict[str, Any] = {}
        if path is not None:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            self._data = data if isinstance(data, dict) else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except OSError as error:
            logger.warning("settings not saved: %s", error)
