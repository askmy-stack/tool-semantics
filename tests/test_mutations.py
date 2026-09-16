"""Tests for mutation generator and detection metrics (#93)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.mutations import (
    MutationKind,
    MutationSpec,
    apply_mutation,
    render_detection_metrics_markdown,
    run_mutation_corpus,
    run_seeded_mutations,
)
from tool_semantics.scanner import capture_manifest

runner = CliRunner()
FIXTURE = Path("examples/github_server_v1.json")
CORPUS = Path("benchmarks/mutations")


def test_seeded_mutations_detect_all_operators() -> None:
    snap = capture_manifest(FIXTURE)
    metrics = run_seeded_mutations(snap, seed=0)
    assert metrics.passed
    assert metrics.cases == len(MutationKind)
    assert metrics.recall == 1.0
    assert metrics.precision == 1.0
    assert "Mutation detection metrics" in render_detection_metrics_markdown(metrics)


def test_mutation_corpus_folders() -> None:
    assert CORPUS.is_dir()
    metrics = run_mutation_corpus(CORPUS)
    assert metrics.cases >= 6
    assert metrics.passed, render_detection_metrics_markdown(metrics)


def test_rename_and_remove_operators() -> None:
    snap = capture_manifest(FIXTURE)
    renamed = apply_mutation(
        snap,
        MutationSpec(kind=MutationKind.RENAME, tool="search_issues", seed=1),
    )
    assert any(tool.name == "search_issues_v2" for tool in renamed.mutated.tools)
    removed = apply_mutation(
        snap, MutationSpec(kind=MutationKind.REMOVE_TOOL, tool="create_issue", seed=2)
    )
    assert all(tool.name != "create_issue" for tool in removed.mutated.tools)


def test_mutate_cli() -> None:
    result = runner.invoke(
        app,
        ["mutate", "examples/github_server_v1.json", "--seed", "0"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Mutation detection metrics" in result.stdout
