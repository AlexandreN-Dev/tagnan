import json
import os
import random
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QMenu

from tagnan.brain_client import BrainClient
from tagnan.game import Game
from tagnan.paths import SOUNDS_DIR
from tagnan.progress import Progress
from tagnan.scheduler import Rhythm, Scheduler
from tagnan.ui.animation.rig import Rig
from tagnan.ui.animation.taps import Mood, TapTracker
from tagnan.ui.animator import Animator
from tagnan.ui.controller import Controller
from tagnan.ui.desktop import Settings
from tagnan.ui.sounds import Sounds
from tagnan.ui.tray import Tray
from tagnan.ui.worker import BrainWorker
from tests.conftest import question_data

NOW = 1_800_000_000.0


@pytest.fixture(scope="module", autouse=True)
def qt_app() -> QApplication:
    app = QApplication.instance() or QApplication([])  # widgets: his menu
    assert isinstance(app, QApplication)
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
    shading = ("inkwellShade", "inkwellLight", "meniscus")
    assert not any(animator.property(name) for name in shading)  # only the inkwell's ink has it
    animator.setProperty("stage", 0)
    assert "L95 122" in animator.property("inkPath")  # the inkwell's ink
    assert all(animator.property(name).startswith("M") for name in shading)


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


class Speaker:
    """What would have played."""

    def __init__(self) -> None:
        self.played: list[str] = []

    def __call__(self, path: Path) -> None:
        assert path.parent == SOUNDS_DIR
        self.played.append(path.stem)


def make(
    game: Game,
    clock: Clock | None = None,
    settings: Settings | None = None,
    speaker: Speaker | None = None,
) -> tuple[Controller, FakeWorker, Animator]:
    clock = clock or Clock()
    worker = FakeWorker()
    animator = Animator(Rig(random.Random(5)))
    scheduler = Scheduler(
        Rhythm(weekends=True, start_hour=0, end_hour=24), random.Random(6), clock()
    )
    controller = Controller(
        game,
        scheduler,
        worker,
        animator,
        random.Random(7),
        clock,
        settings=settings,
        sounds=Sounds(speaker or Speaker()),
    )
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
    assert "come back tomorrow" in bubble["news"]
    assert animator.property("mood") == "angry"
    controller.explainMore()
    assert controller.property("bubble")["mode"] == "thinking"
    assert worker.explanations == [question.id]
    worker.explained.emit(question.id, "Sacrebleu, listen well.")
    assert controller.property("bubble") == {
        "mode": "explanation",
        "title": "Listen well",
        "text": "Sacrebleu, listen well.",
    }


def test_a_flagged_question_never_comes_back(game: Game) -> None:
    fill(game, 1)
    controller, _, _ = make(game)
    controller.askNow()
    question = controller._current
    assert question is not None
    controller.flag()
    assert controller.property("bubble")["title"] == "Question set aside"
    assert game.store.fresh_count(game.exam) == 0


def test_promotion_changes_his_look(game: Game) -> None:
    fill(game)
    game.store.save_progress(game.exam, Progress(points=245, streak=2, grade=0))
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
    assert controller.property("bubble")["news"].startswith("Promotion! Tagnan is now a Gascon")


def test_first_start_writes_questions_then_asks_soon(game: Game) -> None:
    clock = Clock()
    controller, worker, _ = make(game, clock)
    controller.start()
    assert controller.property("bubble")["mode"] == "message"
    assert len(worker.requests) == 1
    assert len(worker.requests[0]["slots"]) == 10
    worker.generating = False
    worker.batchReady.emit({"questions": [question_data(topic=f"t{i}") for i in range(10)]})
    assert controller.property("bubble")["title"] == "Ready!"
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


def test_a_break_for_a_while_or_until_a_time(game: Game) -> None:
    fill(game)
    clock = Clock()
    controller, _, animator = make(game, clock)
    controller.askNow()
    controller.showPause()
    bubble = controller.property("bubble")
    assert bubble["mode"] == "pause"
    assert [c["label"] for c in bubble["choices"]] == [
        "30 min",
        "1 hour",
        "2 hours",
        "Until tomorrow",
    ]
    assert controller.previewPause("") == {"ok": False, "text": ""}
    assert controller.previewPause("1h")["ok"] is True
    assert controller.previewPause("1h")["text"].startswith("A break of 1 hour, back at")
    assert controller.previewPause("whenever")["ok"] is False
    assert controller.pauseWith("whenever") is False
    assert controller.pauseWith("1h") is True
    assert controller.scheduler.paused_until == pytest.approx(clock.now + 3600)
    assert controller.property("paused") is True
    assert controller.property("bubble")["title"] == "At ease!"
    controller.dismiss()
    animator.tap()  # a tap during the break says until when
    assert controller.property("bubble")["text"].startswith("On a break until")
    controller.resume()
    assert controller.property("paused") is False


def test_every_bubble_but_a_question_closes_on_a_click_elsewhere(game: Game) -> None:
    fill(game)
    controller, _, _ = make(game)
    assert not controller.closes_on_outside()  # nothing to close
    controller.showStats()
    assert controller.closes_on_outside()
    controller.askNow()
    assert not controller.closes_on_outside()  # a question stays


