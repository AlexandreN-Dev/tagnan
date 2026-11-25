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
# A man of ink's body is redrawn when the trail of its bottom moves this much (the caches hold
# every outline of a hop); his arms and his hands when one of their joints moves a quarter of a
# unit (a third of a pixel at his usual size), his blade half a degree, his waving hand a degree.
TRAIL_STEP = 0.25
ARM_STEP = 0.25
BLADE_STEP = 0.5


def ripple(wobble: float) -> float:
    """The ripple's phase, brought back within one turn: the rig steps it 22 times a turn, so the
    caches below hold every outline after the first second."""
    return round(wobble % (2 * math.pi), 4)


def trailing(trail: float) -> float:
    return round(trail / TRAIL_STEP) * TRAIL_STEP + 0.0  # never -0.0


@lru_cache(maxsize=1024)
def outline(stage: int, phase: float, drag: float = 0.0) -> str:
    return art.body_path(stage, phase, drag) if art.man(stage) else art.blob_path(stage, phase)


@lru_cache(maxsize=1024)
def shading(stage: int, phase: float, drag: float = 0.0) -> tuple[str, str, str]:
    """The ink's shaded side, lit band and lit edge: the inkwell's (its meniscus, a line to
    stroke) at grade 0; from the Gascon on, a rim of light, a crescent to fill (a man of ink's:
    his body's)."""
    if stage == 0:
        paths = art.inkwell_shading(phase)
        return paths["shade"], paths["light"], paths["meniscus"]
    shaded = (
        art.body_shading(stage, phase, drag) if art.man(stage) else art.ink_shading(stage, phase)
    )
    if shaded:
        return shaded["shade"], shaded["light"], shaded["rim"]
    return "", "", ""


@lru_cache(maxsize=64)
def head(phase: float) -> tuple[str, str, str, str]:
    """A man of ink's head: its outline, its shaded side, lit band and rim of light."""
    shaded = art.head_shading(phase)
    return art.head_path(phase), shaded["shade"], shaded["light"], shaded["rim"]


@lru_cache(maxsize=512)
def hat_ride(stage: int, phase: float) -> tuple[float, float]:
    return art.hat_ride(stage, phase)


@lru_cache(maxsize=1024)
def drip_tops(stage: int, phase: float, drag: float = 0.0) -> list[float]:
    return art.drip_tops(stage, phase, drag)


def arm_parts(
    stage: int, expression: str, joints: tuple[float, ...], blade: float, wave: float
) -> list[dict[str, Any]]:
    """A man of ink's two arms as the window draws them, from his elbows' and hands' positions:
    each sleeve, cuff and lace (tagnan.art.arm_parts) and its hand (tagnan.art.hand_parts). His
    right hand is free: round, or the Captain's, open or a fist as the mood has it, turned with
    his wrist and by its wave. His left is on his rapier from the Lieutenant on: its blade at
    that angle."""
    (r_elbow, r_hand), (l_elbow, l_hand) = (
        ((joints[i], joints[i + 1]), (joints[i + 2], joints[i + 3])) for i in (0, 4)
    )
    right = art.arm_parts(art.SHOULDERS[0], r_elbow, r_hand)
    right["hand"] = art.free_hand(stage, expression, r_elbow, r_hand, wave)
    left = art.arm_parts(art.SHOULDERS[1], l_elbow, l_hand)
    left["hand"] = (
        art.sword_hand(stage, l_hand, blade)
        if art.stands(stage)
        else art.hand_parts("round", l_hand)
    )
    left["blade"] = blade
    return [right, left]


def rest_joints(stage: int, expression: str) -> tuple[float, ...]:
    """His elbows and hands in the mood's pose, his right arm's then his left's."""
    return tuple(v for elbow, hand in art.arm_pose(stage, expression) for v in (*elbow, *hand))


def _pose_property(name: str, kind: type, notify: Signal) -> Any:
    def getter(self: "Animator") -> object:
        return getattr(self._pose, name)

    return Property(kind, getter, notify=notify)


