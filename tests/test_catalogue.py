import json
from pathlib import Path
from typing import Any

import pytest

from tagnan import blueprint, catalogue
from tagnan.blueprint import Blueprint
from tagnan.game import Game
from tagnan.model import CONVERTED, WRITTEN
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
