"""The game in the window: when Tagnan asks, what his bubble says, what his figure does."""

import logging
import random
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QLocale, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QCursor

from tagnan import art, catalogue, language, words
from tagnan import blueprint as blueprints
from tagnan import config as configs
from tagnan import pause as pauses
from tagnan import progress as rules
from tagnan import subject as subjects
from tagnan.game import Added, Game, Outcome
from tagnan.model import CONVERTED, TYPED, Card, Question
from tagnan.scheduler import Scheduler, find_pace
from tagnan.ui import catalogues, desktop, sheetpdf
from tagnan.ui import sounds as calls
from tagnan.ui.animator import Animator
from tagnan.ui.sounds import Sounds
from tagnan.ui.worker import BrainWorker
from tagnan.words import Slot as WordSlot
from tagnan.words import Touch, Touched

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
# A language course: a call is a bout, a few of its words in a row (tagnan.words).
ASKING_MODES = ("question", "meet", "touch")  # he waits for an answer: no click elsewhere closes
BOUT_MODES = ("meet", "touch", "miss")  # a bout under way
ADVANCE_MS = 1100  # a touch answered right: the next one comes by itself
SENTENCE_MS = 1900  # a little later when the word's sentence shows
REMARK_MS = 2600  # or when he has a word to say: an accent, an article
PLACEMENT_MS = 900  # between two of the questions that place one
BUSY_MODES = (
    "question",
    "thinking",
    "result",
    "explanation",
    "pause",
    "meet",
    "touch",
    "miss",
    "bout",
    "level",
)
UPDATED_KEY = "updated"  # in his settings, from tagnan/ui/updater.py: what an update changed
UPDATED_SECONDS = 30
SHEET_NEWS_SECONDS = 12  # "Signed and sealed!": his study sheet is in Downloads
CATALOGUE_NEWS_SECONDS = 15  # what became of questions pasted or imported, a prompt copied
VERDICT_MODES = ("result", "thinking", "explanation")  # where a question's study sheet is offered
# Minimized (his menu's button beside the moon), he takes his full size for these bubbles only:
# he grows before the question shows, and goes back to his corner this long after the last.
FULL_SIZE_MODES = ("question", *VERDICT_MODES, *BOUT_MODES, "bout")
GROW_MS = 380  # Main.qml grows him in 350 ms
SHRINK_SECONDS = 3
THEMES = ("dark", "light")  # chosen in his menu; none: the system's


def counted(count: int, word: str) -> str:
    """ "1 question", "18 new questions"."""
    return f"{count} {word}{'' if count == 1 else 's'}"


