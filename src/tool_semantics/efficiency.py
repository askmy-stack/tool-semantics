"""Efficiency regression metrics (#114).

Correctness remains the only pass/fail gate. Efficiency metrics surface
operational cost (calls, retries, latency, tokens) and relative regressions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EfficiencyMetrics(BaseModel):
    """Operational cost for a probe suite / workflow run."""

    tool_call_count: int = 0
    failed_call_count: int = 0
    retry_count: int = 0
    latency_ms: float | None = None
    wall_clock_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    # Optional provider-reported currency cost when available.
    model_cost: float | None = None
    currency: str | None = None
    label: str = ""


class EfficiencyDelta(BaseModel):
    metric: str
    baseline: float | None = None
    candidate: float | None = None
    absolute: float | None = None
    relative: float | None = None  # fraction, e.g. 0.94 = +94%
    regressing: bool = False


class EfficiencyReport(BaseModel):
    baseline: EfficiencyMetrics = Field(default_factory=EfficiencyMetrics)
    candidate: EfficiencyMetrics = Field(default_factory=EfficiencyMetrics)
    deltas: list[EfficiencyDelta] = Field(default_factory=list)
    # Informational only — never drives compare/probe exit codes by itself.
    has_regression: bool = False

    @property
    def affects_pass_fail(self) -> bool:
        return False


def _rel(baseline: float, candidate: float) -> float | None:
    if baseline == 0:
        return None
    return (candidate - baseline) / abs(baseline)


def _f(value: int | None) -> float | None:
    return None if value is None else float(value)


def compare_efficiency(
    baseline: EfficiencyMetrics,
    candidate: EfficiencyMetrics,
    *,
    call_regression_ratio: float = 0.5,
    latency_regression_ratio: float = 0.5,
    token_regression_ratio: float = 0.5,
    cost_regression_ratio: float = 0.5,
) -> EfficiencyReport:
    """Compare efficiency metrics; flag relative regressions (informational)."""
    deltas: list[EfficiencyDelta] = []

    def add(
        name: str,
        base: float | None,
        cand: float | None,
        *,
        threshold: float | None = None,
        higher_is_worse: bool = True,
    ) -> None:
        if base is None and cand is None:
            return
        absolute = None
        relative = None
        regressing = False
        if base is not None and cand is not None:
            absolute = cand - base
            relative = _rel(base, cand)
            if threshold is not None and relative is not None:
                if higher_is_worse and relative >= threshold:
                    regressing = True
                if not higher_is_worse and relative <= -threshold:
                    regressing = True
        deltas.append(
            EfficiencyDelta(
                metric=name,
                baseline=base,
                candidate=cand,
                absolute=absolute,
                relative=relative,
                regressing=regressing,
            )
        )

    add(
        "tool_call_count",
        float(baseline.tool_call_count),
        float(candidate.tool_call_count),
        threshold=call_regression_ratio,
    )
    add(
        "failed_call_count",
        float(baseline.failed_call_count),
        float(candidate.failed_call_count),
        threshold=call_regression_ratio,
    )
    add(
        "retry_count",
        float(baseline.retry_count),
        float(candidate.retry_count),
        threshold=call_regression_ratio,
    )
    add(
        "latency_ms",
        baseline.latency_ms,
        candidate.latency_ms,
        threshold=latency_regression_ratio,
    )
    add(
        "wall_clock_ms",
        baseline.wall_clock_ms,
        candidate.wall_clock_ms,
        threshold=latency_regression_ratio,
    )
    add(
        "prompt_tokens",
        _f(baseline.prompt_tokens),
        _f(candidate.prompt_tokens),
        threshold=token_regression_ratio,
    )
    add(
        "completion_tokens",
        _f(baseline.completion_tokens),
        _f(candidate.completion_tokens),
        threshold=token_regression_ratio,
    )
    add(
        "model_cost",
        baseline.model_cost,
        candidate.model_cost,
        threshold=cost_regression_ratio,
    )

    return EfficiencyReport(
        baseline=baseline,
        candidate=candidate,
        deltas=deltas,
        has_regression=any(item.regressing for item in deltas),
    )


def aggregate_efficiency(
    records: list[EfficiencyMetrics],
    *,
    label: str = "",
) -> EfficiencyMetrics:
    """Sum / average metrics across per-probe or per-trial records."""
    if not records:
        return EfficiencyMetrics(label=label)
    latency_values = [item.latency_ms for item in records if item.latency_ms is not None]
    wall_values = [item.wall_clock_ms for item in records if item.wall_clock_ms is not None]
    prompt_values = [item.prompt_tokens for item in records if item.prompt_tokens is not None]
    completion_values = [
        item.completion_tokens for item in records if item.completion_tokens is not None
    ]
    cost_values = [item.model_cost for item in records if item.model_cost is not None]
    currency = next((item.currency for item in records if item.currency), None)
    return EfficiencyMetrics(
        tool_call_count=sum(item.tool_call_count for item in records),
        failed_call_count=sum(item.failed_call_count for item in records),
        retry_count=sum(item.retry_count for item in records),
        latency_ms=sum(latency_values) if latency_values else None,
        wall_clock_ms=sum(wall_values) if wall_values else None,
        prompt_tokens=sum(prompt_values) if prompt_values else None,
        completion_tokens=sum(completion_values) if completion_values else None,
        model_cost=sum(cost_values) if cost_values else None,
        currency=currency,
        label=label,
    )


def load_efficiency_pair(path: Path | str) -> tuple[EfficiencyMetrics, EfficiencyMetrics]:
    """Load baseline/candidate metrics from a JSON fixture.

    Expected shape::

        {"baseline": {...}, "candidate": {...}}
    """
    import json

    payload: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return (
        EfficiencyMetrics.model_validate(payload["baseline"]),
        EfficiencyMetrics.model_validate(payload["candidate"]),
    )


def _fmt_rel(relative: float | None) -> str:
    if relative is None:
        return "n/a"
    sign = "+" if relative >= 0 else ""
    return f"{sign}{relative:.0%}"


def render_efficiency_markdown(report: EfficiencyReport) -> str:
    lines = [
        "## EFFICIENCY",
        "",
        "_Informational only — does not affect pass/fail._",
        "",
        "| Metric | Baseline | Candidate | Δ | Relative | Regression? |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report.deltas:
        base = "n/a" if item.baseline is None else f"{item.baseline:g}"
        cand = "n/a" if item.candidate is None else f"{item.candidate:g}"
        absolute = "n/a" if item.absolute is None else f"{item.absolute:g}"
        lines.append(
            f"| `{item.metric}` | {base} | {cand} | {absolute} | "
            f"{_fmt_rel(item.relative)} | "
            f"{'yes' if item.regressing else 'no'} |"
        )
    lines.append("")
    if report.has_regression:
        lines.append("Efficiency regressions detected (review cost/latency).")
    else:
        lines.append("No efficiency regressions above configured thresholds.")
    lines.append("")
    return "\n".join(lines)


def append_efficiency_section(
    markdown: str,
    report: EfficiencyReport | None,
) -> str:
    """Append an EFFICIENCY section when metrics are available."""
    if report is None:
        return markdown
    body = markdown.rstrip() + "\n\n" + render_efficiency_markdown(report)
    return body if body.endswith("\n") else body + "\n"
