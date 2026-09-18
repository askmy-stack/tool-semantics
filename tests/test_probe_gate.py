"""Tests for compare/Action probe gating (#58)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.config import load_config
from tool_semantics.probe_gate import (
    ProbeGateSettings,
    ProbeThresholds,
    evaluate_model_thresholds,
    evaluate_offline_thresholds,
    evaluate_stability_thresholds,
    run_probe_gate_for_snapshot,
)
from tool_semantics.probes import (
    ModelProbeOutcome,
    ModelProbeReport,
    ModelProbeResult,
    ProbeMetrics,
    ProbeReport,
    ProbeResult,
    StabilityProbeSummary,
    StabilityReport,
    load_probes,
)
from tool_semantics.runner import FakeModelRunner, ModelCompletion, RunnerMetadata, ToolCallRequest
from tool_semantics.scanner import capture_manifest, write_snapshot

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]
PROBES_OK = ROOT / "examples" / "probes" / "github_v1_offline.json"
MANIFEST_V1 = ROOT / "examples" / "github_server_v1.json"


def test_load_config_probes_section(tmp_path: Path) -> None:
    probes = tmp_path / "suite.json"
    probes.write_text(PROBES_OK.read_text(encoding="utf-8"), encoding="utf-8")
    config = tmp_path / "rules.toml"
    config.write_text(
        (
            "[probes]\n"
            'file = "suite.json"\n'
            'target = "both"\n'
            'mode = "offline"\n'
            "trials = 1\n"
            "[probes.thresholds]\n"
            "min_pass_rate = 0.9\n"
            "min_tool_selection_accuracy = 0.8\n"
            "fail_on_unstable = false\n"
        ),
        encoding="utf-8",
    )
    loaded = load_config(config)
    assert loaded.probes.file == probes
    assert loaded.probes.target == "both"
    assert loaded.probes.thresholds.min_pass_rate == 0.9
    assert loaded.probes.thresholds.min_tool_selection_accuracy == 0.8
    assert loaded.probes.thresholds.fail_on_unstable is False


def test_evaluate_offline_thresholds() -> None:
    report = ProbeReport(
        results=[
            ProbeResult(probe_id="a", passed=True, message="ok"),
            ProbeResult(probe_id="b", passed=False, message="fail"),
        ]
    )
    assert evaluate_offline_thresholds(report, ProbeThresholds(min_pass_rate=1.0))
    assert not evaluate_offline_thresholds(report, ProbeThresholds(min_pass_rate=0.5))


def test_evaluate_model_and_stability_thresholds() -> None:
    metrics = ProbeMetrics(
        probe_count=1,
        evaluated_count=1,
        tool_selection_accuracy=0.5,
        argument_validity_rate=1.0,
    )
    model = ModelProbeReport(
        results=[
            ModelProbeResult(
                probe_id="a",
                passed=True,
                message="ok",
                outcome=ModelProbeOutcome.OK,
                tool_selection_correct=True,
                arguments_valid=True,
            )
        ]
    )
    breaches = evaluate_model_thresholds(
        model,
        metrics,
        ProbeThresholds(min_pass_rate=1.0, min_tool_selection_accuracy=0.9),
    )
    assert any("tool_selection_accuracy" in item for item in breaches)

    stability = StabilityReport(
        trial_count=2,
        summaries=[
            StabilityProbeSummary(
                probe_id="a",
                trials=[],
                stability_score=0.4,
                unstable=True,
                deterministic_failure=False,
                aggregate_passed=True,
                message="flaky",
            )
        ],
        metrics=metrics,
    )
    stab_breaches = evaluate_stability_thresholds(
        stability,
        ProbeThresholds(min_stability_score=0.9, fail_on_unstable=True),
    )
    assert any("unstable" in item for item in stab_breaches)
    assert any("stability_score" in item for item in stab_breaches)


def test_compare_offline_probe_gate_pass(tmp_path: Path) -> None:
    # Identical snapshots so structural policy passes; only probes exercise the gate.
    same = tmp_path / "same.json"
    write_snapshot(capture_manifest(MANIFEST_V1), same)
    js = tmp_path / "report.json"
    md = tmp_path / "report.md"
    result = runner.invoke(
        app,
        [
            "compare",
            str(same),
            str(same),
            "--probes",
            str(PROBES_OK),
            "--probe-mode",
            "offline",
            "--json-output",
            str(js),
            "--markdown-output",
            str(md),
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert payload["probes"]["enabled"] is True
    assert payload["probes"]["failed"] is False
    assert payload["policy"]["probe_failed"] is False
    assert "Behavioral probes" in md.read_text(encoding="utf-8")
    assert "PASS" in result.stdout


def test_compare_offline_probe_gate_fail(tmp_path: Path) -> None:
    same = tmp_path / "same.json"
    write_snapshot(capture_manifest(MANIFEST_V1), same)
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "probes": [
                    {
                        "id": "missing",
                        "intent": "x",
                        "kind": "positive",
                        "expected_tool": "does_not_exist",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    js = tmp_path / "report.json"
    result = runner.invoke(
        app,
        [
            "compare",
            str(same),
            str(same),
            "--probes",
            str(bad),
            "--policy",
            "permissive",
            "--json-output",
            str(js),
        ],
    )
    assert result.exit_code == 1, result.stdout
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert payload["probes"]["failed"] is True
    assert payload["policy"]["probe_failed"] is True
    assert payload["policy"]["structural_failed"] is False
    assert payload["probes"]["breaches"]


def test_compare_probe_gate_from_config(tmp_path: Path) -> None:
    same = tmp_path / "same.json"
    write_snapshot(capture_manifest(MANIFEST_V1), same)
    probes = tmp_path / "suite.json"
    probes.write_text(PROBES_OK.read_text(encoding="utf-8"), encoding="utf-8")
    config = tmp_path / ".tool-semantics.toml"
    config.write_text(
        f'[probes]\nfile = "{probes.name}"\nmode = "offline"\ntarget = "candidate"\n',
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["compare", str(same), str(same), "--config", str(config)],
    )
    assert result.exit_code == 0, result.stdout
    assert "Probes:" in result.stdout


def test_compare_missing_probe_file_exit_2(tmp_path: Path) -> None:
    same = tmp_path / "same.json"
    write_snapshot(capture_manifest(MANIFEST_V1), same)
    result = runner.invoke(
        app,
        ["compare", str(same), str(same), "--probes", str(tmp_path / "missing.json")],
    )
    assert result.exit_code == 2
    assert "Probe file not found" in result.stdout


def test_compare_model_probe_gate_missing_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    same = tmp_path / "same.json"
    write_snapshot(capture_manifest(MANIFEST_V1), same)
    monkeypatch.delenv("TOOL_SEMANTICS_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = runner.invoke(
        app,
        [
            "compare",
            str(same),
            str(same),
            "--probes",
            str(PROBES_OK),
            "--probe-mode",
            "model",
        ],
    )
    assert result.exit_code == 2
    assert "API key" in result.stdout


def test_compare_model_probe_gate_with_fake_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    same = tmp_path / "same.json"
    write_snapshot(capture_manifest(MANIFEST_V1), same)
    fake = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "open"})],
                metadata=RunnerMetadata(provider="fake", model="fake"),
            ),
            ModelCompletion(
                tool_calls=[],
                metadata=RunnerMetadata(provider="fake", model="fake"),
            ),
        ]
    )

    def _fake_runner(**kwargs: object) -> FakeModelRunner:
        del kwargs
        return fake

    monkeypatch.setattr("tool_semantics.cli._openai_runner_from_env", _fake_runner)
    config = tmp_path / "rules.toml"
    config.write_text(
        (
            "[probes]\n"
            f'file = "{PROBES_OK.resolve()}"\n'
            'mode = "model"\n'
            "[probes.thresholds]\n"
            "min_pass_rate = 0.0\n"
        ),
        encoding="utf-8",
    )
    js = tmp_path / "out.json"
    result = runner.invoke(
        app,
        ["compare", str(same), str(same), "--config", str(config), "--json-output", str(js)],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert payload["probes"]["enabled"] is True
    assert payload["probes"]["targets"][0]["mode"] == "model"
    assert "metrics" in payload["probes"]["targets"][0]


def test_run_probe_gate_for_snapshot_offline() -> None:
    snap = capture_manifest(MANIFEST_V1)
    probes = load_probes(PROBES_OK)
    outcome = run_probe_gate_for_snapshot(
        snap,
        probes,
        ProbeGateSettings(mode="offline", thresholds=ProbeThresholds(min_pass_rate=1.0)),
        target_label="candidate",
    )
    assert outcome.passed
    assert outcome.offline is not None
    assert outcome.mode == "offline"


def test_compare_action_documents_probe_inputs() -> None:
    action = Path(".github/actions/compare/action.yml").read_text(encoding="utf-8")
    assert "probes:" in action
    assert "probe-mode:" in action
    assert "probe-trials:" in action
    assert "probe-failed:" in action
    assert "--probes" in action
    assert "PROBE_FAILED" in action
