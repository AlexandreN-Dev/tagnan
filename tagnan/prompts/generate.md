Write $count practice questions for the $exam_code exam, as follows:

$slots

$subject

Here are the domains involved, with their tasks and each task's notions. Each question is about a single task of its domain; vary the tasks and the notions from one question to the next.

$domains

Difficulty levels:
- easy: a definition, or the direct link between a need and a service or a notion.
- medium: a short scenario where two answers look plausible.
- hard: a scenario with constraints to weigh (cost, latency, security, governance, effort) and very close distractors.

Each question:
- stem: a scenario of one to three sentences, 450 characters at most, ending with the question. For a multiple-answer question, end with "(Choose TWO.)" or "(Choose THREE.)".
- choices: 4 choices for a single-answer question, 5 for a multiple-answer question. Plausible distractors, of the same family as the right answer and of similar length. Never "all of the above" or "none of the above".
- answers: the indices (from 0) of the right answers: one for "single", two or three for "multiple", as the stem says.
- explanation: two sentences at most, saying why the right answer or answers fit.
- why_wrong: one text per choice, in the order of the choices: one sentence saying why that choice does not fit this very scenario; an empty string for the right answers.
- topic: three to six words naming the notion tested, for example "Bedrock Guardrails, denied topics".
- task: the task's identifier, for example "3.1".
- reference: the AWS document to read again, for example "Amazon Bedrock User Guide, Guardrails".
- domain, difficulty, kind: those of the question's slot; when the slot leaves the domain to you, the domain of the task you chose.

Services and features in the exam's scope: $services.

$avoid
