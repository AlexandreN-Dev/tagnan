"""Tagnan's rig: from his grade, the quiz's mood, taps and time to the pose of every piece, one
frame at a time.

Dartt's rig, adapted (same springs, blinks, idle behaviours and tap counting): Tagnan breathes,
ripples, blinks, looks around or at the pointer, twitches his moustache, swings his rapier,
hops; he perks up to ask, bounds when you are right, shakes with rage when you are wrong, and
splashes droplets when tapped. Units are those of the drawing (tagnan.art), angles in degrees,
durations in seconds.
"""

import itertools
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from tagnan.ui.animation.blink import BlinkScheduler
from tagnan.ui.animation.springs import Spring
from tagnan.ui.animation.taps import Mood, TapTracker

QUIZ_MOODS = ("idle", "ask", "happy", "angry")

GAZE_REACH = 3.0
POINTER_REACH_PX = 300.0
POINTER_MEMORY = 2.5
BREATH = 0.02
SWAY = 1.2
TAP_SQUASH = 0.16
SACCADE = 2.0
# The ink's outline changes this many times a second of his time, about 14 in real time: enough
# for so slow a wave. It goes round once a second, so these few outlines repeat (and are cached).
WOBBLE_RATE = 22
# His whole animation runs at 0.648 of real time: a tenth, a fifth, then a tenth slower again
# (taps are still counted in real time).
TEMPO = 0.648
DRIP_PERIOD = 7.0
GLOW_PERIOD = 3.4
BURST_LENGTH = 1.2
QUILL_SWAY = 3.0  # degrees each way, around the nib
DECOR_POP = Spring(260, 0.35)

IDLE_MIN, IDLE_MAX = 7.0, 15.0
IDLE_WEIGHTS = {"look": 3, "twitch": 3, "plop": 2, "blade": 2, "wink": 1}
IDLE_DURATIONS = {"look": 1.6, "twitch": 2.4, "plop": 0.55, "blade": 3.0, "wink": 2.4}
TWITCH = ((0.15, 0.0), (0.2, 7.0), (0.26, -4.0), (0.32, 5.0), (0.38, 0.0))
WINK = ((0.25, 0.0), (0.35, 1.0), (0.62, 1.0), (0.75, 0.0))

PERK = (9.0, 0.42)  # height, duration of the hop when he asks
CHEER = ((18.0, 0.5), (10.0, 0.4))  # two bounds when you are right
PLOP = (6.0, 0.4)
SHAKE = (6.0, 9.0, 0.7)  # amplitude, frequency, duration of his rage
HUFF = (3.0, 12.0, 0.5)
SULK_TURN = (9.0, 6.0)  # he turns away: offset, angle

SWORD_FLOAT = (1.6, 3.3)  # the floating rapier bobs: amplitude, period
DROP_FLOAT = ((4.1, 0.0), (3.6, -1.0), (4.6, -2.0), (3.9, -0.5), (4.3, -1.6))
DROP_DRIFT = (1.6, -3.2)


@dataclass(frozen=True)
class Pose:
    expression: str = "idle"
    body_sx: float = 1.0
    body_sy: float = 1.0
    body_x: float = 0.0
    body_y: float = 0.0
    body_turn: float = 0.0
    wobble: float = 0.0  # phase of the ink's rippling edge
    eye_open: float = 1.0
    wink: float = 0.0  # left eye squashed shut (the idle wink)
    gaze_x: float = 0.0
    gaze_y: float = 0.0
    moustache: float = 0.0
    plume: float = 0.0
    hat: float = 0.0
    quill: float = 0.0
    guard: float = 0.0  # 0: rapier floating point down; 1: raised en garde
    sword: float = 0.0  # swing on top of the guard's angle
    sword_y: float = 0.0  # the floating rapier bobs
    drops: tuple[float, ...] = (0.0,) * 10
    drip: float = 0.0  # 0 to 1 along the drip's cycle
    burst: float = -1.0  # seconds since a tap splashed droplets, -1 when none
    decor: float = 1.0  # pop-in of the decoration
    glow: float = 0.45
    shadow: float = 1.0


REST_POSE = Pose()


@dataclass
class _Hop:
    start: float
    height: float
    duration: float


@dataclass
class _Shake:
    start: float
    amplitude: float
    frequency: float
    duration: float


