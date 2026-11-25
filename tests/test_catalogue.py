import json
import random
from pathlib import Path
from typing import Any

import pytest

from tagnan import blueprint, catalogue
from tagnan.blueprint import Blueprint
from tagnan.game import Game
from tagnan.model import CONVERTED, TYPED, WRITTEN
from tagnan.store import Store
from tests.conftest import pottery_data, pottery_question, question_data

NOW = 1_800_000_000.0


def answer(text: str) -> str:
    """As an assistant answers: a line, the code block, a line."""
    lead = "Here are your questions, in the format you asked for:"
    return f"{lead}\n\n```json\n{text}\n```\n\nGood luck!"


def written(*questions: dict[str, Any], **head: Any) -> str:
    return json.dumps(
        {
            "tagnan": 1,
            "course": "aif-c01",
            "origin": "written",
            **head,
            "questions": list(questions),
        },
        ensure_ascii=False,
        indent=1,
    )


def topics(count: int) -> list[dict[str, Any]]:
    return [
        question_data(topic=f"notion {i}", stem=f"Question number {i}: which one?")
        for i in range(count)
    ]


# --- Reading ---------------------------------------------------------------------------------


def test_an_assistants_answer_is_read_code_block_and_words_around_it() -> None:
    found = catalogue.read(answer(written(*topics(3))))
    assert found.course == "aif-c01"
    assert found.origin == WRITTEN
    assert [q["topic"] for q in found.questions] == ["notion 0", "notion 1", "notion 2"]
    assert not found.cut
    assert found.left_out == ()


def test_an_answer_cut_off_keeps_its_whole_questions() -> None:
    text = answer(written(*topics(15)))
    cut = text[: text.index("Question number 14")]  # the answer stops inside the 15th
    found = catalogue.read(cut)
    assert found.cut
    assert len(found.questions) == 14
    # A question garbled in the middle stops it there too.
    garbled = text.replace('"Question number 5: which one?"', '"Question number 5", which one?"')
    broken = catalogue.read(garbled)
    assert broken.cut
    assert len(broken.questions) == 5
    # Its questions whole but its last brace gone: nothing is cut.
    whole = catalogue.read(written(*topics(2)).rstrip().removesuffix("}"))
    assert not whole.cut
    assert len(whole.questions) == 2


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("Sure! What subject would you like questions on?", "I find no questions in it"),
        ('{"tagnan": 1, "course": "aif-c01", "questions": []}', "it holds no questions"),
        (
            '{"tagnan": 1, "course": "aif-c01", "questions": [{"domain": 3, "ste',
            "breaks off before",
        ),
        ('{"tagnan": 2, "course": "aif-c01", "questions": [{}]}', "a newer Tagnan"),
        (json.dumps({"tagnan": 1, "questions": [question_data()]}), "which course"),
    ],
)
def test_what_is_not_a_catalogue_is_said_so(text: str, said: str) -> None:
    with pytest.raises(ValueError, match=said):
        catalogue.read(text)


def test_a_catalogue_may_bring_its_course_and_say_what_was_left_out() -> None:
    found = catalogue.read(
        json.dumps(
            {
                "tagnan": 1,
                "course": pottery_data(),
                "origin": "converted",
                "left_out": [{"number": 7, "why": "the quiz gives no answer"}, "?"],
                "questions": [pottery_question()],
            }
        )
    )
    assert isinstance(found.course, Blueprint)
    assert found.course.key == "pottery"
    assert found.origin == CONVERTED
    assert found.left_out == ((7, "the quiz gives no answer"),)
    # An origin of its own is taken as written.
    assert catalogue.read(written(question_data(), origin="mine")).origin == WRITTEN


# --- Taking its questions --------------------------------------------------------------------


