"""Tagnan's call: the sound he makes when he asks a question of his own accord, to be heard
away from the screen. A few to choose from in his menu, or none.

Played with winsound (Python's own, on Windows), as Dartt's sounds are, and with afplay (the
system's own) on macOS: no Qt Multimedia to install. Asynchronous: a new sound cuts the one
still playing. The files are synthesized by
scripts/make-sounds into assets/sounds.

His volume, chosen in his menu, lest a call ring too loud in one's earphones: afplay takes it
as is; winsound has none, so he plays a softer copy of the file, written once in his state
folder.
"""

import array
import contextlib
import logging
import subprocess
import sys
import wave
from collections.abc import Callable
from pathlib import Path

from tagnan.paths import SOUNDS_DIR, state_dir

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

# In percent, by steps of 5; 0 is silence.
DEFAULT_VOLUME = 65
VOLUME_STEP = 5


def volume(value: object) -> int | None:
    """A volume to keep, to the nearest step; None for what is not one."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    stepped = round(value / VOLUME_STEP) * VOLUME_STEP
    return int(max(0, min(100, stepped)))


def gain(percent: int) -> float:
    """What the samples are multiplied by: squared, as the ear hears, so that the middle of
    his slider sounds about half as loud (65 %: -7.5 dB)."""
    return (percent / 100) ** 2


AFPLAY = "/usr/bin/afplay"
_playing: list[subprocess.Popen[bytes]] = []  # macOS: the afplay still playing, if any


def play_wav(path: Path, percent: int = 100) -> None:
    if sys.platform == "darwin":
        play_with_afplay(path, percent)
        return
    if sys.platform != "win32":
        return
    import winsound

    if percent < 100 and path.is_file():
        path = softer(path, percent, state_dir() / "sounds")
    # Asynchronous; NODEFAULT: a missing file stays silent instead of Windows' own beep.
    winsound.PlaySound(
        str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
    )


def softer(path: Path, percent: int, folder: Path) -> Path:
    """A copy of a 16-bit WAV file at that volume, in `folder`: written once, again when the
    original is newer (an update), and only the latest volume of each sound is kept."""
    out = folder / f"{path.stem}-{percent}.wav"
    if out.is_file() and out.stat().st_mtime >= path.stat().st_mtime:
        return out
    with wave.open(str(path), "rb") as source:
        params = source.getparams()
        frames = source.readframes(params.nframes)
    if params.sampwidth != 2:
        return path  # not one of ours: played as it is
    samples = array.array("h", frames)
    if sys.byteorder == "big":
        samples.byteswap()  # WAV is little-endian
    factor = gain(percent)
    samples = array.array("h", (round(x * factor) for x in samples))
    if sys.byteorder == "big":
        samples.byteswap()
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{path.stem}-*.wav"):
        with contextlib.suppress(OSError):  # still playing, on Windows: next time
            old.unlink()
    partial = out.with_suffix(".part")
    with wave.open(str(partial), "wb") as copy:
        copy.setparams(params)
        copy.writeframes(samples.tobytes())
    partial.replace(out)
    return out


def play_with_afplay(path: Path, percent: int = 100) -> None:
    """macOS: afplay in the background, after silencing the call before it; a missing file stays
    silent, as on Windows."""
    while _playing:
        _playing.pop().terminate()
    if path.is_file():
        _playing.append(
            subprocess.Popen(  # noqa: S603 - fixed program, a path of ours
                [AFPLAY, "-v", f"{gain(percent):.4f}", str(path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )


class Sounds:
    def __init__(self, play: Callable[[Path, int], None] = play_wav) -> None:
        self._play = play

    def play(self, key: str, percent: int = 100) -> bool:
        """Play a call at a volume; False for silence, an unknown key or a sound that would not
        play."""
        if key == SILENT or key not in CHOICES or percent <= 0:
            return False
        try:
            self._play(SOUNDS_DIR / f"{key}.wav", percent)
        except (OSError, RuntimeError, EOFError, wave.Error) as error:
            logger.warning("could not play a sound: %s", error)
            return False
        return True
