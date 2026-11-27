"""Languages: the ones Tagnan knows by name, the levels one learns them at, and how a word typed
is compared with the word expected: leniently, as a teacher marks a beginner.

Standard library only, as the game.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# The levels of the Common European Framework, and a plain word for each.
LEVELS = (
    ("A1", "Beginner"),
    ("A2", "Elementary"),
    ("B1", "Intermediate"),
    ("B2", "Upper intermediate"),
    ("C1", "Advanced"),
)
LEVEL_KEYS = tuple(key for key, _ in LEVELS)

# A language's name in English, and the other names it goes by: its own, the French one.
_NAMES = {
    "English": ("english", "anglais", "inglés", "ingles", "englisch", "inglese"),
    "French": ("french", "français", "francais", "francés", "frances", "französisch", "francese"),
    "Spanish": ("spanish", "espagnol", "español", "espanol", "castellano", "spanisch", "spagnolo"),
    "German": ("german", "allemand", "deutsch", "alemán", "aleman", "tedesco"),
    "Italian": ("italian", "italien", "italiano"),
    "Portuguese": ("portuguese", "portugais", "português", "portugues"),
    "Dutch": ("dutch", "néerlandais", "neerlandais", "nederlands"),
    "Catalan": ("catalan", "català", "catala"),
    "Basque": ("basque", "euskara"),
    "Breton": ("breton", "brezhoneg"),
    "Occitan": ("occitan",),
    "Irish": ("irish", "irlandais", "gaeilge"),
    "Welsh": ("welsh", "gallois", "cymraeg"),
    "Swedish": ("swedish", "suédois", "suedois", "svenska"),
    "Norwegian": ("norwegian", "norvégien", "norvegien", "norsk"),
    "Danish": ("danish", "danois", "dansk"),
    "Finnish": ("finnish", "finnois", "suomi"),
    "Icelandic": ("icelandic", "islandais"),
    "Polish": ("polish", "polonais", "polski"),
    "Czech": ("czech", "tchèque", "tcheque"),
    "Slovak": ("slovak", "slovaque"),
    "Hungarian": ("hungarian", "hongrois", "magyar"),
    "Romanian": ("romanian", "roumain", "română", "romana"),
    "Bulgarian": ("bulgarian", "bulgare"),
    "Croatian": ("croatian", "croate"),
    "Serbian": ("serbian", "serbe"),
    "Greek": ("greek", "grec"),
    "Turkish": ("turkish", "turc", "türkçe", "turkce"),
    "Russian": ("russian", "russe"),
    "Ukrainian": ("ukrainian", "ukrainien"),
    "Arabic": ("arabic", "arabe"),
    "Hebrew": ("hebrew", "hébreu", "hebreu"),
    "Persian": ("persian", "persan", "farsi"),
    "Hindi": ("hindi",),
    "Chinese": ("chinese", "chinois", "mandarin"),
    "Japanese": ("japanese", "japonais"),
    "Korean": ("korean", "coréen", "coreen"),
    "Vietnamese": ("vietnamese", "vietnamien"),
    "Thai": ("thai", "thaï"),
    "Indonesian": ("indonesian", "indonésien", "indonesien"),
    "Swahili": ("swahili",),
    "Latin": ("latin",),
    "Esperanto": ("esperanto", "espéranto"),
}
_BY_NAME = {other: name for name, others in _NAMES.items() for other in others}
# How the languages one is likely to speak call themselves: the level bubble's "You speak".
_OWN_NAMES = {
    "English": "English",
    "French": "Français",
    "Spanish": "Español",
    "German": "Deutsch",
    "Italian": "Italiano",
    "Portuguese": "Português",
    "Dutch": "Nederlands",
}
_BY_LOCALE = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
}
# Words that say nothing of the subject: "learn Spanish", "apprendre l'anglais", "German words".
_FILLER = frozenset(
    [
        "learn",
        "learning",
        "study",
        "studying",
        "speak",
        "speaking",
        "practise",
        "practice",
        "the",
        "a",
        "some",
        "my",
        "to",
        "in",
        "language",
        "vocabulary",
        "words",
        "course",
        "lessons",
        "basics",
        "apprendre",
        "parler",
        "étudier",
        "etudier",
        "pratiquer",
        "le",
        "la",
        "l",
        "d",
        "les",
        "un",
        "du",
        "de",
        "des",
        "langue",
        "vocabulaire",
        "mots",
        "cours",
        "level",
        "niveau",
    ]
)
_LEVEL_WORDS = {
    "beginner": "A1",
    "beginners": "A1",
    "débutant": "A1",
    "debutant": "A1",
    "elementary": "A2",
    "intermediate": "B1",
    "intermédiaire": "B1",
    "intermediaire": "B1",
    "advanced": "C1",
    "avancé": "C1",
    "avance": "C1",
}
_CURLY = "\N{RIGHT SINGLE QUOTATION MARK}"  # an apostrophe, as phones and Word type it
_PURPOSE = re.compile(r"\b(?:for|pour|at|au|en)\b")


@dataclass(frozen=True)
class Found:
    """A language one asked to learn, in one's own words."""

    name: str  # in English: "Spanish"
    level: str = ""  # "A2", when the words say it
    purpose: str = ""  # "for work", when they say what for


