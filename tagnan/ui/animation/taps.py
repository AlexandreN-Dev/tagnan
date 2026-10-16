"""Taps on Tagnan, counted as Dartt counts them: one tickles him, three within 1.5 s annoy him
for 1.6 s, six within 3 s make him sulk for 2.4 s."""

from collections import deque
from enum import Enum

TICKLE_DURATION = 0.9
ANNOY_TAPS, ANNOY_WINDOW, ANNOY_DURATION = 3, 1.5, 1.6
SULK_TAPS, SULK_WINDOW, SULK_DURATION = 6, 3.0, 2.4


class Mood(Enum):
    NONE = "none"
    TICKLED = "wink"
    ANNOYED = "annoyed"
    SULKING = "sulk"


class TapTracker:
    def __init__(self) -> None:
        self._taps: deque[float] = deque()
        self._mood = Mood.NONE
        self._until = 0.0

    def tap(self, now: float) -> Mood:
        self._taps.append(now)
        while self._taps and now - self._taps[0] > SULK_WINDOW:
            self._taps.popleft()
        recent = sum(1 for t in self._taps if now - t <= ANNOY_WINDOW)
        current = self.mood(now)
        if len(self._taps) >= SULK_TAPS:
            self._mood, self._until = Mood.SULKING, now + SULK_DURATION
            self._taps.clear()
        elif current is Mood.SULKING:
            self._until = now + SULK_DURATION  # poking a sulker keeps him sulking
        elif recent >= ANNOY_TAPS:
            self._mood, self._until = Mood.ANNOYED, now + ANNOY_DURATION
        elif current is not Mood.ANNOYED:
            self._mood, self._until = Mood.TICKLED, now + TICKLE_DURATION
        return self.mood(now)

    def mood(self, now: float) -> Mood:
        return self._mood if now < self._until else Mood.NONE
