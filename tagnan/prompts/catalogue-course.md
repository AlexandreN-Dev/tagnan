I use Tagnan, a quiz game, to learn something new: "$words". Draw up a course on it, then write its first $count questions. Everything you write is in English.

The course:
- If the words name a certification, follow its official exam guide as you know it: its code (for example "SAA-C03"), its full name, its domains with their weights in percent, and for each domain its task statements with the notions each covers. Set exam to true.
- Otherwise, lay out the subject as a good teacher would plan a course for an adult: 4 to 6 domains from foundations to finer points, each with 2 to 4 tasks and the notions each covers, the weights summing to 100. The code is the subject's short name, two or three words ("Pottery", "French Revolution"). Set exam to false.
- Domains are numbered from 1; a task's id is its domain's number, a dot and its own ("2.3"). Notions are concrete: the terms, facts, techniques and distinctions a question can test, 30 to 80 words per task.
- guidance: two to four sentences on how to write sound questions on this subject: which facts are stable enough to ask, what to avoid. reference: what a question's reference points to, with one example.

The questions: $count easy single-answer questions, spread over the domains as their weights say, each on a single task. Accurate, unambiguous, about stable, well-established facts; if a fact seems uncertain to you, choose another notion.
- stem: one to three sentences, 450 characters at most, ending with the question.
- choices: 4, plausible, of the same family as the right answer and of similar length; never "all of the above" or "none of the above".
- answers: the index of the right one.
- explanation: two sentences at most, saying why it fits.
- why_wrong: one sentence per choice, saying why that choice does not fit; an empty string for the right one.
- topic: three to six words naming the notion tested.
- reference: a book, chapter or document to read again.

$format
