import random
from typing import Any

import pytest

from tagnan import blueprint
from tagnan.blueprint import Blueprint
from tagnan.game import Game
from tagnan.store import Store


@pytest.fixture
def bp() -> Blueprint:
    return blueprint.load("aif-c01")


def pottery_data() -> dict[str, Any]:
    """A course as the brain draws it up (brain.plan's "course")."""
    return {
        "key": "pottery",
        "code": "Pottery",
        "name": "Pottery",
        "exam": False,
        "guidance": "Ask about techniques every potter agrees on.",
        "reference": 'a book or chapter, for example "Clay and Glazes for the Potter, ch. 4"',
        "kinds": ["single"],
        "services": [],
        "domains": [
            {
                "id": 1,
                "name": "Clay bodies",
                "weight": 50,
                "tasks": [{"id": "1.1", "title": "Know the clays", "notions": "earthenware"}],
            },
            {
                "id": 2,
                "name": "Glazes and firing",
                "weight": 50,
                "tasks": [{"id": "2.1", "title": "Fire a kiln", "notions": "bisque, cones"}],
            },
        ],
    }


def pottery_question(**changes: Any) -> dict[str, Any]:
    data = {
        "domain": 2,
        "task": "2.1",
        "topic": "bisque firing",
        "stem": "Why is a pot bisque fired before it is glazed?",
        "choices": [
            "To make it porous yet strong",
            "To melt the glaze",
            "To color it",
            "To dry it",
        ],
        "why_wrong": [
            "",
            "No glaze yet.",
            "Firing does not color bare clay.",
            "Drying comes first.",
        ],
        "reference": "Clay and Glazes for the Potter, ch. 4",
    }
    return question_data(**{**data, **changes})


def question_data(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "domain": 3,
        "task": "3.1",
        "topic": "Bedrock Guardrails, denied topics",
        "difficulty": "medium",
        "kind": "single",
        "stem": (
            "A team wants its assistant built on Amazon Bedrock to refuse requests outside its"
            " scope. Which feature should it use?"
        ),
        "choices": [
            "Amazon Bedrock Guardrails",
            "Amazon Comprehend",
            "Amazon Kendra",
            "Amazon SageMaker Clarify",
        ],
        "answers": [0],
        "explanation": "Guardrails applies denied topics to inputs and outputs.",
        "why_wrong": [
            "",
            "Comprehend analyzes text; it does not block an assistant.",
            "Kendra is a search engine.",
            "Clarify measures a model's bias.",
        ],
        "reference": "Amazon Bedrock User Guide, Guardrails",
    }
    data.update(changes)
    return data


def sheet_data(**changes: Any) -> dict[str, Any]:
    """A study sheet's words as the brain answers them (tagnan.studysheet.SCHEMA)."""
    side = {"name": "Fine-tuning", "what": "learns by heart", "icon": "learn"}
    data: dict[str, Any] = {
        "title": "RAG or fine-tuning?",
        "tagline": "Facts that change every week? Hand the model the pages. Don't retrain it.",
        "versus": {
            "left": side,
            "right": {"name": "RAG", "what": "reads, then answers", "icon": "book"},
            "rows": [
                {
                    "label": "To update",
                    "left": {"good": False, "text": "Retrain: hours, $$$"},
                    "right": {"good": True, "text": "Sync: minutes"},
                },
                {
                    "label": "Best for",
                    "left": {"good": True, "text": "Style, tone, format"},
                    "right": {"good": True, "text": "Facts that change"},
                },
                {
                    "label": "Sources",
                    "left": {"good": False, "text": "None to show"},
                    "right": {"good": True, "text": "Cites its passages"},
                },
            ],
        },
        "steps": {
            "title": "How RAG answers",
            "list": [
                {"name": "Chunk", "what": "docs into passages", "icon": "pieces"},
                {"name": "Embed", "what": "each as a vector", "icon": "vector"},
                {"name": "Retrieve", "what": "the closest ones", "icon": "search"},
                {"name": "Answer", "what": "and cite them", "icon": "quote"},
            ],
        },
        "terms": [
            {"name": "Knowledge Bases", "what": "Bedrock's managed RAG, from your own documents."},
            {"name": "Embedding", "what": "Text as numbers that keep its meaning."},
            {"name": "Vector store", "what": "Finds the nearest meaning, fast."},
        ],
        "trap": "Fine-tuning to teach facts that change: slow, costly, and stale by next week.",
        "remember": "RAG is an open-book exam. Fine-tuning is learning by heart.",
    }
    data.update(changes)
    return data


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


@pytest.fixture
def game(store: Store, bp: Blueprint) -> Game:
    return Game(store, bp, random.Random(7))
