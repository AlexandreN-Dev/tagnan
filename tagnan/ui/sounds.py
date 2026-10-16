"""Tagnan's call: the sound he makes when he asks a question of his own accord, to be heard
away from the screen. A few to choose from in his menu, or none.

Played with winsound (Python's own, on Windows), as Dartt's sounds are: no Qt Multimedia to
install. Asynchronous: a new sound cuts the one still playing. The files are synthesized by
scripts/make-sounds into assets/sounds.
"""

import logging
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


def play_wav(path: Path) -> None:
    if sys.platform != "win32":
        return
    import winsound

    # Asynchronous; NODEFAULT: a missing file stays silent instead of Windows' own beep.
    winsound.PlaySound(
        str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
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
