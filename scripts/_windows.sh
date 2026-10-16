# Helpers shared by the scripts that drive the Windows side from WSL (sourced, not run).

windows_env() {
  # From /mnt/c so cmd.exe does not complain about a UNC working directory.
  (cd /mnt/c && cmd.exe /c "echo %$1%" 2>/dev/null) | tr -d '\r'
}

windows_localappdata() {
  windows_env LOCALAPPDATA
}

windows_venv_dir() {
  wslpath -u "$(windows_localappdata)\\tagnan\\venv"
}

# The window's Python: TAGNAN_WIN_VENV_PYTHON if set (a python.exe already holding PySide6),
# else the environment that scripts/ui-setup creates.
windows_venv_python() {
  if [[ -n "${TAGNAN_WIN_VENV_PYTHON:-}" ]]; then
    echo "$TAGNAN_WIN_VENV_PYTHON"
  else
    echo "$(windows_venv_dir)/Scripts/python.exe"
  fi
}

# Python used to create the environment: TAGNAN_WIN_PYTHON if set, else the per-user install,
# else the py launcher's 3.12 (installed for all users, say). The per-user path when none is.
windows_base_python() {
  if [[ -n "${TAGNAN_WIN_PYTHON:-}" ]]; then
    echo "$TAGNAN_WIN_PYTHON"
    return
  fi
  local user found
  user="$(wslpath -u "$(windows_localappdata)\\Programs\\Python\\Python312\\python.exe")"
  if [[ ! -x "$user" ]]; then
    found="$( (cd /mnt/c && py.exe -3.12 -c "import sys; print(sys.executable)") 2>/dev/null \
      | tr -d '\r')" || true
    if [[ -n "$found" ]]; then
      user="$(wslpath -u "$found")"
    fi
  fi
  echo "$user"
}

# uv for Windows, pinned and checked, for a machine without Python: it brings a Python 3.12 of
# Tagnan's own (%LOCALAPPDATA%\tagnan\python), with no admin rights, no Store, no script run.
WINDOWS_UV_VERSION="0.13.0"
WINDOWS_UV_SHA256="088962f9e7b7bd9ea740c04c650b2a21c8928c345bd99ac24350dc924dba656c"

windows_uv() {
  local dir zip
  dir="$(wslpath -u "$(windows_localappdata)\\tagnan\\uv")"
  if [[ ! -x "$dir/uv.exe" ]]; then
    mkdir -p "$dir"
    zip="$dir/uv.zip"
    curl -fsSL -o "$zip" \
      "https://github.com/astral-sh/uv/releases/download/$WINDOWS_UV_VERSION/uv-x86_64-pc-windows-msvc.zip"
    if ! echo "$WINDOWS_UV_SHA256  $zip" | sha256sum --check --status; then
      rm -f "$zip"
      echo "uv for Windows: unexpected checksum, nothing installed." >&2
      return 1
    fi
    # Unzipped by uv's own Python in WSL: unzip is not always there.
    uv run --quiet --no-project --python 3.12 python -m zipfile -e "$zip" "$dir"
    rm -f "$zip"
  fi
  echo "$dir/uv.exe"
}

require_windows_venv() {
  local python
  python="$(windows_venv_python)"
  if [[ ! -x "$python" ]]; then
    echo "No Windows environment: run scripts/setup (or scripts/ui-setup) first." >&2
    exit 1
  fi
  echo "$python"
}

# Arguments that tell the window where the brain and the config live, from Windows' side.
window_arguments() {
  local repo="$1"
  local config="${XDG_CONFIG_HOME:-$HOME/.config}/tagnan/config.toml"
  printf '%s\n' --distro "${WSL_DISTRO_NAME:?run this script from WSL}" --repo "$repo" \
    --config "$(wslpath -w "$config")"
}
