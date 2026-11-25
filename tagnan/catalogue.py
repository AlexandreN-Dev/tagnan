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

Or questions typed by hand, in plain text (a note, a text file) or a spreadsheet saved as CSV,
read here with no assistant: a course of their own, its chapters their headings, checked lighter
(tagnan.model's parse_question). FORMAT_EXAMPLE is their shape.

Standard library only, as the game.
"""

import csv
import io
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from string import Template
from typing import Any

from tagnan import blueprint as blueprints
from tagnan import brain
from tagnan.blueprint import Blueprint
from tagnan.model import CONVERTED, TYPED, WRITTEN, Question
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
    typed: bool = False  # typed by hand in plain text or CSV: a course of its own, checked lighter


def read(text: str, name: str = "") -> Catalogue:
    """A catalogue from what one pasted, or a file (`name`, without its extension): his JSON
    object, with or without the code block and the words around it; else questions typed in
    plain text or CSV. An answer that breaks off keeps the whole questions before the break.
    ValueError, in words one can be told, when there is none."""
    if len(text) > MAX_CHARS:
        raise ValueError("it is too big for a catalogue")
    start = _START.search(text)
    if start is None:
        return read_typed(text, name)
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


# --- Typed by hand ---------------------------------------------------------------------------

FORMAT_EXAMPLE = """# The course's name
## A chapter

Question: The question?
A. A choice
B. Another one
C. A third
Answer: B
Explanation: Why B is right. (optional)
Source: What to read again. (optional)

Question: Another question, with two right answers?
- [x] A right choice
- [ ] A wrong one
- [x] Another right one"""
UNTITLED = "My questions"  # a text pasted with no # title

_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*$")
_QUESTION = re.compile(
    r"^(?:question|q(?=\s*\d))\s*\d*\s*(?:[:.)\]\-–]\s*|\s+|$)(.*)$", re.IGNORECASE
)
_LABELLED = re.compile(r"^([A-Fa-f]|[1-6])\s*[.)\]]\s+(.+)$")
_BULLET = re.compile(r"^[-*•]\s+(?:\[([ xX])\]\s*)?(.+)$")
_FIELD = re.compile(
    r"^(answers?|correct answers?|bonnes? réponses?|réponses?|reponses?|solution|correct"
    r"|explanation|explication|why|pourquoi|source|read again|reference|référence|à relire"
    r"|a relire)\s*:\s*(.*)$",
    re.IGNORECASE,
)
_LABELS_ONLY = re.compile(
    r"^([A-Fa-f]|[1-6])(?:\s*(?:,|;|/|&|\band\b|\bet\b|\s)\s*([A-Fa-f]|[1-6]))*\s*\.?$",
    re.IGNORECASE,
)
_CHAPTER_NUMBER = re.compile(r"^(?:domain|domaine|chapter|chapitre)?\s*(\d+)\b", re.IGNORECASE)


@dataclass
class _Typed:
    """A question as its lines are read."""

    chapter: str
    stem: str = ""
    choices: list[str] = field(default_factory=list)
    ticked: list[int] = field(default_factory=list)
    answer: str = ""
    explanation: str = ""
    source: str = ""
    last: str = "stem"  # what a line with no mark of its own goes on

    def add(self, line: str) -> None:
        if self.last == "stem" and not self.choices:
            self.stem = f"{self.stem} {line}".strip()
        elif self.last == "explanation":
            self.explanation = f"{self.explanation} {line}".strip()
        elif self.choices and self.last == "choice":
            self.choices[-1] = f"{self.choices[-1]} {line}"


def read_typed(text: str, name: str = "") -> Catalogue:
    """Questions typed by hand: a spreadsheet saved as CSV, or plain text in FORMAT_EXAMPLE's
    shape and its usual variants. A course of their own, named by the # title, else by `name`."""
    found = _read_csv(text) if _looks_csv(text) else _read_plain(text)
    if found is None:
        raise ValueError("I find no questions in it")
    title, typed = found
    title = " ".join((title or name or UNTITLED).split())[:80]
    # The chapters of the questions that can be read: one with none waits for them.
    usable = [q for q in typed if not _problem(q)] or typed
    names = list(dict.fromkeys(q.chapter for q in usable))
    course = blueprints.from_dict(
        {
            "code": title,
            "name": title,
            "exam": False,
            "kinds": ["single", "multiple"],
            "domains": [
                {
                    "id": i,
                    "name": chapter,
                    "weight": 1,
                    "tasks": [{"id": f"{i}.1", "title": chapter, "notions": chapter}],
                }
                for i, chapter in enumerate(names, 1)
            ],
        },
        blueprints.slug(title),
    )
    questions = tuple(
        _question(q, names.index(q.chapter) + 1 if q.chapter in names else 1) for q in typed
    )
    return Catalogue(course=course, questions=questions, origin=TYPED, typed=True)


def _read_plain(text: str) -> tuple[str, list[_Typed]] | None:
    title, chapter = "", ""
    typed: list[_Typed] = []
    current: _Typed | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        heading = _HEADING.match(line)
        if heading and len(heading[1]) == 1:
            title = title or heading[2]
            continue
        if heading and len(heading[1]) == 2:
            chapter = heading[2]
            continue
        asked = _QUESTION.match(line)
        if (heading and len(heading[1]) == 3) or asked:
            stem = heading[2] if heading else asked[1] if asked else ""
            current = _Typed(chapter, stem.strip())
            typed.append(current)
            continue
        if current is None:
            continue  # words before the first question
        said = _FIELD.match(line)
        if said:
            word, rest = said[1].casefold(), said[2].strip()
            if word in ("explanation", "explication", "why", "pourquoi"):
                current.explanation, current.last = rest, "explanation"
            elif word in ("source", "read again", "reference", "référence", "à relire", "a relire"):
                current.source, current.last = rest, "source"
            else:
                current.answer, current.last = rest, "answer"
            continue
        bullet = _BULLET.match(line)
        labelled = _LABELLED.match(line)
        if bullet or labelled:
            if bullet and bullet[1] is not None and bullet[1].strip():
                current.ticked.append(len(current.choices))
            current.choices.append((bullet or labelled)[2].strip())  # type: ignore[index]
            current.last = "choice"
            continue
        current.add(line)
    if not typed:
        return None
    for q in typed:
        q.chapter = q.chapter or title or UNTITLED
    return title, typed


def _looks_csv(text: str) -> bool:
    first = text.strip().splitlines()[0].casefold() if text.strip() else ""
    has = re.split(r"[;,\t]", first)
    names = {h.strip().strip('"') for h in has}
    return (
        len(has) > 2
        and bool(names & {"question", "questions"})
        and bool(names & {"answer", "answers", "réponse", "réponses", "reponse"})
    )


_COLUMNS = {
    "chapter": ("chapter", "chapitre", "domain", "domaine"),
    "question": ("question", "questions"),
    "answer": ("answer", "answers", "réponse", "réponses", "reponse"),
    "explanation": ("explanation", "explication", "why", "pourquoi"),
    "source": ("source", "reference", "référence", "read again", "à relire"),
}


def _read_csv(text: str) -> tuple[str, list[_Typed]] | None:
    sample = text[:4096]
    try:
        dialect: Any = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text.strip()), dialect))
    if len(rows) < 2:
        return None
    header = [h.strip().casefold() for h in rows[0]]

    def column(names: tuple[str, ...]) -> int | None:
        return next((i for i, h in enumerate(header) if h in names), None)

    where = {key: column(names) for key, names in _COLUMNS.items()}
    choices = [i for i, h in enumerate(header) if re.fullmatch(r"[a-f]|choice [1-6]|[1-6]", h)]
    if where["question"] is None or where["answer"] is None or not choices:
        return None
    typed = []
    for row in rows[1:]:

        def cell(at: int | None, row: list[str] = row) -> str:
            return row[at].strip() if at is not None and at < len(row) else ""

        stem = cell(where["question"])
        if not stem:
            continue
        q = _Typed(cell(where["chapter"]), stem)
        q.choices = [c for c in (cell(i) for i in choices) if c]
        q.answer, q.explanation, q.source = (
            cell(where["answer"]),
            cell(where["explanation"]),
            cell(where["source"]),
        )
        typed.append(q)
    if not typed:
        return None
    return "", typed


