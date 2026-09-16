"""Tests for task difficulty / messiness metadata (#109)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tool_semantics.difficulty import (
    MessinessBand,
    group_results_by_messiness,
    render_messiness_groups_markdown,
)
from tool_semantics.probes import TaskDifficulty, evaluate_probes, load_probes
from tool_semantics.report import render_offline_probe_report_markdown
from tool_semantics.scanner import capture_manifest


def test_task_difficulty_validation_and_bands() -> None:
    easy = TaskDifficulty(messiness=2, tool_call_count=1)
    assert easy.messiness_band() == "low"
    assert TaskDifficulty(messiness=5).messiness_band() == "medium"
    assert TaskDifficulty(messiness=9).messiness_band() == "high"
    with pytest.raises(ValueError):
        TaskDifficulty(messiness=11)
    suggested = TaskDifficulty(
        tool_call_count=5,
        candidate_tool_count=4,
        cross_tool_dependencies=True,
        stateful=True,
        ambiguous_tool_choice=True,
        permission_complexity=2,
        irreversible_side_effects=True,
        requires_error_recovery=True,
    ).suggested_messiness()
    assert 7 <= suggested <= 10


def test_group_results_by_messiness_and_report() -> None:
    snapshot = capture_manifest(Path("examples/github_server_v1.json"))
    probes = load_probes(Path("examples/probes/github_v1_with_difficulty.json"))
    assert all(probe.difficulty is not None for probe in probes)
    report = evaluate_probes(snapshot, probes)
    groups = group_results_by_messiness(probes, report.results)
    assert groups["low"].probe_count == 1
    assert groups["medium"].probe_count == 1
    assert groups["high"].probe_count == 1
    md = render_offline_probe_report_markdown(report, probes=probes)
    assert "Success by messiness" in md
    assert "`low`" in md
    assert render_messiness_groups_markdown(groups)
    assert MessinessBand.LOW.value == "low"
