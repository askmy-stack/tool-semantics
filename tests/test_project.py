"""Tests for standardized `.tool-semantics/` project layout (#85)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.project import (
    discover_default_probes,
    project_paths,
    scaffold_project,
)


def test_scaffold_project_creates_layout(tmp_path: Path) -> None:
    paths = scaffold_project(tmp_path)
    assert paths.layout.is_dir()
    assert paths.baselines.is_dir()
    assert paths.probes.is_dir()
    assert paths.traces.is_dir()
    assert paths.config.is_file()
    assert paths.behaviors.is_file()
    assert (paths.probes / "example.json").is_file()
    assert (paths.layout / "README.md").is_file()
    # Second init without force preserves content
    paths.config.write_text("# custom\n", encoding="utf-8")
    scaffold_project(tmp_path, force=False)
    assert paths.config.read_text(encoding="utf-8") == "# custom\n"
    scaffold_project(tmp_path, force=True)
    assert "fail_at_or_above" in paths.config.read_text(encoding="utf-8")


def test_discover_default_probes(tmp_path: Path) -> None:
    assert discover_default_probes(tmp_path) is None
    scaffold_project(tmp_path)
    found = discover_default_probes(tmp_path)
    assert found is not None
    assert found.name == "example.json"
    preferred = project_paths(tmp_path).probes / "probes.json"
    preferred.write_text('{"probes": []}\n', encoding="utf-8")
    assert discover_default_probes(tmp_path) == preferred


def test_init_cli(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Initialized Tool-Semantics layout" in result.output
    assert (tmp_path / ".tool-semantics" / "probes").is_dir()
    assert (tmp_path / ".tool-semantics.toml").is_file()
