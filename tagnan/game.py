"""The rules in one place, for the window and the terminal: what to ask, what an answer earns,
and when to ask the brain for more questions."""

import random
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tagnan import progress as rules
from tagnan.blueprint import Blueprint
from tagnan.model import Question, parse_question
from tagnan.progress import Progress
from tagnan.store import Store

# Ask the brain for a new batch below this many fresh questions; a batch takes a minute or two.
LOW_WATER = 5
BATCH = 10
# Each grade asks questions of its own level: easy ones in the inkwell only, then the exam's
# usual level, hard ones for the last two grades; multiple-answer questions from the Gascon on.
DIFFICULTY_BY_GRADE = ("facile", "moyen", "moyen", "moyen", "difficile", "difficile")
MULTIPLE_SHARE_BY_GRADE = (0.0, 0.1, 0.15, 0.2, 0.25, 0.3)
REVIEW_SHARE = 0.5  # when reviews are due, half the questions are reviews
AVOID_TOPICS = 60


@dataclass(frozen=True)
class Outcome:
    question: Question
    chosen: tuple[int, ...]
    correct: bool
    delta: int
    before: Progress
    after: Progress
    review_box: int | None  # where the question goes next; None: not to review

    @property
    def promoted(self) -> bool:
        return self.after.grade > self.before.grade

    @property
    def demoted(self) -> bool:
        return self.after.grade < self.before.grade


class Game:
    def __init__(self, store: Store, blueprint: Blueprint, rng: random.Random) -> None:
        self.store = store
        self.blueprint = blueprint
        self._rng = rng

    @property
    def exam(self) -> str:
        return self.blueprint.key

    @property
    def progress(self) -> Progress:
        return rules.settle(self.store.progress(self.exam))

    # --- Asking -----------------------------------------------------------------------------

    def next_question(self, now: float) -> Question | None:
        """A review that is due, or a fresh question from a domain to work on."""
        due = self.store.due_reviews(self.exam, now)
        fresh = self.store.fresh(self.exam)
        if due and (not fresh or self._rng.random() < REVIEW_SHARE):
            return due[0]
        if not fresh:
            return None
        weights = self.domain_weights()
        by_domain: dict[int, list[Question]] = {}
        for q in fresh:
            by_domain.setdefault(q.domain, []).append(q)
        domains = sorted(by_domain)
        domain = self._rng.choices(domains, weights=[weights.get(d, 1.0) for d in domains])[0]
        level = DIFFICULTY_BY_GRADE[self.progress.grade]
        pool = [q for q in by_domain[domain] if q.difficulty == level] or by_domain[domain]
        return self._rng.choice(pool)

    def domain_weights(self) -> dict[int, float]:
        """The exam's weights, leaning towards the domains where you miss most."""
        stats = self.store.domain_stats(self.exam)
        weights = {}
        for domain in self.blueprint.domains:
            answered, right = stats.get(domain.id, (0, 0))
            accuracy = (right + 1) / (answered + 2)  # one right and one wrong to start with
            weights[domain.id] = domain.weight * (0.5 + (1 - accuracy))
        return weights

    # --- Answering --------------------------------------------------------------------------

    def answer(self, question: Question, chosen: Iterable[int], now: float) -> Outcome:
        if question.id is None:
            raise ValueError("question absente de la base")
        picked = tuple(sorted(set(chosen)))
        correct = question.is_correct(picked)
        before = self.progress
        after, delta = rules.after_answer(before, correct)
        box = rules.after_review(self.store.review_box(question.id), correct)
        self.store.record_answer(question.id, picked, correct, delta, now)
        self.store.set_review(question.id, box, rules.due_at(box, now) if box else 0.0)
        self.store.save_progress(self.exam, after)
        return Outcome(question, picked, correct, delta, before, after, box)

    # --- Feeding the bank -------------------------------------------------------------------

    def needs_questions(self) -> bool:
        return self.store.fresh_count(self.exam) < LOW_WATER

    def batch_request(self, count: int = BATCH) -> dict[str, Any]:
        """What to ask the brain for: one slot per question, the topics to avoid."""
        grade = self.progress.grade
        weights = self.domain_weights()
        domains = sorted(weights)
        picked = self._rng.choices(domains, weights=[weights[d] for d in domains], k=count)
        multiple = round(count * MULTIPLE_SHARE_BY_GRADE[grade])
        slots = [
            {
                "domain": domain,
                "difficulty": DIFFICULTY_BY_GRADE[grade],
                "kind": "multiple"
                if i < multiple and "multiple" in self.blueprint.kinds
                else "single",
            }
            for i, domain in enumerate(sorted(picked))
        ]
        return {
            "exam": self.exam,
            "slots": slots,
            "avoid": self.store.recent_topics(self.exam, AVOID_TOPICS),
        }

    def add_batch(
        self, raw: Sequence[Mapping[str, Any]], now: float
    ) -> tuple[list[int], list[str]]:
        """Keep the questions that hold up, shuffled; say why the others were dropped."""
        kept, rejected = [], []
        for i, data in enumerate(raw, 1):
            try:
                kept.append(parse_question(data, self.blueprint).shuffled(self._rng))
            except ValueError as error:
                rejected.append(f"question {i} : {error}")
        return self.store.add_questions(self.exam, kept, now), rejected

    def summary(self) -> dict[str, Any]:
        """What the stats show: grade, points, streaks, accuracy by domain, the bank."""
        p = self.progress
        stats = self.store.domain_stats(self.exam)
        answered = sum(n for n, _ in stats.values())
        right = sum(r for _, r in stats.values())
        return {
            "grade": p.grade,
            "grade_name": rules.GRADES[p.grade].name,
            "points": p.points,
            "next_threshold": p.next_threshold,
            "next_name": rules.GRADES[p.grade + 1].name if p.next_threshold is not None else None,
            "streak": p.streak,
            "best_streak": p.best_streak,
            "answered": answered,
            "right": right,
            "domains": [
                {
                    "id": d.id,
                    "name": d.name,
                    "answered": stats.get(d.id, (0, 0))[0],
                    "right": stats.get(d.id, (0, 0))[1],
                }
                for d in self.blueprint.domains
            ],
            "fresh": self.store.fresh_count(self.exam),
            "reviews": self.store.reviews_pending(self.exam),
        }


def slot_summary(slots: Sequence[Mapping[str, Any]]) -> Counter[tuple[int, str, str]]:
    return Counter((int(s["domain"]), str(s["difficulty"]), str(s["kind"])) for s in slots)