def _answers(q: _Typed) -> list[int] | str:
    """The right choices' indices, or why none is found."""
    said = q.answer.strip()
    if not said:
        return list(q.ticked) or "no Answer line"
    folded = [c.casefold() for c in q.choices]
    if said.casefold().rstrip(".") in folded:
        return [folded.index(said.casefold().rstrip("."))]
    if _LABELS_ONLY.match(said):
        found = [_index(label) for label in re.findall(r"\b([A-Fa-f]|[1-6])\b", said)]
    else:
        first = re.match(r"^([A-Fa-f]|[1-6])\b\s*[.):-]?", said)
        found = [_index(first[1])] if first else []
    if not found or any(not 0 <= i < len(q.choices) for i in found):
        return "its answer names no choice"
    return sorted(set(found))


def _index(label: str) -> int:
    return int(label) - 1 if label.isdigit() else ord(label.casefold()) - ord("a")


def _question(q: _Typed, domain: int) -> dict[str, Any]:
    """A typed question in the brain's shape; one that cannot be says why, as "problem"."""
    data: dict[str, Any] = {
        "domain": domain,
        "task": f"{domain}.1",
        "topic": " ".join(q.stem.split()[:6])[:80] or "a question",
        "difficulty": "medium",
        "stem": q.stem,
        "choices": q.choices,
        "explanation": q.explanation,
        "why_wrong": [""] * len(q.choices),
        "reference": q.source[:200],
    }
    problem = _problem(q)
    answers = _answers(q)
    if problem:
        data["problem"] = problem
    elif not isinstance(answers, str):
        data["answers"] = answers
        data["kind"] = "single" if len(answers) == 1 else "multiple"
    return data


