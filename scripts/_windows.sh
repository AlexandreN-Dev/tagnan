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

# Python used to create the environment: the per-user install, unless TAGNAN_WIN_PYTHON says
# otherwise.
windows_base_python() {
  if [[ -n "${TAGNAN_WIN_PYTHON:-}" ]]; then
    echo "$TAGNAN_WIN_PYTHON"
  else
    wslpath -u "$(windows_localappdata)\\Programs\\Python\\Python312\\python.exe"
  fi
}

require_windows_venv() {
  local python
  python="$(windows_venv_python)"
  if [[ ! -x "$python" ]]; then
    echo "Environnement Windows absent : lance d'abord scripts/ui-setup." >&2
    exit 1
  fi
  echo "$python"
}

# Arguments that tell the window where the brain and the config live, from Windows' side.
window_arguments() {
  local repo="$1"
  local config="${XDG_CONFIG_HOME:-$HOME/.config}/tagnan/config.toml"
  printf '%s\n' --distro "${WSL_DISTRO_NAME:?lance ce script depuis WSL}" --repo "$repo" \
    --config "$(wslpath -w "$config")"
}