def test_its_questions_are_checked_as_the_brains_and_kept_once(game: Game) -> None:
    first = game.add_questions(game.blueprint, topics(3), NOW, WRITTEN)
    assert len(first.ids) == 3
    assert (first.known, first.rejected) == (0, [])
    q = game.store.question(first.ids[0])
    assert q.origin == WRITTEN
    assert q.choices[q.answers[0]] == "Amazon Bedrock Guardrails"  # checked, then shuffled
    again = [
        question_data(stem="  QUESTION number 1:  which one? "),  # the same, cased and spaced
        question_data(stem="Something new?", choices=["a", "a", "b", "c"]),
        question_data(stem="Something else?", topic="new"),
        question_data(stem="Something else?", topic="the same again"),
        question_data(stem="Another?", domain=9),
    ]
    second = game.add_questions(game.blueprint, again, NOW, CONVERTED, subject="RAG")
    assert len(second.ids) == 1
    assert second.known == 2
    assert [n for n, _ in second.rejected] == [2, 5]
    assert [catalogue.reason(why) for _, why in second.rejected] == [
        "two of its choices are the same",
        "its domain is not one of the course's",
    ]
    kept = game.store.question(second.ids[0])
    assert (kept.origin, kept.subject) == (CONVERTED, "RAG")
    # A question reported as wrong never comes back through a catalogue.
    game.store.flag(first.ids[1])
    assert game.add_questions(game.blueprint, [topics(3)[1]], NOW, WRITTEN).known == 1


def test_a_course_brought_by_a_catalogue_is_kept_but_not_learned(game: Game) -> None:
    pottery = blueprint.from_dict(pottery_data())
    game.keep_course(pottery)
    assert game.exam == "aif-c01"
    assert [c.key for c in game.courses()] == ["aif-c01", "pottery"]
    added = game.add_questions(game.course("pottery"), [pottery_question()], NOW, WRITTEN)
    assert added.ids
    assert game.store.fresh_count("pottery") == 1


# --- Sharing ---------------------------------------------------------------------------------


def test_an_export_holds_the_course_and_the_questions_one_may_share(
    game: Game, tmp_path: Path
) -> None:
    brain = game.add_batch(topics(3), NOW)[0]
    written_ids = game.add_questions(
        game.blueprint, [question_data(stem="Mine?")], NOW, WRITTEN
    ).ids
    converted = game.add_questions(game.blueprint, [question_data(stem="Theirs?")], NOW, CONVERTED)
    game.store.flag(brain[0])
    shared = game.store.shareable(game.exam)
    assert [q.id for q in shared] == [*brain[1:], *written_ids]
    assert converted.ids[0] not in [q.id for q in shared]
    assert game.store.count(game.exam, CONVERTED) == 1
    assert game.store.count(game.exam, "") == 2  # his brain's, the reported one left out
    data = catalogue.export(game.blueprint, shared)
    name = catalogue.file_name(game.blueprint, len(shared))
    assert name == "Tagnan – AIF-C01 – 3 questions.json"
    assert catalogue.file_name(blueprint.from_dict({**pottery_data(), "code": 'A/B: "C"'}), 1) == (
        "Tagnan – A B C – 1 question.json"
    )
    path = catalogue.write(data, tmp_path, name)
    again = catalogue.write(data, tmp_path, name)
    assert again.name == "Tagnan – AIF-C01 – 3 questions (2).json"  # never over another
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([name, again.name])
    # A colleague reads it back: the course whole, the questions as they were.
    found = catalogue.read(path.read_text(encoding="utf-8"))
    assert isinstance(found.course, Blueprint)
    assert found.course.key == "aif-c01"
    assert [q["stem"] for q in found.questions] == [q.stem for q in shared]


# --- Prompts ---------------------------------------------------------------------------------


def test_the_prompt_to_write_asks_as_his_brain_does_then_for_his_format(game: Game) -> None:
    game.add_batch(topics(2), NOW)
    request = game.batch_request(catalogue.BATCH)
    prompt = catalogue.write_prompt(game.blueprint, request)
    assert prompt.startswith("You write the questions of Tagnan")
    assert "Write 20 practice questions for the AIF-C01 exam" in prompt
    assert "- notion 1" in prompt  # the topics asked lately, left aside
    assert '{"tagnan": 1, "course": "aif-c01", "origin": "written", "questions": [' in prompt
    assert catalogue.QUESTION_SHAPE in prompt
    on_rag = catalogue.write_prompt(game.blueprint, {**request, "subject": "RAG"})
    assert 'the subject the learner chose: "RAG"' in on_rag
    assert '"origin": "written", "subject": "RAG", "questions"' in on_rag


def test_the_prompt_to_convert_names_every_task_and_twenty_at_a_time(bp: Blueprint) -> None:
    prompt = catalogue.convert_prompt(bp)
    assert prompt.startswith("I use Tagnan, a quiz game, to prepare for the AWS Certified AI")
    for domain in bp.domains:
        assert f"Domain {domain.id}, {domain.name}:" in prompt
        assert all(f"  - {t.id} {t.title}" in prompt for t in domain.tasks)
    assert "Convert 20 questions at most" in prompt
    assert '"origin": "converted", "left_out": [{"number": 7, "why": "…"}], "questions"' in prompt


