"""A certification question, and how a generated one is checked before it is kept."""

import random
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from tagnan.blueprint import Blueprint

DIFFICULTIES = ("easy", "medium", "hard")
KINDS = ("single", "multiple")
MAX_STEM, MAX_CHOICE, MAX_TEXT = 900, 220, 700
# Who wrote a question that his brain did not (tagnan.catalogue): someone, or an assistant, for
# him; or converted from a quiz of someone else's, kept for oneself and never exported; or typed
# by hand in plain text, one's own notes, checked lighter.
WRITTEN, CONVERTED, TYPED = "written", "converted", "typed"


@dataclass(frozen=True)
class Question:
    domain: int
    task: str
    topic: str  # a few words, to tell the brain what was already asked
    difficulty: str
    kind: str  # "single": one answer; "multiple": two or three
    stem: str
    choices: tuple[str, ...]
    answers: tuple[int, ...]  # indices into choices, sorted
    explanation: str  # why the right answer is right
    why_wrong: tuple[str, ...]  # one per choice, "" for the right ones
    reference: str = ""  # the AWS document to read
    subject: str = ""  # the subject it was written for (tagnan.subject's key), "" for the exam
    origin: str = ""  # "" his brain; WRITTEN, CONVERTED or TYPED: from a catalogue
    id: int | None = None

    def is_correct(self, chosen: Iterable[int]) -> bool:
        return tuple(sorted(set(chosen))) == self.answers

    def shuffled(self, rng: random.Random) -> "Question":
        """The same question with its choices in a random order (models favour B and C)."""
        order = list(range(len(self.choices)))
        rng.shuffle(order)
        return replace(
            self,
            choices=tuple(self.choices[i] for i in order),
            why_wrong=tuple(self.why_wrong[i] for i in order),
            answers=tuple(sorted(order.index(i) for i in self.answers)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "task": self.task,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "kind": self.kind,
            "stem": self.stem,
            "choices": list(self.choices),
            "answers": list(self.answers),
            "explanation": self.explanation,
            "why_wrong": list(self.why_wrong),
            "reference": self.reference,
        }


# A word of a language course: its limits, and how its place is marked in its example.
MAX_TERM, MAX_MEANING, MAX_EXAMPLE, MAX_NOTE = 80, 120, 240, 200
_MARK = re.compile(r"\*\*(.+?)\*\*")


@dataclass(frozen=True)
class Card:
    """A word of a language course (tagnan.language): Tagnan builds his exercises from it, and
    asks it step after step of the ladder (tagnan.progress) until it is known."""

    domain: int  # its chapter
    term: str  # in the language learned, as one would type it: "la cuenta", "madrugar"
    meaning: str  # in the language one speaks: "the bill"
    example: str = ""  # a sentence it lives in, the word marked: "¿Nos trae **la cuenta**?"
    translation: str = ""  # that sentence, in the language one speaks
    note: str = ""  # a trap worth a line: a false friend, an irregular form
    also: tuple[str, ...] = ()  # other words that mean the same: right too, when typed
    origin: str = ""  # "" his brain; WRITTEN or TYPED: from a catalogue
    id: int | None = None
    step: int = 0  # where it stands on the ladder: 0 new, 6 known
    due_at: float = 0.0  # when it comes back
    seen_at: float = 0.0  # when it was last shown or asked

    @property
    def gap(self) -> tuple[str, str, str] | None:
        """Its example around the word: what comes before, the word as written there, what
        comes after; None when the example does not hold the word as it is."""
        found = _MARK.search(self.example)
        if found is None:
            return None
        return self.example[: found.start()], found[1], self.example[found.end() :]

    @property
    def sentence(self) -> str:
        """Its example, as one reads it."""
        return _MARK.sub(r"\1", self.example)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "term": self.term,
            "meaning": self.meaning,
            "example": self.example,
            "translation": self.translation,
            "note": self.note,
            "also": list(self.also),
        }


def mark(example: str, term: str) -> str:
    """An example with its word marked, once: as the writer marked it if that is the word
    itself, else where the word stands in it; unmarked when it is not there as it is (another
    form of it: the gap could not be filled with the word)."""
    alike = " ".join(term.casefold().split())
    found = _MARK.search(example)
    if found and " ".join(found[1].casefold().split()) == alike:
        return example[: found.end()] + _MARK.sub(r"\1", example[found.end() :])
    plain = _MARK.sub(r"\1", example)
    at = re.search(rf"(?<![^\W_]){re.escape(alike)}(?![^\W_])", plain, re.IGNORECASE)
    if at is None:
        return plain
    return f"{plain[: at.start()]}**{plain[at.start() : at.end()]}**{plain[at.end() :]}"


