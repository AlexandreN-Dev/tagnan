from datetime import datetime

import pytest

from tagnan import pause

MONDAY_1120 = datetime(2026, 10, 12, 11, 20).timestamp()


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("1h", "A break of 1 hour, back at 12:20"),
        ("1 h 30", "A break of 1 hour 30 min, back at 12:50"),
        ("1h30", "A break of 1 hour 30 min, back at 12:50"),
        ("90 min", "A break of 1 hour 30 min, back at 12:50"),
        ("45mn", "A break of 45 min, back at 12:05"),
        ("30", "A break of 30 min, back at 11:50"),
        ("2", "A break of 2 hours, back at 13:20"),
        ("for 2 hours", "A break of 2 hours, back at 13:20"),
        ("pendant 2h", "A break of 2 hours, back at 13:20"),
        ("in 45 minutes", "A break of 45 min, back at 12:05"),
        ("15h", "A break until 15:00"),
        ("15h30", "A break until 15:30"),
        ("15:30", "A break until 15:30"),
        ("3pm", "A break until 15:00"),
        ("until 4:45 pm", "A break until 16:45"),
        ("Jusqu\u2019à 16h45", "A break until 16:45"),  # a typographic apostrophe
        ("until 12h", "A break until 12:00"),
        ("noon", "A break until 12:00"),
        ("midi", "A break until 12:00"),
        ("at 9h", "A break until tomorrow at 9:00"),  # already gone today
        ("10h", "A break until tomorrow at 10:00"),
        ("tomorrow", "A break until tomorrow at 9:00"),
        ("demain", "A break until tomorrow at 9:00"),
    ],
)
def test_a_while_or_a_time(text: str, said: str) -> None:
    understood = pause.parse(text, MONDAY_1120)
    assert understood is not None
    assert pause.describe(understood, MONDAY_1120) == said


@pytest.mark.parametrize("text", ["", "soon", "16h75", "25h", "0 min", "9999h", "13pm"])
def test_nonsense_is_refused(text: str) -> None:
    assert pause.parse(text, MONDAY_1120) is None


def test_a_time_already_gone_is_tomorrow_and_days_are_named() -> None:
    friday = datetime(2026, 10, 16, 18, 0).timestamp()
    understood = pause.parse("9h", friday)
    assert understood is not None
    assert pause.clock(understood.until, friday) == "tomorrow at 9:00"
    in_two_days = datetime(2026, 10, 18, 9, 0).timestamp()
    assert pause.clock(in_two_days, friday) == "Sunday at 9:00"
