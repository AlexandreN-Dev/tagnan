"""A language course's exercises: how a word is asked at its step of the ladder
(tagnan.progress), built from the course's cards alone, with no brain: the choices are his other
words. A call asks a few of them in a row, a bout; each one is a touch.

Standard library only, as the game.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from tagnan import language
from tagnan.model import Card
from tagnan.progress import KNOWN, Progress

# How a word is asked. MEET shows it, and asks nothing.
MEET, MEANING, WORD, GAP, TYPE, TYPE_GAP = "meet", "meaning", "word", "gap", "type", "type-gap"
TYPED = (TYPE, TYPE_GAP)
BOUT = 4  # touches at a call, at most
NEW_AT_ONCE = 2  # new words shown in a bout, at most: reviews come first
CHOICES = 4
LOOK_ALIKES = 6  # the words most like it, among which the wrong choices are drawn
REST = 600.0  # a word asked ahead of its time has rested this long at least


@dataclass(frozen=True)
class Slot:
    """A word of a bout: built into a touch when its turn comes, as it stands then."""

    card_id: int
    early: bool = False  # asked ahead of its time, for want of anything due or new


@dataclass(frozen=True)
class Touch:
    card: Card
    kind: str
    choices: tuple[str, ...] = ()  # what one picks among: meanings, or words
    answer: int = -1  # the right one's index
    behind: tuple[Card, ...] = ()  # the word behind each choice: what a wrong pick means
    early: bool = False

    @property
    def expected(self) -> str:
        """What is to be typed: the word, or the word as its example writes it."""
        gap = self.card.gap
        return gap[1] if self.kind == TYPE_GAP and gap else self.card.term


@dataclass(frozen=True)
class Touched:
    """What an answer made of a touch."""

    touch: Touch
    correct: bool
    remark: str  # tagnan.language's RIGHT, ACCENT, ARTICLE, ALSO or WRONG
    picked: int | None  # the choice picked
    typed: str  # or the word typed
    delta: int
    before: Progress
    after: Progress
    step: int  # where the word stands now
    due_at: float  # when it comes back
    moved: bool  # False: right ahead of its time, it stays where it was

    @property
    def promoted(self) -> bool:
        return self.after.grade > self.before.grade


def kind_for(card: Card, rivals: bool) -> str:
    """How a word is asked on its step: its meaning picked, the word picked, the word in its
    sentence, then typed. A word one cannot type (another alphabet) or with no sentence keeps
    to what it has; with no other word to pick among, it is typed."""
    can_type = language.typable(card.term)
    has_gap = card.gap is not None
    if card.step >= 4 and can_type:
        return TYPE_GAP if card.step >= 5 and has_gap else TYPE
    if not rivals:
        return TYPE if can_type else MEANING
    if card.step <= 1:
        return MEANING
    if card.step == 2:
        return WORD
    return GAP if has_gap else WORD


def build(card: Card, others: Sequence[Card], rng: random.Random, early: bool = False) -> Touch:
    """A word's touch, as it stands: the wrong choices are other words of the course, of its
    chapter first for a meaning, the ones that look most like it for a word."""
    same = {language.fold(card.term), *(language.fold(word) for word in card.also)}
    rivals = [
        o
        for o in others
        if o.id != card.id
        and language.fold(o.term) not in same
        and language.fold(o.meaning) != language.fold(card.meaning)
    ]
    kind = kind_for(card, bool(rivals))
    if kind in TYPED:
        return Touch(card, kind, early=early)
    by_meaning = kind == MEANING
    seen: set[str] = set()
    distinct = []
    for rival in rivals:  # two words with one meaning, or one word twice, make one choice
        shown = language.fold(rival.meaning if by_meaning else rival.term)
        if shown not in seen:
            seen.add(shown)
            distinct.append(rival)
    wanted = CHOICES - 1
    if by_meaning:
        near = [r for r in distinct if r.domain == card.domain]
        far = [r for r in distinct if r.domain != card.domain]
        picked = rng.sample(near, min(wanted, len(near)))
        picked += rng.sample(far, min(wanted - len(picked), len(far)))
    else:
        mine = language.bare(card.term)
        alike = sorted(
            distinct,
            key=lambda r: -SequenceMatcher(None, mine, language.bare(r.term)).ratio(),
        )[:LOOK_ALIKES]
        picked = rng.sample(alike, min(wanted, len(alike)))
    order = [*picked, card]
    rng.shuffle(order)
    return Touch(
        card,
        kind,
        tuple(c.meaning if by_meaning else c.term for c in order),
        order.index(card),
        tuple(order),
        early,
    )


def as_question(
    touch: Touch, picked: int | None, typed: str, learned: str
) -> tuple[dict[str, Any], list[int]]:
    """A touch as a question his brain can explain (Tell me more), and the answer given."""
    card = touch.card
    gap = card.gap
    if touch.kind in (GAP, TYPE_GAP) and gap:
        stem = f"{gap[0]}____{gap[2]}" + (f" ({card.translation})" if card.translation else "")
    elif touch.kind == MEANING:
        stem = f'What does "{card.term}" mean?'
    else:
        stem = f'How does one say "{card.meaning}" in {learned}?'
    if touch.kind in TYPED:
        choices = [touch.expected, typed.strip() or "(no answer)"]
        answers, chosen = [0], [1]
    else:
        choices = list(touch.choices)
        answers = [touch.answer]
        chosen = [] if picked is None else [picked]
    explanation = f"{card.term}: {card.meaning}."
    if card.example:
        explanation += f" {card.sentence}"
    if card.note:
        explanation += f" {card.note}"
    return (
        {"stem": stem, "choices": choices, "answers": answers, "explanation": explanation},
        chosen,
    )


def plan(cards: Sequence[Card], now: float) -> list[Slot]:
    """The words of a bout: the new ones it may show, then those due, the longest due first;
    with none of either, the words nearest their time, asked ahead of it."""
    due = sorted((c for c in cards if c.step > 0 and c.due_at <= now), key=lambda c: c.due_at)
    due = due[:BOUT]
    fresh = [c for c in cards if c.step == 0][: max(0, min(NEW_AT_ONCE, BOUT - len(due)))]
    slots = [Slot(c.id) for c in (*fresh, *due) if c.id is not None]
    if slots:
        return slots
    ahead = sorted(
        (c for c in cards if 0 < c.step < KNOWN and c.seen_at <= now - REST),
        key=lambda c: c.due_at,
    )
    return [Slot(c.id, early=True) for c in ahead[:BOUT] if c.id is not None]
