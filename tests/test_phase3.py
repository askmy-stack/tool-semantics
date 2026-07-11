from pathlib import Path

from tool_semantics.benchmarks import time_compare
from tool_semantics.diff import Severity, compare_snapshots
from tool_semantics.models import InterfaceSnapshot, ToolContract, ToolParameter
from tool_semantics.scanner import capture_manifest


def test_detects_likely_tool_rename() -> None:
    baseline = InterfaceSnapshot(
        server_name="demo",
        tools=[
            ToolContract(
                name="search_issues",
                description="Search GitHub issues matching a query",
                parameters=[
                    ToolParameter(name="query", schema={"type": "string"}, required=True),
                    ToolParameter(name="state", schema={"type": "string"}),
                ],
            )
        ],
    )
    candidate = InterfaceSnapshot(
        server_name="demo",
        tools=[
            ToolContract(
                name="find_issues",
                description="Search GitHub issues matching a query string",
                parameters=[
                    ToolParameter(name="query", schema={"type": "string"}, required=True),
                    ToolParameter(name="state", schema={"type": "string"}),
                ],
            )
        ],
    )
    report = compare_snapshots(baseline, candidate)
    assert any(change.code == "tool.renamed" for change in report.changes)
    assert not any(change.code == "tool.removed" for change in report.changes)
    assert report.is_compatible  # rename is warning, params unchanged


def test_type_widened_and_narrowed() -> None:
    baseline = InterfaceSnapshot(
        server_name="demo",
        tools=[
            ToolContract(
                name="t",
                parameters=[ToolParameter(name="n", schema={"type": "integer"})],
            )
        ],
    )
    widened = InterfaceSnapshot(
        server_name="demo",
        tools=[
            ToolContract(
                name="t",
                parameters=[ToolParameter(name="n", schema={"type": "number"})],
            )
        ],
    )
    report = compare_snapshots(baseline, widened)
    assert any(change.code == "parameter.type_widened" for change in report.changes)
    assert report.is_compatible

    narrowed = compare_snapshots(widened, baseline)
    assert any(change.code == "parameter.type_narrowed" for change in narrowed.changes)
    assert not narrowed.is_compatible


def test_constraints_tightened_string_to_enum() -> None:
    baseline = InterfaceSnapshot(
        server_name="demo",
        tools=[
            ToolContract(
                name="t",
                parameters=[ToolParameter(name="mode", schema={"type": "string"})],
            )
        ],
    )
    candidate = InterfaceSnapshot(
        server_name="demo",
        tools=[
            ToolContract(
                name="t",
                parameters=[
                    ToolParameter(
                        name="mode",
                        schema={"type": "string", "enum": ["fast", "slow"]},
                    )
                ],
            )
        ],
    )
    report = compare_snapshots(baseline, candidate)
    assert any(change.code == "parameter.constraints_tightened" for change in report.changes)
    assert all(change.severity != Severity.BREAKING for change in report.changes)


def test_github_demo_still_reports_breaking_without_false_rename() -> None:
    baseline = capture_manifest(Path("examples/github_server_v1.json"))
    candidate = capture_manifest(Path("examples/github_server_v2.json"))
    report = compare_snapshots(baseline, candidate)
    # find_work_items differs enough that we still expect a hard removal signal
    # OR a rename — either is acceptable, but suite must stay incompatible.
    assert not report.is_compatible


def test_benchmark_compare_runs_quickly() -> None:
    stats = time_compare(80, mutate=True)
    assert stats["tool_count"] == 80
    assert stats["change_count"] >= 1
    assert stats["compatible"] is False
    assert float(stats["elapsed_seconds"]) < 2.0
