"""The game in the window: when Tagnan asks, what his bubble says, what his figure does."""

import logging
import random
import time
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QCursor

from tagnan import art
from tagnan import blueprint as blueprints
from tagnan import pause as pauses
from tagnan import progress as rules
from tagnan import subject as subjects
from tagnan.game import Game, Outcome
from tagnan.model import Question
from tagnan.scheduler import Scheduler, find_pace
from tagnan.ui import desktop
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
RESULT_SECONDS = 15  # a right answer's bubble closes by itself, unless hovered
QUIP_SECONDS = 1.8
MAX_COURSE_WORDS = 120
BUSY_MODES = ("question", "thinking", "result", "explanation", "pause")
UPDATED_KEY = "updated"  # in his settings, from tagnan/ui/updater.py: what an update changed
UPDATED_SECONDS = 30


class Controller(QObject):
    stageChanged = Signal()
    bubbleChanged = Signal()
    statusChanged = Signal()
    prefsChanged = Signal()  # his pace, his call or his subject
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
        # The pace chosen in his menu wins over the config file's gaps.
        saved = find_pace(str(self.settings.get("pace", "")))
        if saved is not None:
            scheduler.set_rhythm(scheduler.rhythm.paced(saved), clock())
        call = self.settings.get("call", calls.DEFAULT)
        self._call = call if isinstance(call, str) and call in calls.CHOICES else calls.DEFAULT
        self._stage = game.progress.grade
        self._spec = art.figure(self._stage)
        self._bubble: dict[str, Any] = {"mode": "hidden"}
        self._current: Question | None = None
        self._outcome: Outcome | None = None
        self._held = False
        self._refill_after = 0.0
        self._pending_course: tuple[blueprints.Blueprint, str] | None = None
        self._first_run = game.summary()["answered"] == 0
        animator.set_stage(self._stage)
        animator.tapped.connect(self._on_tapped)
        worker.batchReady.connect(self._on_batch)
        worker.batchFailed.connect(self._on_batch_failed)
        worker.explained.connect(self._on_explained)
        worker.explainFailed.connect(self._on_explain_failed)
        worker.planned.connect(self._on_planned)
        worker.planFailed.connect(self._on_plan_failed)
        self._tick_timer = self._timer(self._tick, single=False)
        self._mood_timer = self._timer(lambda: self._set_mood("idle"))
        self._hide_timer = self._timer(self._auto_hide)
        self._unanswered_timer = self._timer(self._unanswered)

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
        if self._bubble["mode"] not in ("hidden", "quip") or not self.scheduler.due(now):
            return
        if desktop.busy():
            self.scheduler.postpone(now, BUSY_RETRY_MINUTES)
            return
        if self._ask(now):
            self.sounds.play(self._call)  # to be heard away from the screen

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
        self._show(
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
        if outcome.after.grade != self._stage:
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
        if self._bubble["mode"] in ("question", "thinking"):
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
        """The subject bubble: what we learn (a course learned before, or anything in one's own
        words), then what within it (all of it, a domain, a subject chosen before, or one's own
        words)."""
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
                "courses": [{"label": c.name, "key": c.key} for c in self.game.courses()],
                "course": bp.key,
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

    def _change_course(self, bp: blueprints.Blueprint, intro: str = "") -> None:
        if bp.key == self.game.exam:
            text = f"We're already on {bp.name}. I'll keep to it."
        else:
            self.game.set_course(bp)
            logger.info("course: %r", bp.key)
            self._current = None
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

    @Slot(str)
    def setCall(self, key: str) -> None:
        """His call, played at once: one chooses it by ear."""
        if key not in calls.CHOICES:
            return
        self._call = key
        self.settings.set("call", key)
        logger.info("call: %s", key)
        self.prefsChanged.emit()
        self.sounds.play(key)

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

    # --- Brain ------------------------------------------------------------------------------

    def _refill_if_needed(self, force: bool = False) -> None:
        now = self._clock()
        if self.worker.generating or (not force and now < self._refill_after):
            return
        if self.game.needs_questions():
            logger.info("asking the brain for a batch")
            self.worker.generate(self.game.batch_request())

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
            self._show({"mode": "explanation", "title": "Listen well", "text": text})

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

    # --- Bubble -----------------------------------------------------------------------------

    def _show(self, bubble: dict[str, Any]) -> None:
        self._hide_timer.stop()
        self._bubble = bubble
        self.bubbleChanged.emit()

    def _close(self) -> None:
        self._unanswered_timer.stop()
        self._hide_timer.stop()
        if self._bubble["mode"] == "question":
            self._current = None
        self._show({"mode": "hidden"})
        if self.animator.mood_name() == "ask":
            self._set_mood("idle")
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
