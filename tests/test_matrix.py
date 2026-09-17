"""Tests for multi-model matrix / temperature sweeps (#94)."""

from __future__ import annotations

from pathlib import Path

from tool_semantics.matrix import (
    DEFAULT_TEMPERATURES,
    export_matrix_dataset,
    hash_probes,
    hash_snapshot,
    render_matrix_markdown,
    run_model_matrix,
    run_temperature_sweep,
)
from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract, ToolParameter
from tool_semantics.probes import Probe, ProbeKind
from tool_semantics.runner import FakeModelRunner, ModelCompletion, RunnerMetadata, ToolCallRequest


def _snapshot() -> InterfaceSnapshot:
    return InterfaceSnapshot(
        server_name="demo",
        tools=[
            ToolContract(
                name="search_issues",
                description="Search issues",
                parameters=[ToolParameter(name="query", schema={"type": "string"}, required=True)],
                risk=RiskLevel.READ_ONLY,
            )
        ],
    )


def _probe() -> Probe:
    return Probe(
        id="search",
        intent="find bugs",
        kind=ProbeKind.POSITIVE,
        expected_tool="search_issues",
        required_params=["query"],
        approved=True,
        approved_by="ci",
    )


def _factory(model: str, temperature: float, seed: int | None) -> FakeModelRunner:
    del temperature, seed
    return FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "bugs"})],
                metadata=RunnerMetadata(provider="fake", model=model, model_version="test"),
            )
        ],
        model=model,
        model_version="test",
    )


def test_matrix_records_repro_metadata(tmp_path: Path) -> None:
    snap = _snapshot()
    probes = [_probe()]
    report = run_model_matrix(
        snap,
        probes,
        models=["fake-a", "fake-b"],
        runner_factory=_factory,
        temperatures=(0.0, 0.2),
        seed=7,
        trial_count=1,
    )
    assert len(report.cells) == 4
    cell = report.cells[0]
    assert cell.repro.provider == "fake"
    assert cell.repro.model in {"fake-a", "fake-b"}
    assert cell.repro.temperature in {0.0, 0.2}
    assert cell.repro.seed == 7
    assert cell.repro.trial_count == 1
    assert cell.repro.snapshot_hash == hash_snapshot(snap)
    assert cell.repro.probe_hash == hash_probes(probes)
    assert cell.repro.tool_semantics_version
    assert cell.passed
    md = render_matrix_markdown(report)
    assert "Multi-model matrix" in md
    assert "Snapshot" in md
    out = tmp_path / "matrix.json"
    export_matrix_dataset(report, out)
    assert out.is_file()
    assert "snapshot_hash" in out.read_text(encoding="utf-8")


def test_temperature_sweep_defaults() -> None:
    report = run_temperature_sweep(
        _snapshot(),
        [_probe()],
        _factory,
        model="fake-model",
        seed=0,
    )
    assert report.temperatures == list(DEFAULT_TEMPERATURES)
    assert len(report.cells) == 3
    assert all(cell.passed for cell in report.cells)
