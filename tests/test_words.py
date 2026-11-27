import random

import pytest

from tagnan import blueprint, language, words
from tagnan import progress as rules
from tagnan.game import LEVEL_UP_TOUCHES, LOW_WORDS, WORDS_BATCH, Game
from tagnan.model import Card, mark, parse_card
from tagnan.progress import DAY, GRADES, KNOWN, Progress, after_touch, after_touch_points
from tagnan.words import GAP, MEANING, MEET, TYPE, TYPE_GAP, WORD, Slot
from tests.conftest import WORDS, spanish, word_data

NOW = 1_800_000_000.0


# --- Languages by name, and a word typed ---------------------------------------------------------


@pytest.mark.parametrize(
    ("said", "found"),
    [
        ("Spanish", ("Spanish", "", "")),
        ("learn German B1", ("German", "B1", "")),
        ("l'anglais", ("English", "", "")),
        ("apprendre l\N{RIGHT SINGLE QUOTATION MARK}espagnol débutant", ("Spanish", "A1", "")),
        ("Italian for work", ("Italian", "", "for work")),
        ("Japanese words", ("Japanese", "", "")),
    ],
)
def test_a_language_is_found_in_ones_words(said: str, found: tuple[str, str, str]) -> None:
    got = language.find(said)
    assert got is not None
    assert (got.name, got.level, got.purpose) == found


@pytest.mark.parametrize(
    "said", ["the French Revolution", "Greek mythology", "pottery", "English literature", ""]
)
def test_a_subject_that_names_a_language_is_not_one(said: str) -> None:
    assert language.find(said) is None


def test_languages_go_by_their_own_names_and_levels_follow() -> None:
    assert language.named("français") == "French"
    assert language.named("  wolof ") == "Wolof"  # one he does not know: as typed
    assert language.own_name("French") == "Français"
    assert language.own_name("Wolof") == "Wolof"
    assert language.by_locale("fr_FR") == "French"
    assert language.by_locale("xx") == ""
    assert [language.next_level(k) for k in language.LEVEL_KEYS] == ["A2", "B1", "B2", "C1", ""]
    assert language.next_level("") == ""


@pytest.mark.parametrize(
    ("typed", "verdict"),
    [
        ("la cuenta", language.RIGHT),
        (" La  Cuenta. ", language.RIGHT),
        ("cuenta", language.ARTICLE),  # the article left out: the word still counts
        ("el cuenta", language.WRONG),  # a wrong one does not
        ("la cuénta", language.ACCENT),
        ("la nota", language.ALSO),
        ("el cuento", language.WRONG),
        ("", language.WRONG),
    ],
)
def test_a_word_typed_is_marked_leniently(typed: str, verdict: str) -> None:
    assert language.check(typed, "la cuenta", ["la nota"]) == verdict


def test_accents_and_letters_of_a_language() -> None:
    assert language.check("estacion", "la estación") == language.ACCENT
    assert language.check("strasse", "die Straße") == language.ARTICLE
    assert language.check("manana", "mañana") == language.ACCENT
    assert language.letters(["la estación", "el niño", "¿qué?", "pingüino"]) == ["é", "ñ", "ó", "ü"]
    assert language.letters(["plain", "words"]) == []
    assert language.typable("mañana")
    assert not language.typable("こんにちは")
    assert not language.typable("привет")


# --- A word's card -----------------------------------------------------------------------------


