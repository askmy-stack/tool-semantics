"""Tests for field-level output-schema diffs (#89)."""

from __future__ import annotations

from tool_semantics.diff import Severity, compare_snapshots
from tool_semantics.models import InterfaceSnapshot, ToolContract
from tool_semantics.output_schema import (
    detect_field_renames,
    field_name_similarity,
    validate_output_payload,
)


def _snap(name: str, schema: dict[str, object] | None) -> InterfaceSnapshot:
    return InterfaceSnapshot(
        server_name="demo",
        tools=[ToolContract(name=name, description="t", output_schema=schema)],
    )


def test_field_removed_and_added() -> None:
    old = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "name": {"type": "string"},
        },
    }
    new = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "email": {"type": "string"},
        },
    }
    # Force no rename: name vs email should not match threshold strongly enough alone
    # when types match but names differ a lot — email vs name similarity is low.
    report = compare_snapshots(_snap("t", old), _snap("t", new))
    codes = [change.code for change in report.changes]
    assert "tool.output_schema_changed" in codes
    assert "output.field_removed" in codes
    assert "output.field_added" in codes
    removed = next(change for change in report.changes if change.code == "output.field_removed")
    assert "name" in removed.subject
    assert "downstream" in removed.message.lower() or "agents" in removed.message.lower()


def test_user_id_to_id_and_name_to_display_name_renames() -> None:
    old = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "name": {"type": "string"},
        },
    }
    new = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "display_name": {"type": "string"},
        },
    }
    assert field_name_similarity("user_id", "id") >= 0.4
    assert field_name_similarity("name", "display_name") >= 0.4
    renames = detect_field_renames(old["properties"], new["properties"], threshold=0.55)
    rename_pairs = {(item.old_name, item.new_name) for item in renames}
    assert ("user_id", "id") in rename_pairs or ("name", "display_name") in rename_pairs

    report = compare_snapshots(_snap("profile", old), _snap("profile", new))
    assert any(change.code == "output.field_renamed" for change in report.changes)
    renamed = [change for change in report.changes if change.code == "output.field_renamed"]
    assert all(change.severity is Severity.WARNING for change in renamed)
    assert any("confidence=" in change.message for change in renamed)


def test_field_type_changed() -> None:
    old = {"type": "object", "properties": {"count": {"type": "integer"}}}
    new = {"type": "object", "properties": {"count": {"type": "string"}}}
    report = compare_snapshots(_snap("t", old), _snap("t", new))
    assert any(change.code == "output.field_type_changed" for change in report.changes)


def test_validate_output_payload_hook() -> None:
    schema = {
        "type": "object",
        "required": ["id"],
        "properties": {
            "id": {"type": "string"},
            "count": {"type": "integer"},
        },
    }
    assert validate_output_payload({"id": "a", "count": 1}, schema) == []
    errors = validate_output_payload({"count": "x"}, schema)
    assert any("Missing required" in item for item in errors)
    assert any("expected integer" in item for item in errors)
