from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from tool_semantics.models import InterfaceSnapshot

# Keys / substrings that often carry secrets or unstable runtime values.
_SECRET_KEY_PATTERN = re.compile(
    r"(secret|token|password|api[_-]?key|authorization|credential|cookie)",
    re.IGNORECASE,
)
_REDACTED = "***REDACTED***"


def is_secret_key(key: str) -> bool:
    """True when a field name looks like it may hold a secret."""
    return bool(_SECRET_KEY_PATTERN.search(key))


def _redact_value(key: str, value: Any) -> Any:
    if is_secret_key(key):
        return _REDACTED
    if isinstance(value, dict):
        return {child_key: _redact_value(child_key, child) for child_key, child in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    return value


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied mapping with secret-like fields redacted."""
    return {key: _redact_value(key, value) for key, value in deepcopy(data).items()}


def redact_snapshot(snapshot: InterfaceSnapshot) -> InterfaceSnapshot:
    """Redact secret-like metadata and schema annotations on a snapshot."""
    payload = json.loads(snapshot.model_dump_json(by_alias=True))
    redacted = redact_mapping(payload)
    return InterfaceSnapshot.model_validate(redacted)
