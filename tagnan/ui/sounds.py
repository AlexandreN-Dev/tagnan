"""Tagnan's call: the sound he makes when he asks a question of his own accord, to be heard
away from the screen. A few to choose from in his menu, or none.

Played with winsound (Python's own, on Windows), as Dartt's sounds are, and with afplay (the
system's own) on macOS: no Qt Multimedia to install. Asynchronous: a new sound cuts the one
still playing. The files are synthesized by
scripts/make-sounds into assets/sounds.
"""

import logging
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from tagnan.paths import SOUNDS_DIR

logger = logging.getLogger(__name__)

# (key, name in his menu); the key names the file.
CALLS = (
    ("bugle", "Bugle call"),
    ("rapier", "Clashing rapiers"),
    ("bell", "Bell"),
    ("lute", "Lute"),
    ("kalimba", "Kalimba"),
)
SILENT = "silent"
DEFAULT = "bugle"
CHOICES = frozenset([*(key for key, _ in CALLS), SILENT])


AFPLAY = "/usr/bin/afplay"
_playing: list[subprocess.Popen[bytes]] = []  # macOS: the afplay still playing, if any


def play_wav(path: Path) -> None:
    if sys.platform == "darwin":
        play_with_afplay(path)
        return
    if sys.platform != "win32":
        return
    import winsound

    # Asynchronous; NODEFAULT: a missing file stays silent instead of Windows' own beep.
    winsound.PlaySound(
        str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
    )


def play_with_afplay(path: Path) -> None:
    """macOS: afplay in the background, after silencing the call before it; a missing file stays
    silent, as on Windows."""
    while _playing:
        _playing.pop().terminate()
    if path.is_file():
        _playing.append(
            subprocess.Popen(  # noqa: S603 - fixed program, a path of ours
                [AFPLAY, str(path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )


class Sounds:
    def __init__(self, play: Callable[[Path], None] = play_wav) -> None:
        self._play = play

    def play(self, key: str) -> bool:
        """Play a call; False for silence, an unknown key or a sound that would not play."""
        if key == SILENT or key not in CHOICES:
            return False
        try:
            self._play(SOUNDS_DIR / f"{key}.wav")
        except (OSError, RuntimeError) as error:
            logger.warning("could not play a sound: %s", error)
            return False
        return True
