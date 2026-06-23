from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentloop.core.models import RenderedLoop
from agentloop.core.processes import run_interruptible


@dataclass(frozen=True)
class CheckResult:
    name: str
    command: str
    returncode: int
    output: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def run_checks(rendered: RenderedLoop, stop_file: Path | None = None) -> list[CheckResult]:
    results: list[CheckResult] = []
    for check, command in zip(rendered.loop.checks, rendered.commands):
        completed = run_interruptible(
            command,
            cwd=rendered.loop.workspace,
            # Checks are explicit local workflow commands.
            shell=True,  # nosec B604
            stop_file=stop_file,
        )
        results.append(CheckResult(name=check.name, command=command, returncode=completed.returncode, output=completed.stdout))
        if stop_file is not None and stop_file.exists():
            break
    return results
