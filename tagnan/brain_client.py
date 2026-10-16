"""How the window and the terminal quiz reach the brain: directly in WSL, through wsl.exe from
Windows. One JSON request on stdin, one JSON answer on stdout."""

import json
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tagnan.paths import REPO


class BrainError(Exception):
    pass


def decode(data: bytes) -> str:
    """wsl.exe writes its own messages in UTF-16; the brain writes UTF-8."""
    if data[1:2] == b"\x00" or data.count(b"\x00") > len(data) // 4:
        return data.decode("utf-16-le", errors="replace").replace("\x00", "")
    return data.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class BrainClient:
    command: tuple[str, ...]

    @classmethod
    def local(cls, repo: Path = REPO) -> "BrainClient":
        return cls((str(repo / "scripts" / "brain"),))

    @classmethod
    def through_wsl(cls, distro: str, repo: str) -> "BrainClient":
        """From Windows: repo is the repository's path inside WSL, e.g. /home/me/tagnan."""
        return cls(("wsl.exe", "-d", distro, "-e", f"{repo.rstrip('/')}/scripts/brain"))

    def call(self, action: str, request: Mapping[str, Any], timeout: float) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        if sys.platform == "win32":
            # A GUI process starting wsl.exe would flash a console window otherwise.
            extra["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            done = subprocess.run(  # noqa: S603 - fixed argument list, no shell
                [*self.command, action],
                input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
                capture_output=True,
                timeout=timeout,
                check=False,
                **extra,
            )
        except subprocess.TimeoutExpired:
            raise BrainError(f"le cerveau n'a pas répondu en {timeout:.0f} s") from None
        except OSError as error:
            raise BrainError(f"impossible de lancer le cerveau : {error}") from None
        if done.returncode != 0:
            message = decode(done.stderr).strip().splitlines()
            raise BrainError(message[-1] if message else f"le cerveau a échoué ({done.returncode})")
        try:
            answer = json.loads(done.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise BrainError("réponse illisible du cerveau") from None
        if not isinstance(answer, dict):
            raise BrainError("réponse inattendue du cerveau")
        return answer

    def generate(self, request: Mapping[str, Any], timeout: float = 630.0) -> dict[str, Any]:
        return self.call("generate", request, timeout)

    def explain(self, request: Mapping[str, Any], timeout: float = 270.0) -> str:
        return str(self.call("explain", request, timeout).get("text", ""))
