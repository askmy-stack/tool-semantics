from __future__ import annotations

import time
from typing import Any

from tool_semantics.diff import compare_snapshots
from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract, ToolParameter


def synthesize_manifest(tool_count: int, *, prefix: str = "tool") -> dict[str, Any]:
    """Build a large MCP-style manifest for performance checks."""
    tools = []
    for index in range(tool_count):
        tools.append(
            {
                "name": f"{prefix}_{index}",
                "description": f"Synthetic tool number {index} for benchmarks.",
                "risk": "read_only",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "default": 10},
                        "mode": {"type": "string", "enum": ["fast", "thorough"]},
                    },
                    "required": ["query"],
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {"items": {"type": "array"}},
                },
            }
        )
    return {
        "protocol": "mcp-manifest-bench",
        "serverName": f"bench-{prefix}",
        "serverVersion": "0.0.0",
        "tools": tools,
    }


def snapshot_from_manifest(manifest: dict[str, Any]) -> InterfaceSnapshot:
    tools: list[ToolContract] = []
    for raw in manifest.get("tools", []):
        schema = raw.get("inputSchema", {})
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        parameters = [
            ToolParameter(
                name=name,
                schema=prop,
                required=name in required,
                description=prop.get("description") if isinstance(prop, dict) else None,
            )
            for name, prop in properties.items()
            if isinstance(prop, dict)
        ]
        tools.append(
            ToolContract(
                name=raw["name"],
                description=str(raw.get("description", "")),
                parameters=sorted(parameters, key=lambda parameter: parameter.name),
                output_schema=raw.get("outputSchema"),
                risk=RiskLevel(raw.get("risk", "unknown")),
            )
        )
    return InterfaceSnapshot(
        protocol=str(manifest.get("protocol", "manifest")),
        server_name=str(manifest.get("serverName", "bench")),
        server_version=manifest.get("serverVersion"),
        tools=sorted(tools, key=lambda tool: tool.name),
    )


def time_compare(tool_count: int, *, mutate: bool = True) -> dict[str, float | int | bool]:
    """Time a compare of two synthetic snapshots; optionally introduce one breaking change."""
    baseline = snapshot_from_manifest(synthesize_manifest(tool_count, prefix="base"))
    candidate_manifest = synthesize_manifest(tool_count, prefix="base")
    if mutate and candidate_manifest["tools"]:
        # Remove the first tool to force a breaking change without rename noise.
        candidate_manifest["tools"] = candidate_manifest["tools"][1:]
    candidate = snapshot_from_manifest(candidate_manifest)
    started = time.perf_counter()
    report = compare_snapshots(baseline, candidate, detect_renames=False)
    elapsed = time.perf_counter() - started
    return {
        "tool_count": tool_count,
        "elapsed_seconds": elapsed,
        "change_count": len(report.changes),
        "compatible": report.is_compatible,
    }
