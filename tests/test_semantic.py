"""Tests for semantic distance matrix / clustering (#82)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.benchmarks import snapshot_from_manifest, synthesize_manifest
from tool_semantics.cli import app
from tool_semantics.scanner import capture_manifest, write_snapshot
from tool_semantics.semantic import (
    LARGE_CATALOG_N,
    ActionFamily,
    classify_action_family,
    compute_semantic_matrix,
    render_semantic_matrix_markdown,
)

runner = CliRunner()
FIXTURE = Path("examples/semantic/github_catalog.json")


def test_action_families_and_matrix_on_github_catalog() -> None:
    snap = capture_manifest(FIXTURE)
    assert classify_action_family(next(t for t in snap.tools if t.name == "search_issues")) == (
        ActionFamily.SEARCH
    )
    assert classify_action_family(next(t for t in snap.tools if t.name == "create_issue")) == (
        ActionFamily.WRITE
    )
    assert (
        classify_action_family(next(t for t in snap.tools if t.name == "delete_repository"))
        == ActionFamily.DESTRUCTIVE
    )

    report = compute_semantic_matrix(snap, top_k=10, similar_threshold=0.3)
    assert report.tool_count == 8
    assert report.pairs
    assert report.top_similar
    families = {cluster.label: cluster.tools for cluster in report.action_families}
    assert "search_issues" in families["SEARCH"]
    assert "create_issue" in families["WRITE"]
    assert "delete_repository" in families["DESTRUCTIVE"]
    md = render_semantic_matrix_markdown(report)
    assert "Semantic distance" in md
    assert "Action families" in md


def test_large_catalog_subsamples_unless_allow_large() -> None:
    snap = snapshot_from_manifest(synthesize_manifest(LARGE_CATALOG_N, prefix="tool"))
    limited = compute_semantic_matrix(snap, allow_large=False, max_tools=50)
    assert limited.subsampled
    assert limited.compared_count == 50
    assert "subsampled" in limited.subsample_note.lower() or "Catalog has" in limited.subsample_note

    # Full matrix is expensive; only check it does not subsample when allowed with smaller N.
    small = snapshot_from_manifest(synthesize_manifest(20, prefix="t"))
    full = compute_semantic_matrix(small, allow_large=True)
    assert not full.subsampled
    assert full.compared_count == 20


def test_cluster_cli(tmp_path: Path) -> None:
    snap_path = tmp_path / "snap.json"
    write_snapshot(capture_manifest(FIXTURE), snap_path)
    result = runner.invoke(app, ["cluster", str(snap_path), "--top", "5"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Semantic distance" in result.stdout
    assert "SEARCH" in result.stdout
