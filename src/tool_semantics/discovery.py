"""Progressive tool-catalog discovery regression harness (#86).

Evaluate the same probes against growing catalog sizes and compare
baseline vs candidate discovery curves.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from tool_semantics.benchmarks import snapshot_from_manifest, synthesize_manifest
from tool_semantics.diff import Change, Severity
from tool_semantics.models import InterfaceSnapshot, ToolContract
from tool_semantics.probes import (
    Probe,
    ProbeMetrics,
    compute_probe_metrics,
    evaluate_probes_with_model,
)
from tool_semantics.runner import ModelRunner, RunnerConfig

DEFAULT_CATALOG_SIZES: tuple[int, ...] = (10, 25, 50, 100, 250, 500)
CI_CATALOG_SIZES: tuple[int, ...] = (10, 25, 50)


class DiscoveryPoint(BaseModel):
    catalog_size: int
    tool_selection_accuracy: float | None = None
    argument_validity_rate: float | None = None
    risk_compliance_rate: float | None = None
    evaluated_count: int = 0
    elapsed_seconds: float = 0.0
    # Optional cost signals when the runner exposes them via completion metadata.
    latency_ms: float | None = None
    token_estimate: int | None = None


class DiscoveryCurve(BaseModel):
    label: str
    points: list[DiscoveryPoint] = Field(default_factory=list)

    def accuracy_at(self, size: int) -> float | None:
        for point in self.points:
            if point.catalog_size == size:
                return point.tool_selection_accuracy
        return None


class DiscoveryRegression(BaseModel):
    catalog_size: int
    baseline_accuracy: float
    candidate_accuracy: float
    accuracy_drop: float
    baseline_tool_count: int
    candidate_tool_count: int
    message: str


class DiscoveryReport(BaseModel):
    sizes: list[int] = Field(default_factory=list)
    baseline: DiscoveryCurve | None = None
    candidate: DiscoveryCurve | None = None
    regressions: list[DiscoveryRegression] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def has_regression(self) -> bool:
        return bool(self.regressions)


def pad_catalog(
    core: InterfaceSnapshot,
    target_size: int,
    *,
    noise_prefix: str = "noise",
) -> InterfaceSnapshot:
    """Return a snapshot with ``core`` tools plus synthetic fillers to reach ``target_size``.

    Core tools are always retained (never dropped). If ``target_size`` is smaller
    than ``len(core.tools)``, returns the core snapshot unchanged.
    """
    core_tools = list(core.tools)
    if target_size <= len(core_tools):
        return InterfaceSnapshot(
            protocol=core.protocol,
            server_name=core.server_name,
            server_version=core.server_version,
            tools=sorted(core_tools, key=lambda tool: tool.name),
            prompts=list(core.prompts),
            resources=list(core.resources),
            metadata=dict(core.metadata),
        )
    filler_count = target_size - len(core_tools)
    filler = snapshot_from_manifest(synthesize_manifest(filler_count, prefix=noise_prefix)).tools
    # Avoid name collisions with core tools.
    core_names = {tool.name for tool in core_tools}
    safe_filler: list[ToolContract] = []
    for tool in filler:
        name = tool.name
        if name in core_names:
            name = f"{noise_prefix}_x_{tool.name}"
            tool = tool.model_copy(update={"name": name})
        safe_filler.append(tool)
        core_names.add(tool.name)
    merged = core_tools + safe_filler
    return InterfaceSnapshot(
        protocol=core.protocol,
        server_name=core.server_name,
        server_version=core.server_version,
        tools=sorted(merged, key=lambda tool: tool.name),
        metadata={**core.metadata, "discovery_catalog_size": target_size},
    )


def _metrics_to_point(
    metrics: ProbeMetrics,
    *,
    catalog_size: int,
    elapsed_seconds: float,
) -> DiscoveryPoint:
    return DiscoveryPoint(
        catalog_size=catalog_size,
        tool_selection_accuracy=metrics.tool_selection_accuracy,
        argument_validity_rate=metrics.argument_validity_rate,
        risk_compliance_rate=metrics.risk_compliance_rate,
        evaluated_count=metrics.evaluated_count,
        elapsed_seconds=elapsed_seconds,
    )


def run_discovery_curve(
    snapshot: InterfaceSnapshot,
    probes: list[Probe],
    runner: ModelRunner,
    *,
    sizes: tuple[int, ...] | list[int] = CI_CATALOG_SIZES,
    label: str = "curve",
    config: RunnerConfig | None = None,
    require_approval: bool = False,
    noise_prefix: str = "noise",
) -> DiscoveryCurve:
    """Evaluate probes at each catalog size (progressive discovery)."""
    points: list[DiscoveryPoint] = []
    for size in sizes:
        catalog = pad_catalog(snapshot, int(size), noise_prefix=noise_prefix)
        started = time.perf_counter()
        report = evaluate_probes_with_model(
            catalog,
            probes,
            runner,
            config=config,
            require_approval=require_approval,
        )
        elapsed = time.perf_counter() - started
        metrics = compute_probe_metrics(report.results)
        points.append(
            _metrics_to_point(metrics, catalog_size=len(catalog.tools), elapsed_seconds=elapsed)
        )
    return DiscoveryCurve(label=label, points=points)


def compare_discovery_curves(
    baseline: DiscoveryCurve,
    candidate: DiscoveryCurve,
    *,
    baseline_tool_count: int,
    candidate_tool_count: int,
    accuracy_drop_threshold: float = 0.10,
    require_tool_growth: bool = True,
) -> DiscoveryReport:
    """Flag discovery regressions when accuracy drops as the catalog grows.

    A regression is recorded when, at a shared catalog size, candidate
    selection accuracy falls more than ``accuracy_drop_threshold`` below the
    baseline curve **and** (optionally) the candidate snapshot has more tools.
    """
    if accuracy_drop_threshold < 0.0 or accuracy_drop_threshold > 1.0:
        raise ValueError("accuracy_drop_threshold must be in [0, 1]")

    sizes = sorted(
        {point.catalog_size for point in baseline.points}
        & {point.catalog_size for point in candidate.points}
    )
    report = DiscoveryReport(
        sizes=sizes,
        baseline=baseline,
        candidate=candidate,
    )
    if require_tool_growth and candidate_tool_count <= baseline_tool_count:
        report.warnings.append(
            "Candidate tool count did not increase; discovery-regression gate skipped."
        )
        return report

    for size in sizes:
        base_acc = baseline.accuracy_at(size)
        cand_acc = candidate.accuracy_at(size)
        if base_acc is None or cand_acc is None:
            continue
        drop = base_acc - cand_acc
        if drop > accuracy_drop_threshold:
            message = (
                f"DISCOVERY REGRESSION at catalog_size={size}: "
                f"accuracy {base_acc:.2f} → {cand_acc:.2f} "
                f"(drop={drop:.2f} > threshold={accuracy_drop_threshold:.2f}) "
                f"while tools {baseline_tool_count} → {candidate_tool_count}."
            )
            report.regressions.append(
                DiscoveryRegression(
                    catalog_size=size,
                    baseline_accuracy=base_acc,
                    candidate_accuracy=cand_acc,
                    accuracy_drop=round(drop, 4),
                    baseline_tool_count=baseline_tool_count,
                    candidate_tool_count=candidate_tool_count,
                    message=message,
                )
            )
            report.warnings.append(message)
    return report


def discovery_regression_changes(report: DiscoveryReport) -> list[Change]:
    """Convert discovery regressions into warning ``Change`` rows for reports."""
    changes: list[Change] = []
    for item in report.regressions:
        changes.append(
            Change(
                severity=Severity.WARNING,
                code="discovery.accuracy_regression",
                subject=f"catalog@{item.catalog_size}",
                message=item.message,
            )
        )
    return changes


@dataclass
class SizeAwareFakeRunner:
    """Deterministic runner for CI: correct below ``fail_above``, wrong at/above.

    Used to simulate selection degradation as catalogs grow without a live model.
    """

    expected_tool: str
    fail_above: int
    provider: str = "size-aware-fake"
    model: str = "size-aware"
    call_count: int = 0
    _metadata: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        from tool_semantics.runner import RunnerMetadata

        self._metadata = RunnerMetadata(
            provider=self.provider,
            model=self.model,
            model_version="test",
            run_config={"fail_above": self.fail_above},
        )

    @property
    def metadata(self) -> Any:
        return self._metadata

    def complete(
        self,
        *,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
        config: RunnerConfig | None = None,
    ) -> Any:
        from tool_semantics.runner import ModelCompletion, ToolCallRequest

        del system, user, config
        self.call_count += 1
        catalog_size = len(tools)
        if catalog_size >= self.fail_above:
            # Pick a different tool if available to simulate collision under load.
            names = [
                item.get("function", {}).get("name") for item in tools if isinstance(item, dict)
            ]
            wrong = next((name for name in names if name and name != self.expected_tool), None)
            selected = wrong or self.expected_tool
        else:
            selected = self.expected_tool
        return ModelCompletion(
            tool_calls=[ToolCallRequest(name=selected, arguments={"query": "x"})],
            metadata=self.metadata,
        )
