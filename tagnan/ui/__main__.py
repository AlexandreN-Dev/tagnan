"""Start Tagnan's window: python -m tagnan.ui [--distro NAME --repo PATH] [--config PATH].

On Windows, scripts/tagnan-ui launches it from WSL and tells it where the brain lives (the WSL
distribution and the repository's path inside it); on macOS, and in WSL itself for
development, the brain is called directly.
"""

import argparse
import logging
import logging.handlers
import os
import random
import signal
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import (
    QLockFile,
    QMessageLogContext,
    QObject,
    QPoint,
    QRect,
    QTimer,
    QtMsgType,
    QUrl,
    qInstallMessageHandler,
)
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from tagnan import blueprint as blueprints
from tagnan import config as configs
from tagnan import progress as rules
from tagnan.brain_client import BrainClient
from tagnan.game import Game
from tagnan.paths import config_file, state_dir
from tagnan.scheduler import Scheduler
from tagnan.store import Store
from tagnan.ui.animation.rig import WOBBLE_RATE, Rig
from tagnan.ui.animator import Animator
from tagnan.ui.controller import Controller
from tagnan.ui.desktop import Settings
from tagnan.ui.images import LayerImages
from tagnan.ui.menu import Menu
from tagnan.ui.outside import OutsideClicks
from tagnan.ui.placement import Placement
from tagnan.ui.sounds import Sounds
from tagnan.ui.tray import Tray
from tagnan.ui.updater import UpdateClient, Updater
from tagnan.ui.worker import BrainWorker

QML_DIR = Path(__file__).resolve().parent / "qml"
EDGE_MARGIN = 24  # from the screen's right edge to Tagnan's window
FOOT_MARGIN = 0  # from the taskbar to his window's bottom


def forward_qt_messages(kind: QtMsgType, context: QMessageLogContext, message: str) -> None:
    level = logging.INFO if kind in (QtMsgType.QtDebugMsg, QtMsgType.QtInfoMsg) else logging.WARNING
    logging.getLogger("qt").log(level, message)


