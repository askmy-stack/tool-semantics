"""Tests for progressive discovery harness (#86)."""

from __future__ import annotations

from tool_semantics.discovery import (
    CI_CATALOG_SIZES,
    SizeAwareFakeRunner,
    compare_discovery_curves,
    discovery_regression_changes,
    pad_catalog,
    run_discovery_curve,
)
from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract, ToolParameter
from tool_semantics.probes import Probe, ProbeKind


def _core_snapshot() -> InterfaceSnapshot:
    return InterfaceSnapshot(
        server_name="core",
        tools=[
            ToolContract(
                name="search_issues",
                description="Search issues by query",
                parameters=[
                    ToolParameter(name="query", schema={"type": "string"}, required=True),
                ],
                risk=RiskLevel.READ_ONLY,
            )
        ],
    )


def _probe() -> Probe:
    return Probe(
        id="search",
        intent="find open bugs",
        kind=ProbeKind.POSITIVE,
        expected_tool="search_issues",
        approved=True,
    )


def test_pad_catalog_keeps_core_and_grows() -> None:
    core = _core_snapshot()
    padded = pad_catalog(core, 25)
    assert len(padded.tools) == 25
    assert any(tool.name == "search_issues" for tool in padded.tools)


def test_progressive_curve_and_regression_warning() -> None:
    core = _core_snapshot()
    # Baseline runner always succeeds (fail_above very high).
    baseline_runner = SizeAwareFakeRunner(expected_tool="search_issues", fail_above=10_000)
    # Candidate degrades once catalog reaches 25 tools.
    candidate_runner = SizeAwareFakeRunner(expected_tool="search_issues", fail_above=25)

    sizes = (10, 25, 50)
    baseline_curve = run_discovery_curve(
        core,
        [_probe()],
        baseline_runner,
        sizes=sizes,
        label="baseline",
        require_approval=False,
    )
    candidate_curve = run_discovery_curve(
        core,
        [_probe()],
        candidate_runner,
        sizes=sizes,
        label="candidate",
        require_approval=False,
    )

    assert baseline_curve.accuracy_at(10) == 1.0
    assert candidate_curve.accuracy_at(10) == 1.0
    assert candidate_curve.accuracy_at(25) == 0.0

    report = compare_discovery_curves(
        baseline_curve,
        candidate_curve,
        baseline_tool_count=10,
        candidate_tool_count=50,
        accuracy_drop_threshold=0.10,
    )
    assert report.has_regression
    assert any("DISCOVERY REGRESSION" in warning for warning in report.warnings)
    changes = discovery_regression_changes(report)
    assert any(change.code == "discovery.accuracy_regression" for change in changes)


def test_no_regression_without_tool_growth() -> None:
    core = _core_snapshot()
    runner = SizeAwareFakeRunner(expected_tool="search_issues", fail_above=25)
    curve = run_discovery_curve(core, [_probe()], runner, sizes=(10, 25), require_approval=False)
    report = compare_discovery_curves(
        curve,
        curve,
        baseline_tool_count=40,
        candidate_tool_count=40,
    )
    assert not report.has_regression
    assert any("did not increase" in warning for warning in report.warnings)


def test_ci_sizes_are_subset() -> None:
    assert CI_CATALOG_SIZES == (10, 25, 50)