def test_the_prompt_for_something_new_draws_up_its_course_too() -> None:
    prompt = catalogue.course_prompt("pottery")
    assert prompt.startswith('I use Tagnan, a quiz game, to learn something new: "pottery".')
    assert f'"course": {catalogue.COURSE_SHAPE}, "origin": "written"' in prompt
    assert "20 easy single-answer questions" in prompt


def test_ask_your_assistant_is_what_tell_me_more_asks_his_brain(game: Game) -> None:
    question = game.store.question(game.add_batch(topics(1), NOW)[0][0])
    wrong = next(i for i in range(4) if i not in question.answers)
    prompt = catalogue.explain_prompt(game.blueprint, question, [wrong])
    assert prompt.startswith("Someone learning AWS Certified AI Practitioner (AIF-C01) got this")
    assert f"Answer given: {'ABCD'[wrong]}" in prompt


# --- Typed by hand -----------------------------------------------------------------------------

NOTE = """# Networking basics

Some words before the first question are left aside.

## Addressing

Question 1: How long is an IPv4 address?
A. 16 bits
B. 32 bits
C. 64 bits
D. 128 bits
Answer: B
Explanation: Four bytes, written
as four numbers.
Source: RFC 791

Question 2: An IPv6 address is 128 bits long.
- [x] True
- [ ] False

## Routing

Question 3: Which device forwards packets
between networks?
1. A switch
2. A router
3. A hub
Réponse : 2

Q4. Which two are routing protocols?
a) OSPF
b) HTTP
c) BGP
Answer: a, c

### Which one is the loopback address?
- 127.0.0.1
- 10.0.0.1
Answer: 127.0.0.1

Question 6: Lost its answer
A. one
B. two

Question 7: Alone
A. one
Answer: A
"""


def test_a_note_typed_by_hand_is_read_in_its_usual_shapes() -> None:
    found = catalogue.read(NOTE)
    assert found.typed
    assert found.origin == TYPED
    assert isinstance(found.course, Blueprint)
    course = found.course
    assert (course.key, course.name, course.exam) == (
        "networking-basics",
        "Networking basics",
        False,
    )
    assert [d.name for d in course.domains] == ["Addressing", "Routing"]
    assert course.kinds == ("single", "multiple")
    first, true, router, two, loopback, lost, alone = found.questions
    assert first["stem"] == "How long is an IPv4 address?"
    assert (first["answers"], first["domain"], first["task"]) == ([1], 1, "1.1")
    assert first["explanation"] == "Four bytes, written as four numbers."
    assert first["reference"] == "RFC 791"
    assert (true["choices"], true["answers"]) == (["True", "False"], [0])
    assert router["stem"] == "Which device forwards packets between networks?"
    assert (router["answers"], router["domain"]) == ([1], 2)
    assert (two["answers"], two["kind"]) == ([0, 2], "multiple")
    assert (loopback["stem"], loopback["answers"]) == ("Which one is the loopback address?", [0])
    assert lost["problem"] == "no Answer line"
    assert alone["problem"] == "a single choice"


def test_a_typed_text_without_a_title_is_named_by_its_file_or_untitled() -> None:
    text = "Question: Two plus two?\nA. 3\nB. 4\nAnswer: B\n"
    assert catalogue.read(text, "Arithmetic").course.name == "Arithmetic"  # type: ignore[union-attr]
    untitled = catalogue.read(text).course
    assert isinstance(untitled, Blueprint)
    assert (untitled.name, [d.name for d in untitled.domains]) == ("My questions", ["My questions"])
    with pytest.raises(ValueError, match="I find no questions in it"):
        catalogue.read("Just some notes, with no question in them.")


@pytest.mark.parametrize("comma", [",", ";"])
def test_a_spreadsheet_saved_as_csv(comma: str) -> None:
    rows = [
        ["Chapitre", "Question", "A", "B", "C", "D", "Réponse", "Explication"],
        [
            "Addressing",
            "How long is an IPv4 address?",
            "16 bits",
            "32 bits",
            "64 bits",
            "128 bits",
            "B",
            "Four bytes.",
        ],
        ["Addressing", "An IPv6 address is 128 bits long.", "True", "False", "", "", "A", ""],
        [
            "Routing",
            "Which device forwards packets, between networks?",
            "A switch",
            "A router",
            "",
            "",
            "A router",
            "",
        ],
    ]
    text = "\n".join(comma.join(f'"{c}"' if comma in c else c for c in row) for row in rows)
    found = catalogue.read(text, "Networking basics")
    assert isinstance(found.course, Blueprint)
    assert [d.name for d in found.course.domains] == ["Addressing", "Routing"]
    assert [q["answers"] for q in found.questions] == [[1], [0], [1]]
    assert found.questions[1]["choices"] == ["True", "False"]
    assert found.questions[2]["stem"] == "Which device forwards packets, between networks?"


