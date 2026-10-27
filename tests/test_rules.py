import random
from collections import Counter
from datetime import date, datetime

import pytest

from tagnan import progress
from tagnan.blueprint import Blueprint
from tagnan.model import parse_question
from tagnan.progress import GRADES, Progress, after_answer, after_review, grade_for
from tagnan.scheduler import PACES, Pace, Rhythm, Scheduler, find_pace
from tests.conftest import question_data


def test_blueprint_weights_add_up(bp: Blueprint) -> None:
    assert bp.code == "AIF-C01"
    assert [d.id for d in bp.domains] == [1, 2, 3, 4, 5]
    assert sum(d.weight for d in bp.domains) == 100
    assert bp.task_ids(3) == ("3.1", "3.2", "3.3", "3.4")


def test_question_is_checked(bp: Blueprint) -> None:
    q = parse_question(question_data(), bp)
    assert q.answers == (0,)
    assert q.why_wrong[0] == ""
    assert q.is_correct([0])
    assert not q.is_correct([1])
    assert not q.is_correct([0, 1])


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"domain": 9}, "unknown domain"),
        ({"task": "1.1"}, "not in domain"),
        ({"answers": [0, 1]}, "exactly one"),
        ({"answers": [4]}, "indices"),
        ({"choices": ["a", "b", "c"]}, "4 to 6"),
        ({"choices": ["a", "b", "A", "c"]}, "identical"),
        ({"why_wrong": ["", "x"]}, "one text per choice"),
        ({"why_wrong": ["", "", "x", "y"]}, "why_wrong: empty"),
        ({"kind": "multiple"}, "two or three"),
        ({"difficulty": "extreme"}, "unknown difficulty"),
        ({"stem": "x" * 1000}, "too long"),
    ],
)
def test_bad_questions_are_refused(bp: Blueprint, changes: dict[str, object], reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        parse_question(question_data(**changes), bp)


def test_shuffle_keeps_answers_and_reasons_together(bp: Blueprint) -> None:
    q = parse_question(question_data(), bp)
    for seed in range(20):
        s = q.shuffled(random.Random(seed))
        assert s.choices[s.answers[0]] == "Amazon Bedrock Guardrails"
        for choice, why in zip(s.choices, s.why_wrong, strict=True):
            assert why == q.why_wrong[q.choices.index(choice)]


def test_points_streaks_and_grades() -> None:
    p = Progress()
    p, delta = after_answer(p, True)
    assert (p.points, p.streak, delta) == (10, 1, 10)
    p, delta = after_answer(p, True)
    assert (p.points, delta) == (21, 11)  # +1 for each right answer in a row
    p, delta = after_answer(p, False)
    assert (p.points, p.streak, p.best_streak, delta) == (13, 0, 2, -8)
    p2, _ = after_answer(Progress(points=5), False)
    assert p2.points == 0


def test_streak_bonus_is_capped() -> None:
    p = Progress(streak=30)
    _, delta = after_answer(p, True)
    assert delta == progress.RIGHT + progress.MAX_BONUS


def test_a_miss_right_after_a_promotion_keeps_the_grade() -> None:
    gascon = GRADES[1].threshold
    p, _ = after_answer(Progress(points=gascon - 5), True)
    assert p.grade == 1
    p, _ = after_answer(p, False)
    assert p.points < gascon
    assert p.grade == 1


def test_grades_drop_one_at_a_time_past_the_margin() -> None:
    mousquetaire = GRADES[3].threshold  # band 1100 under it: margin 165
    assert grade_for(mousquetaire, 2) == 3
    assert grade_for(mousquetaire - 165, 3) == 3
    assert grade_for(mousquetaire - 166, 3) == 2
    capitaine = GRADES[5].threshold  # band 2400: margin 360
    assert grade_for(capitaine - 360, 5) == 5
    assert grade_for(capitaine - 361, 5) == 4
    assert grade_for(0, 5) == 4
    assert grade_for(100_000, 0) == 5


def test_a_grade_won_on_an_older_scale_is_settled() -> None:
    assert progress.settle(Progress(points=20, grade=1)).grade == 0
    assert progress.settle(Progress(points=100, grade=5)).grade == 0
    within_margin = Progress(points=GRADES[3].threshold - 100, grade=3)
    assert progress.settle(within_margin) == within_margin


def weeks_to_captain(accuracy: float, runs: int = 60, per_week: int = 100) -> float:
    """Median weeks to the last grade, answering per_week questions a week."""
    results = []
    for seed in range(runs):
        rng = random.Random(seed)
        p = Progress()
        answered = 0
        while p.grade < len(GRADES) - 1:
            p, _ = after_answer(p, rng.random() < accuracy)
            answered += 1
        results.append(answered / per_week)
    return sorted(results)[runs // 2]


def test_the_road_to_captain_is_long() -> None:
    assert 6 <= weeks_to_captain(0.8) <= 8.5
    assert 8.5 <= weeks_to_captain(0.7) <= 12
    assert weeks_to_captain(0.6) >= 14


def test_leitner_boxes() -> None:
    assert after_review(None, True) is None
    assert after_review(None, False) == 1
    assert after_review(1, True) == 2
    assert after_review(4, True) is None
    assert after_review(3, False) == 1


def test_rhythm_is_checked() -> None:
    with pytest.raises(ValueError, match="min_minutes"):
        Rhythm(min_minutes=30, max_minutes=10)
    with pytest.raises(ValueError, match="start_hour"):
        Rhythm(start_hour=20, end_hour=9)


def at(day: int, hour: int, minute: int = 0) -> float:
    # 2026-10-12 is a Monday.
    return datetime(2026, 10, day, hour, minute).timestamp()


def test_questions_come_within_working_hours() -> None:
    s = Scheduler(Rhythm(), random.Random(1), at(12, 10))
    assert at(12, 10, 8) <= s.next_at <= at(12, 10, 25)
    assert not s.due(at(12, 10, 7))
    assert s.due(s.next_at)
    s.asked(at(12, 18, 55))  # too late in the day: tomorrow morning
    tomorrow = datetime.fromtimestamp(s.next_at)
    assert (tomorrow.day, tomorrow.hour) == (13, 9)


def test_weekends_are_skipped_unless_wanted() -> None:
    s = Scheduler(Rhythm(), random.Random(2), at(16, 18, 50))  # Friday evening
    assert datetime.fromtimestamp(s.next_at).weekday() == 0  # Monday
    s = Scheduler(Rhythm(weekends=True), random.Random(2), at(16, 18, 50))
    assert datetime.fromtimestamp(s.next_at).weekday() == 5


def test_snooze_pause_and_resume() -> None:
    s = Scheduler(Rhythm(), random.Random(3), at(12, 10))
    s.snooze(at(12, 11))
    assert s.next_at == at(12, 11, 10)
    s.pause(at(12, 11), 60)
    assert not s.due(at(12, 11, 30))
    assert s.next_at >= at(12, 12)
    s.resume(at(12, 11, 30))
    assert s.paused_until == 0
    assert s.next_at <= at(12, 11, 30) + 25 * 60


def a_pace(key: str) -> Pace:
    found = find_pace(key)
    assert found is not None
    return found


def questions_a_day(chosen: Pace, rhythm: Rhythm, seed: int, weeks: int = 2) -> list[int]:
    """Questions asked each working day, each answered at once, from a Monday at the first
    working hour."""
    start = datetime(2026, 10, 12, rhythm.start_hour).timestamp()
    s = Scheduler(rhythm.paced(chosen), random.Random(seed), start)
    days: Counter[date] = Counter()
    while s.next_at < start + weeks * 7 * 86400:
        now = s.next_at
        assert s.due(now)
        days[datetime.fromtimestamp(now).date()] += 1
        s.asked(now)
    return list(days.values())


def test_paces_go_from_rarely_to_intensive_training() -> None:
    assert [(p.name, p.hint) for p in PACES] == [
        ("Rarely", "2 or 3 a day"),
        ("Now and then", "every 45 to 90 min"),
        ("Regularly", "every 8 to 25 min"),
        ("Often", "every 5 to 10 min"),
        ("Intensive training", "every 3 to 5 min"),
    ]
    assert Rhythm().pace is find_pace("regularly")  # the rhythm he always had
    assert Rhythm(min_minutes=2, max_minutes=3).pace is None  # gaps of one's own
    assert find_pace("whenever") is None
    intensive = a_pace("intensive")
    assert Rhythm().paced(intensive).pace is intensive


@pytest.mark.parametrize("hours", [(9, 19), (8, 20), (10, 16)])
def test_rarely_is_two_or_three_questions_a_day(hours: tuple[int, int]) -> None:
    rhythm = Rhythm(start_hour=hours[0], end_hour=hours[1])
    counts = [n for seed in range(30) for n in questions_a_day(a_pace("rarely"), rhythm, seed)]
    assert set(counts) == {2, 3}
    assert len(counts) == 30 * 10  # every working day, none at the weekend


def test_intensive_training_asks_every_three_to_five_minutes() -> None:
    intensive = a_pace("intensive")
    counts = questions_a_day(intensive, Rhythm(), seed=4, weeks=1)
    assert 120 <= min(counts) <= max(counts) <= 200
    s = Scheduler(Rhythm().paced(intensive), random.Random(5), at(12, 10))
    for _ in range(40):
        asked = s.next_at
        s.asked(asked)
        assert 3 * 60 <= s.next_at - asked <= 5 * 60


def test_a_new_pace_takes_effect_at_once_but_not_during_a_break() -> None:
    s = Scheduler(Rhythm().paced(a_pace("rarely")), random.Random(6), at(12, 10))
    assert s.next_at >= at(12, 13, 20)
    s.set_rhythm(s.rhythm.paced(a_pace("intensive")), at(12, 10, 30))
    assert at(12, 10, 33) <= s.next_at <= at(12, 10, 35)
    s.pause(at(12, 10, 30), 60)
    s.set_rhythm(s.rhythm.paced(a_pace("regularly")), at(12, 10, 40))
    assert s.next_at >= at(12, 11, 30)


def test_a_missed_question_does_not_call_back_soon_at_a_slow_pace() -> None:
    s = Scheduler(Rhythm().paced(a_pace("rarely")), random.Random(7), at(12, 10))
    s.missed(at(12, 10))
    assert s.next_at >= at(12, 13, 20)
    s.set_rhythm(s.rhythm.paced(a_pace("intensive")), at(12, 10))
    s.missed(at(12, 10))
    assert s.next_at == at(12, 10, 10)  # the snooze: longer than this pace's gaps


def test_other_hours_keep_the_pace() -> None:
    shorter = Rhythm().paced(a_pace("rarely")).at_hours(9, 13, False)
    assert shorter.pace is a_pace("rarely")
    assert (shorter.min_minutes, shorter.max_minutes) == (80, 120)  # 2 or 3 in four hours
    own = Rhythm(min_minutes=2, max_minutes=3).at_hours(8, 20, True)
    assert (own.min_minutes, own.max_minutes, own.weekends) == (2, 3, True)  # gaps of one's own
    with pytest.raises(ValueError, match="start_hour"):
        Rhythm().at_hours(18, 8, False)
    assert shorter.hours_hint == "Mon–Fri, 9–13"
    assert shorter.hours_sentence == "Weekdays, from 9:00 to 13:00"
    assert own.hours_hint == "Every day, 8–20"


def test_hours_kept_by_the_window_are_read_back_if_they_make_sense() -> None:
    kept = Rhythm().kept({"start": 7, "end": 15, "weekends": True})
    assert kept.hours == {"start": 7, "end": 15, "weekends": True}
    for saved in (
        None,
        [7, 15],
        {"start": 7, "end": 15},
        {"start": "7", "end": 15, "weekends": False},
        {"start": True, "end": 15, "weekends": False},
        {"start": 7.0, "end": 15, "weekends": False},
        {"start": 15, "end": 7, "weekends": False},
        {"start": 7, "end": 25, "weekends": False},
    ):
        assert Rhythm().kept(saved) == Rhythm(), saved
