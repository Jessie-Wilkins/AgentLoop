from __future__ import annotations

from typing import Any


REDACTION = "[REDACTED]"


def secret_names(variables: list[Any]) -> set[str]:
    return {item.name for item in variables if getattr(item, "secret", False)}


def redact_mapping(values: dict[str, Any], secrets: set[str]) -> dict[str, Any]:
    return {key: REDACTION if key in secrets else value for key, value in values.items()}


def redact_text(text: str, values: dict[str, Any], secrets: set[str]) -> str:
    redacted = text
    for name in secrets:
        value = values.get(name)
        if value:
            redacted = redacted.replace(str(value), REDACTION)
    return redacted
