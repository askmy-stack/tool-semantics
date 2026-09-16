"""Binomial confidence intervals for behavioral metrics (#115).

Opt-in research quality helpers. Prevents treating tiny score differences as
regressions when intervals overlap or trial counts are too small.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from tool_semantics.probes import (
    ModelProbeOutcome,
    ModelProbeResult,
    ProbeMetrics,
    StabilityReport,
)

# Common normal critical values (two-sided).
_Z_SCORES: dict[float, float] = {
    0.80: 1.2815515655446004,
    0.90: 1.6448536269514722,
    0.95: 1.959963984540054,
    0.99: 2.5758293035489004,
}

DEFAULT_CONFIDENCE = 0.95
DEFAULT_MIN_N = 10

OVERLAP_WARNING = (
    "Overlapping confidence intervals (or insufficient n) — do not call this a "
    "regression. Small point-estimate gaps are not meaningful without uncertainty."
)


class ConfidenceInterval(BaseModel):
    """Wilson score interval for a binomial proportion."""

    estimate: float
    low: float
    high: float
    successes: int
    n: int
    confidence: float = DEFAULT_CONFIDENCE
    method: str = "wilson"
    sufficient_n: bool = False
    half_width: float = 0.0

    def format_pm(self, *, digits: int = 0) -> str:
        """Display like ``89% ± 3%`` (uses half-width; Wilson is slightly asymmetric)."""
        pct = 100.0 * self.estimate
        pm = 100.0 * self.half_width
        return f"{pct:.{digits}f}% ± {pm:.{digits}f}%"

    def format_bracket(self, *, digits: int = 1) -> str:
        return (
            f"{100.0 * self.estimate:.{digits}f}% "
            f"[{100.0 * self.low:.{digits}f}%, {100.0 * self.high:.{digits}f}%]"
        )


class RateComparison(BaseModel):
    label: str
    baseline: ConfidenceInterval
    candidate: ConfidenceInterval
    overlap: bool
    candidate_clearly_lower: bool
    meaningful_regression: bool
    warning: str | None = None


class MetricInterval(BaseModel):
    name: str
    interval: ConfidenceInterval | None = None
    note: str | None = None


class IntervalsBundle(BaseModel):
    """Optional block for eval / scorecard / stability JSON (#115)."""

    confidence: float = DEFAULT_CONFIDENCE
    min_n: int = DEFAULT_MIN_N
    methodology: str = (
        "Wilson score intervals for binomial rates; "
        "do not treat overlapping intervals as regressions"
    )
    metrics: list[MetricInterval] = Field(default_factory=list)
    per_probe: dict[str, ConfidenceInterval] = Field(default_factory=dict)
    comparisons: list[RateComparison] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def z_score(confidence: float = DEFAULT_CONFIDENCE) -> float:
    if confidence in _Z_SCORES:
        return _Z_SCORES[confidence]
    # Clamp to nearest tabulated level for non-standard requests.
    nearest = min(_Z_SCORES, key=lambda level: abs(level - confidence))
    return _Z_SCORES[nearest]


def wilson_interval(
    successes: int,
    n: int,
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    min_n: int = DEFAULT_MIN_N,
) -> ConfidenceInterval | None:
    """Wilson score interval for ``successes / n``. Returns None when n == 0."""
    if n < 0 or successes < 0 or successes > n:
        raise ValueError("successes must be in [0, n] and n >= 0")
    if n == 0:
        return None
    z = z_score(confidence)
    p_hat = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p_hat + z2 / (2.0 * n)) / denom
    margin = z * math.sqrt((p_hat * (1.0 - p_hat) + z2 / (4.0 * n)) / n) / denom
    low = max(0.0, center - margin)
    high = min(1.0, center + margin)
    return ConfidenceInterval(
        estimate=p_hat,
        low=low,
        high=high,
        successes=successes,
        n=n,
        confidence=confidence,
        sufficient_n=n >= min_n,
        half_width=round((high - low) / 2.0, 6),
    )


def intervals_overlap(a: ConfidenceInterval, b: ConfidenceInterval) -> bool:
    return not (a.high < b.low or b.high < a.low)


