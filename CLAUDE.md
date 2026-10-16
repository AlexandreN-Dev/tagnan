Tagnan : un mousquetaire d'encre qui pose des questions de certification AWS sur le bureau Windows. Architecture et règles du jeu : README.md.

Conventions (comme Dartt) : échanges en français ; code, identifiants et commentaires en anglais ; textes de l'interface en français. Petits commits atomiques, messages en anglais au format Conventional Commits. Dépôt git 100 % local.

Contraintes non négociables :
- Claude n'est appelé que par le CLI officiel `claude`, lancé par `scripts/brain` avec l'environnement propre et les drapeaux d'isolation de `tagnan/brain.py` (jamais d'API Anthropic directe, jamais les identifiants rangés dans `~/.claude/`).
- Le jeu, la base et le cerveau n'utilisent que la bibliothèque standard : le même code tourne dans WSL et dans le Python Windows de la fenêtre.
- Les calques de Tagnan sont dans `tagnan/art.py` ; la fenêtre ne dessine elle-même que l'encre, les bras et les gouttes.

Commandes, depuis la racine du dépôt :

- Installation : `uv sync` ; côté Windows : `scripts/ui-setup` (environnement dans `%LOCALAPPDATA%\tagnan\venv`)
- Vérifications : `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`
- Test réel contre `claude` (consomme un peu de quota, seulement à la demande) : `uv run pytest -m live`
- Démarrer Tagnan (fenêtre détachée, journal dans `~/.local/state/tagnan/ui.log`) : `scripts/tagnan` ; au premier plan : `scripts/tagnan-ui`
- Icône du menu Démarrer : `scripts/install-shortcut` ; démarrage avec Windows : `--startup` ; `--dry-run`, `--remove`
- Quiz en terminal (base WSL, distincte de celle de la fenêtre) : `uv run python -m tagnan.cli` ; `-n 5`, `--stats`, `--import lot.json`
- Cerveau à la main : `scripts/brain generate < requete.json`, `scripts/brain explain < requete.json`
- Image de la fenêtre sans capturer l'écran : `scripts/tagnan-ui --demo question --snapshot <chemin Windows>` ; hors écran dans WSL : `QT_QPA_PLATFORM=offscreen uv run python -m tagnan.ui --demo question --snapshot build/w.png` (rendu logiciel : pas de halo)
- Planche de référence (calques rendus par QtSvg) : `QT_QPA_PLATFORM=offscreen uv run python -m tagnan.ui.sheet build/sheet.png`
- Animation image par image : `QT_QPA_PLATFORM=offscreen uv run python -m tagnan.ui.preview build/frames.png --mood happy --at 0.1 0.3 0.6`
- CPU de la fenêtre : `scripts/tagnan-ui --measure-cpu 30`
- Le halo (MultiEffect) ne se voit qu'avec un rendu GPU : sur Windows, pas hors écran dans WSL.
- Une session Windows verrouillée fige le rendu Qt : ne pas se fier à une capture prise pendant ce temps.
