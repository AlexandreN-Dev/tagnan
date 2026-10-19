import os
from collections.abc import Callable
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tagnan.game import Game
from tagnan.ui.desktop import Settings
from tagnan.ui.menu import Menu
from tagnan.ui.updater import CHECK_EVERY, NEWS_KEY, UpdateClient, UpdateError, Updater
from tests.test_ui import fill, make

NEWS = ["A finished Gascon for grade 1, his inkwell back in the frame", "He moves slower"]


@pytest.fixture(scope="module", autouse=True)
def qt_app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    return app


class FakeClient(UpdateClient):
    """scripts/update as the window would hear it, answers set by each test."""

    def __init__(self, check: Any = None, apply: Any = None, here: Any = None) -> None:
        super().__init__(("scripts/update",))
        here = here or [{"ok": True, "head": "a1", "moved": False, "news": [], "setup": False}]
        object.__setattr__(self, "answers", {"check": check, "apply": apply, "here": here})
        object.__setattr__(self, "calls", [])
        object.__setattr__(self, "heres", [])  # the commit each `here` was asked from

    def call(self, action: str, timeout: float, *args: str) -> dict[str, Any]:
        answer = self.answers[action]  # type: ignore[attr-defined]
        if action == "here":  # his folder, answer after answer (the last one stays)
            self.heres.append(args)  # type: ignore[attr-defined]
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        else:
            self.calls.append(action)  # type: ignore[attr-defined]
        if isinstance(answer, Exception):
            raise answer
        assert isinstance(answer, dict)
        return answer


def at_once(work: Callable[[], None]) -> None:
    work()


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


def updater(
    client: UpdateClient | None, settings: Settings | None = None, clock: Any = None
) -> Updater:
    return Updater(client, settings or Settings(None), clock or Clock(), run=at_once)


def heard(signal: Any) -> list[Any]:
    got: list[Any] = []
    signal.connect(lambda *args: got.append(args))
    return got


def test_a_new_version_lights_his_update_row_then_one_click_takes_it() -> None:
    settings = Settings(None)
    client = FakeClient(
        check={"ok": True, "behind": 2, "news": NEWS},
        apply={"ok": True, "updated": True, "news": NEWS, "setup": False},
    )
    up = updater(client, settings)
    restarts = heard(up.restartRequested)
    assert up.row() == {
        "label": "Update",
        "value": "",
        "pill": False,
        "busy": False,
        "strong": False,
    }
    up.check()
    assert up.property("state") == "new"
    assert up.row() == {
        "label": "Update",
        "value": "New",
        "pill": True,
        "busy": False,
        "strong": True,
    }
    assert up.property("news") == NEWS
    up.activate()  # his menu's Update, now that there is a new version
    assert client.calls == ["check", "apply"]  # type: ignore[attr-defined]
    assert up.property("state") == "updating"
    assert up.row()["busy"] is True  # type: ignore[index]
    assert restarts == [(False,)]
    assert settings.get(NEWS_KEY)["news"] == NEWS  # for his bubble, once he is back


def test_the_window_is_made_again_when_its_pins_change() -> None:
    client = FakeClient(
        check={"ok": True, "behind": 1, "news": []},
        apply={"ok": True, "updated": True, "news": [], "setup": True},
    )
    up = updater(client)
    restarts = heard(up.restartRequested)
    up.check()
    up.activate()
    assert restarts == [(True,)]


def test_up_to_date_and_nothing_new_after_all() -> None:
    client = FakeClient(
        check={"ok": True, "behind": 0, "news": []},
        apply={"ok": True, "updated": False, "news": [], "setup": False},
    )
    up = updater(client)
    restarts = heard(up.restartRequested)
    up.check()
    assert up.row()["value"] == "Up to date"  # type: ignore[index]
    up.activate()  # up to date: looks again
    assert client.calls == ["check", "check"]  # type: ignore[attr-defined]
    up.apply()  # GitHub had nothing more by the time he asked
    assert up.property("state") == "uptodate"
    assert restarts == []


def test_he_says_why_only_when_asked() -> None:
    client = FakeClient(check=UpdateError("cannot start scripts/update: no wsl.exe"))
    up = updater(client)
    said = heard(up.failed)
    up.check(asked=False)  # the morning look: no word if it fails
    assert up.property("state") == "failed"
    assert up.row()["value"] == "Try again"  # type: ignore[index]
    assert said == []
    up.activate()  # from his menu
    assert said == [
        (
            "No update for now",
            "I couldn't reach my updates: cannot start scripts/update: no wsl.exe.",
        )
    ]
    refusal = {
        "ok": False,
        "reason": "local-changes",
        "message": "My files have changes of their own.",
    }
    client.answers.update(check={"ok": True, "behind": 1, "news": []}, apply=refusal)  # type: ignore[attr-defined]
    up.check()
    up.activate()
    assert up.property("state") == "failed"
    assert said[-1] == ("No update for now", "My files have changes of their own.")


def test_he_looks_again_about_once_a_day() -> None:
    clock = Clock()
    client = FakeClient(check={"ok": True, "behind": 0, "news": []})
    up = updater(client, clock=clock)
    up.check()
    clock.now += CHECK_EVERY / 2
    up._maybe_check()
    assert client.calls == ["check"]  # type: ignore[attr-defined]
    clock.now += CHECK_EVERY / 2
    up._maybe_check()
    assert client.calls == ["check", "check"]  # type: ignore[attr-defined]


