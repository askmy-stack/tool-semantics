"""Tests for model-probe / stability report renderers (#64)."""

from __future__ import annotations

import json

from tool_semantics.probes import (
    ModelProbeOutcome,
    ModelProbeReport,
    ModelProbeResult,
    ProbeMetrics,
    StabilityProbeSummary,
    StabilityReport,
    TrialDetail,
)
from tool_semantics.report import (
    render_model_probe_report_markdown,
    render_stability_json,
    render_stability_markdown,
)
from tool_semantics.runner import RunnerMetadata


def test_render_model_probe_report_markdown() -> None:
    report = ModelProbeReport(
        results=[
            ModelProbeResult(
                probe_id="ok",
                passed=True,
                message="Selected search_issues.",
                selected_tool="search_issues",
                outcome=ModelProbeOutcome.OK,
                tool_selection_correct=True,
                arguments_valid=True,
                runner=RunnerMetadata(provider="fake", model="m"),
            ),
            ModelProbeResult(
                probe_id="miss",
                passed=False,
                message="Model returned no tool call.",
                outcome=ModelProbeOutcome.MISSING_DATA,
                tool_selection_correct=False,
            ),
        ]
    )
    md = render_model_probe_report_markdown(report)
    assert "Probe metrics" in md
    assert "Per-probe results" in md
    assert "`ok`" in md
    assert "`miss`" in md
    assert "search_issues" in md


def test_render_stability_json_and_markdown() -> None:
    report = StabilityReport(
        trial_count=2,
        seed=3,
        summaries=[
            StabilityProbeSummary(
                probe_id="search",
                trials=[
                    TrialDetail(
                        trial_index=0,
                        selected_tool="search_issues",
                        arguments={"query": "x"},
                        passed=True,
                        outcome=ModelProbeOutcome.OK,
                        message="ok",
                    ),
                    TrialDetail(
                        trial_index=1,
                        selected_tool="search_issues",
                        arguments={"query": "x"},
                        passed=True,
                        outcome=ModelProbeOutcome.OK,
                        message="ok",
                    ),
                ],
                stability_score=1.0,
                unstable=False,
                deterministic_failure=False,
                aggregate_passed=True,
                message="Stable across trials.",
            )
        ],
        metrics=ProbeMetrics(probe_count=2, evaluated_count=2, tool_selection_accuracy=1.0),
    )
    payload = json.loads(render_stability_json(report))
    assert payload["trial_count"] == 2
    assert payload["seed"] == 3
    assert payload["summaries"][0]["probe_id"] == "search"
    md = render_stability_markdown(report)
    assert "Probe stability report" in md
    assert "Aggregate metrics" in md
    assert "`search`" in md
