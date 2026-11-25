"""The game in the window: when Tagnan asks, what his bubble says, what his figure does."""

import logging
import random
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QCursor

from tagnan import art, catalogue
from tagnan import blueprint as blueprints
from tagnan import config as configs
from tagnan import pause as pauses
from tagnan import progress as rules
from tagnan import subject as subjects
from tagnan.game import Added, Game, Outcome
from tagnan.model import CONVERTED, Question
from tagnan.scheduler import Scheduler, find_pace
from tagnan.ui import catalogues, desktop, sheetpdf
from tagnan.ui import sounds as calls
from tagnan.ui.animator import Animator
from tagnan.ui.sounds import Sounds
from tagnan.ui.worker import BrainWorker

logger = logging.getLogger(__name__)

LETTERS = "ABCDEF"
# Tagnan speaks English, as a Gascon would: an oath of his own country now and then.
ASKS = ("En garde!", "A question, Gascon!", "Your turn, musketeer!", "On your guard!")
CHEERS = ("Touché!", "Well parried!", "An unstoppable thrust!", "By my rapier, that's right!")
SCOLDS = ("Zounds!", "Sacrebleu!", "Blast it, no!", "By my sword, no!")
QUIPS = {
    "wink": ("Hey!", "That tickles!", "Easy there!"),
    "annoyed": ("Enough! I have a rapier, you know.",),
    "sulk": ("…",),
}
DIFFICULTY = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}
REVIEW_WHEN = {1: "tomorrow", 2: "in 3 days", 3: "in a week", 4: "in 3 weeks"}

TICK_MS = 15_000
UNANSWERED_MINUTES = 10  # a question left alone goes away, as if put off
BUSY_RETRY_MINUTES = 5
NO_QUESTION_RETRY_MINUTES = 2
REFILL_BACKOFF = 600.0  # after a failed batch, wait before asking the brain again
FIRST_QUESTION_DELAY = 20.0  # the very first question comes soon after the first batch
MOOD_SECONDS = {"happy": 4.0, "angry": 6.0}
# A promotion's evolution in Tagnan.qml: he takes his new look while both are white silhouettes,
# and shows it at the flash.
PROMOTION_SWAP_MS = 1300
PROMOTION_REVEAL_MS = 3850
RESULT_SECONDS = 15  # a right answer's bubble closes by itself, unless hovered
QUIP_SECONDS = 1.8
MAX_COURSE_WORDS = 120
BUSY_MODES = ("question", "thinking", "result", "explanation", "pause")
UPDATED_KEY = "updated"  # in his settings, from tagnan/ui/updater.py: what an update changed
UPDATED_SECONDS = 30
SHEET_NEWS_SECONDS = 12  # "Signed and sealed!": his study sheet is in Downloads
CATALOGUE_NEWS_SECONDS = 15  # what became of questions pasted or imported, a prompt copied
VERDICT_MODES = ("result", "thinking", "explanation")  # where a question's study sheet is offered
# Minimized (his menu's button beside the moon), he takes his full size for these bubbles only:
# he grows before the question shows, and goes back to his corner this long after the last.
FULL_SIZE_MODES = ("question", *VERDICT_MODES)
GROW_MS = 380  # Main.qml grows him in 350 ms
SHRINK_SECONDS = 3
THEMES = ("dark", "light")  # chosen in his menu; none: the system's


def counted(count: int, word: str) -> str:
    """ "1 question", "18 new questions"."""
    return f"{count} {word}{'' if count == 1 else 's'}"


def sheet_written(path: Path) -> dict[str, Any]:
    """His word once a study sheet is in Downloads."""
    return {
        "mode": "message",
        "title": "Signed and sealed!",
        "text": "Your sheet is in Downloads: one page, to read at a glance.",
        "file": path.name,
        "buttons": [
            {"label": "Open it", "action": "opensheet", "primary": True},
            {"label": "Show in folder", "action": "showfolder"},
        ],
    }


