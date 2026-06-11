from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentloop.adapters.registry import get_adapter
from agentloop.checks.runner import CheckResult, run_checks
from agentloop.core.models import LoopConfig, RunResult
from agentloop.core.rendering import render_loop
from agentloop.storage.runs import (
    create_run_dir,
    new_run_id,
    write_adapter_log,
    write_checks_log,
    write_iteration_prompt,
    write_run_start,
    write_summary,
)


@dataclass(frozen=True)
class DryRunResult:
    prompt: str
    commands: list[str]
    values: dict[str, object]


def dry_run(loop: LoopConfig, values: dict[str, object] | None = None) -> DryRunResult:
    rendered = render_loop(loop, values or {})
    return DryRunResult(prompt=rendered.prompt, commands=rendered.commands, values=rendered.values)


def _failure_signature(results: list[CheckResult]) -> str:
    return "|".join(f"{result.command}:{result.returncode}:{result.output[-500:]}" for result in results if not result.passed)


def execute_loop(
    loop: LoopConfig,
    values: dict[str, object] | None = None,
    *,
    dry: bool = False,
    max_iterations: int | None = None,
    repeat_failure_limit: int = 2,
) -> RunResult | DryRunResult:
    rendered = render_loop(loop, values or {})
    if dry:
        return DryRunResult(prompt=rendered.prompt, commands=rendered.commands, values=rendered.values)

    run_id = new_run_id(loop.name)
    run_dir = create_run_dir(loop.workspace, run_id)
    write_run_start(run_dir, rendered, run_id)

    adapter = get_adapter(loop.adapter)
    limit = max_iterations or loop.max_iterations
    previous_signature = ""
    repeat_count = 0
    status = "failed"
    reason = "max iterations reached"
    iterations = 0
    extra: dict[str, object] = {}

    for iteration in range(1, limit + 1):
        iterations = iteration
        if (run_dir / "STOP").exists():
            status = "stopped"
            reason = "stop requested"
            break

        write_iteration_prompt(run_dir, rendered, iteration)
        adapter_result = adapter.run_iteration(rendered, iteration)
        write_adapter_log(run_dir, rendered, iteration, adapter_result.command, adapter_result.returncode, adapter_result.output)

        if "BLOCKED:" in adapter_result.output:
            status = "blocked"
            reason = "adapter reported BLOCKED:"
            break

        check_results = run_checks(rendered)
        write_checks_log(run_dir, rendered, iteration, check_results)

        if all(result.passed for result in check_results):
            status = "passed"
            reason = "all checks passed"
            break

        signature = _failure_signature(check_results)
        repeat_count = repeat_count + 1 if signature and signature == previous_signature else 1
        previous_signature = signature
        if repeat_count >= repeat_failure_limit:
            status = "failed"
            reason = "same failure repeated"
            extra["failure_signature"] = signature
            break
    else:
        status = "failed"
        reason = "max iterations reached"

    result = RunResult(run_id=run_id, status=status, iterations=iterations, reason=reason, run_dir=run_dir)
    write_summary(run_dir, result, extra)
    return result


def stop_file_for_run(run_dir: Path) -> Path:
    return run_dir / "STOP"
