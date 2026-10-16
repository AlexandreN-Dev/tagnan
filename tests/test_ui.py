import os
import random
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication

from tagnan.brain_client import BrainClient
from tagnan.game import Game
from tagnan.progress import Progress
from tagnan.scheduler import Rhythm, Scheduler
from tagnan.ui.animation.rig import Rig
from tagnan.ui.animation.taps import Mood, TapTracker
from tagnan.ui.animator import Animator
from tagnan.ui.controller import Controller
from tagnan.ui.worker import BrainWorker
from tests.conftest import question_data

NOW = 1_800_000_000.0


@pytest.fixture(scope="module", autouse=True)
def qt_app() -> QGuiApplication:
    app = QGuiApplication.instance() or QGuiApplication([])
    assert isinstance(app, QGuiApplication)
    return app


# --- Taps and rig -----------------------------------------------------------------------------


def test_taps_tickle_annoy_then_sulk() -> None:
    taps = TapTracker()
    assert taps.tap(0.0) is Mood.TICKLED
    assert taps.mood(1.0) is Mood.NONE
    assert taps.tap(10.0) is Mood.TICKLED
    assert taps.tap(10.4) is Mood.TICKLED
    assert taps.tap(10.8) is Mood.ANNOYED
    for t in (11.2, 11.6):
        assert taps.tap(t) is Mood.ANNOYED
    assert taps.tap(12.0) is Mood.SULKING  # six within 3 s
    assert taps.tap(13.0) is Mood.SULKING  # poking a sulker keeps him sulking
    assert taps.mood(15.5) is Mood.NONE


def run(rig: Rig, seconds: float) -> list[Any]:
    poses = []
    for _ in range(round(seconds / 0.033)):
        poses.append(rig.step(0.033))
    return poses


def test_asking_raises_the_rapier_and_cheering_hops() -> None:
    rig = Rig(random.Random(1))
    rig.set_stage(4)
    run(rig, 0.5)
    assert rig.step(0.033).guard < 0.1
    rig.set_mood("ask")
    assert run(rig, 1.2)[-1].guard > 0.9
    rig.set_mood("happy")
    poses = run(rig, 1.2)
    assert min(p.body_y for p in poses) < -12  # two bounds, the first about 18 high
    assert {p.expression for p in poses} == {"happy"}
    rig.set_mood("angry")
    poses = run(rig, 1.5)
    assert max(abs(p.body_x) for p in poses[:15]) > 2  # he shakes with rage
    assert poses[-1].guard < 0.15  # the rapier goes back down


def test_taps_splash_and_change_his_face() -> None:
    rig = Rig(random.Random(2))
    rig.set_stage(5)
    run(rig, 0.3)
    assert rig.tap() is Mood.TICKLED
    pose = rig.step(0.033)
    assert pose.expression == "wink"
    assert pose.burst >= 0
    run(rig, 1.5)
    assert rig.step(0.033).burst == -1.0
    for _ in range(3):  # three within 1.5 s
        rig.tap()
        rig.step(0.1)
    assert rig.tap_mood is Mood.ANNOYED
    assert rig.step(0.033).expression == "annoyed"


def test_the_inkwell_stays_put_and_reduced_motion_is_still() -> None:
    rig = Rig(random.Random(3))
    rig.set_stage(0)
    rig.set_mood("happy")
    assert all(p.body_y == 0 for p in run(rig, 1.0))
    calm = Rig(random.Random(3), reduced_motion=True)
    calm.set_stage(5)
    calm.set_mood("ask")
    pose = calm.step(0.033)
    assert (pose.body_y, pose.body_x, pose.guard, pose.expression) == (0.0, 0.0, 1.0, "ask")


def test_animator_hands_the_outline_to_qml() -> None:
    animator = Animator(Rig(random.Random(4)), stage=5)
    first = animator.property("inkPath")
    animator.advance(0.5)
    assert animator.property("inkPath") != first
    assert animator.property("inkPath").startswith("M")
    animator.setProperty("stage", 0)
    assert "L87 122" in animator.property("inkPath")  # the inkwell's ink


# --- The game in the window -------------------------------------------------------------------


class FakeWorker(BrainWorker):
    def __init__(self) -> None:
        super().__init__(BrainClient(("false",)))
        self.requests: list[dict[str, Any]] = []
        self.explanations: list[int] = []

    def generate(self, request: dict[str, Any]) -> bool:
        self.requests.append(request)
        self.generating = True
        return True

    def explain(self, question_id: int, request: dict[str, Any]) -> None:
        self.explanations.append(question_id)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> float:
        return self.now


