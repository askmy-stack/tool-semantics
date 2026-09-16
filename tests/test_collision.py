"""Tests for tool collision / confusability detection (#79)."""

from __future__ import annotations

from pathlib import Path

from tool_semantics.collision import (
    confusability_score,
    detect_collisions,
)
from tool_semantics.config import load_config
from tool_semantics.diff import Severity, compare_snapshots
from tool_semantics.embeddings import clear_provider, register_provider
from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract, ToolParameter
from tool_semantics.scanner import write_snapshot


def _param(name: str) -> ToolParameter:
    return ToolParameter(name=name, schema={"type": "string"}, required=True)


def _issue_tool(name: str) -> ToolContract:
    return ToolContract(
        name=name,
        description="Search or find GitHub issues by query text and repository.",
        parameters=[_param("query"), _param("repo")],
        risk=RiskLevel.READ_ONLY,
    )


def _delete_tool() -> ToolContract:
    return ToolContract(
        name="delete_repository",
        description="Permanently delete a GitHub repository and all of its data.",
        parameters=[_param("owner"), _param("name")],
        risk=RiskLevel.DESTRUCTIVE,
    )


def _snapshot(tools: list[ToolContract], version: str) -> InterfaceSnapshot:
    return InterfaceSnapshot(
        server_name="fixture",
        server_version=version,
        tools=tools,
    )


def test_confusable_issue_tools_collide_delete_does_not() -> None:
    search = _issue_tool("search_issue")
    find = _issue_tool("find_issue")
    query = _issue_tool("query_issue")
    delete = _delete_tool()

    search_find, _ = confusability_score(search, find)
    search_delete, _ = confusability_score(search, delete)
    assert search_find >= 0.55
    assert search_delete < 0.55

    pairs = detect_collisions([search, find, query, delete], threshold=0.55)
    names = {(pair.left, pair.right) for pair in pairs}
    assert ("find_issue", "search_issue") in names
    assert ("query_issue", "search_issue") in names
    assert ("find_issue", "query_issue") in names
    assert not any("delete_repository" in (pair.left, pair.right) for pair in pairs)


def test_compare_emits_tool_collision_warning_and_cluster(tmp_path: Path) -> None:
    baseline = _snapshot([_issue_tool("search_issue"), _delete_tool()], "v1")
    candidate = _snapshot(
        [
            _issue_tool("search_issue"),
            _issue_tool("find_issue"),
            _issue_tool("query_issue"),
            _delete_tool(),
        ],
        "v2",
    )
    report = compare_snapshots(baseline, candidate, collision_threshold=0.55)
    collisions = [change for change in report.changes if change.code == "tool.collision"]
    assert collisions
    assert all(change.severity is Severity.WARNING for change in collisions)
    assert any("TOOL COLLISION WARNING" in change.message for change in collisions)
    assert any(change.subject == "find_issue~search_issue" for change in collisions)
    # Three overlapping issue tools → multi-member cluster warning.
    assert any(
        "confusable cluster" in change.message and "find_issue" in change.subject
        for change in collisions
    )
    # Warnings alone do not mark the report incompatible.
    assert report.is_compatible


def test_collision_threshold_configurable(tmp_path: Path) -> None:
    config_path = tmp_path / ".tool-semantics.toml"
    config_path.write_text(
        "[diff]\ncollision_threshold = 0.99\ndetect_collisions = true\n",
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config.diff.collision_threshold == 0.99

    tools = [_issue_tool("search_issue"), _issue_tool("find_issue")]
    report = compare_snapshots(
        _snapshot(tools, "a"),
        _snapshot(tools, "b"),
        collision_threshold=config.diff.collision_threshold,
    )
    assert not any(change.code == "tool.collision" for change in report.changes)


def test_detect_collisions_can_be_disabled() -> None:
    tools = [_issue_tool("search_issue"), _issue_tool("find_issue")]
    report = compare_snapshots(
        _snapshot(tools, "a"),
        _snapshot(tools, "b"),
        detect_collisions=False,
    )
    assert not any(change.code == "tool.collision" for change in report.changes)


def test_embedding_layer_blends_when_provider_supplied() -> None:
    class FakeEmbeddings:
        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            # Identical vectors → cosine 1.0, pulls score up when Layer-1 is middling.
            return [[1.0, 0.0], [1.0, 0.0]]

    left = ToolContract(
        name="alpha_tool",
        description="completely different wording here",
        parameters=[_param("x")],
    )
    right = ToolContract(
        name="beta_helper",
        description="unrelated phrase salad totally",
        parameters=[_param("y")],
    )
    token_score, layer = confusability_score(left, right)
    assert layer == "token"
    mixed_score, mixed_layer = confusability_score(left, right, embeddings=FakeEmbeddings())
    assert mixed_layer == "mixed"
    assert mixed_score > token_score


def test_use_embeddings_config_requires_registered_provider(tmp_path: Path) -> None:
    clear_provider()
    config_path = tmp_path / "cfg.toml"
    config_path.write_text("[diff]\nuse_embeddings = true\n", encoding="utf-8")
    config = load_config(config_path)
    assert config.diff.use_embeddings is True

    class UnitProvider:
        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

    register_provider(lambda: UnitProvider())
    try:
        from tool_semantics.collision import try_load_default_embeddings

        assert try_load_default_embeddings() is not None
    finally:
        clear_provider()


def test_cli_compare_surfaces_collision(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from tool_semantics.cli import app

    baseline = _snapshot([_issue_tool("search_issue")], "v1")
    candidate = _snapshot(
        [_issue_tool("search_issue"), _issue_tool("find_issue")],
        "v2",
    )
    b_path = tmp_path / "b.json"
    c_path = tmp_path / "c.json"
    write_snapshot(baseline, b_path)
    write_snapshot(candidate, c_path)
    result = CliRunner().invoke(
        app,
        ["compare", str(b_path), str(c_path), "--policy", "permissive"],
    )
    assert result.exit_code == 0
    assert "tool.collision" in result.output
    assert "find_issue~search_issue" in result.output
