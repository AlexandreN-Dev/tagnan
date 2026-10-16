"""What Tagnan's questions are about: the whole exam, one of its domains, or a subject in one's
own words ("RAG", "Bedrock Guardrails"). He keeps to it until told otherwise."""

import re
from dataclasses import dataclass

from tagnan.blueprint import Blueprint
from tagnan.model import Question

MAX_TEXT = 80
WHOLE_WORDS = frozenset(
    {
        "all",
        "any",
        "anything",
        "everything",
        "exam",
        "the exam",
        "whole exam",
        "the whole exam",
        "all domains",
        "tout",
        "tout l'examen",
        "l'examen",
    }
)
DOMAIN_WORDS = re.compile(r"^(?:domain|domaine|d)?\s*#?\s*(\d+)$")


@dataclass(frozen=True)
class Subject:
    domain: int | None = None  # one of the exam's domains
    text: str = ""  # a subject in one's own words

    @property
    def key(self) -> str:
        """How it is kept, in the database and on each question written for it."""
        if self.domain is not None:
            return f"domain:{self.domain}"
        return self.text

    @property
    def whole(self) -> bool:
        return self.domain is None and not self.text

    def covers(self, question: Question) -> bool:
        if self.domain is not None:
            return question.domain == self.domain
        if self.text:
            return question.subject.casefold() == self.text.casefold()
        return True

    def name(self, bp: Blueprint) -> str:
        if self.domain is not None:
            return f"Domain {self.domain} · {bp.domain(self.domain).name}"
        return self.text or "the whole exam"


def from_key(key: str) -> Subject:
    if key.startswith("domain:") and key[7:].isdigit():
        return Subject(domain=int(key[7:]))
    return Subject(text=key)


def parse(text: str, bp: Blueprint) -> Subject:
    """What one asked for, in words; ValueError says what does not do."""
    said = " ".join(text.split()).strip(" .!?")
    if not said:
        raise ValueError("Tell me a subject.")
    folded = said.casefold()
    if folded in WHOLE_WORDS:
        return Subject()
    ids = {d.id for d in bp.domains}
    found = DOMAIN_WORDS.match(folded)
    if found:
        number = int(found.group(1))
        if number not in ids:
            raise ValueError(f"The exam has domains {min(ids)} to {max(ids)}.")
        return Subject(domain=number)
    for domain in bp.domains:
        if folded == domain.name.casefold():
            return Subject(domain=domain.id)
    if len(said) > MAX_TEXT:
        raise ValueError(f"Shorter, please: {MAX_TEXT} characters at most.")
    return Subject(text=said)
