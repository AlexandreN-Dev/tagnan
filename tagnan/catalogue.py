"""Catalogues: questions that need no brain. Any chat assistant writes them from a prompt Tagnan
copies, or converts a quiz one has; a colleague exports theirs. Pasted or imported, each question
is checked as his brain's are (tagnan.game's add_questions), then asked as usual.

A catalogue is one JSON object, his format:

    {"tagnan": 1,
     "course": "aif-c01",          a course he knows, by its key; or a whole one (a blueprint)
     "origin": "written",          or "converted" from a quiz: kept for oneself, never exported
     "subject": "RAG",             optional: the subject, in one's own words, they are about
     "left_out": [{"number": 7, "why": "..."}],   optional: what an assistant could not convert
     "questions": [...]}           as his brain writes them (tagnan.brain's QUESTION_SCHEMA)

Standard library only, as the game.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any

from tagnan import blueprint as blueprints
from tagnan import brain
from tagnan.blueprint import Blueprint
from tagnan.model import CONVERTED, WRITTEN, Question
from tagnan.paths import PROMPTS_DIR
from tagnan.studysheet import free_path
from tagnan.subject import from_key

FORMAT = 1
ORIGINS = (WRITTEN, CONVERTED)
# Questions an assistant writes or converts per answer: past that, its answers are often cut.
BATCH = 20
MAX_QUESTIONS = 5000  # in one catalogue: years of questions, exported at once
MAX_CHARS = 20_000_000

# Where his object starts, among the words and the code block's fences around it.
_START = re.compile(r'\{\s*"(?:tagnan|course|origin|subject|left_out|questions)"\s*:')
_QUESTIONS = re.compile(r'"questions"\s*:\s*\[')
_DECODER = json.JSONDecoder()
# Characters Windows refuses in a file name, and those no file name should hold.
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')

# What his format looks like, for an assistant to follow.
QUESTION_SHAPE = (
    '{"domain": 1, "task": "1.1", "topic": "…", "difficulty": "medium", "kind": "single",'
    ' "stem": "…", "choices": ["…", "…", "…", "…"], "answers": [0], "explanation": "…",'
    ' "why_wrong": ["", "…", "…", "…"], "reference": "…"}'
)
COURSE_SHAPE = (
    '{"code": "…", "name": "…", "exam": false, "guidance": "…", "reference": "…",'
    ' "kinds": ["single"], "domains": [{"id": 1, "name": "…", "weight": 25,'
    ' "tasks": [{"id": "1.1", "title": "…", "notions": "…"}]}]}'
)


@dataclass(frozen=True)
class Catalogue:
    course: Blueprint | str  # a whole course, or the key of one he knows
    questions: tuple[Mapping[str, Any], ...]  # as written: checked once their course is known
    origin: str = WRITTEN
    subject: str = ""
    left_out: tuple[tuple[int, str], ...] = ()  # their number in the quiz, and why
    cut: bool = False  # it breaks off: the whole questions before the break only


def read(text: str) -> Catalogue:
    """A catalogue from what one pasted, or a file: his JSON object, with or without the code
    block and the words around it. An answer that breaks off keeps the whole questions before
    the break. ValueError, in words one can be told, when there is none."""
    if len(text) > MAX_CHARS:
        raise ValueError("it is too big for a catalogue")
    start = _START.search(text)
    if start is None:
        raise ValueError("I find no questions in it")
    try:
        data, _ = _DECODER.raw_decode(text, start.start())
        cut = False
    except json.JSONDecodeError:
        data, cut = _salvage(text, start.start())
    return _catalogue(data, cut)


def _salvage(text: str, start: int) -> tuple[dict[str, Any], bool]:
    """An object that breaks off (an answer too long for an assistant, or garbled): what comes
    before its questions, its questions up to the first that cannot be read, and whether they
    break off there."""
    found = _QUESTIONS.search(text, start)
    if found is None:
        raise ValueError("it breaks off before its questions")
    try:
        data = json.loads(text[start : found.start()].rstrip().rstrip(",") + "}")
    except json.JSONDecodeError:
        raise ValueError("it breaks off before its questions") from None
    questions = []
    at = found.end()
    while True:
        while at < len(text) and text[at] in " \t\r\n,":
            at += 1
        if at >= len(text) or text[at] != "{":
            break
        try:
            question, at = _DECODER.raw_decode(text, at)
        except json.JSONDecodeError:
            break
        questions.append(question)
    data["questions"] = questions
    return data, not text.startswith("]", at)


def _catalogue(data: object, cut: bool) -> Catalogue:
    if not isinstance(data, dict):
        raise ValueError("I find no questions in it")
    if data.get("tagnan", FORMAT) != FORMAT:
        raise ValueError("it is written for a newer Tagnan: update me first")
    raw = data.get("questions")
    questions = tuple(q for q in raw if isinstance(q, Mapping)) if isinstance(raw, list) else ()
    if not questions:
        raise ValueError(
            "it breaks off before its first question" if cut else "it holds no questions"
        )
    course = data.get("course")
    found: Blueprint | str
    if isinstance(course, Mapping):
        found = blueprints.from_dict(course, where="its course")
    elif isinstance(course, str) and course.strip():
        found = course.strip()
    else:
        raise ValueError("it does not say which course its questions are for")
    left_out = data.get("left_out")
    origin = data.get("origin")
    return Catalogue(
        course=found,
        questions=questions[:MAX_QUESTIONS],
        origin=origin if isinstance(origin, str) and origin in ORIGINS else WRITTEN,
        subject=" ".join(str(data.get("subject") or "").split())[:80],
        left_out=tuple(
            (_number(x.get("number")), " ".join(str(x.get("why") or "").split()))
            for x in (left_out if isinstance(left_out, list) else [])
            if isinstance(x, Mapping)
        ),
        cut=cut,
    )


def _number(value: object) -> int:
    try:
        return int(str(value))
    except ValueError:
        return 0


# Why a question was set aside (tagnan.model's checks), as one tells a learner.
_REASONS = {
    "two identical choices": "two of its choices are the same",
    "4 to 6 choices are needed": "it needs four to six choices",
    "why_wrong: one text per choice": "it does not say why each choice is wrong",
    "explanation: empty": "it does not say why its answer is right",
    "stem: empty": "it has no question",
}


def reason(error: str) -> str:
    """A check's message, said plainly."""
    if error.startswith("unknown domain"):
        return "its domain is not one of the course's"
    if " is not in domain " in error:
        return "its task is not one of its domain's"
    return _REASONS.get(error, error)


