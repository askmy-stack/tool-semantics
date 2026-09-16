"""Messiness grouping helpers for probe reports (#109)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from tool_semantics.probes import Probe, ProbeResult, TaskDifficulty


class MessinessBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MessinessGroupStats(BaseModel):
    band: MessinessBand
    probe_count: int = 0
    passed: int = 0
    failed: int = 0

    @property
    def success_rate(self) -> float | None:
        if self.probe_count == 0:
            return None
        return round(self.passed / self.probe_count, 4)


def messiness_band_for_probe(probe: Probe) -> MessinessBand | None:
    if probe.difficulty is None or probe.difficulty.messiness is None:
        return None
    band = probe.difficulty.messiness_band()
    return MessinessBand(band) if band else None


def group_results_by_messiness(
    probes: list[Probe],
    results: list[ProbeResult],
) -> dict[str, MessinessGroupStats]:
    by_id = {probe.id: probe for probe in probes}
    groups = {band.value: MessinessGroupStats(band=band) for band in MessinessBand}
    for result in results:
        probe = by_id.get(result.probe_id)
        if probe is None:
            continue
        band = messiness_band_for_probe(probe)
        if band is None:
            continue
        stats = groups[band.value]
        stats.probe_count += 1
        if result.passed:
            stats.passed += 1
        else:
            stats.failed += 1
    return groups


def render_messiness_groups_markdown(groups: dict[str, MessinessGroupStats]) -> str:
    lines = [
        "### Success by messiness",
        "",
        "| Band | Probes | Passed | Failed | Success rate |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for band in MessinessBand:
        stats = groups.get(band.value) or MessinessGroupStats(band=band)
        rate = "n/a" if stats.success_rate is None else f"{stats.success_rate:.0%}"
        lines.append(
            f"| `{band.value}` | {stats.probe_count} | {stats.passed} | {stats.failed} | {rate} |"
        )
    lines.append("")
    return "\n".join(lines)


# Re-export for convenience
__all__ = [
    "MessinessBand",
    "MessinessGroupStats",
    "TaskDifficulty",
    "group_results_by_messiness",
    "messiness_band_for_probe",
    "render_messiness_groups_markdown",
]
