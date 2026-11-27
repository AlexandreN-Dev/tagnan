import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tagnan import blueprint, brain, config
from tagnan.blueprint import Blueprint
from tagnan.brain_client import BrainClient, BrainError, decode
from tests.conftest import (
    pottery_data,
    pottery_question,
    question_data,
    sheet_data,
    spanish,
    word_data,
)

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
        "slots": [{"domain": 3, "difficulty": "medium", "kind": "single"}],
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
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5"
    assert argv[argv.index("--effort") + 1] == "max"
    assert argv[argv.index("--settings") + 1] == '{"disableAllHooks": true}'
    env = log["env"]
    assert isinstance(env, dict)
    assert "CLAUDECODE" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "AWS_PROFILE" not in env
    assert "tagnan-brain-" in str(log["cwd"])
    prompt = str(log["stdin"])
    assert "from domain 3 (Applications of Foundation Models)" in prompt
    assert "- Bedrock Guardrails" in prompt
    assert "$" not in prompt  # every placeholder filled


def test_generate_takes_the_model_chosen_in_his_menu(fake_claude: Path) -> None:
    answer(fake_claude, {"questions": [question_data()]})
    slots = [{"domain": 3, "difficulty": "medium", "kind": "single"}]
    request = {"exam": "aif-c01", "slots": slots, "model": "claude-haiku-5-5"}
    brain.generate(request, config.Config())
    argv = call_log(fake_claude)["argv"]
    assert isinstance(argv, list)
    assert argv[argv.index("--model") + 1] == "claude-haiku-5-5"
    assert argv[argv.index("--effort") + 1] == "high"  # the model's own, not the config's
    with pytest.raises(brain.BrainError, match="unknown model"):
        brain.generate({**request, "model": "gpt-4"}, config.Config())


def test_explain_returns_text(fake_claude: Path) -> None:
    answer(fake_claude, {"text": "  Sacrebleu! Guardrails,\n is the guard rail. "})
    request = {"exam": "aif-c01", "question": question_data(), "chosen": [3]}
    assert brain.explain(request, config.Config()) == {
        "text": "Sacrebleu! Guardrails, is the guard rail."
    }
    prompt = str(call_log(fake_claude)["stdin"])
    assert "Answer given: D (Amazon SageMaker Clarify)" in prompt
    assert "Right answer: A (Amazon Bedrock Guardrails)" in prompt


def test_a_study_sheet_is_written_by_tell_me_mores_model(fake_claude: Path) -> None:
    answer(fake_claude, sheet_data(title="  RAG   or **fine-tuning**? "))
    cfg = config.Config(
        brain=config.Brain(explain_model="claude-sonnet-5-5", explain_effort="high")
    )
    sheet = brain.sheet({"exam": "aif-c01", "question": question_data()}, cfg)
    assert sheet["title"] == "RAG or fine-tuning?"
    assert len(sheet["versus"]["rows"]) == 3
    assert [s["name"] for s in sheet["steps"]["list"]] == ["Chunk", "Embed", "Retrieve", "Answer"]
    log = call_log(fake_claude)
    argv = log["argv"]
    assert isinstance(argv, list)
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5-5"
    assert argv[argv.index("--effort") + 1] == "high"
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert set(schema["required"]) >= {"title", "tagline", "versus", "steps", "terms", "trap"}
    prompt = str(log["stdin"])
    assert prompt.startswith("Make an explanatory PDF of this subject.")
    assert "as little text as possible" in prompt
    assert "Right answer: A (Amazon Bedrock Guardrails)" in prompt
    assert "AWS Certified AI Practitioner (AIF-C01)" in prompt


def test_a_sheet_with_neither_comparison_nor_steps_is_refused(fake_claude: Path) -> None:
    empty = sheet_data(
        versus={"left": {}, "right": {}, "rows": []}, steps={"title": "", "list": []}
    )
    answer(fake_claude, empty)
    with pytest.raises(brain.BrainError, match="neither a comparison nor steps"):
        brain.sheet({"exam": "aif-c01", "question": question_data()}, config.Config())


