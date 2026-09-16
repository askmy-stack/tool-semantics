"""Tool-description sensitivity and catalog-scaling research harness (#95).

Opt-in research tooling — not part of default CI. Uses FakeModelRunner for
selection metrics; live models optional via the same runner interface.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Callable, Sequence
from enum import IntEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from tool_semantics.benchmarks import snapshot_from_manifest, synthesize_manifest
from tool_semantics.models import InterfaceSnapshot, ToolContract
from tool_semantics.probes import (
    Probe,
    ProbeMetrics,
    compute_probe_metrics,
    evaluate_probes_with_model,
)
from tool_semantics.runner import (
    ModelCompletion,
    ModelRunner,
    RunnerConfig,
    RunnerMetadata,
    ToolCallRequest,
)

DEFAULT_CATALOG_SIZES: tuple[int, ...] = (10, 25, 50, 100, 250)


class RewriteLevel(IntEnum):
    """Stepwise description rewrite intensity (0 = original)."""

    ORIGINAL = 0
    LIGHT_PARAPHRASE = 1
    SHORTEN = 2
    EXPAND = 3
    SEVERE = 4


_SYNONYMS = {
    "search": "find",
    "find": "locate",
    "create": "open",
    "issue": "ticket",
    "query": "expression",
    "list": "enumerate",
    "get": "fetch",
    "delete": "remove",
    "repository": "repo",
}


class DescriptionLevelResult(BaseModel):
    level: int
    label: str
    metrics: ProbeMetrics = Field(default_factory=ProbeMetrics)
    selection_accuracy: float | None = None


class DescriptionSensitivityReport(BaseModel):
    levels: list[DescriptionLevelResult] = Field(default_factory=list)
    baseline_accuracy: float | None = None
    first_drop_level: int | None = None
    methodology: str = (
        "stepwise description rewrite → model tool-selection accuracy; "
        "research harness, not a universal claim"
    )


class CatalogSizePoint(BaseModel):
    catalog_size: int
    metrics: ProbeMetrics = Field(default_factory=ProbeMetrics)
    selection_accuracy: float | None = None


class CatalogSensitivityReport(BaseModel):
    points: list[CatalogSizePoint] = Field(default_factory=list)
    methodology: str = (
        "catalog-size scaling of selection accuracy (noise tools padded); "
        "reuses synthesize/pad pattern from discovery research"
    )


def _tokens(text: str) -> list[str]:
    return [tok for tok in re.split(r"[^a-z0-9]+", text.lower()) if tok]


def rewrite_description(text: str, level: RewriteLevel) -> str:
    """Deterministic meaning-approx rewrites at increasing intensity."""
    if level == RewriteLevel.ORIGINAL:
        return text
    tokens = _tokens(text)
    if level == RewriteLevel.LIGHT_PARAPHRASE:
        swapped = [_SYNONYMS.get(tok, tok) for tok in tokens]
        return " ".join(swapped) or text
    if level == RewriteLevel.SHORTEN:
        keep = max(3, len(tokens) // 2)
        return " ".join(tokens[:keep]) or text
    if level == RewriteLevel.EXPAND:
        fluff = "please carefully and thoroughly consider this operation when choosing tools"
        return f"{text} {fluff}"
    # SEVERE: strip meaning — keep length-ish opaque tokens only
    return " ".join(f"opaque{i}" for i in range(max(3, len(tokens))))


def apply_description_level(
    snapshot: InterfaceSnapshot,
    level: RewriteLevel,
    *,
    tool_names: Sequence[str] | None = None,
) -> InterfaceSnapshot:
    names = set(tool_names) if tool_names else None
    tools: list[ToolContract] = []
    for tool in snapshot.tools:
        if names is not None and tool.name not in names:
            tools.append(tool)
            continue
        tools.append(
            tool.model_copy(update={"description": rewrite_description(tool.description, level)})
        )
    return snapshot.model_copy(
        update={
            "tools": tools,
            "metadata": {
                **snapshot.metadata,
                "description_rewrite_level": int(level),
            },
        }
    )


def pad_catalog(
    core: InterfaceSnapshot,
    target_size: int,
    *,
    noise_prefix: str = "noise",
) -> InterfaceSnapshot:
    """Pad a snapshot with synthetic noise tools (discovery-style)."""
    if target_size <= len(core.tools):
        return core
    need = target_size - len(core.tools)
    noise = snapshot_from_manifest(synthesize_manifest(need, prefix=noise_prefix))
    # Avoid name collisions with core tools.
    core_names = {tool.name for tool in core.tools}
    noise_tools = [tool for tool in noise.tools if tool.name not in core_names]
    while len(core.tools) + len(noise_tools) < target_size:
        extra = snapshot_from_manifest(synthesize_manifest(target_size, prefix=f"{noise_prefix}_x"))
        for tool in extra.tools:
            if tool.name not in core_names and all(t.name != tool.name for t in noise_tools):
                noise_tools.append(tool)
            if len(core.tools) + len(noise_tools) >= target_size:
                break
    tools = list(core.tools) + noise_tools[:need]
    return core.model_copy(
        update={
            "tools": tools,
            "metadata": {**core.metadata, "catalog_size": len(tools)},
        }
    )


class DescriptionAwareFakeRunner:
    """Pick the tool whose description tokens overlap the user intent most.

    Used so description rewrites can shift selection under a deterministic fake.
    """

    def __init__(self) -> None:
        self._metadata = RunnerMetadata(
            provider="fake-description-aware", model="overlap", model_version="1"
        )
        self.call_count = 0

    @property
    def metadata(self) -> RunnerMetadata:
        return self._metadata

    def complete(
        self,
        *,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
        config: RunnerConfig | None = None,
    ) -> ModelCompletion:
        del system, config
        self.call_count += 1
        intent = set(_tokens(user))
        best_name = "unknown"
        best_score = -1.0
        for item in tools:
            function = item.get("function") or {}
            name = str(function.get("name") or "")
            desc = str(function.get("description") or "")
            score = len(intent & set(_tokens(desc))) / max(1, len(intent))
            # Prefer lexicographically smaller names on ties (stable).
            if score > best_score or (score == best_score and name < best_name):
                best_score = score
                best_name = name
        # No lexical overlap → force a deterministic wrong pick so metrics stay
        # evaluated (MISSING_DATA would null out selection accuracy).
        if best_score <= 0:
            names = sorted(
                str((item.get("function") or {}).get("name") or "")
                for item in tools
                if (item.get("function") or {}).get("name")
            )
            best_name = names[0] if names else "unknown"
        args: dict[str, Any] = {"query": "x"}
        for item in tools:
            function = item.get("function") or {}
            if str(function.get("name") or "") != best_name:
                continue
            params = function.get("parameters") or {}
            required = params.get("required") or []
            if required:
                args = {str(required[0]): "x"}
            break
        return ModelCompletion(
            tool_calls=[ToolCallRequest(name=best_name, arguments=args)],
            metadata=self._metadata,
        )


def description_aware_factory() -> DescriptionAwareFakeRunner:
    """Factory for description-sensitivity runs (CI / offline)."""
    return DescriptionAwareFakeRunner()


def run_description_sensitivity(
    snapshot: InterfaceSnapshot,
    probes: list[Probe],
    runner_factory: Callable[[], ModelRunner],
    *,
    levels: Sequence[RewriteLevel] | None = None,
    require_approval: bool = True,
) -> DescriptionSensitivityReport:
    selected = list(levels) if levels is not None else list(RewriteLevel)
    results: list[DescriptionLevelResult] = []
    baseline_acc: float | None = None
    first_drop: int | None = None
    for level in selected:
        variant = apply_description_level(snapshot, RewriteLevel(level))
        report = evaluate_probes_with_model(
            variant,
            probes,
            runner_factory(),
            require_approval=require_approval,
        )
        metrics = compute_probe_metrics(report.results)
        acc = metrics.tool_selection_accuracy
        if baseline_acc is None:
            baseline_acc = acc
        elif (
            first_drop is None
            and baseline_acc is not None
            and acc is not None
            and acc < baseline_acc - 1e-9
        ):
            first_drop = int(level)
        results.append(
            DescriptionLevelResult(
                level=int(level),
                label=RewriteLevel(level).name.lower(),
                metrics=metrics,
                selection_accuracy=acc,
            )
        )
    return DescriptionSensitivityReport(
        levels=results,
        baseline_accuracy=baseline_acc,
        first_drop_level=first_drop,
    )


def run_catalog_sensitivity(
    snapshot: InterfaceSnapshot,
    probes: list[Probe],
    runner_factory: Callable[[], ModelRunner],
    *,
    sizes: Sequence[int] = DEFAULT_CATALOG_SIZES,
    require_approval: bool = True,
) -> CatalogSensitivityReport:
    points: list[CatalogSizePoint] = []
    for size in sizes:
        padded = pad_catalog(snapshot, int(size))
        report = evaluate_probes_with_model(
            padded,
            probes,
            runner_factory(),
            require_approval=require_approval,
        )
        metrics = compute_probe_metrics(report.results)
        points.append(
            CatalogSizePoint(
                catalog_size=len(padded.tools),
                metrics=metrics,
                selection_accuracy=metrics.tool_selection_accuracy,
            )
        )
    return CatalogSensitivityReport(points=points)


def export_sensitivity_json(payload: BaseModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")


def export_description_sensitivity_csv(report: DescriptionSensitivityReport) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["level", "label", "selection_accuracy", "evaluated_count"],
    )
    writer.writeheader()
    for item in report.levels:
        writer.writerow(
            {
                "level": item.level,
                "label": item.label,
                "selection_accuracy": item.selection_accuracy,
                "evaluated_count": item.metrics.evaluated_count,
            }
        )
    return buf.getvalue()


def export_catalog_sensitivity_csv(report: CatalogSensitivityReport) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["catalog_size", "selection_accuracy", "evaluated_count"],
    )
    writer.writeheader()
    for item in report.points:
        writer.writerow(
            {
                "catalog_size": item.catalog_size,
                "selection_accuracy": item.selection_accuracy,
                "evaluated_count": item.metrics.evaluated_count,
            }
        )
    return buf.getvalue()


def render_description_sensitivity_markdown(report: DescriptionSensitivityReport) -> str:
    lines = [
        "## Description sensitivity",
        "",
        f"_{report.methodology}_",
        "",
        f"Baseline accuracy: {report.baseline_accuracy}",
        f"First drop level: {report.first_drop_level}",
        "",
        "| Level | Label | Selection accuracy |",
        "| ---: | --- | ---: |",
    ]
    for item in report.levels:
        acc = "n/a" if item.selection_accuracy is None else f"{item.selection_accuracy:.0%}"
        lines.append(f"| {item.level} | `{item.label}` | {acc} |")
    lines.append("")
    return "\n".join(lines)


def render_catalog_sensitivity_markdown(report: CatalogSensitivityReport) -> str:
    lines = [
        "## Catalog-size sensitivity",
        "",
        f"_{report.methodology}_",
        "",
        "| Catalog size | Selection accuracy |",
        "| ---: | ---: |",
    ]
    for item in report.points:
        acc = "n/a" if item.selection_accuracy is None else f"{item.selection_accuracy:.0%}"
        lines.append(f"| {item.catalog_size} | {acc} |")
    lines.append("")
    return "\n".join(lines)
