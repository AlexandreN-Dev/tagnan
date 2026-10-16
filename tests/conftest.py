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


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


@pytest.fixture
def game(store: Store, bp: Blueprint) -> Game:
    return Game(store, bp, random.Random(7))
