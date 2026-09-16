"""Tests for efficiency regression metrics (#114)."""

from __future__ import annotations

from pathlib import Path

from tool_semantics.efficiency import (
    EfficiencyMetrics,
    aggregate_efficiency,
    append_efficiency_section,
    compare_efficiency,
    load_efficiency_pair,
    render_efficiency_markdown,
)


def test_efficiency_does_not_affect_pass_fail() -> None:
    baseline = EfficiencyMetrics(tool_call_count=8, latency_ms=100)
    candidate = EfficiencyMetrics(tool_call_count=31, latency_ms=194)
    report = compare_efficiency(baseline, candidate)
    assert report.has_regression
    assert report.affects_pass_fail is False
    calls = next(item for item in report.deltas if item.metric == "tool_call_count")
    assert calls.baseline == 8
    assert calls.candidate == 31
    assert calls.regressing
    latency = next(item for item in report.deltas if item.metric == "latency_ms")
    assert latency.relative is not None
    assert abs(latency.relative - 0.94) < 0.01
    md = render_efficiency_markdown(report)
    assert "## EFFICIENCY" in md
    assert "Informational only" in md
    assert "tool_call_count" in md
    assert "8" in md and "31" in md
    assert "+94%" in md


def test_optional_cost_and_tokens() -> None:
    baseline = EfficiencyMetrics(
        tool_call_count=2,
        prompt_tokens=100,
        completion_tokens=50,
        model_cost=0.01,
        currency="USD",
    )
    candidate = EfficiencyMetrics(
        tool_call_count=2,
        prompt_tokens=120,
        completion_tokens=60,
        model_cost=0.012,
        currency="USD",
    )
    report = compare_efficiency(baseline, candidate)
    assert any(item.metric == "model_cost" for item in report.deltas)
    assert any(item.metric == "prompt_tokens" for item in report.deltas)
    # Same call count → not a call regression
    assert not next(item for item in report.deltas if item.metric == "tool_call_count").regressing


def test_fixture_pair_and_report_section() -> None:
    baseline, candidate = load_efficiency_pair(Path("examples/efficiency/sample_metrics.json"))
    report = compare_efficiency(baseline, candidate)
    assert report.has_regression
    md = append_efficiency_section("# Probe report\n\n**Result:** `PASS`\n", report)
    assert "## EFFICIENCY" in md
    assert "Informational only" in md
    assert append_efficiency_section("# ok\n", None) == "# ok\n"


def test_aggregate_efficiency() -> None:
    total = aggregate_efficiency(
        [
            EfficiencyMetrics(tool_call_count=3, failed_call_count=1, latency_ms=10),
            EfficiencyMetrics(tool_call_count=5, retry_count=2, latency_ms=20),
        ],
        label="suite",
    )
    assert total.tool_call_count == 8
    assert total.failed_call_count == 1
    assert total.retry_count == 2
    assert total.latency_ms == 30
    assert total.label == "suite"
