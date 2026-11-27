"""What Tagnan teaches: a course's blueprint, its domains, their weights and tasks. A certification
comes from a file of exam/ (exam/*.toml); any other subject, from pottery to another AWS exam, has
its blueprint drawn up once by the brain and kept in the database."""

import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from tagnan.paths import EXAMS_DIR

# How the brain writes when the blueprint says nothing of its own.
DEFAULT_GUIDANCE = (
    "You write accurate, unambiguous questions about stable, well-established facts, the kind"
    " a good teacher or textbook would stand by. If a fact seems uncertain to you, choose"
    " another notion."
)
DEFAULT_REFERENCE = "a well-known book, chapter or reference work to read again"


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    notions: str


@dataclass(frozen=True)
class Domain:
    id: int
    name: str
    weight: float
    tasks: tuple[Task, ...]


@dataclass(frozen=True)
class Language:
    """What makes a course a language course: its words are asked, not questions about it."""

    learned: str  # the language, in English: "Spanish"
    speaks: str = ""  # the language one speaks: meanings and explanations come in it
    level: str = ""  # "A2" (tagnan.language's LEVELS); "" for a word list of one's own
    first: int = 1  # the first chapter of that level: the ones before are of levels left behind

    def to_dict(self) -> dict[str, Any]:
        return {
            "learned": self.learned,
            "speaks": self.speaks,
            "level": self.level,
            "first": self.first,
        }


@dataclass(frozen=True)
class Blueprint:
    key: str  # e.g. "aif-c01", the file name without extension, or "pottery"
    code: str
    name: str
    kinds: tuple[str, ...]
    services: tuple[str, ...]  # the terms in scope, named exactly (AWS services for AWS exams)
    domains: tuple[Domain, ...]
    exam: bool = True  # a certification exam, rather than a subject learned for its own sake
    guidance: str = DEFAULT_GUIDANCE  # how the brain writes its questions
    reference: str = DEFAULT_REFERENCE  # what a question's reference points to
    language: Language | None = None  # a language course: its words, its level

    def domain(self, domain_id: int) -> Domain:
        for domain in self.domains:
            if domain.id == domain_id:
                return domain
        raise KeyError(domain_id)

    def task_ids(self, domain_id: int) -> tuple[str, ...]:
        return tuple(task.id for task in self.domain(domain_id).tasks)

    @property
    def whole(self) -> str:
        """All of it, in words."""
        return "the whole exam" if self.exam else f"all of {self.name}"

    @property
    def title(self) -> str:
        """Its name, with its level for a language course: "Spanish A2"."""
        level = self.language.level if self.language else ""
        return f"{self.name} {level}" if level else self.name

    def to_dict(self) -> dict[str, Any]:
        language = {"language": self.language.to_dict()} if self.language else {}
        return {
            **language,
            "key": self.key,
            "code": self.code,
            "name": self.name,
            "exam": self.exam,
            "guidance": self.guidance,
            "reference": self.reference,
            "kinds": list(self.kinds),
            "services": list(self.services),
            "domains": [
                {
                    "id": d.id,
                    "name": d.name,
                    "weight": d.weight,
                    "tasks": [
                        {"id": t.id, "title": t.title, "notions": t.notions} for t in d.tasks
                    ],
                }
                for d in self.domains
            ],
        }


def from_dict(data: Mapping[str, Any], key: str = "", where: str = "blueprint") -> Blueprint:
    """A blueprint from a file of exam/ or from the brain; ValueError says what is wrong."""
    try:
        domains = tuple(
            Domain(
                id=int(d["id"]),
                name=" ".join(str(d["name"]).split()),
                weight=float(d["weight"]),
                tasks=tuple(
                    Task(
                        id=str(t["id"]).strip(),
                        title=" ".join(str(t["title"]).split()),
                        notions=" ".join(str(t["notions"]).split()),
                    )
                    for t in d["tasks"]
                ),
            )
            for d in data["domains"]
        )
        name = " ".join(str(data["name"]).split())
        code = " ".join(str(data.get("code") or name).split())
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{where}: incomplete ({error})") from None
    if not domains or any(not d.tasks or d.weight <= 0 for d in domains):
        raise ValueError(f"{where}: each domain needs a weight and at least one task")
    if len({d.id for d in domains}) != len(domains):
        raise ValueError(f"{where}: two domains with the same id")
    if not name:
        raise ValueError(f"{where}: no name")
    spoken = data.get("language")
    language = None
    if isinstance(spoken, Mapping):
        first = spoken.get("first")
        language = Language(
            learned=" ".join(str(spoken.get("learned") or name).split())[:40],
            speaks=" ".join(str(spoken.get("speaks") or "").split())[:40],
            level=" ".join(str(spoken.get("level") or "").split())[:4],
            first=first if isinstance(first, int) and first in {d.id for d in domains} else 1,
        )
    return Blueprint(
        key=str(key or data.get("key") or slug(code)),
        code=code,
        name=name,
        kinds=tuple(str(k) for k in data.get("kinds", ["single"])),
        services=tuple(str(s) for s in data.get("services", [])),
        domains=domains,
        exam=bool(data.get("exam", True)),
        guidance=" ".join(str(data.get("guidance") or DEFAULT_GUIDANCE).split()),
        reference=" ".join(str(data.get("reference") or DEFAULT_REFERENCE).split()),
        language=language,
    )


# How the brain writes for a language course, whatever the language.
LANGUAGE_GUIDANCE = (
    "You choose the words a learner of that level meets and needs most, the commonest first, and"
    " example sentences a native speaker would say, short and natural. If you are not sure of a"
    " word, its gender or its use, choose another."
)


def language_course(
    learned: str, speaks: str, level: str, chapters: Sequence[tuple[str, str]]
) -> Blueprint:
    """A language course from its chapters, each a name and what its words are about."""
    if not chapters:
        raise ValueError("a language course needs chapters")
    return Blueprint(
        key=slug(learned),
        code=learned,
        name=learned,
        kinds=("single",),
        services=(),
        domains=_chapters(chapters, 1),
        exam=False,
        guidance=LANGUAGE_GUIDANCE,
        language=Language(learned, speaks, level),
    )


def raise_level(bp: Blueprint, level: str, chapters: Sequence[tuple[str, str]]) -> Blueprint:
    """The same course a level up: its new chapters after the ones it has, whose words stay."""
    if bp.language is None or not chapters:
        raise ValueError("not a language course, or no chapters")
    first = max(d.id for d in bp.domains) + 1
    return replace(
        bp,
        domains=(*bp.domains, *_chapters(chapters, first)),
        language=replace(bp.language, level=level, first=first),
    )


def _chapters(chapters: Sequence[tuple[str, str]], first: int) -> tuple[Domain, ...]:
    return tuple(
        Domain(
            id=i,
            name=" ".join(name.split()),
            weight=1.0,
            tasks=(Task(f"{i}.1", " ".join(name.split()), " ".join(about.split())),),
        )
        for i, (name, about) in enumerate(chapters, first)
    )


def slug(text: str) -> str:
    """A course's key from its code: "SAA-C03" gives "saa-c03", "Pottery" gives "pottery"."""
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")[:40] or "course"


def known(directory: Path = EXAMS_DIR) -> list[str]:
    """The courses that come with Tagnan, as files of exam/."""
    return sorted(p.stem for p in directory.glob("*.toml"))


def load(key: str, directory: Path = EXAMS_DIR) -> Blueprint:
    path = directory / f"{key}.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"unknown exam: {key} (no file {path})") from None
    return from_dict(data, key, str(path))
