from __future__ import annotations

from pathlib import Path

from agentloop.adapters.base import AdapterResult
from agentloop.core.models import RenderedLoop
from agentloop.core.processes import run_interruptible
from agentloop.security.redaction import redact_text, secret_names
from agentloop.storage.runs import append_run_event


class ShellAdapter:
    name = "shell"

    def run_iteration(self, rendered: RenderedLoop, iteration: int, stop_file: Path | None = None) -> AdapterResult:
        live_log = stop_file.parent / f"adapter_iteration_{iteration:03d}.live.log" if stop_file is not None else None
        secrets = secret_names(rendered.loop.variables)

        def append_output(chunk: str) -> None:
            if live_log is not None:
                with live_log.open("a", encoding="utf-8") as handle:
                    handle.write(redact_text(chunk, rendered.values, secrets))

        def append_heartbeat(elapsed: float) -> None:
            if stop_file is not None:
                append_run_event(stop_file.parent, f"iteration {iteration}: adapter still running ({int(elapsed)}s elapsed)")

        completed = run_interruptible(
            rendered.prompt,
            cwd=rendered.loop.workspace,
            # The shell adapter exists to run local workflow commands.
            shell=True,  # nosec B604
            stop_file=stop_file,
            output_callback=append_output,
            heartbeat_interval=30,
            heartbeat_callback=append_heartbeat,
        )
        return AdapterResult(returncode=completed.returncode, output=completed.stdout, command=["sh", "-c", rendered.prompt])
