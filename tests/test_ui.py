import json
import os
import random
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

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
from tagnan.ui.menu import Menu, menu_position
from tagnan.ui.placement import Box
from tagnan.ui.sounds import Sounds
from tagnan.ui.tray import Tray
from tagnan.ui.worker import BrainWorker
from tests.conftest import pottery_data, pottery_question, question_data

NOW = 1_800_000_000.0


@pytest.fixture(scope="module", autouse=True)
def qt_app() -> QApplication:
    app = QApplication.instance() or QApplication([])  # widgets: his tray icon
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
        self.plans: list[str] = []

    def generate(self, request: dict[str, Any]) -> bool:
        self.requests.append(request)
        self.generating = True
        return True

    def explain(self, question_id: int, request: dict[str, Any]) -> None:
        self.explanations.append(question_id)

    def plan(self, words: str) -> bool:
        self.plans.append(words)
        self.planning = words
        return True


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


def test_the_subject_is_chosen_kept_and_written_for(game: Game) -> None:
    fill(game)
    controller, worker, _ = make(game)
    controller.showSubject()
    bubble = controller.property("bubble")
    assert bubble["mode"] == "subject"
    assert bubble["choices"][0] == {"label": "The whole exam", "key": ""}
    assert bubble["choices"][3]["key"] == "domain:3"
    assert bubble["current"] == ""
    assert controller.previewSubject("domain 9")["ok"] is False
    assert controller.previewSubject("rag") == {"ok": True, "text": "Questions on rag."}
    assert controller.subjectWith("  ") is False
    assert controller.subjectWith("RAG") is True
    assert controller.property("subject") == "RAG (AIF-C01)"
    assert "a few minutes" in controller.property("bubble")["text"]
    request = worker.requests[-1]
    assert request["subject"] == "RAG"
    controller.askNow()  # nothing on RAG yet
    assert "questions on RAG" in controller.property("bubble")["text"]
    # A batch written for the subject left behind lands with its own subject.
    worker.generating = False
    worker.batchReady.emit({"questions": [question_data(topic="old")], "subject": ""})
    assert game.fresh_count() == 0
    worker.generating = False
    batch = [question_data(topic=f"rag {i}") for i in range(10)]
    worker.batchReady.emit({"questions": batch, "subject": "RAG"})
    assert game.fresh_count() == 10
    controller.askNow()
    assert controller.property("bubble")["meta"] == "RAG · Domain 3"
    controller.dismiss()
    controller.showSubject()
    assert controller.property("bubble")["choices"][-1] == {"label": "RAG", "key": "RAG"}
    controller.setSubject("rag")
    assert controller.property("bubble")["text"].startswith("We're already on RAG")
    controller.setSubject("")
    assert game.subject.whole
    assert game.fresh_count() == 17


def test_his_menu_says_where_he_stands(game: Game) -> None:
    fill(game)
    controller, _, _ = make(game)
    menu = Menu(controller)
    assert menu.property("shown") is False
    changes: list[int] = []
    menu.changed.connect(lambda: changes.append(1))
    controller.menuRequested.emit(300, 200)
    assert menu.property("shown") is True
    c = menu.property("content")
    assert (c["grade"], c["stage"], c["share"]) == ("Inkwell", 0, 0.0)
    assert c["points"] == "0 of 250 points to Gascon"
    assert c["next"].startswith("next ~")
    assert (c["subject"], c["pace"], c["paceKey"], c["call"]) == (
        "AIF-C01",
        "Regularly",
        "regularly",
        "Bugle call",
    )
    assert c["paces"][0]["key"] == "rarely"
    assert c["calls"][-1] == {"key": "silent", "name": "Silent"}
    controller.setSubject("domain:2")
    assert menu.property("content")["subject"] == "Domain 2 · Fundamentals of Generative AI"
    assert changes  # QML hears of it while open
    menu.close()
    assert menu.property("shown") is False


def test_his_menu_opens_at_the_pointer_and_stays_on_the_screen() -> None:
    area = Box(0, 0, 1920, 1040)
    assert menu_position((100, 100), (300, 400), area) == (100, 100)
    # Near his corner, bottom right: up and to the left of the pointer.
    assert menu_position((1800, 1000), (300, 400), area) == (1500, 600)
    assert menu_position((5, 1030), (300, 1200), area) == (8, 8)


