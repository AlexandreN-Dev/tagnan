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
        "topic": "Bedrock Guardrails, sujets refusés",
        "difficulty": "moyen",
        "kind": "single",
        "stem": (
            "Une équipe veut que son assistant bâti sur Amazon Bedrock refuse les sujets hors"
            " périmètre. Quelle fonctionnalité utiliser ?"
        ),
        "choices": [
            "Amazon Bedrock Guardrails",
            "Amazon Comprehend",
            "Amazon Kendra",
            "Amazon SageMaker Clarify",
        ],
        "answers": [0],
        "explanation": "Guardrails applique des sujets refusés aux entrées et aux sorties.",
        "why_wrong": [
            "",
            "Comprehend analyse du texte, il ne bloque pas un assistant.",
            "Kendra est un moteur de recherche.",
            "Clarify mesure les biais d'un modèle.",
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
