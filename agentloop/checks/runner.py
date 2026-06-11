from __future__ import annotations

import subprocess
from dataclasses import dataclass

from agentloop.core.models import RenderedLoop


@dataclass(frozen=True)
class CheckResult:
    name: str
    command: str
    returncode: int
    output: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def run_checks(rendered: RenderedLoop) -> list[CheckResult]:
    results: list[CheckResult] = []
    for check, command in zip(rendered.loop.checks, rendered.commands):
        completed = subprocess.run(
            command,
            cwd=rendered.loop.workspace,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        results.append(CheckResult(name=check.name, command=command, returncode=completed.returncode, output=completed.stdout))
    return results
