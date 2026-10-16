"""The optional config file (~/.config/tagnan/config.toml, see config.example.toml).

Every key has a default; an unknown key or a wrong value stops with a clear message.
"""

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from tagnan.scheduler import Rhythm


@dataclass(frozen=True)
class Brain:
    model: str = "sonnet"  # writes the questions
    explain_model: str = "sonnet"  # « Explique-moi plus »


@dataclass(frozen=True)
class Config:
    exam: str = "aif-c01"
    rhythm: Rhythm = field(default_factory=Rhythm)
    brain: Brain = field(default_factory=Brain)


def _section(cls: type[Any], data: object, name: str) -> Any:
    if not isinstance(data, dict):
        raise ValueError(f"config : [{name}] doit être une section")
    known = {f.name: f.type for f in fields(cls)}
    unknown = sorted(set(data) - set(known))
    if unknown:
        raise ValueError(f"config : clé inconnue dans [{name}] : {', '.join(unknown)}")
    try:
        return cls(**data)
    except (TypeError, ValueError) as error:
        raise ValueError(f"config : [{name}] : {error}") from None


def load(path: Path) -> Config:
    if not path.exists():
        return Config()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"config : {path} illisible : {error}") from None
    unknown = sorted(set(data) - {"exam", "rhythm", "brain"})
    if unknown:
        raise ValueError(f"config : clé inconnue : {', '.join(unknown)}")
    exam = data.get("exam", Config.exam)
    if not isinstance(exam, str):
        raise ValueError("config : exam doit être un nom de fichier de exam/, sans .toml")
    return Config(
        exam=exam,
        rhythm=_section(Rhythm, data.get("rhythm", {}), "rhythm"),
        brain=_section(Brain, data.get("brain", {}), "brain"),
    )
