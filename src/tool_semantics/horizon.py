"""Behavioral Compatibility Horizon (#110).

Project-specific, METR-inspired metric: at what workflow step-complexity does
compatibility begin to fail? Transparent methodology — not a universal claim.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field

# Canonical step-complexity buckets (acceptance: 1 / 3 / 5 / 10 / 20).
STEP_BUCKETS: tuple[int, ...] = (1, 3, 5, 10, 20)

# Minimum observations per bucket before publishing a rate / horizon.
DEFAULT_MIN_SAMPLES = 5
# Minimum total trials across buckets before publishing CIs on horizons.
DEFAULT_MIN_TRIALS_FOR_CI = 20


class HorizonObservation(BaseModel):
    """One probe / workflow outcome at a measured complexity."""

    probe_id: str = ""
    # Measurable complexity: tool steps / state transitions (not human-time).
    step_complexity: int
    passed: bool
    # Optional repeated trials for this probe at this complexity.
    trial_count: int = 1
    success_count: int | None = None  # defaults to trial_count if passed else 0

    def successes(self) -> int:
        if self.success_count is not None:
            return self.success_count
        if self.trial_count <= 1:
            return 1 if self.passed else 0
        return self.trial_count if self.passed else 0


class BucketStats(BaseModel):
    steps: int
    observations: int = 0
    successes: int = 0
    trials: int = 0
    success_rate: float | None = None
    # Wilson score interval when trials are adequate; omitted otherwise.
    ci_low: float | None = None
    ci_high: float | None = None
    adequate_sample: bool = False


class HorizonEstimate(BaseModel):
    """Step-complexity where success rate crosses a target (e.g. 0.8 / 0.5)."""

    target_rate: float
    steps: float | None = None
    omitted_reason: str | None = None
    ci_low: float | None = None
    ci_high: float | None = None


class CompatibilityHorizonReport(BaseModel):
    buckets: list[BucketStats] = Field(default_factory=list)
    horizon_80: HorizonEstimate = Field(default_factory=lambda: HorizonEstimate(target_rate=0.8))
    horizon_50: HorizonEstimate = Field(default_factory=lambda: HorizonEstimate(target_rate=0.5))
    methodology: str = (
        "tool-semantics behavioral compatibility horizon — "
        "step-complexity buckets; not a universal capability claim"
    )
    min_samples: int = DEFAULT_MIN_SAMPLES
    total_observations: int = 0
    total_trials: int = 0


def assign_step_bucket(step_complexity: int, buckets: tuple[int, ...] = STEP_BUCKETS) -> int:
    """Map a raw step count to the nearest canonical bucket (ceil toward harder)."""
    if step_complexity <= 0:
        return buckets[0]
    for bucket in buckets:
        if step_complexity <= bucket:
            return bucket
    return buckets[-1]


def wilson_interval(
    successes: int,
    trials: int,
    *,
    z: float = 1.96,
) -> tuple[float | None, float | None]:
    """Wilson score interval for a binomial proportion; None when trials == 0."""
    if trials <= 0:
        return None, None
    phat = successes / trials
    z2 = z * z
    denom = 1.0 + z2 / trials
    center = (phat + z2 / (2 * trials)) / denom
    margin = (z / denom) * math.sqrt((phat * (1.0 - phat) + z2 / (4 * trials)) / trials)
    return max(0.0, center - margin), min(1.0, center + margin)


def _bucket_stats(
    observations: Iterable[HorizonObservation],
    *,
    buckets: tuple[int, ...] = STEP_BUCKETS,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    min_trials_for_ci: int = DEFAULT_MIN_TRIALS_FOR_CI,
) -> list[BucketStats]:
    by_bucket: dict[int, list[HorizonObservation]] = {b: [] for b in buckets}
    for obs in observations:
        bucket = assign_step_bucket(obs.step_complexity, buckets)
        by_bucket[bucket].append(obs)

    stats: list[BucketStats] = []
    for steps in buckets:
        items = by_bucket[steps]
        observations_n = len(items)
        trials = sum(max(1, item.trial_count) for item in items)
        successes = sum(item.successes() for item in items)
        adequate = observations_n >= min_samples
        rate = (successes / trials) if trials else None
        ci_low = ci_high = None
        if adequate and trials >= min_trials_for_ci and rate is not None:
            ci_low, ci_high = wilson_interval(successes, trials)
        stats.append(
            BucketStats(
                steps=steps,
                observations=observations_n,
                successes=successes,
                trials=trials,
                success_rate=round(rate, 4) if rate is not None else None,
                ci_low=round(ci_low, 4) if ci_low is not None else None,
                ci_high=round(ci_high, 4) if ci_high is not None else None,
                adequate_sample=adequate,
            )
        )
    return stats


def _interpolate_horizon(
    buckets: list[BucketStats],
    target: float,
    *,
    min_samples: int,
) -> HorizonEstimate:
    """Estimate step-complexity where success rate crosses ``target`` from above.

    Uses linear interpolation between adjacent adequate buckets. Omits the
    estimate when sample size is inadequate or the crossing cannot be located.
    """
    adequate = [b for b in buckets if b.adequate_sample and b.success_rate is not None]
    if len(adequate) < 2:
        return HorizonEstimate(
            target_rate=target,
            omitted_reason="insufficient adequate buckets (need ≥2 with min_samples)",
        )

    # Always above target across measured range.
    if all(b.success_rate is not None and b.success_rate >= target for b in adequate):
        return HorizonEstimate(
            target_rate=target,
            omitted_reason=f"success stays ≥{target:.0%} across measured buckets",
        )

    # Always below target.
    if all(b.success_rate is not None and b.success_rate < target for b in adequate):
        return HorizonEstimate(
            target_rate=target,
            steps=float(adequate[0].steps),
            omitted_reason=None,
            ci_low=None,
            ci_high=None,
        )

    for left, right in zip(adequate, adequate[1:], strict=False):
        assert left.success_rate is not None and right.success_rate is not None
        if left.success_rate >= target and right.success_rate < target:
            span = left.success_rate - right.success_rate
            if span <= 0:
                steps = float(right.steps)
            else:
                frac = (left.success_rate - target) / span
                steps = left.steps + frac * (right.steps - left.steps)
            # Rough CI from bucket CIs when both sides have them.
            ci_low = ci_high = None
            if (
                left.ci_low is not None
                and left.ci_high is not None
                and right.ci_low is not None
                and right.ci_high is not None
            ):
                left_steps = float(left.steps)
                right_steps = float(right.steps)
                span_steps = right_steps - left_steps
                crossings: list[float] = []
                for hi, lo in (
                    (left.ci_high, right.ci_low),
                    (left.ci_low, right.ci_high),
                ):
                    rate_span = hi - lo
                    if rate_span <= 0:
                        crossings.append(right_steps)
                    else:
                        crossings.append(left_steps + ((hi - target) / rate_span) * span_steps)
                ci_low, ci_high = min(crossings), max(crossings)
            return HorizonEstimate(
                target_rate=target,
                steps=round(steps, 2),
                ci_low=round(ci_low, 2) if ci_low is not None else None,
                ci_high=round(ci_high, 2) if ci_high is not None else None,
            )

    return HorizonEstimate(
        target_rate=target,
        omitted_reason="no monotonic crossing of target rate in adequate buckets",
    )


def compute_compatibility_horizon(
    observations: list[HorizonObservation],
    *,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    min_trials_for_ci: int = DEFAULT_MIN_TRIALS_FOR_CI,
    buckets: tuple[int, ...] = STEP_BUCKETS,
) -> CompatibilityHorizonReport:
    """Compute bucket rates and 80%/50% horizon estimates."""
    stats = _bucket_stats(
        observations,
        buckets=buckets,
        min_samples=min_samples,
        min_trials_for_ci=min_trials_for_ci,
    )
    total_obs = len(observations)
    total_trials = sum(max(1, item.trial_count) for item in observations)
    h80 = _interpolate_horizon(stats, 0.8, min_samples=min_samples)
    h50 = _interpolate_horizon(stats, 0.5, min_samples=min_samples)
    # Drop CIs on horizons when overall trial count is too small.
    if total_trials < min_trials_for_ci:
        h80 = h80.model_copy(update={"ci_low": None, "ci_high": None})
        h50 = h50.model_copy(update={"ci_low": None, "ci_high": None})
    return CompatibilityHorizonReport(
        buckets=stats,
        horizon_80=h80,
        horizon_50=h50,
        min_samples=min_samples,
        total_observations=total_obs,
        total_trials=total_trials,
    )


def observations_from_records(records: list[dict[str, Any]]) -> list[HorizonObservation]:
    """Build observations from plain dict fixtures."""
    return [HorizonObservation.model_validate(item) for item in records]


def render_horizon_markdown(report: CompatibilityHorizonReport) -> str:
    lines = [
        "## Behavioral Compatibility Horizon",
        "",
        f"_{report.methodology}_",
        "",
        f"Min samples / bucket for rates: **{report.min_samples}**. "
        f"Observations: {report.total_observations}; trials: {report.total_trials}.",
        "",
        "### Success by step-complexity",
        "",
        "| Steps | Obs | Trials | Success rate | 95% CI | Adequate? |",
        "| ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for bucket in report.buckets:
        rate = "n/a" if bucket.success_rate is None else f"{bucket.success_rate:.0%}"
        if bucket.ci_low is None or bucket.ci_high is None:
            ci = "n/a"
        else:
            ci = f"[{bucket.ci_low:.0%}, {bucket.ci_high:.0%}]"
        lines.append(
            f"| {bucket.steps} | {bucket.observations} | {bucket.trials} | "
            f"{rate} | {ci} | {'yes' if bucket.adequate_sample else 'no'} |"
        )
    lines.append("")
    lines.append("### Horizon estimates")
    lines.append("")
    for label, estimate in (("80%", report.horizon_80), ("50%", report.horizon_50)):
        if estimate.steps is None:
            lines.append(
                f"- **{label} horizon:** omitted — {estimate.omitted_reason or 'unavailable'}"
            )
        else:
            ci = ""
            if estimate.ci_low is not None and estimate.ci_high is not None:
                ci = f" (CI steps [{estimate.ci_low:g}, {estimate.ci_high:g}])"
            lines.append(f"- **{label} horizon:** ~{estimate.steps:g} steps{ci}")
    lines.append("")
    return "\n".join(lines)
