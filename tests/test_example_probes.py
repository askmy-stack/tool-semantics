"""Walkthrough coverage for example probe fixtures (#70)."""

from __future__ import annotations

from pathlib import Path

from tool_semantics.probes import (
    ProbeKind,
    evaluate_probes,
    evaluate_probes_with_model,
    load_probes,
)
from tool_semantics.runner import FakeModelRunner, ModelCompletion, RunnerMetadata, ToolCallRequest
from tool_semantics.scanner import capture_manifest

PROBES = Path("examples/probes/github_v1_offline.json")


def test_github_v1_offline_suite_covers_kinds() -> None:
    probes = load_probes(PROBES)
    kinds = {probe.kind for probe in probes}
    assert ProbeKind.POSITIVE in kinds
    assert ProbeKind.NEGATIVE in kinds
    assert ProbeKind.AMBIGUOUS in kinds
    assert all(probe.approved for probe in probes)


def test_github_v1_offline_and_fake_model_walkthrough() -> None:
    snapshot = capture_manifest(Path("examples/github_server_v1.json"))
    probes = load_probes(PROBES)
    assert evaluate_probes(snapshot, probes).passed

    search = next(probe for probe in probes if probe.id == "search-open-issues")
    runner = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "bugs"})],
                metadata=RunnerMetadata(provider="fake", model="demo"),
            )
        ]
    )
    report = evaluate_probes_with_model(snapshot, [search], runner)
    assert report.passed
    assert report.results[0].selected_tool == "search_issues"
