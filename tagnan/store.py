"""The game's SQLite database: the questions, every answer, the reviews to come, the progress."""

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from tagnan.model import Question
from tagnan.progress import Progress

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY,
    exam TEXT NOT NULL,
    domain INTEGER NOT NULL,
    task TEXT NOT NULL,
    topic TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    kind TEXT NOT NULL,
    stem TEXT NOT NULL,
    choices TEXT NOT NULL,
    answers TEXT NOT NULL,
    explanation TEXT NOT NULL,
    why_wrong TEXT NOT NULL,
    reference TEXT NOT NULL,
    created_at REAL NOT NULL,
    flagged INTEGER NOT NULL DEFAULT 0,
    lang TEXT NOT NULL DEFAULT 'fr',
    subject TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    chosen TEXT NOT NULL,
    correct INTEGER NOT NULL,
    points INTEGER NOT NULL,
    answered_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    question_id INTEGER PRIMARY KEY REFERENCES questions(id),
    box INTEGER NOT NULL,
    due_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS answers_by_question ON answers(question_id);
"""


class Store:
    """lang: the language Tagnan speaks; questions written in another one are set aside (kept,
    never asked), so that switching languages loses nothing."""

    def __init__(self, path: Path | str, lang: str = "en") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lang = lang
        self._db = sqlite3.connect(str(path))
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(questions)")}
        if "lang" not in columns:  # a database from before Tagnan spoke English
            with self._db:
                self._db.execute("ALTER TABLE questions ADD COLUMN lang TEXT NOT NULL DEFAULT 'fr'")
        if "subject" not in columns:  # a database from before one chose the subject
            with self._db:
                self._db.execute(
                    "ALTER TABLE questions ADD COLUMN subject TEXT NOT NULL DEFAULT ''"
                )

    def close(self) -> None:
        self._db.close()

    # --- Questions --------------------------------------------------------------------------

    def add_questions(self, exam: str, questions: Iterable[Question], now: float) -> list[int]:
        ids = []
        with self._db:
            for q in questions:
                cursor = self._db.execute(
                    "INSERT INTO questions (exam, domain, task, topic, difficulty, kind, stem,"
                    " choices, answers, explanation, why_wrong, reference, created_at, lang,"
                    " subject)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        exam,
                        q.domain,
                        q.task,
                        q.topic,
                        q.difficulty,
                        q.kind,
                        q.stem,
                        json.dumps(q.choices, ensure_ascii=False),
                        json.dumps(q.answers),
                        q.explanation,
                        json.dumps(q.why_wrong, ensure_ascii=False),
                        q.reference,
                        now,
                        self.lang,
                        q.subject,
                    ),
                )
                ids.append(int(cursor.lastrowid or 0))
        return ids

    def question(self, question_id: int) -> Question:
        row = self._db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        if row is None:
            raise KeyError(question_id)
        return _question(row)

    def fresh(self, exam: str) -> list[Question]:
        """Questions never asked, and not flagged as wrong."""
        rows = self._db.execute(
            "SELECT * FROM questions q WHERE exam = ? AND lang = ? AND flagged = 0"
            " AND NOT EXISTS (SELECT 1 FROM answers a WHERE a.question_id = q.id) ORDER BY id",
            (exam, self.lang),
        )
        return [_question(r) for r in rows]

    def fresh_count(self, exam: str) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) FROM questions q WHERE exam = ? AND lang = ? AND flagged = 0"
            " AND NOT EXISTS (SELECT 1 FROM answers a WHERE a.question_id = q.id)",
            (exam, self.lang),
        ).fetchone()
        return int(row[0])

    def flag(self, question_id: int) -> None:
        """A wrong or badly worded question: never asked again, out of the reviews."""
        with self._db:
            self._db.execute("UPDATE questions SET flagged = 1 WHERE id = ?", (question_id,))
            self._db.execute("DELETE FROM reviews WHERE question_id = ?", (question_id,))

    def recent_topics(self, exam: str, limit: int, subject: str | None = None) -> list[str]:
        """The notions last asked; with `subject`, among the questions written for it only."""
        if subject is None:
            rows = self._db.execute(
                "SELECT topic FROM questions WHERE exam = ? AND lang = ? ORDER BY id DESC LIMIT ?",
                (exam, self.lang, limit),
            )
        else:
            rows = self._db.execute(
                "SELECT topic FROM questions WHERE exam = ? AND lang = ? AND subject = ?"
                " COLLATE NOCASE ORDER BY id DESC LIMIT ?",
                (exam, self.lang, subject, limit),
            )
        return [str(r[0]) for r in rows]

    def subjects(self, exam: str, limit: int = 4) -> list[str]:
        """The subjects in one's own words, last chosen first."""
        rows = self._db.execute(
            "SELECT subject FROM questions WHERE exam = ? AND lang = ? AND subject != ''"
            " AND subject NOT LIKE 'domain:%' GROUP BY subject COLLATE NOCASE"
            " ORDER BY MAX(id) DESC LIMIT ?",
            (exam, self.lang, limit),
        )
        return [str(r[0]) for r in rows]

    # --- Reviews ----------------------------------------------------------------------------

    def due_reviews(self, exam: str, now: float) -> list[Question]:
        rows = self._db.execute(
            "SELECT q.* FROM questions q JOIN reviews r ON r.question_id = q.id"
            " WHERE q.exam = ? AND q.lang = ? AND q.flagged = 0 AND r.due_at <= ?"
            " ORDER BY r.due_at",
            (exam, self.lang, now),
        )
        return [_question(r) for r in rows]

    def review_box(self, question_id: int) -> int | None:
        row = self._db.execute(
            "SELECT box FROM reviews WHERE question_id = ?", (question_id,)
        ).fetchone()
        return None if row is None else int(row[0])

    def set_review(self, question_id: int, box: int | None, due_at: float = 0.0) -> None:
        with self._db:
            if box is None:
                self._db.execute("DELETE FROM reviews WHERE question_id = ?", (question_id,))
            else:
                self._db.execute(
                    "INSERT INTO reviews (question_id, box, due_at) VALUES (?, ?, ?)"
                    " ON CONFLICT(question_id) DO UPDATE SET box = excluded.box,"
                    " due_at = excluded.due_at",
                    (question_id, box, due_at),
                )

    # --- Answers, progress, choices ---------------------------------------------------------

    def record_answer(
        self, question_id: int, chosen: Iterable[int], correct: bool, points: int, now: float
    ) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO answers (question_id, chosen, correct, points, answered_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (question_id, json.dumps(sorted(set(chosen))), int(correct), points, now),
            )

    def progress(self, exam: str) -> Progress:
        row = self._db.execute(
            "SELECT value FROM state WHERE key = ?", (f"progress:{exam}",)
        ).fetchone()
        return Progress(**json.loads(row[0])) if row else Progress()

    def save_progress(self, exam: str, progress: Progress) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO state (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (f"progress:{exam}", json.dumps(asdict(progress))),
            )

    def setting(self, key: str) -> str:
        row = self._db.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else ""

    def set_setting(self, key: str, value: str) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO state (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def course_keys(self) -> list[str]:
        """The courses the brain drew up, kept in the state table."""
        rows = self._db.execute("SELECT key FROM state WHERE key LIKE 'course:%' ORDER BY key")
        return [str(r[0])[7:] for r in rows]

    def domain_stats(self, exam: str) -> dict[int, tuple[int, int]]:
        """For each domain: answers given, right answers."""
        rows = self._db.execute(
            "SELECT q.domain, COUNT(*), SUM(a.correct) FROM answers a"
            " JOIN questions q ON q.id = a.question_id WHERE q.exam = ? GROUP BY q.domain",
            (exam,),
        )
        return {int(r[0]): (int(r[1]), int(r[2] or 0)) for r in rows}

    def reviews_pending(self, exam: str) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) FROM reviews r JOIN questions q ON q.id = r.question_id"
            " WHERE q.exam = ? AND q.lang = ? AND q.flagged = 0",
            (exam, self.lang),
        ).fetchone()
        return int(row[0])


def _question(row: sqlite3.Row) -> Question:
    return Question(
        id=int(row["id"]),
        domain=int(row["domain"]),
        task=str(row["task"]),
        topic=str(row["topic"]),
        difficulty=str(row["difficulty"]),
        kind=str(row["kind"]),
        stem=str(row["stem"]),
        choices=tuple(json.loads(row["choices"])),
        answers=tuple(json.loads(row["answers"])),
        explanation=str(row["explanation"]),
        why_wrong=tuple(json.loads(row["why_wrong"])),
        reference=str(row["reference"]),
        subject=str(row["subject"]),
    )
