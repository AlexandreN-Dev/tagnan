"""Tagnan on macOS, checked from WSL: the system is faked (sys.platform, uname), the Mac's own
calls are replaced, and what is left is how each piece chooses its way."""

import os
import platform
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

from tagnan import paths, setup
from tagnan.paths import REPO, SOUNDS_DIR
from tagnan.ui import desktop, macos, sounds
from tests.test_setup import terminal


@pytest.fixture
def mac(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """sys.platform says macOS; HOME is a fresh folder."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_state_lives_in_application_support(mac: Path) -> None:
    assert paths.state_dir() == mac / "Library" / "Application Support" / "tagnan"
    assert setup.mac_window_python() == paths.state_dir() / "venv" / "bin" / "python"


def test_the_desktop_asks_macos(mac: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos, "screen_locked", lambda: True)
    monkeypatch.setattr(macos, "mouse_down", lambda: True)
    assert desktop.busy() is True
    assert desktop.mouse_down() is True


def test_the_mac_calls_fail_quietly_elsewhere() -> None:
    """Off a Mac the libraries are missing: welcome, no click, the Dock and Spaces left alone."""
    for cached in (macos._graphics, macos._foundation, macos._objc):
        cached.cache_clear()
    assert macos.mouse_down() is False
    assert macos.screen_locked() is False
    macos.hide_from_dock()
    macos.join_all_spaces(1)


def test_a_call_plays_with_afplay_and_cuts_the_one_before(
    mac: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "afplay"
    fake.write_text("#!/bin/sh\nexec sleep 30\n")
    fake.chmod(0o755)
    monkeypatch.setattr(sounds, "AFPLAY", str(fake))
    sounds.play_wav(SOUNDS_DIR / "bugle.wav")
    first = sounds._playing[0]
    assert first.args == [str(fake), str(SOUNDS_DIR / "bugle.wav")]
    sounds.play_wav(SOUNDS_DIR / "bell.wav")
    assert first.wait(5) != 0  # cut
    second = sounds._playing[0]
    assert second.args == [str(fake), str(SOUNDS_DIR / "bell.wav")]
    sounds.play_wav(tmp_path / "missing.wav")  # silence, and the bell is cut too
    assert second.wait(5) != 0
    assert sounds._playing == []


def test_macos_14_or_later_runs_the_window() -> None:
    assert setup.macos_supported("14.0")
    assert setup.macos_supported("15.3.1")
    assert setup.macos_supported("26")
    assert not setup.macos_supported("13.6")
    assert setup.macos_supported("")  # unreadable: let through


def test_an_old_mac_is_told_before_anything(mac: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "mac_ver", lambda: ("13.6", ("", "", ""), ""))
    term, _ = terminal()
    with pytest.raises(setup.SetupError, match="Sonoma"):
        setup.Setup(term, check=True, mac=True).prerequisites()


def test_on_a_mac_the_brain_is_tried_as_an_app_would_call_it(
    mac: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SECRET_TOKEN", "x")
    term, _ = terminal()
    mac_setup = setup.Setup(term, check=True, mac=True)
    command, options = mac_setup.brain_call()
    assert command == [str(REPO / "scripts" / "brain"), "check"]
    assert options["env"]["PATH"] == setup.MAC_APP_PATH
    assert options["env"]["HOME"] == str(mac)
    assert "SECRET_TOKEN" not in options["env"]
    assert mac_setup.window_settings() == paths.state_dir() / "settings.json"
    assert mac_setup.log() == paths.state_dir() / "ui.log"


def test_on_a_mac_the_setup_skips_windows(mac: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    term, _ = terminal()
    mac_setup = setup.Setup(term, check=True, mac=True)
    done: list[str] = []
    for step in ("prerequisites", "claude", "windows_python", "window", "settings", "trial"):
        monkeypatch.setattr(mac_setup, step, lambda step=step: done.append(step))
    assert mac_setup.all() == 0
    assert "windows_python" not in done
    assert done[0] == "prerequisites"


@pytest.fixture
def mac_shell(tmp_path: Path) -> dict[str, str]:
    """An environment where uname says Darwin, with a home of its own and a window's Python."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uname = bin_dir / "uname"
    uname.write_text("#!/bin/sh\necho Darwin\n")
    uname.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(home),
        "TAGNAN_MAC_VENV_PYTHON": sys.executable,
        "QT_QPA_PLATFORM": "offscreen",
    }


def shortcut(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(REPO / "scripts" / "install-shortcut"), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_on_a_mac_the_shortcut_is_an_app_and_a_launch_agent(mac_shell: dict[str, str]) -> None:
    home = Path(mac_shell["HOME"])
    app = home / "Applications" / "Tagnan.app"
    agent = home / "Library" / "LaunchAgents" / "local.tagnan.plist"
    dry = shortcut(mac_shell, "--startup", "--dry-run")
    assert dry.returncode == 0, dry.stderr
    assert not app.exists()

    done = shortcut(mac_shell, "--startup")
    assert done.returncode == 0, done.stderr
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleExecutable"] == "Tagnan"
    assert info["LSUIElement"] is True
    program = (app / "Contents" / "MacOS" / "Tagnan").read_text()
    assert str(REPO / "scripts" / "tagnan-ui") in program
    assert os.access(app / "Contents" / "MacOS" / "Tagnan", os.X_OK)
    assert plistlib.loads(agent.read_bytes())["ProgramArguments"] == [
        "/usr/bin/open",
        "-g",
        str(app),
    ]

    gone = shortcut(mac_shell, "--remove")
    assert gone.returncode == 0, gone.stderr
    assert not app.exists()
    assert not agent.exists()


def test_on_a_mac_the_window_starts_with_its_own_python(
    mac_shell: dict[str, str], tmp_path: Path
) -> None:
    started = subprocess.run(
        [str(REPO / "scripts" / "tagnan-ui"), "--help"],
        env=mac_shell,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert started.returncode == 0, started.stderr
    assert "--distro" in started.stdout  # tagnan.ui's own help: no wsl.exe on the way
    missing = {**mac_shell, "TAGNAN_MAC_VENV_PYTHON": str(tmp_path / "none")}
    refused = subprocess.run(
        [str(REPO / "scripts" / "tagnan-ui")],
        env=missing,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert refused.returncode == 1
    assert "scripts/ui-setup" in refused.stderr