def find(words: str) -> Found | None:
    """The language the words ask to learn, if that is all they ask: "Spanish", "learn German
    B1", "l'anglais", "Italian for work". Not "the French Revolution" or "Greek mythology"."""
    said = " ".join(words.replace(_CURLY, "'").split()).casefold()
    said = re.sub(r"\b([ld])'", r"\1 ", said)
    purpose = ""
    cut = _PURPOSE.search(said)
    if cut:
        said, purpose = said[: cut.start()], said[cut.start() :].strip(" .!?")
    name, level, rest = "", "", []
    for token in re.findall(r"[^\W_]+", said):
        if token in _BY_NAME and not name:
            name = _BY_NAME[token]
        elif token.upper() in LEVEL_KEYS:
            level = token.upper()
        elif token in _LEVEL_WORDS:
            level = _LEVEL_WORDS[token]
        elif token not in _FILLER:
            rest.append(token)
    if not name or rest:
        return None
    return Found(name, level, purpose)


def named(text: str) -> str:
    """A language by any of its names, in English; else the words themselves, tidied: the
    language one speaks, typed."""
    said = " ".join(text.split()).strip(" .!?")
    return _BY_NAME.get(said.casefold(), said[:1].upper() + said[1:])[:40]


def own_name(name: str) -> str:
    """How a language calls itself, where he knows: "Français" for French."""
    return _OWN_NAMES.get(name, name)


def by_locale(locale: str) -> str:
    """The language of a system set to that locale ("fr_FR"), in English; "" when unknown."""
    return _BY_LOCALE.get(locale[:2].casefold(), "")


def next_level(level: str) -> str:
    """The level after this one; "" after the last, or for none."""
    if level in LEVEL_KEYS[:-1]:
        return LEVEL_KEYS[LEVEL_KEYS.index(level) + 1]
    return ""


# --- A word typed -----------------------------------------------------------------------------

# What a noun or a verb is given with, in the languages most learned: left out, the word still
# counts; a wrong one does not.
_ARTICLES = frozenset(
    [
        "the",
        "a",
        "an",
        "to",
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "le",
        "les",
        "l",
        "une",
        "des",
        "der",
        "die",
        "das",
        "ein",
        "eine",
        "il",
        "gli",
        "uno",
        "um",
        "uma",
        "het",
        "een",
    ]
)
_ARTICLE = re.compile(r"^([^\W\d_]+)(?:'|\s+)(.+)$")
_EDGES = " \t.,;:!?¡¿\"'«»()[]…"

RIGHT, ACCENT, ARTICLE, ALSO, WRONG = "right", "accent", "article", "also", "wrong"


def fold(text: str) -> str:
    """A word as two alike are told apart: case, spacing and the punctuation around it aside."""
    said = unicodedata.normalize("NFC", text.replace(_CURLY, "'"))
    return " ".join(said.casefold().split()).strip(_EDGES)


def bare(text: str) -> str:
    """Folded, and without its accents: "estacion" for "Estación"."""
    apart = unicodedata.normalize("NFD", fold(text))
    return "".join(ch for ch in apart if unicodedata.category(ch) != "Mn")


def without_article(term: str) -> str:
    """A word without what it is given with: "cuenta" for "la cuenta"; itself if it has none."""
    found = _ARTICLE.match(fold(term))
    if found and found[1] in _ARTICLES:
        return found[2]
    return fold(term)


def check(typed: str, term: str, also: Sequence[str] = ()) -> str:
    """How a word typed compares with the one expected: RIGHT; right but for an ACCENT, or for
    its ARTICLE left out; ALSO right, another way to say it; WRONG."""
    said = fold(typed)
    if not said:
        return WRONG
    for i, expected in enumerate((term, *also)):
        found = _compare(said, expected)
        if found:
            return found if i == 0 else ALSO
    return WRONG


def _compare(said: str, expected: str) -> str:
    whole, rest = fold(expected), without_article(expected)
    if said == whole:
        return RIGHT
    if said == rest:
        return ARTICLE
    plain = bare(said)
    if plain in (bare(whole), bare(rest)):
        return ACCENT
    return ""


def typable(text: str) -> bool:
    """Written in Latin letters: a word one can type on any of our keyboards."""
    letters_ = [ch for ch in text if ch.isalpha()]
    return bool(letters_) and all(unicodedata.name(ch, "").startswith("LATIN") for ch in letters_)


def letters(texts: Iterable[str], most: int = 12) -> list[str]:
    """The letters a course's words use that a plain keyboard may lack, the commonest first kept,
    in alphabetical order: "á é í ñ ó ú ü" for Spanish."""
    found: Counter[str] = Counter(
        ch
        for text in texts
        for ch in unicodedata.normalize("NFC", text).casefold()
        if ch.isalpha() and not ch.isascii() and unicodedata.name(ch, "").startswith("LATIN")
    )
    kept = [ch for ch, _ in found.most_common(most)]
    return sorted(kept, key=lambda ch: (bare(ch) or ch, ch))
