from __future__ import annotations

import subprocess

from agentloop.adapters.base import AdapterResult
from agentloop.core.models import RenderedLoop


class CodexAdapter:
    name = "codex"

    def run_iteration(self, rendered: RenderedLoop, iteration: int) -> AdapterResult:
        command = ["codex", "exec", rendered.prompt]
        completed = subprocess.run(
            command,
            cwd=rendered.loop.workspace,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        return AdapterResult(returncode=completed.returncode, output=completed.stdout, command=command)
