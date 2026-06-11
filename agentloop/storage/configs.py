from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agentloop.core.models import CheckConfig, LoopConfig, VariableConfig
from agentloop.storage.paths import examples_dir, loops_dir, prompts_dir, templates_dir, workspace_path


class ConfigError(ValueError):
    pass


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
