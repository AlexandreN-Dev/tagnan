"""The setup's terminal interface, in the manner of today's CLI installers: one rail of steps
(◇ done, ◆ asking, ▲ to do, ■ failed), choices made with the arrow keys, a spinner with a
clock for long steps whose raw output goes to a log and only shows when they fail.

Without a terminal (a pipe, a test) the same calls print plain lines and read typed answers.
"""

import os
import select
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

ACCENT = "38;5;111"  # Tagnan's Prussian blue, lightened to read on dark terminals
DIM, BOLD, ITALIC = "2", "1", "3"
GREEN, YELLOW, RED = "32", "33", "31"

UNICODE = {
    "top": "┌",
    "rail": "│",
    "end": "└",
    "done": "◇",
    "ask": "◆",
    "todo": "▲",
    "fail": "■",
    "on": "●",
    "off": "○",
    "spin": "◒◐◓◑",
    "cursor": "▍",
}
ASCII = {
    "top": "+",
    "rail": "|",
    "end": "+",
    "done": "o",
    "ask": "*",
    "todo": "!",
    "fail": "x",
    "on": "(*)",
    "off": "( )",
    "spin": "-\\|/",
    "cursor": "_",
}

TAGNAN = r"""      .-~~-.   ,
  ___/______\_/__
     ( o  o )  /
     (  ~~  ) /
      '-..-' /"""

KEYS = {
    b"\x1b[A": "up",
    b"\x1b[B": "down",
    b"\x1b[C": "right",
    b"\x1b[D": "left",
    b"\x1bOA": "up",
    b"\x1bOB": "down",
    b"\x1bOC": "right",
    b"\x1bOD": "left",
    b"\r": "enter",
    b"\n": "enter",
    b"\t": "tab",
    b"\x7f": "backspace",
    b"\x08": "backspace",
    b"\x03": "interrupt",
    b"\x04": "interrupt",
    b"\x1b": "escape",
}
TAIL = 12  # lines of a failed step's output shown on screen


def read_key() -> str:
    """One key from the terminal, read in raw mode: a name from KEYS, or the character typed."""
    import termios
    import tty

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        data = os.read(fd, 1)
        if data == b"\x1b" and select.select([fd], [], [], 0.05)[0]:
            data += os.read(fd, 8)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    return KEYS.get(data) or data.decode("utf-8", errors="ignore")