def parse_card(data: Mapping[str, Any], blueprint: Blueprint) -> Card:
    """Check a word as the brain or a list gives it; ValueError says what is wrong. Its chapter
    is its "domain", or "chapter" as the brain names it."""
    domain = data.get("domain", data.get("chapter"))
    if not isinstance(domain, int) or domain not in {d.id for d in blueprint.domains}:
        raise ValueError(f"unknown chapter: {domain!r}")
    term = _text(data, "term", MAX_TERM)
    meaning = _text(data, "meaning", MAX_MEANING)
    if term.casefold() == meaning.casefold():
        raise ValueError("its meaning is the word itself")
    raw_also = data.get("also") or []
    if not isinstance(raw_also, list):
        raise ValueError("also: a list of words expected")
    also = tuple(
        dict.fromkeys(
            word
            for word in (_text({"also": w}, "also", MAX_TERM, required=False) for w in raw_also)
            if word and word.casefold() != term.casefold()
        )
    )
    return Card(
        domain=domain,
        term=term,
        meaning=meaning,
        example=mark(_text(data, "example", MAX_EXAMPLE, required=False), term),
        translation=_text(data, "translation", MAX_EXAMPLE, required=False),
        note=_text(data, "note", MAX_NOTE, required=False),
        also=also[:4],
    )


def _text(data: Mapping[str, Any], key: str, limit: int, required: bool = True) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"{key}: text expected")
    value = " ".join(value.split())
    if required and not value:
        raise ValueError(f"{key}: empty")
    if len(value) > limit:
        raise ValueError(f"{key}: too long ({len(value)} characters)")
    return value


def parse_question(
    data: Mapping[str, Any], blueprint: Blueprint, lighter: bool = False
) -> Question:
    """Check a question as the brain wrote it; ValueError says what is wrong. Lighter, for one
    typed by hand: two to six choices, and no explanation needed, nor why each one is wrong."""
    domain = data.get("domain")
    if not isinstance(domain, int) or domain not in {d.id for d in blueprint.domains}:
        raise ValueError(f"unknown domain: {domain!r}")
    task = _text(data, "task", 10)
    if task not in blueprint.task_ids(domain):
        raise ValueError(f"task {task} is not in domain {domain}")
    kind = data.get("kind")
    if kind not in KINDS or kind not in blueprint.kinds:
        raise ValueError(f"unknown question kind: {kind!r}")
    difficulty = data.get("difficulty")
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"unknown difficulty: {difficulty!r}")
    raw_choices = data.get("choices")
    fewest = 2 if lighter else 4
    if not isinstance(raw_choices, list) or not fewest <= len(raw_choices) <= 6:
        raise ValueError(f"{fewest} to 6 choices are needed")
    choices = tuple(_text({"choice": c}, "choice", MAX_CHOICE) for c in raw_choices)
    if len({c.casefold() for c in choices}) != len(choices):
        raise ValueError("two identical choices")
    raw_answers = data.get("answers")
    if not isinstance(raw_answers, list) or not all(isinstance(a, int) for a in raw_answers):
        raise ValueError("answers: a list of indices expected")
    answers = tuple(sorted(set(raw_answers)))
    if len(answers) != len(raw_answers) or any(not 0 <= a < len(choices) for a in answers):
        raise ValueError(f"invalid answer indices: {raw_answers}")
    if kind == "single" and len(answers) != 1:
        raise ValueError("a single-answer question has exactly one right answer")
    if kind == "multiple" and not 2 <= len(answers) <= min(3, len(choices) - 1):
        raise ValueError("a multiple-answer question has two or three")
    raw_why = data.get("why_wrong")
    if lighter and (not isinstance(raw_why, list) or len(raw_why) != len(choices)):
        raw_why = [""] * len(choices)
    if not isinstance(raw_why, list) or len(raw_why) != len(choices):
        raise ValueError("why_wrong: one text per choice")
    why_wrong = tuple(
        "" if i in answers else _text({"why_wrong": w}, "why_wrong", MAX_TEXT, required=not lighter)
        for i, w in enumerate(raw_why)
    )
    return Question(
        domain=domain,
        task=task,
        topic=_text(data, "topic", 80),
        difficulty=str(difficulty),
        kind=str(kind),
        stem=_text(data, "stem", MAX_STEM),
        choices=choices,
        answers=answers,
        explanation=_text(data, "explanation", MAX_TEXT, required=not lighter),
        why_wrong=why_wrong,
        reference=_text(data, "reference", 200, required=False),
    )