class Animator(QObject):
    poseChanged = Signal()
    outlineChanged = Signal()
    armsChanged = Signal()
    stageChanged = Signal()
    moodChanged = Signal()
    tapped = Signal(str)  # the tap's mood: wink, annoyed or sulk

    def __init__(self, rig: Rig | None = None, stage: int = 0, frame_ms: int = FRAME_MS) -> None:
        super().__init__()
        self._rig = rig or Rig()
        self._rig.set_stage(stage)
        self._pose: Pose = REST_POSE
        self._drawn = (0.0, 0.0)  # the ripple's phase and the trail his ink is drawn at
        self._redraw()
        self._arms_at: tuple[Any, ...] = ()  # what his arms are drawn from
        self._arms: list[dict[str, Any]] = []
        self._move_arms()
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

    @Property(bool, constant=True)
    def reducedMotion(self) -> bool:
        """For QML: no spring when he changes size."""
        return self._rig.reduced_motion

    def _get_stage(self) -> int:
        return self._rig.stage

    def _set_stage(self, stage: int) -> None:
        if stage != self._rig.stage:
            self._rig.set_stage(stage)
            self._redraw()
            self._move_arms()
            self.stageChanged.emit()
            self.outlineChanged.emit()
            self.armsChanged.emit()

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
        self._pose = pose
        self.poseChanged.emit()
        drawn = (ripple(pose.wobble), trailing(pose.trail))
        if drawn != self._drawn:
            self._drawn = drawn
            self._redraw()
            self.outlineChanged.emit()
        if self._move_arms():
            self.armsChanged.emit()

    def _redraw(self) -> None:
        """His ink at the ripple's phase (and, the Musketeer's body, the trail) of the pose."""
        stage, (phase, drag) = self._rig.stage, self._drawn
        self._outline = outline(stage, phase, drag)
        self._shading = shading(stage, phase, drag)
        self._drip_tops = drip_tops(stage, phase, drag)
        self._hat_ride = hat_ride(stage, phase)
        self._head = head(phase) if art.man(stage) else ("", "", "", "")

    def _move_arms(self) -> bool:
        """A man of ink's arms where the pose has them (in the mood's pose, his blade at the
        mood's angle, without motion); whether they moved."""
        stage, pose = self._rig.stage, self._pose
        at: tuple[Any, ...] = ()
        if art.man(stage):
            joints = pose.arms or rest_joints(stage, pose.expression)
            blade = pose.blade if pose.arms else art.BLADE[pose.expression]
            at = (
                stage,
                pose.expression,
                tuple(round(round(v / ARM_STEP) * ARM_STEP, 2) for v in joints),
                round(blade / BLADE_STEP) * BLADE_STEP if art.stands(stage) else 0.0,
                float(round(pose.wave)),
            )
        if at == self._arms_at:
            return False
        self._arms_at = at
        self._arms = arm_parts(*at) if at else []
        return True

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

    @Property(str, notify=outlineChanged)
    def headPath(self) -> str:
        """The Musketeer's head (tagnan.art.head_path), and its shading below."""
        return self._head[0]

    @Property(str, notify=outlineChanged)
    def headShade(self) -> str:
        return self._head[1]

    @Property(str, notify=outlineChanged)
    def headLight(self) -> str:
        return self._head[2]

    @Property(str, notify=outlineChanged)
    def headEdge(self) -> str:
        return self._head[3]

    @Property(list, notify=armsChanged)
    def arms(self) -> list[dict[str, Any]]:
        """A man of ink's arms, his right then his left: sleeve, cuff, lace, and under "hand"
        what his hand is drawn of (tagnan.art.arm_parts, hand_parts); his left arm's "blade" is
        his rapier's angle. None before the Musketeer."""
        return self._arms

    @Property(float, notify=outlineChanged)
    def hatRideY(self) -> float:
        """How far the Cadet's hat rises or sinks on his rippling head (tagnan.art.hat_ride)."""
        return self._hat_ride[0]

    @Property(float, notify=outlineChanged)
    def hatRideTip(self) -> float:
        """How far it tips with it, in degrees."""
        return self._hat_ride[1]

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
    drops = _pose_property("drops", list, poseChanged)
    drip = _pose_property("drip", float, poseChanged)
    burst = _pose_property("burst", float, poseChanged)
    decor = _pose_property("decor", float, poseChanged)
    glow = _pose_property("glow", float, poseChanged)
    shadow = _pose_property("shadow", float, poseChanged)
    headY = _pose_property("head_y", float, poseChanged)
    headLean = _pose_property("head_lean", float, poseChanged)
