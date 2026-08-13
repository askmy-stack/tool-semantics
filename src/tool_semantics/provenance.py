from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tool_semantics.redact import redact_mapping

_COMMAND_SECRET_OPTION_PATTERN = re.compile(
    r"^--?(?:secret|token|password|api[_-]?key|authorization|credential|cookie)(?:=|$)",
    re.IGNORECASE,
)
_ENVIRONMENT_KEY_PATTERN = re.compile(r"(?:^|_)(?:env|environment)(?:_|$)", re.IGNORECASE)
_REDACTED = "***REDACTED***"


def snapshot_sha256(snapshot_path: Path) -> str:
    """Return the SHA-256 digest of a snapshot's exact on-disk bytes."""
    return hashlib.sha256(snapshot_path.read_bytes()).hexdigest()


def _redact_source(source: dict[str, Any]) -> dict[str, Any]:
    redacted = redact_mapping(source)
    for key, value in redacted.items():
        if _ENVIRONMENT_KEY_PATTERN.search(key):
            redacted[key] = _REDACTED
        elif key == "command" and isinstance(value, list):
            redacted[key] = _redact_command_arguments(value)
    return redacted


def _redact_command_arguments(command: list[Any]) -> list[Any]:
    redacted = list(command)
    for index, argument in enumerate(command):
        if isinstance(argument, str) and _COMMAND_SECRET_OPTION_PATTERN.match(argument):
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
