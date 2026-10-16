"""The game in the window: when Tagnan asks, what his bubble says, what his figure does."""

import logging
import random
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from tagnan import art
from tagnan import progress as rules
from tagnan.game import Game, Outcome
from tagnan.model import Question
from tagnan.scheduler import Scheduler
from tagnan.ui import desktop
from tagnan.ui.animator import Animator
from tagnan.ui.worker import BrainWorker

logger = logging.getLogger(__name__)

LETTERS = "ABCDEF"
ASKS = ("En garde !", "Une question, Gascon !", "À toi, mousquetaire !", "Garde-à-vous !")
CHEERS = ("Touché !", "Bien paré !", "Une botte imparable !", "Par ma rapière, c'est juste !")
SCOLDS = ("Mordieu !", "Ventre-saint-gris !", "Palsambleu !", "Sang-Dieu, non !")
QUIPS = {
    "wink": ("Hé !", "Ça chatouille !", "Holà, doucement !"),
    "annoyed": ("Tudieu ! Laisse-moi, j'ai une rapière.",),
    "sulk": ("…",),
}
DIFFICULTY = {"facile": "facile", "moyen": "moyenne", "difficile": "difficile"}
REVIEW_WHEN = {1: "demain", 2: "dans 3 jours", 3: "dans une semaine", 4: "dans 3 semaines"}

TICK_MS = 15_000
UNANSWERED_MINUTES = 10  # a question left alone goes away, as if put off
BUSY_RETRY_MINUTES = 5
NO_QUESTION_RETRY_MINUTES = 2
REFILL_BACKOFF = 600.0  # after a failed batch, wait before asking the brain again
FIRST_QUESTION_DELAY = 20.0  # the very first question comes soon after the first batch
MOOD_SECONDS = {"happy": 4.0, "angry": 6.0}
RESULT_SECONDS = 15  # a right answer's bubble closes by itself, unless hovered
QUIP_SECONDS = 1.8


def typeset(value: Any) -> Any:
    """French typography: a no-break space before ! ? : ; so that they never start a line."""
    if isinstance(value, str):
        for mark in "!?:;":
            value = value.replace(f" {mark}", f"\u00a0{mark}")
        return value
    if isinstance(value, dict):
        return {k: typeset(v) for k, v in value.items()}
    if isinstance(value, list):
        return [typeset(v) for v in value]
    return value