def test_his_menu_runs_its_commands(game: Game) -> None:
    fill(game)
    speaker = Speaker()
    controller, worker, _ = make(game, speaker=speaker)
    menu = Menu(controller)
    menu.openAt(10, 10)
    assert menu.run("pace:rarely") is False
    assert controller.property("pace") == "rarely"
    assert menu.property("shown") is False
    # A call is heard, then the next, and the menu stays open meanwhile.
    menu.openAt(10, 10)
    assert menu.run("call:bell") is True
    assert menu.run("call:lute") is True
    assert menu.property("shown") is True
    assert speaker.played == ["bell", "lute"]
    assert controller.property("call") == "lute"
    menu.run("stats")
    assert controller.property("bubble")["mode"] == "stats"
    menu.run("pause:1h")
    assert controller.property("paused") is True
    menu.openAt(10, 10)
    assert menu.property("content")["paused"] is True
    assert menu.property("content")["next"].startswith("until ")
    menu.run("resume")
    assert controller.property("paused") is False
    menu.run("pause")  # no words: the break bubble
    assert controller.property("bubble")["mode"] == "pause"
    menu.run("learn:pottery")
    assert worker.plans == ["pottery"]
    menu.run("focus:RAG")
    assert controller.property("subject") == "RAG (AIF-C01)"
    quits: list[int] = []
    controller.quitRequested.connect(lambda: quits.append(1))
    menu.run("quit")
    assert quits == [1]


def test_a_few_words_typed_in_his_menu_find_the_command(game: Game) -> None:
    controller, _, _ = make(game)
    menu = Menu(controller)

    def actions(text: str) -> list[str]:
        return [s["action"] for s in menu.suggest(text)]

    assert menu.suggest("  ") == []
    first = menu.suggest("break 45")[0]
    assert first["action"] == "pause:45"
    assert first["label"] == "A break of 45 min"
    assert first["sub"].startswith("Back at ")
    assert actions("1h30")[0] == "pause:1h30"
    assert actions("often")[0] == "pace:often"
    assert len(actions("how often")) == 5
    assert actions("bell") == ["call:bell"]
    assert "call:silent" in actions("mute")
    assert actions("learn pottery")[0] == "learn:pottery"
    assert actions("focus RAG")[0] == "focus:RAG"
    assert actions("quest")[0] == "ask"
    assert "quit" in actions("quit")
    assert "resume" not in actions("resume")  # not on a break
    controller.pauseWith("1h")
    assert "resume" in actions("resume")
    assert actions("zzz") == []


def test_his_tray_icon_opens_his_menu(game: Game) -> None:
    fill(game)
    controller, _, _ = make(game)
    menu = Menu(controller)
    tray = Tray(controller, menu)
    tray._activated(QSystemTrayIcon.ActivationReason.Context)
    assert menu.property("shown") is True
    tray._activated(QSystemTrayIcon.ActivationReason.Trigger)
    assert controller.property("bubble")["mode"] == "stats"
    assert tray.tooltip().startswith("Tagnan · Inkwell · 0 points")


def test_anything_can_be_learned_each_with_its_own_grade(game: Game) -> None:
    fill(game)
    game.store.save_progress(game.exam, Progress(points=1000, grade=2))
    controller, worker, _ = make(game)
    assert controller.property("stage") == 2
    controller.showSubject()
    bubble = controller.property("bubble")
    assert bubble["courses"][0] == {"label": "AWS Certified AI Practitioner", "key": "aif-c01"}
    assert bubble["course"] == "aif-c01"
    back = controller.previewCourse("AIF-C01")
    assert back == {"ok": True, "text": "Back to AWS Certified AI Practitioner."}
    assert controller.previewCourse("pottery")["text"].startswith("I'll draw up a course")
    assert controller.previewCourse("x" * 121)["ok"] is False
    assert controller.learnWith("Pottery!") is True
    assert worker.plans == ["Pottery"]
    assert "drawing up" in controller.property("bubble")["text"]
    assert game.exam == "aif-c01"  # until the course is drawn up

    # A course drawn up while a question waits for its answer: it waits for the bubble to close.
    worker.generating = False
    controller.askNow()
    worker.planning = ""
    worker.planned.emit("Pottery", {"understood": True, "course": pottery_data()})
    assert controller.property("bubble")["mode"] == "question"
    assert game.exam == "aif-c01"
    controller.later()
    assert game.exam == "pottery"
    assert controller.property("stage") == 0  # a grade of its own
    assert controller.property("subject") == "Pottery"
    text = controller.property("bubble")["text"]
    assert "Your course is ready: Pottery. 1. Clay bodies; 2. Glazes and firing." in text
    assert worker.requests[-1]["course"]["name"] == "Pottery"

    # A batch written for the course left behind lands in it.
    worker.batchReady.emit({"questions": [question_data(topic="late")], "course": "aif-c01"})
    assert game.fresh_count() == 0
    worker.generating = False
    batch = [pottery_question(topic=f"firing {i}") for i in range(10)]
    worker.batchReady.emit({"questions": batch, "course": "pottery"})
    assert game.fresh_count() == 10
    controller.dismiss()
    controller.askNow()
    assert controller.property("bubble")["meta"] == "Pottery · Domain 2 · Glazes and firing"
    asked = controller._current
    assert asked is not None
    controller.answer([asked.answers[0]])
    assert game.progress.points > 0

    # Back to AWS: its grade comes back.
    controller.dismiss()
    controller.showSubject()
    keys = [c["key"] for c in controller.property("bubble")["courses"]]
    assert keys == ["pottery", "aif-c01"]
    assert controller.learnWith("aif-c01") is True
    assert game.exam == "aif-c01"
    assert controller.property("stage") == 2
    assert game.fresh_count() == 6 + 1  # fill()'s questions and the late one
    controller.setCourse("pottery")
    assert controller.property("stage") == 0


