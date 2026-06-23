from __future__ import annotations

import argparse
import os
import subprocess  # nosec B404
import tempfile
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from agentloop.core.engine import DryRunResult, execute_loop
from agentloop.core.rendering import RenderError
from agentloop.storage.configs import ConfigError, copy_template, create_template, default_template_data, find_config, list_configs, load_loop, write_template
from agentloop.storage.runs import find_run, list_runs, read_rerun_request, request_stop


def _parse_vars(items: list[str], vars_file: str | None) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if vars_file:
        data = yaml.safe_load(Path(vars_file).read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise SystemExit("--vars-file must contain a mapping")
        values.update(data)
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--var must use key=value: {item}")
        key, value = item.split("=", 1)
        values[key] = value
    return values


def _print_dry(result: DryRunResult) -> None:
    print("# Rendered Prompt")
    print(result.prompt)
    print("\n# Commands")
    for command in result.commands:
        print(command)


def _load_named_config(name: str, workspace: str | None, prefer: str = "loops"):
    kinds = [prefer, "templates" if prefer == "loops" else "loops"]
    last_error: Exception | None = None
    for kind in kinds:
        try:
            return load_loop(find_config(name, kind, workspace), workspace)
        except ConfigError as exc:
            last_error = exc
    raise last_error or ConfigError(f"Config not found: {name}")


def add_common_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--var", action="append", default=[], dest="vars")
    parser.add_argument("--vars-file", default=None)
    parser.add_argument("--max-iterations", type=int, default=None)
    parser.add_argument("--allow-outside-workspace", action="store_true")


def cmd_list(args: argparse.Namespace) -> int:
    for kind in ("loops", "templates", "examples"):
        print(f"{kind}:")
        for path in list_configs(kind, args.workspace):
            print(f"  {path.stem}")
    return 0


def cmd_run(args: argparse.Namespace, *, dry: bool = False, prefer: str = "loops") -> int:
    loop = _load_named_config(args.loop_name, args.workspace, prefer)
    values = _parse_vars(args.vars, args.vars_file)
    result = execute_loop(loop, values, dry=dry or getattr(args, "dry_run", False), max_iterations=args.max_iterations)
    if isinstance(result, DryRunResult):
        _print_dry(result)
    else:
        print(f"{result.status}: {result.run_id}")
        print(result.reason)
        print(result.run_dir)
    return 0


def cmd_templates_list(args: argparse.Namespace) -> int:
    for path in list_configs("templates", args.workspace):
        print(path.stem)
    return 0


def cmd_templates_show(args: argparse.Namespace) -> int:
    path = find_config(args.template_name, "templates", args.workspace)
    print(path.read_text(encoding="utf-8"))
    return 0


def _parse_variable_specs(items: list[str]) -> list[dict[str, Any]]:
    variables: list[dict[str, Any]] = []
    for item in items:
        parts = item.split(":")
        variable: dict[str, Any] = {"name": parts[0]}
        for flag in parts[1:]:
            if flag == "required":
                variable["required"] = True
            elif flag == "secret":
                variable["secret"] = True
            elif flag.startswith("default="):
                variable["default"] = flag.split("=", 1)[1]
            elif flag:
                raise SystemExit(f"Unknown variable flag in {item}: {flag}")
        variables.append(variable)
    return variables


def _parse_check_specs(items: list[str]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    for item in items:
        if "=" in item:
            name, command = item.split("=", 1)
        else:
            name, command = item, item
        checks.append({"name": name, "command": command})
    return checks


def _template_data_from_args(args: argparse.Namespace, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(existing or {})
    name = getattr(args, "template_name", None) or getattr(args, "target_name", None)
    if name:
        data["name"] = name
    if args.description is not None:
        data["description"] = args.description
    if args.adapter is not None:
        data["adapter"] = args.adapter
    if args.prompt_file is not None:
        data["prompt"] = Path(args.prompt_file).read_text(encoding="utf-8")
    elif args.prompt is not None:
        data["prompt"] = args.prompt
    if args.max_iterations is not None:
        data["max_iterations"] = args.max_iterations
    if args.variable:
        data["variables"] = _parse_variable_specs(args.variable)
    if args.check:
        data["checks"] = _parse_check_specs(args.check)
    return data


def add_template_write_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--description", default=None)
    parser.add_argument("--adapter", choices=["codex", "shell"], default=None)
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--prompt-file", default=None)
    parser.add_argument("--variable", action="append", default=[], help="name[:required][:secret][:default=value]")
    parser.add_argument("--check", action="append", default=[], help="name=command, or command")
    parser.add_argument("--max-iterations", type=int, default=None)


def cmd_templates_create(args: argparse.Namespace) -> int:
    base = default_template_data(args.template_name)
    if args.from_template:
        source = find_config(args.from_template, "templates", args.workspace)
        base = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        base["name"] = args.template_name
    data = _template_data_from_args(args, base)
    path = create_template(args.template_name, args.workspace, data=data, overwrite=args.force)
    print(path)
    return 0


def cmd_templates_copy(args: argparse.Namespace) -> int:
    path = copy_template(args.source_name, args.target_name, args.workspace, overwrite=args.force)
    print(path)
    return 0


def cmd_templates_edit(args: argparse.Namespace) -> int:
    path = find_config(args.template_name, "templates", args.workspace)
    if any([args.description is not None, args.adapter is not None, args.prompt is not None, args.prompt_file is not None, args.max_iterations is not None, args.variable, args.check]):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        data = _template_data_from_args(args, data)
        write_template(args.template_name, data, args.workspace, overwrite=True)
        print(path)
        return 0

    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        raise ConfigError("Set EDITOR or use edit flags such as --prompt-file, --check, or --variable")
    original = path.read_text(encoding="utf-8")
    with tempfile.NamedTemporaryFile("w+", suffix=".yaml", delete=False, encoding="utf-8") as handle:
        handle.write(original)
        temp_path = Path(handle.name)
    try:
        # The editor command comes from the user's local EDITOR/VISUAL setting.
        completed = subprocess.run([editor, str(temp_path)], check=False)  # nosec
        if completed.returncode != 0:
            raise ConfigError(f"Editor exited with status {completed.returncode}")
        data = yaml.safe_load(temp_path.read_text(encoding="utf-8")) or {}
        write_template(args.template_name, data, args.workspace, overwrite=True)
        print(path)
    finally:
        temp_path.unlink(missing_ok=True)
    return 0


def cmd_runs_list(args: argparse.Namespace) -> int:
    for path in list_runs(args.workspace):
        summary = path / "summary.json"
        if summary.exists():
            data = json.loads(summary.read_text(encoding="utf-8"))
            print(f"{path.name}\t{data.get('status')}\t{data.get('reason')}")
        else:
            print(path.name)
    return 0


def cmd_runs_show(args: argparse.Namespace) -> int:
    path = find_run(args.run_id, args.workspace)
    summary = path / "summary.json"
    if summary.exists():
        print(summary.read_text(encoding="utf-8"))
    else:
        print((path / "run.yaml").read_text(encoding="utf-8"))
    return 0


def cmd_runs_report(args: argparse.Namespace) -> int:
    path = find_run(args.run_id, args.workspace)
    print((path / "final_report.md").read_text(encoding="utf-8"))
    return 0


def cmd_runs_rerun(args: argparse.Namespace) -> int:
    source_path, values = read_rerun_request(args.run_id, args.workspace)
    loop = load_loop(Path(source_path), args.workspace)
    result = execute_loop(loop, values, max_iterations=args.max_iterations)
    if isinstance(result, DryRunResult):
        raise SystemExit("Cannot rerun in dry-run mode")
    print(f"{result.status}: {result.run_id}")
    print(result.reason)
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    stop_file = request_stop(args.run_id, args.workspace)
    print(f"stop requested: {stop_file}")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    path = find_run(args.run_id, args.workspace)
    for log in sorted([*path.glob("adapter_iteration_*.log"), *path.glob("checks_iteration_*.log")]):
        print(f"## {log.name}")
        print(log.read_text(encoding="utf-8"))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from agentloop.web.server import serve

    serve(host=args.host, port=args.port, workspace=args.workspace)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentloop", description="AgentLoop local-first AI workflow loops")
    parser.add_argument("--workspace", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--workspace", default=None)
    serve.set_defaults(func=cmd_serve)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--workspace", default=None)
    list_parser.set_defaults(func=cmd_list)

    run_parser = sub.add_parser("run")
    run_parser.add_argument("loop_name")
    add_common_run_options(run_parser)
    run_parser.set_defaults(func=lambda args: cmd_run(args, dry=False))

    dry_parser = sub.add_parser("dry-run")
    dry_parser.add_argument("loop_name")
    add_common_run_options(dry_parser)
    dry_parser.set_defaults(func=lambda args: cmd_run(args, dry=True))

    stop = sub.add_parser("stop")
    stop.add_argument("run_id")
    stop.add_argument("--workspace", default=None)
    stop.set_defaults(func=cmd_stop)

    logs = sub.add_parser("logs")
    logs.add_argument("run_id")
    logs.add_argument("--workspace", default=None)
    logs.set_defaults(func=cmd_logs)

    templates = sub.add_parser("templates")
    tsub = templates.add_subparsers(dest="template_command", required=True)
    tlist = tsub.add_parser("list")
    tlist.add_argument("--workspace", default=None)
    tlist.set_defaults(func=cmd_templates_list)
    show = tsub.add_parser("show")
    show.add_argument("template_name")
    show.add_argument("--workspace", default=None)
    show.set_defaults(func=cmd_templates_show)
    create = tsub.add_parser("create")
    create.add_argument("template_name")
    create.add_argument("--workspace", default=None)
    create.add_argument("--from-template", default=None)
    create.add_argument("--force", action="store_true")
    add_template_write_options(create)
    create.set_defaults(func=cmd_templates_create)
    copy = tsub.add_parser("copy")
    copy.add_argument("source_name")
    copy.add_argument("target_name")
    copy.add_argument("--workspace", default=None)
    copy.add_argument("--force", action="store_true")
    copy.set_defaults(func=cmd_templates_copy)
    edit = tsub.add_parser("edit")
    edit.add_argument("template_name")
    edit.add_argument("--workspace", default=None)
    add_template_write_options(edit)
    edit.set_defaults(func=cmd_templates_edit)
    tdry = tsub.add_parser("dry-run")
    tdry.add_argument("loop_name")
    add_common_run_options(tdry)
    tdry.set_defaults(func=lambda args: cmd_run(args, dry=True, prefer="templates"))
    trun = tsub.add_parser("run")
    trun.add_argument("loop_name")
    add_common_run_options(trun)
    trun.set_defaults(func=lambda args: cmd_run(args, dry=False, prefer="templates"))

    runs = sub.add_parser("runs")
    rsub = runs.add_subparsers(dest="runs_command", required=True)
    rlist = rsub.add_parser("list")
    rlist.add_argument("--workspace", default=None)
    rlist.set_defaults(func=cmd_runs_list)
    show_run = rsub.add_parser("show")
    show_run.add_argument("run_id")
    show_run.add_argument("--workspace", default=None)
    show_run.set_defaults(func=cmd_runs_show)
    report = rsub.add_parser("report")
    report.add_argument("run_id")
    report.add_argument("--workspace", default=None)
    report.set_defaults(func=cmd_runs_report)
    rerun = rsub.add_parser("rerun")
    rerun.add_argument("run_id")
    rerun.add_argument("--workspace", default=None)
    rerun.add_argument("--max-iterations", type=int, default=None)
    rerun.set_defaults(func=cmd_runs_rerun)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, RenderError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
