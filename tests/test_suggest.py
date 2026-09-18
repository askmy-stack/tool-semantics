"""Tests for adapter suggestion drafts (#62)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.adapters import CompatibilityProxy
from tool_semantics.cli import app
from tool_semantics.diff import compare_snapshots
from tool_semantics.models import InterfaceSnapshot, ToolContract, ToolParameter
from tool_semantics.scanner import capture_manifest, write_snapshot
from tool_semantics.suggest import SuggestionConfidence, suggest_adapter


def test_suggest_adapter_github_v1_v2() -> None:
    baseline = capture_manifest(Path("examples/github_server_v1.json"))
    candidate = capture_manifest(Path("examples/github_server_v2.json"))
    suggestion = suggest_adapter(baseline, candidate)
    assert suggestion.auto_apply is False
    # search_issues → find_work_items via suggestion-threshold rename
    assert any(alias.from_name == "search_issues" for alias in suggestion.adapter.aliases)
    assert any(alias.to_name == "find_work_items" for alias in suggestion.adapter.aliases)
    # query → search_expression and/or state → status when similarity allows
    rename_maps = [item.rename for item in suggestion.adapter.arguments]
    flat = {k: v for mapping in rename_maps for k, v in mapping.items()}
    assert "query" in flat or "state" in flat
    # Required repository add is skipped (no safe default)
    assert any(
        note.confidence == SuggestionConfidence.SKIPPED and "repository" in note.subject
        for note in suggestion.notes
    )


def test_suggest_adapter_from_tool_renamed_and_enum() -> None:
    baseline = InterfaceSnapshot(
        server_name="demo",
        server_version="1",
        tools=[
            ToolContract(
                name="list_items",
                description="List work items by status filter",
                parameters=[
                    ToolParameter(
                        name="status",
                        schema={"type": "string", "enum": ["open", "closed"]},
                        required=True,
                    )
                ],
            )
        ],
    )
    candidate = InterfaceSnapshot(
        server_name="demo",
        server_version="2",
        tools=[
            ToolContract(
                name="list_work_items",
                description="List work items by status filter",
                parameters=[
                    ToolParameter(
                        name="status",
                        schema={"type": "string", "enum": ["open", "closed", "archived"]},
                        required=True,
                    )
                ],
            )
        ],
    )
    report = compare_snapshots(baseline, candidate)
    suggestion = suggest_adapter(baseline, candidate, report=report)
    assert suggestion.adapter.aliases
    # Cardinality differs → enum remap skipped
    assert any(
        note.confidence == SuggestionConfidence.SKIPPED and "enum" in note.message.lower()
        for note in suggestion.notes
    )


def test_suggested_adapter_is_usable_via_proxy() -> None:
    baseline = capture_manifest(Path("examples/github_server_v1.json"))
    candidate = capture_manifest(Path("examples/github_server_v2.json"))
    suggestion = suggest_adapter(baseline, candidate)
    proxy = CompatibilityProxy(suggestion.adapter)
    tool, args = proxy.route_call("search_issues", {"query": "bug", "state": "open"})
    assert tool == "find_work_items"
    # At least one renamed arg should land under the modern name when mapped
    assert "query" not in args or "search_expression" in args or args.get("query") == "bug"


def test_suggest_adapter_cli(tmp_path: Path) -> None:
    baseline = capture_manifest(Path("examples/github_server_v1.json"))
    candidate = capture_manifest(Path("examples/github_server_v2.json"))
    base_path = tmp_path / "v1.json"
    cand_path = tmp_path / "v2.json"
    write_snapshot(baseline, base_path)
    write_snapshot(candidate, cand_path)
    out = tmp_path / "adapter.json"
    result = CliRunner().invoke(
        app,
        ["suggest-adapter", str(base_path), str(cand_path), "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["auto_apply"] is False
    assert "adapter" in payload
    assert "notes" in payload
