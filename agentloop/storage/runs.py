from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agentloop.core.models import LoopConfig, RenderedLoop, RunResult
from agentloop.security.redaction import redact_mapping, redact_text, secret_names
from agentloop.storage.paths import runs_dir


def new_run_id(loop_name: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{loop_name}-{uuid.uuid4().hex[:8]}"


def create_run_dir(workspace: str | Path | None, run_id: str) -> Path:
    path = runs_dir(workspace) / run_id
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_run_start(run_dir: Path, rendered: RenderedLoop, run_id: str) -> None:
    loop = rendered.loop
    secrets = secret_names(loop.variables)
    run_data = {
        "run_id": run_id,
        "loop": loop.name,
        "adapter": loop.adapter,
        "source_path": str(loop.source_path) if loop.source_path else None,
        "workspace": str(loop.workspace),
        "max_iterations": loop.max_iterations,
        "status": "running",
    }
    (run_dir / "run.yaml").write_text(yaml.safe_dump(run_data, sort_keys=False), encoding="utf-8")
    safe_values = redact_mapping(rendered.values, secrets)
    (run_dir / "variables.yaml").write_text(yaml.safe_dump(safe_values, sort_keys=False), encoding="utf-8")
    private_values = run_dir / ".variables.private.yaml"
    private_values.write_text(yaml.safe_dump(rendered.values, sort_keys=False), encoding="utf-8")
    private_values.chmod(0o600)


def write_iteration_prompt(run_dir: Path, rendered: RenderedLoop, iteration: int) -> None:
    secrets = secret_names(rendered.loop.variables)
    prompt = redact_text(rendered.prompt, rendered.values, secrets)
    (run_dir / f"prompt_iteration_{iteration:03d}.txt").write_text(prompt, encoding="utf-8")


def write_adapter_log(run_dir: Path, rendered: RenderedLoop, iteration: int, command: list[str], returncode: int, output: str) -> None:
    secrets = secret_names(rendered.loop.variables)
    body = f"$ {' '.join(command)}\nreturncode: {returncode}\n\n{output}"
    (run_dir / f"adapter_iteration_{iteration:03d}.log").write_text(
        redact_text(body, rendered.values, secrets),
        encoding="utf-8",
    )


def write_checks_log(run_dir: Path, rendered: RenderedLoop, iteration: int, results: list[Any]) -> None:
    secrets = secret_names(rendered.loop.variables)
    parts = []
    for result in results:
        parts.append(f"$ {result.command}\nreturncode: {result.returncode}\n{result.output}")
    (run_dir / f"checks_iteration_{iteration:03d}.log").write_text(
        redact_text("\n\n".join(parts), rendered.values, secrets),
        encoding="utf-8",
    )


def write_summary(run_dir: Path, result: RunResult, extra: dict[str, Any] | None = None) -> None:
    payload = {
        "run_id": result.run_id,
        "status": result.status,
        "iterations": result.iterations,
        "reason": result.reason,
        "run_dir": str(result.run_dir),
    }
    payload.update(extra or {})
    (run_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report = [
        f"# AgentLoop Run {result.run_id}",
        "",
        f"- Status: {result.status}",
        f"- Iterations: {result.iterations}",
        f"- Reason: {result.reason}",
    ]
    (run_dir / "final_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    run_yaml = run_dir / "run.yaml"
    if run_yaml.exists():
        data = yaml.safe_load(run_yaml.read_text(encoding="utf-8")) or {}
        data["status"] = result.status
        data["reason"] = result.reason
        data["iterations"] = result.iterations
        run_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def list_runs(workspace: str | Path | None = None) -> list[Path]:
    root = runs_dir(workspace)
    if not root.exists():
        return []
    return sorted([path for path in root.iterdir() if path.is_dir()], reverse=True)


def find_run(run_id: str, workspace: str | Path | None = None) -> Path:
    path = runs_dir(workspace) / run_id
    if not path.exists():
        raise FileNotFoundError(f"Run not found: {run_id}")
    return path


def request_stop(run_id: str, workspace: str | Path | None = None) -> Path:
    path = find_run(run_id, workspace)
    stop_file = path / "STOP"
    stop_file.write_text("stop requested\n", encoding="utf-8")
    return stop_file
