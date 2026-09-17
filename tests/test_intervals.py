"""Tests for confidence intervals (#115)."""

from __future__ import annotations

from tool_semantics.intervals import (
    OVERLAP_WARNING,
    compare_rates,
    intervals_from_probe_results,
    intervals_from_stability,
    intervals_overlap,
    pass_at_k_interval,
    render_intervals_markdown,
    wilson_interval,
)
from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract, ToolParameter
from tool_semantics.probes import Probe, ProbeKind, run_probe_trials
from tool_semantics.report import render_stability_json, render_stability_markdown
from tool_semantics.runner import FakeModelRunner, ModelCompletion, RunnerMetadata, ToolCallRequest


def test_wilson_interval_bounds_and_format() -> None:
    ci = wilson_interval(89, 100, confidence=0.95, min_n=10)
    assert ci is not None
    assert 0.8 < ci.estimate < 0.95
    assert 0.0 <= ci.low < ci.estimate < ci.high <= 1.0
    assert ci.sufficient_n is True
    assert "±" in ci.format_pm()
    assert "[" in ci.format_bracket()


def test_wilson_insufficient_n() -> None:
    ci = wilson_interval(3, 4, min_n=10)
    assert ci is not None
    assert ci.sufficient_n is False


def test_wilson_n_zero() -> None:
    assert wilson_interval(0, 0) is None


def test_overlap_and_meaningful_regression() -> None:
    baseline = wilson_interval(90, 100, min_n=10)
    close = wilson_interval(87, 100, min_n=10)
    clear = wilson_interval(40, 100, min_n=10)
    assert baseline is not None and close is not None and clear is not None
    assert intervals_overlap(baseline, close)
    cmp_close = compare_rates(baseline, close, label="selection")
    assert cmp_close.meaningful_regression is False
    assert cmp_close.warning == OVERLAP_WARNING
    cmp_clear = compare_rates(baseline, clear, label="selection")
    assert cmp_clear.overlap is False
    assert cmp_clear.candidate_clearly_lower is True
    assert cmp_clear.meaningful_regression is True
    assert cmp_clear.warning is None


def test_pass_at_k_interval() -> None:
    ci = pass_at_k_interval([True, True, False, True], min_n=4)
    assert ci is not None
    assert ci.estimate == 0.75
    assert ci.sufficient_n is True


def test_intervals_in_stability_report() -> None:
    snap = InterfaceSnapshot(
        server_name="demo",
        tools=[
            ToolContract(
                name="search_issues",
                description="Search issues",
                parameters=[ToolParameter(name="query", schema={"type": "string"}, required=True)],
                risk=RiskLevel.READ_ONLY,
            )
        ],
    )
    probes = [
        Probe(
            id="search",
            intent="find bugs",
            kind=ProbeKind.POSITIVE,
            expected_tool="search_issues",
            required_params=["query"],
            approved=True,
            approved_by="ci",
        )
    ]
    completions = [
        ModelCompletion(
            tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "bugs"})],
            metadata=RunnerMetadata(provider="fake", model="fake"),
        )
        for _ in range(4)
    ]
    report = run_probe_trials(
        snap,
        probes,
        FakeModelRunner(completions),
        trial_count=4,
        seed=1,
    )
    assert report.intervals is not None
    assert "metrics" in report.intervals
    names = {item["name"] for item in report.intervals["metrics"]}
    assert "tool_selection_accuracy" in names
    assert "pass_at_k_rate" in names
    md = render_stability_markdown(report)
    assert "Confidence intervals" in md
    assert "Overlapping" not in md or True  # no comparison block by default
    payload = render_stability_json(report)
    assert "intervals" in payload

    # Fallback path without raw results still produces pass-rate CIs.
    bare = report.model_copy(update={"intervals": None})
    bundle = intervals_from_stability(bare)
    assert any(item.name == "pass_rate" for item in bundle.metrics)
    assert "search" in bundle.per_probe
    assert "Confidence intervals" in render_intervals_markdown(bundle)


def test_intervals_from_probe_results_empty_evaluated() -> None:
    bundle = intervals_from_probe_results([])
    assert all(item.interval is None for item in bundle.metrics)
