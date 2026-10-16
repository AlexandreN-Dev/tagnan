Tagnan: an ink musketeer who asks AWS certification questions on the Windows desktop. Architecture and game rules: README.md.

Conventions: talk with the user in French; everything in the repository is in English (code, identifiers, comments, README, script and setup messages, error messages). Tagnan speaks English too: questions, explanations, bubble, menus and terminal quiz. Small atomic commits, Conventional Commits messages. Public repository: https://github.com/AlexandreN-Dev/tagnan (push only when the user asks).

Non-negotiable constraints:
- Claude is called only through the official `claude` CLI, started by `scripts/brain` with the clean environment and isolation flags of `tagnan/brain.py` (never the Anthropic API directly, never the credentials stored in `~/.claude/`).
- The game, the store and the brain use the standard library only: the same code runs in WSL and in the window's Windows Python.
- Tagnan's layers live in `tagnan/art.py`; the window itself only draws the ink and the drops.

Commands, from the repository root:

- Guided setup (what a new user runs after cloning): `scripts/setup`; `--check` changes nothing, `--yes` takes every default. Code in `tagnan/setup.py`, bash bootstrap (WSL, uv) in `scripts/setup`. `--check` touches nothing and can run at will; the normal mode rewrites the config, the window's pace and the shortcuts and starts Tagnan: not on the user's machine without their consent.
- Development: `uv sync`; Windows side: `scripts/ui-setup` (environment in `%LOCALAPPDATA%\tagnan\venv`)
- Checks: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`
- Real test against `claude` (uses a little quota, only on request): `uv run pytest -m live`
- Start Tagnan (detached window, log in `~/.local/state/tagnan/ui.log`): `scripts/tagnan`; in the foreground: `scripts/tagnan-ui`
- Start menu icon: `scripts/install-shortcut`; start with Windows: `--startup`; `--dry-run`, `--remove`
- Terminal quiz (WSL database, separate from the window's): `uv run python -m tagnan.cli`; `-n 5`, `--stats`, `--import batch.json`
- Brain by hand: `scripts/brain generate < request.json`, `scripts/brain explain < request.json`, `scripts/brain check` (one tiny call with the configured model)
- Picture of the window without capturing the screen: `scripts/tagnan-ui --demo question --snapshot <Windows path>`; off screen in WSL: `QT_QPA_PLATFORM=offscreen uv run python -m tagnan.ui --demo question --snapshot build/w.png` (software rendering: no glow)
- Reference sheet (layers rendered by QtSvg): `QT_QPA_PLATFORM=offscreen uv run python -m tagnan.ui.sheet build/sheet.png`
- Animation frame by frame: `QT_QPA_PLATFORM=offscreen uv run python -m tagnan.ui.preview build/frames.png --mood happy --at 0.1 0.3 0.6`
- Window CPU: `scripts/tagnan-ui --measure-cpu 30`
- Tagnan's sounds, synthesized (rewrites `assets/sounds/`, always identically): `scripts/make-sounds`
- The glow (MultiEffect) only shows with GPU rendering: on Windows, not off screen in WSL.
- A locked Windows session freezes Qt rendering: don't trust a capture taken meanwhile.
