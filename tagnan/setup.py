"""The guided setup, which scripts/setup hands over to once WSL (or macOS) and uv are there.

It checks each thing Tagnan needs, installs what is missing with the user's consent, connects
their Claude account, writes their settings, tries the brain for real and starts Tagnan. It can
run again at will: what is already done is skipped.

    scripts/setup            a question at each choice, with a default in brackets
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
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from tagnan import config as configs
from tagnan.paths import EXAMS_DIR, REPO, config_file, state_dir
from tagnan.scheduler import PACES

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
WINGET_PYTHON = (
    "winget.exe",
    "install",
    "--id",
    "Python.Python.3.12",
    "--exact",
    "--scope",
    "user",
    "--accept-package-agreements",
    "--accept-source-agreements",
)

# The models offered, from config.Brain's default down: (model, effort, label, hint).
MODELS = (
    ("claude-opus-5-5", "max", "Opus 5.5, effort max", "the finest questions, minutes per batch"),
    ("claude-sonnet-5-5", "high", "Sonnet 5.5, effort high", "quick, lighter on your usage limits"),
)

TAGNAN = r"""      .-~~-.   ,
  ___/______\_/__
     ( o  o )  /
     (  ~~  ) /
      '-..-' /"""


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


class Terminal:
    """What the setup says and asks, with a line from Tagnan now and then."""

    def __init__(
        self,
        *,
        assume_yes: bool = False,
        out: TextIO = sys.stdout,
        read: Callable[[str], str] = input,
    ) -> None:
        self.assume_yes = assume_yes
        self.out = out
        self.read = read
        self.color = out.isatty() and "NO_COLOR" not in os.environ

    def paint(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def line(self, text: str = "") -> None:
        print(text, file=self.out, flush=True)

    def banner(self) -> None:
        art = TAGNAN.splitlines()
        side = ["", self.paint("Tagnan", "1"), self.paint("guided setup", "2"), "", ""]
        for drawing, words in zip(art, side, strict=True):
            self.line(f"{self.paint(drawing.ljust(19), '38;5;111')} {words}".rstrip())
        self.line()
        self.quip("En garde! Let's set up my quarters.")
        self.line()

    def quip(self, text: str) -> None:
        self.line("  " + self.paint(f"\u201c{text}\u201d", "3;38;5;111"))

    def section(self, title: str, hint: str = "") -> None:
        self.line()
        self.line(self.paint(title, "1") + (f"  {self.paint(hint, '2')}" if hint else ""))

    def status(self, mark: str, name: str, detail: str = "") -> None:
        self.line(f"{mark} {name.ljust(22)} {self.paint(detail, '2')}".rstrip())

    def ok(self, name: str, detail: str = "") -> None:
        self.status(self.paint("✓", "32"), name, detail)

    def todo(self, name: str, detail: str = "") -> None:
        self.status(self.paint("•", "33"), name, detail)

    def fail(self, name: str, detail: str = "") -> None:
        self.status(self.paint("✗", "31"), name, detail)

    def note(self, text: str) -> None:
        for row in text.splitlines():
            self.line(f"  {row}")

    def _ask(self, prompt: str) -> str | None:
        """The answer typed, None for the default (Enter, --yes, or no terminal left)."""
        if self.assume_yes:
            return None
        try:
            answer = self.read(f"  {prompt}").strip()
        except EOFError:
            self.line()
            return None
        return answer or None

    def yes(self, question: str, default: bool = True) -> bool:
        while True:
            answer = self._ask(f"{question} [{'Y/n' if default else 'y/N'}]: ")
            if answer is None:
                return default
            if answer.lower() in ("o", "oui", "y", "yes"):
                return True
            if answer.lower() in ("n", "non", "no"):
                return False
            self.note("Answer y or n.")

    def choose(self, question: str, options: Sequence[tuple[str, str]], default: int = 0) -> int:
        self.note(question)
        for i, (label, hint) in enumerate(options, 1):
            number = self.paint(str(i), "1") if i == default + 1 else str(i)
            self.note(f"  {number} {label.ljust(24)} {self.paint(hint, '2')}".rstrip())
        while True:
            answer = self._ask(f"Choice [{default + 1}]: ")
            if answer is None:
                return default
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return int(answer) - 1
            self.note(f"A number from 1 to {len(options)}.")

    def hour(self, question: str, default: int) -> int:
        while True:
            answer = self._ask(f"{question} [{default}]: ")
            if answer is None:
                return default
            answer = answer.lower().removesuffix("h")
            if answer.isdigit() and 0 <= int(answer) <= 24:
                return int(answer)
            self.note("An hour from 0 to 24, like 9 or 18.")


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
        return not self.check and self.term.yes(question)

    # --- The steps ----------------------------------------------------------------------------

    def prerequisites(self) -> None:
        if self.mac:
            version = platform.mac_ver()[0]
            if not macos_supported(version):
                raise SetupError(
                    f"macOS {version}: my window needs macOS {MIN_MACOS[0]} (Sonoma) or later.\n"
                    "Update the Mac, then run scripts/setup again."
                )
            self.term.ok("macOS", version)
        else:
            self.term.ok("WSL", os.environ.get("WSL_DISTRO_NAME", ""))
        uv = run(["uv", "--version"], capture_output=True).stdout.split()
        self.term.ok("uv", uv[1] if len(uv) > 1 else "")

    def claude(self) -> None:
        program = self.find_claude()
        if program is None:
            self.term.todo("Claude Code", "missing")
            self.term.quip("I need a quill to write my questions.")
            self.term.note("I write my questions with Claude Code, Anthropic's official CLI.")
            if not self.offer(f"Install it ({CLAUDE_INSTALLER})?"):
                self.missing.append("Claude Code")
                return
            if run(["bash", "-c", CLAUDE_INSTALLER]).returncode != 0 or not (
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
                "~/.local/bin (or Homebrew's). The native build installs there (claude install)."
            )
            if not self.offer("Install the native build?"):
                self.missing.append("Claude Code in ~/.local/bin")
                return
            run([str(program), "install"])
            program = LOCAL_BIN / "claude"
            if not program.exists():
                raise SetupError("claude install did not put claude in ~/.local/bin.")
        version = run([str(program), "--version"], capture_output=True).stdout.split()
        signed_in, detail = account(self.auth_status(program))
        if not signed_in:
            self.term.todo("Claude Code", f"{version[0] if version else ''}, not signed in")
            self.term.note(
                "Connect your Claude account (Pro, Max, Team or Enterprise): a sign-in page\n"
                "will open. If no browser opens, open the link shown below."
            )
            if not self.offer("Sign in now?"):
                self.missing.append("Claude sign-in")
                return
            run([str(program), "auth", "login", "--claudeai"])
            signed_in, detail = account(self.auth_status(program))
            if not signed_in:
                raise SetupError("Still not signed in: run scripts/setup again to retry.")
            self.term.ok("  signed in", detail)
        else:
            self.term.ok("Claude Code", f"{version[0] if version else ''}, {detail}")
        if "API" in detail:
            self.term.note(
                "This account pays for Claude by usage. To use your subscription instead:\n"
                "claude auth logout, then run scripts/setup again."
            )

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
        python = Path(windows("windows_base_python"))
        if python.exists():
            self.term.ok("Windows Python 3.12", "found")
            return
        self.term.todo("Windows Python 3.12", "missing")
        self.term.note("My window runs on Windows' Python, installed once.")
        if not self.offer("Install it with winget (for you only, no admin rights)?"):
            self.missing.append("Windows Python 3.12")
            return
        run(WINGET_PYTHON, cwd="/mnt/c")
        if not Path(windows("windows_base_python")).exists():
            raise SetupError(
                "Still no Python 3.12 on the Windows side. Install it from\n"
                "https://www.python.org/downloads/windows/ (for you only), then run this again."
            )
        self.term.ok("  installed")

    def window(self) -> None:
        venv = (
            mac_window_python()
            if self.mac
            else Path(windows("windows_venv_dir")) / "Scripts" / "python.exe"
        )
        if self.check:
            if venv.exists():
                self.term.ok("Window (PySide6)", "ready")
            else:
                self.term.todo("Window (PySide6)", "to prepare")
                self.missing.append("the window's environment")
            return
        if "Windows Python 3.12" in self.missing:
            self.missing.append("the window's environment")
            return
        self.term.todo("Window (PySide6)", "ready, checking" if venv.exists() else "")
        if run([str(REPO / "scripts" / "ui-setup")]).returncode != 0:
            raise SetupError("scripts/ui-setup failed: its message is just above.")
        self.term.ok("Window (PySide6)", "ready")

    def settings(self) -> None:
        path = config_file()
        self.term.section("Settings", "(Enter keeps the value in brackets)")
        if path.exists():
            try:
                current = configs.load(path)
            except ValueError as error:
                raise SetupError(f"{error}\nFix or delete {path}, then run this again.") from None
            self.term.ok("Config", str(path).replace(str(Path.home()), "~"))
            if self.check or self.term.yes("Keep it as it is?"):
                self.pace()
                return
        elif self.check:
            self.term.todo("Config", "none: the defaults")
            return
        else:
            current = configs.Config()
        names = exams()
        exam = current.exam if current.exam in names else names[0]
        if len(names) > 1:
            options = [(n, "") for n in names]
            exam = names[self.term.choose("Which exam?", options, names.index(exam))]
        known = [m for m, _, _, _ in MODELS]
        model = MODELS[
            self.term.choose(
                "Which model writes the questions?",
                [(label, hint) for _, _, label, hint in MODELS],
                known.index(current.brain.model) if current.brain.model in known else 0,
            )
        ]
        rhythm = current.rhythm
        start = self.term.hour("Questions from what hour?", rhythm.start_hour)
        end = self.term.hour("Until what hour?", rhythm.end_hour)
        weekends = self.term.yes("On weekends too?", rhythm.weekends)
        text = config_text(Choices(exam, model[0], model[1], start, end, weekends))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        try:
            configs.load(path)
        except ValueError as error:
            raise SetupError(f"{error}\nRun scripts/setup again with other answers.") from None
        self.term.ok("Config written", str(path).replace(str(Path.home()), "~"))
        self.pace()

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
            self.term.ok("Pace", next(p.name for p in PACES if p.key == current))
            return
        chosen = PACES[
            self.term.choose(
                'At what pace? (his "How often" menu changes it later)',
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
        """One tiny real call, the way the window makes them: scripts/brain, through wsl.exe from
        Windows."""
        self.term.section("Trial")
        if self.check or self.missing:
            if self.missing:
                self.term.note("No trial while something is missing.")
            else:
                self.term.note("Skipped with --check (it uses a little of your usage).")
            return
        self.term.quip("Let me dip my quill.")
        command, options = self.brain_call()
        began = time.monotonic()
        done = run(command, capture_output=True, stdin=subprocess.DEVNULL, **options)
        seconds = time.monotonic() - began
        try:
            answer = json.loads(done.stdout)
        except json.JSONDecodeError:
            answer = {}
        if done.returncode != 0 or not answer.get("ok"):
            lines = done.stderr.strip().splitlines()
            raise SetupError(
                f"Claude did not answer as expected: {lines[-1] if lines else 'no message'}\n"
                "If your plan does not include this model, run scripts/setup again and\n"
                "choose Sonnet. If you have reached your usage limits, try again later."
            )
        self.term.ok("Claude answers", f"{answer.get('model', '')}, {seconds:.0f} s")

    def finish(self) -> None:
        self.term.section("Shortcuts")
        if self.check:
            return
        where = "in Applications (Launchpad, Spotlight)" if self.mac else "in the Start menu"
        startup = False
        shortcut = self.term.yes(f'A "Tagnan" icon {where}?')
        if shortcut:
            startup = self.term.yes(
                "And bring him along at each sign-in?"
                if self.mac
                else "And bring him along at each Windows sign-in?",
                False,
            )
            command = [str(REPO / "scripts" / "install-shortcut")]
            if run([*command, "--startup"] if startup else command).returncode != 0:
                self.term.fail("Shortcuts", "see the message above; Tagnan works without them")
                shortcut = False
        self.term.line()
        if self.term.yes("Bring Tagnan in now?"):
            if run([str(REPO / "scripts" / "tagnan")]).returncode != 0:
                log = str(self.log()).replace(str(Path.home()), "~")
                raise SetupError(f"Tagnan did not start: see {log}.")
            self.term.line()
            self.term.quip("Here I am. My first questions take a few minutes to write.")
        self.term.note(
            "Right-click him: a question now, progress, pace, sound, a break.\n"
            "To start him again later: scripts/tagnan"
            + (f", or his icon {where}." if shortcut else ".")
        )

    def log(self) -> Path:
        """Where scripts/tagnan sends the window's messages."""
        if self.mac:
            return state_dir() / "ui.log"
        state = os.environ.get("XDG_STATE_HOME")
        return (Path(state) if state else Path.home() / ".local" / "state") / "tagnan" / "ui.log"

    def all(self) -> int:
        self.term.banner()
        self.prerequisites()
        self.claude()
        if not self.mac:
            self.windows_python()
        self.window()
        self.settings()
        self.trial()
        if self.missing:
            self.term.line()
            self.term.fail("Missing", ", ".join(self.missing))
            if not self.check:
                self.term.note("Run scripts/setup again whenever you like: the rest is kept.")
            return 1
        if self.check:
            self.term.line()
            self.term.ok("All set")
            return 0
        self.finish()
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scripts/setup", description="Tagnan's guided setup")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--yes", action="store_true", help="take every default, installs included")
    mode.add_argument("--check", action="store_true", help="say what is missing, change nothing")
    args = parser.parse_args(argv)
    term = Terminal(assume_yes=args.yes)
    try:
        return Setup(term, check=args.check).all()
    except SetupError as error:
        term.line()
        term.fail("Stopped")
        term.note(str(error))
        return 1
    except KeyboardInterrupt:
        term.line()
        term.note("Interrupted. Run scripts/setup again whenever you like: what is done is kept.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
