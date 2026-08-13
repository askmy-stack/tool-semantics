import json
from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.cli import app

runner = CliRunner()
FIXTURE = Path(__file__).parent / "fixtures" / "fake_mcp_server.py"


def test_capture_verbose_writes_stderr(tmp_path: Path) -> None:
    output = tmp_path / "snap.json"
    result = runner.invoke(
        app,
        [
            "capture",
            "examples/github_server_v1.json",
            "-o",
            str(output),
            "--verbose",
        ],
    )
    assert result.exit_code == 0
    assert "Reading manifest" in result.stderr
    assert output.is_file()


def test_capture_writes_requested_provenance(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.json"
    provenance = tmp_path / "snapshot.provenance.json"
    result = runner.invoke(
        app,
        [
            "capture",
            "examples/github_server_v1.json",
            "-o",
            str(snapshot),
            "--provenance-output",
            str(provenance),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(provenance.read_text(encoding="utf-8"))
    assert payload["source"] == {
        "kind": "manifest",
        "location": "examples/github_server_v1.json",
    }


def test_capture_preserves_snapshot_write_os_error_without_provenance(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["capture", "examples/github_server_v1.json", "-o", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, IsADirectoryError)
    assert "Capture failed:" not in result.stdout


def test_capture_mcp_writes_redacted_requested_provenance(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.json"
    provenance = tmp_path / "snapshot.provenance.json"
    result = runner.invoke(
        app,
        [
            "capture-mcp",
            "-o",
            str(snapshot),
            "--provenance-output",
            str(provenance),
            "--",
            "python",
            str(FIXTURE),
            "--token",
            "command-secret",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(provenance.read_text(encoding="utf-8"))
    assert payload["source"] == {
        "kind": "mcp-stdio",
        "command": ["python", str(FIXTURE), "--token", "***REDACTED***"],
    }


def test_compare_verbose_and_config_ignore(tmp_path: Path) -> None:
    baseline = tmp_path / "v1.json"
    candidate = tmp_path / "v2.json"
    config = tmp_path / "rules.toml"
    assert (
        runner.invoke(
            app,
            ["capture", "examples/github_server_v1.json", "-o", str(baseline)],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            ["capture", "examples/github_server_v2.json", "-o", str(candidate)],
        ).exit_code
        == 0
    )
    config.write_text(
        '[ignore]\ncodes = ["tool.removed", "parameter.added_required"]\n',
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "compare",
            str(baseline),
            str(candidate),
            "--config",
            str(config),
            "--verbose",
        ],
    )
    assert "Changes=" in result.stderr
    assert result.exit_code == 0
    assert "compatible" in result.stdout.lower()
