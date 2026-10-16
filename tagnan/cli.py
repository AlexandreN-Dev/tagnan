"""Tagnan in the terminal (WSL): the same game as the window, one question after another.

    uv run python -m tagnan.cli            # one question (a batch is written first if needed)
    uv run python -m tagnan.cli -n 5       # five in a row
    uv run python -m tagnan.cli --stats
    uv run python -m tagnan.cli --import batch.json   # questions written by scripts/brain

Its database is WSL's (~/.local/state/tagnan), not the window's (on Windows).
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

LETTERS = "ABCDEF"
CHEERS = ("Touché !", "Bien paré !", "Une botte imparable !", "Par ma rapière, c'est juste !")
SCOLDS = ("Mordieu !", "Ventre-saint-gris !", "Palsambleu !", "Sang-Dieu, non !")


def show(question: Question) -> None:
    print(f"\n— Domaine {question.domain} · {question.difficulty} —")
    print(question.stem)
    for letter, choice in zip(LETTERS, question.choices, strict=False):
        print(f"  {letter}. {choice}")


def read_choice(question: Question) -> list[int] | None:
    wanted = len(question.answers)
    prompt = "Ta réponse (lettre) : " if wanted == 1 else f"Tes {wanted} réponses (ex. AC) : "
    while True:
        try:
            text = input(prompt).strip().upper().replace(" ", "").replace(",", "")
        except EOFError:
            return None
        picked = [LETTERS.index(c) for c in text if c in LETTERS[: len(question.choices)]]
        if len(set(picked)) == wanted and len(picked) == len(text):
            return picked
        last = LETTERS[len(question.choices) - 1]
        print(f"  Il faut {wanted} lettre{'s' if wanted > 1 else ''} parmi A à {last}.")


def tell(outcome: Outcome, rng: random.Random) -> None:
    q = outcome.question
    right = ", ".join(f"{LETTERS[i]} ({q.choices[i]})" for i in q.answers)
    if outcome.correct:
        print(f"\n{rng.choice(CHEERS)} {q.explanation}")
    else:
        print(f"\n{rng.choice(SCOLDS)}")
        for i in outcome.chosen:
            if q.why_wrong[i]:
                print(f"  {LETTERS[i]} : {q.why_wrong[i]}")
        print(f"  La bonne réponse : {right}. {q.explanation}")
    if q.reference:
        print(f"  À relire : {q.reference}")
    after = outcome.after
    sign = "+" if outcome.delta >= 0 else ""
    print(f"  {sign}{outcome.delta} points · {after.points} points · série {after.streak}")
    if outcome.promoted:
        grade = rules.GRADES[after.grade]
        print(f"  Promotion ! Tagnan passe {grade.name} : {grade.look}.")
    elif outcome.demoted:
        print(f"  Tagnan redescend {rules.GRADES[after.grade].name}.")


def refill(game: Game, brain: BrainClient) -> None:
    print("Tagnan prépare de nouvelles questions (une minute environ)…", flush=True)
    answer = brain.generate(game.batch_request())
    ids, rejected = game.add_batch(answer.get("questions", []), time.time())
    print(f"{len(ids)} questions prêtes" + (f", {len(rejected)} écartées." if rejected else "."))


def stats(game: Game) -> None:
    s = game.summary()
    nxt = f", {s['next_threshold']} pour {s['next_name']}" if s["next_name"] else ""
    print(f"Tagnan est {s['grade_name']} : {s['points']} points{nxt}.")
    print(f"Série : {s['streak']} (record {s['best_streak']}).", end=" ")
    print(f"Réponses : {s['right']}/{s['answered']}.")
    for d in s["domains"]:
        rate = f"{100 * d['right'] // d['answered']} %" if d["answered"] else "—"
        print(f"  {d['id']}. {d['name']} : {d['right']}/{d['answered']} ({rate})")
    print(f"En réserve : {s['fresh']} questions neuves, {s['reviews']} à revoir.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tagnan", description="Tagnan dans le terminal")
    parser.add_argument("-n", "--count", type=int, default=1, help="questions d'affilée")
    parser.add_argument("--stats", action="store_true", help="la progression, sans question")
    parser.add_argument("--import", dest="import_file", type=Path, help="ajouter un lot du cerveau")
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
            f"{len(ids)} questions ajoutées" + (f", {len(rejected)} écartées." if rejected else ".")
        )
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
                print(f"Le cerveau n'a pas pu écrire de questions : {error}", file=sys.stderr)
                if question is None:
                    return 1
            question = question or game.next_question(time.time())
        if question is None:
            print("Aucune question disponible.", file=sys.stderr)
            return 1
        show(question)
        chosen = read_choice(question)
        if chosen is None:
            return 0
        outcome = game.answer(question, chosen, time.time())
        tell(outcome, rng)
        if not outcome.correct and sys.stdin.isatty():
            more = input("  Entrée pour continuer, « e » pour une explication plus longue : ")
            if more.strip().lower() == "e":
                try:
                    print(
                        "\n"
                        + brain.explain(
                            {
                                "exam": game.exam,
                                "question": question.to_dict(),
                                "chosen": list(outcome.chosen),
                            }
                        )
                    )
                except BrainError as error:
                    print(f"Pas d'explication : {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
