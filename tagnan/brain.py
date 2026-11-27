"""The brain, in WSL: writes questions and explanations with the claude CLI.

    scripts/brain generate < request.json   # {"course", "slots", "avoid", "subject", "model"}
    scripts/brain explain < request.json    # {"course", "question": {...}, "chosen": [...]}
    scripts/brain sheet < request.json      # {"course", "question": {...}}: a study sheet's words
    scripts/brain plan < request.json       # {"words": "pottery"}: a new course's blueprint
    scripts/brain words < request.json      # {"course", "chapters", "avoid"}: a language's words
    scripts/brain level < request.json      # {"learned", "speaks"}: questions that place one
    scripts/brain check                     # one tiny call with the configured model
    scripts/brain account                   # whose Claude login it writes with

"course" is a blueprint (tagnan.blueprint's to_dict); a request may instead name a file of
exam/ by its key, as "exam". "model", optional, is one of config.MODELS, chosen in his menu: it
writes the questions instead of the config's. It prints one JSON object on stdout; on failure,
a message on stderr and exit code 1. Claude is reached through the official CLI only, with the
user's own login: clean environment, no tools, no hooks, no MCP servers, in an empty folder (no
CLAUDE.md, no project settings).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from string import Template
from typing import Any

from tagnan import blueprint as blueprints
from tagnan import config as configs
from tagnan import language as languages
from tagnan import studysheet
from tagnan.blueprint import Blueprint
from tagnan.model import parse_card, parse_question
from tagnan.paths import PROMPTS_DIR, config_file
from tagnan.subject import from_key

# Allowlist, not denylist: the brain may run under a Claude Code session (CLAUDECODE,
# CLAUDE_CODE_*) or a shell holding AWS or Anthropic variables.
ALLOWED_ENV_VARS = frozenset({"HOME", "PATH", "LANG", "USER", "LOGNAME", "TMPDIR"})

# Away from the user's hooks, MCP servers and project settings, as Dartt's relay does.
ISOLATION_FLAGS = (
    "--setting-sources",
    "user",
    "--strict-mcp-config",
    "--mcp-config",
    '{"mcpServers":{}}',
    "--settings",
    '{"disableAllHooks": true}',
)
# Opus at max effort thinks long: a batch of ten can take minutes, an explanation a minute.
GENERATE_TIMEOUT, EXPLAIN_TIMEOUT, CHECK_TIMEOUT, PLAN_TIMEOUT = 600.0, 240.0, 180.0, 600.0
SHEET_TIMEOUT = 360.0
ACCOUNT_TIMEOUT = 30.0
MAX_WORDS = 120
DIFFICULTIES = ("easy", "medium", "hard")
LANGUAGE_CHAPTERS = 5  # the chapters of a language course, at each level
MAX_CARDS = 40  # the words of one call, at most

QUESTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "domain": {"type": "integer"},
        "task": {"type": "string"},
        "topic": {"type": "string"},
        "difficulty": {"type": "string", "enum": list(DIFFICULTIES)},
        "kind": {"type": "string", "enum": ["single", "multiple"]},
        "stem": {"type": "string"},
        "choices": {"type": "array", "items": {"type": "string"}, "minItems": 4, "maxItems": 6},
        "answers": {"type": "array", "items": {"type": "integer"}, "minItems": 1, "maxItems": 3},
        "explanation": {"type": "string"},
        "why_wrong": {"type": "array", "items": {"type": "string"}},
        "reference": {"type": "string"},
    },
    "required": [
        "domain",
        "task",
        "topic",
        "difficulty",
        "kind",
        "stem",
        "choices",
        "answers",
        "explanation",
        "why_wrong",
        "reference",
    ],
    "additionalProperties": False,
}
BATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"questions": {"type": "array", "items": QUESTION_SCHEMA}},
    "required": ["questions"],
    "additionalProperties": False,
}
TASK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "notions": {"type": "string"},
    },
    "required": ["id", "title", "notions"],
    "additionalProperties": False,
}
PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "understood": {"type": "boolean"},
        "message": {"type": "string"},
        "exam": {"type": "boolean"},
        "code": {"type": "string"},
        "name": {"type": "string"},
        "guidance": {"type": "string"},
        "reference": {"type": "string"},
        "services": {"type": "array", "items": {"type": "string"}},
        "multiple": {"type": "boolean"},
        "language": {"type": "string"},
        "domains": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "weight": {"type": "number"},
                    "tasks": {"type": "array", "items": TASK_SCHEMA},
                },
                "required": ["id", "name", "weight", "tasks"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "understood",
        "message",
        "exam",
        "code",
        "name",
        "guidance",
        "reference",
        "services",
        "multiple",
        "language",
        "domains",
    ],
    "additionalProperties": False,
}
# A language course: its chapters at a level, its words, and the questions that place one.
LANGUAGE_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "understood": {"type": "boolean"},
        "message": {"type": "string"},
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "words": {"type": "string"}},
                "required": ["name", "words"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["understood", "message", "chapters"],
    "additionalProperties": False,
}
CARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "chapter": {"type": "integer"},
        "term": {"type": "string"},
        "meaning": {"type": "string"},
        "example": {"type": "string"},
        "translation": {"type": "string"},
        "note": {"type": "string"},
        "also": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["chapter", "term", "meaning", "example", "translation", "note", "also"],
    "additionalProperties": False,
}
WORDS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"words": {"type": "array", "items": CARD_SCHEMA}},
    "required": ["words"],
    "additionalProperties": False,
}
LEVEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": list(languages.LEVEL_KEYS)},
                    "sentence": {"type": "string"},
                    "choices": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "answer": {"type": "integer"},
                },
                "required": ["level", "sentence", "choices", "answer"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}
CHECK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}
EXPLAIN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


class BrainError(Exception):
    pass


def child_env(parent: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if parent is None else parent
    return {
        name: value
        for name, value in source.items()
        if name in ALLOWED_ENV_VARS or name.startswith("LC_")
    }


def claude_binary() -> str:
    found = os.environ.get("TAGNAN_CLAUDE") or shutil.which("claude")
    if found:
        return found
    default = Path.home() / ".local" / "bin" / "claude"
    if default.exists():
        return str(default)
    raise BrainError("claude not found: install Claude Code, or set TAGNAN_CLAUDE")


def run_claude(
    prompt: str,
    *,
    system: str,
    schema: Mapping[str, Any],
    model: str,
    effort: str,
    timeout: float,
) -> dict[str, Any]:
    """One non-interactive turn; the object that matches the schema."""
    command = [
        claude_binary(),
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        "--effort",
        effort,
        "--tools",
        "",
        "--no-session-persistence",
        *ISOLATION_FLAGS,
        "--system-prompt",
        system,
        "--json-schema",
        json.dumps(schema),
    ]
    with tempfile.TemporaryDirectory(prefix="tagnan-brain-") as folder:
        try:
            done = subprocess.run(  # noqa: S603 - fixed argument list, no shell
                command,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=folder,
                env=child_env(),
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise BrainError(f"claude did not answer within {timeout:.0f} s") from None
    try:
        result = json.loads(done.stdout)
    except json.JSONDecodeError:
        detail = (done.stderr or done.stdout).strip().splitlines()
        raise BrainError(
            f"claude failed (code {done.returncode}): {detail[-1] if detail else 'no message'}"
        ) from None
    if result.get("is_error") or result.get("subtype") != "success":
        raise BrainError(f"claude failed: {str(result.get('result', ''))[:300]}")
    structured = result.get("structured_output")
    if not isinstance(structured, dict):
        raise BrainError("claude gave no structured answer")
    return structured


def _template(name: str, **values: object) -> str:
    text = (PROMPTS_DIR / name).read_text(encoding="utf-8")
    return Template(text).substitute({k: str(v) for k, v in values.items()}).strip()


def course(request: Mapping[str, Any], cfg: configs.Config) -> Blueprint:
    """The course a request is about: its blueprint, or the key of a file of exam/."""
    data = request.get("course")
    if isinstance(data, Mapping):
        return blueprints.from_dict(data, where="course")
    return blueprints.load(str(request.get("exam", cfg.exam)))


def goal(bp: Blueprint) -> str:
    """What the learner is after, as the prompts say it."""
    if bp.language and bp.language.level:
        return f"learn {bp.language.learned}, at level {bp.language.level}"
    return f"prepare for the {bp.name} ({bp.code}) certification" if bp.exam else f"learn {bp.name}"


def tongue(bp: Blueprint) -> str:
    """What the brain writes in: English, as Tagnan speaks; for a language course, the language
    learned for its words and sentences, the one the learner speaks for the rest."""
    if bp.language is None:
        return "Everything you write is in English."
    speaks = bp.language.speaks or "English"
    return (
        f"The words and the sentences of the language are in {bp.language.learned}; everything"
        f" else you write (meanings, translations, notes, explanations) is in {speaks}."
    )


def system_prompt(bp: Blueprint) -> str:
    return _template("system.md", goal=goal(bp), guidance=bp.guidance, tongue=tongue(bp))


def words_prompt(bp: Blueprint, chapters: Sequence[Mapping[str, Any]], avoid: Sequence[str]) -> str:
    """Word cards for a language course: so many for each chapter asked, none he has."""
    if bp.language is None:
        raise BrainError("not a language course")
    lines = []
    for chapter in chapters:
        domain = bp.domain(int(chapter["id"]))
        about = domain.tasks[0].notions
        lines.append(
            f"- {int(chapter['count'])} for chapter {domain.id}, {domain.name}"
            + (f": {about}" if about and about != domain.name else "")
        )
    avoid_text = (
        "The learner already has these words: write others.\n" + ", ".join(avoid) if avoid else ""
    )
    level = bp.language.level
    return _template(
        "words.md",
        count=sum(int(c["count"]) for c in chapters),
        speaks=bp.language.speaks or "English",
        learned=bp.language.learned,
        level=f", at level {level} of the Common European Framework of Reference" if level else "",
        chapters="\n".join(lines),
        avoid=avoid_text,
    )


def generate_prompt(
    bp: Blueprint, slots: Sequence[Mapping[str, Any]], avoid: Sequence[str], subject: str = ""
) -> str:
    """subject: one's own words for what the questions are about; a slot without a domain
    leaves it to the brain, and then every domain is shown."""
    counts: dict[tuple[int, str, str], int] = {}
    for slot in slots:
        key = (int(slot.get("domain") or 0), str(slot["difficulty"]), str(slot["kind"]))
        counts[key] = counts.get(key, 0) + 1
    lines = []
    for (domain_id, difficulty, kind), count in sorted(counts.items()):
        kind_text = "multiple-answer" if kind == "multiple" else "single-answer"
        where = (
            f" from domain {domain_id} ({bp.domain(domain_id).name})"
            if domain_id
            else ", from the domain of your choice"
        )
        lines.append(
            f"- {count} {difficulty} {kind_text} question{'s' if count > 1 else ''}{where}"
        )
    wanted = {d for d, _, _ in counts}
    shown = sorted(d.id for d in bp.domains) if 0 in wanted else sorted(wanted)
    place = "exam" if bp.exam else "course"
    subject_text = (
        f'Every question is about the subject the learner chose: "{subject}". Approach it from'
        f" a different angle each time, and give each question the domain and task of the {place}"
        f" that cover that angle. If the subject reaches beyond the {place}, keep to what the"
        f" {place} covers of it."
        if subject
        else ""
    )
    domains = []
    for domain_id in shown:
        domain = bp.domain(domain_id)
        tasks = "\n".join(f"  - {t.id} {t.title}: {t.notions}" for t in domain.tasks)
        domains.append(f"Domain {domain.id}, {domain.name}:\n{tasks}")
    avoid_text = (
        "These notions were asked recently: choose others, or a clearly different angle.\n"
        + "\n".join(f"- {t}" for t in avoid)
        if avoid
        else ""
    )
    return _template(
        "generate.md",
        count=len(slots),
        what=f"practice questions for the {bp.code} exam"
        if bp.exam
        else f"questions to learn {bp.name}",
        slots="\n".join(lines),
        subject=subject_text,
        domains="\n\n".join(domains),
        task_example=bp.domains[0].tasks[0].id,
        reference=bp.reference,
        services=f"Services and features in the exam's scope: {', '.join(bp.services)}."
        if bp.services
        else "",
        avoid=avoid_text,
    )


def explain_prompt(bp: Blueprint, question: Mapping[str, Any], chosen: Sequence[int]) -> str:
    choices = [str(c) for c in question["choices"]]
    letters = "ABCDEF"

    def named(indices: Sequence[int]) -> str:
        return " and ".join(f"{letters[i]} ({choices[i]})" for i in indices)

    return _template(
        "explain.md",
        course=f"{bp.name} ({bp.code})" if bp.exam else bp.name,
        remember=" on exam day" if bp.exam else "",
        stem=question["stem"],
        choices="\n".join(f"{letters[i]}. {c}" for i, c in enumerate(choices)),
        right=named([int(a) for a in question["answers"]]),
        chosen=named([int(c) for c in chosen]) or "none",
        explanation=question.get("explanation", ""),
    )


def sheet_prompt(bp: Blueprint, question: Mapping[str, Any]) -> str:
    choices = [str(c) for c in question["choices"]]
    letters = "ABCDEF"
    return _template(
        "sheet.md",
        course=f"{bp.name} ({bp.code})" if bp.exam else bp.name,
        stem=question["stem"],
        choices="\n".join(f"{letters[i]}. {c}" for i, c in enumerate(choices)),
        right=" and ".join(f"{letters[int(a)]} ({choices[int(a)]})" for a in question["answers"]),
        explanation=question.get("explanation", ""),
    )


def generate(request: Mapping[str, Any], cfg: configs.Config) -> dict[str, Any]:
    bp = course(request, cfg)
    slots = request.get("slots") or []
    if not slots:
        raise BrainError("request without question slots")
    subject = str(request.get("subject") or "")
    model, effort = cfg.brain.model, cfg.brain.effort
    if request.get("model"):
        chosen = configs.find_model(str(request["model"]))
        if chosen is None:
            raise BrainError(f"unknown model: {request['model']}")
        model, effort = chosen.model, chosen.effort
    structured = run_claude(
        generate_prompt(bp, slots, request.get("avoid") or [], from_key(subject).text),
        system=system_prompt(bp),
        schema=BATCH_SCHEMA,
        model=model,
        effort=effort,
        timeout=GENERATE_TIMEOUT,
    )
    questions, rejected = [], []
    for i, data in enumerate(structured.get("questions", []), 1):
        try:
            parse_question(data, bp)
        except ValueError as error:
            rejected.append(f"question {i} : {error}")
            continue
        questions.append(data)
    if not questions:
        raise BrainError("no usable question: " + "; ".join(rejected[:3]))
    return {"questions": questions, "rejected": rejected, "subject": subject, "course": bp.key}


def explain(request: Mapping[str, Any], cfg: configs.Config) -> dict[str, Any]:
    bp = course(request, cfg)
    question = request.get("question")
    if not isinstance(question, Mapping):
        raise BrainError("request without a question")
    structured = run_claude(
        explain_prompt(bp, question, [int(c) for c in request.get("chosen", [])]),
        system=system_prompt(bp),
        schema=EXPLAIN_SCHEMA,
        model=cfg.brain.explain_model,
        effort=cfg.brain.explain_effort,
        timeout=EXPLAIN_TIMEOUT,
    )
    text = " ".join(str(structured.get("text", "")).split())
    if not text:
        raise BrainError("empty explanation")
    return {"text": text}


def sheet(request: Mapping[str, Any], cfg: configs.Config) -> dict[str, Any]:
    """A study sheet's words on the notion behind a question (tagnan.studysheet): the window
    draws the page. Written by the model and effort of "Tell me more"."""
    bp = course(request, cfg)
    question = request.get("question")
    if not isinstance(question, Mapping):
        raise BrainError("request without a question")
    structured = run_claude(
        sheet_prompt(bp, question),
        system=f"You write the study sheets of Tagnan, a little ink musketeer who helps someone"
        f" {goal(bp)}. Everything you write is in English. Answer with the requested JSON object"
        " only.",
        schema=studysheet.SCHEMA,
        model=cfg.brain.explain_model,
        effort=cfg.brain.explain_effort,
        timeout=SHEET_TIMEOUT,
    )
    try:
        return studysheet.clean(structured)
    except ValueError as error:
        raise BrainError(f"no usable sheet: {error}") from None


def words(request: Mapping[str, Any], cfg: configs.Config) -> dict[str, Any]:
    """A language course's words (tagnan.model's cards): {"words", "rejected", "course"}."""
    bp = course(request, cfg)
    chapters = [c for c in request.get("chapters") or [] if isinstance(c, Mapping)]
    try:
        asked = sum(int(c["count"]) for c in chapters)
        prompt = words_prompt(bp, chapters, [str(w) for w in request.get("avoid") or []])
    except (KeyError, TypeError, ValueError) as error:
        raise BrainError(f"request with odd chapters ({error})") from None
    if not 0 < asked <= MAX_CARDS:
        raise BrainError(f"1 to {MAX_CARDS} words at a time")
    model, effort = cfg.brain.model, cfg.brain.effort
    if request.get("model"):
        chosen = configs.find_model(str(request["model"]))
        if chosen is None:
            raise BrainError(f"unknown model: {request['model']}")
        model, effort = chosen.model, chosen.effort
    structured = run_claude(
        prompt,
        system=system_prompt(bp),
        schema=WORDS_SCHEMA,
        model=model,
        effort=effort,
        timeout=GENERATE_TIMEOUT,
    )
    cards, rejected = [], []
    for i, data in enumerate(structured.get("words", []), 1):
        try:
            parse_card(data, bp)
        except ValueError as error:
            rejected.append(f"word {i} : {error}")
            continue
        cards.append(data)
    if not cards:
        raise BrainError("no usable word: " + "; ".join(rejected[:3]))
    return {"words": cards, "rejected": rejected, "course": bp.key}


def level(request: Mapping[str, Any], cfg: configs.Config) -> dict[str, Any]:
    """Questions that place a learner, the easiest first: {"questions": [{"level",
    "sentence", "choices", "answer"}]}."""
    learned = " ".join(str(request.get("learned") or "").split())[:40]
    speaks = " ".join(str(request.get("speaks") or "English").split())[:40]
    if not learned:
        raise BrainError("request without a language")
    structured = run_claude(
        _template("level.md", learned=learned, speaks=speaks),
        system="You write the placement questions of Tagnan, a little ink musketeer who helps"
        f" someone learn {learned}. Answer with the requested JSON object only.",
        schema=LEVEL_SCHEMA,
        model=cfg.brain.model,
        effort=cfg.brain.effort,
        timeout=EXPLAIN_TIMEOUT,
    )
    questions = []
    for data in structured.get("questions", []):
        choices = [" ".join(str(c).split()) for c in data.get("choices") or []]
        answer = data.get("answer")
        sentence = " ".join(str(data.get("sentence") or "").split())
        if (
            data.get("level") in languages.LEVEL_KEYS
            and len(choices) == 4
            and len({c.casefold() for c in choices}) == 4
            and all(choices)
            and isinstance(answer, int)
            and 0 <= answer < 4
            and "___" in sentence
        ):
            questions.append(
                {"level": data["level"], "sentence": sentence, "choices": choices, "answer": answer}
            )
    if len(questions) < 5:
        raise BrainError("no usable placement questions")
    questions.sort(key=lambda q: languages.LEVEL_KEYS.index(q["level"]))
    return {"questions": questions}


def plan_language(
    request: Mapping[str, Any], spoken: Mapping[str, Any], cfg: configs.Config
) -> dict[str, Any]:
    """A language course's chapters at a level: a new course, or, when the request brings the
    course one has ("course"), the same a level up, its new chapters after its own."""
    learned = " ".join(str(spoken.get("learned") or "").split())[:40]
    speaks = " ".join(str(spoken.get("speaks") or "English").split())[:40]
    wanted = str(spoken.get("level") or "")
    if not learned or wanted not in languages.LEVEL_KEYS:
        raise BrainError("a language and a level from A1 to C1 are needed")
    purpose = " ".join(str(spoken.get("purpose") or "").split())[:60]
    known = (
        blueprints.from_dict(request["course"], where="course") if request.get("course") else None
    )
    have = "; ".join(d.name for d in known.domains) if known else ""
    structured = run_claude(
        _template(
            "plan-language.md",
            learned=learned,
            speaks=speaks,
            level=wanted,
            purpose=f", {purpose}" if purpose else "",
            count=LANGUAGE_CHAPTERS,
            have=f" The course already has these chapters, from the levels before: {have}."
            " Choose other themes, or one of these a level deeper under another name."
            if have
            else "",
        ),
        system="You draw up the language courses of Tagnan, a little ink musketeer who asks"
        " someone the words of the language they learn. You know how good textbooks lay out each"
        " level. Answer with the requested JSON object only.",
        schema=LANGUAGE_PLAN_SCHEMA,
        model=cfg.brain.model,
        effort=cfg.brain.effort,
        timeout=PLAN_TIMEOUT,
    )
    if not structured.get("understood"):
        message = " ".join(str(structured.get("message") or "").split())
        return {"understood": False, "message": message or "I don't know how to teach that."}
    chapters = [
        (str(c.get("name") or ""), str(c.get("words") or ""))
        for c in structured.get("chapters") or []
        if isinstance(c, Mapping) and str(c.get("name") or "").strip()
    ][: LANGUAGE_CHAPTERS + 1]
    if not chapters:
        raise BrainError("a language course with no chapters")
    if known is not None:
        bp = blueprints.raise_level(known, wanted, chapters)
    else:
        bp = blueprints.language_course(learned, speaks, wanted, chapters)
    return {"understood": True, "course": bp.to_dict()}


def plan(request: Mapping[str, Any], cfg: configs.Config) -> dict[str, Any]:
    """A new course from the learner's words: {"understood": true, "course": blueprint}, or
    {"understood": false, "message": what to say instead}. With "language" ({"learned",
    "speaks", "level"}), a language course's chapters at that level; words that ask for a
    language without one get {"understood": true, "language": its name}: the level comes first."""
    spoken = request.get("language")
    if isinstance(spoken, Mapping):
        return plan_language(request, spoken, cfg)
    words = " ".join(str(request.get("words") or "").split())
    if not words:
        raise BrainError("request without words")
    if len(words) > MAX_WORDS:
        raise BrainError(f"{MAX_WORDS} characters at most")
    structured = run_claude(
        _template("plan.md", words=words),
        system="You draw up the courses of Tagnan, a little ink musketeer who quizzes someone"
        " on what they want to learn. You know certification exam guides well, and how to plan"
        " a course on any subject. Answer with the requested JSON object only.",
        schema=PLAN_SCHEMA,
        model=cfg.brain.model,
        effort=cfg.brain.effort,
        timeout=PLAN_TIMEOUT,
    )
    if not structured.get("understood"):
        message = " ".join(str(structured.get("message") or "").split())
        return {"understood": False, "message": message or "I don't know how to teach that."}
    asked = " ".join(str(structured.get("language") or "").split())
    if asked:
        return {"understood": True, "language": languages.named(asked)}
    data = {
        **{k: v for k, v in structured.items() if k != "language"},
        "kinds": ["single", "multiple"] if structured.get("multiple") else ["single"],
    }
    bp = blueprints.from_dict(data, blueprints.slug(str(structured.get("code") or "")))
    return {"understood": True, "course": bp.to_dict()}


def check(cfg: configs.Config) -> dict[str, Any]:
    """The setup's real try: the login, the model and the isolation flags, for a sliver of quota."""
    structured = run_claude(
        "Set ok to true.",
        system="You answer a connection check for Tagnan, a quiz game.",
        schema=CHECK_SCHEMA,
        model=cfg.brain.model,
        effort="low",
        timeout=CHECK_TIMEOUT,
    )
    if structured.get("ok") is not True:
        raise BrainError("claude answered the check oddly")
    return {"ok": True, "model": cfg.brain.model}


