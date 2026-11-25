"""A study sheet: the words Claude writes for one page on what a question was about, and the
icons Tagnan may draw beside them. Standard library only: the brain checks the words in WSL,
the window draws them (tagnan/ui/sheetpdf.py).

The words come in fields capped by the prompt, never by the schema (the claude CLI's structured
output takes no string lengths): clean() keeps what a page can hold and says what is missing.
"""

import re
from pathlib import Path
from typing import Any

# Icons, 24 units square, drawn as strokes like those of his menu: the brain picks one for each
# side of a comparison and each step.
ICONS: dict[str, str] = {
    "book": "M12 6.5C9.5 4.8 6.5 4.5 3 5.2v13c3.5-.7 6.5-.4 9 1.3 2.5-1.7 5.5-2 9-1.3v-13c-3.5-.7-6.5-.4-9 1.3zM12 6.5v13",
    "learn": "M2 9l10-5 10 5-10 5zM6 11v5c3 2 9 2 12 0v-5",
    "pieces": "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
    "vector": "M6 18L18 6M11 6h7v7M6 16.5a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3z",
    "search": "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-3.5-3.5",
    "quote": "M10 7H6.5A1.5 1.5 0 0 0 5 8.5V12h4v1c0 2-1 3.2-3 3.8M19 7h-3.5A1.5 1.5 0 0 0 14 8.5V12h4v1c0 2-1 3.2-3 3.8",
    "gear": "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM10.6 3h2.8l.5 2.4 1.9.8 2-1.4 2 2-1.4 2 .8 1.9 2.4.5v2.8l-2.4.5-.8 1.9 1.4 2-2 2-2-1.4-1.9.8-.5 2.4h-2.8l-.5-2.4-1.9-.8-2 1.4-2-2 1.4-2-.8-1.9-2.4-.5v-2.8l2.4-.5.8-1.9-1.4-2 2-2 2 1.4 1.9-.8z",
    "cloud": "M7 18a4 4 0 0 1-.6-8 6 6 0 0 1 11.4 1.5A3.5 3.5 0 0 1 17.5 18z",
    "database": "M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
    "shield": "M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z",
    "lock": "M6 11h12v10H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3",
    "chart": "M4 20V10M10 20V4M16 20v-7M22 20H2",
    "clock": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2",
    "coin": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM14.5 9.2c-.6-.8-1.5-1.2-2.5-1.2-1.4 0-2.5.8-2.5 1.9 0 2.6 5 1.4 5 4.1 0 1.1-1.1 2-2.5 2-1.1 0-2-.4-2.6-1.2M12 6.5V8M12 16v1.5",
    "people": "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20c.8-3.6 3.3-5.5 6.5-5.5s5.7 1.9 6.5 5.5M16 4.3a3.5 3.5 0 0 1 0 6.4M18 14.8c1.9.7 3.1 2.4 3.5 5.2",
    "chat": "M4 5h16v11H9l-5 4zM8 9.5h8M8 12.5h5",
    "idea": "M9 18h6M10 21h4M12 3a6 6 0 0 0-3.6 10.8c.8.6 1.1 1.4 1.1 2.2h5c0-.8.3-1.6 1.1-2.2A6 6 0 0 0 12 3z",
    "check": "M5 12.5l4.5 4.5L19 7",
    "flask": "M9 3h6M10 3v6l-5.5 9.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3M7.5 15h9",
    "palette": "M12 3a9 9 0 0 0 0 18c1.4 0 2-1 2-2s-1-1.5-1-2.5 1-1.5 2-1.5h2a4 4 0 0 0 4-4c0-4.4-4-8-9-8zM7.5 11.5v.1M10 7.5v.1M15 7.5v.1",
    "fire": "M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2.5 1.5-4 2.5-5 .3 2 1.2 3 2.5 3.5 0-3-1.5-5.5 0-8.5z",
    "drop": "M12 3.5C9 8 6 11 6 14.5a6 6 0 0 0 12 0C18 11 15 8 12 3.5z",
    "leaf": "M5 19C5 10 10 5 20 4c-.5 9-5.5 15-14 15zM5 19l7-7",
    "globe": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.5 2.5 3.8 5.5 3.8 9s-1.3 6.5-3.8 9M12 3C9.5 5.5 8.2 8.5 8.2 12s1.3 6.5 3.8 9",
    "balance": "M12 4v16M8 20h8M5 7h14M5 7l-3 6a3 3 0 0 0 6 0zM19 7l-3 6a3 3 0 0 0 6 0z",
    "crown": "M3 8l4.5 4L12 5l4.5 7L21 8l-2 11H5z",
    "map": "M9 4L3 6.5V20l6-2.5 6 2.5 6-2.5V4l-6 2.5zM9 4v13.5M15 6.5V20",
    "eye": "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
    "bolt": "M13 2L4 14h7l-1 8 9-12h-7z",
    "tag": "M3 12V4h8l10 10-8 8zM7.5 7.5v.1",
    "layers": "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5",
    "target": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9zM12 11.5v1",
    "code": "M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16",
    "music": "M9 18V5l11-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
    "heart": "M12 20s-8-4.6-8-10.5A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 8 2.5C20 15.4 12 20 12 20z",
    "robot": "M6 8h12v11H6zM9.5 12.5v.1M14.5 12.5v.1M10 16h4M12 4v4M3 12v4M21 12v4",
    "document": "M6 3h8l5 5v13H6zM14 3v5h5M9 13h6M9 17h6",
    "sync": "M20 12a8 8 0 0 1-14.3 4.9M4 12a8 8 0 0 1 14.3-4.9M18.6 3.2v4.1h-4.1M5.4 20.8v-4.1h4.1",
    "warning": "M12 3.5 22 20.5H2zM12 10v4.5M12 17.5v.5",
}
ICON_NAMES = tuple(ICONS)
# The marks and the trap's sign: drawn by the page, not chosen by the brain.
MARKS = {
    "yes": "M5 12.5l4.5 4.5L19 7",
    "no": "M6 6l12 12M18 6L6 18",
    "trap": ICONS["warning"],
}

