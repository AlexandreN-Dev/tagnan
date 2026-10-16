"""A certification question, and how a generated one is checked before it is kept."""

import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from tagnan.blueprint import Blueprint

DIFFICULTIES = ("facile", "moyen", "difficile")
KINDS = ("single", "multiple")
MAX_STEM, MAX_CHOICE, MAX_TEXT = 900, 220, 700


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


def _text(data: Mapping[str, Any], key: str, limit: int, required: bool = True) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"{key} : texte attendu")
    value = " ".join(value.split())
    if required and not value:
        raise ValueError(f"{key} : vide")
    if len(value) > limit:
        raise ValueError(f"{key} : trop long ({len(value)} caractères)")
    return value


def parse_question(data: Mapping[str, Any], blueprint: Blueprint) -> Question:
    """Check a question as the brain wrote it; ValueError says what is wrong."""
    domain = data.get("domain")
    if not isinstance(domain, int) or domain not in {d.id for d in blueprint.domains}:
        raise ValueError(f"domaine inconnu : {domain!r}")
    task = _text(data, "task", 10)
    if task not in blueprint.task_ids(domain):
        raise ValueError(f"tâche {task} hors du domaine {domain}")
    kind = data.get("kind")
    if kind not in KINDS or kind not in blueprint.kinds:
        raise ValueError(f"type de question inconnu : {kind!r}")
    difficulty = data.get("difficulty")
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"difficulté inconnue : {difficulty!r}")
    raw_choices = data.get("choices")
    if not isinstance(raw_choices, list) or not 4 <= len(raw_choices) <= 6:
        raise ValueError("il faut de 4 à 6 choix")
    choices = tuple(_text({"choix": c}, "choix", MAX_CHOICE) for c in raw_choices)
    if len({c.casefold() for c in choices}) != len(choices):
        raise ValueError("deux choix identiques")
    raw_answers = data.get("answers")
    if not isinstance(raw_answers, list) or not all(isinstance(a, int) for a in raw_answers):
        raise ValueError("answers : liste d'indices attendue")
    answers = tuple(sorted(set(raw_answers)))
    if len(answers) != len(raw_answers) or any(not 0 <= a < len(choices) for a in answers):
        raise ValueError(f"indices de réponse invalides : {raw_answers}")
    if kind == "single" and len(answers) != 1:
        raise ValueError("une question à réponse unique a exactement une bonne réponse")
    if kind == "multiple" and not 2 <= len(answers) <= 3:
        raise ValueError("une question à réponses multiples en a deux ou trois")
    raw_why = data.get("why_wrong")
    if not isinstance(raw_why, list) or len(raw_why) != len(choices):
        raise ValueError("why_wrong : un texte par choix")
    why_wrong = tuple(
        "" if i in answers else _text({"pourquoi": w}, "pourquoi", MAX_TEXT)
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
        explanation=_text(data, "explanation", MAX_TEXT),
        why_wrong=why_wrong,
        reference=_text(data, "reference", 200, required=False),
    )
