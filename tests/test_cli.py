from pathlib import Path

import pytest

from tagnan import cli
from tagnan.brain_client import BrainClient


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
