"""The guided setup, which scripts/setup hands over to once WSL and uv are there.

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
from tagnan.paths import EXAMS_DIR, REPO, config_file
from tagnan.scheduler import PACES

LOCAL_BIN = Path.home() / ".local" / "bin"
# Where the brain finds programs: it runs through `wsl.exe -e`, without a login shell, so only
# with ~/.local/bin (scripts/brain adds it) and the system's own folders.
BRAIN_PATH = (LOCAL_BIN, Path("/usr/local/bin"), Path("/usr/bin"), Path("/bin"))
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
    ("claude-opus-5-5", "max", "Opus 5.5, effort max", "le plus fin, quelques minutes par lot"),
    ("claude-sonnet-5-5", "high", "Sonnet 5.5, effort high", "rapide, plus léger pour tes limites"),
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
        return False, "pas connecté"
    if status.get("authMethod") == "claude.ai":
        plan = status.get("subscriptionType")
        return True, f"abonnement {plan}" if plan else "abonnement Claude"
    return True, f"compte {status.get('authMethod', '?')}, facturé à l'usage de l'API"


def exams() -> list[str]:
    return sorted(p.stem for p in EXAMS_DIR.glob("*.toml"))


class Terminal:
    """What the setup says and asks; Tagnan's lines are in English, like his bubble."""

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
        side = ["", self.paint("Tagnan", "1"), self.paint("installation guidée", "2"), "", ""]
        for drawing, words in zip(art, side, strict=True):
            self.line(f"{self.paint(drawing.ljust(19), '38;5;111')} {words}".rstrip())
        self.line()
        self.quip("En garde! Let's set up my quarters.")
        self.line()

    def quip(self, text: str) -> None:
        self.line("  " + self.paint(f"« {text} »", "3;38;5;111"))

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
            answer = self._ask(f"{question} [{'O/n' if default else 'o/N'}] : ")
            if answer is None:
                return default
            if answer.lower() in ("o", "oui", "y", "yes"):
                return True
            if answer.lower() in ("n", "non", "no"):
                return False
            self.note("Réponds o ou n.")

    def choose(self, question: str, options: Sequence[tuple[str, str]], default: int = 0) -> int:
        self.note(question)
        for i, (label, hint) in enumerate(options, 1):
            number = self.paint(str(i), "1") if i == default + 1 else str(i)
            self.note(f"  {number} {label.ljust(24)} {self.paint(hint, '2')}".rstrip())
        while True:
            answer = self._ask(f"Choix [{default + 1}] : ")
            if answer is None:
                return default
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return int(answer) - 1
            self.note(f"Un nombre de 1 à {len(options)}.")

    def hour(self, question: str, default: int) -> int:
        while True:
            answer = self._ask(f"{question} [{default}] : ")
            if answer is None:
                return default
            answer = answer.lower().removesuffix("h")
            if answer.isdigit() and 0 <= int(answer) <= 24:
                return int(answer)
            self.note("Une heure de 0 à 24, comme 9 ou 18.")


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
        raise SetupError(f"{function} : {done.stderr.strip() or 'échec'}")
    return done.stdout.strip()