def account() -> dict[str, Any]:
    """Whose Claude login writes his questions, as `claude auth status` says it (no call to a
    model, no quota): its address, its organisation and its plan, shown at the foot of his menu
    so that one sees which licence is spent. Nobody signed in: signedIn false, the rest empty."""
    command = [claude_binary(), "auth", "status", "--json"]
    with tempfile.TemporaryDirectory(prefix="tagnan-brain-") as folder:
        try:
            done = subprocess.run(  # noqa: S603 - fixed argument list, no shell
                command,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=folder,
                env=child_env(),
                timeout=ACCOUNT_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise BrainError("claude did not say who is signed in") from None
    try:
        status = json.loads(done.stdout)
    except json.JSONDecodeError:
        status = None
    if not isinstance(status, dict):
        raise BrainError("claude did not say who is signed in")
    signed_in = status.get("loggedIn") is True

    def said(name: str) -> str:
        value = status.get(name)
        return value.strip() if signed_in and isinstance(value, str) else ""

    return {
        "signedIn": signed_in,
        "email": said("email"),
        "org": said("orgName"),
        "plan": said("subscriptionType").capitalize(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brain", description="Tagnan's brain")
    parser.add_argument(
        "action",
        choices=["generate", "explain", "sheet", "plan", "words", "level", "check", "account"],
    )
    parser.add_argument("--config", type=Path, default=config_file())
    args = parser.parse_args(argv)
    try:
        if args.action == "account":
            sys.stdout.write(json.dumps(account(), ensure_ascii=False))
            return 0
        cfg = configs.load(args.config)
        if args.action == "check":
            result = check(cfg)
        else:
            request = json.loads(sys.stdin.read() or "{}")
            actions = {
                "generate": generate,
                "explain": explain,
                "sheet": sheet,
                "plan": plan,
                "words": words,
                "level": level,
            }
            result = actions[args.action](request, cfg)
    except (BrainError, ValueError, KeyError) as error:
        print(f"brain: {error}", file=sys.stderr)
        return 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