def place(window: QQuickWindow, settings: Settings) -> None:
    """Where he was left, if that is still on a screen; else bottom right, above the taskbar."""
    saved = settings.get("figure")
    app = QGuiApplication.instance()
    screens = app.screens() if isinstance(app, QGuiApplication) else []
    if isinstance(saved, list) and len(saved) == 2:
        centre = QPoint(int(saved[0]) + window.width() // 2, int(saved[1]) + window.height() // 2)
        if any(s.availableGeometry().contains(centre) for s in screens):
            window.setPosition(int(saved[0]), int(saved[1]))
            return
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return
    area = screen.availableGeometry()
    window.setPosition(
        area.right() + 1 - EDGE_MARGIN - window.width(),
        area.bottom() + 1 - FOOT_MARGIN - window.height(),
    )


def setup_logging() -> None:
    folder = state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    handlers.append(
        logging.handlers.RotatingFileHandler(
            folder / "tagnan.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
        )
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def compose(window: QQuickWindow) -> QImage:
    """Tagnan's window and, when shown, his bubble's, as they stand on the screen: only their
    own pixels, nothing else of the screen."""
    windows = [window] + [w for w in window.findChildren(QQuickWindow) if w.isVisible()]
    area = QRect()
    for w in windows:
        logging.info("snapshot: %s at %s, ratio %s", w.title(), w.geometry(), w.devicePixelRatio())
        area = area.united(w.geometry())
    ratio = window.devicePixelRatio()
    image = QImage(
        round(area.width() * ratio), round(area.height() * ratio), QImage.Format.Format_ARGB32
    )
    image.setDevicePixelRatio(ratio)  # drawn in logical units, as the grabs are
    image.fill(0)
    painter = QPainter(image)
    for w in windows:
        offset = w.geometry().topLeft() - area.topLeft()
        grab = w.grabWindow()
        grab.setDevicePixelRatio(w.devicePixelRatio())  # not every platform marks it
        painter.drawImage(offset, grab)
    painter.end()
    return image


def demo(controller: Controller, what: str) -> None:
    """Development: show a bubble at once (snapshots)."""
    if what.startswith("question") or what.startswith("result"):
        controller.askNow()
        question = controller._current
        if what != "question" and question is not None:
            right = list(question.answers)
            wrong = [i for i in range(len(question.choices)) if i not in right][: len(right)]
            controller.answer(right if what == "result-right" else wrong)
    elif what == "stats":
        controller.showStats()
    elif what == "quip":
        controller.animator.tap()
    elif what == "pause":
        controller.showPause()
    elif what == "subject":
        controller.showSubject()
    elif what == "menu":
        controller.showMenu()
    elif what == "promotion":  # his evolution only: nothing saved
        before = min(controller.property("stage"), len(rules.GRADES) - 2)
        controller._set_stage(before)
        grade = rules.GRADES[before + 1]
        controller._show(
            {
                "mode": "result",
                "correct": True,
                "title": "Touché!",
                "chosen": [],
                "right": "",
                "explanation": "A right answer that takes him over the line.",
                "reference": "",
                "points": f"+14 points · {grade.threshold + 3} in all · streak of 4",
                "news": f"Promotion! Tagnan is now a {grade.name}: {grade.look}.",
                "promoted": True,
                "rank": grade.name,
            }
        )
        controller._promote(before, before + 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Tagnan's window")
    parser.add_argument("--distro", help="the brain's WSL distribution (from Windows)")
    parser.add_argument("--repo", help="the repository's path in WSL (from Windows)")
    parser.add_argument("--config", type=Path, default=config_file())
    parser.add_argument("--db", type=Path, default=state_dir() / "tagnan.db")
    parser.add_argument("--reduced-motion", action="store_true", help="reduced motion")
    parser.add_argument(
        "--snapshot", type=Path, help="development: picture of the window, then quit"
    )
    parser.add_argument("--snapshot-delay", type=int, default=2500, help="in milliseconds")
    parser.add_argument(
        "--demo",
        choices=[
            "question",
            "result-right",
            "result-wrong",
            "stats",
            "quip",
            "pause",
            "subject",
            "menu",
            "promotion",
        ],
        help="development: show a bubble right away",
    )
    parser.add_argument("--grade", type=int, choices=range(6), help="development: force a grade")
    parser.add_argument(
        "--measure-cpu", type=float, metavar="SECONDS", help="measure the CPU, then quit"
    )
    parser.add_argument("--fps", type=int, default=30, help="development: frames per second")
    parser.add_argument("--window-size", type=int, nargs=2, help="development: window size")
    parser.add_argument(
        "--ripple-rate",
        type=int,
        default=WOBBLE_RATE,
        help="development: ink outlines per second of his time",
    )
    args = parser.parse_args()

    setup_logging()
    qInstallMessageHandler(forward_qt_messages)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Tagnan")
    app.setQuitOnLastWindowClosed(False)
    if sys.platform == "darwin":
        from tagnan.ui import macos

        macos.hide_from_dock()
    development = bool(args.snapshot or args.measure_cpu or args.demo)
    lock = QLockFile(str(Path(tempfile.gettempdir()) / "tagnan-ui.lock"))
    if not development and not lock.tryLock(0):
        logging.info("a Tagnan window is already open: nothing to do")
        return 0

    try:
        cfg = configs.load(args.config)
        bp = blueprints.load(cfg.exam)
    except ValueError as error:
        logging.error("%s", error)
        return 1
    rng = random.Random()  # noqa: S311 - questions and interjections, not secrets
    store = Store(args.db)
    game = Game(store, bp, rng)
    if args.grade is not None:
        from dataclasses import replace

        store.save_progress(game.exam, replace(game.progress, grade=args.grade))
    scheduler = Scheduler(cfg.rhythm, rng, time.time())
    client = (
        BrainClient.through_wsl(args.distro, args.repo)
        if args.distro and args.repo
        else BrainClient.local()
    )
    worker = BrainWorker(client)
    worker.offline = args.snapshot is not None or args.measure_cpu is not None
    rig = Rig(rng, reduced_motion=args.reduced_motion)
    rig.wobble_rate = max(1, args.ripple_rate)
    animator = Animator(rig, frame_ms=round(1000 / max(1, args.fps)))
    settings = Settings(state_dir() / "settings.json")
    controller = Controller(
        game,
        scheduler,
        worker,
        animator,
        rng,
        settings=settings,
        sounds=Sounds(),
        model=cfg.brain.model,
    )
    placement = Placement()
    # His updates: from GitHub, through scripts/update; none in a development snapshot or measure.
    updates = (
        UpdateClient.through_wsl(args.distro, args.repo)
        if args.distro and args.repo
        else UpdateClient.local()
    )
    updater = Updater(None if development else updates, settings)
    menu = Menu(controller, updater)
    tray = Tray(controller, menu)

    def leave(code: int = 0) -> None:
        """Every way out ends the process at once: Qt's own teardown waits for its render
        thread, which a locked session freezes (Dartt learnt it the hard way)."""
        qInstallMessageHandler(None)
        store.close()
        logging.shutdown()
        os._exit(code)

    controller.quitRequested.connect(leave)

    def restart(setup: bool) -> None:
        """Updated: scripts/update restart starts him again once this window is gone."""
        lock.unlock()
        try:
            updates.restart(setup)
        except OSError as error:
            logging.warning("cannot start again by myself: %s", error)
            lock.tryLock(0)
            controller.say("Updated!", "Quit me and start me again to see what's new.")
            return
        leave()

    updater.restartRequested.connect(restart)
    updater.failed.connect(controller.say)
    QQuickStyle.setStyle("Basic")  # the same look everywhere, no native style
    engine = QQmlApplicationEngine()
    engine.addImageProvider("tagnan", LayerImages())
    engine.setInitialProperties(
        {"controller": controller, "animator": animator, "placement": placement, "menu": menu}
    )
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    roots = engine.rootObjects()
    if not roots or not isinstance(roots[0], QQuickWindow):
        logging.error("the window did not load")
        return 1
    window: QQuickWindow = roots[0]
    if args.window_size:
        window.resize(*args.window_size)
    place(window, settings)
    window.show()
    if sys.platform == "darwin":
        for each in (window, *window.findChildren(QQuickWindow)):
            macos.join_all_spaces(int(each.winId()))

    # A click outside Tagnan and his bubble closes the bubble (not a question).
    def inside(point: QPoint) -> bool:
        windows = [window, *window.findChildren(QQuickWindow)]
        return any(w.isVisible() and w.geometry().contains(point) for w in windows)

    outside = OutsideClicks(inside)
    outside.clickedOutside.connect(controller.dismiss)
    controller.bubbleChanged.connect(lambda: outside.watch(controller.closes_on_outside()))

    save_timer = QTimer()
    save_timer.setSingleShot(True)
    save_timer.timeout.connect(lambda: settings.set("figure", [window.x(), window.y()]))
    window.xChanged.connect(lambda: save_timer.start(800))
    window.yChanged.connect(lambda: save_timer.start(800))

    animator.start()
    controller.start()
    updater.start()
    logging.info(
        "Tagnan is up (grade %d, %d fresh questions)",
        game.progress.grade,
        store.fresh_count(game.exam),
    )

    if args.demo:
        QTimer.singleShot(300, lambda: demo(controller, args.demo))
    if args.snapshot is not None:
        snapshot: Path = args.snapshot

        def save() -> None:
            compose(window).save(str(snapshot))
            leave()

        QTimer.singleShot(args.snapshot_delay, save)
    if args.measure_cpu:
        # After 3 s of start-up (QML, layers), as Dartt measures it.
        QTimer.singleShot(3000, lambda: measure(args.measure_cpu, leave))

    signal.signal(signal.SIGINT, lambda *_: leave())
    heartbeat = QTimer()  # lets Python see Ctrl+C now and then
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(250)
    # What QML holds, kept alive here until the end.
    keep: list[QObject] = [tray, menu, placement, outside, animator, controller, worker, updater]
    app.exec()
    del keep
    leave()
    return 0


def measure(seconds: float, leave: Callable[[int], None]) -> None:
    """CPU used by the whole window process, as Task Manager counts it."""
    start_cpu, start_wall = time.process_time(), time.monotonic()

    def report() -> None:
        cpu, wall = time.process_time() - start_cpu, time.monotonic() - start_wall
        cores = os.cpu_count() or 1
        print(
            f"Window CPU over {wall:.0f} s: {100 * cpu / wall / cores:.2f} % of the machine "
            f"({100 * cpu / wall:.1f} % of one core)",
            flush=True,
        )
        leave(0)

    QTimer.singleShot(round(seconds * 1000), report)


if __name__ == "__main__":
    sys.exit(main())
