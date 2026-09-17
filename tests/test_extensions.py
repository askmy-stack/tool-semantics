"""Tests for MCP extension capture and diffs (#91)."""

from __future__ import annotations

from tool_semantics.diff import Severity, compare_snapshots
from tool_semantics.extensions import (
    extensions_metadata,
    extract_extensions_from_initialize,
)
from tool_semantics.mcp_capture import _server_extensions_metadata
from tool_semantics.models import InterfaceSnapshot


def test_extract_extensions_from_fake_initialize_payloads() -> None:
    init = {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {},
            "experimental": {"com.example/debug": True},
            "extensions": {
                "io.modelcontextprotocol/sampling": {"version": "1.0.0"},
            },
        },
        "extensions": {
            "com.acme/tasks": {"version": "0.2.0", "methods": ["tasks/list"]},
        },
    }
    found = extract_extensions_from_initialize(init)
    assert "com.example/debug" in found
    assert found["com.example/debug"].source == "capabilities.experimental"
    assert found["io.modelcontextprotocol/sampling"].version == "1.0.0"
    # Top-level extensions win / coexist
    assert found["com.acme/tasks"].version == "0.2.0"
    assert found["com.acme/tasks"].details.get("methods") == ["tasks/list"]
    meta = extensions_metadata(init)
    assert meta["io.modelcontextprotocol/sampling"]["version"] == "1.0.0"
    assert _server_extensions_metadata(init) == meta


def test_extension_diff_added_removed_version_changed() -> None:
    baseline = InterfaceSnapshot(
        server_name="demo",
        metadata={
            "extensions": {
                "ext.a": {"name": "ext.a", "version": "1.0.0", "source": "initialize.extensions"},
                "ext.b": {"name": "ext.b", "version": "2.0.0", "source": "initialize.extensions"},
            }
        },
    )
    candidate = InterfaceSnapshot(
        server_name="demo",
        metadata={
            "extensions": {
                "ext.b": {"name": "ext.b", "version": "3.0.0", "source": "initialize.extensions"},
                "ext.c": {"name": "ext.c", "version": None, "source": "capabilities.experimental"},
            }
        },
    )
    report = compare_snapshots(baseline, candidate)
    codes = {
        change.code: change for change in report.changes if change.code.startswith("extension.")
    }
    assert codes["extension.removed"].subject == "ext.a"
    assert codes["extension.removed"].severity == Severity.BREAKING
    assert codes["extension.added"].subject == "ext.c"
    assert codes["extension.added"].severity == Severity.INFO
    assert codes["extension.version_changed"].subject == "ext.b"
    assert codes["extension.version_changed"].severity == Severity.BREAKING
    assert not report.is_compatible


def test_manifests_without_extensions_skip_diff_noise() -> None:
    left = InterfaceSnapshot(server_name="a", tools=[])
    right = InterfaceSnapshot(server_name="b", tools=[])
    report = compare_snapshots(left, right)
    assert not any(change.code.startswith("extension.") for change in report.changes)
