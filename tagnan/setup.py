"""The guided setup, which scripts/setup hands over to once WSL (or macOS) and uv are there.

It checks each thing Tagnan needs, installs what is missing with the user's consent, connects
their Claude account, writes their settings, tries the brain for real and starts Tagnan. It can
run again at will: what is already done is skipped.

    scripts/setup            a question at each choice (arrow keys), with a default
    scripts/setup --yes      every default, installs included
    scripts/setup --check    what is ready and what is missing; changes nothing
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tagnan import config as configs
from tagnan.paths import EXAMS_DIR, REPO, config_file, state_dir
from tagnan.scheduler import PACES
from tagnan.setup_ui import Terminal

__all__ = ["Setup", "SetupError", "Terminal", "main"]

LOCAL_BIN = Path.home() / ".local" / "bin"
# Where the brain finds programs: it runs through `wsl.exe -e`, or from the Finder or launchd on
# macOS, without a login shell, so only with ~/.local/bin and Homebrew's (scripts/brain adds
# them) and the system's own folders.
BRAIN_PATH = (
    LOCAL_BIN,
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/usr/bin"),
    Path("/bin"),
)
# The environment a Mac app starts with (Finder, launchd): the trial calls the brain in it.
MAC_APP_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
# The oldest macOS the window's Qt runs on (PySide6 6.12's wheels are macosx_14_0).
MIN_MACOS = (14, 0)
CLAUDE_INSTALLER = "curl -fsSL https://claude.ai/install.sh | bash"


class SetupError(Exception):
    """A step that cannot go on; the message says what to do."""


@dataclass(frozen=True)
class Choices:
    exam: str
    model: str
    effort: str
    start_hour: int
    end_hour: int
    weekends: bool


def config_text(choices: Choices) -> str:
    """The config file the setup writes; config.load reads it back to the same choices."""
    return f"""# Tagnan's config, written by scripts/setup (run it again to change your answers).
# More keys, and what each one does: config.example.toml.

exam = "{choices.exam}"

[rhythm]
start_hour = {choices.start_hour}
end_hour = {choices.end_hour}
weekends = {"true" if choices.weekends else "false"}

[brain]
model = "{choices.model}"
explain_model = "{choices.model}"
effort = "{choices.effort}"
explain_effort = "{choices.effort}"
"""


def account(status: dict[str, Any]) -> tuple[bool, str]:
    """From `claude auth status --json`: whether the brain can write, and how it is billed."""
    if not status.get("loggedIn"):
        return False, "not signed in"
    if status.get("authMethod") == "claude.ai":
        plan = status.get("subscriptionType")
        return True, f"{plan} subscription" if plan else "Claude subscription"
    return True, f"{status.get('authMethod', '?')} account, billed by API usage"


def exams() -> list[str]:
    return sorted(p.stem for p in EXAMS_DIR.glob("*.toml"))


def run(command: Sequence[str], **options: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - argument lists built here, no shell
        list(command), text=True, check=False, **options
    )


def windows(function: str) -> str:
    """One of scripts/_windows.sh's helpers, run from WSL: its output, a path or a value."""
    done = run(
        ["bash", "-c", f'source "$0"; {function}', str(REPO / "scripts" / "_windows.sh")],
        capture_output=True,
    )
    if done.returncode != 0:
        raise SetupError(f"{function}: {done.stderr.strip() or 'failed'}")
    return done.stdout.strip()


def macos_supported(version: str) -> bool:
    """Whether a macOS version ("14.5", "15") runs the window; an unreadable one is let through."""
    try:
        numbers = tuple(int(part) for part in version.split(".")[:2])
    except ValueError:
        return True
    return not numbers or numbers >= MIN_MACOS


def mac_window_python() -> Path:
    """The window's Python on macOS, in the environment scripts/ui-setup creates."""
    return state_dir() / "venv" / "bin" / "python"