class Setup:
    def __init__(self, term: Terminal, *, check: bool) -> None:
        self.term = term
        self.check = check
        self.missing: list[str] = []

    def offer(self, question: str) -> bool:
        """Whether to change something: never in --check, else the user's say (yes by default)."""
        return not self.check and self.term.yes(question)

    # --- The steps ----------------------------------------------------------------------------

    def prerequisites(self) -> None:
        self.term.ok("WSL", os.environ.get("WSL_DISTRO_NAME", ""))
        uv = run(["uv", "--version"], capture_output=True).stdout.split()
        self.term.ok("uv", uv[1] if len(uv) > 1 else "")

    def claude(self) -> None:
        program = self.find_claude()
        if program is None:
            self.term.todo("Claude Code", "absent")
            self.term.quip("I need a quill to write my questions.")
            self.term.note("J'écris mes questions avec Claude Code, le CLI officiel d'Anthropic.")
            if not self.offer(f"L'installer ({CLAUDE_INSTALLER}) ?"):
                self.missing.append("Claude Code")
                return
            if run(["bash", "-c", CLAUDE_INSTALLER]).returncode != 0 or not (
                program := self.find_claude()
            ):
                raise SetupError(
                    "L'installation de Claude Code a échoué. Voir https://code.claude.com/docs"
                    " puis relance scripts/setup."
                )
        if program.parent not in BRAIN_PATH:
            self.term.todo("Claude Code", f"dans {program.parent}, hors de portée de la fenêtre")
            self.term.note(
                "La fenêtre appelle Claude sans ton shell de connexion : il doit être dans\n"
                "~/.local/bin. La version native s'y installe (claude install)."
            )
            if not self.offer("Installer la version native ?"):
                self.missing.append("Claude Code dans ~/.local/bin")
                return
            run([str(program), "install"])
            program = LOCAL_BIN / "claude"
            if not program.exists():
                raise SetupError("claude install n'a pas mis claude dans ~/.local/bin.")
        version = run([str(program), "--version"], capture_output=True).stdout.split()
        signed_in, detail = account(self.auth_status(program))
        if not signed_in:
            self.term.todo("Claude Code", f"{version[0] if version else ''}, pas connecté")
            self.term.note(
                "Connecte ton compte Claude (Pro, Max, Team ou Enterprise) : une page de\n"
                "connexion va s'ouvrir. Si le navigateur ne s'ouvre pas, ouvre le lien affiché."
            )
            if not self.offer("Te connecter maintenant ?"):
                self.missing.append("connexion à Claude")
                return
            run([str(program), "auth", "login", "--claudeai"])
            signed_in, detail = account(self.auth_status(program))
            if not signed_in:
                raise SetupError("Toujours pas connecté : relance scripts/setup pour réessayer.")
            self.term.ok("  connecté", detail)
        else:
            self.term.ok("Claude Code", f"{version[0] if version else ''}, {detail}")
        if "API" in detail:
            self.term.note(
                "Ce compte paie Claude à l'usage. Pour passer par ton abonnement :\n"
                "claude auth logout, puis relance scripts/setup."
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
            self.term.ok("Python Windows 3.12", "déjà là")
            return
        self.term.todo("Python Windows 3.12", "absent")
        self.term.note("Ma fenêtre tourne avec le Python de Windows, à installer une fois.")
        if not self.offer("L'installer avec winget (pour toi seul, sans droits admin) ?"):
            self.missing.append("Python Windows 3.12")
            return
        run(WINGET_PYTHON, cwd="/mnt/c")
        if not Path(windows("windows_base_python")).exists():
            raise SetupError(
                "Python 3.12 toujours introuvable côté Windows. Installe-le depuis\n"
                "https://www.python.org/downloads/windows/ (« pour moi seulement »), puis relance."
            )
        self.term.ok("  installé")

    def window(self) -> None:
        venv = Path(windows("windows_venv_dir")) / "Scripts" / "python.exe"
        if self.check:
            if venv.exists():
                self.term.ok("Fenêtre (PySide6)", "prête")
            else:
                self.term.todo("Fenêtre (PySide6)", "à préparer")
                self.missing.append("environnement de la fenêtre")
            return
        if "Python Windows 3.12" in self.missing:
            self.missing.append("environnement de la fenêtre")
            return
        self.term.todo("Fenêtre (PySide6)", "déjà prête, vérification" if venv.exists() else "")
        if run([str(REPO / "scripts" / "ui-setup")]).returncode != 0:
            raise SetupError("scripts/ui-setup a échoué : son message est juste au-dessus.")
        self.term.ok("Fenêtre (PySide6)", "prête")

    def settings(self) -> None:
        path = config_file()
        self.term.section("Réglages", "(Entrée garde la valeur entre crochets)")
        if path.exists():
            try:
                current = configs.load(path)
            except ValueError as error:
                raise SetupError(f"{error}\nCorrige ou supprime {path}, puis relance.") from None
            self.term.ok("Config", str(path).replace(str(Path.home()), "~"))
            if self.check or self.term.yes("La garder telle quelle ?"):
                self.pace()
                return
        elif self.check:
            self.term.todo("Config", "aucune : les valeurs par défaut")
            return
        else:
            current = configs.Config()
        names = exams()
        exam = current.exam if current.exam in names else names[0]
        if len(names) > 1:
            options = [(n, "") for n in names]
            exam = names[self.term.choose("Quel examen ?", options, names.index(exam))]
        known = [m for m, _, _, _ in MODELS]
        model = MODELS[
            self.term.choose(
                "Quel modèle écrit les questions ?",
                [(label, hint) for _, _, label, hint in MODELS],
                known.index(current.brain.model) if current.brain.model in known else 0,
            )
        ]
        rhythm = current.rhythm
        start = self.term.hour("Des questions à partir de quelle heure ?", rhythm.start_hour)
        end = self.term.hour("Et jusqu'à quelle heure ?", rhythm.end_hour)
        weekends = self.term.yes("Le week-end aussi ?", rhythm.weekends)
        text = config_text(Choices(exam, model[0], model[1], start, end, weekends))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        try:
            configs.load(path)
        except ValueError as error:
            raise SetupError(f"{error}\nRelance scripts/setup avec d'autres réponses.") from None
        self.term.ok("Config écrite", str(path).replace(str(Path.home()), "~"))
        self.pace()

    def pace(self) -> None:
        """His starting pace, kept by the window in its settings.json; the menu changes it later."""
        path = Path(windows('wslpath -u "$(windows_localappdata)"')) / "tagnan" / "settings.json"
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        saved = saved if isinstance(saved, dict) else {}
        keys = [p.key for p in PACES]
        current = str(saved.get("pace")) if saved.get("pace") in keys else "regularly"
        if self.check:
            self.term.ok("Allure", next(p.name for p in PACES if p.key == current))
            return
        chosen = PACES[
            self.term.choose(
                "À quelle allure ? (son menu « How often » la change ensuite)",
                [(p.name, p.hint) for p in PACES],
                keys.index(current),
            )
        ]
        saved["pace"] = chosen.key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(saved, indent=2), encoding="utf-8")

    def trial(self) -> None:
        """One tiny real call, the way the window makes them: wsl.exe, then scripts/brain."""
        self.term.section("Essai")
        if self.check or self.missing:
            if self.missing:
                self.term.note("Pas d'essai tant qu'il manque quelque chose.")
            else:
                self.term.note("Sauté avec --check (il consomme un peu de quota).")
            return
        self.term.quip("Let me dip my quill.")
        command = [
            "wsl.exe",
            "-d",
            os.environ["WSL_DISTRO_NAME"],
            "-e",
            str(REPO / "scripts" / "brain"),
            "check",
        ]
        began = time.monotonic()
        done = run(command, capture_output=True, stdin=subprocess.DEVNULL, cwd="/mnt/c")
        seconds = time.monotonic() - began
        try:
            answer = json.loads(done.stdout)
        except json.JSONDecodeError:
            answer = {}
        if done.returncode != 0 or not answer.get("ok"):
            lines = done.stderr.strip().splitlines()
            raise SetupError(
                f"Claude n'a pas répondu comme prévu : {lines[-1] if lines else 'sans message'}\n"
                "Si le modèle n'est pas inclus dans ton abonnement, relance scripts/setup et\n"
                "choisis Sonnet. Si tes limites d'usage sont atteintes, réessaie plus tard."
            )
        self.term.ok("Claude répond", f"{answer.get('model', '')}, {seconds:.0f} s")

    def finish(self) -> None:
        self.term.section("Raccourcis")
        if self.check:
            return
        startup = False
        if self.term.yes("Une icône « Tagnan » dans le menu Démarrer ?"):
            startup = self.term.yes("Et qu'il vienne à chaque ouverture de session ?", False)
            command = [str(REPO / "scripts" / "install-shortcut")]
            if run([*command, "--startup"] if startup else command).returncode != 0:
                self.term.fail("Raccourcis", "voir le message ci-dessus ; Tagnan marche sans")
        self.term.line()
        if self.term.yes("Faire venir Tagnan maintenant ?"):
            if run([str(REPO / "scripts" / "tagnan")]).returncode != 0:
                raise SetupError("Tagnan n'a pas démarré : voir ~/.local/state/tagnan/ui.log.")
            self.term.line()
            self.term.quip("Here I am. My first questions take a few minutes to write.")
        self.term.note(
            "Clic droit sur lui : une question tout de suite, la progression, l'allure, le son,\n"
            "une pause. Pour le relancer plus tard : scripts/tagnan"
            + (", ou son icône du menu Démarrer." if not startup else ".")
        )

    def all(self) -> int:
        self.term.banner()
        self.prerequisites()
        self.claude()
        self.windows_python()
        self.window()
        self.settings()
        self.trial()
        if self.missing:
            self.term.line()
            self.term.fail("Il manque", ", ".join(self.missing))
            if not self.check:
                self.term.note("Relance scripts/setup quand tu veux : le reste est gardé.")
            return 1
        if self.check:
            self.term.line()
            self.term.ok("Tout est prêt")
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
        term.fail("Arrêt")
        term.note(str(error))
        return 1
    except KeyboardInterrupt:
        term.line()
        term.note("Interrompu. Relance scripts/setup quand tu veux : ce qui est fait est gardé.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
