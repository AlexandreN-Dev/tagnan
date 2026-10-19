"""Tagnan's updates: what is new on GitHub, and taking it. The window calls it through
scripts/update (through wsl.exe from Windows), as it calls the brain: no state, one JSON answer
on stdout. Standard library only, git for the rest.

    scripts/update check    what is new upstream: {"ok", "behind", "news"}
    scripts/update apply    take it, a fast-forward only: {"ok", "updated", "news", "setup"}
    scripts/update here [COMMIT]
                            what his folder holds that the window, started at COMMIT, does
                            not run yet (one's own commits): {"ok", "head", "moved", "news",
                            "setup"}; no network

A refusal is an answer too: {"ok": false, "reason", "message"}, the message in his own words.
"""

import json
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tagnan.paths import REPO

# The window's pinned dependencies: when they change, its environment is made again.
PINS = "tagnan/ui/requirements.txt"
MAX_NEWS = 4
FETCH_SECONDS = 60.0
# A commit worth telling about: a feature or a fix, "type(scope)!: what it does".
WORTH_TELLING = re.compile(r"^(feat|fix)(\([^)]*\))?!?:\s*(?P<what>.+)$")


class Refusal(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason, self.message = reason, message


def news(subjects: Sequence[str]) -> list[str]:
    """What the user would notice among commit subjects, newest first: features and fixes,
    without their prefix, a capital to start, at most a few."""
    told: list[str] = []
    for subject in subjects:
        found = WORTH_TELLING.match(subject.strip())
        if not found:
            continue
        what = found.group("what").strip().rstrip(".")
        what = what[:1].upper() + what[1:]
        if what and what not in told:
            told.append(what)
    return told[:MAX_NEWS]


def git(repo: Path, *args: str, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    """git in the repository, never asking anything: no prompt for a password, no dialog."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "LC_ALL": "C"}
    try:
        return subprocess.run(  # noqa: S603 - fixed argument list, no shell
            ["git", "-C", str(repo), *args],  # noqa: S607 - git from the PATH, as one would
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except FileNotFoundError:
        raise Refusal("no-git", "I need git to update myself, and it isn't installed.") from None
    except subprocess.TimeoutExpired:
        raise Refusal("offline", "GitHub doesn't answer: I'll try again later.") from None


def _output(done: subprocess.CompletedProcess[str]) -> str:
    return done.stdout.strip()


def _last_words(done: subprocess.CompletedProcess[str]) -> str:
    lines = [line.strip() for line in done.stderr.splitlines() if line.strip()]
    return lines[-1] if lines else f"git failed ({done.returncode})"


def _ready(repo: Path) -> None:
    """A clone of a repository that has an upstream: else no update but by hand."""
    if git(repo, "rev-parse", "--is-inside-work-tree").returncode != 0:
        raise Refusal(
            "not-a-clone", "This copy of me wasn't installed with git: update it by hand."
        )
    if git(repo, "rev-parse", "--abbrev-ref", "@{upstream}").returncode != 0:
        raise Refusal("no-upstream", "My copy doesn't follow GitHub: update it by hand.")


def _fetch(repo: Path) -> None:
    done = git(repo, "fetch", "--quiet", timeout=FETCH_SECONDS)
    if done.returncode != 0:
        raise Refusal("offline", f"I couldn't reach GitHub ({_last_words(done)}).")


def _subjects(repo: Path, span: str) -> list[str]:
    return _output(git(repo, "log", "--format=%s", span)).splitlines()


def check(repo: Path = REPO) -> dict[str, Any]:
    _ready(repo)
    _fetch(repo)
    behind = int(_output(git(repo, "rev-list", "--count", "HEAD..@{upstream}")) or 0)
    return {"ok": True, "behind": behind, "news": news(_subjects(repo, "HEAD..@{upstream}"))}


def here(repo: Path = REPO, running: str = "") -> dict[str, Any]:
    """His folder's commit, and what changed since `running`, the one his window started at:
    a restart shows it. Local only: one's own commits, or an update taken by hand."""
    if git(repo, "rev-parse", "--is-inside-work-tree").returncode != 0:
        raise Refusal("not-a-clone", "This copy of me wasn't installed with git.")
    head = _output(git(repo, "rev-parse", "HEAD"))
    moved = bool(running) and running != head
    known = moved and git(repo, "cat-file", "-e", f"{running}^{{commit}}").returncode == 0
    span = f"{running}..{head}"
    return {
        "ok": True,
        "head": head,
        "moved": moved,
        "news": news(_subjects(repo, span)) if known else [],
        "setup": known and bool(_output(git(repo, "diff", "--name-only", span, "--", PINS))),
    }


def apply(repo: Path = REPO) -> dict[str, Any]:
    """A fast-forward to GitHub's version, never over changes of one's own."""
    _ready(repo)
    if _output(git(repo, "status", "--porcelain", "--untracked-files=no")):
        raise Refusal(
            "local-changes",
            "My files have changes of their own: update me by hand (git pull in my folder).",
        )
    _fetch(repo)
    before = _output(git(repo, "rev-parse", "HEAD"))
    done = git(repo, "merge", "--ff-only", "--quiet", "@{upstream}")
    if done.returncode != 0:
        raise Refusal(
            "diverged",
            "My copy has commits of its own that GitHub doesn't: update me by hand.",
        )
    after = _output(git(repo, "rev-parse", "HEAD"))
    setup = after != before and bool(
        _output(git(repo, "diff", "--name-only", before, after, "--", PINS))
    )
    return {
        "ok": True,
        "updated": after != before,
        "news": news(_subjects(repo, f"{before}..{after}")),
        "setup": setup,
    }


def by_hand(repo: Path = REPO) -> int:
    """scripts/update with nothing more: take what is new, then say how to see it."""
    try:
        done = apply(repo)
    except Refusal as refusal:
        print(refusal.message, file=sys.stderr)
        return 1
    if not done["updated"]:
        print("Tagnan is up to date.")
        return 0
    print("Tagnan is updated." + "".join(f"\n  · {line}" for line in done["news"]))
    if done["setup"]:
        print("His window's environment changes too:")
        if subprocess.run([str(repo / "scripts" / "ui-setup")], check=False).returncode != 0:  # noqa: S603
            print("it failed: run scripts/setup.", file=sys.stderr)
            return 1
    print("If he is on your desktop, quit him from his menu and start him again.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    action = args[0] if args else ""
    repo = REPO
    if action == "":
        return by_hand(repo)
    if action not in ("check", "apply", "here"):
        print("Usage: scripts/update [check | apply | here [COMMIT]]", file=sys.stderr)
        return 2
    try:
        if action == "here":
            answer = here(repo, args[1] if len(args) > 1 else "")
        else:
            answer = check(repo) if action == "check" else apply(repo)
    except Refusal as refusal:
        answer = {"ok": False, "reason": refusal.reason, "message": refusal.message}
    print(json.dumps(answer, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
