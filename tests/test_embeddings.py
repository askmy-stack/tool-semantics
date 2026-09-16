"""Tests for optional embedding similarity (#117)."""

from __future__ import annotations

from pathlib import Path

from tool_semantics.diff import compare_snapshots
from tool_semantics.embeddings import (
    FakeEmbeddingProvider,
    SimilaritySource,
    embedding_similarity,
    hybrid_tool_similarity,
    similarity_matrix,
)
from tool_semantics.models import ToolContract, ToolParameter
from tool_semantics.scanner import capture_manifest


def test_fake_embeddings_are_deterministic() -> None:
    provider = FakeEmbeddingProvider()
    left = ToolContract(
        name="search_issues",
        description="Search open GitHub issues matching a query.",
        parameters=[ToolParameter(name="query", schema={"type": "string"})],
    )
    right = ToolContract(
        name="find_work_items",
        description="Find open GitHub issues matching a query.",
        parameters=[ToolParameter(name="query", schema={"type": "string"})],
    )
    first = embedding_similarity(left, right, provider)
    second = embedding_similarity(left, right, provider)
    assert first.score == second.score
    assert first.source == SimilaritySource.MODEL_BASED
    assert first.metadata is not None
    assert first.metadata.provider == "fake"
    assert first.score > 0.5


def test_hybrid_blends_token_and_embedding() -> None:
    provider = FakeEmbeddingProvider()
    left = ToolContract(name="a", description="alpha beta")
    right = ToolContract(name="b", description="alpha beta gamma")
    hybrid = hybrid_tool_similarity(left, right, provider, token_score=0.2, embedding_weight=1.0)
    assert hybrid.source == SimilaritySource.HYBRID
    assert hybrid.token_score == 0.2
    assert hybrid.embedding_score is not None


def test_compare_without_embeddings_unchanged() -> None:
    baseline = capture_manifest(Path("examples/github_server_v1.json"))
    candidate = capture_manifest(Path("examples/github_server_v2.json"))
    plain = compare_snapshots(baseline, candidate)
    with_fake = compare_snapshots(
        baseline, candidate, embedding_provider=FakeEmbeddingProvider(), rename_threshold=0.3
    )
    # Deterministic path still runs; embedding path may add renames but must not crash.
    assert plain.changes
    assert with_fake.changes


def test_similarity_matrix_metadata() -> None:
    tools = [
        ToolContract(name="search_issues", description="search issues"),
        ToolContract(name="find_issues", description="find issues"),
        ToolContract(name="weather", description="forecast"),
    ]
    matrix = similarity_matrix(tools, FakeEmbeddingProvider())
    assert matrix
    assert all(item.metadata and item.metadata.model for item in matrix)
    assert matrix[0].source == SimilaritySource.MODEL_BASED
