"""Tests for expanded safety semantics (#87)."""

from __future__ import annotations

from pathlib import Path

from tool_semantics.diff import Severity, compare_snapshots
from tool_semantics.models import (
    InterfaceSnapshot,
    PermissionScope,
    RiskLevel,
    ToolContract,
    ToolParameter,
    extract_safety_annotations,
)
from tool_semantics.probes import Probe, ProbeKind, evaluate_probes
from tool_semantics.scanner import capture_manifest


def _tool(**kwargs: object) -> ToolContract:
    base = {
        "name": "t",
        "description": "tool",
        "parameters": [ToolParameter(name="q", schema={"type": "string"})],
        "risk": RiskLevel.READ_ONLY,
    }
    base.update(kwargs)
    return ToolContract(**base)  # type: ignore[arg-type]


def test_absent_safety_fields_default_unknown() -> None:
    tool = ToolContract(name="x", description="")
    assert tool.scope is PermissionScope.UNKNOWN
    assert tool.side_effects == []
    assert tool.requires_confirmation is None


def test_extract_safety_from_annotations_never_invents() -> None:
    raw = {"name": "t", "annotations": {"risk": "destructive", "scope": "organization"}}
    safety = extract_safety_annotations(raw)
    assert safety["risk"] is RiskLevel.DESTRUCTIVE
    assert safety["scope"] is PermissionScope.ORGANIZATION
    assert safety["side_effects"] == []
    assert safety["requires_confirmation"] is None


def test_scope_escalation_and_confirmation_removed() -> None:
    baseline = InterfaceSnapshot(
        server_name="s",
        tools=[
            _tool(
                name="delete",
                scope=PermissionScope.PROJECT,
                requires_confirmation=True,
                side_effects=["write"],
            )
        ],
    )
    candidate = InterfaceSnapshot(
        server_name="s",
        tools=[
            _tool(
                name="delete",
                scope=PermissionScope.GLOBAL,
                requires_confirmation=False,
                side_effects=["write", "delete"],
            )
        ],
    )
    report = compare_snapshots(baseline, candidate)
    codes = {change.code: change for change in report.changes}
    assert codes["tool.scope_escalated"].severity is Severity.CRITICAL
    assert codes["tool.confirmation_removed"].severity is Severity.CRITICAL
    assert codes["tool.side_effect_added"].severity is Severity.CRITICAL
    assert not report.is_compatible


def test_scope_unknown_change_is_warning_not_escalation() -> None:
    baseline = InterfaceSnapshot(
        server_name="s",
        tools=[_tool(name="t", scope=PermissionScope.UNKNOWN)],
    )
    candidate = InterfaceSnapshot(
        server_name="s",
        tools=[_tool(name="t", scope=PermissionScope.PROJECT)],
    )
    report = compare_snapshots(baseline, candidate)
    assert any(change.code == "tool.scope_changed" for change in report.changes)
    assert not any(change.code == "tool.scope_escalated" for change in report.changes)


def test_probe_max_scope_and_forbidden_side_effects() -> None:
    snapshot = InterfaceSnapshot(
        server_name="s",
        tools=[
            _tool(
                name="pay",
                scope=PermissionScope.ACCOUNT,
                side_effects=["payment"],
                risk=RiskLevel.EXTERNAL_WRITE,
            )
        ],
    )
    probes = [
        Probe(
            id="p1",
            intent="pay invoice",
            kind=ProbeKind.POSITIVE,
            expected_tool="pay",
            max_scope="workspace",
        ),
        Probe(
            id="p2",
            intent="pay invoice",
            kind=ProbeKind.POSITIVE,
            expected_tool="pay",
            forbidden_side_effects=["payment"],
        ),
    ]
    report = evaluate_probes(snapshot, probes)
    assert not report.passed
    messages = " ".join(item.message for item in report.results)
    assert "max_scope" in messages
    assert "forbidden side effect" in messages


def test_manifest_capture_reads_safety_fields(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    path.write_text(
        """
{
  "serverName": "demo",
  "tools": [
    {
      "name": "wipe",
      "description": "delete stuff",
      "inputSchema": {"type": "object", "properties": {}},
      "risk": "destructive",
      "scope": "organization",
      "side_effects": ["delete", "admin"],
      "requires_confirmation": true
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    snap = capture_manifest(path)
    tool = snap.tools[0]
    assert tool.risk is RiskLevel.DESTRUCTIVE
    assert tool.scope is PermissionScope.ORGANIZATION
    assert tool.side_effects == ["delete", "admin"]
    assert tool.requires_confirmation is True
