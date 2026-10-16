Écris $count questions d'entraînement pour l'examen $exam_code, réparties ainsi :

$slots

Voici les domaines concernés, avec leurs tâches et les notions de chaque tâche. Chaque question porte sur une seule tâche de son domaine ; varie les tâches et les notions d'une question à l'autre.

$domains

Niveaux de difficulté :
- facile : une définition, ou le lien direct entre un besoin et un service ou une notion.
- moyen : une courte mise en situation où deux réponses semblent plausibles.
- difficile : une mise en situation avec des contraintes (coût, latence, sécurité, gouvernance, effort) à arbitrer, et des distracteurs très proches.

Format de chaque question :
- stem : une mise en situation de une à trois phrases, 450 caractères au plus, qui se termine par la question. Pour une question à réponses multiples, termine par « (Choisissez-en DEUX.) » ou « (Choisissez-en TROIS.) ».
- choices : 4 choix pour une question à réponse unique, 5 pour une question à réponses multiples. Des distracteurs plausibles, de la même famille que la bonne réponse et de longueur comparable. Jamais « toutes les réponses » ni « aucune ».
- answers : les indices (à partir de 0) des bonnes réponses : un seul pour « single », deux ou trois pour « multiple », comme annoncé dans le stem.
- explanation : deux phrases au plus, qui disent pourquoi la ou les bonnes réponses conviennent.
- why_wrong : un texte par choix, dans l'ordre des choix : une phrase qui dit pourquoi ce choix ne convient pas à cette situation précise ; une chaîne vide pour les bonnes réponses.
- topic : trois à six mots qui nomment la notion testée, par exemple « Bedrock Guardrails, sujets refusés ».
- task : l'identifiant de la tâche, par exemple « 3.1 ».
- reference : le document AWS à relire, par exemple « Amazon Bedrock User Guide, Guardrails ».
- domain, difficulty, kind : ceux du créneau de la question.

Services et fonctionnalités dans le périmètre de l'examen : $services.

$avoid
