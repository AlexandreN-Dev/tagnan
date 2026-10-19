# Tagnan

A small Prussian-blue ink musketeer who lives in the bottom right corner of your screen and, out of the blue, asks you questions on whatever you are learning: the **AWS Certified AI Practitioner (AIF-C01)** exam to begin with, then another AWS certification, pottery, the French Revolution, anything you tell him. Right answer: he leaps, rapier raised. Wrong answer: he shakes with rage, tells you off ("Zounds!", "Sacrebleu!") and explains why. The more you get right, the higher his rank, from the inkwell to captain.

Questions and explanations are written by Claude, through the Claude Code CLI and your own subscription. Everything else stays on your computer.

## Quick start

You need Windows 10 or 11 with WSL (Ubuntu; otherwise run `wsl --install` in PowerShell) and a Claude subscription (Pro, Max, Team or Enterprise). In an Ubuntu terminal:

```bash
git clone https://github.com/AlexandreN-Dev/tagnan.git ~/tagnan && cd ~/tagnan && scripts/setup
```

The guided setup checks each requirement and installs what is missing, asking first: uv and Claude Code. No Python needed beforehand, on Windows or on a Mac: if there is none, Tagnan gets a Python 3.12 of his own (through uv, pinned and checksum-verified, no admin rights), kept in his folder. It connects your Claude account (a sign-in page opens), asks for the model, your hours and the starting pace, makes one small real call to Claude to check everything works, offers a Start menu icon and starting with Windows, then brings Tagnan in, bottom right of the screen. Arrow keys choose, Enter keeps the value offered.

It is safe to run again, to change your answers or after an update: what is already done is skipped. `scripts/setup --check` reports what is ready without changing anything; `scripts/setup --yes` takes every default.

On his first start he writes his first ten questions (a few minutes), then asks the first one soon after. From then on he asks every 8 to 25 minutes, from 9:00 to 19:00 on weekdays, with a bugle call for each question. Change the pace and the sound in his menu, the hours by running `scripts/setup` again (or in `~/.config/tagnan/config.toml`, see `config.example.toml`).

To start Tagnan later: his Start menu icon, or `scripts/tagnan`.

### On a Mac

You need macOS 14 (Sonoma) or later, and the same Claude subscription. In Terminal:

```bash
git clone https://github.com/AlexandreN-Dev/tagnan.git ~/tagnan && cd ~/tagnan && scripts/setup
```

The same guided setup, without the Windows part: uv, Claude Code, the window's environment (PySide6, in `~/Library/Application Support/tagnan/venv`), your settings, one small real call to Claude, then a "Tagnan" app in `~/Applications` (Launchpad, Spotlight) and, if you like, a start at each sign-in. On a Mac everything runs on the one machine: the window calls the brain directly, and the window and the terminal quiz share one database, in `~/Library/Application Support/tagnan`. Tagnan has no Dock icon: he lives on the desktop and in the menu bar.

What differs from Windows: he holds back only while the screen is locked (not during a presentation), and does not come over a full-screen application; he follows you on every desktop (Spaces). Sounds play through `afplay`, at his volume within the Mac's.

<details>
<summary>The same steps, by hand</summary>

```bash
claude auth login            # Claude Code installed in ~/.local/bin and signed in
scripts/ui-setup             # the window's environment (Windows' Python 3.12, or one uv brings)
cp config.example.toml ~/.config/tagnan/config.toml   # optional
scripts/brain check          # one small real call to Claude
scripts/tagnan               # Tagnan arrives in the bottom right corner
scripts/install-shortcut --startup   # optional: Start menu, and start with Windows
```

To work on the code: `uv sync`, then the checks listed in `CLAUDE.md`.
</details>

### Updating

When a new version is out, "Update" in his menu shows a gold "New": one click and he takes it, starts again and tells you what changed. He looks for one a minute after he starts, then once a day. By hand, in a terminal: `cd ~/tagnan && scripts/update`, then quit him from his menu and start him again. Your progress, questions and settings stay: they live outside the repository. He never updates over changes of your own to his files: then `git pull` it is.

## Living with Tagnan

