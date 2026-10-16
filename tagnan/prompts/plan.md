The learner told Tagnan what they want to learn now: "$words"

Draw up the blueprint of that course, the way an exam guide lays out its domains.

- If it names a certification (an AWS exam, or any other), follow that exam's official guide as you know it: its code (for example "SAA-C03"), its full name, its domains with their weights in percent, and for each domain its task statements with the notions each covers. Set exam to true.
- Otherwise, lay out the subject as a good teacher would plan a course for an adult: 4 to 6 domains from foundations to finer points, each with 2 to 4 tasks and the notions each covers, the weights summing to 100. The code is the subject's short name, two or three words ("Pottery", "French Revolution"). Set exam to false.
- If the words are too vague to teach ("stuff", "things"), or not something to learn with quiz questions, set understood to false and say in one short sentence, in English, what to say instead; the rest may then be empty.

Domains are numbered from 1; a task's id is its domain's number, a dot and its own ("2.3"). Notions are concrete: the terms, facts, techniques and distinctions a question can test, 30 to 80 words per task.

- name: the course's full name, in English.
- guidance: two to four sentences telling the question writer how to write well on this subject: what makes a question sound or unsound here, which facts are stable enough to ask, what to avoid (for an AWS exam: name services exactly as AWS does, never ask about quotas, prices or Regions).
- reference: what a question's reference should point to, with one example: "the AWS document to read again, for example \"Amazon S3 User Guide, Storage classes\"", or "a book or chapter to read again, for example \"Daniel Rhodes, Clay and Glazes for the Potter, chapter 4\"".
- services: for an exam on a product range, the services or tools in its scope, named exactly; otherwise an empty list.
- multiple: true if the subject lends itself to questions with two or three right answers among five.
