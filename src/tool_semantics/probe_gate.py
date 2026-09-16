"""Probe gating for compare / CI — thresholds over offline, model, and stability runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from tool_semantics.models import InterfaceSnapshot
from tool_semantics.probes import (
    ModelProbeReport,
    Probe,
    ProbeMetrics,
    ProbeReport,
    StabilityReport,
    compute_probe_metrics,
    evaluate_probes,
    evaluate_probes_with_model,
    run_probe_trials,
)
from tool_semantics.runner import ModelRunner, RunnerConfig

ProbeTarget = Literal["baseline", "candidate", "both"]
ProbeMode = Literal["offline", "model"]


@dataclass(frozen=True)
class ProbeThresholds:
    """Minimum rates / scores required for a probe gate to pass."""

    min_pass_rate: float = 1.0
    min_tool_selection_accuracy: float | None = None
    min_argument_validity_rate: float | None = None
    min_stability_score: float | None = None
    fail_on_unstable: bool = True
    fail_on_deterministic_failure: bool = True


@dataclass(frozen=True)
class ProbeGateSettings:
    """How compare should run and gate on probes when enabled."""

    file: Path | None = None
    target: ProbeTarget = "candidate"
    mode: ProbeMode = "offline"
    trials: int = 1
    seed: int | None = None
    allow_unapproved: bool = False
    thresholds: ProbeThresholds = field(default_factory=ProbeThresholds)


@dataclass
class TargetProbeOutcome:
    """Result of running probes against one snapshot (baseline or candidate)."""

    target: str
    mode: str
    passed: bool
    breaches: list[str] = field(default_factory=list)
    offline: ProbeReport | None = None
    model: ModelProbeReport | None = None
    stability: StabilityReport | None = None
    metrics: ProbeMetrics | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "target": self.target,
            "mode": self.mode,
            "passed": self.passed,
            "breaches": list(self.breaches),
        }
        if self.offline is not None:
            payload["offline"] = {
                "passed": self.offline.passed,
                "results": [item.model_dump(mode="json") for item in self.offline.results],
                "failure_count": len(self.offline.failures),
                "pass_rate": _pass_rate_offline(self.offline),
            }
        if self.model is not None:
            payload["model"] = {
                "passed": self.model.passed,
                "opt_in": self.model.opt_in,
                "results": [item.model_dump(mode="json") for item in self.model.results],
            }
        if self.stability is not None:
            payload["stability"] = self.stability.model_dump(mode="json")
        if self.metrics is not None:
            payload["metrics"] = self.metrics.model_dump(mode="json")
        return payload


@dataclass
class ProbeGateReport:
    """Aggregate probe-gate outcome for a compare run."""

    enabled: bool
    settings: dict[str, Any] = field(default_factory=dict)
    targets: list[TargetProbeOutcome] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return self.enabled and any(not item.passed for item in self.targets)

    @property
    def breaches(self) -> list[str]:
        out: list[str] = []
        for item in self.targets:
            out.extend(f"{item.target}: {msg}" for msg in item.breaches)
        return out

    def to_json(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "settings": self.settings,
            "failed": self.failed,
            "breaches": self.breaches,
            "targets": [item.to_json() for item in self.targets],
        }


def _pass_rate_offline(report: ProbeReport) -> float | None:
    if not report.results:
        return None
    return sum(1 for item in report.results if item.passed) / len(report.results)


def _pass_rate_model(report: ModelProbeReport) -> float | None:
    evaluated = [item for item in report.results if item.outcome.value != "skipped"]
    if not evaluated:
        return None
    return sum(1 for item in evaluated if item.passed) / len(evaluated)


def _check_rate(
    name: str,
    actual: float | None,
    minimum: float | None,
    breaches: list[str],
) -> None:
    if minimum is None:
        return
    if actual is None:
        breaches.append(f"{name}: no measurable rate (missing data); required >= {minimum:.2f}")
        return
    if actual + 1e-12 < minimum:
        breaches.append(f"{name}: {actual:.2f} < required {minimum:.2f}")


def evaluate_offline_thresholds(report: ProbeReport, thresholds: ProbeThresholds) -> list[str]:
    breaches: list[str] = []
    _check_rate("pass_rate", _pass_rate_offline(report), thresholds.min_pass_rate, breaches)
    return breaches


def evaluate_model_thresholds(
    report: ModelProbeReport,
    metrics: ProbeMetrics,
    thresholds: ProbeThresholds,
) -> list[str]:
    breaches: list[str] = []
    _check_rate("pass_rate", _pass_rate_model(report), thresholds.min_pass_rate, breaches)
    _check_rate(
        "tool_selection_accuracy",
        metrics.tool_selection_accuracy,
        thresholds.min_tool_selection_accuracy,
        breaches,
    )
    _check_rate(
        "argument_validity_rate",
        metrics.argument_validity_rate,
        thresholds.min_argument_validity_rate,
        breaches,
    )
    return breaches


def evaluate_stability_thresholds(
    report: StabilityReport, thresholds: ProbeThresholds
) -> list[str]:
    breaches: list[str] = []
    if report.summaries:
        pass_rate = sum(1 for item in report.summaries if item.aggregate_passed) / len(
            report.summaries
        )
        _check_rate("pass_rate", pass_rate, thresholds.min_pass_rate, breaches)
    elif thresholds.min_pass_rate is not None and thresholds.min_pass_rate > 0:
        breaches.append(
            f"pass_rate: no probes evaluated; required >= {thresholds.min_pass_rate:.2f}"
        )

    _check_rate(
        "tool_selection_accuracy",
        report.metrics.tool_selection_accuracy,
        thresholds.min_tool_selection_accuracy,
        breaches,
    )
    _check_rate(
        "argument_validity_rate",
        report.metrics.argument_validity_rate,
        thresholds.min_argument_validity_rate,
        breaches,
    )

    if thresholds.min_stability_score is not None:
        for summary in report.summaries:
            if summary.stability_score + 1e-12 < thresholds.min_stability_score:
                breaches.append(
                    f"stability_score[{summary.probe_id}]: "
                    f"{summary.stability_score:.2f} < required "
                    f"{thresholds.min_stability_score:.2f}"
                )

    if thresholds.fail_on_unstable:
        for summary in report.summaries:
            if summary.unstable:
                breaches.append(f"unstable[{summary.probe_id}]: {summary.message}")

    if thresholds.fail_on_deterministic_failure:
        for summary in report.summaries:
            if summary.deterministic_failure:
                breaches.append(f"deterministic_failure[{summary.probe_id}]: {summary.message}")

    return breaches


def run_probe_gate_for_snapshot(
    snapshot: InterfaceSnapshot,
    probes: list[Probe],
    settings: ProbeGateSettings,
    *,
    target_label: str,
    runner: ModelRunner | None = None,
) -> TargetProbeOutcome:
    """Execute probes for one snapshot and apply configured thresholds."""
    thresholds = settings.thresholds
    if settings.mode == "offline":
        report = evaluate_probes(snapshot, probes)
        breaches = evaluate_offline_thresholds(report, thresholds)
        return TargetProbeOutcome(
            target=target_label,
            mode="offline",
            passed=not breaches,
            breaches=breaches,
            offline=report,
        )

    if runner is None:
        raise ValueError("Model-backed probe gate requires a ModelRunner")

    require_approval = not settings.allow_unapproved
    cfg = RunnerConfig(seed=settings.seed)
    if settings.trials > 1:
        stability = run_probe_trials(
            snapshot,
            probes,
            runner,
            trial_count=settings.trials,
            config=cfg,
            require_approval=require_approval,
            seed=settings.seed,
        )
        breaches = evaluate_stability_thresholds(stability, thresholds)
        return TargetProbeOutcome(
            target=target_label,
            mode="stability",
            passed=not breaches,
            breaches=breaches,
            stability=stability,
            metrics=stability.metrics,
        )

    model_report = evaluate_probes_with_model(
        snapshot,
        probes,
        runner,
        config=cfg,
        require_approval=require_approval,
    )
    metrics = compute_probe_metrics(model_report.results)
    breaches = evaluate_model_thresholds(model_report, metrics, thresholds)
    return TargetProbeOutcome(
        target=target_label,
        mode="model",
        passed=not breaches,
        breaches=breaches,
        model=model_report,
        metrics=metrics,
    )


def resolve_probe_targets(target: ProbeTarget) -> tuple[str, ...]:
    if target == "both":
        return ("baseline", "candidate")
    if target in {"baseline", "candidate"}:
        return (target,)
    raise ValueError(f"Unknown probe target {target!r}; expected baseline|candidate|both")