def test_without_updates_there_is_no_row() -> None:
    up = updater(None)
    assert up.row() is None
    up.activate()
    assert up.property("state") == "idle"


def test_his_menu_shows_update_and_stays_open_while_it_runs(game: Game) -> None:
    fill(game)
    controller, _, _ = make(game)
    client = FakeClient(
        check={"ok": True, "behind": 1, "news": NEWS},
        apply={"ok": True, "updated": True, "news": NEWS, "setup": False},
    )
    up = updater(client)
    menu = Menu(controller, up)
    menu.openAt(10, 10)
    assert menu.property("content")["update"]["label"] == "Update"
    assert menu.run("update") is True  # it says how it goes, the menu open
    assert menu.property("shown") is True
    assert menu.property("content")["update"]["pill"] is True
    assert [s["action"] for s in menu.suggest("upd")] == ["update"]
    assert "update" not in [s["action"] for s in Menu(controller).suggest("upd")]
    restarts = heard(up.restartRequested)
    menu.run("update")
    assert restarts == [(False,)]


def test_back_from_an_update_he_says_what_changed(game: Game) -> None:
    fill(game)
    settings = Settings(None)
    settings.set(NEWS_KEY, {"news": NEWS, "at": 1.0})
    controller, _, _ = make(game, settings=settings)
    controller.start()
    bubble = controller.property("bubble")
    assert (bubble["mode"], bubble["title"], bubble["button"]) == (
        "message",
        "Freshly inked!",
        "Splendid!",
    )
    assert bubble["text"] == "I'm up to date. What's new:\n· " + "\n· ".join(NEWS)
    assert settings.get(NEWS_KEY) is None  # once


def test_restart_lights_up_when_his_folder_holds_what_he_does_not_run(game: Game) -> None:
    fill(game)
    controller, _, _ = make(game)
    clock = Clock()
    settings = Settings(None)
    news = ["His call's volume, set by ear under his sounds"]
    client = FakeClient(
        here=[
            {"ok": True, "head": "a1", "moved": False, "news": [], "setup": False},
            {"ok": True, "head": "b2", "moved": True, "news": news, "setup": True},
        ]
    )
    up = updater(client, settings, clock)
    menu = Menu(controller, up)
    up.start()  # learns the commit he runs
    assert client.heres == [()]  # type: ignore[attr-defined]
    row = {"label": "Restart Tagnan", "value": "", "pill": False}
    assert menu.property("content")["restart"] == row
    menu.openAt(10, 10)  # opened at once: not asked again
    assert len(client.heres) == 1  # type: ignore[attr-defined]
    menu.close()
    clock.now += 60
    menu.openAt(10, 10)  # a commit since: gold
    assert client.heres[-1] == ("a1",)  # type: ignore[attr-defined]
    assert menu.property("content")["restart"] == {**row, "value": "New", "pill": True}
    assert [s["action"] for s in menu.suggest("restart")] == ["restart"]
    restarts = heard(up.restartRequested)
    assert menu.run("restart") is False
    assert menu.property("shown") is False
    assert restarts == [(True,)]  # its pins changed: his environment again
    assert settings.get(NEWS_KEY)["news"] == news  # he says what changed, once back
    assert Menu(controller).property("content")["restart"] is None
    assert "restart" not in [s["action"] for s in Menu(controller).suggest("restart")]


def test_restart_without_a_folder_to_read_still_works() -> None:
    client = FakeClient(here=[UpdateError("no wsl.exe")])
    up = updater(client)
    restarts = heard(up.restartRequested)
    up.start()
    assert up.restart_row() == {"label": "Restart Tagnan", "value": "", "pill": False}
    up.restart()
    assert restarts == [(False,)]


def test_his_menu_draws_the_update_row(game: Game) -> None:
    from PySide6.QtCore import QUrl, qInstallMessageHandler
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow

    from tagnan.ui.__main__ import QML_DIR
    from tagnan.ui.images import LayerImages
    from tagnan.ui.placement import Placement

    fill(game)
    controller, _, animator = make(game)
    client = FakeClient(check={"ok": True, "behind": 1, "news": NEWS})
    up = updater(client)
    menu = Menu(controller, up)
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
        popup: Any = next(
            w for w in window.findChildren(QQuickWindow) if w.title() == "Tagnan — menu"
        )
        menu.openAt(400, 300)
        QApplication.processEvents()

        def update_row() -> dict[str, Any]:
            rows = popup.property("rows").toVariant()
            assert rows[-1]["action"] == "quit"  # Quit Tagnan stays last
            assert rows[-2]["action"] == "restart"  # Restart just above
            return next(r for r in rows if r.get("action") == "update")

        assert update_row()["value"] == ""
        up.check()
        QApplication.processEvents()
        assert (update_row()["value"], update_row()["pill"]) == ("New", True)
        up._set("updating")
        QApplication.processEvents()
        assert (update_row()["label"], update_row()["busy"], update_row()["icon"]) == (
            "Updating…",
            True,
            "spinner",
        )
        menu.close()
        window.close()
        del engine
    finally:
        qInstallMessageHandler(None)
    assert not [w for w in warnings if "TagnanMenu" in w or "Bubble" in w], warnings
