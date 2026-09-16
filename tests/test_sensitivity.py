"""Tests for description / catalog sensitivity research harness (#95)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract, ToolParameter
from tool_semantics.probes import Probe, ProbeKind
from tool_semantics.scanner import capture_manifest, write_snapshot
from tool_semantics.sensitivity import (
    RewriteLevel,
    apply_description_level,
    description_aware_factory,
    export_catalog_sensitivity_csv,
    export_description_sensitivity_csv,
    export_sensitivity_json,
    pad_catalog,
    render_catalog_sensitivity_markdown,
    render_description_sensitivity_markdown,
    rewrite_description,
    run_catalog_sensitivity,
    run_description_sensitivity,
)

runner = CliRunner()


def _snapshot() -> InterfaceSnapshot:
    return InterfaceSnapshot(
        server_name="demo",
        tools=[
            ToolContract(
                name="search_issues",
                description="Search GitHub issues by query text",
                parameters=[
                    ToolParameter(name="query", schema={"type": "string"}, required=True),
                ],
                risk=RiskLevel.READ_ONLY,
            ),
            ToolContract(
                name="create_issue",
                description="Create a new repository issue with title",
                parameters=[
                    ToolParameter(name="title", schema={"type": "string"}, required=True),
                ],
                risk=RiskLevel.EXTERNAL_WRITE,
            ),
        ],
    )


def _probe() -> Probe:
    return Probe(
        id="search",
        intent="Search GitHub issues by query",
        kind=ProbeKind.POSITIVE,
        expected_tool="search_issues",
        required_params=["query"],
        approved=True,
        approved_by="ci",
    )


def test_rewrite_levels_change_text() -> None:
    text = "Search GitHub issues by query text"
    assert rewrite_description(text, RewriteLevel.ORIGINAL) == text
    light = rewrite_description(text, RewriteLevel.LIGHT_PARAPHRASE)
    assert light != text
    assert "find" in light or "ticket" in light
    short = rewrite_description(text, RewriteLevel.SHORTEN)
    assert len(short.split()) < len(text.split())
    expanded = rewrite_description(text, RewriteLevel.EXPAND)
    assert text in expanded
    assert "carefully" in expanded
    severe = rewrite_description(text, RewriteLevel.SEVERE)
    assert "opaque" in severe
    assert "Search" not in severe


def test_apply_description_level_updates_metadata() -> None:
    snap = apply_description_level(_snapshot(), RewriteLevel.SHORTEN)
    assert snap.metadata["description_rewrite_level"] == int(RewriteLevel.SHORTEN)
    assert snap.tools[0].description != _snapshot().tools[0].description


def test_pad_catalog_reaches_target() -> None:
    core = _snapshot()
    padded = pad_catalog(core, 25)
    assert len(padded.tools) == 25
    names = [tool.name for tool in padded.tools]
    assert names.count("search_issues") == 1
    assert padded.metadata["catalog_size"] == 25
    assert pad_catalog(core, 1) is core or len(pad_catalog(core, 1).tools) == len(core.tools)


def test_description_sensitivity_detects_drop() -> None:
    report = run_description_sensitivity(
        _snapshot(),
        [_probe()],
        description_aware_factory,
        levels=[RewriteLevel.ORIGINAL, RewriteLevel.SEVERE],
    )
    assert report.baseline_accuracy == 1.0
    assert report.first_drop_level == int(RewriteLevel.SEVERE)
    assert report.levels[-1].selection_accuracy is not None
    assert report.levels[-1].selection_accuracy < report.baseline_accuracy  # type: ignore[operator]
    md = render_description_sensitivity_markdown(report)
    assert "Description sensitivity" in md
    assert "severe" in md
    csv_text = export_description_sensitivity_csv(report)
    assert "selection_accuracy" in csv_text
    assert "severe" in csv_text


def test_catalog_sensitivity_scales(tmp_path: Path) -> None:
    report = run_catalog_sensitivity(
        _snapshot(),
        [_probe()],
        description_aware_factory,
        sizes=(2, 10, 25),
    )
    assert [point.catalog_size for point in report.points] == [2, 10, 25]
    assert all(point.selection_accuracy == 1.0 for point in report.points)
    md = render_catalog_sensitivity_markdown(report)
    assert "Catalog-size sensitivity" in md
    out = tmp_path / "catalog.json"
    export_sensitivity_json(report, out)
    assert out.is_file()
    assert "catalog_size" in out.read_text(encoding="utf-8")
    assert "selection_accuracy" in export_catalog_sensitivity_csv(report)


def test_sensitivity_cli_description(tmp_path: Path) -> None:
    snap_path = tmp_path / "snap.json"
    write_snapshot(capture_manifest(Path("examples/github_server_v1.json")), snap_path)
    probes = tmp_path / "probes.json"
    probes.write_text(
        """
{
  "probes": [
    {
      "id": "search",
      "intent": "Search GitHub issues by query",
      "expected_tool": "search_issues",
      "required_params": ["query"],
      "approved": true,
      "approved_by": "ci"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    json_out = tmp_path / "desc.json"
    md_out = tmp_path / "desc.md"
    csv_out = tmp_path / "desc.csv"
    result = runner.invoke(
        app,
        [
            "sensitivity",
            str(snap_path),
            "--probes",
            str(probes),
            "--mode",
            "description",
            "--fake",
            "--json-output",
            str(json_out),
            "--markdown-output",
            str(md_out),
            "--csv-output",
            str(csv_out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Description sensitivity" in result.output
    assert json_out.is_file()
    assert md_out.is_file()
    assert csv_out.is_file()


def test_sensitivity_cli_catalog(tmp_path: Path) -> None:
    snap_path = tmp_path / "snap.json"
    write_snapshot(_snapshot(), snap_path)
    probes = tmp_path / "probes.json"
    probes.write_text(
        """
{
  "probes": [
    {
      "id": "search",
      "intent": "Search GitHub issues by query",
      "expected_tool": "search_issues",
      "required_params": ["query"],
      "approved": true,
      "approved_by": "ci"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "sensitivity",
            str(snap_path),
            "--probes",
            str(probes),
            "--mode",
            "catalog",
            "--sizes",
            "2,5",
            "--fake",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Catalog-size sensitivity" in result.output
