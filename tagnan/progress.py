"""Points, streaks and grades; and the Leitner boxes that bring back the questions you missed."""

from dataclasses import dataclass, replace

DAY = 86_400.0


@dataclass(frozen=True)
class Grade:
    name: str
    threshold: int  # points from which the grade is reached
    look: str  # what Tagnan gains, as the window and the stats say it


# A long road, on purpose: about 100 answers a week (twenty a working day) at 80 % right make
# Tagnan Gascon in two days, Cadet in a week, Mousquetaire in two and a half, Lieutenant in four
# and Capitaine in seven; at 70 % right, ten weeks; at 60 %, four months. Simulated in
# tests/test_rules.py.
GRADES = (
    Grade("Encrier", 0, "de l'encre dans son encrier"),
    Grade("Gascon", 250, "il s'échappe de l'encrier"),
    Grade("Cadet", 900, "un feutre"),
    Grade("Mousquetaire", 2000, "la casaque à croix et la plume blanche"),
    Grade("Lieutenant", 3600, "la rapière et la moustache en croc"),
    Grade("Capitaine", 6000, "le chapeau à cocarde, la royale et l'or"),
)

RIGHT, STREAK_BONUS, MAX_BONUS, WRONG = 10, 1, 5, -8
# A grade is lost only well below its threshold: 15 % of the band under it, and never for a
# single miss right after the promotion (two misses at least).
DEMOTION_MARGIN = 0.15
DEMOTION_MISSES = 2


@dataclass(frozen=True)
class Progress:
    points: int = 0
    streak: int = 0
    best_streak: int = 0
    grade: int = 0

    @property
    def next_threshold(self) -> int | None:
        return GRADES[self.grade + 1].threshold if self.grade + 1 < len(GRADES) else None


def grade_for(points: int, current: int) -> int:
    """Up as soon as a threshold is reached; down one grade at a time, past the margin."""
    reached = max(i for i, g in enumerate(GRADES) if points >= g.threshold)
    if reached >= current:
        return reached
    band = GRADES[current].threshold - GRADES[current - 1].threshold
    margin = max(DEMOTION_MARGIN * band, DEMOTION_MISSES * -WRONG)
    if points < GRADES[current].threshold - margin:
        return current - 1
    return current


def settle(progress: Progress) -> Progress:
    """The grade the points support, should the thresholds have changed since it was won (a
    grade within its margin is kept, as after a miss)."""
    grade = progress.grade
    while (lower := grade_for(progress.points, grade)) < grade:
        grade = lower
    return progress if grade == progress.grade else replace(progress, grade=grade)


def after_answer(progress: Progress, correct: bool) -> tuple[Progress, int]:
    """The new progress and the points won (or lost)."""
    if correct:
        streak = progress.streak + 1
        delta = RIGHT + min(STREAK_BONUS * (streak - 1), MAX_BONUS)
    else:
        streak = 0
        delta = WRONG
    points = max(0, progress.points + delta)
    updated = replace(
        progress,
        points=points,
        streak=streak,
        best_streak=max(progress.best_streak, streak),
        grade=grade_for(points, progress.grade),
    )
    return updated, points - progress.points


# Leitner: a missed question comes back the next day; each right answer sends it further away,
# and after the last box it is learnt. A miss sends it back to the first box.
REVIEW_DAYS = {1: 1, 2: 3, 3: 7, 4: 21}


def after_review(box: int | None, correct: bool) -> int | None:
    """The question's next box (None: not or no longer to review)."""
    if not correct:
        return 1
    if box is None:
        return None
    return box + 1 if box + 1 in REVIEW_DAYS else None


def due_at(box: int, now: float) -> float:
    return now + REVIEW_DAYS[box] * DAY