def make(game: Game, clock: Clock | None = None) -> tuple[Controller, FakeWorker, Animator]:
    clock = clock or Clock()
    worker = FakeWorker()
    animator = Animator(Rig(random.Random(5)))
    scheduler = Scheduler(
        Rhythm(weekends=True, start_hour=0, end_hour=24), random.Random(6), clock()
    )
    controller = Controller(game, scheduler, worker, animator, random.Random(7), clock)
    return controller, worker, animator


def fill(game: Game, count: int = 6) -> None:
    ids, rejected = game.add_batch([question_data(topic=f"n{i}") for i in range(count)], NOW)
    assert not rejected
    assert ids


def test_a_question_then_a_right_answer(game: Game) -> None:
    fill(game)
    controller, _, animator = make(game)
    controller.askNow()
    bubble = controller.property("bubble")
    assert bubble["mode"] == "question"
    assert len(bubble["choices"]) == 4
    assert animator.property("mood") == "ask"
    question = controller._current
    assert question is not None
    controller.answer(list(question.answers))
    bubble = controller.property("bubble")
    assert bubble["mode"] == "result"
    assert bubble["correct"] is True
    assert bubble["points"].startswith("+10 points")
    assert animator.property("mood") == "happy"
    assert game.progress.points == 10
    controller.dismiss()
    assert controller.property("bubble")["mode"] == "hidden"


def test_a_wrong_answer_explains_and_can_say_more(game: Game) -> None:
    fill(game)
    controller, worker, animator = make(game)
    controller.askNow()
    question = controller._current
    assert question is not None
    wrong = next(i for i in range(4) if i not in question.answers)
    controller.answer([wrong])
    bubble = controller.property("bubble")
    assert bubble["correct"] is False
    assert bubble["chosen"][0]["why"] == question.why_wrong[wrong]
    assert "Amazon Bedrock Guardrails" in bubble["right"]
    assert "reviendra demain" in bubble["news"]
    assert animator.property("mood") == "angry"
    controller.explainMore()
    assert controller.property("bubble")["mode"] == "thinking"
    assert worker.explanations == [question.id]
    worker.explained.emit(question.id, "Mordieu, écoute bien.")
    assert controller.property("bubble") == {
        "mode": "explanation",
        "title": "Écoute bien",
        "text": "Mordieu, écoute bien.",
    }


def test_a_flagged_question_never_comes_back(game: Game) -> None:
    fill(game, 1)
    controller, _, _ = make(game)
    controller.askNow()
    question = controller._current
    assert question is not None
    controller.flag()
    assert controller.property("bubble")["title"] == "Question écartée"
    assert game.store.fresh_count(game.exam) == 0


def test_promotion_changes_his_look(game: Game) -> None:
    fill(game)
    game.store.save_progress(game.exam, Progress(points=15, streak=2, grade=0))
    controller, _, animator = make(game)
    stages: list[int] = []
    controller.stageChanged.connect(lambda: stages.append(controller.property("stage")))
    controller.askNow()
    question = controller._current
    assert question is not None
    controller.answer(list(question.answers))
    assert stages == [1]
    assert animator.property("stage") == 1
    assert controller.property("spec")["stage"] == 1
    assert controller.property("bubble")["news"].startswith("Promotion ! Tagnan passe Gascon")


def test_first_start_writes_questions_then_asks_soon(game: Game) -> None:
    clock = Clock()
    controller, worker, _ = make(game, clock)
    controller.start()
    assert controller.property("bubble")["mode"] == "message"
    assert len(worker.requests) == 1
    assert len(worker.requests[0]["slots"]) == 10
    worker.generating = False
    worker.batchReady.emit({"questions": [question_data(topic=f"t{i}") for i in range(10)]})
    assert controller.property("bubble")["title"] == "Prêt !"
    assert controller.scheduler.next_at == pytest.approx(clock.now + 20)
    assert game.store.fresh_count(game.exam) == 10


def test_a_tap_gets_a_quip_only_when_he_is_free(game: Game) -> None:
    fill(game)
    controller, _, animator = make(game)
    animator.tap()
    assert controller.property("bubble")["mode"] == "quip"
    controller.askNow()
    animator.tap()
    assert controller.property("bubble")["mode"] == "question"