def test_outside_clicks_count_presses_outside_only() -> None:
    from PySide6.QtCore import QPoint

    from tagnan.ui.outside import OutsideClicks

    pressed = [True]
    at = [QPoint(5, 5)]
    clicks: list[bool] = []
    watcher = OutsideClicks(
        inside=lambda p: p.x() < 10, pressed=lambda: pressed[0], cursor=lambda: at[0]
    )
    watcher.clickedOutside.connect(lambda: clicks.append(True))
    watcher.watch(True)  # the button that opened the bubble is still down
    watcher.poll()
    assert clicks == []
    pressed[0] = False
    watcher.poll()
    pressed[0], at[0] = True, QPoint(50, 50)
    watcher.poll()
    watcher.poll()  # held down: one click
    assert clicks == [True]
    pressed[0] = False
    watcher.poll()
    pressed[0], at[0] = True, QPoint(3, 3)  # inside
    watcher.poll()
    assert clicks == [True]
    watcher.watch(False)
    assert not watcher.watching


# --- How often, and his call ------------------------------------------------------------------


def test_every_call_ships() -> None:
    from tagnan.ui.sounds import CALLS

    for key, _ in CALLS:
        assert (SOUNDS_DIR / f"{key}.wav").stat().st_size > 50_000


def test_he_sounds_his_call_only_when_he_asks_of_his_own_accord(game: Game) -> None:
    fill(game)
    clock = Clock()
    speaker = Speaker()
    controller, _, _ = make(game, clock, speaker=speaker)
    controller.askNow()
    assert speaker.played == []  # asked for: one is at the screen
    controller.later()
    clock.now = controller.scheduler.next_at
    controller._tick()
    assert controller.property("bubble")["mode"] == "question"
    assert speaker.played == ["bugle"]
    controller.later()
    controller.setCall("silent")
    clock.now = controller.scheduler.next_at
    controller._tick()
    assert controller.property("bubble")["mode"] == "question"
    assert speaker.played == ["bugle"]


def test_his_call_is_chosen_by_ear_and_kept(game: Game, tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"figure": [10, 20], "pace": 3, "call": ["bell"]}))
    speaker = Speaker()
    controller, _, _ = make(game, settings=Settings(path), speaker=speaker)
    assert controller.property("call") == "bugle"  # what is not a call is ignored
    assert controller.property("pace") == "regularly"
    controller.setCall("bell")
    assert speaker.played == ["bell"]  # heard at once
    controller.setCall("klaxon")
    controller.setCall("silent")
    assert speaker.played == ["bell"]
    again, _, _ = make(game, settings=Settings(path))
    assert again.property("call") == "silent"
    assert json.loads(path.read_text())["figure"] == [10, 20]


def test_how_often_he_asks_is_chosen_and_kept(game: Game, tmp_path: Path) -> None:
    fill(game)
    clock = Clock()
    path = tmp_path / "settings.json"
    controller, _, _ = make(game, clock, settings=Settings(path))
    controller.setPace("intensive")
    assert clock.now + 3 * 60 <= controller.scheduler.next_at <= clock.now + 5 * 60
    bubble = controller.property("bubble")
    assert bubble["title"] == "As you wish!"
    assert bubble["text"].startswith("A question every 3 to 5 min. The next one around ")
    controller.setPace("rarely")
    assert controller.property("bubble")["text"].startswith("2 or 3 questions a day.")
    controller.setPace("sometimes")
    assert controller.property("pace") == "rarely"
    controller.askNow()
    controller.setPace("often")  # not a word over a question
    assert controller.property("bubble")["mode"] == "question"
    controller.pauseWith("1h")
    controller.setPace("now-and-then")
    assert controller.property("bubble")["text"].endswith("once your break is over.")
    assert controller.scheduler.next_at >= clock.now + 3600
    again, _, _ = make(game, clock, settings=Settings(path))
    assert again.property("pace") == "now-and-then"
    assert again.scheduler.next_at >= clock.now + 45 * 60


def test_a_question_left_alone_goes_and_the_next_one_waits_for_the_pace(game: Game) -> None:
    fill(game)
    clock = Clock()
    controller, _, _ = make(game, clock)
    controller.setPace("rarely")  # hours 0 to 24 here: 2 or 3 a day is every 8 to 12 hours
    controller.askNow()
    controller._unanswered()
    assert controller.property("bubble")["mode"] == "hidden"
    assert controller.scheduler.next_at >= clock.now + 8 * 3600


def test_his_menu_sets_the_pace_and_lets_one_hear_every_call(game: Game) -> None:
    speaker = Speaker()
    controller, _, _ = make(game, speaker=speaker)
    tray = Tray(controller)
    assert [a.text() for a in tray.menu.actions()] == [
        "A question now",
        "Progress",
        "",
        "How often",
        "Sound",
        "",
        "A break…",
        "Resume",
        "",
        "Quit Tagnan",
    ]
    assert tray.paces["intensive"].text() == "Intensive training\tevery 3 to 5 min"
    assert [k for k, a in tray.paces.items() if a.isChecked()] == ["regularly"]
    tray.paces["rarely"].trigger()
    assert controller.property("pace") == "rarely"
    assert [k for k, a in tray.paces.items() if a.isChecked()] == ["rarely"]
    assert [k for k, a in tray.calls.items() if a.isChecked()] == ["bugle"]

    sounds = tray.calls["bell"].parent()
    assert isinstance(sounds, QMenu)
    sounds.popup(QPoint(100, 100))
    for key in ("bell", "lute"):
        centre = QPointF(sounds.actionGeometry(tray.calls[key]).center())
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            centre,
            QPointF(sounds.mapToGlobal(centre.toPoint())),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(sounds, release)
        assert sounds.isVisible()  # still open, to hear the next one
    assert speaker.played == ["bell", "lute"]
    assert controller.property("call") == "lute"
    assert [k for k, a in tray.calls.items() if a.isChecked()] == ["lute"]
    sounds.close()
