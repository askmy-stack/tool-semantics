"""MCP extension capture and compatibility helpers (#91).

Best-effort extraction of extensions / experimental capabilities advertised at
``initialize``, normalized into snapshot metadata for diffing.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExtensionInfo(BaseModel):
    """Normalized extension advertisement."""

    name: str
    version: str | None = None
    # Where the advertisement was found (for docs / debugging).
    source: str = "unknown"
    # Raw payload fragment when not a simple version string.
    details: dict[str, Any] = Field(default_factory=dict)


def _as_extension_info(
    name: str,
    value: Any,
    *,
    source: str,
) -> ExtensionInfo:
    if value is True or value is None:
        return ExtensionInfo(name=name, version=None, source=source)
    if isinstance(value, str):
        return ExtensionInfo(name=name, version=value, source=source)
    if isinstance(value, dict):
        version = value.get("version")
        version_s = str(version) if version is not None else None
        details = {key: val for key, val in value.items() if key != "version"}
        return ExtensionInfo(
            name=name,
            version=version_s,
            source=source,
            details=details if details else {},
        )
    return ExtensionInfo(
        name=name,
        version=None,
        source=source,
        details={"value": value},
    )


def extract_extensions_from_initialize(init: Any) -> dict[str, ExtensionInfo]:
    """Best-effort extension map from an MCP ``initialize`` result.

    Protocol generations differ; we accept several shapes without inventing
    extensions when none are advertised:

    - top-level ``extensions`` object
    - ``capabilities.extensions``
    - ``capabilities.experimental`` (treated as experimental extension stubs)
    """
    if not isinstance(init, dict):
        return {}

    found: dict[str, ExtensionInfo] = {}

    def ingest(raw: Any, *, source: str) -> None:
        if isinstance(raw, dict):
            for name, value in raw.items():
                if not isinstance(name, str) or not name:
                    continue
                # Later, more-specific sources can override.
                found[name] = _as_extension_info(name, value, source=source)
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item:
                    found[item] = ExtensionInfo(name=item, source=source)
                elif isinstance(item, dict) and isinstance(item.get("name"), str):
                    name = item["name"]
                    found[name] = _as_extension_info(name, item, source=source)

    ingest(init.get("extensions"), source="initialize.extensions")
    caps = init.get("capabilities")
    if isinstance(caps, dict):
        ingest(caps.get("extensions"), source="capabilities.extensions")
        ingest(caps.get("experimental"), source="capabilities.experimental")

    return found


def extensions_metadata(init: Any) -> dict[str, dict[str, Any]]:
    """JSON-serializable ``metadata['extensions']`` payload for snapshots."""
    return {
        name: info.model_dump(mode="json")
        for name, info in sorted(extract_extensions_from_initialize(init).items())
    }


def extensions_from_snapshot_metadata(
    metadata: dict[str, Any],
) -> dict[str, ExtensionInfo]:
    raw = metadata.get("extensions")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, ExtensionInfo] = {}
    for name, value in raw.items():
        if not isinstance(name, str):
            continue
        if isinstance(value, dict):
            out[name] = ExtensionInfo.model_validate({"name": name, **value})
        else:
            out[name] = _as_extension_info(name, value, source="snapshot.metadata")
    return out
