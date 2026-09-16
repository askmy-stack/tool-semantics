"""Tests for final-state verification (#105)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.probes import Probe, ProbeKind, evaluate_probes, evaluate_probes_with_model
from tool_semantics.runner import FakeModelRunner, ModelCompletion, RunnerMetadata, ToolCallRequest
from tool_semantics.scanner import capture_manifest, write_snapshot
from tool_semantics.state_verifier import verify_final_state

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "examples" / "github_server_v1.json"
FINAL_STATE_PROBES = ROOT / "examples" / "probes" / "github_v1_final_state.json"


def test_verify_final_state_pass_partial_fail() -> None:
    ok = verify_final_state({"a": 1, "b": "x"}, {"a": 1, "b": "x", "c": 9})
    assert ok.passed
    assert not ok.partial

    partial = verify_final_state({"a": 1, "b": "x"}, {"a": 1, "b": "wrong"})
    assert not partial.passed
    assert partial.partial
    assert partial.matched_count == 1
    assert any(check.key == "b" and not check.matched for check in partial.checks)
    assert "b" in partial.message

    missing = verify_final_state({"a": 1}, None)
    assert not missing.passed
    assert missing.missing_observed
    assert "Observed state was not provided" in missing.message


def test_evaluate_probes_tracks_axes_separately() -> None:
    snap = capture_manifest(MANIFEST)
    probe = Probe(
        id="search",
        intent="find bugs",
        kind=ProbeKind.POSITIVE,
        expected_tool="search_issues",
        required_params=["query"],
        expected_state={"ready": True, "count": 2},
    )
    # Tool call ok, final state partial
    report = evaluate_probes(
        snap,
        [probe],
        observed_states={"search": {"ready": True, "count": 0}},
    )
    result = report.results[0]
    assert result.tool_call_correct is True
    assert result.trajectory_correct is True
    assert result.final_state_correct is False
    assert result.final_state is not None
    assert result.final_state.partial
    assert not result.passed
    assert "count" in result.message


def test_different_trajectories_same_state_pass() -> None:
    """Final-state pass does not depend on which tool path was taken."""
    expected = {"issue_open": True}
    via_create = verify_final_state(expected, {"issue_open": True, "path": "create_issue"})
    via_reopen = verify_final_state(expected, {"issue_open": True, "path": "reopen_issue"})
    assert via_create.passed and via_reopen.passed


def test_model_probe_final_state_with_fake_runner() -> None:
    snap = capture_manifest(MANIFEST)
    probe = Probe(
        id="search",
        intent="find bugs",
        kind=ProbeKind.POSITIVE,
        expected_tool="search_issues",
        approved=True,
        expected_state={"ok": True},
        observed_state={"ok": True},
    )
    fake = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "bug"})],
                metadata=RunnerMetadata(provider="fake", model="fake"),
            )
        ]
    )
    report = evaluate_probes_with_model(snap, [probe], fake)
    assert report.passed
    result = report.results[0]
    assert result.tool_call_correct is True
    assert result.final_state_correct is True


def test_probe_cli_final_state_fixture(tmp_path: Path) -> None:
    snap = tmp_path / "snap.json"
    write_snapshot(capture_manifest(MANIFEST), snap)
    md = tmp_path / "out.md"
    js = tmp_path / "out.json"
    result = runner.invoke(
        app,
        [
            "probe",
            str(snap),
            "--probes",
            str(FINAL_STATE_PROBES),
            "--markdown-output",
            str(md),
            "--json-output",
            str(js),
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert payload["results"][0]["final_state_correct"] is True
    text = md.read_text(encoding="utf-8")
    assert "Final state" in text
    assert "Tool call" in text


def test_probe_cli_observed_states_file(tmp_path: Path) -> None:
    snap = tmp_path / "snap.json"
    write_snapshot(capture_manifest(MANIFEST), snap)
    probes = tmp_path / "probes.json"
    probes.write_text(
        json.dumps(
            {
                "probes": [
                    {
                        "id": "s",
                        "intent": "x",
                        "kind": "positive",
                        "expected_tool": "search_issues",
                        "expected_state": {"done": True},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    observed = tmp_path / "observed.json"
    observed.write_text(json.dumps({"s": {"done": False}}), encoding="utf-8")
    result = runner.invoke(
        app,
        ["probe", str(snap), "--probes", str(probes), "--observed-states", str(observed)],
    )
    assert result.exit_code == 1
    assert "FAIL" in result.stdout
