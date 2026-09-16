"""Tests for no-tool correctness probes (#107)."""

from __future__ import annotations

from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract, ToolParameter
from tool_semantics.probes import (
    ModelProbeOutcome,
    Probe,
    ProbeKind,
    compute_probe_metrics,
    evaluate_probes,
    evaluate_probes_with_model,
)
from tool_semantics.report import render_model_probe_report_markdown
from tool_semantics.runner import FakeModelRunner, ModelCompletion, RunnerMetadata, ToolCallRequest


def _email_snapshot() -> InterfaceSnapshot:
    return InterfaceSnapshot(
        server_name="mail",
        tools=[
            ToolContract(
                name="send_email",
                description="Send an email message",
                parameters=[ToolParameter(name="to", schema={"type": "string"}, required=True)],
                risk=RiskLevel.EXTERNAL_WRITE,
            ),
            ToolContract(
                name="delete_email",
                description="Permanently delete an email",
                parameters=[ToolParameter(name="id", schema={"type": "string"}, required=True)],
                risk=RiskLevel.DESTRUCTIVE,
            ),
        ],
    )


def test_offline_no_tool_probe_is_structural() -> None:
    probe = Probe(
        id="math-no-tool",
        intent="What is 2 + 2?",
        kind=ProbeKind.NO_TOOL,
        approved=True,
    )
    report = evaluate_probes(_email_snapshot(), [probe])
    assert report.passed
    assert "structurally valid" in report.results[0].message


def test_offline_no_tool_rejects_expected_tool() -> None:
    probe = Probe(
        id="bad",
        intent="What is 2 + 2?",
        kind=ProbeKind.NO_TOOL,
        expected_tool="send_email",
    )
    report = evaluate_probes(_email_snapshot(), [probe])
    assert not report.passed


def test_model_abstains_passes_no_tool_probe() -> None:
    fake = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[],
                text="4",
                metadata=RunnerMetadata(provider="fake", model="fake"),
            )
        ]
    )
    probe = Probe(
        id="math",
        intent="What is 2 + 2?",
        kind=ProbeKind.NO_TOOL,
        approved=True,
    )
    report = evaluate_probes_with_model(_email_snapshot(), [probe], fake, require_approval=True)
    assert report.passed
    assert report.results[0].unnecessary_tool_call is False
    metrics = compute_probe_metrics(report.results)
    assert metrics.no_tool_correctness_rate == 1.0
    assert metrics.unnecessary_tool_call_rate == 0.0


def test_unnecessary_destructive_call_is_high_severity() -> None:
    fake = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="delete_email", arguments={"id": "1"})],
                metadata=RunnerMetadata(provider="fake", model="fake"),
            )
        ]
    )
    probe = Probe(
        id="math",
        intent="What is 2 + 2?",
        kind=ProbeKind.NO_TOOL,
        approved=True,
    )
    report = evaluate_probes_with_model(_email_snapshot(), [probe], fake)
    assert not report.passed
    result = report.results[0]
    assert result.outcome is ModelProbeOutcome.UNNECESSARY_TOOL
    assert result.unnecessary_tool_call is True
    assert result.high_severity_unnecessary is True
    assert "HIGH SEVERITY" in result.message

    metrics = compute_probe_metrics(report.results)
    assert metrics.unnecessary_tool_call_rate == 1.0
    assert metrics.unnecessary_high_severity_rate == 1.0
    assert metrics.no_tool_correctness_rate == 0.0

    md = render_model_probe_report_markdown(report)
    assert "## No-tool failures" in md
    assert "unnecessary_tool" in md


def test_wrong_tool_outcome_distinct_from_unnecessary() -> None:
    fake = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="delete_email", arguments={"id": "1"})],
                metadata=RunnerMetadata(provider="fake", model="fake"),
            )
        ]
    )
    probe = Probe(
        id="send",
        intent="Send a note to alice@example.com",
        kind=ProbeKind.POSITIVE,
        expected_tool="send_email",
        approved=True,
    )
    report = evaluate_probes_with_model(_email_snapshot(), [probe], fake)
    assert report.results[0].outcome is ModelProbeOutcome.WRONG_TOOL
    assert report.results[0].unnecessary_tool_call is False
