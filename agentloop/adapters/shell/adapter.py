from __future__ import annotations

import subprocess

from agentloop.adapters.base import AdapterResult
from agentloop.core.models import RenderedLoop


class ShellAdapter:
    name = "shell"

    def run_iteration(self, rendered: RenderedLoop, iteration: int) -> AdapterResult:
        completed = subprocess.run(
            rendered.prompt,
            cwd=rendered.loop.workspace,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        return AdapterResult(returncode=completed.returncode, output=completed.stdout, command=["sh", "-c", rendered.prompt])
