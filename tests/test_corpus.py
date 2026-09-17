"""Tests for multi-domain benchmark corpus (#92)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.corpus import discover_corpus_cases, render_corpus_markdown, run_corpus

runner = CliRunner()
ROOT = Path("benchmarks")


def test_corpus_discovers_three_full_domains_and_stubs() -> None:
    cases, stubs = discover_corpus_cases(ROOT)
    assert {path.name for path in cases} >= {"github", "filesystem", "database"}
    assert set(stubs) >= {"messaging", "project-management", "generic"}


def test_corpus_run_passes_expected_detections() -> None:
    report = run_corpus(ROOT)
    assert report.passed, render_corpus_markdown(report)
    assert len(report.results) >= 3
    assert all(item.passed for item in report.results)


def test_corpus_cli() -> None:
    result = runner.invoke(app, ["corpus"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Benchmark corpus" in result.stdout
    assert "github" in result.stdout
