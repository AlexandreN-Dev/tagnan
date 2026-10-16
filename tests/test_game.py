from pathlib import Path

import pytest

from tagnan import config
from tagnan.game import LOW_WATER, Game
from tagnan.progress import DAY, Progress
from tagnan.store import Store
from tests.conftest import question_data

NOW = 1_800_000_000.0


def fill(game: Game, count: int, **changes: object) -> list[int]:
    raw = [question_data(topic=f"notion {i}", **changes) for i in range(count)]
    ids, rejected = game.add_batch(raw, NOW)
    assert not rejected
    return ids


def test_batch_is_checked_and_shuffled(game: Game) -> None:
    raw = [question_data(topic=f"n{i}") for i in range(12)] + [question_data(answers=[9])]
    ids, rejected = game.add_batch(raw, NOW)
    assert len(ids) == 12
    assert rejected
    assert "question 13" in rejected[0]
    positions = {game.store.question(i).answers[0] for i in ids}
    assert len(positions) > 1  # the right answer is not always first
    for i in ids:
        q = game.store.question(i)
        assert q.choices[q.answers[0]] == "Amazon Bedrock Guardrails"


def test_answering_moves_points_reviews_and_the_bank(game: Game) -> None:
    ids = fill(game, LOW_WATER)
    assert not game.needs_questions()
    q = game.next_question(NOW)
    assert q is not None
    assert q.id in ids
    wrong = next(i for i in range(4) if i not in q.answers)
    outcome = game.answer(q, [wrong], NOW)
    assert not outcome.correct
    assert outcome.review_box == 1
    assert game.progress == Progress(points=0, streak=0, best_streak=0, grade=0)
    assert game.needs_questions()  # one fresh question fewer
    # The miss comes back the next day, and only then.
    assert game.store.due_reviews(game.exam, NOW + DAY / 2) == []
    assert [r.id for r in game.store.due_reviews(game.exam, NOW + DAY)] == [q.id]
    outcome = game.answer(q, q.answers, NOW + DAY)
    assert outcome.correct
    assert outcome.review_box == 2
    assert outcome.delta == 10


def test_reviews_are_asked_when_no_fresh_question_is_left(game: Game) -> None:
    (only,) = fill(game, 1)
    q = game.store.question(only)
    game.answer(q, [i for i in range(4) if i not in q.answers][:1], NOW)
    assert game.next_question(NOW) is None
    later = game.next_question(NOW + DAY)
    assert later is not None
    assert later.id == only


def test_flagged_questions_are_never_asked(game: Game) -> None:
    (only,) = fill(game, 1)
    game.store.flag(only)
    assert game.next_question(NOW) is None
    assert game.store.fresh_count(game.exam) == 0


def test_weak_domains_weigh_more(game: Game) -> None:
    ids = fill(game, 6, domain=1, task="1.1")
    for i in ids:
        q = game.store.question(i)
        game.answer(q, [a for a in range(4) if a not in q.answers][:1], NOW)
    weights = game.domain_weights()
    assert weights[1] / 20 > weights[2] / 24


def test_batch_request_follows_the_grade(game: Game) -> None:
    request = game.batch_request()
    assert request["exam"] == "aif-c01"
    assert len(request["slots"]) == 10
    assert {s["difficulty"] for s in request["slots"]} == {"facile"}
    assert {s["kind"] for s in request["slots"]} == {"single"}
    game.store.save_progress(game.exam, Progress(points=3700, grade=4))
    slots = game.batch_request()["slots"]
    assert {s["difficulty"] for s in slots} == {"difficile"}
    assert sum(s["kind"] == "multiple" for s in slots) == 2  # a quarter of ten, rounded


def test_progress_and_stats_survive_a_restart(tmp_path: Path, game: Game) -> None:
    store = Store(tmp_path / "tagnan.db")
    g = Game(store, game.blueprint, game._rng)
    (only,) = fill(g, 1)
    q = store.question(only)
    g.answer(q, q.answers, NOW)
    store.close()
    again = Game(Store(tmp_path / "tagnan.db"), game.blueprint, game._rng)
    assert again.progress.points == 10
    summary = again.summary()
    assert summary["answered"] == 1
    assert summary["right"] == 1
    assert summary["domains"][2]["answered"] == 1
    assert summary["next_name"] == "Gascon"


def test_config_defaults_and_errors(tmp_path: Path) -> None:
    assert config.load(tmp_path / "absent.toml") == config.Config()
    path = tmp_path / "config.toml"
    path.write_text('exam = "aif-c01"\n[rhythm]\nmin_minutes = 2\nmax_minutes = 3\n')
    assert config.load(path).rhythm.max_minutes == 3
    path.write_text("[rhythm]\nmin_minute = 2\n")
    with pytest.raises(ValueError, match="clé inconnue dans \\[rhythm\\] : min_minute"):
        config.load(path)
    path.write_text("[rhythm]\nmin_minutes = 30\n")
    with pytest.raises(ValueError, match="min_minutes"):
        config.load(path)