class Setup:
    def __init__(
        self, term: Terminal, *, check: bool, mac: bool = sys.platform == "darwin"
    ) -> None:
        self.term = term
        self.check = check
        self.mac = mac  # window, brain and game side by side; else the window is on Windows
        self.missing: list[str] = []

    def offer(self, question: str) -> bool:
        """Whether to change something: never in --check, else the user's say (yes by default)."""
        return not self.check and self.term.confirm(question)

    def install(self, label: str, command: Sequence[str], **options: Any) -> bool:
        """A long step behind a spinner; False if it failed (the terminal shows why)."""
        done, _ = self.term.task(label, command, **options)
        return done.returncode == 0

    # --- The steps ----------------------------------------------------------------------------

    def prerequisites(self) -> None:
        if self.mac:
            version = platform.mac_ver()[0]
            if not macos_supported(version):
                raise SetupError(
                    f"macOS {version}: my window needs macOS {MIN_MACOS[0]} (Sonoma) or later.\n"
                    "Update the Mac, then run scripts/setup again."
                )
            self.term.done("macOS", version)
        else:
            self.term.done("WSL", os.environ.get("WSL_DISTRO_NAME", ""))
        uv = run(["uv", "--version"], capture_output=True).stdout.split()
        self.term.done("uv", uv[1] if len(uv) > 1 else "")

    def claude(self) -> None:
        program = self.find_claude()
        if program is None:
            self.term.todo("Claude Code", "not installed")
            self.term.quip("I need a quill to write my questions.")
            self.term.note("I write them with Claude Code, Anthropic's official CLI.")
            if not self.offer("Install Claude Code?"):
                self.missing.append("Claude Code")
                return
            if not self.install("Installing Claude Code", ["bash", "-c", CLAUDE_INSTALLER]) or not (
                program := self.find_claude()
            ):
                raise SetupError(
                    "Installing Claude Code failed. See https://code.claude.com/docs,"
                    " then run scripts/setup again."
                )
        if program.parent not in BRAIN_PATH:
            self.term.todo("Claude Code", f"in {program.parent}, out of the window's reach")
            self.term.note(
                "The window calls Claude without your login shell, so it must be in\n"
                "~/.local/bin (or Homebrew's). The native build installs there."
            )
            if not self.offer("Install the native build?"):
                self.missing.append("Claude Code in ~/.local/bin")
                return
            self.install("Installing the native build", [str(program), "install"])
            program = LOCAL_BIN / "claude"
            if not program.exists():
                raise SetupError("claude install did not put claude in ~/.local/bin.")
        version = run([str(program), "--version"], capture_output=True).stdout.split()
        self.term.done("Claude Code", version[0] if version else "")
        signed_in, detail = account(self.auth_status(program))
        if not signed_in:
            self.term.todo("Claude account", "not signed in")
            self.term.note("Pro, Max, Team or Enterprise: questions come out of your plan.")
            if not self.offer("Sign in now?"):
                self.missing.append("Claude sign-in")
                return
            self.term.handover(
                "Your browser opens Claude's sign-in page. No browser? Open the link below."
            )
            run([str(program), "auth", "login", "--claudeai"])
            signed_in, detail = account(self.auth_status(program))
            if not signed_in:
                raise SetupError("Still not signed in: run scripts/setup again to retry.")
        if "API" in detail:
            self.term.todo("Claude account", detail)
            self.term.note(
                "To use your subscription instead: claude auth logout, then scripts/setup."
            )
        else:
            self.term.done("Claude account", detail)

    @staticmethod
    def find_claude() -> Path | None:
        for candidate in (LOCAL_BIN / "claude", shutil.which("claude")):
            if candidate and Path(candidate).exists():
                return Path(candidate)
        return None

    @staticmethod
    def auth_status(program: Path) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="tagnan-setup-") as folder:
            done = run([str(program), "auth", "status", "--json"], capture_output=True, cwd=folder)
        try:
            status = json.loads(done.stdout)
        except json.JSONDecodeError:
            return {}
        return status if isinstance(status, dict) else {}

    def windows_python(self) -> None:
        """The window's Python on Windows: the one installed, else one that uv brings for Tagnan
        only, at the window's step (scripts/ui-setup): no admin rights, no Store."""
        if Path(windows("windows_base_python")).exists():
            self.term.done("Windows Python 3.12", "found")
        elif not (Path(windows("windows_venv_dir")) / "Scripts" / "python.exe").exists():
            self.term.done("Windows Python 3.12", "none needed: Tagnan brings his own")

    def window(self) -> None:
        venv = (
            mac_window_python()
            if self.mac
            else Path(windows("windows_venv_dir")) / "Scripts" / "python.exe"
        )
        if self.check:
            if venv.exists():
                self.term.done("Window", "ready")
            else:
                self.term.todo("Window", "to prepare")
                self.missing.append("the window's environment")
            return
        label = "Checking the window" if venv.exists() else "Preparing the window (a few minutes)"
        if not self.install(label, [str(REPO / "scripts" / "ui-setup")]):
            raise SetupError("Preparing the window failed: its last messages are above.")
        self.term.done("Window", "ready")

    def settings(self) -> None:
        path = config_file()
        shown = str(path).replace(str(Path.home()), "~")
        self.term.heading("Settings")
        if path.exists():
            try:
                current = configs.load(path)
            except ValueError as error:
                raise SetupError(f"{error}\nFix or delete {path}, then run this again.") from None
            self.term.done("Config", shown)
            if self.check or self.term.confirm("Keep your current settings?"):
                self.pace()
                return
        elif self.check:
            self.term.done("Config", "the defaults (no file yet)")
            return
        else:
            current = configs.Config()
        names = exams()
        exam = current.exam if current.exam in names else names[0]
        if len(names) > 1:
            options = [(n, "") for n in names]
            exam = names[self.term.select("Which exam?", options, names.index(exam))]
        known = [m.model for m in configs.MODELS]
        model = configs.MODELS[
            self.term.select(
                "Which model writes the questions?",
                [(m.label, m.hint) for m in configs.MODELS],
                known.index(
                    current.brain.model if current.brain.model in known else configs.Brain.model
                ),
            )
        ]
        rhythm = current.rhythm
        start = self.term.hour("Questions from what hour?", rhythm.start_hour)
        end = self.term.hour("Until what hour?", rhythm.end_hour)
        weekends = self.term.confirm("On weekends too?", rhythm.weekends)
        text = config_text(Choices(exam, model[0], model[1], start, end, weekends))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        try:
            configs.load(path)
        except ValueError as error:
            raise SetupError(f"{error}\nRun scripts/setup again with other answers.") from None
        self.pace()
        self.term.done("Settings saved", shown)

    def pace(self) -> None:
        """His starting pace, kept by the window in its settings.json; the menu changes it later."""
        path = self.window_settings()
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        saved = saved if isinstance(saved, dict) else {}
        keys = [p.key for p in PACES]
        current = str(saved.get("pace")) if saved.get("pace") in keys else "regularly"
        if self.check:
            self.term.done("Pace", next(p.name for p in PACES if p.key == current))
            return
        chosen = PACES[
            self.term.select(
                "How often should he ask?",
                [(p.name, p.hint) for p in PACES],
                keys.index(current),
            )
        ]
        saved["pace"] = chosen.key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(saved, indent=2), encoding="utf-8")

    def window_settings(self) -> Path:
        if self.mac:
            return state_dir() / "settings.json"
        return Path(windows('wslpath -u "$(windows_localappdata)"')) / "tagnan" / "settings.json"

    def brain_call(self) -> tuple[list[str], dict[str, Any]]:
        """How the window calls the brain: through wsl.exe from Windows; on macOS directly, in
        the bare environment a Mac app starts with."""
        brain = str(REPO / "scripts" / "brain")
        if self.mac:
            env = {
                name: os.environ[name]
                for name in ("HOME", "USER", "LOGNAME", "TMPDIR", "LANG")
                if name in os.environ
            }
            return [brain, "check"], {"env": {**env, "PATH": MAC_APP_PATH}}
        command = ["wsl.exe", "-d", os.environ["WSL_DISTRO_NAME"], "-e", brain, "check"]
        return command, {"cwd": "/mnt/c"}

    def trial(self) -> None:
        """One tiny real call, the way the window makes them."""
        self.term.heading("Trial")
        if self.check or self.missing:
            self.term.note(
                "Waits until nothing is missing."
                if self.missing
                else "Skipped with --check: it uses a little of your plan."
            )
            return
        command, options = self.brain_call()
        done, seconds = self.term.task("Asking Claude for a first word", command, **options)
        try:
            answer = json.loads(done.stdout)
        except json.JSONDecodeError:
            answer = {}
        if done.returncode != 0 or not answer.get("ok"):
            raise SetupError(
                "Claude did not answer as expected. If your plan does not include this\n"
                "model, run scripts/setup again and choose Sonnet. If you have reached your\n"
                "usage limits, try again later."
            )
        self.term.done("Claude answers", f"{answer.get('model', '')} · {seconds:.0f}s")

    def finish(self) -> None:
        self.term.heading("Last touches")
        where = "in Applications" if self.mac else "in the Start menu"
        shortcut = self.term.confirm(f"Add Tagnan to {where.removeprefix('in ')}?")
        if shortcut:
            startup = self.term.confirm("Start him at each sign-in?", False)
            command = [str(REPO / "scripts" / "install-shortcut")]
            if self.install(
                "Creating the shortcut", [*command, "--startup"] if startup else command
            ):
                place = "Applications" if self.mac else "Start menu"
                self.term.done("Shortcut", place + (", and at each sign-in" if startup else ""))
            else:
                shortcut = False
        if not self.install("Calling Tagnan", [str(REPO / "scripts" / "tagnan")]):
            log = str(self.log()).replace(str(Path.home()), "~")
            raise SetupError(f"Tagnan did not start: see {log}.")
        self.term.gap()
        self.term.done("Tagnan is on your desktop", "bottom right")
        self.term.quip("Here I am! En garde, the questions are coming.")
        self.term.note("Right-click him for a question now, progress, pace, sound or a break.")
        self.term.note(
            "Start him later: " + (f"his icon {where}, or " if shortcut else "") + "scripts/tagnan"
        )
        self.term.note("Change your answers: scripts/setup")
        self.term.outro("All set.")

    def log(self) -> Path:
        """Where scripts/tagnan sends the window's messages."""
        if self.mac:
            return state_dir() / "ui.log"
        state = os.environ.get("XDG_STATE_HOME")
        return (Path(state) if state else Path.home() / ".local" / "state") / "tagnan" / "ui.log"

    def all(self) -> int:
        self.term.intro("Tagnan", "guided setup")
        self.term.quip("En garde! Let's set up my quarters.")
        self.term.gap()
        self.prerequisites()
        self.claude()
        if not self.mac:
            self.windows_python()
        self.window()
        self.settings()
        self.trial()
        if self.missing:
            self.term.gap()
            self.term.fail("Missing", ", ".join(self.missing))
            self.term.outro(
                "Run scripts/setup again whenever you like: the rest is kept.", ok=False
            )
            return 1
        if self.check:
            self.term.gap()
            self.term.outro("All set.")
            return 0
        self.finish()
        return 0


def setup_log() -> Path:
    """The raw output of the setup's long steps, for when one fails."""
    state = os.environ.get("XDG_STATE_HOME")
    base = Path(state) if state else Path.home() / ".local" / "state"
    return (state_dir() if sys.platform == "darwin" else base / "tagnan") / "setup.log"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts/setup", description="Tagnan's guided setup")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--yes", action="store_true", help="take every default, installs included")
    mode.add_argument("--check", action="store_true", help="say what is missing, change nothing")
    args = parser.parse_args(argv)
    term = Terminal(assume_yes=args.yes, log=setup_log())
    try:
        return Setup(term, check=args.check).all()
    except SetupError as error:
        term.gap()
        term.fail("Stopped")
        term.note(str(error))
        term.outro("Run scripts/setup again once it is fixed: what is done is kept.", ok=False)
        return 1
    except KeyboardInterrupt:
        term.raw("\033[?25h\n")
        term.fail("Cancelled")
        term.outro("Run scripts/setup again whenever you like: what is done is kept.", ok=False)
        return 130


if __name__ == "__main__":
    sys.exit(main())
