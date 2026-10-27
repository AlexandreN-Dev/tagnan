"""When Tagnan asks: at random within working hours, at the pace one chose, never while
paused."""

import random
from dataclasses import dataclass, replace
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Pace:
    """How often Tagnan asks: a gap between two questions, in minutes, or a number of questions
    a working day, whatever the working hours."""

    key: str
    name: str
    every: tuple[float, float] = (0.0, 0.0)  # the shortest and longest gap, in minutes
    per_day: tuple[int, int] | None = None  # the fewest and most questions a working day

    def gaps(self, day_minutes: float) -> tuple[float, float]:
        """n to m questions a day: gaps between an m-th and an n-th of the day. The day's first
        question comes within its first m-th (Scheduler._place), so there is never one more
        than m, and never fewer than n unless one starts late or answers late."""
        if self.per_day is None:
            return self.every
        fewest, most = self.per_day
        return day_minutes / most, day_minutes / fewest

    @property
    def hint(self) -> str:
        """Like "2 or 3 a day" or "every 3 to 5 min": beside its name, in his menu."""
        if self.per_day is not None:
            return f"{self.per_day[0]} or {self.per_day[1]} a day"
        return f"every {self.every[0]:g} to {self.every[1]:g} min"

    @property
    def sentence(self) -> str:
        if self.per_day is not None:
            return f"{self.per_day[0]} or {self.per_day[1]} questions a day"
        return f"A question {self.hint}"


# From the slowest to the fastest; Regularly is the rhythm Tagnan always had.
PACES = (
    Pace("rarely", "Rarely", per_day=(2, 3)),
    Pace("now-and-then", "Now and then", every=(45, 90)),
    Pace("regularly", "Regularly", every=(8, 25)),
    Pace("often", "Often", every=(5, 10)),
    Pace("intensive", "Intensive training", every=(3, 5)),
)


def find_pace(key: str) -> Pace | None:
    return next((p for p in PACES if p.key == key), None)


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

    @property
    def day_minutes(self) -> float:
        return (self.end_hour - self.start_hour) * 60.0

    def paced(self, chosen: Pace) -> "Rhythm":
        """The same hours, at another pace."""
        low, high = chosen.gaps(self.day_minutes)
        return replace(self, min_minutes=low, max_minutes=high)

    @property
    def pace(self) -> Pace | None:
        """The pace these gaps are, if any: gaps of one's own in the config file may be none."""
        gaps = (self.min_minutes, self.max_minutes)
        return next((p for p in PACES if p.gaps(self.day_minutes) == gaps), None)

    def at_hours(self, start_hour: int, end_hour: int, weekends: bool) -> "Rhythm":
        """Other hours, at the same pace: a pace of so many questions a day spreads them over
        the new day."""
        chosen = self.pace
        moved = replace(self, start_hour=start_hour, end_hour=end_hour, weekends=weekends)
        return moved.paced(chosen) if chosen else moved

    @property
    def hours(self) -> dict[str, int | bool]:
        """His hours as the window keeps them in its settings, once chosen in his menu."""
        return {"start": self.start_hour, "end": self.end_hour, "weekends": self.weekends}

    def kept(self, saved: object) -> "Rhythm":
        """The hours the window kept (`hours`), if they make sense; else these."""
        if not isinstance(saved, dict):
            return self
        start, end, weekends = saved.get("start"), saved.get("end"), saved.get("weekends")
        if type(start) is not int or type(end) is not int or not isinstance(weekends, bool):
            return self
        try:
            return self.at_hours(start, end, weekends)
        except ValueError:
            return self

    @property
    def hours_hint(self) -> str:
        """Like "Mon–Fri, 9–19": beside Hours, in his menu."""
        days = "Every day" if self.weekends else "Mon–Fri"
        return f"{days}, {self.start_hour}–{self.end_hour}"

    @property
    def hours_sentence(self) -> str:
        days = "Every day" if self.weekends else "Weekdays"
        return f"{days}, from {self.start_hour}:00 to {self.end_hour}:00"


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

    def missed(self, now: float) -> None:
        """A question left unanswered (one is away, maybe): the next one waits a snooze, or a
        gap of the pace if that is longer, lest he call every twenty minutes at a slow pace."""
        self.next_at = self._place(now + max(self.rhythm.snooze_minutes * 60, self._gap()))

    def set_rhythm(self, rhythm: Rhythm, now: float) -> None:
        """Another pace: the next question comes after a gap of the new one (and after the
        break, if one is on)."""
        self.rhythm = rhythm
        self.next_at = self._place(now + self._gap())
        if self.paused_until > now:
            self.next_at = max(self.next_at, self._place(self.paused_until + self._gap() / 3))

    def postpone(self, now: float, minutes: float) -> None:
        """Not now (a full-screen application, a locked session): try again a little later."""
        self.next_at = max(self.next_at, now + minutes * 60)

    def pause(self, now: float, minutes: float) -> None:
        self.pause_until(now + minutes * 60)

    def pause_until(self, until: float) -> None:
        """No question before then; the first one comes a little after."""
        self.paused_until = until
        self.next_at = max(self.next_at, self._place(until + self._gap() / 3))

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
