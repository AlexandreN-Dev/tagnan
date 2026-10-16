import io
from collections.abc import Iterator
from pathlib import Path

import pytest

from tagnan import brain, config, setup
from tests.test_brain import answer, call_log, fake_claude

__all__ = ["fake_claude"]


def terminal(*answers: str, assume_yes: bool = False) -> tuple[setup.Terminal, io.StringIO]:
    typed: Iterator[str] = iter(answers)

    def read(prompt: str) -> str:
        try:
            return next(typed)
        except StopIteration:
            raise EOFError from None

    out = io.StringIO()
    return setup.Terminal(assume_yes=assume_yes, out=out, read=read), out


def test_config_text_reads_back_to_the_choices(tmp_path: Path) -> None:
    choices = setup.Choices("aif-c01", "claude-sonnet-5-5", "high", 8, 18, True)
    path = tmp_path / "config.toml"
    path.write_text(setup.config_text(choices), encoding="utf-8")
    loaded = config.load(path)
    assert loaded.exam == "aif-c01"
    assert (loaded.rhythm.start_hour, loaded.rhythm.end_hour, loaded.rhythm.weekends) == (
        8,
        18,
        True,
    )
    assert loaded.brain == config.Brain("claude-sonnet-5-5", "claude-sonnet-5-5", "high", "high")


def test_offered_models_start_with_the_default() -> None:
    model, effort, _, _ = setup.MODELS[0]
    assert (model, effort) == (config.Brain.model, config.Brain.effort)
    for _, effort, _, _ in setup.MODELS:
        assert effort in config.EFFORT_LEVELS


def test_account_tells_subscription_from_api_billing() -> None:
    assert setup.account({}) == (False, "pas connecté")
    assert setup.account({"loggedIn": False, "authMethod": "claude.ai"})[0] is False
    team = {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "team"}
    assert setup.account(team) == (True, "abonnement team")
    signed_in, detail = setup.account({"loggedIn": True, "authMethod": "console"})
    assert signed_in
    assert "API" in detail


def test_questions_take_the_default_on_enter_yes_or_end_of_input() -> None:
    term, _ = terminal("", "")
    assert term.yes("Go?") is True
    assert term.choose("Which?", [("a", ""), ("b", "")], 1) == 1
    term, _ = terminal(assume_yes=True)
    assert term.yes("Go?", False) is False
    assert term.hour("When?", 9) == 9
    term, _ = terminal()  # no terminal left: defaults, no hang
    assert term.yes("Go?") is True


def test_questions_insist_until_the_answer_makes_sense() -> None:
    term, out = terminal("peut-être", "n", "7", "2", "25", "18h")
    assert term.yes("Go?") is False
    assert term.choose("Which?", [("a", ""), ("b", "")]) == 1
    assert term.hour("Until?", 19) == 18
    text = out.getvalue()
    assert "Réponds o ou n." in text
    assert "Un nombre de 1 à 2." in text
    assert "Une heure de 0 à 24" in text


def test_no_colour_outside_a_terminal() -> None:
    term, out = terminal()
    term.banner()
    term.ok("WSL", "Ubuntu")
    assert "\033[" not in out.getvalue()
    assert "Tagnan" in out.getvalue()


def test_brain_check_is_one_cheap_call(fake_claude: Path) -> None:
    answer(fake_claude, {"ok": True})
    cfg = config.Config(brain=config.Brain(model="claude-sonnet-5-5"))
    assert brain.check(cfg) == {"ok": True, "model": "claude-sonnet-5-5"}
    argv = call_log(fake_claude)["argv"]
    assert isinstance(argv, list)
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5-5"
    assert argv[argv.index("--effort") + 1] == "low"
    assert "--strict-mcp-config" in argv
    answer(fake_claude, {"ok": False})
    with pytest.raises(brain.BrainError, match="oddly"):
        brain.check(cfg)


def test_brain_check_reads_no_request(fake_claude: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    answer(fake_claude, {"ok": True})
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert brain.main(["check", "--config", str(fake_claude / "none.toml")]) == 0