_TEXT: dict[str, Any] = {"type": "string"}
_ICON: dict[str, Any] = {"type": "string", "enum": list(ICON_NAMES)}


def _object(**properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


_SIDE = _object(name=_TEXT, what=_TEXT, icon=_ICON)
_CELL = _object(good={"type": "boolean"}, text=_TEXT)
SCHEMA: dict[str, Any] = _object(
    title=_TEXT,
    tagline=_TEXT,
    versus=_object(
        left=_SIDE,
        right=_SIDE,
        rows={"type": "array", "items": _object(label=_TEXT, left=_CELL, right=_CELL)},
    ),
    steps=_object(
        title=_TEXT,
        list={"type": "array", "items": _object(name=_TEXT, what=_TEXT, icon=_ICON)},
    ),
    terms={"type": "array", "items": _object(name=_TEXT, what=_TEXT)},
    trap=_TEXT,
    remember=_TEXT,
)

# What a page holds. The prompt asks for fewer words; past these, the words are cut.
MAX_WORDS = {
    "title": 9,
    "tagline": 22,
    "side": 4,
    "what": 7,
    "label": 3,
    "cell": 7,
    "steps": 6,
    "step": 3,
    "term": 4,
    "definition": 14,
    "trap": 22,
    "remember": 20,
}
MAX_ROWS, MIN_ROWS = 3, 2
MAX_STEPS, MIN_STEPS = 5, 3
MAX_TERMS = 3


def words(text: object, most: int) -> str:
    """The text on one line, cut at `most` words (with an ellipsis), stripped of markdown."""
    cleaned = " ".join(re.sub(r"[*_`#]+", "", str(text or "")).split()).strip(" \"'")
    parts = cleaned.split(" ")
    if len(parts) <= most:
        return cleaned
    return " ".join(parts[:most]).rstrip(",;:.") + "…"


def _icon(name: object) -> str:
    return str(name) if str(name) in ICONS else "idea"


def clean(data: object) -> dict[str, Any]:
    """The brain's answer as a page can hold it: words cut where too long, empty rows and steps
    left out. ValueError when a page cannot be made of it."""
    if not isinstance(data, dict):
        raise ValueError("not an object")
    title = words(data.get("title"), MAX_WORDS["title"])
    tagline = words(data.get("tagline"), MAX_WORDS["tagline"])
    if not title or not tagline:
        raise ValueError("no title or no tagline")

    versus: dict[str, Any] = {}
    v = data.get("versus")
    if isinstance(v, dict) and isinstance(v.get("left"), dict) and isinstance(v.get("right"), dict):
        sides = {
            k: {
                "name": words(v[k].get("name"), MAX_WORDS["side"]),
                "what": words(v[k].get("what"), MAX_WORDS["what"]),
                "icon": _icon(v[k].get("icon")),
            }
            for k in ("left", "right")
        }
        rows = []
        for row in v.get("rows") or []:
            if not isinstance(row, dict):
                continue
            cells = {}
            for k in ("left", "right"):
                found = row.get(k)
                cell: dict[str, Any] = found if isinstance(found, dict) else {}
                cells[k] = {
                    "good": cell.get("good") is True,
                    "text": words(cell.get("text"), MAX_WORDS["cell"]),
                }
            label = words(row.get("label"), MAX_WORDS["label"])
            if label and cells["left"]["text"] and cells["right"]["text"]:
                rows.append({"label": label, **cells})
        if sides["left"]["name"] and sides["right"]["name"] and len(rows) >= MIN_ROWS:
            versus = {**sides, "rows": rows[:MAX_ROWS]}

    steps: dict[str, Any] = {}
    s = data.get("steps")
    if isinstance(s, dict):
        found = [
            {
                "name": words(x.get("name"), MAX_WORDS["step"]),
                "what": words(x.get("what"), MAX_WORDS["what"]),
                "icon": _icon(x.get("icon")),
            }
            for x in s.get("list") or []
            if isinstance(x, dict)
        ]
        found = [x for x in found if x["name"]]
        if len(found) >= MIN_STEPS:
            steps = {"title": words(s.get("title"), MAX_WORDS["steps"]), "list": found[:MAX_STEPS]}
    if not versus and not steps:
        raise ValueError("neither a comparison nor steps")

    terms = [
        {
            "name": words(t.get("name"), MAX_WORDS["term"]),
            "what": words(t.get("what"), MAX_WORDS["definition"]),
        }
        for t in data.get("terms") or []
        if isinstance(t, dict)
    ]
    terms = [t for t in terms if t["name"] and t["what"]][:MAX_TERMS]
    return {
        "title": title,
        "tagline": tagline,
        "versus": versus,
        "steps": steps,
        "terms": terms,
        "trap": words(data.get("trap"), MAX_WORDS["trap"]),
        "remember": words(data.get("remember"), MAX_WORDS["remember"]),
    }


# Characters Windows refuses in a file name, and those no file name should hold.
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def file_name(title: str) -> str:
    """The PDF's name in Downloads: "Tagnan – RAG or fine-tuning.pdf"."""
    safe = " ".join(_UNSAFE.sub(" ", title).split()).strip(" .")[:80].strip(" .")
    return f"Tagnan – {safe or 'Study sheet'}.pdf"


def free_path(folder: Path, name: str) -> Path:
    """Where to save without overwriting anything: the name, else "… (2).pdf", "… (3).pdf"."""
    path = folder / name
    stem, suffix = path.stem, path.suffix
    number = 2
    while path.exists():
        path = folder / f"{stem} ({number}){suffix}"
        number += 1
    return path
