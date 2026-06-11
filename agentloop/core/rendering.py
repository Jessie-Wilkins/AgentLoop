from __future__ import annotations

from typing import Any

from jinja2 import StrictUndefined, Template

from agentloop.core.models import LoopConfig, RenderedLoop


class RenderError(ValueError):
    pass


def merge_values(loop: LoopConfig, provided: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    missing: list[str] = []
    for variable in loop.variables:
        if variable.name in provided:
            values[variable.name] = provided[variable.name]
        elif variable.default is not None:
            values[variable.name] = variable.default
        elif variable.required:
            missing.append(variable.name)
    extra = {key: value for key, value in provided.items() if key not in values}
    values.update(extra)
    if missing:
        raise RenderError(f"Missing required variables: {', '.join(sorted(missing))}")
    return values


def render_text(text: str, values: dict[str, Any]) -> str:
    try:
        return Template(text, undefined=StrictUndefined).render(**values)
    except Exception as exc:
        raise RenderError(str(exc)) from exc


def render_loop(loop: LoopConfig, provided: dict[str, Any] | None = None) -> RenderedLoop:
    values = merge_values(loop, provided or {})
    prompt = render_text(loop.prompt, values)
    commands = [render_text(check.command, values) for check in loop.checks]
    return RenderedLoop(loop=loop, values=values, prompt=prompt, commands=commands)
