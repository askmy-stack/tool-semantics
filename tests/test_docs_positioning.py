"""Smoke tests for docs positioning (#101)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docs_index_and_beginner_pages_exist() -> None:
    for relative in (
        "docs/index.md",
        "docs/simple-explanation.md",
        "docs/concepts.md",
    ):
        path = ROOT / relative
        assert path.is_file(), relative
        text = path.read_text(encoding="utf-8")
        assert len(text) > 100


def test_readme_positions_capture_evaluate_and_schema_valid() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Schema-valid ≠ agent-safe" in readme or "schema-valid ≠ agent-safe" in readme.lower()
    assert "DETECT" in readme and "TEST" in readme and "PROTECT" in readme
    assert "capture → evaluate" in readme.lower() or "capture → evaluate" in readme
    assert "docs/simple-explanation.md" in readme
    assert "docs/index.md" in readme


def test_claude_and_plan_point_at_milestone7_docs() -> None:
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    plan = (ROOT / "docs/PLAN.md").read_text(encoding="utf-8")
    assert "docs/PLAN.md" in claude
    assert "AGENT_EXECUTION.md" in claude
    assert "simple-explanation.md" in plan
    assert "capture → compare" in plan or "capture → compare + probe" in plan
