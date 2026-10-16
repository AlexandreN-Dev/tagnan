import random
from datetime import datetime

import pytest

from tagnan import progress
from tagnan.blueprint import Blueprint
from tagnan.model import parse_question
from tagnan.progress import GRADES, Progress, after_answer, after_review, grade_for
from tagnan.scheduler import Rhythm, Scheduler
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
        ({"domain": 9}, "domaine"),
        ({"task": "1.1"}, "tâche"),
        ({"answers": [0, 1]}, "exactement une"),
        ({"answers": [4]}, "indices"),
        ({"choices": ["a", "b", "c"]}, "4 à 6"),
        ({"choices": ["a", "b", "A", "c"]}, "identiques"),
        ({"why_wrong": ["", "x"]}, "un texte par choix"),
        ({"why_wrong": ["", "", "x", "y"]}, "pourquoi"),
        ({"kind": "multiple"}, "deux ou trois"),
        ({"difficulty": "extrême"}, "difficulté"),
        ({"stem": "x" * 1000}, "trop long"),
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
    assert (p.points, p.grade, delta) == (22, 1, 12)  # streak bonus, Gascon from 20
    p, delta = after_answer(p, False)
    assert (p.points, p.streak, p.best_streak, delta) == (14, 0, 2, -8)
    assert p.grade == 1  # one miss right after the promotion keeps the grade
    p, _ = after_answer(p, False)
    assert (p.points, p.grade) == (6, 1)  # 20 - 16 = 4: still within the margin
    p, _ = after_answer(p, False)
    assert (p.points, p.grade) == (0, 0)
    p2, _ = after_answer(Progress(points=5), False)
    assert p2.points == 0


def test_streak_bonus_is_capped() -> None:
    p = Progress(streak=30)
    _, delta = after_answer(p, True)
    assert delta == progress.RIGHT + progress.MAX_BONUS


def test_grades_drop_one_at_a_time_past_the_margin() -> None:
    mousquetaire = GRADES[3].threshold  # 140, band 80 under it: margin max(12, 16) = 16
    assert grade_for(mousquetaire, 2) == 3
    assert grade_for(mousquetaire - 16, 3) == 3
    assert grade_for(mousquetaire - 17, 3) == 2
    capitaine = GRADES[5].threshold  # 420, band 160: margin 24
    assert grade_for(capitaine - 24, 5) == 5
    assert grade_for(capitaine - 25, 5) == 4
    assert grade_for(0, 5) == 4
    assert grade_for(1000, 0) == 5


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