# --- Sharing ---------------------------------------------------------------------------------


def export(bp: Blueprint, questions: Sequence[Question]) -> dict[str, Any]:
    """A course and the questions one may share, as a catalogue: a colleague imports both."""
    return {
        "tagnan": FORMAT,
        "course": bp.to_dict(),
        "origin": WRITTEN,
        "questions": [q.to_dict() for q in questions],
    }


def file_name(bp: Blueprint, count: int) -> str:
    """The file an export is written to: "Tagnan – AIF-C01 – 120 questions.json"."""
    safe = " ".join(_UNSAFE.sub(" ", bp.code).split()).strip(" .")[:60].strip(" .")
    return f"Tagnan – {safe or 'Catalogue'} – {count} question{'' if count == 1 else 's'}.json"


def write(data: Mapping[str, Any], folder: Path, name: str) -> Path:
    """A catalogue into `folder`, next to nothing it would replace ("… (2).json" otherwise),
    under a temporary name first: a failure leaves no half a file."""
    folder.mkdir(parents=True, exist_ok=True)
    path = free_path(folder, name)
    partial = path.with_name(path.name + ".part")
    try:
        partial.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    return path


# --- Prompts for one's own assistant ---------------------------------------------------------


def write_prompt(bp: Blueprint, request: Mapping[str, Any]) -> str:
    """Questions written as his brain writes them: the batch the game asks for (tagnan.game's
    batch_request: the level of his rank, the topics asked lately left aside), then his format."""
    subject = str(request.get("subject") or "")
    text = "\n\n".join(
        (
            brain.system_prompt(bp),
            brain.generate_prompt(
                bp, request["slots"], request.get("avoid") or [], from_key(subject).text
            ),
            answer_format(bp.key, WRITTEN, subject=subject),
        )
    )
    return re.sub(r"\n{3,}", "\n\n", text)  # the brain's blanks, where it has no subject


def convert_prompt(bp: Blueprint) -> str:
    """A quiz one has, its questions put into his format and completed, twenty at a time."""
    domains = "\n\n".join(
        f"Domain {d.id}, {d.name}:\n" + "\n".join(f"  - {t.id} {t.title}" for t in d.tasks)
        for d in bp.domains
    )
    return _template(
        "catalogue-convert.md",
        goal=brain.goal(bp),
        reference=bp.reference,
        domains=domains,
        count=BATCH,
        format=answer_format(bp.key, CONVERTED, left_out=True),
    )


def course_prompt(words: str) -> str:
    """A new course drawn up, as his brain would, with its first questions."""
    return _template(
        "catalogue-course.md", words=words, count=BATCH, format=answer_format(None, WRITTEN)
    )


def explain_prompt(bp: Blueprint, question: Question, chosen: Sequence[int]) -> str:
    """In place of Tell me more: what his brain would be asked."""
    return brain.explain_prompt(bp, question.to_dict(), chosen)


def answer_format(
    course: str | None, origin: str, subject: str = "", left_out: bool = False
) -> str:
    """How an assistant answers: his object, for a course he knows (its key) or a new one."""
    head = [
        '"tagnan": 1',
        f'"course": {json.dumps(course) if course else COURSE_SHAPE}',
        f'"origin": "{origin}"',
    ]
    if subject:
        head.append(f'"subject": {json.dumps(subject, ensure_ascii=False)}')
    if left_out:
        head.append('"left_out": [{"number": 7, "why": "…"}]')
    shape = "{" + ", ".join(head) + ', "questions": [\n  ' + QUESTION_SHAPE + ",\n  …\n]}"
    return _template("catalogue-format.md", shape=shape)


def _template(name: str, **values: object) -> str:
    text = (PROMPTS_DIR / name).read_text(encoding="utf-8")
    return Template(text).substitute({k: str(v) for k, v in values.items()}).strip()
