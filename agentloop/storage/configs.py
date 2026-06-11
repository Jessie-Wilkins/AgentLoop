from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml

from agentloop.core.models import CheckConfig, LoopConfig, VariableConfig
from agentloop.storage.paths import examples_dir, loops_dir, prompts_dir, templates_dir, workspace_path


class ConfigError(ValueError):
    pass


_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def validate_config_name(name: str) -> str:
    if not name or not _NAME_PATTERN.match(name):
        raise ConfigError("Template names must use letters, numbers, dots, underscores, or hyphens")
    if ".." in Path(name).parts or "/" in name or "\\" in name:
        raise ConfigError("Template names cannot contain path separators")
    return name


def template_path(name: str, workspace: str | Path | None = None) -> Path:
    safe_name = validate_config_name(name)
    return templates_dir(workspace) / f"{safe_name}.yaml"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Config not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config must be a mapping: {path}")
    return data


def _load_prompt(prompt_ref: str, source_path: Path, workspace: Path) -> str:
    prompt_path = Path(prompt_ref)
    candidates = []
    if prompt_path.is_absolute():
        candidates.append(prompt_path)
    else:
        candidates.extend([source_path.parent / prompt_path, prompts_dir(workspace) / prompt_path])
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return prompt_ref


def _parse_variables(items: Any) -> list[VariableConfig]:
    variables: list[VariableConfig] = []
    for item in items or []:
        if isinstance(item, str):
            variables.append(VariableConfig(name=item, required=True))
        elif isinstance(item, dict):
            name = item.get("name")
            if not name:
                raise ConfigError("Variable entries require a name")
            variables.append(
                VariableConfig(
                    name=str(name),
                    required=bool(item.get("required", False)),
                    default=item.get("default"),
                    secret=bool(item.get("secret", False)),
                    description=str(item.get("description", "")),
                )
            )
        else:
            raise ConfigError("Variables must be strings or mappings")
    return variables


def _parse_checks(items: Any) -> list[CheckConfig]:
    checks: list[CheckConfig] = []
    for item in items or []:
        if isinstance(item, str):
            checks.append(CheckConfig(name=item, command=item))
        elif isinstance(item, dict):
            command = item.get("command")
            if not command:
                raise ConfigError("Check entries require a command")
            checks.append(CheckConfig(name=str(item.get("name") or command), command=str(command)))
        else:
            raise ConfigError("Checks must be strings or mappings")
    return checks


def load_loop(path: Path, workspace: str | Path | None = None) -> LoopConfig:
    root = workspace_path(workspace)
    data = _read_yaml(path)
    name = str(data.get("name") or path.stem)
    prompt_ref = data.get("prompt") or data.get("prompt_file")
    if not prompt_ref:
        raise ConfigError(f"Loop config requires prompt or prompt_file: {path}")
    checks = _parse_checks(data.get("checks"))
    if not checks:
        raise ConfigError(f"Loop config requires at least one check: {path}")
    return LoopConfig(
        name=name,
        description=str(data.get("description", "")),
        adapter=str(data.get("adapter", "codex")),
        prompt=_load_prompt(str(prompt_ref), path, root),
        checks=checks,
        variables=_parse_variables(data.get("variables")),
        max_iterations=int(data.get("max_iterations", 3)),
        workspace=root,
        source_path=path,
    )


def list_configs(kind: str, workspace: str | Path | None = None) -> list[Path]:
    roots = {
        "loops": loops_dir,
        "templates": templates_dir,
        "examples": examples_dir,
    }
    root_fn = roots[kind]
    root = root_fn(workspace)
    if not root.exists():
        return []
    return sorted([*root.glob("*.yaml"), *root.glob("*.yml")])


def find_config(name: str, kind: str, workspace: str | Path | None = None) -> Path:
    root = {"loops": loops_dir, "templates": templates_dir, "examples": examples_dir}[kind](workspace)
    candidate = Path(name)
    if candidate.exists():
        return candidate.resolve()
    for suffix in ("", ".yaml", ".yml"):
        path = root / f"{name}{suffix}"
        if path.exists():
            return path
    raise ConfigError(f"{kind[:-1].title()} not found: {name}")


def default_template_data(name: str) -> dict[str, Any]:
    safe_name = validate_config_name(name)
    return {
        "name": safe_name,
        "description": "AgentLoop template.",
        "adapter": "codex",
        "prompt": "Complete this task:\n\n{{ task_description }}\n\nRespond with BLOCKED: if required context is missing.",
        "max_iterations": 3,
        "variables": [{"name": "task_description", "required": True}, {"name": "check_command", "required": True}],
        "checks": [{"name": "objective check", "command": "{{ check_command }}"}],
    }


def write_template(name: str, data: dict[str, Any], workspace: str | Path | None = None, *, overwrite: bool = False) -> Path:
    path = template_path(name, workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise ConfigError(f"Template already exists: {name}")
    payload = dict(data)
    payload["name"] = validate_config_name(str(payload.get("name") or name))
    if payload["name"] != validate_config_name(name):
        raise ConfigError("Template name and filename must match")
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    load_loop(path, workspace)
    return path


def create_template(name: str, workspace: str | Path | None = None, *, data: dict[str, Any] | None = None, overwrite: bool = False) -> Path:
    return write_template(name, data or default_template_data(name), workspace, overwrite=overwrite)


def copy_template(source_name: str, target_name: str, workspace: str | Path | None = None, *, overwrite: bool = False) -> Path:
    source_path = find_config(source_name, "templates", workspace)
    data = _read_yaml(source_path)
    data["name"] = validate_config_name(target_name)
    return write_template(target_name, data, workspace, overwrite=overwrite)