def test_the_account_is_what_claude_says_of_its_login(fake_claude: Path) -> None:
    status = {
        "loggedIn": True,
        "authMethod": "claude.ai",
        "email": "athos@example.com",
        "orgName": "Example Org",
        "subscriptionType": "max",
    }
    (fake_claude / "fake-answer.json").write_text(json.dumps(status))
    assert brain.account() == {
        "signedIn": True,
        "email": "athos@example.com",
        "org": "Example Org",
        "plan": "Max",
    }
    log = call_log(fake_claude)
    assert log["argv"] == ["auth", "status", "--json"]  # no model called, no quota spent
    env = log["env"]
    assert isinstance(env, dict)
    assert "ANTHROPIC_API_KEY" not in env
    assert "CLAUDECODE" not in env
    # Nobody signed in: said so, and nothing of an earlier login.
    (fake_claude / "fake-answer.json").write_text(
        json.dumps({"loggedIn": False, "email": "old@example.com"})
    )
    assert brain.account() == {"signedIn": False, "email": "", "org": "", "plan": ""}
    # A login without an address or a plan.
    (fake_claude / "fake-answer.json").write_text(json.dumps({"loggedIn": True, "email": None}))
    assert brain.account() == {"signedIn": True, "email": "", "org": "", "plan": ""}
    (fake_claude / "fake-answer.json").write_text("Unknown command")
    with pytest.raises(brain.BrainError, match="did not say who"):
        brain.account()


