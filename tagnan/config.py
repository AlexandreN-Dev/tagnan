"""The optional config file (~/.config/tagnan/config.toml, see config.example.toml).

Every key has a default; an unknown key or a wrong value stops with a clear message.
"""

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, NamedTuple

from tagnan.scheduler import Rhythm

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")  # claude --effort


class Model(NamedTuple):
    """A model offered to write the questions (the setup, his menu), with its effort."""

    model: str
    effort: str
    label: str
    hint: str

    @property
    def name(self) -> str:
        return self.label.partition(",")[0]


# From the most capable down to the quickest.
MODELS = (
    Model("claude-fable-5-1", "max", "Fable 5.1, effort max", "the most capable, the slowest"),
    Model("claude-opus-5-5", "max", "Opus 5.5, effort max", "fine, minutes per batch"),
    Model("claude-sonnet-5-5", "high", "Sonnet 5.5, effort high", "quick, lighter on your limits"),
    Model("claude-haiku-5-5", "high", "Haiku 5.5, effort high", "the quickest, plainer questions"),
)


def find_model(model: str) -> Model | None:
    return next((m for m in MODELS if m.model == model), None)


@dataclass(frozen=True)
class Brain:
    model: str = "claude-opus-5-5"  # writes the questions
    explain_model: str = "claude-opus-5-5"  # "Tell me more"
    effort: str = "max"
    explain_effort: str = "max"

    def __post_init__(self) -> None:
        for name in ("effort", "explain_effort"):
            if getattr(self, name) not in EFFORT_LEVELS:
                raise ValueError(f"{name} must be one of: {', '.join(EFFORT_LEVELS)}")


@dataclass(frozen=True)
class Config:
    exam: str = "aif-c01"
    rhythm: Rhythm = field(default_factory=Rhythm)
    brain: Brain = field(default_factory=Brain)


def _section(cls: type[Any], data: object, name: str) -> Any:
    if not isinstance(data, dict):
        raise ValueError(f"config: [{name}] must be a section")
    known = {f.name: f.type for f in fields(cls)}
    unknown = sorted(set(data) - set(known))
    if unknown:
        raise ValueError(f"config: unknown key in [{name}]: {', '.join(unknown)}")
    try:
        return cls(**data)
    except (TypeError, ValueError) as error:
        raise ValueError(f"config: [{name}]: {error}") from None


def load(path: Path) -> Config:
    if not path.exists():
        return Config()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"config: cannot read {path}: {error}") from None
    unknown = sorted(set(data) - {"exam", "rhythm", "brain"})
    if unknown:
        raise ValueError(f"config: unknown key: {', '.join(unknown)}")
    exam = data.get("exam", Config.exam)
    if not isinstance(exam, str):
        raise ValueError("config: exam must be the name of a file in exam/, without .toml")
    return Config(
        exam=exam,
        rhythm=_section(Rhythm, data.get("rhythm", {}), "rhythm"),
        brain=_section(Brain, data.get("brain", {}), "brain"),
    )
