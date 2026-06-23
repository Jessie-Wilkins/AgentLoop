from __future__ import annotations

from pathlib import Path

from agentloop.core.models import CONFIG_DIR, RUNS_DIR


def workspace_path(workspace: str | Path | None = None) -> Path:
    return Path(workspace or Path.cwd()).expanduser().resolve()


def config_dir(workspace: str | Path | None = None) -> Path:
    return workspace_path(workspace) / CONFIG_DIR


def loops_dir(workspace: str | Path | None = None) -> Path:
    return config_dir(workspace) / "loops"


def prompts_dir(workspace: str | Path | None = None) -> Path:
    return config_dir(workspace) / "prompts"


def templates_dir(workspace: str | Path | None = None) -> Path:
    return config_dir(workspace) / "templates"


def examples_dir(workspace: str | Path | None = None) -> Path:
    return config_dir(workspace) / "examples"


def apps_dir(workspace: str | Path | None = None) -> Path:
    return config_dir(workspace) / "apps"


def uploads_dir(workspace: str | Path | None = None) -> Path:
    return config_dir(workspace) / "uploads"


def runs_dir(workspace: str | Path | None = None) -> Path:
    return workspace_path(workspace) / RUNS_DIR
