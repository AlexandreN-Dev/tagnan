Tagnan: an ink musketeer who asks questions on whatever one learns (an AWS certification at first, or any subject: the brain draws up its course) on the Windows desktop (window on Windows, brain in WSL) or on macOS (all on the Mac). Architecture and game rules: README.md.

Conventions: talk with the user in French; everything in the repository is in English (code, identifiers, comments, README, script and setup messages, error messages). Tagnan speaks English too: questions, explanations, bubble, menus and terminal quiz. Small atomic commits, Conventional Commits messages. Public repository: https://github.com/AlexandreN-Dev/tagnan (push only when the user asks).

Non-negotiable constraints:
- Claude is called only through the official `claude` CLI, started by `scripts/brain` with the clean environment and isolation flags of `tagnan/brain.py` (never the Anthropic API directly, never the credentials stored in `~/.claude/`).
- The game, the store and the brain use the standard library only: the same code runs in WSL, in the window's Windows Python and on macOS.
- The bash scripts also run on macOS: bash 3.2 (no `mapfile`, `${x,,}`, `setsid`, GNU options). Each script picks its way with `is_mac` (`scripts/_mac.sh`); what the window asks of macOS goes through ctypes in `tagnan/ui/macos.py`, with no dependency.
- Tagnan's layers live in `tagnan/art.py`; the window itself only draws the ink and the drops.

Commands, from the repository root:

- Guided setup (what a new user runs after cloning): `scripts/setup`; `--check` changes nothing, `--yes` takes every default. Steps in `tagnan/setup.py`, terminal interface (rail of steps, arrow keys, spinners, log in `~/.local/state/tagnan/setup.log`) in `tagnan/setup_ui.py`, bash bootstrap (WSL, uv) in `scripts/setup`. `--check` touches nothing and can run at will; the normal mode rewrites the config, the window's pace and the shortcuts and starts Tagnan: not on the user's machine without their consent.
- Development: `uv sync`; Windows side: `scripts/ui-setup` (environment in `%LOCALAPPDATA%\tagnan\venv`; on a Mac, `~/Library/Application Support/tagnan/venv`)
- Checks: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`
- Real test against `claude` (uses a little quota, only on request): `uv run pytest -m live`
- Start Tagnan (detached window, log in `~/.local/state/tagnan/ui.log`): `scripts/tagnan`; in the foreground: `scripts/tagnan-ui`
- Start menu icon: `scripts/install-shortcut`; start with Windows: `--startup`; `--dry-run`, `--remove` (on a Mac: `~/Applications/Tagnan.app` and the LaunchAgent `local.tagnan`, through `scripts/_mac-app`)
- Terminal quiz (WSL database, separate from the window's; on a Mac, the same database): `uv run python -m tagnan.cli`; `-n 5`, `--stats`, `--learn pottery`, `--subject RAG`, `--import batch.json`
- Updates from GitHub: `scripts/update` (by hand), `scripts/update check` / `scripts/update apply` (one line of JSON: what his menu's Update calls through wsl.exe), `scripts/update here [COMMIT]` (local, no network: the commit his folder is at, what changed since the one the window runs; lights his menu's Restart), `scripts/update restart [--setup]` (the window has just quit: start him again). Tests run against throwaway git repositories (`tests/test_update.py`).
- Brain by hand: `scripts/brain generate < request.json`, `scripts/brain explain < request.json`, `echo '{"words": "pottery"}' | scripts/brain plan` (a new course's outline), `scripts/brain check` (one tiny call with the configured model)
- Picture of the window without capturing the screen: `scripts/tagnan-ui --demo question --snapshot <Windows path>`; off screen in WSL: `QT_QPA_PLATFORM=offscreen uv run python -m tagnan.ui --demo question --snapshot build/w.png` (software rendering: no glow); `--demo menu` for his menu. A snapshot never calls the brain.
- Reference sheet (layers rendered by QtSvg): `QT_QPA_PLATFORM=offscreen uv run python -m tagnan.ui.sheet build/sheet.png`
- Animation frame by frame: `QT_QPA_PLATFORM=offscreen uv run python -m tagnan.ui.preview build/frames.png --mood happy --at 0.1 0.3 0.6`
- Window CPU: `scripts/tagnan-ui --measure-cpu 30`
- Tagnan's sounds, synthesized (rewrites `assets/sounds/`, always identically): `scripts/make-sounds`
- The glow (MultiEffect) only shows with GPU rendering: on Windows, not off screen in WSL.
- A locked Windows session freezes Qt rendering: don't trust a capture taken meanwhile.
- No Mac here: the Mac branches are tested from WSL by faking the system (`tests/test_macos.py`: `sys.platform`, a fake `uname`). What only a real Mac shows (windows that stay visible, Dock, click elsewhere, lock, icon) is checked on a colleague's Mac.
