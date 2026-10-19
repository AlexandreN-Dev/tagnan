"""Tagnan's menu: a panel of his own, in his bubbles' style, opened by a right click on him or
on his tray icon. What it shows (his grade, the next question, the pace, the call), what a few
words typed at its top would do ("break 45", "often", "learn pottery"), where it opens, and
running its commands. TagnanMenu.qml draws it.
"""

import logging
from typing import Any

from PySide6.QtCore import Property, QObject, QPoint, Signal, Slot

from tagnan import pause as pauses
from tagnan import progress as rules
from tagnan.scheduler import PACES
from tagnan.ui import sounds as calls
from tagnan.ui.controller import Controller
from tagnan.ui.placement import Box, screen_area
from tagnan.ui.updater import Updater

logger = logging.getLogger(__name__)

MARGIN = 16  # from the screen's edges: never against them, let alone past them
GAP = 6  # between the menu and a list beside it
MAX_SUGGESTIONS = 6
COMMANDS = (
    # (action, label, words that find it)
    ("ask", "A question now", ("question", "ask", "quiz", "now", "en garde")),
    ("stats", "Progress", ("progress", "stats", "score", "points", "grade")),
    ("subject", "Subject…", ("subject", "topic", "course", "learn")),
    ("pause", "A break…", ("break", "pause", "rest", "stop")),
    ("resume", "Resume now", ("resume", "back", "continue")),
    ("update", "Update", ("update", "upgrade", "new version", "version")),
    ("restart", "Restart Tagnan", ("restart", "reload", "start again", "reboot")),
    ("quit", "Quit Tagnan", ("quit", "exit", "close", "bye")),
)
BREAK_WORDS = ("break", "pause", "a break", "rest")
LEARN_WORDS = ("learn", "study")
FOCUS_WORDS = ("subject", "focus", "on")


def menu_position(anchor: tuple[int, int], size: tuple[int, int], area: Box) -> tuple[int, int]:
    """Top-left corner of the menu opened at the pointer: below and right of it as menus open,
    flipped up or left where the screen ends, always on the screen."""
    (x, y), (width, height) = anchor, size
    if x + width > area.right - MARGIN:
        x -= width
    if y + height > area.bottom - MARGIN:
        y -= height
    x = max(area.x + MARGIN, min(x, area.right - MARGIN - width))
    y = max(area.y + MARGIN, min(y, area.bottom - MARGIN - height))
    return x, y


def _words(text: str) -> str:
    return " ".join(text.casefold().split()).strip(" .!?")


def _after(text: str, words: tuple[str, ...]) -> str | None:
    """What follows one of the words at the start of the text, or None."""
    folded = _words(text)
    for word in sorted(words, key=len, reverse=True):
        if folded == word:
            return ""
        if folded.startswith(word + " "):
            return " ".join(text.split())[len(word) + 1 :].strip()
    return None