def test_words_that_cannot_be_taught_are_said_so(game: Game) -> None:
    fill(game)
    controller, worker, _ = make(game)
    controller.learnWith("stuff")
    worker.planning = ""
    worker.planned.emit("stuff", {"understood": False, "message": "Name a subject, please."})
    assert controller.property("bubble")["text"] == "A course on stuff? Name a subject, please."
    worker.planFailed.emit("pottery", "claude did not answer within 600 s")
    assert "couldn't draw up a course on pottery" in controller.property("bubble")["text"]
    assert game.exam == "aif-c01"


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


def test_his_menu_loads_in_the_window_and_answers_the_keyboard(game: Game) -> None:
    from PySide6.QtCore import QObject, QUrl, qInstallMessageHandler
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow

    from tagnan.ui.__main__ import QML_DIR
    from tagnan.ui.images import LayerImages
    from tagnan.ui.placement import Placement

    fill(game)
    controller, _, animator = make(game)
    menu = Menu(controller)
    warnings: list[str] = []
    qInstallMessageHandler(lambda _kind, _context, message: warnings.append(message))
    try:
        engine = QQmlApplicationEngine()
        engine.addImageProvider("tagnan", LayerImages())
        placement = Placement()
        engine.setInitialProperties(
            {"controller": controller, "animator": animator, "placement": placement, "menu": menu}
        )
        engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
        window = engine.rootObjects()[0]
        assert isinstance(window, QQuickWindow)
        window.show()
        popup: Any = next(
            w for w in window.findChildren(QQuickWindow) if w.title() == "Tagnan — menu"
        )
        menu.openAt(400, 300)
        QApplication.processEvents()
        assert popup.isVisible()
        assert popup.property("current") == 0
        # The mouse takes the row it moves onto; only one row is lit, and the highlight goes
        # with it.
        from PySide6.QtCore import QPoint
        from PySide6.QtTest import QTest

        def items(item: QQuickItem) -> list[QQuickItem]:
            return [item] + [d for child in item.childItems() for d in items(child)]

        def row_centre(index: int) -> QPoint:
            row = next(i for i in items(popup.contentItem()) if i.objectName() == f"row-{index}")
            centre = row.mapToScene(row.boundingRect().center())
            return QPoint(round(centre.x()), round(centre.y()))

        rows = popup.property("rows").toVariant()
        progress = next(i for i, r in enumerate(rows) if r.get("action") == "stats")
        subject = next(i for i, r in enumerate(rows) if r.get("action") == "subject")
        QTest.mouseMove(popup, row_centre(progress))
        QTest.mouseMove(popup, row_centre(progress) + QPoint(3, 0))
        assert popup.property("current") == progress
        QTest.mouseMove(popup, row_centre(subject))
        assert popup.property("current") == subject
        # Rows made anew under the still pointer, as one types, leave the first one lit.
        popup.findChild(QObject, "field").setProperty("text", "how often")
        assert popup.property("current") == 0
        popup.findChild(QObject, "field").setProperty("text", "")
        popup.openSub("pace", 4)
        assert popup.property("sub") == "pace"
        field = popup.findChild(QObject, "field")
        field.setProperty("text", "bell")
        assert popup.property("sub") == ""  # typing closes the list
        assert [r["action"] for r in popup.property("rows").toVariant()] == ["call:bell"]
        popup.activate(0)
        assert controller.property("call") == "bell"
        menu.close()
        QApplication.processEvents()
        assert not popup.isVisible()
        window.close()
        del engine  # before the objects it shows
    finally:
        qInstallMessageHandler(None)
    assert [w for w in warnings if "qml" in w.casefold()] == []
