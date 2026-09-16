"""Tests for Behavioral Compatibility Horizon (#110)."""

from __future__ import annotations

import json
from pathlib import Path

from tool_semantics.horizon import (
    HorizonObservation,
    assign_step_bucket,
    compute_compatibility_horizon,
    observations_from_records,
    render_horizon_markdown,
    wilson_interval,
)


def _obs(steps: int, passed: bool, *, n: int = 1, trials: int = 1) -> list[HorizonObservation]:
    return [
        HorizonObservation(
            probe_id=f"p-{steps}-{i}",
            step_complexity=steps,
            passed=passed,
            trial_count=trials,
        )
        for i in range(n)
    ]


def test_assign_step_bucket() -> None:
    assert assign_step_bucket(1) == 1
    assert assign_step_bucket(2) == 3
    assert assign_step_bucket(5) == 5
    assert assign_step_bucket(7) == 10
    assert assign_step_bucket(100) == 20


def test_horizon_estimates_and_omit_when_thin() -> None:
    thin = compute_compatibility_horizon(_obs(1, True, n=2) + _obs(3, False, n=2), min_samples=5)
    assert thin.horizon_80.steps is None
    assert "insufficient" in (thin.horizon_80.omitted_reason or "")

    observations = (
        _obs(1, True, n=8, trials=3)
        + _obs(3, True, n=8, trials=3)
        + _obs(5, True, n=6, trials=3)
        + _obs(5, False, n=2, trials=3)
        + _obs(10, False, n=8, trials=3)
        + _obs(20, False, n=8, trials=3)
    )
    report = compute_compatibility_horizon(observations, min_samples=5, min_trials_for_ci=20)
    assert report.buckets[0].adequate_sample
    assert report.horizon_80.steps is not None
    assert report.horizon_50.steps is not None
    assert 3 <= report.horizon_80.steps <= 20
    md = render_horizon_markdown(report)
    assert "Behavioral Compatibility Horizon" in md
    assert "not a universal" in md
    assert "80%" in md


def test_fixture_observations_produce_horizons() -> None:
    records = json.loads(Path("examples/horizon/sample_observations.json").read_text())
    report = compute_compatibility_horizon(
        observations_from_records(records),
        min_samples=5,
        min_trials_for_ci=20,
    )
    assert all(bucket.adequate_sample for bucket in report.buckets)
    assert report.horizon_80.steps is not None
    assert report.horizon_50.steps is not None
    assert report.horizon_80.ci_low is not None


def test_wilson_and_ci_omitted_without_trials() -> None:
    low, high = wilson_interval(8, 10)
    assert low is not None and high is not None
    assert 0.0 <= low <= 0.8 <= high <= 1.0
    report = compute_compatibility_horizon(
        _obs(1, True, n=5) + _obs(10, False, n=5),
        min_samples=5,
        min_trials_for_ci=100,
    )
    assert report.horizon_80.ci_low is None
    assert report.buckets[0].ci_low is None
