"""Tagnan in the terminal (WSL or macOS): the same game as the window, one question after another.

    uv run python -m tagnan.cli            # one question (a batch is written first if needed)
    uv run python -m tagnan.cli -n 5       # five in a row
    uv run python -m tagnan.cli --stats
    uv run python -m tagnan.cli --learn pottery # learn something else (a course is drawn up)
    uv run python -m tagnan.cli --subject RAG   # questions on RAG from now on ("all": the exam)
    uv run python -m tagnan.cli --import batch.json   # questions written by scripts/brain

Its database is WSL's (~/.local/state/tagnan), not the window's (on Windows); on macOS both
share ~/Library/Application Support/tagnan.
"""

import argparse
import json
import random
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from tagnan import blueprint as blueprints
from tagnan import config as configs
from tagnan import progress as rules
from tagnan.brain_client import BrainClient, BrainError
from tagnan.game import Game, Outcome
from tagnan.model import Question
from tagnan.paths import config_file, state_dir
from tagnan.store import Store
from tagnan.subject import parse as parse_subject

LETTERS = "ABCDEF"
CHEERS = ("Touché!", "Well parried!", "An unstoppable thrust!", "By my rapier, that's right!")
SCOLDS = ("Zounds!", "Sacrebleu!", "Blast it, no!", "By my sword, no!")


def show(question: Question) -> None:
    print(f"\n— Domain {question.domain} · {question.difficulty} —")
    print(question.stem)
    for letter, choice in zip(LETTERS, question.choices, strict=False):
        print(f"  {letter}. {choice}")


def read_choice(question: Question) -> list[int] | None:
    wanted = len(question.answers)
    prompt = "Your answer (letter): " if wanted == 1 else f"Your {wanted} answers (e.g. AC): "
    while True:
        try:
            text = input(prompt).strip().upper().replace(" ", "").replace(",", "")
        except EOFError:
            return None
        picked = [LETTERS.index(c) for c in text if c in LETTERS[: len(question.choices)]]
        if len(set(picked)) == wanted and len(picked) == len(text):
            return picked
        last = LETTERS[len(question.choices) - 1]
        print(f"  {wanted} letter{'s' if wanted > 1 else ''} from A to {last}, please.")


def tell(outcome: Outcome, rng: random.Random) -> None:
    q = outcome.question
    right = ", ".join(f"{LETTERS[i]} ({q.choices[i]})" for i in q.answers)
    if outcome.correct:
        print(f"\n{rng.choice(CHEERS)} {q.explanation}")
    else:
        print(f"\n{rng.choice(SCOLDS)}")
        for i in outcome.chosen:
            if q.why_wrong[i]:
                print(f"  {LETTERS[i]}: {q.why_wrong[i]}")
        print(f"  The right answer: {right}. {q.explanation}")
    if q.reference:
        print(f"  Read again: {q.reference}")
    after = outcome.after
    sign = "+" if outcome.delta >= 0 else ""
    print(f"  {sign}{outcome.delta} points · {after.points} in all · streak {after.streak}")
    if outcome.promoted:
        grade = rules.GRADES[after.grade]
        print(f"  Promotion! Tagnan is now a {grade.name}: {grade.look}.")
    elif outcome.demoted:
        print(f"  Tagnan falls back to {rules.GRADES[after.grade].name}.")


def refill(game: Game, brain: BrainClient) -> None:
    print("Tagnan is writing new questions (a few minutes)…", flush=True)
    answer = brain.generate(game.batch_request())
    ids, rejected = game.add_batch(
        answer.get("questions", []), time.time(), str(answer.get("subject") or "")
    )
    print(f"{len(ids)} questions ready" + (f", {len(rejected)} set aside." if rejected else "."))


