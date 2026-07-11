from pathlib import Path

import pytest

from tool_semantics.scanner import ManifestError, capture_manifest


def test_capture_manifest() -> None:
    snapshot = capture_manifest(Path("examples/github_server_v1.json"))
    assert snapshot.server_name == "github-demo"
    assert snapshot.server_version == "1.0.0"
    assert [tool.name for tool in snapshot.tools] == ["create_issue", "search_issues"]
    assert snapshot.tool_semantics_version == "0.1"


def test_capture_rejects_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ManifestError, match="Unable to read manifest"):
        capture_manifest(bad)


def test_capture_rejects_non_object_root(tmp_path: Path) -> None:
    bad = tmp_path / "list.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(ManifestError, match="Manifest root must be an object"):
        capture_manifest(bad)


def test_capture_rejects_tools_not_array(tmp_path: Path) -> None:
    bad = tmp_path / "tools_not_array.json"
    bad.write_text('{"tools": {"name": "broken"}}', encoding="utf-8")
    with pytest.raises(ManifestError, match="'tools' must be an array"):
        capture_manifest(bad)


def test_capture_rejects_tool_missing_name(tmp_path: Path) -> None:
    bad = tmp_path / "missing_name.json"
    bad.write_text(
        '{"tools": [{"description": "no name field"}]}',
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="Each tool must contain a string 'name'"):
        capture_manifest(bad)


def test_capture_rejects_non_object_input_schema(tmp_path: Path) -> None:
    bad = tmp_path / "bad_input_schema.json"
    bad.write_text(
        '{"tools": [{"name": "demo", "inputSchema": ["not", "an", "object"]}]}',
        encoding="utf-8",
    )
    with pytest.raises(
        ManifestError,
        match="Tool 'demo' inputSchema must be an object",
    ):
        capture_manifest(bad)


def test_capture_rejects_non_object_parameter_schema(tmp_path: Path) -> None:
    bad = tmp_path / "bad_param_schema.json"
    bad.write_text(
        (
            '{"tools": [{"name": "demo", "inputSchema": '
            '{"type": "object", "properties": {"query": "not-an-object"}}}]}'
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        ManifestError,
        match="Schema for parameter 'query' must be an object",
    ):
        capture_manifest(bad)