class Controller(QObject):
    stageChanged = Signal()
    sizeChanged = Signal()  # minimized or not, grown to ask or not
    promotionChanged = Signal()
    bubbleChanged = Signal()
    statusChanged = Signal()
    prefsChanged = Signal()  # his pace, hours, call, volume, subject, model or theme
    menuRequested = Signal(int, int)  # where the pointer is: his menu opens there
    quitRequested = Signal()

    def __init__(
        self,
        game: Game,
        scheduler: Scheduler,
        worker: BrainWorker,
        animator: Animator,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.time,
        settings: desktop.Settings | None = None,
        sounds: Sounds | None = None,
        model: str = configs.Brain.model,
        sheet_files: sheetpdf.Files | None = None,
        catalogue_files: catalogues.Files | None = None,
    ) -> None:
        super().__init__()
        self.game = game
        self.scheduler = scheduler
        self.worker = worker
        self.animator = animator
        self._rng = rng or random.Random()  # noqa: S311 - which interjection: not a secret
        self._clock = clock
        self.settings = settings or desktop.Settings(None)
        self.sounds = sounds or Sounds()
        self.sheet_files = sheet_files or sheetpdf.Files()
        self.catalogue_files = catalogue_files or catalogues.Files()
        # The hours and the pace chosen in his menu win over the config file's.
        hours = scheduler.rhythm.kept(self.settings.get("hours"))
        if hours != scheduler.rhythm:
            scheduler.set_rhythm(hours, clock())
        saved = find_pace(str(self.settings.get("pace", "")))
        if saved is not None:
            scheduler.set_rhythm(scheduler.rhythm.paced(saved), clock())
        call = self.settings.get("call", calls.DEFAULT)
        self._call = call if isinstance(call, str) and call in calls.CHOICES else calls.DEFAULT
        volume = calls.volume(self.settings.get("volume", calls.DEFAULT_VOLUME))
        self._volume = calls.DEFAULT_VOLUME if volume is None else volume
        # The model chosen in his menu wins over the config file's (`model`).
        self._config_model = model
        chosen = configs.find_model(str(self.settings.get("model", "")))
        self._model = chosen.model if chosen else ""
        theme = self.settings.get("theme", "")
        self._theme = theme if theme in THEMES else ""
        # Minimized: small in his corner, but while he asks (FULL_SIZE_MODES).
        self._small = self.settings.get("small") is True
        self._grown = False
        self._pending_question: dict[str, Any] | None = None  # shown once he has grown
        self._pointer_on_him = False
        self._stage = game.progress.grade
        self._spec = art.figure(self._stage)
        self._promotion: dict[str, int] = {}
        self._bubble: dict[str, Any] = {"mode": "hidden"}
        self._current: Question | None = None
        self._outcome: Outcome | None = None
        self._held = False
        self._refill_after = 0.0
        self._pending_course: tuple[blueprints.Blueprint, str] | None = None
        self._first_run = game.summary()["answered"] == 0
        # Study sheets (makeSheet): written this session, waiting or being written (the first),
        # what the brain and the page need for each, and word of one written while he was busy.
        self._sheets: dict[int, Path] = {}
        self._sheet_queue: list[int] = []
        self._sheet_requests: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
        self._sheet_news: dict[str, Any] | None = None
        self._last_sheet: Path | None = None
        self._failed_sheet: int | None = None
        # Catalogues: a course whose questions were pasted, until one learns it or not; the
        # last export, to show in its folder.
        self._pasted_course: blueprints.Blueprint | None = None
        self._last_export: Path | None = None
        animator.set_stage(self._stage)
        animator.tapped.connect(self._on_tapped)
        worker.batchReady.connect(self._on_batch)
        worker.batchFailed.connect(self._on_batch_failed)
        worker.explained.connect(self._on_explained)
        worker.explainFailed.connect(self._on_explain_failed)
        worker.planned.connect(self._on_planned)
        worker.planFailed.connect(self._on_plan_failed)
        worker.sheetWritten.connect(self._on_sheet_written)
        worker.sheetFailed.connect(self._on_sheet_failed)
        self._tick_timer = self._timer(self._tick, single=False)
        self._mood_timer = self._timer(lambda: self._set_mood("idle"))
        self._hide_timer = self._timer(self._auto_hide)
        self._unanswered_timer = self._timer(self._unanswered)
        self._swap_timer = self._timer(self._swap)
        self._reveal_timer = self._timer(self._reveal)
        self._grow_timer = self._timer(self._grown_ready)
        self._shrink_timer = self._timer(self._shrink)

    def _timer(self, slot: Callable[[], None], single: bool = True) -> QTimer:
        timer = QTimer(self)
        timer.setSingleShot(single)
        timer.timeout.connect(slot)
        return timer

    def start(self) -> None:
        self._tick_timer.start(TICK_MS)
        if not self._tell_updated() and self.game.store.fresh_count(self.game.exam) == 0:
            self._show(
                {
                    "mode": "message",
                    "title": "Hello!",
                    "text": "I'm writing my first questions: give me a few minutes. "
                    "Poke me meanwhile, if you like.",
                }
            )
        self._refill_if_needed()

    def _tell_updated(self) -> bool:
        """Back from an update (tagnan/ui/updater.py): what changed, once."""
        updated = self.settings.get(UPDATED_KEY)
        if not isinstance(updated, dict):
            return False
        self.settings.set(UPDATED_KEY, None)
        news = [str(line) for line in updated.get("news") or []][:4]
        text = "I'm up to date." + (
            " What's new:" + "".join(f"\n· {line}" for line in news) if news else ""
        )
        self._show(
            {"mode": "message", "title": "Freshly inked!", "text": text, "button": "Splendid!"}
        )
        self._hide_timer.start(UPDATED_SECONDS * 1000)
        return True

    @Slot(str, str)
    def say(self, title: str, text: str) -> None:
        """A word in his bubble from elsewhere (his updates), unless he is busy."""
        self._tell_if_free(title, text)

    # --- What QML reads ---------------------------------------------------------------------

    @Property(int, notify=stageChanged)
    def stage(self) -> int:
        return self._stage

    @Property(dict, notify=stageChanged)
    def spec(self) -> dict[str, Any]:
        return self._spec

    @Property(dict, notify=promotionChanged)
    def promotion(self) -> dict[str, int]:
        """His evolution under way: the grades it goes "from" and "to"; empty once he shows
        his new look."""
        return self._promotion

    @Property(dict, notify=bubbleChanged)
    def bubble(self) -> dict[str, Any]:
        return self._bubble

    @Property(bool, notify=statusChanged)
    def paused(self) -> bool:
        return self.scheduler.paused_until > self._clock()

    @Property(str, notify=prefsChanged)
    def pace(self) -> str:
        """The pace he asks at, or "" for gaps of one's own in the config file."""
        current = self.scheduler.rhythm.pace
        return current.key if current else ""

    @Property(str, notify=prefsChanged)
    def call(self) -> str:
        return self._call

    @Property(int, notify=prefsChanged)
    def volume(self) -> int:
        """His call's volume, in percent."""
        return self._volume

    @Property(str, notify=prefsChanged)
    def model(self) -> str:
        """The model that writes his questions: his menu's choice, else the config file's."""
        return self._model or self._config_model

    @Property(bool, notify=prefsChanged)
    def small(self) -> bool:
        """Minimized, as chosen in his menu."""
        return self._small

    @Property(bool, notify=sizeChanged)
    def tiny(self) -> bool:
        """Drawn small now: minimized, and not grown to ask."""
        return self._small and not self._grown

    @Property(str, notify=prefsChanged)
    def theme(self) -> str:
        """His colours: "dark" or "light" as chosen in his menu, "" for the system's."""
        return self._theme

    @Property(str, notify=prefsChanged)
    def subject(self) -> str:
        """What he asks about: the course, or the subject within it."""
        return self.game.topic()

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        p = self.game.progress
        return f"Tagnan · {rules.GRADES[p.grade].name} · {p.points} points · streak {p.streak}"

    # --- Ticks: ask when it is time ---------------------------------------------------------

    def _tick(self) -> None:
        now = self._clock()
        self._refill_if_needed()
        self.statusChanged.emit()
        if (
            self._bubble["mode"] not in ("hidden", "quip")
            or self._pending_question is not None
            or not self.scheduler.due(now)
        ):
            return
        if desktop.busy():
            self.scheduler.postpone(now, BUSY_RETRY_MINUTES)
            return
        if self._ask(now):
            self.sounds.play(self._call, self._volume)  # to be heard away from the screen

    def _ask(self, now: float) -> bool:
        question = self.game.next_question(now)
        if question is None:
            self._refill_if_needed(force=True)
            self.scheduler.postpone(now, NO_QUESTION_RETRY_MINUTES)
            return False
        self._current, self._outcome = question, None
        domain = self.game.blueprint.domain(question.domain)
        review = question.id is not None and self.game.store.review_box(question.id) is not None
        need = len(question.answers)
        meta = f"Domain {domain.id} · {domain.name}"
        if self.game.subject.text:
            meta = f"{self.game.subject.text} · Domain {domain.id}"
        if not self.game.blueprint.exam:  # a subject of one's own: its name says what it is
            meta = f"{self.game.blueprint.code} · {meta}"
        self._show_question(
            {
                "mode": "question",
                "title": self._rng.choice(ASKS),
                "meta": meta,
                "tag": "Review"
                if review
                else f"{DIFFICULTY.get(question.difficulty, '')} question",
                "stem": question.stem,
                "choices": [
                    {"letter": LETTERS[i], "text": c} for i, c in enumerate(question.choices)
                ],
                "need": need,
                "hint": "" if need == 1 else f"Choose {need}, then confirm.",
            }
        )
        self._set_mood("ask")
        self._unanswered_timer.start(UNANSWERED_MINUTES * 60_000)
        return True

    # --- What the bubble does ---------------------------------------------------------------

    @Slot("QVariantList")
    def answer(self, chosen: list[Any]) -> None:
        question = self._current
        if question is None or self._bubble["mode"] != "question":
            return
        now = self._clock()
        self._unanswered_timer.stop()
        outcome = self.game.answer(question, [int(c) for c in chosen], now)
        self._outcome = outcome
        self.scheduler.asked(now)
        self._set_mood(
            "happy" if outcome.correct else "angry",
            MOOD_SECONDS["happy" if outcome.correct else "angry"],
        )
        self._show(self._result(outcome))
        if outcome.promoted and not self.animator.reduced_motion():
            self._promote(self._stage, outcome.after.grade)
        elif outcome.after.grade != self._stage:
            self._set_stage(outcome.after.grade)
        if outcome.correct and not outcome.promoted:
            self._hide_timer.start(RESULT_SECONDS * 1000)
        self.statusChanged.emit()
        self._refill_if_needed()

    def _result(self, outcome: Outcome) -> dict[str, Any]:
        q = outcome.question
        after = outcome.after
        if outcome.correct:
            points = f"+{outcome.delta} points · {after.points} in all · streak of {after.streak}"
        elif outcome.delta:
            # A real minus sign, as the bubble prints it.
            points = f"\u2212{-outcome.delta} points · {after.points} in all · streak reset"
        else:
            points = f"{after.points} points · streak reset"
        if outcome.promoted:
            grade = rules.GRADES[after.grade]
            news = f"Promotion! Tagnan is now a {grade.name}: {grade.look}."
        elif outcome.demoted:
            news = f"Tagnan falls back to {rules.GRADES[after.grade].name}."
        elif outcome.review_box and not outcome.correct:
            news = f"This question will come back {REVIEW_WHEN[outcome.review_box]}."
        else:
            news = ""
        return {
            "mode": "result",
            "correct": outcome.correct,
            "title": self._rng.choice(CHEERS if outcome.correct else SCOLDS),
            "chosen": [
                {"letter": LETTERS[i], "text": q.choices[i], "why": q.why_wrong[i]}
                for i in outcome.chosen
                if not outcome.correct and q.why_wrong[i]
            ],
            "right": " · ".join(f"{LETTERS[i]}. {q.choices[i]}" for i in q.answers),
            "explanation": q.explanation,
            "reference": q.reference,
            "points": points,
            "news": news,
            "promoted": outcome.promoted,
            "rank": rules.GRADES[after.grade].name if outcome.promoted else "",
            "sheet": self._sheet_state(q.id),
        }

    @Slot()
    def later(self) -> None:
        if self._bubble["mode"] == "question":
            self.scheduler.snooze(self._clock())
        self._close()

    @Slot()
    def flag(self) -> None:
        """A wrong or badly worded question: never again, and no points either way."""
        question = self._current
        if question is None or question.id is None:
            return
        self.game.store.flag(question.id)
        logger.info("question %s flagged", question.id)
        self.scheduler.asked(self._clock())
        self._current = None
        self._set_mood("idle")
        self._show(
            {
                "mode": "message",
                "title": "Question set aside",
                "text": "Thank you, I won't ask it again. My brain will write others.",
            }
        )
        self._hide_timer.start(6000)

    @Slot()
    def dismiss(self) -> None:
        self._close()

    @Slot()
    def explainMore(self) -> None:
        outcome = self._outcome
        if outcome is None or outcome.question.id is None:
            return
        self._hide_timer.stop()
        self._show({**self._bubble, "mode": "thinking"})
        self.worker.explain(
            outcome.question.id, self.game.explain_request(outcome.question, outcome.chosen)
        )

    @Slot()
    def askNow(self) -> None:
        if self._bubble["mode"] in ("question", "thinking") or self._pending_question is not None:
            return
        if not self._ask(self._clock()):
            self._show(
                {
                    "mode": "message",
                    "title": "Not yet",
                    "text": "My brain is writing questions on "
                    f"{self.subject}. Come back in a few minutes.",
                }
            )
            self._hide_timer.start(6000)

    @Slot()
    def showStats(self) -> None:
        s = self.game.summary()
        low = self.game.blueprint.domains
        band_start = rules.GRADES[s["grade"]].threshold
        band_end = s["next_threshold"]
        share = (
            1.0 if band_end is None else (s["points"] - band_start) / max(1, band_end - band_start)
        )
        now = self._clock()
        if self.scheduler.paused_until > now:
            when = f"On a break until {pauses.clock(self.scheduler.paused_until, now)}."
        else:
            when = f"Next question around {pauses.clock(self.scheduler.next_at, now)}."
        self._show(
            {
                "mode": "stats",
                "title": rules.GRADES[s["grade"]].name,
                "points": s["points"],
                "next": f"{band_end} for {s['next_name']}"
                if band_end is not None
                else "the highest grade",
                "share": max(0.0, min(1.0, share)),
                "streak": f"Streak: {s['streak']} · best {s['best_streak']}",
                "answers": f"{s['right']} right answers out of {s['answered']}",
                "domains": [
                    {
                        "name": f"{d['id']}. {low[i].name}",
                        "rate": d["right"] / d["answered"] if d["answered"] else -1.0,
                        "count": f"{d['right']}/{d['answered']}",
                    }
                    for i, d in enumerate(s["domains"])
                ],
                "bank": f"{s['topic']}: {s['fresh']} new questions in store, "
                f"{s['reviews']} to review in all. {when}",
            }
        )

    @Slot()
    def showPause(self) -> None:
        """The pause bubble: quick choices, or a while or a time in his own words."""
        now = self._clock()
        paused = self.scheduler.paused_until > now
        self._show(
            {
                "mode": "pause",
                "title": "A break?",
                "choices": [
                    {"label": "30 min", "text": "30 min"},
                    {"label": "1 hour", "text": "1h"},
                    {"label": "2 hours", "text": "2h"},
                    {"label": "Until tomorrow", "text": "tomorrow"},
                ],
                "status": f"On a break until {pauses.clock(self.scheduler.paused_until, now)}."
                if paused
                else "",
            }
        )

    @Slot(str, result=dict)
    def previewPause(self, text: str) -> dict[str, Any]:
        """What the pause typed so far would be, said before it is confirmed."""
        if not text.strip():
            return {"ok": False, "text": ""}
        now = self._clock()
        understood = pauses.parse(text, now, self.scheduler.rhythm.start_hour)
        if understood is None:
            return {"ok": False, "text": "I don't follow. Try 1h30, 45 min, 4:45pm or noon."}
        return {"ok": True, "text": pauses.describe(understood, now) + "."}

    @Slot(str, result=bool)
    def pauseWith(self, text: str) -> bool:
        now = self._clock()
        understood = pauses.parse(text, now, self.scheduler.rhythm.start_hour)
        if understood is None:
            return False
        self.scheduler.pause_until(understood.until)
        self._current = None
        self._set_mood("idle")
        self._show(
            {
                "mode": "message",
                "title": "At ease!",
                "text": pauses.describe(understood, now) + ". Not a word from me till then.",
            }
        )
        self._hide_timer.start(5000)
        self.statusChanged.emit()
        return True

    @Slot()
    def showSubject(self) -> None:
        self._show_subject()

    def _show_subject(self, put_away: blueprints.Blueprint | None = None) -> None:
        """The subject bubble: what we learn (a course learned before, or anything in one's own
        words), then what within it (all of it, a domain, a subject chosen before, or one's own
        words). put_away: the course just put away, said with a way back."""
        bp = self.game.blueprint
        whole = bp.whole
        choices = [{"label": whole[0].upper() + whole[1:], "key": ""}]
        choices += [{"label": f"{d.id}. {d.name}", "key": f"domain:{d.id}"} for d in bp.domains]
        choices += [{"label": text, "key": text} for text in self.game.store.subjects(bp.key)]
        planning = self.worker.planning
        self._show(
            {
                "mode": "subject",
                "title": "What shall we work on?",
                "courses": [
                    {"label": c.name, "key": c.key, "removable": c.key != bp.key}
                    for c in self.game.courses()
                ],
                "course": bp.key,
                "putAway": {}
                if put_away is None
                else {
                    "key": put_away.key,
                    "text": f"{put_away.name} put away. Learn it again and it comes back,"
                    " progress and all.",
                },
                "within": f"Within {bp.name}:",
                "choices": choices,
                "current": self.game.subject.key,
                "status": f"Now: {self.subject}."
                + (f" I'm drawing up a course on {planning}." if planning else ""),
            }
        )

    @Slot(str, result=dict)
    def previewCourse(self, text: str) -> dict[str, Any]:
        """What the course typed so far would be, said before it is confirmed."""
        said = " ".join(text.split())
        if not said:
            return {"ok": False, "text": ""}
        known = self.game.find_course(said)
        if known is not None:
            return {"ok": True, "text": f"Back to {known.name}."}
        if len(said) > MAX_COURSE_WORDS:
            return {"ok": False, "text": f"Shorter, please: {MAX_COURSE_WORDS} characters at most."}
        return {"ok": True, "text": "I'll draw up a course on it: a minute or two."}

    @Slot(str, result=bool)
    def learnWith(self, text: str) -> bool:
        """Learn something else: a course learned before at once, anything else once the brain
        has drawn up its course."""
        said = " ".join(text.split()).strip(" .!?")
        if not self.previewCourse(said)["ok"]:
            return False
        known = self.game.find_course(said)
        if known is not None:
            self._change_course(known)
            return True
        if self.worker.planning:
            title = "One at a time!"
            line = f"I'm still drawing up a course on {self.worker.planning}."
        else:
            self.worker.plan(said)
            logger.info("course asked for: %r", said)
            title = "Let me think…"
            line = (
                f"A course on {said}: I'm drawing up its chapters, give me a minute or two."
                " I'll tell you when it's ready."
            )
        self._set_mood("idle")
        self._show({"mode": "message", "title": title, "text": line})
        self._hide_timer.start(8000)
        return True

    @Slot(str)
    def setCourse(self, key: str) -> None:
        """A course learned before: its key, as showSubject gives it."""
        try:
            self._change_course(self.game.course(key))
        except (KeyError, ValueError):
            logger.warning("unknown course: %r", key)

    @Slot(str)
    def putAwayCourse(self, key: str) -> None:
        """No longer offer a course learned before (its key, as showSubject gives it); its
        questions and progress are kept."""
        try:
            self.game.put_away(key)
        except (KeyError, ValueError):
            logger.warning("cannot put away course: %r", key)
            return
        logger.info("course put away: %r", key)
        self._show_subject(put_away=self.game.course(key))

    @Slot(str)
    def bringBackCourse(self, key: str) -> None:
        """Undo putAwayCourse."""
        self.game.bring_back(key)
        self._show_subject()

    def _change_course(self, bp: blueprints.Blueprint, intro: str = "") -> None:
        if bp.key == self.game.exam:
            text = f"We're already on {bp.name}. I'll keep to it."
        else:
            self.game.set_course(bp)
            logger.info("course: %r", bp.key)
            self._current = None
            self._end_promotion()
            self._set_stage(self.game.progress.grade)  # each course has its own grade
            self.prefsChanged.emit()
            self.statusChanged.emit()
            grade = rules.GRADES[self.game.progress.grade].name
            text = intro or f"From now on, we learn {bp.name}."
            text += f" Here I'm {grade}."
            if not self.game.fresh_count():
                text += " Give me a few minutes to write the questions."
            self._refill_if_needed(force=True)
        self._set_mood("idle")
        self._show({"mode": "message", "title": "As you wish!", "text": text})
        self._hide_timer.start(9000)

    @Slot(str, result=dict)
    def previewSubject(self, text: str) -> dict[str, Any]:
        """What the subject typed so far would be, said before it is confirmed."""
        if not text.strip():
            return {"ok": False, "text": ""}
        try:
            understood = subjects.parse(text, self.game.blueprint)
        except ValueError as error:
            return {"ok": False, "text": str(error)}
        return {"ok": True, "text": f"Questions on {understood.name(self.game.blueprint)}."}

    @Slot(str, result=bool)
    def subjectWith(self, text: str) -> bool:
        try:
            understood = subjects.parse(text, self.game.blueprint)
        except ValueError:
            return False
        self._change_subject(understood)
        return True

    @Slot(str)
    def setSubject(self, key: str) -> None:
        """A quick choice: its key, as showSubject gives it."""
        self._change_subject(subjects.from_key(key))

    def _change_subject(self, chosen: subjects.Subject) -> None:
        name = chosen.name(self.game.blueprint)
        if chosen.key.casefold() == self.game.subject.key.casefold():
            text = f"We're already on {self.subject}. I'll keep to it."
        else:
            self.game.set_subject(chosen)
            logger.info("subject: %r", chosen.key)
            self.prefsChanged.emit()
            self.statusChanged.emit()
            if self.game.fresh_count():
                text = f"From now on, I ask about {name}, until you tell me otherwise."
            else:
                text = (
                    f"From now on, I ask about {name}. Give me a few minutes to write the"
                    " questions."
                )
            self._refill_if_needed(force=True)
        self._set_mood("idle")
        self._show({"mode": "message", "title": "As you wish!", "text": text})
        self._hide_timer.start(7000)

    @Slot(str)
    def setPace(self, key: str) -> None:
        chosen = find_pace(key)
        if chosen is None:
            return
        now = self._clock()
        self.scheduler.set_rhythm(self.scheduler.rhythm.paced(chosen), now)
        self.settings.set("pace", chosen.key)
        logger.info("pace: %s", chosen.key)
        self.prefsChanged.emit()
        self.statusChanged.emit()
        if self._bubble["mode"] in ("question", "thinking"):
            return  # not a word over a question: his menu shows the pace
        if self.scheduler.paused_until > now:
            text = f"{chosen.sentence}, once your break is over."
        else:
            text = (
                f"{chosen.sentence}. The next one around "
                f"{pauses.clock(self.scheduler.next_at, now)}."
            )
        self._show({"mode": "message", "title": "As you wish!", "text": text})
        self._hide_timer.start(6000)

    @Slot(int, int)
    def setHours(self, start: int, end: int) -> None:
        """From when until when he may ask, on the same days."""
        self._change_hours(start, end, self.scheduler.rhythm.weekends)

    @Slot(bool)
    def setWeekends(self, weekends: bool) -> None:
        rhythm = self.scheduler.rhythm
        self._change_hours(rhythm.start_hour, rhythm.end_hour, weekends)

    def _change_hours(self, start: int, end: int, weekends: bool) -> None:
        rhythm = self.scheduler.rhythm
        if (start, end, weekends) == (rhythm.start_hour, rhythm.end_hour, rhythm.weekends):
            return
        try:
            changed = rhythm.at_hours(start, end, weekends)
        except ValueError:
            return
        now = self._clock()
        self.scheduler.set_rhythm(changed, now)
        self.settings.set("hours", changed.hours)
        logger.info("hours: %s", changed.hours_hint)
        self.prefsChanged.emit()
        self.statusChanged.emit()
        if self._bubble["mode"] in ("question", "thinking"):
            return  # not a word over a question: his menu shows the hours
        next_at = self.scheduler.next_at
        if self.scheduler.paused_until > now:
            text = f"{changed.hours_sentence}, once your break is over."
        elif datetime.fromtimestamp(next_at).date() == datetime.fromtimestamp(now).date():
            text = f"{changed.hours_sentence}. The next one around {pauses.clock(next_at, now)}."
        else:
            text = (
                f"{changed.hours_sentence}. Not a word more today: the next one"
                f" {pauses.clock(next_at, now)}."
            )
        self._show({"mode": "message", "title": "As you wish!", "text": text})
        self._hide_timer.start(6000)

    @Slot(str)
    def setCall(self, key: str) -> None:
        """His call, played at once: one chooses it by ear."""
        if key not in calls.CHOICES:
            return
        self._call = key
        self.settings.set("call", key)
        logger.info("call: %s", key)
        self.prefsChanged.emit()
        self.sounds.play(key, self._volume)

    @Slot(int)
    def setVolume(self, percent: int) -> None:
        """His call's volume, his call played at once at it: one sets it by ear."""
        chosen = calls.volume(percent)
        if chosen is None:
            return
        self._volume = chosen
        self.settings.set("volume", chosen)
        logger.info("volume: %s", chosen)
        self.prefsChanged.emit()
        self.sounds.play(self._call, chosen)

    @Slot(str)
    def setModel(self, key: str) -> None:
        """The model that writes his next questions; those already written stay."""
        chosen = configs.find_model(key)
        if chosen is None or chosen.model == (self._model or self._config_model):
            return
        self._model = chosen.model
        self.settings.set("model", chosen.model)
        logger.info("model: %s", chosen.model)
        self.prefsChanged.emit()
        if self._bubble["mode"] in BUSY_MODES:
            return  # not a word over a question: his menu shows the model
        text = (
            f"{chosen.name} writes my next questions: {chosen.hint}."
            " The ones I already hold stay as they are."
        )
        self._show({"mode": "message", "title": f"{chosen.name.split()[0]} it is!", "text": text})
        self._hide_timer.start(7000)

    @Slot(str)
    def setTheme(self, key: str) -> None:
        if key not in THEMES or key == self._theme:
            return
        self._theme = key
        self.settings.set("theme", key)
        logger.info("theme: %s", key)
        self.prefsChanged.emit()

    @Slot(int)
    def pause(self, minutes: int) -> None:
        self.pauseWith(f"{minutes} min")

    @Slot()
    def pauseUntilTomorrow(self) -> None:
        self.pauseWith("tomorrow")

    @Slot()
    def resume(self) -> None:
        self.scheduler.resume(self._clock())
        self.statusChanged.emit()
        if self._bubble["mode"] == "pause":
            self._close()

    def closes_on_outside(self) -> bool:
        """Every bubble but a question closes when one clicks elsewhere: a question stays until
        it is answered or put off, lest a click in another window lose it."""
        return self._bubble["mode"] not in ("hidden", "question")

    @Slot(bool)
    def hold(self, held: bool) -> None:
        """The pointer is over the bubble: it does not close by itself meanwhile."""
        self._held = held
        if not held and self._hide_timer.isActive() is False and self._bubble["mode"] == "message":
            self._hide_timer.start(4000)

    @Slot()
    def showMenu(self) -> None:
        at = QCursor.pos()
        self.menuRequested.emit(at.x(), at.y())

    @Slot()
    def quit(self) -> None:
        self.quitRequested.emit()

    # --- Study sheets -----------------------------------------------------------------------

    def inking(self) -> bool:
        """A study sheet is being written (his menu's busy row)."""
        return bool(self._sheet_queue)

    def _sheet_state(self, question_id: int | None) -> str:
        """A question's study sheet: "ready" to be asked for, "inking", "done"; "" for none."""
        if question_id is None:
            return ""
        if question_id in self._sheets:
            return "done"
        return "inking" if question_id in self._sheet_queue else "ready"

    def _showing(self, question_id: int) -> bool:
        """His bubble is the verdict (or its explanation) of that question."""
        outcome = self._outcome
        return (
            outcome is not None
            and outcome.question.id == question_id
            and self._bubble["mode"] in VERDICT_MODES
        )

    def _refresh_sheet(self, question_id: int, **changes: Any) -> None:
        """The open verdict says where its sheet stands, without closing sooner or later."""
        if self._showing(question_id) and "sheet" in self._bubble:
            self._bubble = {**self._bubble, **changes, "sheet": self._sheet_state(question_id)}
            self.bubbleChanged.emit()

    def _sheet_meta(self, question: Question) -> dict[str, Any]:
        """What the page says besides the brain's words: the course, where in it, what to read
        again, the date, his grade (his figure on the page)."""
        bp = self.game.blueprint
        domain = bp.domain(question.domain)
        today = datetime.fromtimestamp(self._clock())
        return {
            "course": bp.name,
            "where": f"Domain {domain.id}" if bp.exam else domain.name,
            "source": question.reference,
            "date": f"{today.day} {today:%B %Y}",
            "stage": self._stage,
        }

    @Slot()
    def makeSheet(self) -> None:
        """A study sheet on the notion behind the question just answered: its words by the brain,
        its page drawn here, the file in Downloads. The bubble may close meanwhile; a second
        sheet waits for the first."""
        outcome = self._outcome
        if outcome is None or outcome.question.id is None:
            return
        question = outcome.question
        question_id = outcome.question.id
        if question_id in self._sheets:
            self.openSheet()
            return
        if question_id in self._sheet_queue:
            return
        self._sheet_requests[question_id] = (
            self.game.sheet_request(question),
            self._sheet_meta(question),
        )
        self._sheet_queue.append(question_id)
        logger.info("study sheet asked for: question %s", question_id)
        self._refresh_sheet(question_id)
        self._next_sheet()

    def _next_sheet(self) -> None:
        if self._sheet_queue and not self.worker.sheeting:
            question_id = self._sheet_queue[0]
            self.worker.sheet(question_id, self._sheet_requests[question_id][0])
        self.statusChanged.emit()  # his menu's busy row

    def _on_sheet_written(self, question_id: int, answer: object) -> None:
        if question_id in self._sheet_queue:
            self._sheet_queue.remove(question_id)
        asked = self._sheet_requests.get(question_id)
        try:
            if asked is None or not isinstance(answer, dict):
                raise ValueError("nothing to draw")
            path = self.sheet_files.write(answer, asked[1])
        except (OSError, ValueError, KeyError, TypeError) as error:
            logger.warning("study sheet not drawn: %s", error)
            self._sheet_failed(question_id, f"I could not draw it ({error})")
        else:
            self._sheet_requests.pop(question_id, None)
            self._sheets[question_id] = self._last_sheet = path
            if self._showing(question_id):
                self._refresh_sheet(question_id)
            else:
                self._tell_sheet(sheet_written(path))
        self._next_sheet()

    def _on_sheet_failed(self, question_id: int, error: str) -> None:
        if question_id in self._sheet_queue:
            self._sheet_queue.remove(question_id)
        self._sheet_failed(question_id, error)
        self._next_sheet()

    def _sheet_failed(self, question_id: int, error: str) -> None:
        """Said in the verdict still open, else in a word of his with Try again."""
        self._failed_sheet = question_id
        if self._showing(question_id):
            self._refresh_sheet(question_id, news=f"No sheet this time: {error}.")
            return
        self._tell_sheet(
            {
                "mode": "message",
                "title": "My quill broke",
                "text": f"I couldn't ink the sheet: {error}. Shall I try again?",
                "buttons": [
                    {"label": "Try again", "action": "retrysheet", "primary": True},
                    {"label": "Not now", "action": "dismiss"},
                ],
            }
        )

    def _tell_sheet(self, news: dict[str, Any]) -> None:
        """At once if his bubble is free, else once it closes: never over a question, a verdict,
        a break or the subject being chosen."""
        if self._bubble["mode"] in ("hidden", "quip", "message", "stats"):
            self._show(news)
            if news.get("file"):
                self._hide_timer.start(SHEET_NEWS_SECONDS * 1000)
        else:
            self._sheet_news = news

    @Slot()
    def openSheet(self) -> None:
        """The open verdict's sheet, else the last one written, in the system's PDF reader."""
        outcome = self._outcome
        path = self._sheets.get(outcome.question.id or -1) if outcome else None
        path = path or self._last_sheet
        if path is not None:
            self.sheet_files.open(path)

    @Slot(str)
    def bubbleAction(self, action: str) -> None:
        """A button of one of his words: opensheet, showfolder, retrysheet; ask, paste, import,
        prompt:write or prompt:convert, learnpasted, showexport; dismiss."""
        last = self._last_sheet
        self._close()
        if action == "opensheet" and last is not None:
            self.sheet_files.open(last)
        elif action == "showfolder" and last is not None:
            self.sheet_files.show(last)
        elif action == "ask":
            self.askNow()
        elif action == "paste":
            self.pasteQuestions()
        elif action == "import":
            self.importCatalogue()
        elif action.startswith("prompt:"):
            self.copyPrompt(action.removeprefix("prompt:"))
        elif action == "learnpasted" and self._pasted_course is not None:
            course, self._pasted_course = self._pasted_course, None
            self._change_course(course)
        elif action == "showexport" and self._last_export is not None:
            self.catalogue_files.show(self._last_export)
        elif action == "retrysheet":
            question_id = self._failed_sheet
            if (
                question_id is not None
                and question_id in self._sheet_requests
                and question_id not in self._sheet_queue
            ):
                self._sheet_queue.append(question_id)
                self._next_sheet()

    # --- Catalogues --------------------------------------------------------------------------

    @Slot()
    def pasteQuestions(self) -> None:
        """Questions from the clipboard: one's assistant's answer, as copied."""
        self._take_catalogue(self.catalogue_files.text(), pasted=True)

    @Slot()
    def importCatalogue(self) -> None:
        """Questions from a file, chosen in the system's Open dialog: a catalogue a colleague
        exported, or an assistant's answer saved."""
        path = self.catalogue_files.choose()
        if path is None:
            return
        try:
            text = self.catalogue_files.read(path)
        except (OSError, ValueError) as error:
            self._say_catalogue("Nothing to read", f"I couldn't read {path.name}: {error}.")
            return
        self._take_catalogue(text, pasted=False)

    def _take_catalogue(self, text: str, pasted: bool) -> None:
        """Its questions, checked and kept in their course: one he knows, or the one it brings,
        kept then but learned only if one says so."""
        try:
            found = catalogue.read(text)
        except ValueError as error:
            where = "Your clipboard" if pasted else "This file"
            if str(error) == "I find no questions in it":
                line = f"{where} holds no questions I can read."
                if pasted:
                    line += (
                        " Copy your assistant's whole answer: the Copy button of its code block"
                        " takes it all."
                    )
            else:
                line = f"{where} holds no questions I can use: {error}."
            self._say_catalogue("Nothing to read", line)
            return
        new = False
        if isinstance(found.course, str):
            try:
                bp = self.game.course(found.course)
            except (KeyError, ValueError):
                self._say_catalogue(
                    "A course I don't know",
                    f"These questions are for {found.course}, a course I don't have: a catalogue"
                    " that brings its course along will do.",
                )
                return
        else:
            try:
                bp = self.game.course(found.course.key)  # one he has: his own, as it is
            except (KeyError, ValueError):
                bp, new = found.course, True
        added = self.game.add_questions(
            bp, found.questions, self._clock(), found.origin, found.subject
        )
        logger.info(
            "catalogue on %r: %d kept, %d known, %d set aside %s%s",
            bp.key,
            len(added.ids),
            added.known,
            len(added.rejected),
            added.rejected[:3],
            ", cut" if found.cut else "",
        )
        current = bp.key == self.game.exam
        if added.ids:
            if new:
                self.game.keep_course(bp)
            if current and self._first_run:
                self._first_run = False
                self.scheduler.next_at = self._clock() + FIRST_QUESTION_DELAY
            self._set_mood("happy", MOOD_SECONDS["happy"])
        self._pasted_course = bp if added.ids and not current else None
        self.prefsChanged.emit()  # his menu: the course's questions to share
        self.statusChanged.emit()
        self._show(self._catalogue_news(bp, found, added, new))
        self._hide_timer.start(CATALOGUE_NEWS_SECONDS * 1000)

    def _catalogue_news(
        self, bp: blueprints.Blueprint, found: catalogue.Catalogue, added: Added, new: bool
    ) -> dict[str, Any]:
        """What became of a catalogue's questions, said plainly."""
        kept, known, aside = len(added.ids), added.known, added.rejected
        current = bp.key == self.game.exam
        lines = []
        if new and kept:
            title = "A new course!"
            lines.append(
                f"{bp.name}: {counted(len(bp.domains), 'chapter')}, {counted(kept, 'question')}."
            )
        elif kept:
            title = "Cut short!" if found.cut else "Fresh ink, mostly" if aside else "Fresh ink!"
            said = f"{counted(kept, 'new question')} on {bp.name}"
            if found.origin == CONVERTED:
                said += ", converted from your quiz: they stay with you, never exported"
            lines.append(said + ".")
        elif aside:
            title = "Set aside"
            lines.append(f"None of these questions holds up for {bp.name}.")
        else:
            title = "Nothing new"
            lines.append(f"I already had {'it' if known == 1 else f'all {known}'}, in {bp.name}.")
        if known and kept:
            lines.append(f"{known} I already had.")
        if aside:
            reasons = "; ".join(f"question {n}: {catalogue.reason(why)}" for n, why in aside[:3])
            more = f"; and {len(aside) - 3} more" if len(aside) > 3 else ""
            lines.append(f"{len(aside)} set aside: {reasons}{more}.")
        if found.left_out:
            left = "; ".join(
                f"question {n}, {why}" if why else f"question {n}" for n, why in found.left_out[:3]
            )
            lines.append(f"Your assistant left {len(found.left_out)} out: {left}.")
        if found.cut and kept:
            lines.append(
                "Your assistant's answer breaks off: I kept the whole questions before the"
                " break. For the rest, tell it “next”, then paste its answer again."
            )
        if kept and not current:
            lines.append(
                "Shall we learn it now?"
                if new
                else f"They wait in {bp.name}: shall we learn it now?"
            )
            buttons = [
                {"label": "Learn it now", "action": "learnpasted", "primary": True},
                {"label": "Later", "action": "dismiss"},
            ]
        elif kept:
            buttons = [
                {"label": "A question now", "action": "ask", "primary": True},
                {"label": "Got it", "action": "dismiss"},
            ]
        else:
            buttons = [{"label": "Got it", "action": "dismiss", "primary": True}]
        return {"mode": "message", "title": title, "text": " ".join(lines), "buttons": buttons}

    @Slot(str)
    def copyPrompt(self, kind: str) -> None:
        """A prompt for one's own assistant, in the clipboard: to write questions on what he
        asks about now ("write"), or to convert a quiz one has ("convert")."""
        bp = self.game.blueprint
        if kind == "convert":
            prompt = catalogue.convert_prompt(bp)
            text = (
                "The prompt is in your clipboard. Paste it into your assistant, then your quiz:"
                " its text, or the file if it takes files. Twenty questions at a time: “next”"
                " for the rest."
            )
            if bp.exam:
                text += "\nOnly a quiz you may use: never real exam questions."
        else:
            prompt = catalogue.write_prompt(bp, self.game.batch_request(catalogue.BATCH))
            text = (
                "The prompt is in your clipboard. Paste it into ChatGPT, Gemini or Copilot, then"
                " copy its whole answer and bring it to me: Paste questions."
            )
        self.catalogue_files.copy(prompt)
        logger.info("prompt copied: %s", kind)
        self._show_catalogue_prompt(text)

    def _show_catalogue_prompt(self, text: str) -> None:
        self._set_mood("idle")
        self._show(
            {
                "mode": "message",
                "title": "Over to your assistant!",
                "text": text,
                "buttons": [
                    {"label": "Paste questions", "action": "paste", "primary": True},
                    {"label": "Got it", "action": "dismiss"},
                ],
            }
        )
        self._hide_timer.start(CATALOGUE_NEWS_SECONDS * 1000)

    @Slot()
    def exportQuestions(self) -> None:
        """The course learned now and the questions one may share, as a catalogue in Downloads:
        a colleague imports both. Those converted from a quiz stay with one."""
        bp = self.game.blueprint
        shared = self.game.store.shareable(bp.key)
        converted = self.game.store.count(bp.key, CONVERTED)
        stay = (
            ""
            if not converted
            else " The one converted from your quiz stays with you."
            if converted == 1
            else f" The {converted} converted from your quizzes stay with you."
        )
        if not shared:
            self._say_catalogue(
                "Nothing to share yet", f"I hold no questions of my own on {bp.name} yet.{stay}"
            )
            return
        try:
            path = self.catalogue_files.write(
                catalogue.export(bp, shared), catalogue.file_name(bp, len(shared))
            )
        except OSError as error:
            logger.warning("catalogue not written: %s", error)
            self._say_catalogue("My quill broke", f"I couldn't write the catalogue: {error}.")
            return
        logger.info("catalogue exported: %s", path)
        self._last_export = path
        self._set_mood("idle")
        self._show(
            {
                "mode": "message",
                "title": "Signed and sealed!",
                "text": f"{counted(len(shared), 'question')} on {bp.name}, in Downloads, ready"
                f" to share.{stay}",
                "file": path.name,
                "buttons": [
                    {"label": "Show in folder", "action": "showexport", "primary": True},
                    {"label": "Got it", "action": "dismiss"},
                ],
            }
        )
        self._hide_timer.start(CATALOGUE_NEWS_SECONDS * 1000)

    def _say_catalogue(self, title: str, text: str) -> None:
        self._set_mood("idle")
        self._show({"mode": "message", "title": title, "text": text})
        self._hide_timer.start(CATALOGUE_NEWS_SECONDS * 1000)

    # --- Brain ------------------------------------------------------------------------------

    def _refill_if_needed(self, force: bool = False) -> None:
        now = self._clock()
        if self.worker.generating or (not force and now < self._refill_after):
            return
        if self.game.needs_questions():
            logger.info("asking the brain for a batch")
            request = self.game.batch_request()
            if self._model:
                request["model"] = self._model
            self.worker.generate(request)

    def _on_batch(self, answer: object) -> None:
        questions = answer.get("questions", []) if isinstance(answer, dict) else []
        subject = str(answer.get("subject") or "") if isinstance(answer, dict) else ""
        course = str(answer.get("course") or "") if isinstance(answer, dict) else ""
        ids, rejected = self.game.add_batch(questions, self._clock(), subject, course)
        logger.info(
            "batch on %r: %d kept, %d dropped %s", subject, len(ids), len(rejected), rejected[:3]
        )
        if self._first_run and ids:
            self._first_run = False
            self.scheduler.next_at = self._clock() + FIRST_QUESTION_DELAY
            if self._bubble["mode"] == "message":
                self._show(
                    {
                        "mode": "message",
                        "title": "Ready!",
                        "text": "My questions are written. En garde, the first one is coming.",
                    }
                )
                self._hide_timer.start(8000)
        self._refill_if_needed()  # written for a subject left meanwhile: one for the new one

    def _on_batch_failed(self, error: str) -> None:
        self._refill_after = self._clock() + REFILL_BACKOFF
        if self.game.fresh_count() == 0 and self._bubble["mode"] in (
            "hidden",
            "message",
        ):
            self._show(
                {
                    "mode": "message",
                    "title": "My brain stalls",
                    "text": f"I couldn't write questions: {error}. I'll try again in ten minutes.",
                }
            )

    def _on_planned(self, words: str, answer: object) -> None:
        data = answer if isinstance(answer, dict) else {}
        try:
            if not data.get("understood"):
                raise ValueError(str(data.get("message") or "I don't know how to teach that."))
            bp = blueprints.from_dict(data.get("course") or {}, where="course")
        except ValueError as error:
            self._tell_if_free("Hmm…", f"A course on {words}? {error}")
            return
        chapters = "; ".join(f"{d.id}. {d.name}" for d in bp.domains)
        intro = f"Your course is ready: {bp.name}. {chapters}."
        if self._bubble["mode"] in BUSY_MODES:
            self._pending_course = (bp, intro)  # not over a question or a verdict
            return
        self._change_course(bp, intro)

    def _on_plan_failed(self, words: str, error: str) -> None:
        self._tell_if_free("My brain stalls", f"I couldn't draw up a course on {words}: {error}.")

    def _tell_if_free(self, title: str, text: str) -> None:
        if self._bubble["mode"] in ("hidden", "message", "quip", "subject", "stats"):
            self._set_mood("idle")
            self._show({"mode": "message", "title": title, "text": text})
            self._hide_timer.start(9000)

    def _on_explained(self, question_id: int, text: str) -> None:
        if (
            self._bubble["mode"] == "thinking"
            and self._outcome
            and self._outcome.question.id == question_id
        ):
            self._show(
                {
                    "mode": "explanation",
                    "title": "Listen well",
                    "text": text,
                    "sheet": self._sheet_state(question_id),
                }
            )

    def _on_explain_failed(self, question_id: int, error: str) -> None:
        if self._bubble["mode"] == "thinking":
            self._show({**self._bubble, "mode": "result", "news": f"No more explanation: {error}"})

    # --- Figure -----------------------------------------------------------------------------

    def _on_tapped(self, mood: str) -> None:
        if self._bubble["mode"] in ("hidden", "quip"):
            now = self._clock()
            if self.scheduler.paused_until > now and mood == "wink":
                line = f"On a break until {pauses.clock(self.scheduler.paused_until, now)}."
            else:
                line = self._rng.choice(QUIPS.get(mood, ("Hey!",)))
            self._show({"mode": "quip", "text": line})
            self._hide_timer.start(round(QUIP_SECONDS * 1000))

    def _set_mood(self, mood: str, seconds: float = 0.0) -> None:
        self.animator.set_mood(mood)
        if seconds:
            self._mood_timer.start(round(seconds * 1000))
        else:
            self._mood_timer.stop()

    def _set_stage(self, stage: int) -> None:
        self._stage = stage
        self._spec = art.figure(stage)
        self.animator.set_stage(stage)
        self.stageChanged.emit()

    def _promote(self, before: int, after: int) -> None:
        """His evolution, as in the games: Tagnan.qml plays it, he changes under cover."""
        self._promotion = {"from": before, "to": after}
        self.promotionChanged.emit()
        self._swap_timer.start(PROMOTION_SWAP_MS)
        self._reveal_timer.start(PROMOTION_REVEAL_MS)

    def _swap(self) -> None:
        if self._promotion and self._stage != self._promotion["to"]:
            self._set_stage(self._promotion["to"])

    def _reveal(self) -> None:
        self._end_promotion()
        self._set_mood("happy", MOOD_SECONDS["happy"])

    def _end_promotion(self) -> None:
        self._swap_timer.stop()
        self._reveal_timer.stop()
        if self._promotion:
            self._swap()
            self._promotion = {}
            self.promotionChanged.emit()

    # --- Minimized ----------------------------------------------------------------------------

    @Slot(bool)
    def setSmall(self, on: bool) -> None:
        """Minimized or not, kept as his theme is."""
        if on == self._small:
            return
        self._small = on
        self.settings.set("small", on)
        logger.info("small: %s", on)
        self._grown = on and self._bubble["mode"] in FULL_SIZE_MODES
        self._shrink_timer.stop()
        self.prefsChanged.emit()
        self.sizeChanged.emit()

    @Slot(bool)
    def pointerOnHim(self, on: bool) -> None:
        """The pointer on his figure: he waits before shrinking, lest he slip from under it."""
        self._pointer_on_him = on

    def _show_question(self, content: dict[str, Any]) -> None:
        """Minimized, he grows first; the question shows once he has (Main.qml)."""
        if self.property("tiny"):
            self._grown = True
            self.sizeChanged.emit()
            self._pending_question = content
            self._grow_timer.start(GROW_MS)
            return
        self._show(content)

    def _grown_ready(self) -> None:
        content, self._pending_question = self._pending_question, None
        if content is not None:
            self._show(content)

    def _fit_size(self) -> None:
        """Grown, he keeps his size while a question, its verdict or Tell me more is open; the
        last closed, he waits a little, then goes back to his corner."""
        if not (self._small and self._grown):
            return
        if self._bubble["mode"] in FULL_SIZE_MODES or self._pending_question is not None:
            self._shrink_timer.stop()
        elif not self._shrink_timer.isActive():
            self._shrink_timer.start(SHRINK_SECONDS * 1000)

    def _shrink(self) -> None:
        if self._bubble["mode"] in FULL_SIZE_MODES or self._pending_question is not None:
            return
        if self._held or self._pointer_on_him:
            self._shrink_timer.start(1000)
            return
        self._grown = False
        self.sizeChanged.emit()

    # --- Bubble -----------------------------------------------------------------------------

    def _show(self, bubble: dict[str, Any]) -> None:
        self._hide_timer.stop()
        self._bubble = bubble
        self.bubbleChanged.emit()
        self._fit_size()

    def _close(self) -> None:
        self._unanswered_timer.stop()
        self._hide_timer.stop()
        if self._bubble["mode"] == "question":
            self._current = None
        self._show({"mode": "hidden"})
        if self.animator.mood_name() == "ask":
            self._set_mood("idle")
        if self._sheet_news is not None:  # a study sheet written, or failed, while he was busy
            news, self._sheet_news = self._sheet_news, None
            self._show(news)
            if news.get("file"):
                self._hide_timer.start(SHEET_NEWS_SECONDS * 1000)
            return
        if self._pending_course is not None:  # a course drawn up while he was busy
            bp, intro = self._pending_course
            self._pending_course = None
            self._change_course(bp, intro)

    def _auto_hide(self) -> None:
        if self._held:
            self._hide_timer.start(2000)
            return
        if self._bubble["mode"] in ("result", "message", "quip"):
            self._close()

    def _unanswered(self) -> None:
        if self._bubble["mode"] == "question":
            logger.info("question left unanswered: put off")
            self.scheduler.missed(self._clock())
            self._close()