class Menu(QObject):
    changed = Signal()  # shown, where, what it shows

    def __init__(self, controller: Controller, updater: Updater | None = None) -> None:
        super().__init__()
        self._controller = controller
        self._updater = updater
        self._shown = False
        self._anchor = (0, 0)
        self._x = self._y = 0
        self._sub_left = False
        self._area = Box(0, 0, 1920, 1080)
        self._size = (300, 430)  # the panel's, as QML last laid it out
        self._sub_width = 230
        controller.menuRequested.connect(self.openAt)
        for signal in (controller.prefsChanged, controller.statusChanged, controller.stageChanged):
            signal.connect(self._refresh)
        if updater is not None:
            updater.changed.connect(self._refresh)

    # --- What QML reads -----------------------------------------------------------------------

    @Property(bool, notify=changed)
    def shown(self) -> bool:
        return self._shown

    @Property(int, notify=changed)
    def x(self) -> int:
        return self._x

    @Property(int, notify=changed)
    def y(self) -> int:
        return self._y

    @Property(list, notify=changed)
    def anchor(self) -> list[int]:
        """The pointer it opened at: the panel grows out of it as it opens."""
        return list(self._anchor)

    @Property(bool, notify=changed)
    def subLeft(self) -> bool:
        """The pace's and the call's lists open on the left: no room on the right."""
        return self._sub_left

    @Property(list, notify=changed)
    def area(self) -> list[int]:
        """The screen's free area (taskbar left out): the menu's window covers all of it while
        open and never moves or resizes, lest the panel jump as the lists open and close."""
        a = self._area
        return [a.x, a.y, a.width, a.height]

    @Property(int, notify=changed)
    def areaTop(self) -> int:
        """The highest a list beside the menu may start, on the menu's screen."""
        return self._area.y + MARGIN

    @Property(int, notify=changed)
    def areaBottom(self) -> int:
        """The lowest a list beside the menu may end."""
        return self._area.bottom - MARGIN

    @Property(dict, notify=changed)
    def content(self) -> dict[str, Any]:
        c = self._controller
        s = c.game.summary()
        now = c._clock()
        paused = c.scheduler.paused_until > now
        band_start = rules.GRADES[s["grade"]].threshold
        band_end = s["next_threshold"]
        if band_end is None:
            share, points = 1.0, f"{s['points']} points · the highest grade"
        else:
            share = (s["points"] - band_start) / max(1, band_end - band_start)
            points = f"{s['points']} of {band_end} points to {s['next_name']}"
        if s["streak"] > 1:
            points += f" · streak {s['streak']}"
        bp, subject = c.game.blueprint, c.game.subject
        pace = c.scheduler.rhythm.pace
        call = dict(calls.CALLS).get(str(c.call), "Silent")
        return {
            "stage": s["grade"],
            "grade": s["grade_name"],
            "share": max(0.0, min(1.0, share)),
            "points": points,
            "paused": paused,
            "next": f"until {pauses.clock(c.scheduler.paused_until, now)}"
            if paused
            else f"next ~{pauses.clock(c.scheduler.next_at, now)}",
            "subject": bp.code if subject.whole else subject.name(bp),
            "subjectFull": c.game.topic(),
            "pace": pace.name if pace else "Your own",
            "paceKey": pace.key if pace else "",
            "call": call,
            "sound": call if str(c.call) == calls.SILENT else f"{call} · {c.volume} %",
            "volume": c.volume,
            "callKey": str(c.call),
            "paces": [{"key": p.key, "name": p.name, "hint": p.hint} for p in PACES],
            "calls": [{"key": k, "name": name} for k, name in calls.CALLS]
            + [{"key": calls.SILENT, "name": "Silent"}],
            # His Update row (tagnan/ui/updater.py), None without updates.
            "update": self._updater.row() if self._updater else None,
            # His Restart row, the same way; gold when his folder holds what he does not run.
            "restart": self._updater.restart_row() if self._updater else None,
        }

    # --- Opening and closing ------------------------------------------------------------------

    @Slot(int, int)
    def openAt(self, x: int, y: int) -> None:
        """Open at the pointer: placed at once with the panel's last size, so that its window
        is where it belongs from its first frame."""
        self._anchor = (x, y)
        self._shown = True
        if self._updater is not None:
            self._updater.look_here()  # a commit of one's own since he started lights Restart
        self._layout()
        self.changed.emit()

    @Slot()
    def close(self) -> None:
        if self._shown:
            self._shown = False
            self.changed.emit()

    @Slot(int, int, int)
    def place(self, width: int, height: int, sub_width: int) -> None:
        """The panel's size, known once QML has laid it out; the lists' width, to know their
        side."""
        before = (self._x, self._y, self._sub_left, self._area)
        self._size, self._sub_width = (width, height), sub_width
        self._layout()
        if (self._x, self._y, self._sub_left, self._area) != before:
            self.changed.emit()

    def _layout(self) -> None:
        area = screen_area(QPoint(*self._anchor))
        width = self._size[0]
        self._x, self._y = menu_position(self._anchor, self._size, area)
        self._sub_left = self._x + width + GAP + self._sub_width > area.right - MARGIN
        self._area = area

    def _refresh(self) -> None:
        if self._shown:
            self.changed.emit()

    def _updates(self) -> bool:
        return self._updater is not None and self._updater.row() is not None

    # --- Typing -------------------------------------------------------------------------------

    @Slot(str, result=list)
    def suggest(self, text: str) -> list[dict[str, str]]:
        """What the words typed so far could mean, the likeliest first: {label, sub, action}."""
        folded = _words(text)
        if not folded:
            return []
        c = self._controller
        found: list[dict[str, str]] = []

        def add(label: str, action: str, sub: str = "") -> None:
            if all(f["action"] != action for f in found):
                found.append({"label": label, "sub": sub, "action": action})

        now = c._clock()
        rest = _after(text, BREAK_WORDS)
        understood = pauses.parse(rest if rest else text, now, c.scheduler.rhythm.start_hour)
        if understood is not None and (rest or rest is None):
            said, _, back = pauses.describe(understood, now).partition(", ")
            add(said, f"pause:{rest or text}", back.capitalize())
        rest = _after(text, LEARN_WORDS)
        if rest:
            preview = c.previewCourse(rest)
            if preview["ok"]:
                add(f"Learn {rest}", f"learn:{rest}", preview["text"])
        rest = _after(text, FOCUS_WORDS)
        if rest:
            preview = c.previewSubject(rest)
            if preview["ok"]:
                add(f"Questions on {rest}", f"focus:{rest}", preview["text"])
        paused = c.scheduler.paused_until > now
        for action, label, words in COMMANDS:
            if (action == "resume" and not paused) or (
                action in ("update", "restart") and not self._updates()
            ):
                continue
            if any(w.startswith(folded) or folded in w for w in (label.casefold(), *words)):
                add(label, action)
        everything = folded in ("how often", "pace", "rhythm", "frequency")
        paces = sorted(PACES, key=lambda p: not p.name.casefold().startswith(folded))
        for p in paces:
            if everything or p.name.casefold().startswith(folded) or folded in p.key:
                add(f"How often: {p.name}", f"pace:{p.key}", p.hint)
        everything = folded in ("sound", "sounds", "call", "music")
        for key, name in [*calls.CALLS, (calls.SILENT, "Silent")]:
            if everything or name.casefold().startswith(folded) or folded in ("mute", "quiet"):
                add(f"Sound: {name}", f"call:{key}")
        return found[:MAX_SUGGESTIONS]

    # --- Running ------------------------------------------------------------------------------

    @Slot(str, result=bool)
    def run(self, action: str) -> bool:
        """Do what a row or a suggestion says; True when the menu stays open (a call heard)."""
        c = self._controller
        verb, _, arg = action.partition(":")
        logger.info("menu: %s", action)
        if verb == "call":
            c.setCall(arg)
            return True  # one hears a call, then the next, and keeps the last
        if verb == "volume":
            if arg.isdigit():
                c.setVolume(int(arg))
            return True  # heard at once, the list stays open to try another
        if verb == "update":
            if self._updater is not None:
                self._updater.activate()
            return True  # it says how it goes, until he starts again
        self.close()
        match verb:
            case "ask":
                c.askNow()
            case "stats":
                c.showStats()
            case "subject":
                c.showSubject()
            case "pause":
                if not arg or not c.pauseWith(arg):
                    c.showPause()
            case "resume":
                c.resume()
            case "pace":
                c.setPace(arg)
            case "learn":
                c.learnWith(arg)
            case "focus":
                c.subjectWith(arg)
            case "restart":
                if self._updater is not None:
                    self._updater.restart()
            case "quit":
                c.quit()
        return False
