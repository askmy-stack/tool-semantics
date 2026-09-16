"""CI smoke: capture demo-mcp stdio variants and compare (#102)."""

from __future__ import annotations

import sys
from pathlib import Path

from tool_semantics.diff import Severity, compare_snapshots
from tool_semantics.mcp_capture import capture_mcp_stdio

SERVER = Path(__file__).resolve().parents[1] / "examples" / "demo-mcp" / "server.py"


def _capture(variant: str):
    return capture_mcp_stdio([sys.executable, str(SERVER), variant])


def test_demo_mcp_variants_capture_and_compare() -> None:
    v1 = _capture("v1")
    safe = _capture("v2-safe")
    breaking = _capture("v2-breaking")
    confusing = _capture("v2-confusing")

    assert v1.server_name == "demo-mcp"
    assert {tool.name for tool in v1.tools} == {"search_notes", "create_note"}

    safe_report = compare_snapshots(v1, safe)
    assert safe_report.is_compatible
    assert any(change.code == "tool.added" for change in safe_report.changes)

    breaking_report = compare_snapshots(v1, breaking)
    assert not breaking_report.is_compatible
    assert any(
        change.code == "tool.removed" and change.subject == "search_notes"
        for change in breaking_report.changes
    )
    assert any(
        change.severity == Severity.BREAKING and change.code == "parameter.added_required"
        for change in breaking_report.changes
    )

    confusing_report = compare_snapshots(v1, confusing)
    assert any(
        change.code == "tool.added" and change.subject == "find_notes"
        for change in confusing_report.changes
    )
    # Additive only → still structurally compatible under default gate
    assert confusing_report.is_compatible
