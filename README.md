# Tagnan

Un petit mousquetaire d'encre bleu de Prusse qui vit en bas à droite de l'écran et te pose, à l'improviste, des questions pour préparer la certification **AWS Certified AI Practitioner (AIF-C01)**. Bonne réponse : il bondit, rapière levée. Mauvaise : il tremble de rage, t'engueule (« Zounds! », « Sacrebleu! ») et t'explique pourquoi. Plus tu enchaînes, plus il gagne en grade, de l'encrier au capitaine.

Tagnan parle anglais, la langue de l'examen : questions, explications, bulle et menus. Les questions et les explications sont écrites par Claude, à travers le CLI Claude Code et ton propre abonnement. Tout le reste est local.

## Démarrage rapide

Il faut Windows 10 ou 11 avec WSL (Ubuntu ; sinon `wsl --install` dans PowerShell) et un abonnement Claude (Pro, Max, Team ou Enterprise). Dans un terminal Ubuntu :

```bash
git clone <url du dépôt> ~/tagnan && cd ~/tagnan && scripts/setup
```

L'installation guidée vérifie chaque prérequis et installe ce qui manque, en demandant d'abord : uv, Claude Code, le Python 3.12 de Windows (par winget, sans droits admin) et l'environnement de la fenêtre. Elle connecte ton compte Claude (une page de connexion s'ouvre), te demande le modèle, tes heures et l'allure de départ, fait un vrai petit appel à Claude pour vérifier le tout, propose une icône au menu Démarrer et le démarrage avec Windows, puis fait venir Tagnan. Entrée garde la valeur proposée entre crochets.

Elle se relance sans risque, pour changer ses réponses ou après une mise à jour : ce qui est déjà fait est sauté. `scripts/setup --check` dit ce qui est prêt sans rien changer ; `scripts/setup --yes` prend toutes les valeurs par défaut.

Au premier lancement, il écrit ses dix premières questions (quelques minutes), puis pose la première peu après. Ensuite il demande toutes les 8 à 25 minutes, de 9 h à 19 h en semaine, et sonne du clairon à chaque question. L'allure et le son se changent dans son menu, les heures en relançant `scripts/setup` (ou dans `~/.config/tagnan/config.toml`, voir `config.example.toml`).

Pour relancer Tagnan plus tard : son icône du menu Démarrer, ou `scripts/tagnan`.

<details>
<summary>Les mêmes étapes, à la main</summary>

```bash
claude auth login            # Claude Code installé dans ~/.local/bin et connecté
scripts/ui-setup             # l'environnement de la fenêtre, côté Windows (Python 3.12 Windows requis)
cp config.example.toml ~/.config/tagnan/config.toml   # facultatif
scripts/brain check          # un petit appel réel à Claude
scripts/tagnan               # Tagnan arrive en bas à droite de l'écran
scripts/install-shortcut --startup   # facultatif : menu Démarrer et démarrage avec Windows
```

Pour développer : `uv sync`, puis les vérifications de `CLAUDE.md`.
</details>

## Avec Tagnan

- **Une question** : clique la bonne réponse (ou les deux bonnes, puis « Confirm »). « Later » la repousse de dix minutes ; laissée sans réponse, elle s'en va au bout de dix minutes, sans pénalité, et la suivante attend dix minutes, ou l'intervalle de l'allure s'il est plus long.
- **Une erreur** : la bulle dit pourquoi ton choix ne convenait pas, donne la bonne réponse et le document AWS à relire. « Tell me more » demande à Claude une explication plus longue, avec un exemple ou un moyen mnémotechnique. La question reviendra le lendemain, puis à 3, 7 et 21 jours (boîtes de Leitner) tant que tu ne la maîtrises pas.
- **Une question douteuse** : « Report » l'écarte pour de bon, sans points.
- **Une pause** : clic droit sur Tagnan (ou icône de notification), « A break… ». Des boutons pour 30 min, 1 h, 2 h ou jusqu'à demain, et un champ où dire une durée (`1h`, `1h30`, `45 min`) ou une heure de rendez-vous (`15h30`, `16:45`, `3pm`, `noon`). Il affiche ce qu'il a compris avant que tu valides. Une heure seule encore à venir est une heure de retour (`15h`), un petit nombre d'heures une durée (`1h`), une heure passée vise le lendemain ; « for » / « pendant » et « until » / « jusqu'à » tranchent.
- **L'allure** : clic droit sur Tagnan, « How often ». « Rarely » : 2 ou 3 questions par jour, quelles que soient les heures de travail ; « Now and then » : toutes les 45 à 90 min ; « Regularly » : toutes les 8 à 25 min, l'allure de départ ; « Often » : toutes les 5 à 10 min ; « Intensive training » : toutes les 3 à 5 min. Il le dit dans sa bulle, avec l'heure de la question suivante, et s'en souvient.
- **Son appel** : quand il pose une question de lui-même, il sonne, pour qu'on l'entende loin de l'écran. Au choix dans « Sound » : « Bugle call » (la charge de cavalerie, par défaut), « Clashing rapiers », « Bell », « Lute », « Kalimba » ou « Silent ». Un clic joue le son et le choisit ; le menu reste ouvert pour écouter les autres, Échap ou un clic ailleurs le ferme. Une question demandée (« A question now ») ne sonne pas. Le volume est celui de Python dans le mélangeur de volume de Windows.
- **Fermer une bulle** : un clic n'importe où ailleurs suffit, sauf pour une question, qui reste jusqu'à ta réponse ou « Later ».
- **Clic sur Tagnan** : il cligne de l'œil et éclabousse (pendant une pause, il te dit jusqu'à quand) ; trois clics de suite l'agacent, six le font bouder. **Glisser** le déplace (il retient sa place). **Clic droit** ou icône de la zone de notification : une question maintenant, la progression, l'allure, le son, une pause, quitter.
- Il ne se montre pas pendant une application en plein écran, une présentation ou quand la session est verrouillée, et donc ne sonne pas non plus : si Windows verrouille la session après quelques minutes sans toi, il se tait jusqu'à ton retour.