class Controller(QObject):
    stageChanged = Signal()
    bubbleChanged = Signal()
    statusChanged = Signal()
    menuRequested = Signal()
    quitRequested = Signal()

    def __init__(
        self,
        game: Game,
        scheduler: Scheduler,
        worker: BrainWorker,
        animator: Animator,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        super().__init__()
        self.game = game
        self.scheduler = scheduler
        self.worker = worker
        self.animator = animator
        self._rng = rng or random.Random()  # noqa: S311 - which interjection: not a secret
        self._clock = clock
        self._stage = game.progress.grade
        self._spec = art.figure(self._stage)
        self._bubble: dict[str, Any] = {"mode": "hidden"}
        self._current: Question | None = None
        self._outcome: Outcome | None = None
        self._held = False
        self._refill_after = 0.0
        self._first_run = game.summary()["answered"] == 0
        animator.set_stage(self._stage)
        animator.tapped.connect(self._on_tapped)
        worker.batchReady.connect(self._on_batch)
        worker.batchFailed.connect(self._on_batch_failed)
        worker.explained.connect(self._on_explained)
        worker.explainFailed.connect(self._on_explain_failed)
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
        if self.game.store.fresh_count(self.game.exam) == 0:
            self._show(
                {
                    "mode": "message",
                    "title": "Bonjour !",
                    "text": "Je prépare mes premières questions, une minute ou deux. "
                    "Clique sur moi en attendant, si le cœur t'en dit.",
                }
            )
        self._refill_if_needed()

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

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        p = self.game.progress
        return f"Tagnan · {rules.GRADES[p.grade].name} · {p.points} points · série {p.streak}"

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
        self._ask(now)

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
        self._show(
            {
                "mode": "question",
                "title": self._rng.choice(ASKS),
                "meta": f"Domaine {domain.id} · {domain.name}",
                "tag": "À revoir"
                if review
                else f"Question {DIFFICULTY.get(question.difficulty, '')}",
                "stem": question.stem,
                "choices": [
                    {"letter": LETTERS[i], "text": c} for i, c in enumerate(question.choices)
                ],
                "need": need,
                "hint": "" if need == 1 else f"Choisis-en {need}, puis valide.",
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
            points = f"+{outcome.delta} points · {after.points} au total · série de {after.streak}"
        elif outcome.delta:
            # A real minus sign, as the bubble prints it.
            points = (
                f"\u2212{-outcome.delta} points · {after.points} au total · série remise à zéro"
            )
        else:
            points = f"{after.points} points · série remise à zéro"
        if outcome.promoted:
            grade = rules.GRADES[after.grade]
            news = f"Promotion ! Tagnan passe {grade.name} : {grade.look}."
        elif outcome.demoted:
            news = f"Tagnan redescend {rules.GRADES[after.grade].name}."
        elif outcome.review_box and not outcome.correct:
            news = f"Cette question reviendra {REVIEW_WHEN[outcome.review_box]}."
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
                "title": "Question écartée",
                "text": "Merci, je ne la poserai plus. Le cerveau en écrira d'autres.",
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
            outcome.question.id,
            {
                "exam": self.game.exam,
                "question": outcome.question.to_dict(),
                "chosen": list(outcome.chosen),
            },
        )

    @Slot()
    def askNow(self) -> None:
        if self._bubble["mode"] in ("question", "thinking"):
            return
        if not self._ask(self._clock()):
            self._show(
                {
                    "mode": "message",
                    "title": "Pas encore",
                    "text": "Le cerveau écrit de nouvelles questions. Repasse dans une minute.",
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
            when = f"En pause jusqu'à {datetime.fromtimestamp(self.scheduler.paused_until):%H:%M}."
        else:
            when = (
                f"Prochaine question vers {datetime.fromtimestamp(self.scheduler.next_at):%H:%M}."
            )
        self._show(
            {
                "mode": "stats",
                "title": rules.GRADES[s["grade"]].name,
                "points": s["points"],
                "next": f"{band_end} pour {s['next_name']}"
                if band_end is not None
                else "grade le plus haut",
                "share": max(0.0, min(1.0, share)),
                "streak": f"Série : {s['streak']} · record {s['best_streak']}",
                "answers": f"{s['right']} bonnes réponses sur {s['answered']}",
                "domains": [
                    {
                        "name": f"{d['id']}. {low[i].name}",
                        "rate": d["right"] / d["answered"] if d["answered"] else -1.0,
                        "count": f"{d['right']}/{d['answered']}",
                    }
                    for i, d in enumerate(s["domains"])
                ],
                "bank": f"{s['fresh']} questions neuves en réserve, {s['reviews']} à revoir."
                f" {when}",
            }
        )

    @Slot(int)
    def pause(self, minutes: int) -> None:
        self.scheduler.pause(self._clock(), minutes)
        if self._bubble["mode"] == "question":
            self._close()
        self.statusChanged.emit()

    @Slot()
    def pauseUntilTomorrow(self) -> None:
        now = datetime.fromtimestamp(self._clock())
        tomorrow = now.replace(hour=self.scheduler.rhythm.start_hour, minute=0, second=0)
        minutes = (tomorrow.timestamp() - now.timestamp()) / 60
        self.pause(int(minutes if minutes > 0 else minutes + 24 * 60))

    @Slot()
    def resume(self) -> None:
        self.scheduler.resume(self._clock())
        self.statusChanged.emit()

    @Slot(bool)
    def hold(self, held: bool) -> None:
        """The pointer is over the bubble: it does not close by itself meanwhile."""
        self._held = held
        if not held and self._hide_timer.isActive() is False and self._bubble["mode"] == "message":
            self._hide_timer.start(4000)

    @Slot()
    def showMenu(self) -> None:
        self.menuRequested.emit()

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
        ids, rejected = self.game.add_batch(questions, self._clock())
        logger.info("batch: %d kept, %d dropped %s", len(ids), len(rejected), rejected[:3])
        if self._first_run and ids:
            self._first_run = False
            self.scheduler.next_at = self._clock() + FIRST_QUESTION_DELAY
            if self._bubble["mode"] == "message":
                self._show(
                    {
                        "mode": "message",
                        "title": "Prêt !",
                        "text": "Mes questions sont écrites. En garde, la première arrive.",
                    }
                )
                self._hide_timer.start(8000)

    def _on_batch_failed(self, error: str) -> None:
        self._refill_after = self._clock() + REFILL_BACKOFF
        if self.game.store.fresh_count(self.game.exam) == 0 and self._bubble["mode"] in (
            "hidden",
            "message",
        ):
            self._show(
                {
                    "mode": "message",
                    "title": "Le cerveau cale",
                    "text": f"Je n'ai pas pu écrire de questions : {error}."
                    " Je réessaie dans dix minutes.",
                }
            )

    def _on_explained(self, question_id: int, text: str) -> None:
        if (
            self._bubble["mode"] == "thinking"
            and self._outcome
            and self._outcome.question.id == question_id
        ):
            self._show({"mode": "explanation", "title": "Écoute bien", "text": text})

    def _on_explain_failed(self, question_id: int, error: str) -> None:
        if self._bubble["mode"] == "thinking":
            self._show(
                {**self._bubble, "mode": "result", "news": f"Pas d'explication de plus : {error}"}
            )

    # --- Figure -----------------------------------------------------------------------------

    def _on_tapped(self, mood: str) -> None:
        if self._bubble["mode"] in ("hidden", "quip"):
            self._show({"mode": "quip", "text": self._rng.choice(QUIPS.get(mood, ("Hé !",)))})
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
        self._bubble = typeset(bubble)
        self.bubbleChanged.emit()

    def _close(self) -> None:
        self._unanswered_timer.stop()
        self._hide_timer.stop()
        if self._bubble["mode"] == "question":
            self._current = None
        self._show({"mode": "hidden"})
        if self.animator.mood_name() == "ask":
            self._set_mood("idle")

    def _auto_hide(self) -> None:
        if self._held:
            self._hide_timer.start(2000)
            return
        if self._bubble["mode"] in ("result", "message", "quip"):
            self._close()

    def _unanswered(self) -> None:
        if self._bubble["mode"] == "question":
            logger.info("question left unanswered: put off")
            self.later()
