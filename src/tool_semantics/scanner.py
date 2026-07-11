from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tool_semantics.models import InterfaceSnapshot, ToolContract, ToolParameter


class ManifestError(ValueError):
    """Raised when a manifest cannot be normalized."""


SUPPORTED_SNAPSHOT_VERSIONS = frozenset({"0.1"})
CURRENT_SNAPSHOT_VERSION = "0.1"


def _normalize_parameters(input_schema: dict[str, Any]) -> list[ToolParameter]:
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    if not isinstance(properties, dict):
        raise ManifestError("inputSchema.properties must be an object")

    parameters: list[ToolParameter] = []
    for name, schema in properties.items():
        if not isinstance(schema, dict):
            raise ManifestError(f"Schema for parameter '{name}' must be an object")
        parameters.append(
            ToolParameter(
                name=name,
                schema=schema,
                required=name in required,
                description=schema.get("description"),
            )
        )
    return sorted(parameters, key=lambda parameter: parameter.name)


def capture_manifest(path: Path) -> InterfaceSnapshot:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"Unable to read manifest: {exc}") from exc

    if not isinstance(raw, dict):
        raise ManifestError("Manifest root must be an object")
    raw_tools = raw.get("tools", [])
    if not isinstance(raw_tools, list):
        raise ManifestError("'tools' must be an array")

    tools: list[ToolContract] = []
    for raw_tool in raw_tools:
        if not isinstance(raw_tool, dict) or not isinstance(raw_tool.get("name"), str):
            raise ManifestError("Each tool must contain a string 'name'")
        input_schema = raw_tool.get("inputSchema", {"type": "object", "properties": {}})
        if not isinstance(input_schema, dict):
            raise ManifestError(f"Tool '{raw_tool['name']}' inputSchema must be an object")
        output_schema = raw_tool.get("outputSchema")
        if output_schema is not None and not isinstance(output_schema, dict):
            raise ManifestError(f"Tool '{raw_tool['name']}' outputSchema must be an object")
        tools.append(
            ToolContract(
                name=raw_tool["name"],
                description=str(raw_tool.get("description", "")),
                parameters=_normalize_parameters(input_schema),
                output_schema=output_schema,
                risk=raw_tool.get("risk", "unknown"),
            )
        )

    return InterfaceSnapshot(
        protocol=str(raw.get("protocol", "manifest")),
        server_name=str(raw.get("serverName", path.stem)),
        server_version=raw.get("serverVersion"),
        tools=sorted(tools, key=lambda tool: tool.name),
        metadata=raw.get("metadata", {}),
    )


def write_snapshot(snapshot: InterfaceSnapshot, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(snapshot.model_dump_json(indent=2, by_alias=True) + "\n", encoding="utf-8")


def _validate_snapshot_version(version: str) -> None:
    if version in SUPPORTED_SNAPSHOT_VERSIONS:
        return
    supported = ", ".join(sorted(SUPPORTED_SNAPSHOT_VERSIONS))
    raise ManifestError(
        f"Unsupported tool_semantics_version {version!r}. "
        f"Supported versions: {supported}. "
        f"Upgrade Tool-Semantics or re-capture snapshots with version {CURRENT_SNAPSHOT_VERSION}."
    )


def read_snapshot(path: Path) -> InterfaceSnapshot:
    try:
        snapshot = InterfaceSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"Unable to read snapshot: {exc}") from exc
    _validate_snapshot_version(snapshot.tool_semantics_version)
    return snapshot
