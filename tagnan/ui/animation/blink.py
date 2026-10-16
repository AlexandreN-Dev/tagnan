"""Blinks: 70 ms closing, 30 ms shut, 90 ms opening, every 1.8 to 6 s; 12 % come in pairs."""

import random

CLOSING, SHUT, OPENING = 0.070, 0.030, 0.090
DURATION = CLOSING + SHUT + OPENING
MIN_GAP, MAX_GAP = 1.8, 6.0
DOUBLE_CHANCE = 0.12
DOUBLE_GAP = 0.12
AFTER_SACCADE_CHANCE = 0.45


class BlinkScheduler:
    def __init__(self, rng: random.Random, now: float = 0.0) -> None:
        self._rng = rng
        self._start: float | None = None
        self._next = now + rng.uniform(MIN_GAP, MAX_GAP)
        self._double_pending = False
        self._is_second = False

    @property
    def next_at(self) -> float:
        """When the next blink starts (or the current one started)."""
        return self._start if self._start is not None else self._next

    def after_saccade(self, now: float) -> None:
        """A big glance often comes with a blink."""
        if self._start is None and self._rng.random() < AFTER_SACCADE_CHANCE:
            self._next = min(self._next, now)

    def openness(self, now: float) -> float:
        """1 when open, 0 when shut."""
        if self._start is None and now >= self._next:
            self._start = self._next
            self._double_pending = not self._is_second and self._rng.random() < DOUBLE_CHANCE
        if self._start is None:
            return 1.0
        t = now - self._start
        if t < CLOSING:
            return 1.0 - t / CLOSING
        if t < CLOSING + SHUT:
            return 0.0
        if t < DURATION:
            return (t - CLOSING - SHUT) / OPENING
        end = self._start + DURATION
        self._start = None
        if self._double_pending:
            self._double_pending = False
            self._is_second = True
            self._next = end + DOUBLE_GAP
        else:
            self._is_second = False
            self._next = end + self._rng.uniform(MIN_GAP, MAX_GAP)
        return self.openness(now) if now >= self._next else 1.0
