import pytest

from tagnan.blueprint import Blueprint
from tagnan.subject import Subject, from_key, parse


def test_words_name_the_exam_a_domain_or_a_subject(bp: Blueprint) -> None:
    assert parse("the whole exam", bp) == Subject()
    assert parse("All", bp).whole
    assert parse("domain 3", bp) == Subject(domain=3)
    assert parse("D2", bp) == Subject(domain=2)
    assert parse("4", bp) == Subject(domain=4)
    assert parse("guidelines for responsible ai", bp) == Subject(domain=4)
    assert parse("  RAG  with   Knowledge Bases. ", bp) == Subject(text="RAG with Knowledge Bases")


def test_what_does_not_do_says_why(bp: Blueprint) -> None:
    with pytest.raises(ValueError, match="Tell me"):
        parse("  ", bp)
    with pytest.raises(ValueError, match="domains 1 to 5"):
        parse("domain 9", bp)
    with pytest.raises(ValueError, match="Shorter"):
        parse("x" * 81, bp)


def test_keys_come_back_and_names_read_well(bp: Blueprint) -> None:
    for subject in (Subject(), Subject(domain=3), Subject(text="RAG")):
        assert from_key(subject.key) == subject
    assert Subject().name(bp) == "the whole exam"
    assert Subject(domain=3).name(bp) == "Domain 3 · Applications of Foundation Models"
    assert Subject(text="RAG").name(bp) == "RAG"
