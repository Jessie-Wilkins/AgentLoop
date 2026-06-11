from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CONFIG_DIR = ".agentloop"
RUNS_DIR = ".agentloop-runs"


@dataclass(frozen=True)
class CheckConfig:
    name: str
    command: str


@dataclass(frozen=True)
class VariableConfig:
    name: str
    required: bool = False
    default: Any = None
    secret: bool = False
    description: str = ""


@dataclass(frozen=True)
class LoopConfig:
    name: str
    description: str
    adapter: str
    prompt: str
    checks: list[CheckConfig]
    variables: list[VariableConfig] = field(default_factory=list)
    max_iterations: int = 3
    workspace: Path = field(default_factory=Path.cwd)
    source_path: Path | None = None


@dataclass(frozen=True)
class RenderedLoop:
    loop: LoopConfig
    values: dict[str, Any]
    prompt: str
    commands: list[str]


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str
    iterations: int
    reason: str
    run_dir: Path
