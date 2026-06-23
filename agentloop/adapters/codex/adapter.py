from __future__ import annotations

import os
import shutil
from pathlib import Path

from agentloop.adapters.base import AdapterResult
from agentloop.core.models import RenderedLoop
from agentloop.core.processes import run_interruptible
from agentloop.security.redaction import redact_text, secret_names
from agentloop.storage.runs import append_run_event


class CodexAdapter:
    name = "codex"

    def _codex_command_prefix(self) -> list[str]:
        candidates = [
            os.environ.get("AGENTLOOP_CODEX_BIN"),
            shutil.which("codex"),
            str(Path.home() / ".npm-global" / "bin" / "codex"),
            "/home/ubuntu/.npm-global/bin/codex",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists() and os.access(candidate, os.X_OK):
                return [candidate]
        npx_bin = shutil.which("npx")
        if npx_bin:
            return [npx_bin, "--yes", "@openai/codex"]
        raise FileNotFoundError("Codex binary not found. Install Codex or set AGENTLOOP_CODEX_BIN to the executable path.")

    def _codex_binary(self) -> str:
        return self._codex_command_prefix()[0]

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

        command = [
            *self._codex_command_prefix(),
            "exec",
            "--sandbox",
            "danger-full-access",
            "-c",
            'approval_policy="never"',
            rendered.prompt,
        ]
        completed = run_interruptible(
            command,
            cwd=rendered.loop.workspace,
            stop_file=stop_file,
            output_callback=append_output,
            heartbeat_interval=30,
            heartbeat_callback=append_heartbeat,
        )
        final_lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        blocked = any(line.startswith("BLOCKED:") for line in final_lines[-3:])
        return AdapterResult(returncode=completed.returncode, output=completed.stdout, command=command, blocked=blocked)
