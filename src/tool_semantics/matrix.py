"""Multi-model matrix, temperature sweeps, and reproducibility metadata (#94).

Config-driven evaluation of the same probes across models and temperatures.
Unit tests use FakeModelRunner only; live runners are opt-in.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from tool_semantics import __version__ as TOOL_SEMANTICS_VERSION
from tool_semantics.models import InterfaceSnapshot
from tool_semantics.probes import (
    ModelProbeReport,
    Probe,
    ProbeMetrics,
    compute_probe_metrics,
    evaluate_probes_with_model,
    run_probe_trials,
)
from tool_semantics.runner import ModelRunner, RunnerConfig, RunnerMetadata

DEFAULT_TEMPERATURES: tuple[float, ...] = (0.0, 0.2, 0.5)


class ReproRunConfig(BaseModel):
    """Reproducibility metadata recorded for every model-backed matrix cell."""

    provider: str
    model: str
    model_version: str | None = None
    temperature: float = 0.0
    seed: int | None = None
    trial_count: int = 1
    snapshot_hash: str = ""
    probe_hash: str = ""
    tool_semantics_version: str = TOOL_SEMANTICS_VERSION
    # Optional cost / token fields when the provider returns them.
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost: float | None = None
    currency: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class MatrixCellResult(BaseModel):
    label: str
    repro: ReproRunConfig
    metrics: ProbeMetrics = Field(default_factory=ProbeMetrics)
    passed: bool = False
    stability_score_mean: float | None = None


class MatrixReport(BaseModel):
    cells: list[MatrixCellResult] = Field(default_factory=list)
    temperatures: list[float] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(cell.passed for cell in self.cells)


RunnerFactory = Callable[[str, float, int | None], ModelRunner]


def hash_snapshot(snapshot: InterfaceSnapshot) -> str:
    payload = snapshot.model_dump(mode="json")
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def hash_probes(probes: Sequence[Probe]) -> str:
    payload = [probe.model_dump(mode="json") for probe in probes]
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def build_repro_config(
    runner: ModelRunner,
    *,
    temperature: float,
    seed: int | None,
    trial_count: int,
    snapshot: InterfaceSnapshot,
    probes: Sequence[Probe],
    cost: float | None = None,
    currency: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> ReproRunConfig:
    meta: RunnerMetadata = runner.metadata
    return ReproRunConfig(
        provider=meta.provider,
        model=meta.model,
        model_version=meta.model_version,
        temperature=temperature,
        seed=seed,
        trial_count=trial_count,
        snapshot_hash=hash_snapshot(snapshot),
        probe_hash=hash_probes(probes),
        cost=cost,
        currency=currency,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        extra=dict(meta.run_config or {}),
    )


def _run_cell(
    snapshot: InterfaceSnapshot,
    probes: list[Probe],
    runner: ModelRunner,
    *,
    temperature: float,
    seed: int | None,
    trial_count: int,
    require_approval: bool,
    label: str,
) -> MatrixCellResult:
    cfg = RunnerConfig(temperature=temperature, seed=seed)
    stability_mean: float | None = None
    if trial_count > 1:
        stability = run_probe_trials(
            snapshot,
            probes,
            runner,
            trial_count=trial_count,
            config=cfg,
            require_approval=require_approval,
            seed=seed,
        )
        metrics = stability.metrics
        passed = all(item.aggregate_passed for item in stability.summaries)
        if stability.summaries:
            stability_mean = round(
                sum(item.stability_score for item in stability.summaries)
                / len(stability.summaries),
                4,
            )
    else:
        report: ModelProbeReport = evaluate_probes_with_model(
            snapshot,
            probes,
            runner,
            config=cfg,
            require_approval=require_approval,
        )
        metrics = compute_probe_metrics(report.results)
        passed = report.passed

    repro = build_repro_config(
        runner,
        temperature=temperature,
        seed=seed,
        trial_count=trial_count,
        snapshot=snapshot,
        probes=probes,
    )
    return MatrixCellResult(
        label=label,
        repro=repro,
        metrics=metrics,
        passed=passed,
        stability_score_mean=stability_mean,
    )


def run_model_matrix(
    snapshot: InterfaceSnapshot,
    probes: list[Probe],
    *,
    models: Sequence[str],
    runner_factory: RunnerFactory,
    temperatures: Sequence[float] = DEFAULT_TEMPERATURES,
    seed: int | None = 0,
    trial_count: int = 1,
    require_approval: bool = True,
) -> MatrixReport:
    """Execute the same probes across models × temperatures (config-driven)."""
    cells: list[MatrixCellResult] = []
    for model in models:
        for temperature in temperatures:
            runner = runner_factory(model, float(temperature), seed)
            label = f"{model}@t={temperature}"
            cells.append(
                _run_cell(
                    snapshot,
                    probes,
                    runner,
                    temperature=float(temperature),
                    seed=seed,
                    trial_count=trial_count,
                    require_approval=require_approval,
                    label=label,
                )
            )
    return MatrixReport(
        cells=cells,
        temperatures=[float(value) for value in temperatures],
        models=list(models),
    )


def run_temperature_sweep(
    snapshot: InterfaceSnapshot,
    probes: list[Probe],
    runner_factory: RunnerFactory,
    *,
    model: str = "fake-model",
    temperatures: Sequence[float] = DEFAULT_TEMPERATURES,
    seed: int | None = 0,
    trial_count: int = 1,
    require_approval: bool = True,
) -> MatrixReport:
    """Temperature sweep helper (default 0 / 0.2 / 0.5) with stability comparison."""
    return run_model_matrix(
        snapshot,
        probes,
        models=[model],
        runner_factory=runner_factory,
        temperatures=temperatures,
        seed=seed,
        trial_count=trial_count,
        require_approval=require_approval,
    )


def export_matrix_dataset(report: MatrixReport, path: Path) -> None:
    """Write a machine-readable research dataset (JSON)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )


def render_matrix_markdown(report: MatrixReport) -> str:
    lines = [
        "## Multi-model matrix",
        "",
        f"Models: {', '.join(f'`{m}`' for m in report.models) or '—'}",
        f"Temperatures: {', '.join(str(t) for t in report.temperatures) or '—'}",
        "",
        "| Cell | Provider | Model | Temp | Seed | Trials | "
        "Selection acc | Passed | Snapshot | Probes | TS ver |",
        "| --- | --- | --- | ---: | --- | ---: | ---: | --- | --- | --- | --- |",
    ]
    for cell in report.cells:
        repro = cell.repro
        acc = cell.metrics.tool_selection_accuracy
        acc_s = "n/a" if acc is None else f"{acc:.0%}"
        seed_s = "n/a" if repro.seed is None else str(repro.seed)
        lines.append(
            f"| `{cell.label}` | `{repro.provider}` | `{repro.model}` | "
            f"{repro.temperature:g} | {seed_s} | {repro.trial_count} | {acc_s} | "
            f"{'yes' if cell.passed else 'no'} | `{repro.snapshot_hash}` | "
            f"`{repro.probe_hash}` | `{repro.tool_semantics_version}` |"
        )
    lines.append("")
    lines.append(
        "_Every cell records provider/model/version/temperature/seed/trials/"
        "snapshot hash/probe hash/tool-semantics version. Cost/tokens optional._"
    )
    lines.append("")
    return "\n".join(lines)
