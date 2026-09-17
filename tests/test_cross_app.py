"""Tests for cross-application / multi-namespace workflows (#112)."""

from __future__ import annotations

import json
from pathlib import Path

from tool_semantics.cross_app import (
    AttributionConfidence,
    CrossAppTask,
    CrossAppTrace,
    attribute_failure,
    evaluate_cross_app,
    evaluate_cross_app_suite,
    render_cross_app_markdown,
)
from tool_semantics.diff import Change, CompatibilityReport, Severity

FIXTURE = Path("examples/cross_app/drive_gmail_calendar_crm.json")


def _load_fixture() -> tuple[CrossAppTask, CrossAppTrace, CrossAppTrace]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    task = CrossAppTask.model_validate(payload["task"])
    passing = CrossAppTrace.model_validate(payload["passing_trace"])
    failing = CrossAppTrace.model_validate(payload["failing_trace_missing_gmail"])
    return task, passing, failing


def test_multi_namespace_fixture_passes() -> None:
    task, passing, _failing = _load_fixture()
    result = evaluate_cross_app(task, passing)
    assert result.passed
    assert result.final_state_matched
    assert result.namespace_sequence_ok
    assert result.attribution is None
    assert len(task.namespaces) == 4


def test_failure_attributes_missing_namespace_tools() -> None:
    task, _passing, failing = _load_fixture()
    result = evaluate_cross_app(task, failing)
    assert not result.passed
    assert result.attribution is not None
    assert result.attribution.namespace == "gmail"
    assert result.attribution.confidence == AttributionConfidence.CONFIRMED
    assert "gmail" in result.message


def test_attribute_from_namespace_diffs() -> None:
    task, passing, _failing = _load_fixture()
    # Force failure via bad final state on a copy of the passing trace.
    broken = passing.model_copy(update={"final_state": {"file_id": "file-1", "email_sent": False}})
    gmail_diff = CompatibilityReport(
        baseline="gmail-v1",
        candidate="gmail-v2",
        changes=[
            Change(
                code="tool.removed",
                severity=Severity.BREAKING,
                subject="gmail_send",
                message="gmail_send removed",
            )
        ],
    )
    result = evaluate_cross_app(
        task,
        broken,
        namespace_diffs={
            "gmail": gmail_diff,
            "drive": CompatibilityReport(baseline="d1", candidate="d2", changes=[]),
        },
    )
    assert not result.passed
    assert result.attribution is not None
    assert result.attribution.namespace == "gmail"
    assert "tool.removed" in result.attribution.change_codes
    assert result.attribution.confidence == AttributionConfidence.LIKELY

    # Direct API
    attr = attribute_failure(task, broken, namespace_diffs={"gmail": gmail_diff})
    assert attr.namespace == "gmail"


def test_suite_report_markdown() -> None:
    task, passing, failing = _load_fixture()
    report = evaluate_cross_app_suite([task], [passing, failing])
    # Suite maps by task_id — last wins if duplicates; use unique traces carefully
    report = evaluate_cross_app_suite(
        [task, task.model_copy(update={"id": "schedule-from-drive-b"})],
        [
            passing,
            failing.model_copy(update={"task_id": "schedule-from-drive-b"}),
        ],
    )
    assert len(report.results) == 2
    assert report.results[0].passed
    assert not report.results[1].passed
    md = render_cross_app_markdown(report)
    assert "Cross-application workflows" in md
    assert "gmail" in md