def test_the_brain_script_says_the_account(
    fake_claude: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (fake_claude / "fake-answer.json").write_text(
        json.dumps({"loggedIn": True, "email": "athos@example.com", "subscriptionType": "team"})
    )
    assert brain.main(["account", "--config", str(fake_claude / "none.toml")]) == 0
    said = json.loads(capsys.readouterr().out)
    assert (said["email"], said["plan"]) == ("athos@example.com", "Team")


def test_claude_errors_become_messages(fake_claude: Path) -> None:
    answer(fake_claude, None, is_error=True, subtype="error", result="usage limit reached")
    with pytest.raises(brain.BrainError, match="usage limit"):
        brain.explain({"question": question_data(), "chosen": [1]}, config.Config())
    answer(fake_claude, {"questions": [question_data(kind="poem")]})
    with pytest.raises(brain.BrainError, match="no usable question"):
        brain.generate(
            {"slots": [{"domain": 1, "difficulty": "easy", "kind": "single"}]}, config.Config()
        )


def test_prompt_lists_slots_and_only_their_domains(bp: Blueprint) -> None:
    slots = [{"domain": 2, "difficulty": "easy", "kind": "single"}] * 3 + [
        {"domain": 5, "difficulty": "easy", "kind": "multiple"}
    ]
    prompt = brain.generate_prompt(bp, slots, [])
    assert "Write 4 practice questions" in prompt
    assert (
        "- 3 easy single-answer questions from domain 2 (Fundamentals of Generative AI)" in prompt
    )
    assert "multiple-answer" in prompt
    assert "5.2 Recognize governance" in prompt
    assert "3.2 Choose effective" not in prompt
    assert "asked recently" not in prompt


def test_a_subject_of_ones_own_leaves_the_domain_to_the_brain(bp: Blueprint) -> None:
    slots = [{"domain": None, "difficulty": "medium", "kind": "single"}] * 4
    prompt = brain.generate_prompt(bp, slots, [], "RAG")
    assert "- 4 medium single-answer questions, from the domain of your choice" in prompt
    assert 'the subject the learner chose: "RAG"' in prompt
    assert "1.1 Explain basic AI concepts" in prompt  # every domain is shown
    assert "5.2 Recognize governance" in prompt
    assert "learner chose" not in brain.generate_prompt(bp, slots[:1], [])


def test_the_batch_says_which_subject_it_was_written_for(fake_claude: Path) -> None:
    answer(fake_claude, {"questions": [question_data()]})
    request = {
        "exam": "aif-c01",
        "slots": [{"domain": None, "difficulty": "medium", "kind": "single"}],
        "subject": "RAG",
    }
    assert brain.generate(request, config.Config())["subject"] == "RAG"
    assert '"RAG"' in str(call_log(fake_claude)["stdin"])
    request = {**request, "subject": "domain:3"}  # a domain: no subject paragraph
    assert brain.generate(request, config.Config())["subject"] == "domain:3"
    assert "learner chose" not in str(call_log(fake_claude)["stdin"])


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
    script.write_text("#!/bin/sh\necho 'brain: claude not found' >&2\nexit 1\n")
    script.chmod(0o755)
    with pytest.raises(BrainError, match="claude not found"):
        BrainClient((str(script),)).explain({}, timeout=10)


def test_wsl_command_and_utf16_messages() -> None:
    client = BrainClient.through_wsl("Ubuntu", "/home/me/tagnan/")
    assert client.command == ("wsl.exe", "-d", "Ubuntu", "-e", "/home/me/tagnan/scripts/brain")
    assert decode("Distribution not found".encode("utf-16-le")) == "Distribution not found"
    assert decode("é".encode()) == "é"


@pytest.mark.live
def test_live_generation_writes_usable_questions(bp: Blueprint) -> None:
    """Calls the real claude CLI with Sonnet: a few cents of quota."""
    request = {
        "exam": "aif-c01",
        "slots": [{"domain": 3, "difficulty": "medium", "kind": "single"}],
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


@pytest.mark.live
def test_live_study_sheet_is_usable() -> None:
    """Calls the real claude CLI with Sonnet at low effort, schema and all: a few cents."""
    cfg = config.Config(brain=config.Brain(explain_model="claude-sonnet-5-5", explain_effort="low"))
    sheet = brain.sheet({"exam": "aif-c01", "question": question_data()}, cfg)
    assert sheet["title"]
    assert sheet["tagline"]
    assert sheet["versus"] or sheet["steps"]


def test_any_course_travels_with_the_request_and_leaves_aws_out(fake_claude: Path) -> None:
    answer(fake_claude, {"questions": [pottery_question()]})
    request = {
        "course": pottery_data(),
        "slots": [{"domain": 2, "difficulty": "easy", "kind": "single"}],
    }
    result = brain.generate(request, config.Config())
    assert result["course"] == "pottery"
    assert len(result["questions"]) == 1
    log = call_log(fake_claude)
    argv = [str(a) for a in log["argv"]]  # type: ignore[attr-defined]
    system = argv[argv.index("--system-prompt") + 1]
    assert "helps someone learn Pottery." in system
    assert "Ask about techniques every potter agrees on." in system
    prompt = str(log["stdin"])
    assert "questions to learn Pottery" in prompt
    assert "Clay and Glazes for the Potter" in prompt
    assert "AWS" not in system + prompt
    explained = brain.explain_prompt(blueprint.from_dict(pottery_data()), pottery_question(), [1])
    assert explained.startswith("Someone learning Pottery got")
    assert "exam day" not in explained


def test_the_aws_exam_keeps_its_own_rules(bp: Blueprint) -> None:
    system = brain.system_prompt(bp)
    assert "AWS Certified AI Practitioner (AIF-C01) certification" in system
    assert "Never rely on quotas, prices" in system
    slots = [{"domain": 3, "difficulty": "hard", "kind": "single"}]
    prompt = brain.generate_prompt(bp, slots, [])
    assert "practice questions for the AIF-C01 exam" in prompt
    assert "Services and features in the exam's scope: Amazon Bedrock," in prompt
    assert 'the AWS document to read again, for example "Amazon Bedrock User Guide' in prompt


def test_a_course_is_drawn_up_from_words(fake_claude: Path) -> None:
    data = pottery_data()
    structured = {
        "understood": True,
        "message": "",
        "exam": False,
        "code": "Pottery",
        "name": "Pottery",
        "guidance": data["guidance"],
        "reference": data["reference"],
        "services": [],
        "multiple": True,
        "domains": data["domains"],
    }
    answer(fake_claude, structured)
    result = brain.plan({"words": "  la   poterie "}, config.Config())
    assert '"la poterie"' in str(call_log(fake_claude)["stdin"])
    course = blueprint.from_dict(result["course"])
    assert course.key == "pottery"
    assert not course.exam
    assert course.kinds == ("single", "multiple")
    assert course.whole == "all of Pottery"
    answer(fake_claude, {**structured, "code": "SAA-C03", "exam": True, "multiple": False})
    assert brain.plan({"words": "solutions architect"}, config.Config())["course"]["key"] == (
        "saa-c03"
    )
    answer(fake_claude, {**structured, "understood": False, "message": "Name a subject."})
    assert brain.plan({"words": "stuff"}, config.Config()) == {
        "understood": False,
        "message": "Name a subject.",
    }
    answer(fake_claude, {**structured, "domains": []})
    with pytest.raises(ValueError, match="each domain"):
        brain.plan({"words": "pottery"}, config.Config())
    with pytest.raises(brain.BrainError, match="without words"):
        brain.plan({"words": " "}, config.Config())


# --- A language course -------------------------------------------------------------------------


def test_words_are_written_in_the_language_and_explained_in_ones_own(fake_claude: Path) -> None:
    course = spanish()
    good = word_data(4)
    answer(fake_claude, {"words": [good, word_data(0, chapter=9), word_data(1, meaning="")]})
    request = {
        "course": {**course.to_dict(), "language": {"learned": "Spanish", "speaks": "French"}},
        "chapters": [{"id": 2, "count": 12}, {"id": 1, "count": 8}],
        "avoid": ["la cuchara", "el cuento"],
    }
    result = brain.words(request, config.Config())
    assert result["words"] == [good]
    assert result["course"] == "spanish"
    assert result["rejected"] == ["word 2 : unknown chapter: 9", "word 3 : meaning: empty"]
    call = call_log(fake_claude)
    argv = call["argv"]
    assert isinstance(argv, list)
    system = argv[argv.index("--system-prompt") + 1]
    assert "helps someone learn Spanish" in system
    assert "sentences of the language are in Spanish" in system
    assert "is in French" in system
    assert "Everything you write is in English" not in system
    assert json.loads(argv[argv.index("--json-schema") + 1]) == brain.WORDS_SCHEMA
    prompt = str(call["stdin"])
    assert "Write 20 word cards for someone who speaks French and learns Spanish" in prompt
    assert "- 12 for chapter 2, Food and eating out: meals, the restaurant, the market" in prompt
    assert "- 8 for chapter 1, Everyday life" in prompt
    assert "already has these words: write others.\nla cuchara, el cuento" in prompt
    assert "$" not in prompt
    # The level, when the course has one; the model chosen in his menu.
    answer(fake_claude, {"words": [good]})
    brain.words(
        {**request, "course": course.to_dict(), "model": "claude-sonnet-5-5"}, config.Config()
    )
    call = call_log(fake_claude)
    assert "learns Spanish, at level A2 of the Common European Framework" in str(call["stdin"])
    argv = call["argv"]
    assert isinstance(argv, list)
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5-5"
    assert "learn Spanish, at level A2" in argv[argv.index("--system-prompt") + 1]


def test_words_need_a_language_course_and_usable_cards(fake_claude: Path, bp: Blueprint) -> None:
    answer(fake_claude, {"words": [word_data(0, chapter=9)]})
    request = {"course": spanish().to_dict(), "chapters": [{"id": 1, "count": 10}]}
    with pytest.raises(brain.BrainError, match="no usable word: word 1 : unknown chapter"):
        brain.words(request, config.Config())
    with pytest.raises(brain.BrainError, match="not a language course"):
        brain.words({**request, "course": bp.to_dict()}, config.Config())
    with pytest.raises(brain.BrainError, match="1 to 40 words"):
        brain.words({**request, "chapters": [{"id": 1, "count": 90}]}, config.Config())
    with pytest.raises(brain.BrainError, match="odd chapters"):
        brain.words({**request, "chapters": [{"id": 7, "count": 5}]}, config.Config())


def test_a_language_course_is_drawn_up_at_ones_level(fake_claude: Path) -> None:
    chapters = [
        {"name": " Everyday  life ", "words": "the day's routine"},
        {"name": "Food and eating out", "words": "meals, the restaurant"},
    ]
    answer(fake_claude, {"understood": True, "message": "", "chapters": chapters})
    spoken = {"learned": "Spanish", "speaks": "French", "level": "A2", "purpose": "for work"}
    result = brain.plan({"words": "spanish", "language": spoken}, config.Config())
    course = blueprint.from_dict(result["course"])
    assert (course.key, course.name, course.title, course.exam) == (
        "spanish",
        "Spanish",
        "Spanish A2",
        False,
    )
    assert course.language == blueprint.Language("Spanish", "French", "A2", 1)
    assert [(d.id, d.name, d.tasks[0].notions) for d in course.domains] == [
        (1, "Everyday life", "the day's routine"),
        (2, "Food and eating out", "meals, the restaurant"),
    ]
    call = call_log(fake_claude)
    prompt = str(call["stdin"])
    assert "speaks French and wants to learn Spanish, at level A2" in prompt
    assert "Framework of Reference, for work." in prompt
    assert "$" not in prompt
    argv = call["argv"]
    assert isinstance(argv, list)
    assert json.loads(argv[argv.index("--json-schema") + 1]) == brain.LANGUAGE_PLAN_SCHEMA
    # A level up: the course one has comes along, its new chapters go after its own.
    answer(
        fake_claude,
        {"understood": True, "message": "", "chapters": [{"name": "Opinions", "words": "doubt"}]},
    )
    up = brain.plan(
        {"words": "spanish", "language": {**spoken, "level": "B1"}, "course": course.to_dict()},
        config.Config(),
    )
    raised = blueprint.from_dict(up["course"])
    assert [d.name for d in raised.domains] == ["Everyday life", "Food and eating out", "Opinions"]
    assert raised.language == blueprint.Language("Spanish", "French", "B1", 3)
    assert "already has these chapters" in str(call_log(fake_claude)["stdin"])
    assert "Everyday life; Food and eating out." in str(call_log(fake_claude)["stdin"])
    answer(fake_claude, {"understood": False, "message": "Klingon has no A2.", "chapters": []})
    assert brain.plan({"language": spoken}, config.Config()) == {
        "understood": False,
        "message": "Klingon has no A2.",
    }
    answer(fake_claude, {"understood": True, "message": "", "chapters": []})
    with pytest.raises(brain.BrainError, match="no chapters"):
        brain.plan({"language": spoken}, config.Config())
    with pytest.raises(brain.BrainError, match="a level from A1 to C1"):
        brain.plan({"language": {**spoken, "level": "Z9"}}, config.Config())


def test_words_that_ask_for_a_language_get_its_name_first(fake_claude: Path) -> None:
    structured = {
        "understood": True,
        "message": "",
        "exam": False,
        "code": "",
        "name": "",
        "guidance": "",
        "reference": "",
        "services": [],
        "multiple": False,
        "language": "wolof",
        "domains": [],
    }
    answer(fake_claude, structured)
    assert brain.plan({"words": "business wolof"}, config.Config()) == {
        "understood": True,
        "language": "Wolof",
    }
    assert "to learn a language itself" in str(call_log(fake_claude)["stdin"])


def test_questions_that_place_a_learner_come_sorted_and_checked(fake_claude: Path) -> None:
    def placed(level: str, **changes: object) -> dict[str, object]:
        return {
            "level": level,
            "sentence": f"Yo ____ {level}.",
            "choices": ["soy", "eres", "es", "somos"],
            "answer": 0,
            **changes,
        }

    answer(
        fake_claude,
        {
            "questions": [
                placed("B1"),
                placed("A1"),
                placed("C1"),
                placed("A2", answer=4),  # no such choice
                placed("A2", choices=["soy", "Soy", "es", "somos"]),  # the same twice
                placed("B2", sentence="No gap here."),
                placed("A2"),
                placed("B2"),
            ]
        },
    )
    result = brain.level({"learned": "Spanish", "speaks": "French"}, config.Config())
    assert [q["level"] for q in result["questions"]] == ["A1", "A2", "B1", "B2", "C1"]
    prompt = str(call_log(fake_claude)["stdin"])
    assert "speaks French and wants to learn Spanish" in prompt
    assert "$" not in prompt
    answer(fake_claude, {"questions": [placed("A1")]})
    with pytest.raises(brain.BrainError, match="no usable placement"):
        brain.level({"learned": "Spanish"}, config.Config())
    with pytest.raises(brain.BrainError, match="without a language"):
        brain.level({}, config.Config())
