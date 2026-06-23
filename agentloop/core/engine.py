from __future__ import annotations

import traceback
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Callable

from agentloop.adapters.registry import get_adapter
from agentloop.checks.runner import CheckResult, run_checks
from agentloop.core.models import LoopConfig, RunResult
from agentloop.core.rendering import render_loop
from agentloop.storage.runs import (
    append_run_event,
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


def _format_check_feedback(results: list[CheckResult]) -> str:
    lines = ["Previous checks failed. Fix the issues below, then rerun the required tests and scans:"]
    for result in results:
        if result.passed:
            continue
        output = result.output.strip() or "(no output)"
        lines.append(f"- {result.name} exited {result.returncode}: `{result.command}`")
        lines.append(output[-2000:])
    return "\n".join(lines)


def execute_loop(
    loop: LoopConfig,
    values: dict[str, object] | None = None,
    *,
    dry: bool = False,
    max_iterations: int | None = None,
    repeat_failure_limit: int = 2,
    on_run_started: Callable[[str, Path], None] | None = None,
) -> RunResult | DryRunResult:
    rendered = render_loop(loop, values or {})
    if dry:
        return DryRunResult(prompt=rendered.prompt, commands=rendered.commands, values=rendered.values)

    run_id = new_run_id(loop.name)
    run_dir = create_run_dir(loop.workspace, run_id)
    write_run_start(run_dir, rendered, run_id)
    if on_run_started is not None:
        on_run_started(run_id, run_dir)

    adapter = get_adapter(loop.adapter)
    limit = max_iterations or loop.max_iterations
    previous_signature = ""
    repeat_count = 0
    status = "failed"
    reason = "max iterations reached"
    iterations = 0
    extra: dict[str, object] = {}
    check_feedback = ""

    try:
        for iteration in range(1, limit + 1):
            iterations = iteration
            stop_file = run_dir / "STOP"
            if stop_file.exists():
                status = "stopped"
                reason = "stop requested"
                append_run_event(run_dir, "stop file detected before starting iteration")
                break

            iteration_rendered = (
                replace(rendered, prompt=f"{rendered.prompt}\n\n{check_feedback}") if check_feedback else rendered
            )
            write_iteration_prompt(run_dir, iteration_rendered, iteration)
            append_run_event(run_dir, f"iteration {iteration}: starting adapter")
            adapter_result = adapter.run_iteration(iteration_rendered, iteration, stop_file)
            write_adapter_log(run_dir, iteration_rendered, iteration, adapter_result.command, adapter_result.returncode, adapter_result.output)

            if stop_file.exists():
                status = "stopped"
                reason = "stop requested"
                append_run_event(run_dir, f"iteration {iteration}: stopped after adapter")
                break

            output_lines = [line.strip() for line in adapter_result.output.splitlines() if line.strip()]
            output_reported_blocked = any(line.startswith("BLOCKED:") for line in output_lines[-3:])
            if adapter_result.blocked or output_reported_blocked:
                status = "blocked"
                reason = "adapter reported BLOCKED:"
                append_run_event(run_dir, f"iteration {iteration}: adapter reported BLOCKED")
                break

            append_run_event(run_dir, f"iteration {iteration}: starting checks")
            check_results = run_checks(rendered, stop_file)
            write_checks_log(run_dir, rendered, iteration, check_results)

            if stop_file.exists():
                status = "stopped"
                reason = "stop requested"
                append_run_event(run_dir, f"iteration {iteration}: stopped after checks")
                break

            if all(result.passed for result in check_results):
                status = "passed"
                reason = "all checks passed"
                append_run_event(run_dir, f"iteration {iteration}: all checks passed")
                break

            signature = _failure_signature(check_results)
            check_feedback = _format_check_feedback(check_results)
            repeat_count = repeat_count + 1 if signature and signature == previous_signature else 1
            previous_signature = signature
            if repeat_count >= repeat_failure_limit:
                status = "failed"
                reason = "same failure repeated"
                extra["failure_signature"] = signature
                append_run_event(run_dir, f"iteration {iteration}: repeated failure limit reached")
                break
        else:
            status = "failed"
            reason = "max iterations reached"
    except Exception as exc:
        status = "failed"
        reason = f"run error: {type(exc).__name__}: {exc}"
        error_log = traceback.format_exc()
        (run_dir / "error.log").write_text(error_log, encoding="utf-8")
        append_run_event(run_dir, reason)
        extra["error"] = str(exc)
        extra["error_type"] = type(exc).__name__

    result = RunResult(run_id=run_id, status=status, iterations=iterations, reason=reason, run_dir=run_dir)
    write_summary(run_dir, result, extra)
    return result


def stop_file_for_run(run_dir: Path) -> Path:
    return run_dir / "STOP"