def _problem(q: _Typed) -> str:
    """Why a typed question cannot be read, or ""."""
    if not q.stem:
        return "no question text"
    if len(q.choices) < 2:
        return "a single choice" if q.choices else "no choices"
    answers = _answers(q)
    return answers if isinstance(answers, str) else ""


def merge(
    known: Blueprint, found: Blueprint, questions: Sequence[Mapping[str, Any]]
) -> tuple[Blueprint, list[dict[str, Any]]]:
    """Typed questions for a course he has: their chapters matched to its own by name or number;
    a chapter it lacks is added, but to a course of exam/, fixed by its guide, where such
    questions are set aside."""
    domains = list(known.domains)
    fixed = known.key in blueprints.known()
    to: dict[int, int | None] = {}
    for chapter in found.domains:
        same = next((d for d in domains if d.name.casefold() == chapter.name.casefold()), None)
        number = _CHAPTER_NUMBER.match(chapter.name)
        if same is None and number and int(number[1]) in {d.id for d in domains}:
            same = known.domain(int(number[1]))
        if same is None and not fixed:
            new = max(d.id for d in domains) + 1
            same = blueprints.Domain(
                new, chapter.name, 1.0, (blueprints.Task(f"{new}.1", chapter.name, chapter.name),)
            )
            domains.append(same)
        to[chapter.id] = same.id if same else None
    merged = replace(known, domains=tuple(domains))
    moved = []
    for data in questions:
        where = to.get(int(data.get("domain") or 0))
        if where is None:
            name = found.domain(int(data["domain"])).name
            moved.append({**data, "problem": f"its chapter, {name}, is not one of {known.code}'s"})
        else:
            moved.append({**data, "domain": where, "task": merged.task_ids(where)[0]})
    return merged, moved


# Why a question was set aside (tagnan.model's checks), as one tells a learner.
_REASONS = {
    "two identical choices": "two of its choices are the same",
    "4 to 6 choices are needed": "it needs four to six choices",
    "2 to 6 choices are needed": "it needs two to six choices",
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
        # Typed by hand, checked lighter: said so, for a colleague to check them so too.
        "questions": [
            {**q.to_dict(), "origin": TYPED} if q.origin == TYPED else q.to_dict()
            for q in questions
        ],
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
