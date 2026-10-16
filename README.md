# Tagnan

Un petit mousquetaire d'encre bleu de Prusse qui vit en bas à droite de l'écran et te pose, à l'improviste, des questions pour préparer la certification **AWS Certified AI Practitioner (AIF-C01)**. Bonne réponse : il bondit, rapière levée. Mauvaise : il tremble de rage, t'engueule (« Mordieu ! ») et t'explique pourquoi. Plus tu enchaînes, plus il gagne en grade, de l'encrier au capitaine.

Les questions et les explications sont écrites par Claude, à travers le CLI Claude Code et ton propre abonnement. Tout le reste est local.

## Démarrage rapide

Depuis WSL, à la racine du dépôt :

```bash
uv sync                      # l'environnement de développement (WSL)
scripts/ui-setup             # une fois : l'environnement de la fenêtre, côté Windows
scripts/tagnan               # Tagnan arrive en bas à droite de l'écran
scripts/install-shortcut --startup   # facultatif : une icône « Tagnan » au menu Démarrer, et au démarrage de Windows
```

Au premier lancement, il écrit ses dix premières questions (une minute environ), puis pose la première peu après. Ensuite il demande toutes les 8 à 25 minutes, de 9 h à 19 h en semaine (réglable, voir `config.example.toml`).

Il faut : Claude Code installé et connecté dans WSL (`~/.local/bin/claude`), uv, et Python 3.12 côté Windows (le même que pour Dartt).

## Avec Tagnan

- **Une question** : clique la bonne réponse (ou les deux bonnes, puis « Valider »). « Plus tard » la repousse de dix minutes ; laissée sans réponse, elle s'en va au bout de dix minutes, sans pénalité.
- **Une erreur** : la bulle dit pourquoi ton choix ne convenait pas, donne la bonne réponse et le document AWS à relire. « Explique-moi plus » demande à Claude une explication plus longue, avec un exemple ou un moyen mnémotechnique. La question reviendra le lendemain, puis à 3, 7 et 21 jours (boîtes de Leitner) tant que tu ne la maîtrises pas.
- **Une question douteuse** : « Signaler » l'écarte pour de bon, sans points.
- **Clic sur Tagnan** : il cligne de l'œil et éclabousse ; trois clics de suite l'agacent, six le font bouder. **Glisser** le déplace (il retient sa place). **Clic droit** ou icône de la zone de notification : une question maintenant, la progression, une pause d'une heure ou jusqu'à demain, quitter.
- Il ne se montre pas pendant une application en plein écran, une présentation ou quand la session est verrouillée.

## Les grades

| Grade | Points | Ce qu'il gagne |
|---|---|---|
| Encrier | 0 | de l'encre dans son encrier, une plume d'oie trempée |
| Gascon | 20 | il s'échappe de l'encrier |
| Cadet | 60 | un feutre |
| Mousquetaire | 140 | la casaque à croix et la plume blanche |
| Lieutenant | 260 | la rapière et la moustache en croc |
| Capitaine | 420 | le chapeau à cocarde, la royale et l'or |

Une bonne réponse rapporte 10 points, plus 2 par réponse juste d'affilée (jusqu'à +10) ; une erreur en coûte 8 et remet la série à zéro. Un grade ne se perd que bien en dessous de son seuil (deux erreurs au moins). La difficulté des questions suit le grade, et les domaines où tu te trompes le plus reviennent plus souvent.

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

- **La fenêtre** (`tagnan/ui/`) tourne avec le Python Windows et lit le code de ce dépôt par `\\wsl.localhost`. Elle porte tout l'état : la base SQLite des questions, des réponses et des révisions, et ses réglages, dans `%LOCALAPPDATA%\tagnan`.
- **Le cerveau** (`tagnan/brain.py`, `scripts/brain`) tourne dans WSL et n'a aucun état : une requête JSON sur l'entrée, une réponse JSON sur la sortie. Il lance `claude -p` comme le relais de Dartt (variables d'environnement en liste blanche, `--setting-sources user`, `--strict-mcp-config`, `disableAllHooks`), avec `--tools ""` et un dossier vide, et valide la sortie par `--json-schema`. Les questions sont écrites par lots de dix, en tâche de fond, quand il en reste moins de cinq : on n'attend jamais Claude pour une question.
- **Le jeu** (`tagnan/game.py`, `progress.py`, `scheduler.py`, `store.py`, `model.py`) n'utilise que la bibliothèque standard, testé dans WSL. Chaque question générée est vérifiée (domaine, tâche, nombre de bonnes réponses, une explication par mauvais choix) et ses choix sont mélangés avant d'être gardés.
- **Le référentiel** de l'examen (`exam/aif-c01.toml`) donne les cinq domaines, leurs poids et les notions de chaque tâche, d'après le guide d'examen officiel. Pour un autre examen, un autre fichier et `exam = "…"` dans la config.
- **Tagnan** (`tagnan/art.py`) est dessiné à plat, dans la direction artistique de Dartt, et découpé en calques : la fenêtre dessine l'encre qui ondule (la formule de Dartt), les bras et les gouttes, et anime les calques SVG (yeux, bouche, chapeau, plumes, rapière…) au rythme d'un rig repris de celui de Dartt (`tagnan/ui/animation/`) : ressorts, clignements, regard qui suit la souris, gestes au hasard, tapes.

## Quota

Un lot de dix questions coûte un appel Sonnet d'environ 40 secondes ; une vingtaine de questions par jour, c'est deux ou trois appels, plus les « Explique-moi plus ». Le tout passe par ton abonnement Claude, jamais par une clé d'API.
