from __future__ import annotations

import time
from typing import Any

from tool_semantics.diff import compare_snapshots
from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract, ToolParameter
from tool_semantics.probes import Probe, ProbeKind, evaluate_probes

DEFAULT_SCALE_SIZES: tuple[int, ...] = (10, 100, 500, 1000, 5000)


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


def time_snapshot_build(tool_count: int) -> dict[str, float | int]:
    """Time synthesize + snapshot_from_manifest (capture-like path)."""
    started = time.perf_counter()
    snap = snapshot_from_manifest(synthesize_manifest(tool_count, prefix="bench"))
    elapsed = time.perf_counter() - started
    return {
        "tool_count": tool_count,
        "elapsed_seconds": elapsed,
        "tools": len(snap.tools),
    }


def time_offline_probes(tool_count: int, *, probe_count: int = 5) -> dict[str, float | int]:
    """Time offline probe evaluation against a synthetic catalog."""
    snap = snapshot_from_manifest(synthesize_manifest(tool_count, prefix="bench"))
    names = [tool.name for tool in snap.tools] or ["missing"]
    probes = [
        Probe(
            id=f"p{index}",
            intent=f"use tool {index}",
            kind=ProbeKind.POSITIVE,
            expected_tool=names[index % len(names)],
            required_params=["query"],
        )
        for index in range(probe_count)
    ]
    started = time.perf_counter()
    report = evaluate_probes(snap, probes)
    elapsed = time.perf_counter() - started
    return {
        "tool_count": tool_count,
        "probe_count": probe_count,
        "elapsed_seconds": elapsed,
        "passed": int(report.passed),
    }


def run_scale_benchmark(
    sizes: tuple[int, ...] = DEFAULT_SCALE_SIZES,
    *,
    include_probes: bool = True,
) -> list[dict[str, Any]]:
    """Run snapshot/diff/(optional) probe timings for each catalog size (#100).

    Not gated in PR CI — timings vary by host. Call from ``scripts/bench_scale.py``.
    """
    rows: list[dict[str, Any]] = []
    for size in sizes:
        row: dict[str, Any] = {"tool_count": size}
        row["snapshot"] = time_snapshot_build(size)
        row["compare"] = time_compare(size)
        if include_probes:
            row["offline_probes"] = time_offline_probes(size)
        rows.append(row)
    return rows


def render_scale_benchmark_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "## Scale benchmark",
        "",
        "_Informational timings — not a CI gate (#100)._",
        "",
        "| Tools | Snapshot (s) | Compare (s) | Offline probes (s) |",
        "| ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        snap = row.get("snapshot", {})
        cmp = row.get("compare", {})
        probes = row.get("offline_probes") or {}
        probe_s = f"{probes['elapsed_seconds']:.4f}" if probes else "—"
        lines.append(
            f"| {row['tool_count']} | "
            f"{snap.get('elapsed_seconds', 0):.4f} | "
            f"{cmp.get('elapsed_seconds', 0):.4f} | "
            f"{probe_s} |"
        )
    lines.append("")
    return "\n".join(lines)
