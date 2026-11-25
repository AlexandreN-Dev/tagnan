Answer with one JSON object only, in a single code block, with nothing after it, shaped exactly like this:

$shape

- domain: the number of the question's domain; task: the identifier of one of its tasks, as given above.
- difficulty: easy, medium or hard. kind: "single" for one right answer, "multiple" for two or three.
- choices: four to six, none twice. answers: the indices of the right choices, counted from 0.
- why_wrong: one text per choice, in the order of the choices; an empty string for each right one.
- Plain text in every field: no markdown.
