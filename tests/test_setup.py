import io
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from tagnan import brain, config, setup, setup_ui
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
    return setup.Terminal(assume_yes=assume_yes, out=out, read=read, interactive=False), out


def keyboard(*keys: str, log: Path | None = None) -> tuple[setup.Terminal, io.StringIO]:
    """A terminal driven by keys, as setup_ui.read_key names them."""
    pressed: Iterator[str] = iter(keys)
    out = io.StringIO()
    return setup.Terminal(out=out, keys=lambda: next(pressed), interactive=True, log=log), out


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


def test_offered_models_hold_the_default() -> None:
    default = config.find_model(config.Brain.model)
    assert default is not None
    assert default.effort == config.Brain.effort
    for m in config.MODELS:
        assert m.effort in config.EFFORT_LEVELS
        assert m.label.startswith(m.name + ", effort ")


def test_account_tells_subscription_from_api_billing() -> None:
    assert setup.account({}) == (False, "not signed in")
    assert setup.account({"loggedIn": False, "authMethod": "claude.ai"})[0] is False
    team = {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "team"}
    assert setup.account(team) == (True, "team subscription")
    signed_in, detail = setup.account({"loggedIn": True, "authMethod": "console"})
    assert signed_in
    assert "API" in detail


def test_questions_take_the_default_on_enter_yes_or_end_of_input() -> None:
    term, _ = terminal("", "")
    assert term.confirm("Go?") is True
    assert term.select("Which?", [("a", ""), ("b", "")], 1) == 1
    term, _ = terminal(assume_yes=True)
    assert term.confirm("Go?", False) is False
    assert term.hour("When?", 9) == 9
    term, _ = terminal()  # no terminal left: defaults, no hang
    assert term.confirm("Go?") is True


def test_questions_insist_until_the_answer_makes_sense() -> None:
    term, out = terminal("maybe", "n", "7", "2", "25", "18h")
    assert term.confirm("Go?") is False
    assert term.select("Which?", [("a", ""), ("b", "")]) == 1
    assert term.hour("Until?", 19) == 18
    text = out.getvalue()
    assert "Answer y or n." in text
    assert "A number from 1 to 2." in text
    assert "An hour from 0 to 24" in text


def test_no_colour_outside_a_terminal() -> None:
    term, out = terminal()
    term.intro("Tagnan", "guided setup")
    term.done("WSL", "Ubuntu")
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


def test_arrow_keys_choose_and_the_answer_stays_on_the_rail() -> None:
    term, out = keyboard("down", "down", "up", "enter")
    assert term.select("Which model?", [("Opus", "finest"), ("Sonnet", "quick")]) == 1
    term2, _ = keyboard("3")
    assert term2.select("Pace?", [("a", ""), ("b", ""), ("c", "")]) == 2
    text = out.getvalue()
    assert "◇  Which model?" in text
    assert "◇  Which model?  Sonnet\n" in text


def test_confirm_with_arrows_or_a_letter() -> None:
    term, _ = keyboard("right", "enter")
    assert term.confirm("Install it?") is False
    term, _ = keyboard("y")
    assert term.confirm("Install it?", False) is True
    term, _ = keyboard("interrupt")
    with pytest.raises(KeyboardInterrupt):
        term.confirm("Install it?")


def test_hour_typed_with_a_hint_on_a_wrong_one() -> None:
    term, out = keyboard("3", "0", "enter", "backspace", "backspace", "1", "8", "h", "enter")
    assert term.hour("Until what hour?", 19) == 18
    assert "An hour from 0 to 24" in out.getvalue()
    term, _ = keyboard("enter")
    assert term.hour("From what hour?", 9) == 9


def test_a_failed_step_shows_its_tail_and_keeps_the_rest_in_the_log(tmp_path: Path) -> None:
    log = tmp_path / "setup.log"
    term, out = keyboard(log=log)
    command = ["sh", "-c", "for i in $(seq 1 30); do echo line$i; done; echo boom >&2; exit 3"]
    done, seconds = term.task("Installing", command)
    assert done.returncode == 3
    assert seconds >= 0
    text = out.getvalue()
    assert "■  Installing" in text
    assert "boom" in text
    assert "line30" in text
    assert "line1\n" not in text  # only the tail on screen
    assert "line1\n" in log.read_text()
    ok, _ = term.task("Listing", ["true"])
    assert ok.returncode == 0


def test_plain_glyphs_where_the_terminal_cannot_show_them() -> None:
    out = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
    term = setup_ui.Terminal(out=out, interactive=False)
    assert term.g is setup_ui.ASCII


def test_hours_offered_are_those_of_his_menu_and_answers_go_where_he_reads_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = tmp_path / "settings.json"
    window.write_text('{"pace": "often", "hours": {"start": 7, "end": 15, "weekends": true}}')
    monkeypatch.setattr(setup, "config_file", lambda: tmp_path / "config.toml")
    monkeypatch.setattr(setup.Setup, "window_settings", lambda self: window)
    monkeypatch.setattr(setup, "exams", lambda: ["aif-c01"])
    # The model, From (Enter: his menu's 7), Until, weekends, the pace.
    term, _ = terminal("", "", "18", "n", "")
    setup.Setup(term, check=False, mac=True).settings()
    rhythm = config.load(tmp_path / "config.toml").rhythm
    assert (rhythm.start_hour, rhythm.end_hour, rhythm.weekends) == (7, 18, False)
    saved = json.loads(window.read_text())
    assert saved == {"pace": "often", "hours": {"start": 7, "end": 18, "weekends": False}}
