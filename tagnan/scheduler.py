"""When Tagnan asks: at random within working hours, never while paused."""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Rhythm:
    min_minutes: float = 8
    max_minutes: float = 25
    snooze_minutes: float = 10
    start_hour: int = 9  # first hour he may ask in
    end_hour: int = 19  # he stops asking at this hour
    weekends: bool = False

    def __post_init__(self) -> None:
        if not 0 < self.min_minutes <= self.max_minutes:
            raise ValueError("rythme : il faut 0 < min_minutes <= max_minutes")
        if not 0 <= self.start_hour < self.end_hour <= 24:
            raise ValueError("rythme : il faut 0 <= start_hour < end_hour <= 24")


class Scheduler:
    def __init__(self, rhythm: Rhythm, rng: random.Random, now: float) -> None:
        self.rhythm = rhythm
        self._rng = rng
        self.paused_until = 0.0
        self.next_at = self._place(now + self._gap())

    def is_active(self, now: float) -> bool:
        """Within working hours, on a working day (unless weekends are on)."""
        moment = datetime.fromtimestamp(now)
        if not self.rhythm.weekends and moment.weekday() >= 5:
            return False
        return self.rhythm.start_hour <= moment.hour < self.rhythm.end_hour

    def due(self, now: float) -> bool:
        return now >= self.next_at and now >= self.paused_until and self.is_active(now)

    def asked(self, now: float) -> None:
        """A question was asked (or answered): the next one comes after a random gap."""
        self.next_at = self._place(now + self._gap())

    def snooze(self, now: float) -> None:
        self.next_at = self._place(now + self.rhythm.snooze_minutes * 60)

    def postpone(self, now: float, minutes: float) -> None:
        """Not now (a full-screen application, a locked session): try again a little later."""
        self.next_at = max(self.next_at, now + minutes * 60)

    def pause(self, now: float, minutes: float) -> None:
        self.paused_until = now + minutes * 60
        self.next_at = max(self.next_at, self._place(self.paused_until + self._gap() / 3))

    def resume(self, now: float) -> None:
        self.paused_until = 0.0
        self.next_at = self._place(now + self._gap() / 3)

    def _gap(self) -> float:
        return self._rng.uniform(self.rhythm.min_minutes, self.rhythm.max_minutes) * 60

    def _place(self, when: float) -> float:
        """The same moment if active, else a few minutes into the next working period."""
        if self.is_active(when):
            return when
        moment = datetime.fromtimestamp(when)
        day = moment.replace(hour=self.rhythm.start_hour, minute=0, second=0, microsecond=0)
        if moment.hour >= self.rhythm.start_hour:
            day += timedelta(days=1)
        while not self.rhythm.weekends and day.weekday() >= 5:
            day += timedelta(days=1)
        return day.timestamp() + self._rng.uniform(2, self.rhythm.min_minutes) * 60