def compare_rates(
    baseline: ConfidenceInterval,
    candidate: ConfidenceInterval,
    *,
    label: str = "rate",
) -> RateComparison:
    overlap = intervals_overlap(baseline, candidate)
    clearly_lower = candidate.high < baseline.low
    meaningful = clearly_lower and baseline.sufficient_n and candidate.sufficient_n and not overlap
    warning = None if meaningful else OVERLAP_WARNING
    return RateComparison(
        label=label,
        baseline=baseline,
        candidate=candidate,
        overlap=overlap,
        candidate_clearly_lower=clearly_lower,
        meaningful_regression=meaningful,
        warning=warning,
    )


def _count_bools(values: Sequence[bool | None]) -> tuple[int, int]:
    known = [value for value in values if value is not None]
    return sum(1 for value in known if value), len(known)


def interval_from_flags(
    values: Sequence[bool | None],
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    min_n: int = DEFAULT_MIN_N,
) -> ConfidenceInterval | None:
    successes, n = _count_bools(values)
    return wilson_interval(successes, n, confidence=confidence, min_n=min_n)


def pass_at_k_interval(
    trial_passes: Sequence[bool],
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    min_n: int = DEFAULT_MIN_N,
) -> ConfidenceInterval | None:
    """CI for empirical pass rate across k trials (feeds pass@k-style reporting)."""
    return wilson_interval(
        sum(1 for passed in trial_passes if passed),
        len(trial_passes),
        confidence=confidence,
        min_n=min_n,
    )


def intervals_from_probe_results(
    results: list[ModelProbeResult],
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    min_n: int = DEFAULT_MIN_N,
) -> IntervalsBundle:
    unevaluated = {
        ModelProbeOutcome.SKIPPED,
        ModelProbeOutcome.MISSING_DATA,
        ModelProbeOutcome.FAILED_EVALUATION,
    }
    evaluated = [item for item in results if item.outcome not in unevaluated]
    selection = interval_from_flags(
        [item.tool_selection_correct for item in evaluated],
        confidence=confidence,
        min_n=min_n,
    )
    arguments = interval_from_flags(
        [item.arguments_valid for item in evaluated],
        confidence=confidence,
        min_n=min_n,
    )
    passed = interval_from_flags(
        [item.passed for item in evaluated],
        confidence=confidence,
        min_n=min_n,
    )
    metrics: list[MetricInterval] = [
        MetricInterval(name="tool_selection_accuracy", interval=selection),
        MetricInterval(name="argument_validity_rate", interval=arguments),
        MetricInterval(name="pass_rate", interval=passed),
    ]
    warnings: list[str] = []
    for item in metrics:
        if item.interval is not None and not item.interval.sufficient_n:
            warnings.append(
                f"{item.name}: n={item.interval.n} < min_n={min_n}; interval is informational only"
            )
    return IntervalsBundle(
        confidence=confidence,
        min_n=min_n,
        metrics=metrics,
        warnings=warnings,
    )


