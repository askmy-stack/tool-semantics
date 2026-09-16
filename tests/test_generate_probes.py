"""Tests for deterministic probe draft generation (#98)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.generate_probes import generate_probe_drafts, write_probe_drafts
from tool_semantics.probes import ProbeKind, load_probes
from tool_semantics.scanner import capture_manifest, write_snapshot


def test_generate_probe_drafts_deterministic_kinds() -> None:
    snapshot = capture_manifest(Path("examples/github_server_v1.json"))
    first = generate_probe_drafts(snapshot)
    second = generate_probe_drafts(snapshot)
    assert [probe.model_dump() for probe in first] == [probe.model_dump() for probe in second]
    assert all(not probe.approved for probe in first)
    kinds = {probe.kind for probe in first}
    assert ProbeKind.POSITIVE in kinds
    assert ProbeKind.NEGATIVE in kinds
    positives = [probe for probe in first if probe.kind == ProbeKind.POSITIVE]
    assert {probe.expected_tool for probe in positives} == {tool.name for tool in snapshot.tools}


def test_generate_probes_cli_yaml(tmp_path: Path) -> None:
    snapshot = capture_manifest(Path("examples/github_server_v1.json"))
    snap_path = tmp_path / "snap.json"
    write_snapshot(snapshot, snap_path)
    out = tmp_path / "drafts.yaml"
    result = CliRunner().invoke(app, ["generate-probes", str(snap_path), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.is_file()
    probes = load_probes(out)
    assert probes
    assert all(not probe.approved for probe in probes)
    write_probe_drafts(probes, tmp_path / "drafts.json")
    assert (tmp_path / "drafts.json").is_file()
