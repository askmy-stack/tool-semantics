from pathlib import Path

import pytest
from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.probes import load_probes
from tool_semantics.runner import FakeModelRunner, ModelCompletion, RunnerMetadata, ToolCallRequest
from tool_semantics.scanner import capture_manifest, write_snapshot

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]
PROBES_OK = ROOT / "examples" / "probes" / "github_v1_offline.json"
PROBES_UNAPPROVED = ROOT / "examples" / "probes" / "github_v1_unapproved.yaml"
MANIFEST = ROOT / "examples" / "github_server_v1.json"


def test_load_probes_json_and_yaml() -> None:
    json_probes = load_probes(PROBES_OK)
    assert len(json_probes) == 2
    assert json_probes[0].id == "search-open-issues"
    yaml_probes = load_probes(PROBES_UNAPPROVED)
    assert len(yaml_probes) == 2
    assert yaml_probes[0].approved is False


def test_probe_cli_offline_pass(tmp_path: Path) -> None:
    snapshot = tmp_path / "snap.json"
    write_snapshot(capture_manifest(MANIFEST), snapshot)
    md = tmp_path / "report.md"
    js = tmp_path / "report.json"
    result = runner.invoke(
        app,
        [
            "probe",
            str(snapshot),
            "--probes",
            str(PROBES_OK),
            "--markdown-output",
            str(md),
            "--json-output",
            str(js),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "PASS" in result.stdout
    assert md.is_file()
    assert '"mode": "offline"' in js.read_text(encoding="utf-8")


def test_probe_cli_offline_fail(tmp_path: Path) -> None:
    snapshot = tmp_path / "snap.json"
    write_snapshot(capture_manifest(MANIFEST), snapshot)
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"probes":[{"id":"x","intent":"x","kind":"positive","expected_tool":"nope"}]}',
        encoding="utf-8",
    )
    result = runner.invoke(app, ["probe", str(snapshot), "--probes", str(bad)])
    assert result.exit_code == 1
    assert "FAIL" in result.stdout


def test_probe_cli_missing_file_exit_2(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["probe", str(tmp_path / "missing.json"), "--probes", str(PROBES_OK)],
    )
    assert result.exit_code == 2


def test_probe_cli_model_requires_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = tmp_path / "snap.json"
    write_snapshot(capture_manifest(MANIFEST), snapshot)
    monkeypatch.delenv("TOOL_SEMANTICS_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = runner.invoke(
        app,
        ["probe", str(snapshot), "--probes", str(PROBES_OK), "--model"],
    )
    assert result.exit_code == 2
    assert "API key" in result.stdout


def test_probe_cli_model_skips_unapproved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = tmp_path / "snap.json"
    write_snapshot(capture_manifest(MANIFEST), snapshot)
    fake = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "bug"})],
                metadata=RunnerMetadata(provider="fake", model="fake"),
            )
        ]
    )

    def _fake_runner(**kwargs: object) -> FakeModelRunner:
        del kwargs
        return fake

    monkeypatch.setattr("tool_semantics.cli._openai_runner_from_env", _fake_runner)
    result = runner.invoke(
        app,
        ["probe", str(snapshot), "--probes", str(PROBES_UNAPPROVED), "--model"],
    )
    # Both probes unapproved → SKIPPED → report.passed is True (skipped excluded).
    assert result.exit_code == 0, result.stdout
    assert "skipped" in result.stdout.lower()
    assert fake.call_count == 0
