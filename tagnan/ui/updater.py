"""Keeps Tagnan up to date, for his menu's Update: asks scripts/update what is new on GitHub a
minute after he starts, then about once a day, and takes it when asked; then hands over to
`scripts/update restart`, which outlives the window and starts him again in his new version,
and he says what changed once he is back."""

import json
import logging
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from tagnan.brain_client import decode
from tagnan.paths import REPO
from tagnan.ui import desktop

logger = logging.getLogger(__name__)

FIRST_CHECK_MS = 60_000  # a minute after he starts: never in the way of his first steps
CHECK_EVERY = 20 * 3600.0  # then about once a day
TICK_MS = 3_600_000  # he looks at the clock every hour: a laptop sleeps, timers with it
CHECK_TIMEOUT = 90.0
APPLY_TIMEOUT = 180.0
NEWS_KEY = "updated"  # in his settings: what changed, for his bubble once he is back
# The row in his menu for each state: label, value, gold "New" pill, busy, stressed.
ROWS = {
    "idle": ("Update", "", False, False, False),
    "checking": ("Update", "Checking…", False, False, False),
    "uptodate": ("Update", "Up to date", False, False, False),
    "new": ("Update", "New", True, False, True),
    "updating": ("Updating…", "back in a moment", False, True, False),
    "failed": ("Update", "Try again", False, False, False),
}


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class UpdateClient:
    """How the window reaches scripts/update: directly in WSL or on a Mac, through wsl.exe from
    Windows. One JSON answer on stdout."""

    command: tuple[str, ...]

    @classmethod
    def local(cls, repo: Path = REPO) -> "UpdateClient":
        return cls((str(repo / "scripts" / "update"),))

    @classmethod
    def through_wsl(cls, distro: str, repo: str) -> "UpdateClient":
        """From Windows: repo is the repository's path inside WSL, e.g. /home/me/tagnan."""
        return cls(("wsl.exe", "-d", distro, "-e", f"{repo.rstrip('/')}/scripts/update"))

    def call(self, action: str, timeout: float) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        if sys.platform == "win32":
            extra["creationflags"] = subprocess.CREATE_NO_WINDOW  # no console flashing
        try:
            done = subprocess.run(  # noqa: S603 - fixed argument list, no shell
                [*self.command, action],
                capture_output=True,
                timeout=timeout,
                check=False,
                **extra,
            )
        except subprocess.TimeoutExpired:
            raise UpdateError(f"no answer within {timeout:.0f} s") from None
        except OSError as error:
            raise UpdateError(f"cannot start scripts/update: {error}") from None
        if done.returncode != 0:
            message = decode(done.stderr).strip().splitlines()
            failed = f"scripts/update failed ({done.returncode})"
            raise UpdateError(message[-1] if message else failed)
        try:
            answer = json.loads(done.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise UpdateError("unreadable answer from scripts/update") from None
        if not isinstance(answer, dict):
            raise UpdateError("unexpected answer from scripts/update")
        return answer

    def check(self) -> dict[str, Any]:
        return self.call("check", CHECK_TIMEOUT)

    def apply(self) -> dict[str, Any]:
        return self.call("apply", APPLY_TIMEOUT)

    def restart(self, setup: bool) -> None:
        """Start `scripts/update restart`, which outlives the window: it waits for it to be
        gone, makes its environment again if `setup`, then starts Tagnan."""
        args = [*self.command, "restart", *(["--setup"] if setup else [])]
        quiet: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
        if sys.platform == "win32":
            flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            away = flags | subprocess.CREATE_BREAKAWAY_FROM_JOB
            try:  # out of the window's job, if it has one, lest it go with the window
                subprocess.Popen(args, creationflags=away, **quiet)  # noqa: S603
            except OSError:
                subprocess.Popen(args, creationflags=flags, **quiet)  # noqa: S603
        else:
            subprocess.Popen(args, start_new_session=True, **quiet)  # noqa: S603


def _in_a_thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, daemon=True).start()


