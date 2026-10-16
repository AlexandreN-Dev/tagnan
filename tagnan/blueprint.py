"""The exam's blueprint: its domains, their weights and task statements (exam/*.toml)."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from tagnan.paths import EXAMS_DIR


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    notions: str


@dataclass(frozen=True)
class Domain:
    id: int
    name: str
    weight: float
    tasks: tuple[Task, ...]


@dataclass(frozen=True)
class Blueprint:
    key: str  # file name without extension, e.g. "aif-c01"
    code: str
    name: str
    kinds: tuple[str, ...]
    services: tuple[str, ...]
    domains: tuple[Domain, ...]

    def domain(self, domain_id: int) -> Domain:
        for domain in self.domains:
            if domain.id == domain_id:
                return domain
        raise KeyError(domain_id)

    def task_ids(self, domain_id: int) -> tuple[str, ...]:
        return tuple(task.id for task in self.domain(domain_id).tasks)


def load(key: str, directory: Path = EXAMS_DIR) -> Blueprint:
    path = directory / f"{key}.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"unknown exam: {key} (no file {path})") from None
    domains = tuple(
        Domain(
            id=int(d["id"]),
            name=str(d["name"]),
            weight=float(d["weight"]),
            tasks=tuple(
                Task(
                    id=str(t["id"]),
                    title=str(t["title"]),
                    notions=" ".join(str(t["notions"]).split()),
                )
                for t in d["tasks"]
            ),
        )
        for d in data["domains"]
    )
    if not domains or any(not d.tasks or d.weight <= 0 for d in domains):
        raise ValueError(f"{path}: each domain needs a weight and at least one task")
    return Blueprint(
        key=key,
        code=str(data["code"]),
        name=str(data["name"]),
        kinds=tuple(str(k) for k in data.get("kinds", ["single"])),
        services=tuple(str(s) for s in data.get("services", [])),
        domains=domains,
    )
