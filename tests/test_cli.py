import json
import random
from pathlib import Path

import pytest

from tagnan import blueprint, cli
from tagnan.brain_client import BrainClient
from tagnan.game import Game
from tagnan.store import Store
from tests.conftest import WORDS, spanish, word_data


def test_without_a_brain_the_terminal_quiz_calls_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[brain]\nmodel = "none"\n', encoding="utf-8")

    def no_brain(self: BrainClient, *args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("nobody writes his questions")

    monkeypatch.setattr(BrainClient, "generate", no_brain)
    assert cli.main(["--db", str(tmp_path / "tagnan.db"), "--config", str(config)]) == 1
    assert "Bring him a catalogue: his menu, Catalogues." in capsys.readouterr().err


# --- A language course -------------------------------------------------------------------------


def a_language(db: Path) -> None:
    """A database whose course is Spanish, its eight words in store."""
    game = Game(Store(db), blueprint.load("aif-c01"), random.Random(1))
    course = spanish()
    game.set_course(course)
    game.add_cards(course, [word_data(i) for i in range(len(WORDS))], 0.0)
    game.store.close()


def typing(monkeypatch: pytest.MonkeyPatch, *lines: str) -> None:
    """What one types, line after line; then the end of input."""
    waiting = list(lines)

    def answer(_prompt: str = "") -> str:
        if not waiting:
            raise EOFError
        return waiting.pop(0)

    monkeypatch.setattr("builtins.input", answer)


def test_a_bout_in_the_terminal_shows_new_words_then_asks_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "tagnan.db"
    config = tmp_path / "config.toml"
    config.write_text('[brain]\nmodel = "none"\n', encoding="utf-8")
    a_language(db)
    typing(monkeypatch, "", "k")  # two new words: Enter, then "I know it already"
    assert cli.main(["--db", str(db), "--config", str(config)]) == 0
    out = capsys.readouterr().out
    assert "— A new word —\nmadrugar: to get up early" in out
    assert "Mañana tengo que madrugar. (I must rise early.)" in out
    store = Store(db)
    assert [store.card(i).step for i in (1, 2)] == [1, 4]
    # Later the same day they are asked: a meaning to pick, a word to type.
    store.move_card(1, 1, 0.0, 0.0)
    store.move_card(2, 4, 1.0, 0.0)
    for other in range(3, 9):
        store.move_card(other, 2, 4_000_000_000.0, 0.0)
    store.close()
    game = Game(Store(db), blueprint.load("aif-c01"), random.Random(1))
    touch = game.touch(game.next_bout(1.0e9)[0])
    game.store.close()
    right = "ABCD"[touch.choices.index("to get up early")]
    same = random.Random(1)  # the shuffle the touch above was built with
    monkeypatch.setattr(random, "Random", lambda: same)  # the one the terminal quiz makes
    typing(monkeypatch, "Z", right, "trasnochár")
    assert cli.main(["--db", str(db), "--config", str(config)]) == 0
    out = capsys.readouterr().out
    assert "madrugar: what does it mean?" in out
    assert "to stay up late: in Spanish?" in out
    assert "Mind the accent: trasnochar." in out
    assert "+3 points · 3 in all · step 2" in out
    assert "+3 points · 6 in all · step 5" in out
    assert cli.main(["--db", str(db), "--config", str(config), "--stats"]) == 0
    out = capsys.readouterr().out
    assert "Spanish: Tagnan is Inkwell, 6 points" in out
    assert "Words: 0 known, 8 on the ladder, 0 new in store" in out
    assert "1. Everyday life: 0/4 known" in out


def test_a_language_is_learned_in_the_terminal_at_ones_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked: list[tuple[str, object]] = []

    def plan(self: BrainClient, said: str, spoken: object = None, *_: object) -> dict[str, object]:
        asked.append((said, spoken))
        return {"understood": True, "course": spanish().to_dict()}

    monkeypatch.setattr(BrainClient, "plan", plan)
    args = ["--db", str(tmp_path / "tagnan.db"), "--config", str(tmp_path / "none.toml")]
    assert cli.main([*args, "--learn", "spanish"]) == 1
    assert "Spanish is a language: say your level" in capsys.readouterr().err
    assert asked == []
    assert (
        cli.main([*args, "--learn", "learn Spanish", "--level", "a2", "--speaks", "français"]) == 0
    )
    assert asked == [
        ("Spanish", {"learned": "Spanish", "level": "A2", "speaks": "French", "purpose": ""})
    ]
    assert "From now on, Tagnan teaches Spanish" in capsys.readouterr().out
    assert cli.main([*args, "--learn", "spanish"]) == 0  # the course one has, now
    assert len(asked) == 1
    # Words written by scripts/brain words, added by hand.
    batch = tmp_path / "words.json"
    batch.write_text(
        json.dumps({"words": [word_data(0), word_data(1, chapter=9)]}), encoding="utf-8"
    )
    assert cli.main([*args, "--import", str(batch)]) == 0
    assert "1 words added, 1 set aside." in capsys.readouterr().out
