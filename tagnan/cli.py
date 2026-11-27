"""Tagnan in the terminal (WSL or macOS): the same game as the window, one question after another.

    uv run python -m tagnan.cli            # one question (a batch is written first if needed)
    uv run python -m tagnan.cli -n 5       # five in a row
    uv run python -m tagnan.cli --stats
    uv run python -m tagnan.cli --learn pottery # learn something else (a course is drawn up)
    uv run python -m tagnan.cli --learn spanish --level A2 --speaks French   # a language
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
from tagnan import language, words
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


def learn(game: Game, said: str, brain: BrainClient, level: str = "", speaks: str = "") -> None:
    """A course learned before at once; anything else once the brain has drawn up its course.
    A language is drawn up at one's level, its meanings in the language one speaks."""
    spoken = language.find(said)
    bp = game.find_course(said) or (game.find_course(spoken.name) if spoken else None)
    if bp is None:
        asked = None
        if spoken is not None:
            level = (level or spoken.level).upper()
            if level not in language.LEVEL_KEYS:
                raise BrainError(
                    f"{spoken.name} is a language: say your level, --level A1 to --level C1"
                )
            asked = {
                "learned": spoken.name,
                "level": level,
                "speaks": language.named(speaks or "English"),
                "purpose": spoken.purpose,
            }
        print(f"Tagnan is drawing up a course on {said.strip()} (a minute or two)…", flush=True)
        answer = brain.plan(spoken.name if spoken else said, asked)
        if not answer.get("understood"):
            raise BrainError(str(answer.get("message") or "he doesn't know how to teach that"))
        found = str(answer.get("language") or "")
        if found and not answer.get("course"):  # a language he did not know by name
            if level.upper() not in language.LEVEL_KEYS:
                raise BrainError(f"{found} is a language: say your level, --level A1 to --level C1")
            asked = {
                "learned": found,
                "level": level.upper(),
                "speaks": language.named(speaks or "English"),
                "purpose": "",
            }
            answer = brain.plan(found, asked)
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


def refill_words(game: Game, brain: BrainClient) -> None:
    print("Tagnan is writing new words (a few minutes)…", flush=True)
    answer = brain.words(game.words_request())
    added = game.add_cards(game.blueprint, answer.get("words", []), time.time())
    print(
        f"{len(added.ids)} words ready"
        + (f", {len(added.rejected)} set aside." if added.rejected else ".")
    )


def bout(game: Game, rng: random.Random) -> bool:
    """A call in a language course: a few of its words in a row. False when one stops (end of
    input), or when there is nothing to ask."""
    slots = game.next_bout(time.time())
    if not slots:
        return False
    spoken = game.blueprint.language
    learned = spoken.learned if spoken else game.blueprint.name
    for slot in slots:
        touch = game.touch(slot)
        card = touch.card
        try:
            if touch.kind == words.MEET:
                print(f"\n— A new word —\n{card.term}: {card.meaning}")
                if card.example:
                    print(
                        f"  {card.sentence}"
                        + (f" ({card.translation})" if card.translation else "")
                    )
                if card.note:
                    print(f"  {card.note}")
                known = input("  Enter to go on, 'k' if you know it already: ").strip().lower()
                game.meet(card, time.time(), known == "k")
                continue
            gap = card.gap
            if touch.kind in (words.GAP, words.TYPE_GAP) and gap:
                print(
                    f"\n{gap[0]}____{gap[2]}"
                    + (f" ({card.translation})" if card.translation else "")
                )
            elif touch.kind == words.MEANING:
                print(f"\n{card.term}: what does it mean?")
            else:
                print(f"\n{card.meaning}: in {learned}?")
            if touch.kind in words.TYPED:
                done = game.answer_touch(touch, time.time(), typed=input("Type it: "))
            else:
                for letter, choice in zip(LETTERS, touch.choices, strict=False):
                    print(f"  {letter}. {choice}")
                picked = None
                while picked is None:
                    text = input("Your answer (letter): ").strip().upper()
                    if len(text) == 1 and text in LETTERS[: len(touch.choices)]:
                        picked = LETTERS.index(text)
                done = game.answer_touch(touch, time.time(), picked=picked)
        except EOFError:
            return False
        after = done.after
        if done.correct:
            remark = {
                language.ACCENT: f" Mind the accent: {touch.expected}.",
                language.ARTICLE: f" With its article: {card.term}.",
                language.ALSO: f" I had {card.term} in mind: both are right.",
            }.get(done.remark, "")
            print(f"{rng.choice(CHEERS)}{remark}")
        else:
            print(f"{rng.choice(SCOLDS)} {card.term}: {card.meaning}.")
            if card.example:
                print(f"  {card.sentence}")
        sign = "+" if done.delta >= 0 else ""
        print(f"  {sign}{done.delta} points · {after.points} in all · step {done.step}")
        if done.promoted:
            grade = rules.GRADES[after.grade]
            print(f"  Promotion! Tagnan is now a {grade.name}: {grade.look}.")
    return True