def when(due_at: float, now: float) -> str:
    """When a word comes back, in words: "later today", "tomorrow", "in 3 weeks"."""
    ahead = due_at - now
    days = round(ahead / rules.DAY)
    if ahead < rules.DAY / 2:
        return "later today"
    if days <= 1:
        return "tomorrow"
    if days < 7:
        return f"in {days} days"
    if days < 14:
        return "in a week"
    if days < 30:
        return f"in {days // 7} weeks"
    return f"in {max(2, round(days / 30))} months"


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
        kept = str(self.settings.get("model", ""))
        chosen = configs.find_model(kept)
        self._model = configs.NOBODY if kept == configs.NOBODY else chosen.model if chosen else ""
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
        self._told_empty = False  # without a brain: "My satchel is empty", once till refilled
        # A language course's bout under way: its words, the one asked now, what it made of
        # each (its dots), the answer just given, and whether one has taken part (a word to
        # type may then take the keyboard).
        self._bout: list[WordSlot] = []
        self._bout_at = 0
        self._marks: list[str] = []
        self._rows: list[dict[str, str]] = []
        self._bout_before = game.progress
        self._touch: Touch | None = None
        self._touched: Touched | None = None
        self._engaged = False
        self._explaining: int | None = None  # the word Tell me more is about, as -its id
        # A language being set up (the level bubble), the questions that place one in it, and
        # what waits for the bubble to be free: a language the brain found in one's words, the
        # placement questions it wrote.
        self._setup: dict[str, str] | None = None
        self._placement: dict[str, Any] | None = None
        self._pending_language = ""
        self._pending_placement: list[dict[str, Any]] | None = None
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
        worker.wordsReady.connect(self._on_words)
        worker.wordsFailed.connect(self._on_batch_failed)
        worker.levelReady.connect(self._on_level)
        worker.levelFailed.connect(self._on_level_failed)
        self._tick_timer = self._timer(self._tick, single=False)
        self._mood_timer = self._timer(lambda: self._set_mood("idle"))
        self._hide_timer = self._timer(self._auto_hide)
        self._unanswered_timer = self._timer(self._unanswered)
        self._swap_timer = self._timer(self._swap)
        self._reveal_timer = self._timer(self._reveal)
        self._grow_timer = self._timer(self._grown_ready)
        self._shrink_timer = self._timer(self._shrink)
        self._advance_timer = self._timer(self._advance)

    def _timer(self, slot: Callable[[], None], single: bool = True) -> QTimer:
        timer = QTimer(self)
        timer.setSingleShot(single)
        timer.timeout.connect(slot)
        return timer

    def start(self) -> None:
        self._tick_timer.start(TICK_MS)
        nothing = (
            not self.game.store.cards(self.game.exam)
            if self.game.is_language
            else self.game.store.fresh_count(self.game.exam) == 0
        )
        if not self._tell_updated() and nothing:
            if self.brainless:
                self._show(
                    {
                        "mode": "message",
                        "title": "Hello!",
                        "text": "No brain here to write my questions: bring me some. Copy a"
                        " prompt for your assistant, or import a catalogue a colleague gave you.",
                        "buttons": [
                            {"label": "Copy the prompt", "action": "prompt:write", "primary": True},
                            {"label": "Import a file…", "action": "import"},
                        ],
                    }
                )
            else:
                self._show(
                    {
                        "mode": "message",
                        "title": "Hello!",
                        "text": f"I'm writing my first {self._things}: give me a few minutes. "
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
        """The model that writes his questions: his menu's choice, else the config file's;
        config.NOBODY for none."""
        return self._model or self._config_model

    @Property(bool, notify=prefsChanged)
    def brainless(self) -> bool:
        """Nobody writes his questions: he asks those of his catalogues, and leaves out what
        only a brain can do (Tell me more, the study sheet, a subject in one's own words)."""
        return (self._model or self._config_model) == configs.NOBODY

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

    @property
    def _things(self) -> str:
        """What he asks, in the course learned now: questions, or a language's words."""
        return "words" if self.game.is_language else "questions"

    def _ask(self, now: float, asked: bool = False) -> bool:
        """asked: one asked for it, in his menu or his bubble; else he asks of his own accord."""
        if self.game.is_language:
            return self._ask_bout(now, asked)
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
                else "Your question"  # typed by hand: no level of its own
                if question.origin == TYPED
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
            # Without a brain: no study sheet, and Tell me more asks one's own assistant.
            "sheet": "" if self.brainless else self._sheet_state(q.id),
            "more": "Ask your assistant" if self.brainless else "Tell me more",
        }

    @Slot()
    def later(self) -> None:
        asking = self._bubble["mode"] in ASKING_MODES
        self._close()
        if asking:
            self.scheduler.snooze(self._clock())

    @Slot()
    def flag(self) -> None:
        """A wrong or badly worded question: never again, and no points either way."""
        if self._bout and self._touch is not None and self._bubble["mode"] in BOUT_MODES:
            self._flag_word()
            return
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
                "text": "Thank you, I won't ask it again."
                + ("" if self.brainless else " My brain will write others."),
            }
        )
        self._hide_timer.start(6000)

    @Slot()
    def dismiss(self) -> None:
        if self._bout and self._bubble["mode"] == "explanation":
            self.nextTouch()  # Tell me more, about a word missed: the bout goes on
            return
        self._close()

    @Slot()
    def explainMore(self) -> None:
        """Tell me more: his brain explains; without one, the question goes to the clipboard,
        for one's own assistant."""
        if self._bout and self._bubble["mode"] == "miss":
            self._explain_word()
            return
        outcome = self._outcome
        if outcome is None or outcome.question.id is None:
            return
        if self.brainless:
            self.catalogue_files.copy(
                catalogue.explain_prompt(self.game.blueprint, outcome.question, outcome.chosen)
            )
            if self._bubble["mode"] == "result":
                self._show({**self._bubble, "more": "copied"})
            return
        self._hide_timer.stop()
        self._show({**self._bubble, "mode": "thinking"})
        self.worker.explain(
            outcome.question.id, self.game.explain_request(outcome.question, outcome.chosen)
        )

    @Slot()
    def askNow(self) -> None:
        if (
            self._bubble["mode"] in (*ASKING_MODES, "thinking", "miss")
            or self._pending_question is not None
        ):
            return
        if not self._ask(self._clock(), asked=True):
            resting = self._words_resting()
            if resting:
                self._show({"mode": "message", "title": "All quiet", "text": resting})
                self._hide_timer.start(8000)
                return
            if self.brainless:
                self._told_empty = True
                self._show(self._satchel_empty())
                self._hide_timer.start(CATALOGUE_NEWS_SECONDS * 1000)
                return
            self._show(
                {
                    "mode": "message",
                    "title": "Not yet",
                    "text": f"My brain is writing {self._things} on "
                    f"{self.subject}. Come back in a few minutes.",
                }
            )
            self._hide_timer.start(6000)

    def _words_resting(self) -> str:
        """A language course with nothing to ask now, though it has words: when the next is."""
        if not self.game.is_language:
            return ""
        now = self._clock()
        ahead = [c.due_at for c in self.game.words() if rules.NEW < c.step < rules.KNOWN]
        if not ahead:
            return ""
        return (
            "Nothing to ask right now: your words are resting. The next one is due "
            f"{when(min(ahead), now)}."
        )

    def _satchel_empty(self) -> dict[str, Any]:
        """Without a brain, every question of his catalogues asked: the reviews go on."""
        if self.game.is_language:
            return {
                "mode": "message",
                "title": "My satchel is empty",
                "text": f"I've shown you every word of your lists on {self.subject}. They come"
                " back as planned; for new words, paste or import another list.",
                "buttons": [
                    {"label": "Copy the prompt", "action": "prompt:write", "primary": True},
                    {"label": "Got it", "action": "dismiss"},
                ],
            }
        reviews = self.game.store.reviews_pending(self.game.exam)
        come = "comes" if reviews == 1 else "come"
        then = (
            f"Your {counted(reviews, 'review')} {come} back as planned; for" if reviews else "For"
        )
        return {
            "mode": "message",
            "title": "My satchel is empty",
            "text": f"I've asked you every question of your catalogues on {self.subject}. {then}"
            " new questions, paste or import another catalogue.",
            "buttons": [
                {"label": "Copy the prompt", "action": "prompt:write", "primary": True},
                {"label": "Got it", "action": "dismiss"},
            ],
        }

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
            next_at = f"On a break until {pauses.clock(self.scheduler.paused_until, now)}."
        else:
            what = "bout" if self.game.is_language else "question"
            next_at = f"Next {what} around {pauses.clock(self.scheduler.next_at, now)}."
        counts = self.game.word_counts(now) if self.game.is_language else None
        up = self.game.level_up(now) if counts and not self.brainless else ""
        level = self.game.blueprint.language.level if self.game.blueprint.language else ""
        self._show(
            {
                "mode": "stats",
                # A language course: its words, where a course of questions shows its answers.
                "words": {}
                if counts is None
                else {
                    "course": " · ".join(x for x in (self.game.blueprint.name, level) if x),
                    "known": counts["known"],
                    "climbing": counts["climbing"],
                    "fresh": counts["fresh"],
                    "chapters": [
                        {
                            "name": f"{c['id']}. {c['name']}",
                            "rate": c["known"] / c["of"] if c["of"] else 0.0,
                            "count": f"{c['known']}/{c['of']}",
                        }
                        for c in counts["chapters"]
                    ],
                    "news": f"You hold {level} well: nine right in ten this week. {up} whenever"
                    " you like."
                    if up
                    else "",
                    "up": up,
                    "bank": f"{counted(counts['due'], 'word')} due today. {next_at}",
                },
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
                f"{s['reviews']} to review in all. {next_at}",
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
                # Without a brain, nothing writes questions on a subject in one's own words; a
                # language course keeps to its chapters.
                "noWords": self.brainless or self.game.is_language,
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
        known = self._known_course(said)
        if known is not None:
            return {"ok": True, "text": f"Back to {known.name}."}
        if len(said) > MAX_COURSE_WORDS:
            return {"ok": False, "text": f"Shorter, please: {MAX_COURSE_WORDS} characters at most."}
        spoken = language.find(said)
        if spoken is not None:
            then = (
                "copy the prompt that draws it up, for your assistant"
                if self.brainless
                else "draw up its chapters"
            )
            return {
                "ok": True,
                "text": f"{spoken.name}: a language. I'll ask your level, then {then}.",
            }
        if self.brainless:
            return {
                "ok": True,
                "text": f"{said[0].upper() + said[1:]}: I'll copy the prompt that draws up the"
                " course, for your assistant.",
            }
        return {"ok": True, "text": "I'll draw up a course on it: a minute or two."}

    def _known_course(self, said: str) -> blueprints.Blueprint | None:
        """A course one has, named as it is, or as the language it teaches ("learn Spanish")."""
        known = self.game.find_course(said)
        spoken = language.find(said)
        if known is None and spoken is not None:
            known = self.game.find_course(spoken.name)
        return known

    @Slot(str, result=bool)
    def learnWith(self, text: str) -> bool:
        """Learn something else: a course learned before at once, anything else once the brain
        has drawn up its course."""
        said = " ".join(text.split()).strip(" .!?")
        if not self.previewCourse(said)["ok"]:
            return False
        known = self._known_course(said)
        if known is not None:
            self._change_course(known)
            return True
        spoken = language.find(said)
        if spoken is not None:  # a language: one's level and the language one speaks, first
            self._show_level(spoken)
            return True
        if self.brainless:
            self.catalogue_files.copy(catalogue.course_prompt(said))
            logger.info("course prompt copied: %r", said)
            self._show_catalogue_prompt(
                f"No brain here to draw up a course: the prompt for {said} is in your clipboard."
                " Paste it into your assistant, then bring me its answer: Paste questions."
            )
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
                text += (
                    f" Bring me {self._things} on it: my menu, Catalogues."
                    if self.brainless
                    else " Your first words in a minute or two."
                    if self.game.is_language and not self.game.store.cards(bp.key)
                    else ""
                    if self.game.is_language
                    else " Give me a few minutes to write the questions."
                )
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
            elif self.brainless:
                text = (
                    f"From now on, I ask about {name}. I have no new question on it: bring me"
                    " some, from my menu's Catalogues."
                )
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
        """The model that writes his next questions, or config.NOBODY: those of his catalogues
        only. The questions already written stay."""
        chosen = configs.find_model(key)
        if key == configs.NOBODY:
            if self.brainless:
                return
            self._model = configs.NOBODY
            self.settings.set("model", configs.NOBODY)
            logger.info("model: nobody, catalogues only")
            self.prefsChanged.emit()
            if self._bubble["mode"] not in BUSY_MODES:
                self._set_mood("idle")
                self._show(
                    {
                        "mode": "message",
                        "title": "As you wish!",
                        "text": "Nobody writes my questions now: I ask those of your catalogues."
                        " My menu's Catalogues has a prompt for your assistant.",
                    }
                )
                self._hide_timer.start(9000)
            return
        if chosen is None or chosen.model == (self._model or self._config_model):
            return
        was_brainless = self.brainless
        self._model = chosen.model
        self.settings.set("model", chosen.model)
        logger.info("model: %s", chosen.model)
        self.prefsChanged.emit()
        if was_brainless:
            self.worker.look_up_account()  # whose Claude login he writes with, at his menu's foot
            self._refill_if_needed(force=True)
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
        return self._bubble["mode"] not in ("hidden", *ASKING_MODES, "miss")

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
        self._take_catalogue(text, pasted=False, name=path.stem)

    def _take_catalogue(self, text: str, pasted: bool, name: str = "") -> None:
        """Its questions, checked and kept in their course: one he knows, or the one it brings,
        kept then but learned only if one says so. Questions typed by hand bring a course of
        their own, named by their # title or the file's `name`; the same name again adds to it,
        its chapters matched by name."""
        try:
            found = catalogue.read(text, name)
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
        questions: Sequence[Mapping[str, Any]] = found.questions
        cards: Sequence[Mapping[str, Any]] = found.words
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
            else:
                if found.typed:  # a note pasted again, longer: its new chapters join the course
                    merged, questions = catalogue.merge(bp, found.course, found.questions)
                    merged, cards = catalogue.merge(merged, found.course, found.words)
                    if merged != bp:
                        self.game.keep_course(merged)
                        bp = merged
        if cards and bp.language is None:
            self._say_catalogue(
                "A course of questions",
                f"These are words, and {bp.name} is a course of questions: give your list"
                " another title.",
            )
            return
        added = self.game.add_questions(bp, questions, self._clock(), found.origin, found.subject)
        if cards:  # a language course's words: what became of them is what he says
            added = self.game.add_cards(bp, cards, self._clock(), found.origin)
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
            if current:
                self._told_empty = False
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
        what = "word" if found.words else "question"
        lines = []
        if new and kept:
            title = "A new course!"
            lines.append(
                f"{bp.name}: {counted(len(bp.domains), 'chapter')}, {counted(kept, what)}."
            )
        elif kept:
            title = "Cut short!" if found.cut else "Fresh ink, mostly" if aside else "Fresh ink!"
            said = f"{counted(kept, f'new {what}')} on {bp.name}"
            if found.origin == CONVERTED:
                said += ", converted from your quiz: they stay with you, never exported"
            lines.append(said + ".")
        elif aside:
            title = "Set aside"
            lines.append(f"None of these {what}s holds up for {bp.name}.")
        else:
            title = "Nothing new"
            lines.append(f"I already had {'it' if known == 1 else f'all {known}'}, in {bp.name}.")
        if known and kept:
            lines.append(f"{known} I already had.")
        if aside:
            reasons = "; ".join(f"{what} {n}: {catalogue.reason(why)}" for n, why in aside[:3])
            more = f"; and {len(aside) - 3} more" if len(aside) > 3 else ""
            lines.append(f"{len(aside)} set aside: {reasons}{more}.")
        if found.left_out:
            left = "; ".join(
                f"question {n}, {why}" if why else f"question {n}" for n, why in found.left_out[:3]
            )
            lines.append(f"Your assistant left {len(found.left_out)} out: {left}.")
        if found.cut and kept:
            lines.append(
                f"Your assistant's answer breaks off: I kept the whole {what}s before the"
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
            if found.words and found.typed:
                lines.append("I build their questions myself: no brain needed.")
            buttons = [
                {
                    "label": "A bout now" if found.words else "A question now",
                    "action": "ask",
                    "primary": True,
                },
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
        if bp.language is not None:  # a language course: words, as his brain would write them
            prompt = catalogue.words_prompt(bp, self.game.words_request(catalogue.BATCH))
            text = (
                "The prompt is in your clipboard. Paste it into ChatGPT, Gemini or Copilot, then"
                " copy its whole answer and bring it to me: Paste questions."
            )
        elif kind == "convert":
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

    @Slot()
    def copyFormat(self) -> None:
        """The plain-text shape he reads, in the clipboard: an example to write after."""
        self.catalogue_files.copy(catalogue.FORMAT_EXAMPLE)
        logger.info("plain-text format copied")
        self._set_mood("idle")
        self._show(
            {
                "mode": "message",
                "title": "Your quill, sir!",
                "text": "The format is in your clipboard: an example to follow. Write your"
                " questions in its shape, in a note or a text file, then Paste questions or Import"
                " a file…",
                "buttons": [
                    {"label": "Paste questions", "action": "paste", "primary": True},
                    {"label": "Got it", "action": "dismiss"},
                ],
            }
        )
        self._hide_timer.start(CATALOGUE_NEWS_SECONDS * 1000)

    @Slot()
    def copyWordList(self) -> None:
        """A list of words as he reads it, in the clipboard: an example to write after."""
        self.catalogue_files.copy(catalogue.WORDS_EXAMPLE)
        logger.info("word list example copied")
        self._set_mood("idle")
        self._show(
            {
                "mode": "message",
                "title": "Your quill, sir!",
                "text": "A list of words is in your clipboard: an example to follow. The word,"
                " “=”, its meaning; under it, if you like, a sentence it lives in. Then Paste"
                " questions or Import a file…",
                "buttons": [
                    {"label": "Paste questions", "action": "paste", "primary": True},
                    {"label": "Got it", "action": "dismiss"},
                ],
            }
        )
        self._hide_timer.start(CATALOGUE_NEWS_SECONDS * 1000)

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
        if bp.language is not None:
            self._export_words(bp)
            return
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

    def _export_words(self, bp: blueprints.Blueprint) -> None:
        """A language course and its words, as a catalogue in Downloads: where one stands on
        each is one's own, a colleague starts them from the foot of the ladder."""
        cards = self.game.store.cards(bp.key)
        if not cards:
            self._say_catalogue("Nothing to share yet", f"I hold no words on {bp.name} yet.")
            return
        try:
            path = self.catalogue_files.write(
                catalogue.export(bp, [], cards), catalogue.file_name(bp, len(cards), "word")
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
                "text": f"{counted(len(cards), 'word')} on {bp.name}, in Downloads, ready to"
                " share.",
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

    # --- A language course: a bout ----------------------------------------------------------

    def _ask_bout(self, now: float, asked: bool) -> bool:
        """A call in a language course: a few of its words in a row, each a touch."""
        slots = self.game.next_bout(now)
        if not slots:
            self._refill_if_needed(force=True)
            self.scheduler.postpone(now, NO_QUESTION_RETRY_MINUTES)
            return False
        self._current, self._outcome = None, None
        self._bout, self._bout_at = slots, 0
        self._marks, self._rows = [""] * len(slots), []
        self._bout_before = self.game.progress
        self._engaged = asked
        self._show_touch(first=True)
        self._set_mood("ask")
        return True

    def _show_touch(self, first: bool = False) -> None:
        """The bout's word whose turn it is, as it stands now; its end after the last."""
        touch = None
        while self._bout_at < len(self._bout) and touch is None:
            try:
                touch = self.game.touch(self._bout[self._bout_at])
            except KeyError:  # a word gone meanwhile
                self._bout_at += 1
        if touch is None:
            self._end_bout()
            return
        self._touch, self._touched = touch, None
        content = (
            self._meet_content(touch) if touch.kind == words.MEET else self._touch_content(touch)
        )
        if first:
            self._show_question(content)
        else:
            self._show(content)
            self._set_mood("ask")
        self._unanswered_timer.start(UNANSWERED_MINUTES * 60_000)

    def _dots(self) -> list[str]:
        """The bout's touches, one each: seen, good, bad, the one asked now, those to come."""
        return [m or ("now" if i == self._bout_at else "") for i, m in enumerate(self._marks)]

    def _word_meta(self, card: Card) -> str:
        bp = self.game.blueprint
        try:
            return f"{bp.title} · {bp.domain(card.domain).name}"
        except KeyError:
            return bp.title

    def _meet_content(self, touch: Touch) -> dict[str, Any]:
        card = touch.card
        return {
            "mode": "meet",
            "title": "A new word",
            "dots": self._dots(),
            "meta": self._word_meta(card),
            "term": card.term,
            "meaning": card.meaning,
            "example": card.example,
            "translation": card.translation,
            "note": card.note,
        }

    def _touch_content(self, touch: Touch) -> dict[str, Any]:
        """How a word is asked: its meaning picked, the word picked, the word in its sentence,
        or typed, with the letters a plain keyboard may lack."""
        card = touch.card
        spoken = self.game.blueprint.language
        learned = spoken.learned if spoken else self.game.blueprint.name
        gap = card.gap
        typing = touch.kind in words.TYPED
        sentence = ""
        if gap and touch.kind in (words.GAP, words.TYPE_GAP):
            sentence = f"{gap[0]}____{gap[2]}"
        if touch.kind == words.MEANING:
            term, ask = card.term, "What does it mean?"
        elif sentence:
            term, ask = "", "Type the missing word:" if typing else "Which word goes there?"
        else:
            term, ask = card.meaning, f"In {learned}:" if typing else f"In {learned}?"
        return {
            "mode": "touch",
            "title": self._rng.choice(ASKS),
            "dots": self._dots(),
            "meta": self._word_meta(card),
            "term": term,
            "plain": touch.kind != words.MEANING,  # a meaning: said, not a word to look at
            "sentence": sentence,
            "translation": card.translation if sentence else "",
            "ask": ask,
            "choices": [{"letter": LETTERS[i], "text": c} for i, c in enumerate(touch.choices)],
            "long": any(len(c) > 24 for c in touch.choices),
            "typing": typing,
            # The letters of the course's words and sentences: of this word alone, they would
            # give it away.
            "letters": language.letters(
                f"{c.term} {c.sentence}" for c in self.game.store.cards(self.game.exam)
            )
            if typing
            else [],
            # A word to type takes the keyboard only once one has taken part in the bout.
            "focus": typing and self._engaged,
            "typed": "",
            "done": False,
            "good": -1,
            "bad": -1,
            "verdict": "",
            "tone": "",
            "other": "I don't know" if typing else "Wrong word? Report it",
            "placement": False,
        }

    @Slot(bool)
    def meetWord(self, known: bool) -> None:
        """A new word shown: Got it, or I know it already (straight to where it is typed)."""
        touch = self._touch
        if touch is None or self._bubble["mode"] != "meet":
            return
        self.game.meet(touch.card, self._clock(), known)
        self._marks[self._bout_at] = "seen"
        self._rows.append(
            {
                "term": touch.card.term,
                "mark": "seen",
                "next": "known already · typed later today" if known else "met · asked later today",
            }
        )
        self._engaged = True
        self._bout_at += 1
        self._show_touch()

    @Slot(int)
    def touchPick(self, index: int) -> None:
        """A choice picked: of a word's touch, or of a question that places one."""
        if self._placement is not None:
            self._placed(index)
            return
        touch = self._touch
        if (
            touch is None
            or self._bubble["mode"] != "touch"
            or self._touched is not None
            or touch.kind in words.TYPED
            or not 0 <= index < len(touch.choices)
        ):
            return
        self._answered(self.game.answer_touch(touch, self._clock(), picked=index))

    @Slot(str)
    def touchType(self, text: str) -> None:
        """A word typed; nothing typed is no answer yet."""
        touch = self._touch
        if (
            touch is None
            or self._bubble["mode"] != "touch"
            or self._touched is not None
            or touch.kind not in words.TYPED
            or not text.strip()
        ):
            return
        self._answered(self.game.answer_touch(touch, self._clock(), typed=text))

    @Slot()
    def touchSkip(self) -> None:
        """I don't know: a miss, and the word shown."""
        touch = self._touch
        if (
            touch is None
            or self._bubble["mode"] != "touch"
            or self._touched is not None
            or touch.kind not in words.TYPED
        ):
            return
        self._answered(self.game.answer_touch(touch, self._clock(), typed=""))

    def _answered(self, done: Touched) -> None:
        """Right: the touch says so and the next comes by itself. A miss stops the bout until
        Next: the word, its meaning, its sentence."""
        now = self._clock()
        self._unanswered_timer.stop()
        self._touched = done
        self._engaged = True
        card = done.touch.card
        self._marks[self._bout_at] = "good" if done.correct else "bad"
        self._rows.append(
            {
                "term": card.term,
                "mark": "good" if done.correct else "bad",
                "next": self._whereabouts(done, now),
            }
        )
        self.statusChanged.emit()
        if not done.correct:
            self._set_mood("angry", MOOD_SECONDS["angry"])
            self._show(self._miss_content(done))
            self._unanswered_timer.start(UNANSWERED_MINUTES * 60_000)
            return
        verdict, tone, wait = self._praise(done)
        self._set_mood("happy", wait / 1000)
        self._show(
            {
                **self._bubble,
                "dots": self._dots(),
                "good": done.touch.answer,
                "verdict": verdict,
                "tone": tone,
                "typed": done.typed,
                "done": True,
                "focus": False,
            }
        )
        self._advance_timer.start(wait)

    def _praise(self, done: Touched) -> tuple[str, str, int]:
        """His word on a right touch, its tone, and how long it stays."""
        card = done.touch.card
        if done.remark == language.ACCENT:
            return f"Touché, all but the accent: **{done.touch.expected}**.", "gold", REMARK_MS
        if done.remark == language.ARTICLE:
            return f"Touché! With its article: **{card.term}**.", "gold", REMARK_MS
        if done.remark == language.ALSO:
            return f"Touché! I had **{card.term}** in mind: both are right.", "gold", REMARK_MS
        cheer = self._rng.choice(CHEERS)
        if card.example and done.touch.kind not in (words.GAP, words.TYPE_GAP):
            return f"{cheer} «{card.example}»", "good", SENTENCE_MS
        return cheer, "good", ADVANCE_MS

    def _whereabouts(self, done: Touched, now: float) -> str:
        """Where a word goes on the ladder, and when it comes back: a row of the bout's end."""
        back = when(done.due_at, now)
        if not done.correct:
            fell = done.step < done.touch.card.step
            return f"{'back to ' if fell else ''}step {done.step} · {back}"
        if not done.moved:
            return f"still step {done.step} · {back}"
        if done.step >= rules.KNOWN:
            return f"known · {back}"
        return f"step {done.step} · {back}"

    def _miss_content(self, done: Touched) -> dict[str, Any]:
        touch = done.touch
        card = touch.card
        chosen = ""
        if touch.kind in words.TYPED:
            if done.typed.strip():
                chosen = f"You wrote **{done.typed.strip()}**."
        elif done.picked is not None and 0 <= done.picked < len(touch.behind):
            other = touch.behind[done.picked]  # a word of his too: he says what it is
            chosen = f"You picked **{touch.choices[done.picked]}**: " + (
                f"that is **{other.term}**." if touch.kind == words.MEANING else f"{other.meaning}."
            )
        return {
            "mode": "miss",
            "title": self._rng.choice(SCOLDS),
            "tone": "bad",
            "dots": self._dots(),
            "right": f"**{card.term}**: {card.meaning}.",
            "chosen": chosen,
            "example": card.example,
            "translation": card.translation,
            "note": card.note,
            "news": ("One step down: it" if done.step < card.step else "It")
            + f" comes back {when(done.due_at, self._clock())}.",
            "more": "Ask your assistant" if self.brainless else "Tell me more",
        }

    @Slot()
    def nextTouch(self) -> None:
        """The bout's next word, once this one is answered; its end after the last."""
        if self._placement is not None:
            self._advance()
            return
        if not self._bout or self._touched is None:
            return
        if self._bubble["mode"] not in ("touch", "miss", "explanation"):
            return
        self._advance_timer.stop()
        self._bout_at += 1
        self._show_touch()

    def _advance(self) -> None:
        """A right touch has been read, or a question that places one answered: the next."""
        if self._placement is not None:
            self._next_placement()
        elif self._bout and self._bubble["mode"] == "touch" and self._touched is not None:
            self.nextTouch()

    def _flag_word(self) -> None:
        """A wrong or badly worded word: never again; the bout goes on."""
        touch = self._touch
        if touch is None or touch.card.id is None:
            return
        self.game.store.flag_card(touch.card.id)
        logger.info("word %s flagged", touch.card.id)
        self._advance_timer.stop()
        if not self._marks[self._bout_at]:
            self._marks[self._bout_at] = "gone"
        self._bout_at += 1
        self._show_touch()

    def _explain_word(self) -> None:
        """Tell me more, about a word missed: his brain explains; without one, the question
        goes to the clipboard, for one's own assistant."""
        done = self._touched
        if done is None or done.touch.card.id is None:
            return
        bp = self.game.blueprint
        learned = bp.language.learned if bp.language else bp.name
        question, chosen = words.as_question(done.touch, done.picked, done.typed, learned)
        if self.brainless:
            self.catalogue_files.copy(catalogue.explain_prompt(bp, question, chosen))
            self._show({**self._bubble, "more": "copied"})
            return
        if self._bubble.get("more") == "thinking":
            return
        self._explaining = -done.touch.card.id
        self._show({**self._bubble, "more": "thinking"})
        self.worker.explain(
            self._explaining,
            {
                "exam": self.game.exam,
                "course": bp.to_dict(),
                "question": question,
                "chosen": chosen,
            },
        )

    def _end_bout(self) -> None:
        """The bout's last word answered: where each goes on the ladder, the points, and his
        promotion if the bout took him over the line."""
        now = self._clock()
        before, after = self._bout_before, self.game.progress
        rows, marks = self._rows, [m for m in self._marks if m != "gone"]
        self._bout, self._touch, self._touched = [], None, None
        self._marks, self._rows = [], []
        self._unanswered_timer.stop()
        self._advance_timer.stop()
        self.scheduler.asked(now)
        asked = [r for r in rows if r["mark"] != "seen"]
        delta = after.points - before.points
        promoted = after.grade > before.grade
        if not rows:  # every word of it reported
            self._close()
            return
        if not asked:
            title = "A new word" if len(rows) == 1 else f"{len(rows)} new words"
            points = (
                "No points yet: I'll ask " + ("it" if len(rows) == 1 else "them") + " in a while."
            )
        else:
            good = sum(1 for r in asked if r["mark"] == "good")
            title = (
                self._rng.choice(CHEERS)
                if good == len(asked)
                else "Well fought!"
                if good
                else self._rng.choice(SCOLDS)
            )
            if delta > 0:
                points = f"+{delta} points · {after.points} in all"
            elif delta < 0:
                points = f"\u2212{-delta} points · {after.points} in all"
            else:
                points = f"{after.points} points"
        if promoted:
            grade = rules.GRADES[after.grade]
            news = f"Promotion! Tagnan is now a {grade.name}: {grade.look}."
        elif after.grade < before.grade:
            news = f"Tagnan falls back to {rules.GRADES[after.grade].name}."
        else:
            news = ""
        clean = bool(asked) and all(r["mark"] == "good" for r in asked)
        self._set_mood("happy" if clean or not asked else "idle", MOOD_SECONDS["happy"])
        self._show(
            {
                "mode": "bout",
                "title": title,
                "tone": "good" if clean else "",
                "dots": marks,
                "rows": rows,
                "points": points,
                "news": news,
                "promoted": promoted,
                "rank": rules.GRADES[after.grade].name if promoted else "",
            }
        )
        if promoted and not self.animator.reduced_motion():
            self._promote(self._stage, after.grade)
        elif after.grade != self._stage:
            self._set_stage(after.grade)
        if not promoted:
            self._hide_timer.start(RESULT_SECONDS * 1000)
        self.statusChanged.emit()
        self._refill_if_needed()

    # --- A language course: its level, and the language one speaks -------------------------

    def _speaks(self, learned: str) -> str:
        """The language one speaks, as last chosen; else the system's, else English: but not
        the one learned."""
        kept = str(self.settings.get("speaks", ""))
        found = kept or language.by_locale(QLocale.system().name()) or "English"
        if found == learned:
            found = "French" if learned == "English" else "English"
        return found

    def _show_level(self, found: language.Found, status: str = "") -> None:
        """The level bubble: one's level, and the language one speaks, before the course."""
        self._setup = {
            "learned": found.name,
            "level": found.level,
            "speaks": self._speaks(found.name),
            "purpose": found.purpose,
        }
        self._set_mood("happy", MOOD_SECONDS["happy"])
        self._show(self._level_content(status))

    def _level_content(self, status: str = "") -> dict[str, Any]:
        setup = self._setup or {}
        learned, speaks = setup.get("learned", ""), setup.get("speaks", "English")
        offered = list(dict.fromkeys(["English", "French", speaks]))
        return {
            "mode": "level",
            "title": "A language!",
            "text": f"{learned}: I'll ask you its words, in {learned}. Two things before I draw"
            " up the course.",
            "levels": [{"key": key, "label": f"{key} · {name}"} for key, name in language.LEVELS],
            "level": setup.get("level", ""),
            "speaks": [
                {"key": name, "label": language.own_name(name)}
                for name in offered
                if name != learned
            ],
            "speak": speaks,
            # Finding one's level takes a brain to write the questions.
            "find": not self.brainless,
            "status": status,
        }

    @Slot(str)
    def setLevel(self, key: str) -> None:
        if self._setup is None or key not in language.LEVEL_KEYS:
            return
        self._setup["level"] = key
        self._show(self._level_content())

    @Slot(str)
    def setSpeaks(self, name: str) -> None:
        """The language one speaks: one offered, or typed (any of its names)."""
        said = language.named(name)
        if self._setup is None or not said or said == self._setup["learned"]:
            return
        self._setup["speaks"] = said
        self._show(self._level_content())

    @Slot()
    def drawLanguage(self) -> None:
        """Draw up the course: the brain writes its chapters; without one, the prompt for
        one's assistant, which draws it up and writes its first words."""
        setup = self._setup
        if setup is None or setup["level"] not in language.LEVEL_KEYS:
            return
        self._setup = None
        self.settings.set("speaks", setup["speaks"])
        learned, level = setup["learned"], setup["level"]
        if self.brainless:
            self.catalogue_files.copy(
                catalogue.language_prompt(learned, level, setup["speaks"], setup["purpose"])
            )
            logger.info("language prompt copied: %r %s", learned, level)
            self._show_catalogue_prompt(
                f"No brain here to draw up a course: the prompt for {learned} at {level} is in"
                " your clipboard. Paste it into your assistant, then bring me its answer: Paste"
                " questions."
            )
            return
        if self.worker.planning:
            title = "One at a time!"
            line = f"I'm still drawing up a course on {self.worker.planning}."
        else:
            self.worker.plan(learned, language=setup)
            logger.info("language asked for: %r %s", learned, level)
            title = "Let me think…"
            line = (
                f"{learned} at {level}: I'm drawing up its chapters, give me a minute or two."
                " I'll tell you when it's ready."
            )
        self._set_mood("idle")
        self._show({"mode": "message", "title": title, "text": line})
        self._hide_timer.start(8000)

    @Slot()
    def moveUp(self) -> None:
        """The next level, once he offers it (his progress): new chapters after the course's
        own, whose words stay."""
        bp = self.game.blueprint
        up = self.game.level_up(self._clock())
        if bp.language is None or not up or self.brainless:
            return
        if self.worker.planning:
            self._tell_if_free(
                "One at a time!", f"I'm still drawing up a course on {self.worker.planning}."
            )
            return
        spoken = {**bp.language.to_dict(), "level": up}
        self.worker.plan(bp.language.learned, language=spoken, course=bp.to_dict())
        logger.info("level asked for: %r %s", bp.key, up)
        self._set_mood("happy", MOOD_SECONDS["happy"])
        self._show(
            {
                "mode": "message",
                "title": f"{up} it is!",
                "text": f"I'm drawing up the chapters of {bp.name} at {up}: a minute or two."
                " The words you know stay known.",
            }
        )
        self._hide_timer.start(8000)

    def _raise_level(self, bp: blueprints.Blueprint) -> None:
        """The course learned now, a level up: its new chapters, and words for them."""
        self.game.keep_course(bp)
        level = bp.language.level if bp.language else ""
        first = bp.language.first if bp.language else 1
        chapters = "; ".join(f"{d.id}. {d.name}" for d in bp.domains if d.id >= first)
        logger.info("level: %r %s", bp.key, level)
        self.prefsChanged.emit()
        self.statusChanged.emit()
        self._refill_if_needed(force=True)
        self._set_mood("happy", MOOD_SECONDS["happy"])
        self._show(
            {
                "mode": "message",
                "title": "Onwards!",
                "text": f"{bp.name} at {level}: {chapters}. Their first words in a minute or two;"
                " the ones you are learning go on.",
            }
        )
        self._hide_timer.start(9000)

    # --- A language course: where one stands -----------------------------------------------

    @Slot()
    def findLevel(self) -> None:
        """Find my level: the brain writes a few questions that climb; they place one."""
        setup = self._setup
        if setup is None or self.brainless:
            return
        if self.worker.levelling:
            self._show(self._level_content(f"I'm writing them, for {self.worker.levelling}…"))
            return
        if not self.worker.level(setup["learned"], setup["speaks"]):
            return
        logger.info("placement asked for: %r", setup["learned"])
        self._set_mood("idle")
        self._show(
            {
                "mode": "message",
                "title": "Let me think…",
                "text": f"A few questions to find your level in {setup['learned']}: give me a"
                " minute. They come as soon as they are written.",
            }
        )
        self._hide_timer.start(8000)

    def _on_level(self, learned: str, answer: object) -> None:
        questions = answer.get("questions") if isinstance(answer, dict) else None
        if not isinstance(questions, list) or not questions:
            self._on_level_failed(learned, "no questions came")
            return
        if self._setup is None or self._setup["learned"] != learned:
            return  # one has moved on meanwhile
        placed = []
        for q in questions:  # their choices shuffled: models favour B and C
            order = list(range(len(q["choices"])))
            self._rng.shuffle(order)
            placed.append(
                {
                    "level": q["level"],
                    "sentence": q["sentence"],
                    "choices": [q["choices"][i] for i in order],
                    "answer": order.index(q["answer"]),
                }
            )
        if self._bubble["mode"] in BUSY_MODES:
            self._pending_placement = placed  # not over a question or a verdict
            return
        self._start_placement(placed)

    def _on_level_failed(self, learned: str, error: str) -> None:
        waiting = self._setup is not None and self._setup["learned"] == learned
        if waiting and self._bubble["mode"] in ("hidden", "message", "quip"):
            self._show(
                self._level_content(f"I couldn't write the questions ({error}): pick a level.")
            )

    def _start_placement(self, questions: list[dict[str, Any]]) -> None:
        self._placement = {"questions": questions, "at": 0, "marks": [""] * len(questions)}
        self._show_placement(first=True)
        self._set_mood("ask")

    def _show_placement(self, first: bool = False) -> None:
        placement = self._placement
        if placement is None:
            return
        at = placement["at"]
        question = placement["questions"][at]
        setup = self._setup or {}
        content = {
            "mode": "touch",
            "title": "Where do you stand?",
            "dots": [m or ("now" if i == at else "") for i, m in enumerate(placement["marks"])],
            "meta": f"{setup.get('learned', '')} · your level",
            "term": "",
            "plain": False,
            "sentence": question["sentence"],
            "translation": "",
            "ask": "Which one fits?",
            "choices": [
                {"letter": LETTERS[i], "text": c} for i, c in enumerate(question["choices"])
            ],
            "long": any(len(c) > 24 for c in question["choices"]),
            "typing": False,
            "letters": [],
            "focus": False,
            "typed": "",
            "done": False,
            "good": -1,
            "bad": -1,
            "verdict": "",
            "tone": "",
            "other": "",
            "placement": True,
        }
        if first:
            self._show_question(content)
        else:
            self._show(content)
        self._unanswered_timer.start(UNANSWERED_MINUTES * 60_000)

    def _placed(self, index: int) -> None:
        """A question that places one, answered: no points; the right choice shows."""
        placement = self._placement
        if placement is None or self._bubble["mode"] != "touch" or self._bubble.get("done"):
            return
        at = placement["at"]
        question = placement["questions"][at]
        right = index == question["answer"]
        placement["marks"][at] = "good" if right else "bad"
        self._unanswered_timer.stop()
        self._show(
            {
                **self._bubble,
                "dots": list(placement["marks"]),
                "good": question["answer"],
                "bad": -1 if right else index,
                "done": True,
            }
        )
        self._advance_timer.start(PLACEMENT_MS)

    def _next_placement(self) -> None:
        """The next question that places one; after the last, or two misses in a row, one's
        level: that of the last question answered right."""
        placement = self._placement
        if placement is None:
            return
        self._advance_timer.stop()
        marks = placement["marks"]
        at = placement["at"]
        missed_twice = at >= 1 and marks[at] == "bad" and marks[at - 1] == "bad"
        if at + 1 < len(placement["questions"]) and not missed_twice:
            placement["at"] = at + 1
            self._show_placement()
            return
        reached = [
            q["level"] for q, m in zip(placement["questions"], marks, strict=True) if m == "good"
        ]
        level = reached[-1] if reached else language.LEVEL_KEYS[0]
        self._placement = None
        self._unanswered_timer.stop()
        if self._setup is None:
            self._close()
            return
        self._setup["level"] = level
        name = dict(language.LEVELS)[level]
        logger.info("placed: %s", level)
        self._set_mood("happy", MOOD_SECONDS["happy"])
        self._show(self._level_content(f"I'd say {level}, {name}. Change it if you like."))

    # --- Brain ------------------------------------------------------------------------------

    def _refill_if_needed(self, force: bool = False) -> None:
        now = self._clock()
        if self.brainless or self.worker.generating or (not force and now < self._refill_after):
            return
        if self.game.is_language:
            spoken = self.game.blueprint.language
            # A list of one's own (no level) is one's own: the brain adds nothing to it.
            if spoken is not None and spoken.level and self.game.needs_words():
                logger.info("asking the brain for words")
                asked = self.game.words_request()
                if self._model:
                    asked["model"] = self._model
                self.worker.words(asked)
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

    def _on_words(self, answer: object) -> None:
        """A language course's words, written by the brain: kept in the course they are for."""
        data = answer if isinstance(answer, dict) else {}
        try:
            bp = self.game.course(str(data.get("course") or self.game.exam))
        except (KeyError, ValueError):
            logger.warning("words for an unknown course: %r", data.get("course"))
            return
        added = self.game.add_cards(bp, data.get("words") or [], self._clock())
        logger.info(
            "words on %r: %d kept, %d known, %d dropped %s",
            bp.key,
            len(added.ids),
            added.known,
            len(added.rejected),
            added.rejected[:3],
        )
        if self._first_run and added.ids and bp.key == self.game.exam:
            self._first_run = False
            self.scheduler.next_at = self._clock() + FIRST_QUESTION_DELAY
            if self._bubble["mode"] == "message":
                self._show(
                    {
                        "mode": "message",
                        "title": "Ready!",
                        "text": "My words are written. En garde, the first ones are coming.",
                    }
                )
                self._hide_timer.start(8000)
        self.statusChanged.emit()
        self._refill_if_needed()  # written for a course left meanwhile: some for this one

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
                    "text": f"I couldn't write {self._things}: {error}. I'll try again in ten"
                    " minutes.",
                }
            )

    def _on_planned(self, words: str, answer: object) -> None:
        data = answer if isinstance(answer, dict) else {}
        asked = str(data.get("language") or "") if data.get("understood") else ""
        if asked and not data.get("course"):
            # The words name a language he did not know by name: its level comes first.
            if self._bubble["mode"] in BUSY_MODES:
                self._pending_language = asked
            else:
                self._show_level(language.Found(asked))
            return
        try:
            if not data.get("understood"):
                raise ValueError(str(data.get("message") or "I don't know how to teach that."))
            bp = blueprints.from_dict(data.get("course") or {}, where="course")
        except ValueError as error:
            self._tell_if_free("Hmm…", f"A course on {words}? {error}")
            return
        mine = self.game.blueprint
        if (
            bp.language
            and mine.language
            and bp.key == mine.key
            and len(bp.domains) > len(mine.domains)
        ):
            self._raise_level(bp)  # the course learned now, a level up
            return
        chapters = "; ".join(f"{d.id}. {d.name}" for d in bp.domains)
        level = f", {bp.language.level}" if bp.language and bp.language.level else ""
        intro = f"Your course is ready: {bp.name}{level}. {chapters}."
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
        if self._bubble["mode"] == "miss" and self._explaining == question_id:
            # About a word missed in a bout: Got it goes on to its next word.
            self._explaining = None
            self._show({"mode": "explanation", "title": "Listen well", "text": text, "sheet": ""})
            return
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
        if self._bubble["mode"] == "miss" and self._explaining == question_id:
            self._explaining = None
            self._show(
                {
                    **self._bubble,
                    "more": "Tell me more",
                    "news": f"No more explanation: {error}",
                }
            )
            return
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
        closed = self._bubble["mode"]
        if closed == "question":
            self._current = None
        if self._bout or self._placement is not None:
            # A bout left before its end: the words not asked stay due. Once one has taken
            # part in it, it counts as his call.
            took_part = any(self._marks)
            self._bout, self._touch, self._touched, self._placement = [], None, None, None
            self._marks, self._rows = [], []
            self._advance_timer.stop()
            if took_part:
                self.scheduler.asked(self._clock())
        if closed == "level":
            self._setup = None
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
            return
        if self._pending_language:  # a language found in one's words while he was busy
            asked, self._pending_language = self._pending_language, ""
            self._show_level(language.Found(asked))
            return
        if self._pending_placement is not None and self._setup is not None:
            placed, self._pending_placement = self._pending_placement, None
            self._start_placement(placed)
            return
        if (
            closed in (*VERDICT_MODES, "bout")
            and self.brainless
            and not self._told_empty
            and self.game.fresh_count() == 0
        ):  # the last new question of his catalogues answered: said once
            self._told_empty = True
            self._show(self._satchel_empty())
            self._hide_timer.start(CATALOGUE_NEWS_SECONDS * 1000)

    def _auto_hide(self) -> None:
        if self._held:
            self._hide_timer.start(2000)
            return
        if self._bubble["mode"] in ("result", "message", "quip", "bout"):
            self._close()

    def _unanswered(self) -> None:
        if self._bubble["mode"] in (*ASKING_MODES, "miss"):
            logger.info("question left unanswered: put off")
            self.scheduler.missed(self._clock())
            self._close()
