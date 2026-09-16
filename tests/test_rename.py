"""Tests for multi-signal rename confidence (#80)."""

from __future__ import annotations

from tool_semantics.diff import compare_snapshots
from tool_semantics.models import InterfaceSnapshot, ToolContract, ToolParameter
from tool_semantics.rename import (
    RenameConfidence,
    detect_rename_candidates,
    format_rename_message,
    score_rename_pair,
)


def _tool(
    name: str,
    description: str,
    params: list[str],
    *,
    output_schema: dict[str, object] | None = None,
) -> ToolContract:
    return ToolContract(
        name=name,
        description=description,
        parameters=[
            ToolParameter(name=param, schema={"type": "string"}, required=True) for param in params
        ],
        output_schema=output_schema,
    )


def test_clear_rename_is_high_confidence() -> None:
    old = _tool(
        "search_issues",
        "Search GitHub issues matching a query",
        ["query", "state"],
        output_schema={"type": "object"},
    )
    new = _tool(
        "find_issues",
        "Search GitHub issues matching a query string",
        ["query", "state"],
        output_schema={"type": "object"},
    )
    score, signals = score_rename_pair(old, new)
    assert score >= 0.60
    assert signals.parameters == 1.0
    candidates = detect_rename_candidates({"search_issues": old}, {"find_issues": new})
    assert len(candidates) == 1
    assert candidates[0].confidence in {RenameConfidence.MEDIUM, RenameConfidence.HIGH}
    message = format_rename_message(candidates[0])
    assert "rename confidence" in message
    assert "signals:" in message
    assert "parameters=" in message


def test_unrelated_add_remove_has_no_rename() -> None:
    removed = _tool("search_issues", "Search GitHub issues", ["query"])
    added = _tool(
        "delete_repository",
        "Permanently destroy a GitHub repository and all contents",
        ["owner", "name"],
    )
    candidates = detect_rename_candidates({"search_issues": removed}, {"delete_repository": added})
    assert candidates == []
    report = compare_snapshots(
        InterfaceSnapshot(server_name="d", tools=[removed]),
        InterfaceSnapshot(server_name="d", tools=[added]),
    )
    assert not any(change.code == "tool.renamed" for change in report.changes)
    assert any(change.code == "tool.removed" for change in report.changes)
    assert any(change.code == "tool.added" for change in report.changes)


def test_ambiguous_partial_overlap_is_low_or_absent() -> None:
    removed = _tool("list_repos", "List repositories for a user", ["user"])
    added = _tool("list_pull_requests", "List pull requests in a repository", ["repo"])
    score, _ = score_rename_pair(removed, added)
    # Shared "list" token only — should stay below default threshold.
    assert score < 0.55
    candidates = detect_rename_candidates({"list_repos": removed}, {"list_pull_requests": added})
    assert candidates == []


def test_default_keeps_removed_added_collapse_opt_in() -> None:
    old = _tool("search_issues", "Search GitHub issues matching a query", ["query", "state"])
    new = _tool("find_issues", "Search GitHub issues matching a query string", ["query", "state"])
    baseline = InterfaceSnapshot(server_name="d", tools=[old])
    candidate = InterfaceSnapshot(server_name="d", tools=[new])

    default = compare_snapshots(baseline, candidate)
    assert any(c.code == "tool.renamed" for c in default.changes)
    assert any(c.code == "tool.removed" for c in default.changes)
    assert any(c.code == "tool.added" for c in default.changes)

    collapsed = compare_snapshots(baseline, candidate, collapse_renames=True)
    assert any(c.code == "tool.renamed" for c in collapsed.changes)
    assert not any(c.code == "tool.removed" for c in collapsed.changes)
    assert not any(c.code == "tool.added" for c in collapsed.changes)


def test_embedding_boost_changes_score() -> None:
    class FakeEmbeddings:
        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0], [1.0, 0.0]]

    left = _tool("alpha_one", "totally different wording", ["x"])
    right = _tool("beta_two", "unrelated phrase salad", ["y"])
    base, _ = score_rename_pair(left, right)
    boosted, signals = score_rename_pair(left, right, embeddings=FakeEmbeddings())
    assert signals.embedding == 1.0
    assert boosted > base
