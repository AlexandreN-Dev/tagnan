"""The brain, in WSL: writes questions and explanations with the claude CLI.

    scripts/brain generate < request.json   # {"course", "slots", "avoid", "subject", "model"}
    scripts/brain explain < request.json    # {"course", "question": {...}, "chosen": [...]}
    scripts/brain plan < request.json       # {"words": "pottery"}: a new course's blueprint
    scripts/brain check                     # one tiny call with the configured model

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
from tagnan.blueprint import Blueprint
from tagnan.model import parse_question
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
MAX_WORDS = 120
DIFFICULTIES = ("easy", "medium", "hard")

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
        "domains",
    ],
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


def system_prompt(bp: Blueprint) -> str:
    goal = f"prepare for the {bp.name} ({bp.code}) certification" if bp.exam else f"learn {bp.name}"
    return _template("system.md", goal=goal, guidance=bp.guidance)


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


def plan(request: Mapping[str, Any], cfg: configs.Config) -> dict[str, Any]:
    """A new course from the learner's words: {"understood": true, "course": blueprint}, or
    {"understood": false, "message": what to say instead}."""
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
    data = {
        **structured,
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brain", description="Tagnan's brain")
    parser.add_argument("action", choices=["generate", "explain", "plan", "check"])
    parser.add_argument("--config", type=Path, default=config_file())
    args = parser.parse_args(argv)
    try:
        cfg = configs.load(args.config)
        if args.action == "check":
            result = check(cfg)
        else:
            request = json.loads(sys.stdin.read() or "{}")
            result = {"generate": generate, "explain": explain, "plan": plan}[args.action](
                request, cfg
            )
    except (BrainError, ValueError, KeyError) as error:
        print(f"brain: {error}", file=sys.stderr)
        return 1
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