## Les grades

| Grade | Points | Ce qu'il gagne | À 80 % de bonnes réponses |
|---|---|---|---|
| Inkwell | 0 | de l'encre dans son encrier, une plume d'oie trempée | au départ |
| Gascon | 250 | il s'échappe de l'encrier | 2 jours |
| Cadet | 900 | un feutre | 1 semaine |
| Musketeer | 2 000 | la croix et la plume blanche | 2 semaines et demie |
| Lieutenant | 3 600 | la rapière et la moustache en croc | 4 semaines |
| Captain | 6 000 | le chapeau à cocarde, la royale et l'or | 7 semaines |

La route est longue exprès. Une bonne réponse rapporte 10 points, plus 1 par réponse juste d'affilée (jusqu'à +5) ; une erreur en coûte 8 et remet la série à zéro. Les durées supposent une centaine de réponses par semaine, l'allure de départ ; plus vite, la route raccourcit d'autant : à 70 % de bonnes réponses, il faut dix semaines pour devenir Captain, à 60 % plus de quatre mois. Un grade ne se perd que bien en dessous de son seuil. Les questions sont faciles dans l'encrier, au niveau de l'examen ensuite, difficiles pour les deux derniers grades ; les domaines où tu te trompes le plus reviennent plus souvent.

## Comment c'est fait

```
Windows                                          WSL (Ubuntu)
┌──────────────────────────────────────┐          ┌──────────────────────────────────┐
│ python -m tagnan.ui (PySide6, QML)   │          │ scripts/brain                    │
│  figure animée, bulle, notification  │ wsl.exe  │  claude -p, environnement propre │
│  rythme, points, grades, Leitner     ├─────────►│  --json-schema, aucun outil,     │
│  SQLite %LOCALAPPDATA%\tagnan        │◄─────────┤  aucun hook ni serveur MCP       │
└──────────────────────────────────────┘   JSON   └──────────────────────────────────┘
```

- **La fenêtre** (`tagnan/ui/`) tourne avec le Python Windows et lit le code de ce dépôt par `\\wsl.localhost`. Elle porte tout l'état : la base SQLite des questions, des réponses et des révisions, et ses réglages (sa place, son allure, son appel, dans `settings.json`), dans `%LOCALAPPDATA%\tagnan`. L'allure choisie au menu remplace les intervalles du fichier de configuration.
- **Le cerveau** (`tagnan/brain.py`, `scripts/brain`) tourne dans WSL et n'a aucun état : une requête JSON sur l'entrée, une réponse JSON sur la sortie. Il lance `claude -p` comme le relais de Dartt (variables d'environnement en liste blanche, `--setting-sources user`, `--strict-mcp-config`, `disableAllHooks`), avec `--tools ""` et un dossier vide, et valide la sortie par `--json-schema`. Les questions sont écrites par lots de dix, en tâche de fond, quand il en reste moins de cinq : on n'attend jamais Claude pour une question.
- **Le jeu** (`tagnan/game.py`, `progress.py`, `scheduler.py`, `pause.py`, `store.py`, `model.py`) n'utilise que la bibliothèque standard, testé dans WSL. Chaque question générée est vérifiée (domaine, tâche, nombre de bonnes réponses, une explication par mauvais choix) et ses choix sont mélangés avant d'être gardés. Chaque question porte sa langue : celles écrites en français avant le passage à l'anglais restent en base mais ne sont plus posées.
- **Les sons** (`assets/sounds/`) sont synthétisés par `scripts/make-sounds`, comme ceux de Dartt : bibliothèque standard, aucune banque de sons, même volume perçu pour tous (−16 LUFS). La fenêtre les joue avec `winsound`, sans Qt Multimedia.
- **Le référentiel** de l'examen (`exam/aif-c01.toml`) donne les cinq domaines, leurs poids et les notions de chaque tâche, d'après le guide d'examen officiel. Pour un autre examen, un autre fichier et `exam = "…"` dans la config.
- **Tagnan** (`tagnan/art.py`) est dessiné à plat, dans la direction artistique de Dartt, et découpé en calques : la fenêtre dessine l'encre qui ondule (la formule de Dartt) et les gouttes, et anime les calques SVG (yeux, bouche, chapeau, plumes, rapière…) au rythme d'un rig repris de celui de Dartt (`tagnan/ui/animation/`) : ressorts, clignements, regard qui suit la souris, gestes au hasard, tapes.

## Quota

Un lot de dix questions coûte un appel Opus 5.5 en effort max, qui prend quelques minutes ; une vingtaine de questions par jour, c'est deux ou trois appels, plus les « Tell me more ». En « Intensive training », c'est jusqu'à quinze questions par heure, donc un lot toutes les quarante minutes environ et une quinzaine d'appels par journée : de quoi peser sur les limites d'usage de l'abonnement. Le tout passe par ton abonnement Claude, jamais par une clé d'API.