def test_a_word_is_checked_and_its_place_marked() -> None:
    bp = spanish()
    card = parse_card(word_data(4, example="¿Nos trae la cuenta, por favor?"), bp)
    assert (card.term, card.meaning, card.domain) == ("la cuenta", "the bill", 2)
    assert card.gap == ("¿Nos trae ", "la cuenta", ", por favor?")
    assert card.sentence == "¿Nos trae la cuenta, por favor?"
    # Marked by its writer, at the start of a sentence: kept as written there.
    assert parse_card(word_data(0, term="el plazo", example="**El plazo** termina."), bp).gap == (
        "",
        "El plazo",
        " termina.",
    )
    # Another form of the word: shown, but no gap to fill with the word itself.
    other = parse_card(word_data(0, example="Mañana **madrugo** mucho."), bp)
    assert other.gap is None
    assert other.sentence == "Mañana madrugo mucho."
    assert mark("Cuento un cuento.", "el cuento") == "Cuento un cuento."
    assert parse_card(word_data(0, also=["levantarse temprano", "madrugar", ""]), bp).also == (
        "levantarse temprano",
    )


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"chapter": 9}, "unknown chapter"),
        ({"term": ""}, "term: empty"),
        ({"meaning": " "}, "meaning: empty"),
        ({"meaning": "Madrugar"}, "the word itself"),
        ({"term": "x" * 90}, "too long"),
        ({"also": "otro"}, "a list"),
    ],
)
def test_bad_words_are_refused(changes: dict[str, object], reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        parse_card(word_data(0, **changes), spanish())


def test_a_language_course_keeps_its_language() -> None:
    bp = spanish()
    assert (bp.key, bp.name, bp.title, bp.exam) == ("spanish", "Spanish", "Spanish A2", False)
    assert bp.language == blueprint.Language("Spanish", "English", "A2", 1)
    assert blueprint.from_dict(bp.to_dict()) == bp
    assert blueprint.load("aif-c01").language is None
    up = blueprint.raise_level(bp, "B1", [("Opinions", "agreeing, doubting"), ("News", "media")])
    assert [d.id for d in up.domains] == [1, 2, 3, 4]
    assert up.language == blueprint.Language("Spanish", "English", "B1", 3)
    assert blueprint.from_dict(up.to_dict()) == up
    with pytest.raises(ValueError, match="language course"):
        blueprint.raise_level(blueprint.load("aif-c01"), "B1", [("x", "y")])


# --- The ladder --------------------------------------------------------------------------------


def test_a_word_climbs_a_step_when_right_and_steps_down_when_missed() -> None:
    assert [after_touch(step, True) for step in range(1, 7)] == [2, 3, 4, 5, 6, 6]
    assert [after_touch(step, False) for step in range(1, 7)] == [1, 1, 2, 3, 4, 5]
    days = [(rules.ladder_due(step, True, NOW) - NOW) / DAY for step in range(2, 7)]
    assert days == [1, 3, 7, 21, 60]  # his reviews' gaps, then a long one once known
    assert rules.ladder_due(3, False, NOW) == NOW + DAY  # a miss: back tomorrow


def test_a_touch_wins_three_points_and_a_miss_costs_two() -> None:
    p, delta = after_touch_points(Progress(), True)
    assert (p.points, p.streak, delta) == (3, 1, 3)
    p, delta = after_touch_points(Progress(points=40, streak=9, best_streak=9), True)
    assert (p.points, p.streak, p.best_streak, delta) == (43, 10, 10, 3)  # no bonus for a streak
    p, delta = after_touch_points(p, False)
    assert (p.points, p.streak, p.best_streak, delta) == (41, 0, 10, -2)
    assert after_touch_points(Progress(points=1), False)[0].points == 0


def weeks_to_captain_by_touches(accuracy: float, runs: int = 40, calls: int = 100) -> float:
    """Median weeks to the last grade, at `calls` bouts a week: four touches each, one in
    seven a new word shown, which wins nothing."""
    results = []
    for seed in range(runs):
        rng = random.Random(seed)
        p = Progress()
        touches = 0
        while p.grade < len(GRADES) - 1:
            touches += 1
            if touches % 7:
                p, _ = after_touch_points(p, rng.random() < accuracy)
        results.append(touches / 4 / calls)
    return sorted(results)[runs // 2]


def test_a_bout_is_worth_about_a_question_on_the_road_to_captain() -> None:
    assert 6 <= weeks_to_captain_by_touches(0.85) <= 9.5  # words are answered right more often
    assert 8 <= weeks_to_captain_by_touches(0.8) <= 12
    assert weeks_to_captain_by_touches(0.6) >= 14


# --- A bout ------------------------------------------------------------------------------------


def test_words_are_kept_once_and_bad_ones_set_aside(lingo: Game) -> None:
    bp = lingo.blueprint
    added = lingo.add_cards(
        bp,
        [
            word_data(0),  # he has it
            word_data(0, term="  La Cuenta "),  # and this one, case and spacing aside
            word_data(0, term="el plazo", meaning="the deadline", example=""),
            word_data(0, term="", meaning="nothing"),
            {"problem": "no meaning"},
        ],
        NOW,
        origin="written",
    )
    assert (len(added.ids), added.known) == (1, 2)
    assert added.rejected == [(4, "term: empty"), (5, "no meaning")]
    kept = lingo.store.card(added.ids[0])
    assert (kept.term, kept.origin, kept.step, kept.gap) == ("el plazo", "written", 0, None)
    assert lingo.is_language
    assert lingo.fresh_count() == lingo.new_words() == len(WORDS) + 1


def test_the_first_bouts_show_new_words_then_ask_them(lingo: Game) -> None:
    slots = lingo.next_bout(NOW)
    assert slots == [Slot(1), Slot(2)]  # two new words at once, at most
    touches = [lingo.touch(s) for s in slots]
    assert [(t.kind, t.card.term) for t in touches] == [(MEET, "madrugar"), (MEET, "trasnochar")]
    for t in touches:
        met = lingo.meet(t.card, NOW)
        assert (met.step, met.due_at) == (1, NOW + rules.SOON)
    # A little later the same day: they are asked, with two more new ones.
    later = NOW + rules.SOON + 60
    slots = lingo.next_bout(later)
    assert [s.card_id for s in slots] == [3, 4, 1, 2]
    asked = lingo.touch(slots[2])
    assert (asked.kind, asked.card.term) == (MEANING, "madrugar")
    assert len(asked.choices) == 4
    assert asked.choices[asked.answer] == "to get up early"
    assert [c.meaning for c in asked.behind] == list(asked.choices)
    # The other meanings are words of its chapter first.
    assert set(asked.choices) == {m for _, m, _, _, chapter in WORDS if chapter == 1}


def test_a_right_touch_sends_the_word_up_and_a_miss_down(lingo: Game) -> None:
    card = lingo.meet(lingo.store.card(5), NOW)  # la cuenta
    touch = lingo.touch(Slot(5))
    done = lingo.answer_touch(touch, NOW + 1500, picked=touch.answer)
    assert (done.correct, done.remark, done.delta, done.step, done.moved) == (
        True,
        language.RIGHT,
        3,
        2,
        True,
    )
    assert done.due_at == NOW + 1500 + DAY
    assert lingo.progress.points == 3
    touch = lingo.touch(Slot(5))
    assert touch.kind == WORD  # step 2: the word picked for its meaning
    assert touch.choices[touch.answer] == "la cuenta"
    wrong = next(i for i in range(len(touch.choices)) if i != touch.answer)
    missed = lingo.answer_touch(touch, NOW + 2 * DAY, picked=wrong)
    assert (missed.correct, missed.remark, missed.delta, missed.step) == (
        False,
        language.WRONG,
        -2,
        1,
    )
    assert missed.due_at == NOW + 3 * DAY
    assert lingo.progress.points == 1
    assert lingo.store.touch_stats("spanish") == {2: (2, 1)}
    assert card.id == 5


def test_each_step_asks_in_a_harder_way(lingo: Game) -> None:
    kinds = []
    for step in range(1, 7):
        lingo.store.move_card(5, step, NOW, NOW)
        kinds.append(lingo.touch(Slot(5)).kind)
    assert kinds == [MEANING, WORD, GAP, TYPE, TYPE_GAP, TYPE_GAP]
    lingo.store.move_card(5, 3, NOW, NOW)
    gap = lingo.touch(Slot(5))
    # In its sentence, the wrong choices are the words that look most like it.
    assert "el cuento" in gap.choices
    assert gap.choices[gap.answer] == "la cuenta"
    # A word with no sentence keeps to its word; one that cannot be typed, to choices.
    bp = lingo.blueprint
    plain = lingo.add_cards(bp, [word_data(0, term="el plazo", meaning="x", example="")], NOW)
    kana = lingo.add_cards(bp, [word_data(0, term="ねこ", meaning="the cat", example="")], NOW)
    for card_id, expected in (
        (plain.ids[0], [WORD, TYPE, TYPE]),
        (kana.ids[0], [WORD, WORD, WORD]),
    ):
        got = []
        for step in (3, 4, 5):
            lingo.store.move_card(card_id, step, NOW, NOW)
            got.append(lingo.touch(Slot(card_id)).kind)
        assert got == expected


def test_a_word_typed_is_right_but_for_its_accent(lingo: Game) -> None:
    lingo.store.move_card(4, 4, NOW, NOW)  # la estación, where it is typed
    touch = lingo.touch(Slot(4))
    assert (touch.kind, touch.expected, touch.choices) == (TYPE, "la estación", ())
    done = lingo.answer_touch(touch, NOW, typed="la estacion")
    assert (done.correct, done.remark, done.step) == (True, language.ACCENT, 5)
    assert done.due_at == NOW + 21 * DAY
    touch = lingo.touch(Slot(4))
    assert (touch.kind, touch.expected) == (TYPE_GAP, "la estación")
    assert lingo.answer_touch(touch, NOW, typed="").correct is False  # "I don't know"
    assert lingo.store.card(4).step == 4
    known = lingo.answer_touch(lingo.touch(Slot(4)), NOW, typed="La estación")
    assert known.step == 5
    assert lingo.answer_touch(lingo.touch(Slot(4)), NOW, typed="estación").step == KNOWN


def test_a_word_known_already_goes_where_it_is_typed(lingo: Game) -> None:
    met = lingo.meet(lingo.store.card(1), NOW, known=True)
    assert (met.step, met.due_at) == (rules.SKIP_TO, NOW + rules.SOON)
    assert lingo.touch(Slot(1)).kind == TYPE


def test_with_nothing_due_or_new_he_asks_ahead_and_the_word_stays(lingo: Game) -> None:
    for card in lingo.store.cards("spanish"):
        assert card.id is not None
        lingo.store.move_card(card.id, 2, NOW + card.id * DAY, NOW)
    assert lingo.next_bout(NOW + 60) == []  # all just seen: let them rest
    slots = lingo.next_bout(NOW + words.REST)
    assert slots == [Slot(i, early=True) for i in (1, 2, 3, 4)]  # the nearest their time
    touch = lingo.touch(slots[0])
    assert touch.early
    done = lingo.answer_touch(touch, NOW + words.REST, picked=touch.answer)
    assert (done.correct, done.delta, done.moved, done.step) == (True, 3, False, 2)
    assert done.due_at == NOW + DAY  # as it was
    wrong = next(i for i in range(len(touch.choices)) if i != touch.answer)
    missed = lingo.answer_touch(touch, NOW + words.REST, picked=wrong)
    assert (missed.moved, missed.step) == (True, 1)  # a miss counts, whenever it comes


def test_reviews_come_before_new_words(lingo: Game) -> None:
    for card_id in (5, 6, 7):
        lingo.store.move_card(card_id, 2, NOW - card_id, NOW - DAY)
    slots = lingo.next_bout(NOW)
    assert [s.card_id for s in slots] == [
        1,
        7,
        6,
        5,
    ]  # room for one new word, the longest due first
    lingo.store.move_card(8, 3, NOW - 1, NOW - DAY)
    assert [s.card_id for s in lingo.next_bout(NOW)] == [7, 6, 5, 8]  # four due: no new word
    # One chapter chosen: its words only.
    lingo.set_subject(lingo.subject.__class__(domain=1))
    assert [s.card_id for s in lingo.next_bout(NOW)] == [1, 2]
    assert lingo.new_words() == 4


def test_he_asks_the_brain_for_words_where_he_has_fewest(lingo: Game) -> None:
    assert not lingo.needs_words()  # eight new ones
    lingo.meet(lingo.store.card(1), NOW)
    assert lingo.new_words() == LOW_WORDS - 1
    assert lingo.needs_words()
    lingo.add_cards(lingo.blueprint, [word_data(0, term="el piso", meaning="the flat")], NOW)
    request = lingo.words_request()
    assert request["exam"] == "spanish"
    assert request["course"]["language"]["level"] == "A2"
    assert request["chapters"] == [{"id": 2, "count": 10}, {"id": 1, "count": 10}]
    assert sum(c["count"] for c in request["chapters"]) == WORDS_BATCH
    assert set(request["avoid"]) == {w[0] for w in WORDS} | {"el piso"}
    lingo.set_subject(lingo.subject.__class__(domain=1))
    assert lingo.words_request()["chapters"] == [{"id": 1, "count": 20}]


def test_his_summary_counts_words_and_offers_the_next_level(lingo: Game) -> None:
    lingo.store.move_card(1, KNOWN, NOW + 60 * DAY, NOW)
    lingo.store.move_card(5, 2, NOW + 3600, NOW)
    lingo.store.move_card(6, 3, NOW + 9 * DAY, NOW)
    counts = lingo.word_counts(NOW)
    assert (counts["known"], counts["climbing"], counts["fresh"]) == (1, 2, 5)
    assert counts["due"] == 1  # by tonight
    assert counts["chapters"] == [
        {"id": 1, "name": "Everyday life", "known": 1, "of": 4},
        {"id": 2, "name": "Food and eating out", "known": 0, "of": 4},
    ]
    summary = lingo.summary()
    assert (summary["fresh"], summary["reviews"], summary["answered"]) == (5, 2, 0)
    assert lingo.level_up(NOW) == ""  # nothing answered yet
    for i in range(LEVEL_UP_TOUCHES):
        lingo.store.record_touch(5, MEANING, i % 10 != 0, 3, NOW - 3600)
    assert lingo.level_up(NOW) == "B1"  # nine right in ten, this week
    assert lingo.level_up(NOW + 8 * DAY) == ""  # not on last week's
    lingo.store.record_touch(5, MEANING, False, -2, NOW - 60)
    assert lingo.level_up(NOW) == ""
    summary = lingo.summary()
    assert (summary["answered"], summary["right"]) == (81, 72)
    assert summary["domains"][1] == {
        "id": 2,
        "name": "Food and eating out",
        "answered": 81,
        "right": 72,
    }


def test_a_course_of_questions_has_no_words(game: Game) -> None:
    assert not game.is_language
    assert game.next_bout(NOW) == []
    assert game.level_up(NOW) == ""
    assert isinstance(Card(1, "a", "b"), Card)
