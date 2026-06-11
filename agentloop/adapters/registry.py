from __future__ import annotations

from agentloop.adapters.base import AgentAdapter
from agentloop.adapters.codex import CodexAdapter
from agentloop.adapters.shell import ShellAdapter


def get_adapter(name: str) -> AgentAdapter:
    normalized = name.lower()
    if normalized == "codex":
        return CodexAdapter()
    if normalized == "shell":
        return ShellAdapter()
    raise ValueError(f"Unknown adapter: {name}")
