"""Where Tagnan keeps its files, in WSL and on Windows."""

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXAMS_DIR = REPO / "exam"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
SOUNDS_DIR = REPO / "assets" / "sounds"  # written by scripts/make-sounds


def state_dir() -> Path:
    """The game's database and the window's settings: %LOCALAPPDATA%\\tagnan on Windows,
    ~/.local/state/tagnan elsewhere."""
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        return (Path(local) if local else Path.home() / "AppData" / "Local") / "tagnan"
    state = os.environ.get("XDG_STATE_HOME")
    return (Path(state) if state else Path.home() / ".local" / "state") / "tagnan"


def config_file() -> Path:
    """The optional config file, in WSL (the launcher hands its Windows path to the window)."""
    config = os.environ.get("XDG_CONFIG_HOME")
    return (Path(config) if config else Path.home() / ".config") / "tagnan" / "config.toml"