class Updater(QObject):
    changed = Signal()
    failed = Signal(str, str)  # title, text: what he says in his bubble
    restartRequested = Signal(bool)  # updated: start again (True: his window's environment too)
    _answered = Signal(str, object, bool)  # action, answer or error, asked from his menu

    def __init__(
        self,
        client: UpdateClient | None,
        settings: desktop.Settings | None = None,
        clock: Callable[[], float] = time.time,
        run: Callable[[Callable[[], None]], None] = _in_a_thread,
    ) -> None:
        """No client: no updates (development snapshots, a CPU measure)."""
        super().__init__()
        self.client = client
        self._settings = settings or desktop.Settings(None)
        self._clock = clock
        self._run = run
        self._state = "idle"
        self._news: list[str] = []
        self._checked_at = 0.0
        self._answered.connect(self._on_answer)
        self._first = QTimer(self)
        self._first.setSingleShot(True)
        self._first.timeout.connect(lambda: self.check(asked=False))
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._maybe_check)

    def start(self) -> None:
        if self.client is not None:
            self._first.start(FIRST_CHECK_MS)
            self._tick.start(TICK_MS)

    # --- What his menu reads ------------------------------------------------------------------

    @Property(str, notify=changed)
    def state(self) -> str:
        return self._state

    @Property(list, notify=changed)
    def news(self) -> list[str]:
        return list(self._news)

    def row(self) -> dict[str, Any] | None:
        """His menu's Update row, None when there is nothing to update with."""
        if self.client is None:
            return None
        label, value, pill, busy, strong = ROWS[self._state]
        return {"label": label, "value": value, "pill": pill, "busy": busy, "strong": strong}

    # --- Doing --------------------------------------------------------------------------------

    @Slot()
    def activate(self) -> None:
        """His menu's Update: take the new version, or look again for one."""
        if self._state == "new":
            self.apply()
        elif self._state not in ("checking", "updating"):
            self.check(asked=True)

    def check(self, asked: bool = False) -> None:
        client = self.client
        if client is None or self._state in ("checking", "updating"):
            return
        self._set("checking")
        self._checked_at = self._clock()
        self._run(lambda: self._work("check", client.check, asked))

    def apply(self) -> None:
        client = self.client
        if client is None or self._state == "updating":
            return
        self._set("updating")
        self._run(lambda: self._work("apply", client.apply, True))

    def _maybe_check(self) -> None:
        if self._clock() - self._checked_at >= CHECK_EVERY:
            self.check(asked=False)

    def _work(self, action: str, call: Callable[[], dict[str, Any]], asked: bool) -> None:
        try:
            answer: object = call()
        except UpdateError as error:
            answer = error
        self._answered.emit(action, answer, asked)

    def _on_answer(self, action: str, answer: object, asked: bool) -> None:
        if isinstance(answer, UpdateError) or not isinstance(answer, dict):
            logger.warning("update %s failed: %s", action, answer)
            self._set("failed")
            if asked:
                self.failed.emit("No update for now", f"I couldn't reach my updates: {answer}.")
            return
        if not answer.get("ok"):
            logger.info("update %s refused: %s", action, answer.get("reason"))
            self._set("failed")
            if asked:
                self.failed.emit("No update for now", str(answer.get("message") or ""))
            return
        if action == "check":
            behind = int(answer.get("behind") or 0)
            self._news = [str(line) for line in answer.get("news") or []]
            logger.info("update check: %d new commits", behind)
            self._set("new" if behind else "uptodate")
            return
        if not answer.get("updated"):
            self._set("uptodate")
            return
        self._news = [str(line) for line in answer.get("news") or []]
        self._settings.set(NEWS_KEY, {"news": self._news, "at": self._clock()})
        logger.info("updated, starting again (setup: %s)", bool(answer.get("setup")))
        self.restartRequested.emit(bool(answer.get("setup")))

    def _set(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.changed.emit()
