"""Runs Tagnan's rig 30 times a second and hands the pose to QML, as Dartt's animator does."""

import math
import time
from functools import lru_cache
from typing import Any

from PySide6.QtCore import Property, QObject, QPointF, QTimer, Signal, Slot
from PySide6.QtGui import QCursor

from tagnan import art
from tagnan.ui.animation.rig import REST_POSE, Pose, Rig

FRAME_MS = 33  # about 30 frames per second
POINTER_JITTER_PX = 2


def ripple(wobble: float) -> float:
    """The ripple's phase, brought back within one turn: the rig steps it 15 times a turn, so the
    caches below hold every outline after the first second."""
    return round(wobble % (2 * math.pi), 4)


@lru_cache(maxsize=512)
def outline(stage: int, phase: float) -> str:
    return art.blob_path(stage, phase)


@lru_cache(maxsize=512)
def shading(stage: int, phase: float) -> tuple[str, str, str]:
    """The ink's shaded side, lit band and lit edge: the inkwell's (its meniscus, a line to
    stroke) at grade 0, the Gascon's (his rim of light, a crescent to fill) at grade 1; none at
    the others."""
    if stage == 0:
        paths = art.inkwell_shading(phase)
        return paths["shade"], paths["light"], paths["meniscus"]
    if stage == 1:
        paths = art.splash_shading(phase)
        return paths["shade"], paths["light"], paths["rim"]
    return "", "", ""


@lru_cache(maxsize=512)
def drip_tops(stage: int, phase: float) -> list[float]:
    return art.drip_tops(stage, phase)


def _pose_property(name: str, kind: type, notify: Signal) -> Any:
    def getter(self: "Animator") -> object:
        return getattr(self._pose, name)

    return Property(kind, getter, notify=notify)


class Animator(QObject):
    poseChanged = Signal()
    outlineChanged = Signal()
    stageChanged = Signal()
    moodChanged = Signal()
    tapped = Signal(str)  # the tap's mood: wink, annoyed or sulk

    def __init__(self, rig: Rig | None = None, stage: int = 0, frame_ms: int = FRAME_MS) -> None:
        super().__init__()
        self._rig = rig or Rig()
        self._rig.set_stage(stage)
        self._pose: Pose = REST_POSE
        self._outline = outline(stage, 0.0)
        self._shading = shading(stage, 0.0)
        self._drip_tops = drip_tops(stage, 0.0)
        self._eyes: QPointF | None = None
        self._cursor: QPointF | None = None
        self._last = time.monotonic()
        self._timer = QTimer(self)
        self._frame_ms = frame_ms
        self._timer.setInterval(frame_ms)
        self._timer.timeout.connect(self._frame)

    def start(self) -> None:
        self._last = time.monotonic()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def advance(self, seconds: float) -> None:
        """Development: step the rig as if this much time had passed (snapshots, tests)."""
        while seconds > 0:
            self._apply(self._rig.step(min(seconds, self._frame_ms / 1000)))
            seconds -= self._frame_ms / 1000

    # --- Inputs from the window -------------------------------------------------------------

    def set_stage(self, stage: int) -> None:
        self._set_stage(stage)

    def set_mood(self, mood: str) -> None:
        self._set_mood(mood)

    def mood_name(self) -> str:
        return self._rig.mood

    def reduced_motion(self) -> bool:
        return self._rig.reduced_motion

    def _get_stage(self) -> int:
        return self._rig.stage

    def _set_stage(self, stage: int) -> None:
        if stage != self._rig.stage:
            self._rig.set_stage(stage)
            self._outline = outline(stage, ripple(self._pose.wobble))
            self._shading = shading(stage, ripple(self._pose.wobble))
            self._drip_tops = drip_tops(stage, ripple(self._pose.wobble))
            self.stageChanged.emit()
            self.outlineChanged.emit()

    stage = Property(int, _get_stage, _set_stage, notify=stageChanged)

    def _get_mood(self) -> str:
        return self._rig.mood

    def _set_mood(self, mood: str) -> None:
        if mood != self._rig.mood:
            self._rig.set_mood(mood)
            self.moodChanged.emit()

    mood = Property(str, _get_mood, _set_mood, notify=moodChanged)

    @Slot()
    def tap(self) -> None:
        self.tapped.emit(self._rig.tap().value)

    @Slot(float, float)
    def setEyes(self, x: float, y: float) -> None:
        """Where his eyes are on the screen (global coordinates), to look at the pointer."""
        self._eyes = QPointF(x, y)

    @Slot(str)
    def idle(self, kind: str) -> None:
        self._rig.idle(kind)

    # --- Frames -----------------------------------------------------------------------------

    def _frame(self) -> None:
        now = time.monotonic()
        dt, self._last = now - self._last, now
        if self._eyes is not None:
            cursor = QPointF(QCursor.pos())
            if (
                self._cursor is None
                or (cursor - self._cursor).manhattanLength() > POINTER_JITTER_PX
            ):
                self._cursor = cursor
                self._rig.look_at(cursor.x() - self._eyes.x(), cursor.y() - self._eyes.y())
        self._apply(self._rig.step(dt))

    def _apply(self, pose: Pose) -> None:
        wobble_changed = pose.wobble != self._pose.wobble
        self._pose = pose
        self.poseChanged.emit()
        if wobble_changed:
            phase = ripple(pose.wobble)
            self._outline = outline(self._rig.stage, phase)
            self._shading = shading(self._rig.stage, phase)
            self._drip_tops = drip_tops(self._rig.stage, phase)
            self.outlineChanged.emit()

    @Property(str, notify=outlineChanged)
    def inkPath(self) -> str:
        return self._outline

    @Property(str, notify=outlineChanged)
    def inkShade(self) -> str:
        return self._shading[0]

    @Property(str, notify=outlineChanged)
    def inkLight(self) -> str:
        return self._shading[1]

    @Property(str, notify=outlineChanged)
    def inkEdge(self) -> str:
        return self._shading[2]

    @Property(list, notify=outlineChanged)
    def dripTops(self) -> list[float]:
        """Where each drip hangs from, the falling one last (tagnan.art.drip_tops)."""
        return self._drip_tops

    expression = _pose_property("expression", str, poseChanged)
    bodySx = _pose_property("body_sx", float, poseChanged)
    bodySy = _pose_property("body_sy", float, poseChanged)
    bodyX = _pose_property("body_x", float, poseChanged)
    bodyY = _pose_property("body_y", float, poseChanged)
    bodyTurn = _pose_property("body_turn", float, poseChanged)
    eyeOpen = _pose_property("eye_open", float, poseChanged)
    wink = _pose_property("wink", float, poseChanged)
    gazeX = _pose_property("gaze_x", float, poseChanged)
    gazeY = _pose_property("gaze_y", float, poseChanged)
    moustache = _pose_property("moustache", float, poseChanged)
    plume = _pose_property("plume", float, poseChanged)
    hat = _pose_property("hat", float, poseChanged)
    quill = _pose_property("quill", float, poseChanged)
    guard = _pose_property("guard", float, poseChanged)
    sword = _pose_property("sword", float, poseChanged)
    swordY = _pose_property("sword_y", float, poseChanged)
    drops = _pose_property("drops", list, poseChanged)
    drip = _pose_property("drip", float, poseChanged)
    burst = _pose_property("burst", float, poseChanged)
    decor = _pose_property("decor", float, poseChanged)
    glow = _pose_property("glow", float, poseChanged)
    shadow = _pose_property("shadow", float, poseChanged)