def test_typed_questions_are_checked_lighter(game: Game) -> None:
    found = catalogue.read(NOTE)
    assert isinstance(found.course, Blueprint)
    added = game.add_questions(found.course, found.questions, NOW, found.origin)
    assert len(added.ids) == 5  # two choices, no explanation: kept
    assert [(n, catalogue.reason(why)) for n, why in added.rejected] == [
        (6, "no Answer line"),
        (7, "a single choice"),
    ]
    q = game.store.question(added.ids[1])
    assert (q.origin, q.explanation, q.why_wrong) == (TYPED, "", ("", ""))
    # Written by an assistant, the same question is checked in full.
    strict = game.add_questions(
        found.course, [{**found.questions[1], "stem": "Other?"}], NOW, WRITTEN
    )
    assert catalogue.reason(strict.rejected[0][1]) == "it needs four to six choices"


def test_a_note_pasted_again_adds_its_new_chapters(game: Game) -> None:
    first = catalogue.read(NOTE)
    assert isinstance(first.course, Blueprint)
    game.keep_course(first.course)
    game.add_questions(first.course, first.questions, NOW, TYPED)
    longer = catalogue.read(
        NOTE
        + "\n## Switching\n\nQuestion: What does a switch learn?\nA. MAC addresses\nB. Routes\n"
        "Answer: A\n\n## routing\n\nQuestion: Which protocol is a distance vector one?\n"
        "A. RIP\nB. OSPF\nAnswer: A\n"
    )
    assert isinstance(longer.course, Blueprint)
    merged, moved = catalogue.merge(
        game.course("networking-basics"), longer.course, longer.questions
    )
    assert [d.name for d in merged.domains] == ["Addressing", "Routing", "Switching"]
    assert [(q["domain"], q["task"]) for q in moved[-2:]] == [(3, "3.1"), (2, "2.1")]  # by name
    added = game.add_questions(merged, moved, NOW, TYPED)
    assert (len(added.ids), added.known) == (2, 5)
    # A course of exam/ keeps its guide's chapters: one it lacks is set aside; "Domain 3" is
    # its third.
    note = catalogue.read(
        "## Domain 3\nQuestion: Which?\nA. a\nB. b\nAnswer: A\n"
        "## Pottery\nQuestion: Clay?\nA. a\nB. b\nAnswer: B\n"
    )
    assert isinstance(note.course, Blueprint)
    exam, kept = catalogue.merge(game.course("aif-c01"), note.course, note.questions)
    assert exam.domains == game.course("aif-c01").domains
    assert kept[0]["domain"] == 3
    assert kept[1]["problem"] == "its chapter, Pottery, is not one of AIF-C01's"


def test_typed_questions_are_shared_and_read_back_lighter(game: Game) -> None:
    found = catalogue.read(NOTE)
    assert isinstance(found.course, Blueprint)
    game.keep_course(found.course)
    game.add_questions(found.course, found.questions, NOW, TYPED)
    shared = game.store.shareable("networking-basics")
    assert len(shared) == 5  # one's own notes: shared
    data = catalogue.export(found.course, shared)
    assert {q["origin"] for q in data["questions"]} == {TYPED}
    colleague = Game(Store(":memory:"), game.course("aif-c01"), random.Random(2))
    again = catalogue.read(json.dumps(data))
    assert isinstance(again.course, Blueprint)
    added = colleague.add_questions(again.course, again.questions, NOW, again.origin)
    assert (len(added.ids), added.rejected) == (5, [])
    assert colleague.store.question(added.ids[0]).origin == TYPED


def test_the_format_example_reads_as_it_says() -> None:
    found = catalogue.read(catalogue.FORMAT_EXAMPLE)
    assert isinstance(found.course, Blueprint)
    assert found.course.name == "The course's name"
    assert [q.get("answers") for q in found.questions] == [[1], [0, 2]]
