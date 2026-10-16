# Helpers shared by the scripts on macOS, where the window, the brain and the game run side by
# side (sourced, not run). macOS has bash 3.2: no mapfile, no ${x,,}, no setsid.

is_mac() {
  [[ "$(uname -s)" == Darwin ]]
}

# The game's database, the window's settings, its environment and its log (tagnan/paths.py).
mac_state_dir() {
  echo "$HOME/Library/Application Support/tagnan"
}

# The window's Python: TAGNAN_MAC_VENV_PYTHON if set (a python already holding PySide6), else
# the environment that scripts/ui-setup creates.
mac_venv_python() {
  echo "${TAGNAN_MAC_VENV_PYTHON:-$(mac_state_dir)/venv/bin/python}"
}

require_mac_venv() {
  local python
  python="$(mac_venv_python)"
  if [[ ! -x "$python" ]]; then
    echo "The window's environment is missing: run scripts/ui-setup first." >&2
    exit 1
  fi
  echo "$python"
}