def learn(game: Game, words: str, brain: BrainClient) -> None:
    """A course learned before at once; anything else once the brain has drawn up its course."""
    bp = game.find_course(words)
    if bp is None:
        print(f"Tagnan is drawing up a course on {words.strip()} (a minute or two)…", flush=True)
        answer = brain.plan(words)
        if not answer.get("understood"):
            raise BrainError(str(answer.get("message") or "he doesn't know how to teach that"))
        try:
            bp = blueprints.from_dict(answer.get("course") or {}, where="course")
        except ValueError as error:
            raise BrainError(str(error)) from None
        for d in bp.domains:
            print(f"  {d.id}. {d.name}")
    game.set_course(bp)
    print(f"From now on, Tagnan teaches {bp.name}: he is {rules.GRADES[game.progress.grade].name}.")


def stats(game: Game) -> None:
    s = game.summary()
    nxt = f", {s['next_threshold']} for {s['next_name']}" if s["next_name"] else ""
    print(f"{s['course']}: Tagnan is {s['grade_name']}, {s['points']} points{nxt}.")
    print(f"Streak: {s['streak']} (best {s['best_streak']}).", end=" ")
    print(f"Answers: {s['right']}/{s['answered']}.")
    for d in s["domains"]:
        rate = f"{100 * d['right'] // d['answered']}%" if d["answered"] else "—"
        print(f"  {d['id']}. {d['name']}: {d['right']}/{d['answered']} ({rate})")
    print(f"Subject: {s['topic']}, {s['fresh']} new questions on it.", end=" ")
    print(f"To review in all: {s['reviews']}.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tagnan", description="Tagnan in the terminal")
    parser.add_argument("-n", "--count", type=int, default=1, help="questions in a row")
    parser.add_argument("--stats", action="store_true", help="the progress, no question")
    parser.add_argument("--learn", help="learn something else from now on: an exam, pottery…")
    parser.add_argument("--subject", help='what to work on from now on ("all": the whole exam)')
    parser.add_argument(
        "--import", dest="import_file", type=Path, help="add a batch from the brain"
    )
    parser.add_argument("--db", type=Path, default=state_dir() / "tagnan.db")
    parser.add_argument("--config", type=Path, default=config_file())
    args = parser.parse_args(argv)
    cfg = configs.load(args.config)
    rng = random.Random()  # noqa: S311 - which question, which interjection: not secrets
    game = Game(Store(args.db), blueprints.load(cfg.exam), rng)
    if args.import_file:
        batch = json.loads(args.import_file.read_text(encoding="utf-8"))
        ids, rejected = game.add_batch(batch.get("questions", []), time.time())
        print(
            f"{len(ids)} questions added" + (f", {len(rejected)} set aside." if rejected else ".")
        )
        return 0
    if args.learn is not None:
        try:
            learn(game, args.learn, BrainClient.local())
        except BrainError as error:
            print(f"No course: {error}", file=sys.stderr)
            return 1
        if args.count == 1 and not args.stats and args.subject is None:
            return 0
    if args.subject is not None:
        try:
            game.set_subject(parse_subject(args.subject, game.blueprint))
        except ValueError as error:
            print(error, file=sys.stderr)
            return 1
        print(f"From now on, Tagnan asks about {game.subject.name(game.blueprint)}.")
        if args.count == 1 and not args.stats:
            return 0
    if args.stats:
        stats(game)
        return 0
    brain = BrainClient.local()
    for _ in range(args.count):
        question = game.next_question(time.time())
        if question is None or game.needs_questions():
            try:
                refill(game, brain)
            except BrainError as error:
                print(f"The brain could not write questions: {error}", file=sys.stderr)
                if question is None:
                    return 1
            question = question or game.next_question(time.time())
        if question is None:
            print("No question available.", file=sys.stderr)
            return 1
        show(question)
        chosen = read_choice(question)
        if chosen is None:
            return 0
        outcome = game.answer(question, chosen, time.time())
        tell(outcome, rng)
        if not outcome.correct and sys.stdin.isatty():
            more = input("  Enter to go on, 'e' for a longer explanation: ")
            if more.strip().lower() == "e":
                try:
                    print("\n" + brain.explain(game.explain_request(question, outcome.chosen)))
                except BrainError as error:
                    print(f"No explanation: {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
