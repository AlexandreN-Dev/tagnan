"""The rules in one place, for the window and the terminal: what to ask, what an answer earns,
and when to ask the brain for more questions."""

import json
import random
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from tagnan import blueprint as blueprints
from tagnan import progress as rules
from tagnan.blueprint import Blueprint
from tagnan.model import Question, parse_question
from tagnan.progress import Progress
from tagnan.store import Store
from tagnan.subject import Subject, from_key

# Ask the brain for a new batch below this many fresh questions; a batch takes a minute or two.
LOW_WATER = 5
BATCH = 10
# Each grade asks questions of its own level: easy ones in the inkwell only, then the exam's
# usual level, hard ones for the last two grades; multiple-answer questions from the Gascon on.
DIFFICULTY_BY_GRADE = ("easy", "medium", "medium", "medium", "hard", "hard")
MULTIPLE_SHARE_BY_GRADE = (0.0, 0.1, 0.15, 0.2, 0.25, 0.3)
REVIEW_SHARE = 0.5  # when reviews are due, half the questions are reviews
AVOID_TOPICS = 60
PUT_AWAY = "courses put away"  # setting: the keys of the courses no longer offered


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
    """blueprint: the course learned until one chooses another (the config file's exam)."""

    def __init__(self, store: Store, blueprint: Blueprint, rng: random.Random) -> None:
        self.store = store
        self._default = blueprint
        self._courses: dict[str, Blueprint] = {blueprint.key: blueprint}
        self._rng = rng

    @property
    def exam(self) -> str:
        """The course learned now: its key, under which its questions and progress are kept."""
        return self.blueprint.key

    @property
    def progress(self) -> Progress:
        """Tagnan's grade and points in the course learned now: each course has its own."""
        return rules.settle(self.store.progress(self.exam))

    # --- The course -------------------------------------------------------------------------

    @property
    def blueprint(self) -> Blueprint:
        try:
            return self.course(self.store.setting("course") or self._default.key)
        except KeyError:
            return self._default

    def course(self, key: str) -> Blueprint:
        """A course by its key: one learned before, or a file of exam/; KeyError otherwise."""
        if key not in self._courses:
            kept = self.store.setting(f"course:{key}")
            if kept:
                self._courses[key] = blueprints.from_dict(json.loads(kept), key)
            elif key in blueprints.known():
                self._courses[key] = blueprints.load(key)
            else:
                raise KeyError(key)
        return self._courses[key]

    def set_course(self, bp: Blueprint) -> None:
        """Learn this course from now on; one drawn up by the brain is kept for good."""
        if bp.key not in blueprints.known():
            self.store.set_setting(f"course:{bp.key}", json.dumps(bp.to_dict(), ensure_ascii=False))
        self._courses[bp.key] = bp
        self.store.set_setting("course", bp.key)
        self.bring_back(bp.key)

    def courses(self) -> list[Blueprint]:
        """The courses one can go back to: the one learned now first, then the others, but
        those put away."""
        put_away = self._put_away()
        return [bp for bp in self._known_courses() if bp.key == self.exam or bp.key not in put_away]

    def _known_courses(self) -> list[Blueprint]:
        keys = [self.exam, self._default.key, *self.store.course_keys(), *blueprints.known()]
        found = []
        for key in dict.fromkeys(keys):
            try:
                found.append(self.course(key))
            except (KeyError, ValueError):
                continue
        return found

    def put_away(self, key: str) -> None:
        """No longer offer this course; its questions and progress are kept, and learning it
        again brings it back. Not the course learned now: ValueError."""
        if key == self.exam:
            raise ValueError("the course learned now")
        self.course(key)  # KeyError for an unknown one
        put_away = self._put_away() | {key}
        self.store.set_setting(PUT_AWAY, json.dumps(sorted(put_away)))

    def bring_back(self, key: str) -> None:
        put_away = self._put_away()
        if key in put_away:
            self.store.set_setting(PUT_AWAY, json.dumps(sorted(put_away - {key})))

    def _put_away(self) -> set[str]:
        try:
            return set(json.loads(self.store.setting(PUT_AWAY) or "[]"))
        except ValueError:
            return set()

    def find_course(self, words: str) -> Blueprint | None:
        """A known course, named by its key, its code or its name: one put away too."""
        said = " ".join(words.split()).strip(" .!?").casefold()
        for bp in self._known_courses():
            if said in (bp.key.casefold(), bp.code.casefold(), bp.name.casefold()):
                return bp
        return None

    def topic(self) -> str:
        """What he asks about now, in words: the course, or the subject within it."""
        bp, subject = self.blueprint, self.subject
        return bp.name if subject.whole else f"{subject.name(bp)} ({bp.code})"

    # --- The subject ------------------------------------------------------------------------

    @property
    def subject(self) -> Subject:
        """What he asks about, kept until one asks for something else."""
        return from_key(self.store.setting(f"subject:{self.exam}"))

    def set_subject(self, subject: Subject) -> None:
        self.store.set_setting(f"subject:{self.exam}", subject.key)

    def fresh(self) -> list[Question]:
        """The questions never asked, on the subject."""
        subject = self.subject
        return [q for q in self.store.fresh(self.exam) if subject.covers(q)]

    def fresh_count(self) -> int:
        return len(self.fresh())

    # --- Asking -----------------------------------------------------------------------------

    def next_question(self, now: float) -> Question | None:
        """A review that is due, or a fresh question from a domain to work on, both on the
        subject: the reviews of other subjects wait for their turn."""
        subject = self.subject
        due = [q for q in self.store.due_reviews(self.exam, now) if subject.covers(q)]
        fresh = self.fresh()
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
            raise ValueError("question not in the database")
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
        return self.fresh_count() < LOW_WATER

    def batch_request(self, count: int = BATCH) -> dict[str, Any]:
        """What to ask the brain for: one slot per question, the topics to avoid, the subject.
        On a subject in one's own words, the brain picks each question's domain."""
        grade = self.progress.grade
        subject = self.subject
        picked: list[int | None]
        if subject.domain is not None:
            picked = [subject.domain] * count
        elif subject.text:
            picked = [None] * count
        else:
            weights = self.domain_weights()
            domains = sorted(weights)
            picked = list(
                self._rng.choices(domains, weights=[weights[d] for d in domains], k=count)
            )
        multiple = round(count * MULTIPLE_SHARE_BY_GRADE[grade])
        slots = [
            {
                "domain": domain,
                "difficulty": DIFFICULTY_BY_GRADE[grade],
                "kind": "multiple"
                if i < multiple and "multiple" in self.blueprint.kinds
                else "single",
            }
            for i, domain in enumerate(sorted(picked, key=lambda d: d or 0))
        ]
        return {
            "exam": self.exam,
            "course": self.blueprint.to_dict(),
            "slots": slots,
            "avoid": self.store.recent_topics(
                self.exam, AVOID_TOPICS, subject.text if subject.text else None
            ),
            "subject": subject.key,
        }

    def add_batch(
        self, raw: Sequence[Mapping[str, Any]], now: float, subject: str = "", course: str = ""
    ) -> tuple[list[int], list[str]]:
        """Keep the questions that hold up, shuffled; say why the others were dropped.
        subject, course: the keys of the subject and the course they were written for (the
        course learned now when not said: one may have chosen another meanwhile)."""
        try:
            bp = self.course(course) if course else self.blueprint
        except (KeyError, ValueError):
            return [], [f"unknown course: {course}"]
        kept, rejected = [], []
        for i, data in enumerate(raw, 1):
            try:
                question = parse_question(data, bp).shuffled(self._rng)
                kept.append(replace(question, subject=subject))
            except ValueError as error:
                rejected.append(f"question {i} : {error}")
        return self.store.add_questions(bp.key, kept, now), rejected

    def explain_request(self, question: Question, chosen: Sequence[int]) -> dict[str, Any]:
        return {
            "exam": self.exam,
            "course": self.blueprint.to_dict(),
            "question": question.to_dict(),
            "chosen": list(chosen),
        }

    def summary(self) -> dict[str, Any]:
        """What the stats show: grade, points, streaks, accuracy by domain, the bank."""
        p = self.progress
        subject = self.subject
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
            "subject": subject.name(self.blueprint),
            "course": self.blueprint.name,
            "topic": self.topic(),
            "fresh": self.fresh_count(),
            "reviews": self.store.reviews_pending(self.exam),
        }


def slot_summary(slots: Sequence[Mapping[str, Any]]) -> Counter[tuple[int, str, str]]:
    """0 for a slot whose domain the brain picks."""
    return Counter((int(s["domain"] or 0), str(s["difficulty"]), str(s["kind"])) for s in slots)
