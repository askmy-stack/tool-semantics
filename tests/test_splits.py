"""Tests for DEV/TEST/VERIFIED corpus splits (#116)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.corpus import render_corpus_markdown, run_corpus
from tool_semantics.splits import (
    DEFAULT_CI_SPLIT,
    ENV_SPLIT,
    CorpusSplit,
    filter_case_dirs,
    load_splits_manifest,
    render_splits_markdown,
    resolve_split,
)

runner = CliRunner()
ROOT = Path("benchmarks")
SPLITS = Path("benchmarks/splits.json")


def test_splits_manifest_has_required_partitions() -> None:
    manifest = load_splits_manifest(SPLITS)
    assert set(manifest.partitions) >= {"dev", "test", "verified"}
    assert manifest.domains_for(CorpusSplit.TEST) == ["toy-test"]
    assert manifest.split_for_domain("toy-dev") == CorpusSplit.DEV
    md = render_splits_markdown(manifest)
    assert "Calibrate" in md
    assert "`test`" in md


def test_resolve_split_defaults_to_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_SPLIT, raising=False)
    assert resolve_split() == CorpusSplit.TEST
    assert DEFAULT_CI_SPLIT == "test"
    monkeypatch.setenv(ENV_SPLIT, "verified")
    assert resolve_split() == CorpusSplit.VERIFIED
    assert resolve_split("dev") == CorpusSplit.DEV


def test_filter_case_dirs() -> None:
    manifest = load_splits_manifest(SPLITS)
    cases = [ROOT / "toy-dev", ROOT / "toy-test", ROOT / "toy-verified"]
    filtered = filter_case_dirs(cases, CorpusSplit.TEST, manifest)
    assert [path.name for path in filtered] == ["toy-test"]


def test_corpus_ci_default_runs_test_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_SPLIT, raising=False)
    report = run_corpus(ROOT)
    assert report.split == "test"
    assert [item.domain for item in report.results] == ["toy-test"]
    assert report.passed, render_corpus_markdown(report)
    assert set(report.skipped_domains) == {"toy-dev", "toy-verified"}


def test_corpus_dev_and_verified_partitions() -> None:
    for split, domain in (
        (CorpusSplit.DEV, "toy-dev"),
        (CorpusSplit.VERIFIED, "toy-verified"),
    ):
        report = run_corpus(ROOT, split=split)
        assert report.split == split.value
        assert [item.domain for item in report.results] == [domain]
        assert report.passed, render_corpus_markdown(report)


def test_duplicate_domain_rejected(tmp_path: Path) -> None:
    path = tmp_path / "splits.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "partitions": {
                    "dev": ["x"],
                    "test": ["x"],
                    "verified": ["y"],
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="both"):
        load_splits_manifest(path)


def test_corpus_cli_default_test() -> None:
    result = runner.invoke(app, ["corpus"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Split: `test`" in result.stdout
    assert "`toy-test`" in result.stdout
    # DEV/VERIFIED are skipped, not executed as result rows with passed=yes exclusively for test.
    assert "cases: 1" in result.stdout


def test_corpus_cli_verified() -> None:
    result = runner.invoke(app, ["corpus", "--split", "verified"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "toy-verified" in result.stdout