def stats(game: Game) -> None:
    s = game.summary()
    nxt = f", {s['next_threshold']} for {s['next_name']}" if s["next_name"] else ""
    print(f"{s['course']}: Tagnan is {s['grade_name']}, {s['points']} points{nxt}.")
    if game.is_language:
        counts = game.word_counts(time.time())
        print(
            f"Words: {counts['known']} known, {counts['climbing']} on the ladder,"
            f" {counts['fresh']} new in store; {counts['due']} due today."
        )
        for c in counts["chapters"]:
            print(f"  {c['id']}. {c['name']}: {c['known']}/{c['of']} known")
        return
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
    parser.add_argument("--level", default="", help="a language's level, from A1 to C1")
    parser.add_argument("--speaks", default="", help="the language one speaks (English)")
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
        if batch.get("words"):  # a language course's words, as scripts/brain words writes them
            added = game.add_cards(game.blueprint, batch["words"], time.time())
            aside = f", {len(added.rejected)} set aside." if added.rejected else "."
            print(f"{len(added.ids)} words added{aside}")
            return 0
        ids, rejected = game.add_batch(batch.get("questions", []), time.time())
        print(
            f"{len(ids)} questions added" + (f", {len(rejected)} set aside." if rejected else ".")
        )
        return 0
    if args.learn is not None:
        try:
            learn(game, args.learn, BrainClient.local(), args.level, args.speaks)
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
    nobody = cfg.brain.model == configs.NOBODY  # his catalogues only: no brain to call
    for _ in range(args.count):
        if game.is_language:  # its words, a bout at a time
            spoken = game.blueprint.language
            if not nobody and spoken is not None and spoken.level and game.needs_words():
                try:
                    refill_words(game, brain)
                except BrainError as error:
                    print(f"The brain could not write words: {error}", file=sys.stderr)
            if not bout(game, rng):
                if not game.next_bout(time.time()):
                    print("No word to ask right now.", file=sys.stderr)
                    return 1
                return 0
            continue
        question = game.next_question(time.time())
        if not nobody and (question is None or game.needs_questions()):
            try:
                refill(game, brain)
            except BrainError as error:
                print(f"The brain could not write questions: {error}", file=sys.stderr)
                if question is None:
                    return 1
            question = question or game.next_question(time.time())
        if question is None:
            more = " Bring him a catalogue: his menu, Catalogues." if nobody else ""
            print(f"No question available.{more}", file=sys.stderr)
            return 1
        show(question)
        chosen = read_choice(question)
        if chosen is None:
            return 0
        outcome = game.answer(question, chosen, time.time())
        tell(outcome, rng)
        if not outcome.correct and not nobody and sys.stdin.isatty():
            more = input("  Enter to go on, 'e' for a longer explanation: ")
            if more.strip().lower() == "e":
                try:
                    print("\n" + brain.explain(game.explain_request(question, outcome.chosen)))
                except BrainError as error:
                    print(f"No explanation: {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
