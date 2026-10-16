"""What a break can be: for a while (1h, 1h30, 45 min) or until a time (15:30, 3pm, noon).

A bare hour is read the way one says it: a time still to come today ("15h", "15:30") is
when he comes back; a small number of hours ("1h", "2h30") is how long he waits; a time
already gone ("10h" in the afternoon) is tomorrow morning's. "for" or "until" settle it
either way, and the bubble shows what he understood before it is confirmed. English and French
words both work: Tagnan speaks English, the one who types may not.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta

MAX_MINUTES = 7 * 24 * 60
SHORT_HOURS = 5  # "1h" to "5h": a while, not a time of night

FOR_A_WHILE = r"^(for|in|pendant|pour|\+)\s*"
UNTIL = r"^(until|till|til|at|to|jusqu'?a|a)\s+|^(jusqu'?a)"
HOURS = r"(?:h|hr|hrs|hour|hours|heure|heures)"
MINUTES = r"(?:m|mn|min|mins|minute|minutes)"
NOON = ("noon", "midday", "midi")
TOMORROW = ("tomorrow", "tomorrowmorning", "demain", "demainmatin")
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@dataclass(frozen=True)
class Pause:
    until: float  # when he comes back (timestamp)
    minutes: float | None = None  # how long, when it was given as a while


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.replace("\u2019", "'").split())  # a typographic apostrophe


def _at(now: datetime, hour: int, minute: int) -> datetime:
    when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return when if when > now else when + timedelta(days=1)


def parse(text: str, now: float, morning_hour: int = 9) -> Pause | None:
    """The break the text asks for, or None when it makes no sense."""
    plain = _plain(text)
    if not plain:
        return None
    moment = datetime.fromtimestamp(now)
    for_a_while = bool(re.match(FOR_A_WHILE, plain))
    until = bool(re.match(UNTIL, plain))
    body = re.sub(FOR_A_WHILE, "", plain)
    body = re.sub(UNTIL, "", body).replace(" ", "")

    if body in NOON and not for_a_while:
        return Pause(_at(moment, 12, 0).timestamp())
    if body in TOMORROW:
        tomorrow = moment + timedelta(days=1)
        back = tomorrow.replace(hour=morning_hour, minute=0, second=0, microsecond=0)
        return Pause(back.timestamp())

    if match := re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(am|pm)", body):
        hour, minute = int(match[1]), int(match[2] or 0)
        if not 1 <= hour <= 12 or minute >= 60:
            return None
        hour = hour % 12 + (12 if match[3] == "pm" else 0)
        return Pause(_at(moment, hour, minute).timestamp())

    minutes: float
    if match := re.fullmatch(rf"(\d{{1,4}}){MINUTES}", body):
        minutes = int(match[1])
    elif match := re.fullmatch(r"(\d{1,3})", body):
        value = int(match[1])
        minutes = value * 60 if value < 10 else value  # "2" is two hours, "30" half an hour
    elif match := re.fullmatch(rf"(\d{{1,2}})(?:{HOURS}|:)(\d{{1,2}})?{MINUTES}?", body):
        hour, minute = int(match[1]), int(match[2] or 0)
        if minute >= 60:
            return None
        if not for_a_while and (until or hour > SHORT_HOURS):
            if hour > 23:
                return None
            return Pause(_at(moment, hour, minute).timestamp())
        minutes = hour * 60 + minute
    else:
        return None
    if not 1 <= minutes <= MAX_MINUTES:
        return None
    return Pause(now + minutes * 60, minutes)


def clock(when: float, now: float) -> str:
    """Like "15:30", "tomorrow at 9:00" or "Monday at 9:00"."""
    moment, today = datetime.fromtimestamp(when), datetime.fromtimestamp(now)
    hour = f"{moment.hour}:{moment.minute:02d}"
    days = (moment.date() - today.date()).days
    if days == 0:
        return hour
    if days == 1:
        return f"tomorrow at {hour}"
    return f"{DAYS[moment.weekday()]} at {hour}"


def duration(minutes: float) -> str:
    """Like "45 min", "1 hour", "1 hour 30 min" or "2 hours"."""
    total = round(minutes)
    hours, rest = divmod(total, 60)
    if not hours:
        return f"{rest} min"
    text = f"{hours} hour{'s' if hours > 1 else ''}"
    return text + (f" {rest} min" if rest else "")


def describe(pause: Pause, now: float) -> str:
    """What the bubble says before it is confirmed: "A break of 1 hour 30 min, back at
    12:50", "A break until 15:30", "A break until tomorrow at 9:00"."""
    back = clock(pause.until, now)
    if pause.minutes is not None:
        when = f"at {back}" if back[0].isdigit() else back
        return f"A break of {duration(pause.minutes)}, back {when}"
    return f"A break until {back}"