def intervals_from_stability(
    report: StabilityReport,
    *,
    results: list[ModelProbeResult] | None = None,
    confidence: float = DEFAULT_CONFIDENCE,
    min_n: int = DEFAULT_MIN_N,
) -> IntervalsBundle:
    """Aggregate + per-probe intervals from a multi-trial stability report.

    Prefer passing the raw ``results`` list from ``run_probe_trials`` so selection /
    argument rates keep their Wilson intervals. Without ``results``, only
    pass-rate / pass@k-style metrics from trial outcomes are available.
    """
    if results is not None:
        bundle = intervals_from_probe_results(results, confidence=confidence, min_n=min_n)
    else:
        trial_passes = [trial.passed for summary in report.summaries for trial in summary.trials]
        bundle = IntervalsBundle(
            confidence=confidence,
            min_n=min_n,
            metrics=[
                MetricInterval(
                    name="pass_rate",
                    interval=interval_from_flags(trial_passes, confidence=confidence, min_n=min_n),
                )
            ],
        )
        if trial_passes and (
            bundle.metrics[0].interval is not None and not bundle.metrics[0].interval.sufficient_n
        ):
            bundle.warnings.append(
                f"pass_rate: n={bundle.metrics[0].interval.n} < min_n={min_n}; "
                "interval is informational only"
            )

    per_probe: dict[str, ConfidenceInterval] = {}
    for summary in report.summaries:
        interval = pass_at_k_interval(
            [trial.passed for trial in summary.trials],
            confidence=confidence,
            min_n=min_n,
        )
        if interval is not None:
            per_probe[summary.probe_id] = interval
    bundle.per_probe = per_probe
    # pass@k style: fraction of probes with ≥1 success, with CI over probes.
    if report.summaries:
        pass_at_k_flags = [
            any(trial.passed for trial in summary.trials) for summary in report.summaries
        ]
        pass_hat_k_flags = [
            all(trial.passed for trial in summary.trials) and bool(summary.trials)
            for summary in report.summaries
        ]
        bundle.metrics.extend(
            [
                MetricInterval(
                    name="pass_at_k_rate",
                    interval=interval_from_flags(
                        pass_at_k_flags, confidence=confidence, min_n=min_n
                    ),
                    note="fraction of probes with ≥1 passing trial",
                ),
                MetricInterval(
                    name="pass_hat_k_rate",
                    interval=interval_from_flags(
                        pass_hat_k_flags, confidence=confidence, min_n=min_n
                    ),
                    note="fraction of probes where every trial passed",
                ),
            ]
        )
    return bundle


def attach_intervals(
    report: StabilityReport,
    *,
    results: list[ModelProbeResult] | None = None,
    confidence: float = DEFAULT_CONFIDENCE,
    min_n: int = DEFAULT_MIN_N,
) -> StabilityReport:
    """Return a copy of ``report`` with ``intervals`` populated (optional JSON field)."""
    bundle = intervals_from_stability(report, results=results, confidence=confidence, min_n=min_n)
    return report.model_copy(update={"intervals": bundle.model_dump(mode="json")})


def enrich_metrics_dict(
    metrics: ProbeMetrics,
    results: list[ModelProbeResult],
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    min_n: int = DEFAULT_MIN_N,
) -> dict[str, Any]:
    """JSON-friendly metrics dump with optional ``intervals`` block for scorecards."""
    payload = metrics.model_dump(mode="json")
    payload["intervals"] = intervals_from_probe_results(
        results, confidence=confidence, min_n=min_n
    ).model_dump(mode="json")
    return payload


def render_intervals_markdown(bundle: IntervalsBundle) -> str:
    lines = [
        "## Confidence intervals",
        "",
        f"_{bundle.methodology}_",
        "",
        f"Confidence: {bundle.confidence:.0%} · min_n: {bundle.min_n}",
        "",
        "| Metric | Estimate | Interval | n | Sufficient |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for item in bundle.metrics:
        if item.interval is None:
            lines.append(f"| `{item.name}` | n/a | n/a | 0 | no |")
            continue
        ci = item.interval
        lines.append(
            f"| `{item.name}` | {ci.format_pm()} | {ci.format_bracket()} | "
            f"{ci.n} | {'yes' if ci.sufficient_n else 'no'} |"
        )
    lines.append("")
    if bundle.per_probe:
        lines.extend(
            [
                "### Per-probe pass rate",
                "",
                "| Probe | Pass rate |",
                "| --- | --- |",
            ]
        )
        for probe_id, ci in sorted(bundle.per_probe.items()):
            lines.append(f"| `{probe_id}` | {ci.format_pm()} |")
        lines.append("")
    if bundle.comparisons:
        lines.extend(["### Comparisons", ""])
        for cmp in bundle.comparisons:
            status = (
                "meaningful regression"
                if cmp.meaningful_regression
                else "not a meaningful regression"
            )
            lines.append(
                f"- **{cmp.label}**: baseline {cmp.baseline.format_pm()} vs "
                f"candidate {cmp.candidate.format_pm()} — {status}"
            )
            if cmp.warning:
                lines.append(f"  - _{cmp.warning}_")
        lines.append("")
    for warning in bundle.warnings:
        lines.append(f"> ⚠ {warning}")
    if bundle.warnings:
        lines.append("")
    return "\n".join(lines)
