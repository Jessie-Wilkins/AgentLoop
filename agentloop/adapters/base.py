from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agentloop.core.models import RenderedLoop


@dataclass(frozen=True)
class AdapterResult:
    returncode: int
    output: str
    command: list[str]


class AgentAdapter(Protocol):
    name: str

    def run_iteration(self, rendered: RenderedLoop, iteration: int) -> AdapterResult:
        ...
