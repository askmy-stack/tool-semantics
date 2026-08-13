from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tool_semantics.redact import redact_mapping

_COMMAND_SECRET_OPTION_PATTERN = re.compile(
    r"^--?(?:[a-z0-9_-]*(?:secret|token|password|api[_-]?key|authorization|credential|cookie)|auth|bearer)(?:=|$)",
    re.IGNORECASE,
)
_COMMAND_HEADER_OPTION_PATTERN = re.compile(r"^(?:-H|--header)(?:=|$)", re.IGNORECASE)
_COMMAND_ENVIRONMENT_OPTION_PATTERN = re.compile(r"^(?:--env|-e)(?:=|$)", re.IGNORECASE)
_ENVIRONMENT_KEY_PATTERN = re.compile(r"(?:^|_)(?:env|environment)(?:_|$)", re.IGNORECASE)
_ENVIRONMENT_ASSIGNMENT_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=", re.IGNORECASE)
_REDACTED = "***REDACTED***"


def snapshot_sha256(snapshot_path: Path) -> str:
    """Return the SHA-256 digest of a snapshot's exact on-disk bytes."""
    return hashlib.sha256(snapshot_path.read_bytes()).hexdigest()


def _redact_source(source: dict[str, Any]) -> dict[str, Any]:
    redacted = redact_mapping(source)
    return {key: _redact_source_value(key, value) for key, value in redacted.items()}


def _redact_source_value(key: str, value: Any) -> Any:
    if _ENVIRONMENT_KEY_PATTERN.search(key):
        return _REDACTED
    if key == "command" and isinstance(value, list):
        return _redact_command_arguments(value)
    if isinstance(value, dict):
        return {
            child_key: _redact_source_value(child_key, child) for child_key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact_source_value(key, item) for item in value]
    return value


def _redact_command_arguments(command: list[Any]) -> list[Any]:
    redacted = list(command)
    for index, argument in enumerate(command):
        if not isinstance(argument, str):
            continue
        environment_assignment = _ENVIRONMENT_ASSIGNMENT_PATTERN.match(argument)
        if environment_assignment:
            redacted[index] = _REDACTED
        elif _COMMAND_ENVIRONMENT_OPTION_PATTERN.match(argument):
            if "=" in argument:
                redacted[index] = f"{argument.split('=', maxsplit=1)[0]}={_REDACTED}"
            elif index + 1 < len(redacted):
                redacted[index + 1] = _REDACTED
        elif _COMMAND_SECRET_OPTION_PATTERN.match(argument) or _COMMAND_HEADER_OPTION_PATTERN.match(
            argument
        ):
            if "=" in argument:
                redacted[index] = _REDACTED
            elif index + 1 < len(redacted):
                redacted[index + 1] = _REDACTED
    return redacted


def write_provenance(
    snapshot_path: Path,
    output_path: Path,
    source: dict[str, Any],
    captured_at: datetime | None = None,
) -> None:
    """Write deterministic, redacted provenance for an existing snapshot."""
    timestamp = captured_at or datetime.now(UTC)
    payload = {
        "provenance_version": "0.1",
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": snapshot_sha256(snapshot_path),
        "captured_at": timestamp.isoformat(),
        "source": _redact_source(source),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
