from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.cli import app

runner = CliRunner()


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
