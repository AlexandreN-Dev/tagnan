import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tagnan import update
from tagnan.update import Refusal

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

IDENTITY = {
    "GIT_AUTHOR_NAME": "Tagnan",
    "GIT_AUTHOR_EMAIL": "tagnan@example.com",
    "GIT_COMMITTER_NAME": "Tagnan",
    "GIT_COMMITTER_EMAIL": "tagnan@example.com",
}


def git(where: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(where), *args],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **IDENTITY},
    )
    return done.stdout.strip()


def commit(repo: Path, path: str, text: str, subject: str) -> None:
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text, encoding="utf-8")
    git(repo, "add", path)
    git(repo, "commit", "--quiet", "-m", subject)


@pytest.fixture
def clones(tmp_path: Path) -> tuple[Path, Path]:
    """GitHub, as a bare repository; the author's clone; the user's, a version behind."""
    origin, author, user = tmp_path / "origin.git", tmp_path / "author", tmp_path / "user"
    git(tmp_path, "init", "--quiet", "--bare", "-b", "main", str(origin))
    git(tmp_path, "init", "--quiet", "-b", "main", str(author))
    commit(author, "README.md", "Tagnan\n", "feat: an ink musketeer")
    commit(author, update.PINS, "pyside6==6.12.0\n", "feat(launch): his window")
    git(author, "remote", "add", "origin", str(origin))
    git(author, "push", "--quiet", "-u", "origin", "main")
    git(tmp_path, "clone", "--quiet", str(origin), str(user))
    return author, user


def publish(author: Path, path: str, text: str, subject: str) -> None:
    commit(author, path, text, subject)
    git(author, "push", "--quiet")


def test_the_news_are_features_and_fixes_in_plain_words() -> None:
    subjects = [
        "feat(art): a finished Gascon for grade 1, his inkwell back in the frame",
        "docs: Tagnan on a Mac",
        "fix(ui): his menu keeps clear of the screen's edges.",
        "refactor: every message in English",
        "feat!: a breaking change",
        "feat(ui): a finished Gascon for grade 1, his inkwell back in the frame",
    ]
    assert update.news(subjects) == [
        "A finished Gascon for grade 1, his inkwell back in the frame",
        "His menu keeps clear of the screen's edges",
        "A breaking change",
    ]
    assert len(update.news([f"fix: thing {i}" for i in range(9)])) == update.MAX_NEWS


def test_a_check_says_what_is_new_and_changes_nothing(clones: tuple[Path, Path]) -> None:
    author, user = clones
    assert update.check(user) == {"ok": True, "behind": 0, "news": []}
    publish(author, "art.txt", "Gascon\n", "feat(art): a finished Gascon")
    publish(author, "README.md", "Tagnan, updated\n", "docs: how to update")
    before = git(user, "rev-parse", "HEAD")
    answer = update.check(user)
    assert answer == {"ok": True, "behind": 2, "news": ["A finished Gascon"]}
    assert git(user, "rev-parse", "HEAD") == before


def test_an_update_fast_forwards_and_says_when_the_window_changes(
    clones: tuple[Path, Path],
) -> None:
    author, user = clones
    publish(author, "art.txt", "Gascon\n", "feat(art): a finished Gascon")
    answer = update.apply(user)
    assert answer == {"ok": True, "updated": True, "news": ["A finished Gascon"], "setup": False}
    assert (user / "art.txt").read_text(encoding="utf-8") == "Gascon\n"
    assert update.apply(user) == {"ok": True, "updated": False, "news": [], "setup": False}
    publish(author, update.PINS, "pyside6==6.13.0\n", "fix(launch): a newer window")
    assert update.apply(user)["setup"] is True  # his window's environment is made again


def test_an_update_never_goes_over_changes_of_ones_own(clones: tuple[Path, Path]) -> None:
    author, user = clones
    publish(author, "art.txt", "Gascon\n", "feat(art): a finished Gascon")
    (user / "README.md").write_text("my notes\n", encoding="utf-8")
    with pytest.raises(Refusal) as refused:
        update.apply(user)
    assert refused.value.reason == "local-changes"
    assert (user / "README.md").read_text(encoding="utf-8") == "my notes\n"
    git(user, "checkout", "--", "README.md")
    commit(user, "mine.txt", "mine\n", "feat: a change of my own")
    with pytest.raises(Refusal) as refused:
        update.apply(user)
    assert refused.value.reason == "diverged"


def test_no_update_without_a_clone_or_github(tmp_path: Path, clones: tuple[Path, Path]) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(Refusal) as refused:
        update.check(plain)
    assert refused.value.reason == "not-a-clone"
    _, user = clones
    git(user, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    with pytest.raises(Refusal) as refused:
        update.check(user)
    assert refused.value.reason == "offline"
    assert refused.value.message.startswith("I couldn't reach GitHub")


def test_the_window_gets_one_line_of_json(
    clones: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    author, user = clones
    publish(author, "art.txt", "Gascon\n", "feat(art): a finished Gascon")
    monkeypatch.setattr(update, "REPO", user)
    assert update.main(["check"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "behind": 1,
        "news": ["A finished Gascon"],
    }
    (user / "README.md").write_text("my notes\n", encoding="utf-8")
    assert update.main(["apply"]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert (answer["ok"], answer["reason"]) == (False, "local-changes")
    assert update.main(["sideways"]) == 2