- **A question**: click the right answer (or the two right ones, then "Confirm"). "Later" puts it off for ten minutes; left unanswered, it goes away after ten minutes with no penalty, and the next one waits ten minutes, or the pace's gap if longer.
- **A mistake**: the bubble says why your choice was wrong, gives the right answer and what to read again (the AWS document, for an AWS exam). "Tell me more" asks Claude for a longer explanation, with an example or a mnemonic. The question comes back the next day, then after 3, 7 and 21 days (Leitner boxes) until you master it.
- **What he asks about**: right-click Tagnan, "Subject…". At the top, what you learn: the courses you learned before, and a field to learn something else, in your own words ("AWS Solutions Architect Associate", "pottery", "the history of Venice"). For a certification he follows its official exam guide; for anything else he draws up a course of four to six chapters, as a teacher would (a minute or two, he says when it's ready). Each course keeps its own questions, reviews and rank: on a new one he starts again from the inkwell, and going back to an old one gives him his rank there. The cross on a course you no longer follow puts it away (not the one learned now): its questions and rank are kept, "Undo" or learning it again brings it back. Below, what within the course: all of it, one domain, or a corner of it in your own words ("RAG", "glazes"). He keeps to it until you tell him otherwise. In the terminal: `--learn pottery`, `--subject RAG`.
- **A dubious question**: "Report" drops it for good, with no points.
- **A break**: right-click Tagnan (or his tray icon), "A break…". Buttons for 30 min, 1 h, 2 h or until tomorrow, and a field for a duration (`1h`, `1h30`, `45 min`) or a time to come back (`15h30`, `16:45`, `3pm`, `noon`). He shows what he understood before you confirm. A bare time still to come is when he comes back (`15h`), a small number of hours is a duration (`1h`), a time already gone means tomorrow; "for" and "until" settle it.
- **The pace**: right-click Tagnan, "How often". "Rarely": 2 or 3 questions a day, whatever the working hours; "Now and then": every 45 to 90 min; "Regularly": every 8 to 25 min, the starting pace; "Often": every 5 to 10 min; "Intensive training": every 3 to 5 min. He says so in his bubble, with the time of the next question, and remembers it.
- **His call**: when he asks a question on his own, he sounds a call, so you hear him away from the screen. Pick one in "Sound": "Bugle call" (the cavalry charge, the default), "Clashing rapiers", "Bell", "Lute", "Kalimba" or "Silent". A click plays the sound and picks it; the menu stays open to hear the others, Esc or a click elsewhere closes it. A question you ask for ("A question now") makes no sound. Under the sounds, "Volume" sets how loud he is (65 % to begin with), gentler in earphones: let go of the slider, or use ← and → on it, and he sounds his call at that volume. It goes on top of the Windows volume (on a Mac, the Mac's).
- **Closing a bubble**: a click anywhere else does it, except for a question, which stays until you answer or choose "Later".
- **Clicking Tagnan**: he winks and splashes (during a break, he tells you until when); three clicks in a row annoy him, six make him sulk. **Drag** him to move him (he remembers his place).
- **His menu**: right-click Tagnan or his tray icon (a left click on the icon shows his progress). At the top, his rank and the points to the next; then a question now (with the time of the next one), progress, subject, pace, sound, a break, update, quit. "How often" and "Sound" open their list beside it; a click on a sound plays it and keeps the list open, to hear the next. Or just type: `break 45`, `until 4pm`, `often`, `bell`, `learn pottery`, `focus RAG`; he shows what he understood and Enter does it. The arrows, Enter, → and ← for the lists, and Esc work throughout.
- He stays hidden during a full-screen application, a presentation or while the session is locked, and so makes no sound either: if Windows locks the session after a few idle minutes, he keeps quiet until you are back.

## Ranks

| Rank | Points | What he gains | At 80 % right answers |
|---|---|---|---|
| Inkwell | 0 | ink in his inkwell, a dipped goose quill | at the start |
| Gascon | 250 | he climbs out of the inkwell | 2 days |
| Cadet | 900 | a felt hat | 1 week |
| Musketeer | 2,000 | the cross and the white plume | 2 and a half weeks |
| Lieutenant | 3,600 | the rapier and the hooked moustache | 4 weeks |
| Captain | 6,000 | the cockaded hat, the royale and the gold | 7 weeks |

The road is long on purpose. A right answer earns 10 points, plus 1 per right answer in a row (up to +5); a mistake costs 8 and resets the streak. The durations assume about a hundred answers a week, the starting pace; faster, the road gets shorter in proportion. At 70 % right answers it takes ten weeks to become Captain, at 60 % more than four months. A rank is only lost well below its threshold. Questions are easy in the inkwell, at exam level after that, hard for the last two ranks; the domains where you make the most mistakes come back more often.

## How it is built

```
Windows                                          WSL (Ubuntu)
┌──────────────────────────────────────┐          ┌──────────────────────────────────┐
│ python -m tagnan.ui (PySide6, QML)   │          │ scripts/brain                    │
│  animated figure, bubble, tray icon  │ wsl.exe  │  claude -p, clean environment    │
│  rhythm, points, ranks, Leitner      ├─────────►│  --json-schema, no tools,        │
│  SQLite %LOCALAPPDATA%\tagnan        │◄─────────┤  no hooks, no MCP servers        │
└──────────────────────────────────────┘   JSON   └──────────────────────────────────┘
```

- **The window** (`tagnan/ui/`) runs on Windows' Python and reads this repository's code through `\\wsl.localhost` (on a Mac, on its own Python next to the brain; what it asks of macOS is in `tagnan/ui/macos.py`). It holds all the state: the SQLite database of questions, answers and reviews, and its settings (its place, pace and call, in `settings.json`), in `%LOCALAPPDATA%\tagnan` (on a Mac, `~/Library/Application Support/tagnan`). The pace chosen in the menu replaces the gaps of the config file.
- **The brain** (`tagnan/brain.py`, `scripts/brain`) runs in WSL (or on the Mac) and has no state: a JSON request on stdin, a JSON answer on stdout. It runs `claude -p` isolated from your own Claude Code setup (allowlisted environment variables, `--setting-sources user`, `--strict-mcp-config`, `disableAllHooks`), with `--tools ""` in an empty folder, and validates the output with `--json-schema`. Questions are written ten at a time, in the background, when fewer than five are left: you never wait for Claude to get a question.
- **The game** (`tagnan/game.py`, `progress.py`, `scheduler.py`, `pause.py`, `store.py`, `model.py`) uses only the standard library and is tested in WSL. Each generated question is checked (domain, task, number of right answers, one explanation per wrong choice) and its choices are shuffled before it is stored. Each question records its language: those written in French in early versions stay in the database but are no longer asked.
- **The sounds** (`assets/sounds/`) are synthesized by `scripts/make-sounds`: standard library, no sound bank, the same loudness for all (−16 LUFS). The window plays them with `winsound` (on a Mac, `afplay`), without Qt Multimedia.
- **The course outline** (a blueprint) gives the domains, their weights, the notions of each task, and how to write good questions on the subject. `exam/aif-c01.toml` comes with Tagnan, from the official exam guide; the course one asks for in his menu is drawn up once by the brain (`scripts/brain plan`) and kept in the database. Every request to the brain carries the whole outline, so the brain stays stateless. The course learned at first is the config's `exam = "…"`.
- **His updates** (`tagnan/update.py`, `scripts/update`) come from GitHub: a fast-forward of this clone, never over changes of your own. The window asks through wsl.exe, as it asks the brain (`tagnan/ui/updater.py`), then quits, and `scripts/update restart` starts him again once he is gone, making his window's environment again first when its pinned versions changed.
- **Tagnan** (`tagnan/art.py`) is drawn flat and cut into layers: the window draws the rippling ink and the drops, and animates the SVG layers (eyes, mouth, hat, plumes, rapier…) with a rig (`tagnan/ui/animation/`): springs, blinks, eyes that follow the mouse, random gestures, taps.

## Usage limits

A batch of ten questions is one Opus 5.5 call at max effort, which takes a few minutes; twenty questions a day is two or three calls, plus the "Tell me more" ones. In "Intensive training" it is up to fifteen questions an hour, so a batch about every forty minutes and some fifteen calls a day: enough to weigh on your subscription's usage limits (choose Sonnet in `scripts/setup` to go lighter). Everything goes through your Claude subscription, never through an API key.