class Terminal:
    def __init__(
        self,
        *,
        assume_yes: bool = False,
        out: TextIO = sys.stdout,
        read: Callable[[str], str] = input,
        keys: Callable[[], str] = read_key,
        interactive: bool | None = None,
        log: Path | None = None,
    ) -> None:
        self.assume_yes = assume_yes
        self.out = out
        self.read = read
        self.keys = keys
        self.interactive = (
            out.isatty() and sys.stdin.isatty() if interactive is None else interactive
        )
        self.color = out.isatty() and "NO_COLOR" not in os.environ
        encoding = (getattr(out, "encoding", None) or "utf-8").lower()
        self.g = UNICODE if "utf" in encoding else ASCII
        self.log = log
        self._drawn = 0  # lines of the block being redrawn (a question while it is asked)

    # --- Drawing --------------------------------------------------------------------------------

    def paint(self, text: str, *codes: str) -> str:
        return f"\033[{';'.join(codes)}m{text}\033[0m" if self.color and codes else text

    def write(self, text: str = "") -> None:
        print(text, file=self.out, flush=True)

    def raw(self, text: str) -> None:
        if self.interactive:
            self.out.write(text)
            self.out.flush()

    def _rail(self, text: str = "") -> str:
        return f"{self.paint(self.g['rail'], DIM)}  {text}".rstrip()

    def _mark(self, glyph: str, colour: str, label: str, detail: str = "") -> str:
        detail = f"  {self.paint(detail, DIM)}" if detail else ""
        return (
            f"{self.paint(self.g[glyph], colour)}  {label.ljust(22) if detail else label}{detail}"
        )

    def draw(self, lines: Sequence[str]) -> None:
        """Draw a block in place of the previous one (a question being answered)."""
        if self._drawn:
            self.raw(f"\033[{self._drawn}F\033[J")
        self.raw("\033[?7l")  # no wrapping: a long hint is cut, the block keeps its height
        for line in lines:
            self.write(line)
        self.raw("\033[?7h")
        self._drawn = len(lines)

    def settle(self, lines: Sequence[str]) -> None:
        """The block's final form, which stays on screen."""
        self.draw(lines)
        self._drawn = 0
        self.raw("\033[?25h")

    # --- What the setup says ----------------------------------------------------------------

    def intro(self, title: str, subtitle: str) -> None:
        self.write()
        for row in TAGNAN.splitlines():
            self.write(self.paint(row, ACCENT))
        self.write()
        badge = self.paint(f" {title} ", BOLD, "7", ACCENT)  # reversed: a tag, as installers do
        self.write(f"{self.paint(self.g['top'], DIM)}  {badge}  {self.paint(subtitle, DIM)}")
        self.gap()

    def gap(self) -> None:
        self.write(self._rail())

    def done(self, label: str, detail: str = "") -> None:
        self.write(self._mark("done", GREEN, label, detail))

    def todo(self, label: str, detail: str = "") -> None:
        self.write(self._mark("todo", YELLOW, label, detail))

    def fail(self, label: str, detail: str = "") -> None:
        self.write(self._mark("fail", RED, label, detail))

    def note(self, text: str) -> None:
        for row in text.splitlines():
            self.write(self._rail(self.paint(row, DIM)))

    def quip(self, text: str) -> None:
        self.write(self._rail(self.paint(f"“{text}”", ITALIC, ACCENT)))

    def heading(self, title: str, hint: str = "") -> None:
        self.gap()
        self.write(
            self._rail(
                self.paint(title.upper(), BOLD) + (f"  {self.paint(hint, DIM)}" if hint else "")
            )
        )

    def outro(self, text: str, *, ok: bool = True) -> None:
        self.write(f"{self.paint(self.g['end'], DIM)}  {self.paint(text, ACCENT if ok else RED)}")
        self.write()

    # --- What the setup asks ------------------------------------------------------------------

    def _settled(self, question: str, answer: str) -> list[str]:
        """An answered question, on one line: the question, then the answer in grey."""
        return [f"{self.paint(self.g['done'], GREEN)}  {question}  {self.paint(answer, DIM)}"]

    def _answered(self, question: str, answer: str) -> None:
        self.write(self._settled(question, answer)[0])

    def _typed(self, prompt: str) -> str | None:
        """Without a terminal: the answer typed, None for the default (Enter, end of input)."""
        try:
            answer = self.read(self._rail(prompt)).strip()
        except EOFError:
            self.write()
            return None
        return answer or None

    def _key(self) -> str:
        key = self.keys()
        if key == "interrupt":
            self.raw("\033[?25h")
            raise KeyboardInterrupt
        return key

    def confirm(self, question: str, default: bool = True) -> bool:
        if self.assume_yes:
            self._answered(question, "Yes" if default else "No")
            return default
        if not self.interactive:
            while True:
                answer = self._typed(f"{question} [{'Y/n' if default else 'y/N'}]: ")
                if answer is None:
                    return default
                if answer.lower() in ("y", "yes", "o", "oui"):
                    return True
                if answer.lower() in ("n", "no", "non"):
                    return False
                self.note("Answer y or n.")
        value = default
        self.raw("\033[?25l")
        while True:
            yes = f"{self.g['on' if value else 'off']} Yes"
            no = f"{self.g['off' if value else 'on']} No"
            yes, no = (
                (self.paint(yes, ACCENT), self.paint(no, DIM))
                if value
                else (self.paint(yes, DIM), self.paint(no, ACCENT))
            )
            self.draw(
                [
                    self._mark("ask", ACCENT, question),
                    self._rail(f"{yes} {self.paint('/', DIM)} {no}"),
                    self.paint(f"{self.g['end']}  ←→ choose · enter confirm", DIM),
                ]
            )
            key = self._key()
            if key in ("left", "right", "up", "down", "tab", "h", "l"):
                value = not value
            elif key.lower() in ("y", "o"):
                value = True
                break
            elif key.lower() == "n":
                value = False
                break
            elif key == "enter":
                break
        self.settle(self._settled(question, "Yes" if value else "No"))
        return value

    def select(self, question: str, options: Sequence[tuple[str, str]], default: int = 0) -> int:
        if self.assume_yes:
            self._answered(question, options[default][0])
            return default
        if not self.interactive:
            self.write(self._mark("ask", ACCENT, question))
            for i, (label, hint) in enumerate(options, 1):
                self.write(self._rail(f"{i} {label.ljust(24)} {self.paint(hint, DIM)}".rstrip()))
            while True:
                answer = self._typed(f"Choice [{default + 1}]: ")
                if answer is None:
                    return default
                if answer.isdigit() and 1 <= int(answer) <= len(options):
                    return int(answer) - 1
                self.note(f"A number from 1 to {len(options)}.")
        focus = default
        width = max(len(label) for label, _ in options) + 2
        self.raw("\033[?25l")
        while True:
            rows = [self._mark("ask", ACCENT, question)]
            for i, (label, hint) in enumerate(options):
                if i == focus:
                    row = self.paint(f"{self.g['on']} {label.ljust(width)}", ACCENT) + self.paint(
                        hint, DIM
                    )
                else:
                    row = self.paint(f"{self.g['off']} {label}", DIM)
                rows.append(self._rail(row))
            rows.append(self.paint(f"{self.g['end']}  ↑↓ choose · enter confirm", DIM))
            self.draw(rows)
            key = self._key()
            if key in ("up", "k", "left"):
                focus = (focus - 1) % len(options)
            elif key in ("down", "j", "right", "tab"):
                focus = (focus + 1) % len(options)
            elif key.isdigit() and 1 <= int(key) <= len(options):
                focus = int(key) - 1
                break
            elif key == "enter":
                break
        self.settle(self._settled(question, options[focus][0]))
        return focus

    def hour(self, question: str, default: int) -> int:
        """An hour of the day, 0 to 24; "18h" is understood too."""

        def parse(text: str) -> int | None:
            text = text.lower().removesuffix("h").strip()
            return int(text) if text.isdigit() and 0 <= int(text) <= 24 else None

        if self.assume_yes:
            self._answered(question, str(default))
            return default
        if not self.interactive:
            while True:
                answer = self._typed(f"{question} [{default}]: ")
                if answer is None:
                    return default
                if (value := parse(answer)) is not None:
                    return value
                self.note("An hour from 0 to 24, like 9 or 18.")
        typed, error = "", ""
        self.raw("\033[?25l")
        while True:
            shown = (
                typed + self.paint(self.g["cursor"], ACCENT)
                if typed
                else self.paint(self.g["cursor"], ACCENT) + self.paint(str(default), DIM)
            )
            footer = (
                self.paint(f"{self.g['end']}  {error}", YELLOW)
                if error
                else self.paint(f"{self.g['end']}  enter keeps {default}", DIM)
            )
            self.draw([self._mark("ask", ACCENT, question), self._rail(shown), footer])
            key = self._key()
            if key == "enter":
                value = default if not typed else parse(typed)
                if value is not None:
                    break
                error = "An hour from 0 to 24, like 9 or 18"
            elif key == "backspace":
                typed, error = typed[:-1], ""
            elif len(key) == 1 and (key.isdigit() or key.lower() == "h") and len(typed) < 3:
                typed, error = typed + key, ""
        self.settle(self._settled(question, str(value)))
        return value

    # --- Long steps -------------------------------------------------------------------------------

    def task(
        self, label: str, command: Sequence[str], **options: Any
    ) -> tuple[subprocess.CompletedProcess[str], float]:
        """Run a command behind a spinner, its output to the log; on failure, its last lines on
        screen. The caller says how it went: done() or fail() after."""
        began = time.monotonic()
        result: dict[str, Any] = {}

        def work() -> None:
            try:
                process = subprocess.Popen(  # noqa: S603 - argument lists built by the setup
                    list(command),
                    stdin=options.pop("stdin", subprocess.DEVNULL),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    errors="replace",
                    **options,
                )
            except OSError as error:
                result["done"] = subprocess.CompletedProcess(command, 127, "", str(error))
                return
            result["process"] = process
            stdout, stderr = process.communicate()
            result["done"] = subprocess.CompletedProcess(
                command, process.returncode, stdout, stderr
            )

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        if not self.interactive:
            self.write(self._mark("todo", YELLOW, f"{label}…"))
        frames = self.g["spin"]
        tick = 0
        try:
            self.raw("\033[?25l")
            while worker.is_alive():
                seconds = time.monotonic() - began
                frame = self.paint(frames[tick % len(frames)], ACCENT)
                clock = self.paint(f"{seconds:.0f}s", DIM)
                self.raw(f"\r\033[2K{frame}  {label}…  {clock}")
                tick += 1
                worker.join(0.1)
        except KeyboardInterrupt:
            process = result.get("process")
            if process is not None:
                process.kill()
            raise
        finally:
            self.raw("\r\033[2K\033[?25h")
        done: subprocess.CompletedProcess[str] = result["done"]
        seconds = time.monotonic() - began
        self._log(label, command, done)
        if done.returncode != 0:
            self.fail(label, f"failed after {seconds:.0f}s")
            # The errors last, where the eye lands.
            lines = (done.stdout.strip() + "\n" + done.stderr.strip()).strip().splitlines()
            for row in lines[-TAIL:]:
                self.write(self._rail(self.paint(row, DIM)))
            if self.log is not None:
                self.note(f"Full output: {self.log}")
        return done, seconds

    def _log(
        self, label: str, command: Sequence[str], done: subprocess.CompletedProcess[str]
    ) -> None:
        if self.log is None:
            return
        try:
            self.log.parent.mkdir(parents=True, exist_ok=True)
            with self.log.open("a", encoding="utf-8") as log:
                log.write(
                    f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} {label} (exit {done.returncode})\n"
                )
                log.write(f"$ {' '.join(command)}\n{done.stdout}{done.stderr}")
        except OSError:
            pass

    def handover(self, note: str) -> None:
        """Before a program that talks to the user itself (a sign-in): the terminal is theirs."""
        self.note(note)
        self.raw("\033[?25h")
