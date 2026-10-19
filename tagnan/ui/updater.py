"""Keeps Tagnan up to date, for his menu's Update & Restart: asks scripts/update what is new on
GitHub a minute after he starts, then about once a day. A click takes what is new, if anything,
then hands over to `scripts/update restart`, which outlives the window and starts him again,
and he says what changed once he is back.

The row also lights up when his folder holds commits his window does not run yet (one's own, as
one works on him): `scripts/update here`, asked as he starts and as his menu opens, says which
commit the folder is at; a click then simply starts him again in them."""

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
HERE_TIMEOUT = 30.0
LOOK_AGAIN = 10.0  # seconds: his menu opened again soon after asks nothing more
NEWS_KEY = "updated"  # in his settings: what changed, for his bubble once he is back
# The row in his menu for each state: label, value, busy.
LABEL = "Update & Restart"
ROWS = {
    "idle": (LABEL, "", False),
    "checking": (LABEL, "Checking…", False),
    "uptodate": (LABEL, "", False),
    "new": (LABEL, "", False),
    "updating": ("Updating…", "back in a moment", True),
    "failed": (LABEL, "Try again", False),
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

    def call(self, action: str, timeout: float, *args: str) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        if sys.platform == "win32":
            extra["creationflags"] = subprocess.CREATE_NO_WINDOW  # no console flashing
        try:
            done = subprocess.run(  # noqa: S603 - fixed argument list, no shell
                [*self.command, action, *args],
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

    def here(self, running: str) -> dict[str, Any]:
        return self.call("here", HERE_TIMEOUT, *([running] if running else []))

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
        self._then_restart = False  # a click's check: whatever it finds, he starts again
        self._news: list[str] = []
        self._checked_at = 0.0
        # The commit his window runs, learnt as he starts; what his folder has beyond it.
        self._running = ""
        self._here: dict[str, Any] = {"moved": False, "news": [], "setup": False}
        self._looking = False
        self._looked_at = float("-inf")
        self._answered.connect(self._on_answer)
        self._first = QTimer(self)
        self._first.setSingleShot(True)
        self._first.timeout.connect(lambda: self.check(asked=False))
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._maybe_check)

    def start(self) -> None:
        if self.client is not None:
            self.look_here()
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
        """His menu's Update & Restart row, None when there is nothing to update with: a gold
        "New" for a new version on GitHub, or commits in his folder he does not run yet."""
        if self.client is None:
            return None
        label, value, busy = ROWS[self._state]
        fresh = not busy and (self._state == "new" or bool(self._here["moved"]))
        if fresh:
            value = "New"
        return {"label": label, "value": value, "pill": fresh, "busy": busy, "strong": fresh}

    # --- Doing --------------------------------------------------------------------------------

    def look_here(self) -> None:
        """Which commit his folder is at: the first answer is the one he runs."""
        client = self.client
        if client is None or self._looking or self._clock() - self._looked_at < LOOK_AGAIN:
            return
        self._looking = True
        self._looked_at = self._clock()
        running = self._running
        self._run(lambda: self._work("here", lambda: client.here(running), False))

    @Slot()
    def restart(self) -> None:
        """He quits and comes back, in what his folder holds."""
        if self.client is None:
            return
        news = [str(line) for line in self._here["news"]]
        if news:
            self._settings.set(NEWS_KEY, {"news": news, "at": self._clock()})
        logger.info("restarting (setup: %s)", bool(self._here["setup"]))
        self.restartRequested.emit(bool(self._here["setup"]))

    @Slot()
    def activate(self) -> None:
        """His menu's Update & Restart: take the new version and start again in it. Commits of
        one's own in his folder: start again in them. Else look for a new version first, and
        start again whatever the answer."""
        if self.client is None or self._state in ("checking", "updating"):
            return
        if self._state == "new":
            self.apply()
        elif self._here["moved"]:
            self.restart()
        else:
            self._then_restart = True
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
        if action == "here":
            self._on_here(answer)
            return
        if action == "check" and self._then_restart:
            self._then_restart = False
            if isinstance(answer, dict) and answer.get("ok") and int(answer.get("behind") or 0):
                self._news = [str(line) for line in answer.get("news") or []]
                self._set("new")
                self.apply()
            else:
                logger.info("nothing to take (%s): starting again", answer)
                self._set("uptodate" if isinstance(answer, dict) and answer.get("ok") else "failed")
                self.restart()
            return
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
            self._set("uptodate")  # GitHub had nothing more by the time he asked
            self.restart()
            return
        self._news = [str(line) for line in answer.get("news") or []]
        self._settings.set(NEWS_KEY, {"news": self._news, "at": self._clock()})
        logger.info("updated, starting again (setup: %s)", bool(answer.get("setup")))
        self.restartRequested.emit(bool(answer.get("setup")))

    def _on_here(self, answer: object) -> None:
        self._looking = False
        if not isinstance(answer, dict) or not answer.get("ok") or not answer.get("head"):
            logger.info("his folder unread: %s", answer)  # no signal, Restart still works
            return
        if not self._running:
            self._running = str(answer["head"])
            return
        here = {
            "moved": bool(answer.get("moved")),
            "news": [str(line) for line in answer.get("news") or []],
            "setup": bool(answer.get("setup")),
        }
        if here != self._here:
            self._here = here
            logger.info("his folder: %s", here)
            self.changed.emit()

    def _set(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.changed.emit()