@dataclass
class _Idle:
    kind: str
    start: float
    kicked: bool = False


@dataclass
class _Queue:
    hops: list[tuple[float, float]] = field(default_factory=list)


def keyframes(t: float, points: Sequence[tuple[float, float]]) -> float:
    if t <= points[0][0]:
        return points[0][1]
    for (t0, v0), (t1, v1) in itertools.pairwise(points):
        if t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return points[-1][1]


def breathing(now: float) -> float:
    """Two mixed rhythms, between -1 and 1."""
    return 0.6 * math.sin(2 * math.pi * now / 3.6) + 0.4 * math.sin(2 * math.pi * now / 2.2 + 1.3)


class Rig:
    def __init__(self, rng: random.Random | None = None, reduced_motion: bool = False) -> None:
        self._rng = rng or random.Random()  # noqa: S311 - animation, not secrets
        self.reduced_motion = reduced_motion
        self.tempo = TEMPO
        self.wobble_rate = WOBBLE_RATE
        self.now = 0.0  # animation time
        self.real_now = 0.0  # wall time, for counting taps
        self.stage = 0
        self.mood = "idle"
        self._mood_since = 0.0
        self._blink = BlinkScheduler(self._rng)
        self._taps = TapTracker()
        self._gaze_x = Spring(900, 1.0)
        self._gaze_y = Spring(900, 1.0)
        self._gaze_target = (0.0, 0.0)
        self._landing = Spring(180, 0.35)
        self._tap = Spring(300, 0.3)
        self._sword = Spring(50, 0.22)
        self._guard = Spring(70, 0.75)
        self._moustache = Spring(300, 0.5)
        self._plume = Spring(90, 0.25)
        self._hat = Spring(160, 0.4)
        self._turn = Spring(120, 0.8)
        self._decor = Spring(DECOR_POP.stiffness, DECOR_POP.damping, value=1.0, target=1.0)
        self._hop: _Hop | None = None
        self._queue = _Queue()
        self._shake: _Shake | None = None
        self._burst_at: float | None = None
        self._next_idle = self._rng.uniform(IDLE_MIN, IDLE_MAX)
        self._idle: _Idle | None = None
        self._look: tuple[float, float] | None = None
        self._look_until = 0.0
        self._pointer: tuple[float, float] | None = None
        self._pointer_at = -math.inf

    # --- Inputs -----------------------------------------------------------------------------

    def set_stage(self, stage: int) -> None:
        self.stage = stage
        self._idle = None

    def set_mood(self, mood: str) -> None:
        """The quiz's mood: idle, ask (a question is up), happy (right), angry (wrong)."""
        if mood not in QUIZ_MOODS or mood == self.mood:
            return
        self.mood, self._mood_since = mood, self.now
        self._idle = None
        if mood != "idle":
            self._decor.value, self._decor.velocity = 0.0, 0.0
        if self.reduced_motion:
            return
        if mood == "ask":
            self._start_hops([PERK])
            self._sword.kick(-120)
        elif mood == "happy":
            self._start_hops(list(CHEER))
            self._sword.kick(260)
        elif mood == "angry":
            self._shake = _Shake(self.now, *SHAKE)
            self._moustache.kick(400)

    def tap(self) -> Mood:
        mood = self._taps.tap(self.real_now)
        if self.reduced_motion:
            return mood
        self._burst_at = self.now
        self._tap.value, self._tap.velocity = TAP_SQUASH, 0.0
        self._sword.kick(90)
        self._plume.kick(60)
        if mood is Mood.ANNOYED:
            self._shake = _Shake(self.now, *HUFF)
        return mood

    def look_at(self, dx: float, dy: float) -> None:
        """The pointer moved; (dx, dy) in screen pixels from between Tagnan's eyes."""
        distance = math.hypot(dx, dy)
        if distance < 1:
            self._pointer = (0.0, 0.0)
        else:
            reach = GAZE_REACH * min(1.0, distance / POINTER_REACH_PX)
            self._pointer = (dx / distance * reach, dy / distance * reach * 0.7)
        self._pointer_at = self.now

    def idle(self, kind: str) -> None:
        """Start an idle behaviour now (debug, tests)."""
        if kind in IDLE_WEIGHTS and not self.reduced_motion:
            self._start_idle(kind)

    @property
    def tap_mood(self) -> Mood:
        return self._taps.mood(self.real_now)

    # --- Frame ------------------------------------------------------------------------------

    def step(self, dt: float) -> Pose:
        dt = min(max(dt, 0.0), 0.1)
        self.real_now += dt
        dt *= self.tempo
        self.now += dt
        now = self.now
        overlay = self._taps.mood(self.real_now)
        expression = overlay.value if overlay is not Mood.NONE else self.mood
        if self.reduced_motion:
            return Pose(expression=expression, guard=1.0 if self._en_garde(expression) else 0.0)

        still = self.stage == 0  # the inkwell does not breathe or hop
        if self.mood == "idle" and overlay is Mood.NONE:
            self._schedule_idle(now)
        idle = self._current_idle(now)

        # Body: breathing, sway, hops and their landing, taps, rage, turning away when sulking.
        breath = 0.0 if still else BREATH * breathing(now)
        sway = 0.0 if still else SWAY * math.sin(2 * math.pi * now / 5.3)
        hop_y, hop_speed = (0.0, 0.0) if still else self._hops()
        landing = self._landing.step(dt)
        tap = self._tap.step(dt)
        body_sy = 1 + breath - landing - tap + min(abs(hop_speed) * 0.0005, 0.06)
        body_sx = 1 / math.sqrt(max(body_sy, 0.5))
        shake = self._shaking(now)
        self._turn.target = 1.0 if overlay is Mood.SULKING else 0.0
        turn = self._turn.step(dt)
        body_x = sway + shake + SULK_TURN[0] * turn
        body_turn = SULK_TURN[1] * turn
        if self.stage == 1:  # the escaped ink floats and rocks
            body_turn += 2.0 * math.sin(2 * math.pi * now / 2.8)
            hop_y -= 2.5 * (1 + math.sin(2 * math.pi * now / 2.8 * 2)) / 2
        if still:
            body_sy = 1 - tap * 0.3
            body_sx = 1.0

        # Eyes: blinks, the idle wink, the gaze.
        eye_open = self._blink.openness(now)
        wink = keyframes(self._progress(idle, now), WINK) if idle and idle.kind == "wink" else 0.0
        gaze_x, gaze_y = self._gaze(idle, now, dt)

        # Moustache and plumes: twitches, kicks, a breeze.
        twitch = (
            keyframes(self._progress(idle, now), TWITCH) if idle and idle.kind == "twitch" else 0.0
        )
        self._moustache.target = twitch + (2.5 if expression == "angry" else 0.0)
        moustache = self._moustache.step(dt)
        if expression == "angry":
            moustache += 1.5 * math.copysign(1, math.sin(2 * math.pi * 11 * now))
        plume = self._plume.step(dt, -hop_speed * 0.8) + 4.0 * math.sin(2 * math.pi * now / 3.8)
        hat = self._hat.step(dt, -hop_speed * 0.15) + 0.4 * sway

        # Rapier: raised en garde to ask or cheer, at his side otherwise; it swings on hops,
        # taps and idle flourishes.
        self._guard.target = 1.0 if self._en_garde(expression) else 0.0
        guard = min(max(self._guard.step(dt), -0.1), 1.1)
        if idle and idle.kind == "blade" and not idle.kicked and self._progress(idle, now) > 0.35:
            idle.kicked = True
            self._sword.kick(-240)
        sword = self._sword.step(dt, -sway * 1.5)
        if expression == "angry":
            sword += 2.0 * math.sin(2 * math.pi * 13 * now)

        # Decoration pops in when the mood changes.
        self._decor.target = 1.0
        decor = self._decor.step(dt)

        burst = -1.0
        if self._burst_at is not None:
            burst = now - self._burst_at
            if burst > BURST_LENGTH:
                self._burst_at, burst = None, -1.0

        return Pose(
            expression=expression,
            body_sx=body_sx,
            body_sy=body_sy,
            body_x=body_x,
            body_y=hop_y,
            body_turn=body_turn,
            wobble=2 * math.pi * math.floor(now * self.wobble_rate) / self.wobble_rate,
            eye_open=eye_open,
            wink=wink,
            gaze_x=gaze_x,
            gaze_y=gaze_y,
            moustache=moustache,
            plume=plume,
            hat=hat,
            quill=QUILL_SWAY * math.sin(2 * math.pi * now / 4.2),
            guard=guard,
            sword=sword,
            sword_y=SWORD_FLOAT[0] * math.sin(2 * math.pi * now / SWORD_FLOAT[1]),
            drops=self._drops(now, hop_y),
            drip=(now % DRIP_PERIOD) / DRIP_PERIOD,
            burst=burst,
            decor=decor,
            glow=0.49 + 0.11 * math.sin(2 * math.pi * now / GLOW_PERIOD),
            shadow=1 + hop_y / 60,
        )

    # --- Parts ------------------------------------------------------------------------------

    @staticmethod
    def _en_garde(expression: str) -> bool:
        return expression in ("ask", "happy")

    def _schedule_idle(self, now: float) -> None:
        if now < self._next_idle or self._idle is not None:
            return
        allowed = {
            "look": True,
            "wink": True,
            "plop": self.stage >= 1,
            "twitch": self.stage >= 4,
            "blade": self.stage >= 4,
        }
        kinds = [k for k in IDLE_WEIGHTS if allowed[k]]
        kind = self._rng.choices(kinds, weights=[IDLE_WEIGHTS[k] for k in kinds])[0]
        self._start_idle(kind)
        self._next_idle = now + self._rng.uniform(IDLE_MIN, IDLE_MAX)

    def _start_idle(self, kind: str) -> None:
        self._idle = _Idle(kind, self.now)
        if kind == "look":
            self._look = (self._rng.uniform(-3, 3), self._rng.uniform(-2, 1.5))
            self._look_until = self.now + IDLE_DURATIONS["look"]
        elif kind == "plop":
            self._start_hops([PLOP])

    def _current_idle(self, now: float) -> _Idle | None:
        if self._idle is not None and now - self._idle.start > IDLE_DURATIONS[self._idle.kind]:
            self._idle = None
        return self._idle

    @staticmethod
    def _progress(idle: _Idle | None, now: float) -> float:
        return 0.0 if idle is None else (now - idle.start) / IDLE_DURATIONS[idle.kind]

    def _start_hops(self, hops: list[tuple[float, float]]) -> None:
        if self.stage == 0:
            return
        first, *rest = hops
        self._hop = _Hop(self.now, *first)
        self._queue.hops = rest

    def _hops(self) -> tuple[float, float]:
        """Height (negative is up) and vertical speed of the current hop."""
        hop = self._hop
        if hop is None:
            return 0.0, 0.0
        tau = (self.now - hop.start) / hop.duration
        if tau >= 1:
            speed = 4 * hop.height / hop.duration
            self._landing.kick(speed * 0.012)
            self._sword.kick(-speed * 0.8)
            self._plume.kick(speed * 0.6)
            self._hop = None
            if self._queue.hops:
                self._hop = _Hop(self.now, *self._queue.hops.pop(0))
            return 0.0, 0.0
        return -4 * hop.height * tau * (1 - tau), -4 * hop.height * (1 - 2 * tau) / hop.duration

    def _shaking(self, now: float) -> float:
        shake = self._shake
        if shake is None:
            return 0.0
        t = now - shake.start
        if t >= shake.duration:
            self._shake = None
            return 0.0
        decay = 1 - t / shake.duration
        return shake.amplitude * decay * math.sin(2 * math.pi * shake.frequency * t)

    def _gaze(self, idle: _Idle | None, now: float, dt: float) -> tuple[float, float]:
        if self._pointer is not None and now - self._pointer_at <= POINTER_MEMORY:
            target = self._pointer
        elif self._look is not None and now < self._look_until:
            target = self._look
        else:
            target = (0.0, 0.0)
        if idle and idle.kind == "blade":
            target = (2.5, 1.5)  # a glance at the blade
        if math.dist(target, self._gaze_target) > SACCADE:
            self._blink.after_saccade(now)
        self._gaze_target = target
        self._gaze_x.target, self._gaze_y.target = target
        return self._gaze_x.step(dt), self._gaze_y.step(dt)

    def _drops(self, now: float, hop_y: float) -> tuple[float, ...]:
        offsets: list[float] = []
        for period, shift in DROP_FLOAT:
            drift = (1 - math.cos(2 * math.pi * (now + shift) / period)) / 2
            offsets.append(DROP_DRIFT[0] * drift)
            offsets.append(DROP_DRIFT[1] * drift + hop_y * 0.6)
        return tuple(offsets)
