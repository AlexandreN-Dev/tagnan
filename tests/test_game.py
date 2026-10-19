import random
import sqlite3
from pathlib import Path

import pytest

from tagnan import blueprint, config
from tagnan.blueprint import Blueprint
from tagnan.game import LOW_WATER, Game
from tagnan.progress import DAY, Progress
from tagnan.store import Store
from tagnan.subject import Subject
from tagnan.subject import parse as parse_subject
from tests.conftest import pottery_data, pottery_question, question_data

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
    assert {s["difficulty"] for s in request["slots"]} == {"easy"}
    assert {s["kind"] for s in request["slots"]} == {"single"}
    game.store.save_progress(game.exam, Progress(points=3700, grade=4))
    slots = game.batch_request()["slots"]
    assert {s["difficulty"] for s in slots} == {"hard"}
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
    with pytest.raises(ValueError, match="unknown key in \\[rhythm\\]: min_minute"):
        config.load(path)
    path.write_text("[rhythm]\nmin_minutes = 30\n")
    with pytest.raises(ValueError, match="min_minutes"):
        config.load(path)
    path.write_text('[brain]\nmodel = "sonnet"\nexplain_effort = "low"\n')
    assert config.load(path).brain == config.Brain(model="sonnet", explain_effort="low")
    path.write_text('[brain]\neffort = "maximal"\n')
    with pytest.raises(ValueError, match="\\[brain\\]: effort must be one of"):
        config.load(path)


def test_he_keeps_to_the_subject_until_told_otherwise(game: Game) -> None:
    fill(game, 3)
    rag = [question_data(topic=f"rag {i}") for i in range(3)]
    rag_ids, _ = game.add_batch(rag, NOW, "RAG")
    assert game.subject.whole
    assert game.fresh_count() == 6
    game.set_subject(parse_subject("rag", game.blueprint))
    assert game.subject == Subject(text="rag")
    assert game.fresh_count() == 3
    asked = {q.id for q in (game.next_question(NOW) for _ in range(20)) if q}
    assert asked <= set(rag_ids)
    # A review of another subject waits for its turn.
    other = next(q for q in game.store.fresh(game.exam) if q.id not in rag_ids)
    game.answer(other, [i for i in range(4) if i not in other.answers][:1], NOW)
    assert all(q and q.id in rag_ids for q in (game.next_question(NOW + DAY) for _ in range(20)))
    game.set_subject(Subject(domain=1))
    assert game.next_question(NOW) is None  # every question so far is in domain 3
    assert game.summary()["subject"] == "Domain 1 · Fundamentals of AI and ML"


def test_batches_are_written_for_the_subject(game: Game) -> None:
    game.add_batch([question_data(topic="chunking")], NOW, "RAG")
    game.add_batch([question_data(topic="guardrails")], NOW)
    game.set_subject(Subject(domain=2))
    request = game.batch_request()
    assert request["subject"] == "domain:2"
    assert {s["domain"] for s in request["slots"]} == {2}
    game.set_subject(Subject(text="RAG"))
    request = game.batch_request()
    assert request["subject"] == "RAG"
    assert {s["domain"] for s in request["slots"]} == {None}
    assert request["avoid"] == ["chunking"]  # the notions of this subject only
    game.set_subject(Subject())
    request = game.batch_request()
    assert request["subject"] == ""
    assert None not in {s["domain"] for s in request["slots"]}
    assert game.store.subjects(game.exam) == ["RAG"]


def test_an_older_database_gains_the_subject(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.executescript(
        "CREATE TABLE questions (id INTEGER PRIMARY KEY, exam TEXT NOT NULL, domain INTEGER"
        " NOT NULL, task TEXT NOT NULL, topic TEXT NOT NULL, difficulty TEXT NOT NULL, kind TEXT"
        " NOT NULL, stem TEXT NOT NULL, choices TEXT NOT NULL, answers TEXT NOT NULL,"
        " explanation TEXT NOT NULL, why_wrong TEXT NOT NULL, reference TEXT NOT NULL,"
        " created_at REAL NOT NULL, flagged INTEGER NOT NULL DEFAULT 0, lang TEXT NOT NULL"
        " DEFAULT 'fr');"
        "INSERT INTO questions VALUES (1, 'aif-c01', 3, '3.1', 't', 'easy', 'single', 's',"
        ' \'["a","b","c","d"]\', \'[0]\', \'e\', \'["","x","y","z"]\', \'\', 0, 0, \'en\');'
    )
    db.commit()
    db.close()
    store = Store(path)
    assert store.question(1).subject == ""


def test_a_course_drawn_up_is_kept_and_found_again(tmp_path: Path, bp: Blueprint) -> None:
    path = tmp_path / "tagnan.db"
    game = Game(Store(path), bp, random.Random(1))
    assert game.courses() == [bp]
    game.set_course(blueprint.from_dict(pottery_data()))
    ids, rejected = game.add_batch([pottery_question()], NOW)
    assert ids
    assert not rejected
    assert game.batch_request()["course"]["name"] == "Pottery"
    assert game.topic() == "Pottery"
    game.set_subject(parse_subject("glazes", game.blueprint))
    assert game.topic() == "glazes (Pottery)"

    again = Game(Store(path), bp, random.Random(1))
    assert again.exam == "pottery"
    assert [c.key for c in again.courses()] == ["pottery", "aif-c01"]
    assert again.find_course(" pottery. ") == again.blueprint
    assert again.find_course("aws certified ai practitioner") == bp
    assert again.find_course("history") is None
    assert again.subject == Subject(text="glazes")
    # Each course keeps its questions apart.
    again.set_course(bp)
    assert again.store.fresh(again.exam) == []
    assert again.add_batch([question_data()], NOW, course="nowhere") == (
        [],
        ["unknown course: nowhere"],
    )


def test_a_course_put_away_keeps_its_progress_and_comes_back(tmp_path: Path, bp: Blueprint) -> None:
    game = Game(Store(tmp_path / "tagnan.db"), bp, random.Random(1))
    game.set_course(blueprint.from_dict(pottery_data()))
    game.store.save_progress("pottery", Progress(points=500, grade=1))
    with pytest.raises(ValueError, match="the course learned now"):
        game.put_away("pottery")  # not the course learned now
    with pytest.raises(KeyError):
        game.put_away("nowhere")
    game.set_course(bp)
    game.put_away("pottery")
    assert [c.key for c in game.courses()] == ["aif-c01"]
    again = Game(Store(tmp_path / "tagnan.db"), bp, random.Random(1))
    assert [c.key for c in again.courses()] == ["aif-c01"]
    # Learning it again finds it, and brings it back with its grade.
    found = again.find_course("Pottery")
    assert found is not None
    again.set_course(found)
    assert again.progress.grade == 1
    assert [c.key for c in again.courses()] == ["pottery", "aif-c01"]
    # A course of exam/ can be put away too, and undone.
    again.put_away("aif-c01")
    assert [c.key for c in again.courses()] == ["pottery"]
    again.bring_back("aif-c01")
    assert [c.key for c in again.courses()] == ["pottery", "aif-c01"]
