import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tagnan import brain, config
from tagnan.blueprint import Blueprint
from tagnan.brain_client import BrainClient, BrainError, decode
from tests.conftest import question_data

FAKE_CLAUDE = """#!/usr/bin/env python3
import json, os, sys
log = os.environ.get("TAGNAN_TEST_LOG") or os.path.join(os.environ["HOME"], "fake-claude.json")
json.dump({"argv": sys.argv[1:], "env": dict(os.environ), "cwd": os.getcwd(),
           "stdin": sys.stdin.read()}, open(log, "w"))
print(open(os.path.join(os.environ["HOME"], "fake-answer.json")).read())
"""


@pytest.fixture
def fake_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A claude that records how it was called and prints fake-answer.json."""
    program = tmp_path / "claude"
    program.write_text(FAKE_CLAUDE)
    program.chmod(0o755)
    monkeypatch.setenv("TAGNAN_CLAUDE", str(program))
    monkeypatch.setenv("HOME", str(tmp_path))
    # What must not reach claude.
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("AWS_PROFILE", "prod")
    return tmp_path


def answer(home: Path, structured: object, **result: object) -> None:
    payload = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "",
        "structured_output": structured,
        **result,
    }
    (home / "fake-answer.json").write_text(json.dumps(payload))


def call_log(home: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads((home / "fake-claude.json").read_text())
    return data


def test_generate_runs_claude_isolated(fake_claude: Path) -> None:
    good, bad = question_data(), question_data(answers=[1, 2])
    answer(fake_claude, {"questions": [good, bad]})
    request = {
        "exam": "aif-c01",
        "slots": [{"domain": 3, "difficulty": "moyen", "kind": "single"}],
        "avoid": ["Bedrock Guardrails"],
    }
    result = brain.generate(request, config.Config())
    assert result["questions"] == [good]
    assert "question 2" in result["rejected"][0]
    log = call_log(fake_claude)
    argv = log["argv"]
    assert isinstance(argv, list)
    for flag in ("-p", "--no-session-persistence", "--strict-mcp-config", "--json-schema"):
        assert flag in argv
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert argv[argv.index("--settings") + 1] == '{"disableAllHooks": true}'
    env = log["env"]
    assert isinstance(env, dict)
    assert "CLAUDECODE" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "AWS_PROFILE" not in env
    assert "tagnan-brain-" in str(log["cwd"])
    prompt = str(log["stdin"])
    assert "domaine 3 (Applications des modèles de fondation)" in prompt
    assert "- Bedrock Guardrails" in prompt
    assert "$" not in prompt  # every placeholder filled


def test_explain_returns_text(fake_claude: Path) -> None:
    answer(fake_claude, {"text": "  Mordieu ! Guardrails,\n c'est le garde-fou. "})
    request = {"exam": "aif-c01", "question": question_data(), "chosen": [3]}
    assert brain.explain(request, config.Config()) == {
        "text": "Mordieu ! Guardrails, c'est le garde-fou."
    }
    prompt = str(call_log(fake_claude)["stdin"])
    assert "Réponse donnée : D (Amazon SageMaker Clarify)" in prompt
    assert "Bonne réponse : A (Amazon Bedrock Guardrails)" in prompt


def test_claude_errors_become_messages(fake_claude: Path) -> None:
    answer(fake_claude, None, is_error=True, subtype="error", result="usage limit reached")
    with pytest.raises(brain.BrainError, match="usage limit"):
        brain.explain({"question": question_data(), "chosen": [1]}, config.Config())
    answer(fake_claude, {"questions": [question_data(kind="poème")]})
    with pytest.raises(brain.BrainError, match="aucune question utilisable"):
        brain.generate(
            {"slots": [{"domain": 1, "difficulty": "facile", "kind": "single"}]}, config.Config()
        )


def test_prompt_lists_slots_and_only_their_domains(bp: Blueprint) -> None:
    slots = [{"domain": 2, "difficulty": "facile", "kind": "single"}] * 3 + [
        {"domain": 5, "difficulty": "facile", "kind": "multiple"}
    ]
    prompt = brain.generate_prompt(bp, slots, [])
    assert "Écris 4 questions" in prompt
    assert (
        "- 3 questions du domaine 2 (Fondamentaux de l'IA générative), faciles, à réponse unique"
        in prompt
    )
    assert "à réponses multiples" in prompt
    assert "5.2 Reconnaître" in prompt
    assert "3.2 Choisir" not in prompt
    assert "déjà été posées" not in prompt


def test_script_runs_the_brain_end_to_end(fake_claude: Path) -> None:
    answer(fake_claude, {"text": "Touché."})
    repo = Path(__file__).resolve().parent.parent
    env = {**os.environ, "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}"}
    client = BrainClient.local(repo)
    request = {"exam": "aif-c01", "question": question_data(), "chosen": [2]}
    try:
        assert client.explain(request, timeout=60) == "Touché."
    except BrainError as error:  # no uv-managed Python 3.12 here: say so rather than fail
        pytest.skip(f"scripts/brain indisponible : {error}")
    finally:
        del env


def test_client_reports_the_brain_error(tmp_path: Path) -> None:
    script = tmp_path / "brain"
    script.write_text("#!/bin/sh\necho 'cerveau : claude introuvable' >&2\nexit 1\n")
    script.chmod(0o755)
    with pytest.raises(BrainError, match="claude introuvable"):
        BrainClient((str(script),)).explain({}, timeout=10)


def test_wsl_command_and_utf16_messages() -> None:
    client = BrainClient.through_wsl("Ubuntu", "/home/me/tagnan/")
    assert client.command == ("wsl.exe", "-d", "Ubuntu", "-e", "/home/me/tagnan/scripts/brain")
    assert decode("Distribution introuvable".encode("utf-16-le")) == "Distribution introuvable"
    assert decode("é".encode()) == "é"


@pytest.mark.live
def test_live_generation_writes_usable_questions(bp: Blueprint) -> None:
    """Calls the real claude CLI with Sonnet: a few cents of quota."""
    request = {
        "exam": "aif-c01",
        "slots": [{"domain": 3, "difficulty": "moyen", "kind": "single"}],
        "avoid": [],
    }
    done = subprocess.run(
        [str(Path(__file__).resolve().parent.parent / "scripts" / "brain"), "generate"],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["questions"]
