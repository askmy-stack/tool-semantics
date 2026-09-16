"""Format-sensitivity fuzz testing for equivalent schemas (#111).

Generate meaning-preserving schema presentation variants and measure whether
model tool-selection accuracy changes. CI must use FakeModelRunner only.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from tool_semantics.models import InterfaceSnapshot, ToolContract, ToolParameter
from tool_semantics.probes import (
    Probe,
    ProbeMetrics,
    compute_probe_metrics,
    evaluate_probes_with_model,
)
from tool_semantics.runner import (
    FakeModelRunner,
    ModelCompletion,
    ModelRunner,
    RunnerConfig,
    RunnerMetadata,
    ToolCallRequest,
)


class FormatTransform(StrEnum):
    """Documented meaning-preserving presentation transforms."""

    PROPERTY_ORDER = "property_order"
    DESCRIPTION_WHITESPACE = "description_whitespace"
    EQUIVALENT_JSON_SCHEMA = "equivalent_json_schema"
    PARAMETER_ORDER = "parameter_order"


TRANSFORM_DOCS: dict[FormatTransform, str] = {
    FormatTransform.PROPERTY_ORDER: (
        "Reorder keys inside each parameter's JSON Schema object; "
        "semantics unchanged (JSON objects are unordered)."
    ),
    FormatTransform.DESCRIPTION_WHITESPACE: (
        "Collapse / expand incidental whitespace in tool and parameter descriptions "
        "without changing visible words."
    ),
    FormatTransform.EQUIVALENT_JSON_SCHEMA: (
        "Rewrite schemas with equivalent JSON Schema forms "
        "(e.g. type string ↔ single-entry type array; stable reordering of `required`)."
    ),
    FormatTransform.PARAMETER_ORDER: (
        "Reorder the tool's parameter list; names/types/required flags unchanged."
    ),
}


def _reorder_object_keys(schema: dict[str, Any], *, reverse: bool = False) -> dict[str, Any]:
    items = sorted(schema.items(), key=lambda item: item[0], reverse=reverse)
    out: dict[str, Any] = {}
    for key, value in items:
        if isinstance(value, dict):
            out[key] = _reorder_object_keys(value, reverse=reverse)
        elif isinstance(value, list):
            out[key] = [
                _reorder_object_keys(item, reverse=reverse) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            out[key] = value
    return out


def _normalize_description_whitespace(text: str, *, style: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip())
    if style == "expand":
        return "  " + collapsed.replace(" ", "  ") + "  "
    return collapsed


def _equivalent_schema(schema: dict[str, Any], *, variant: int) -> dict[str, Any]:
    out = copy.deepcopy(schema)
    type_value = out.get("type")
    if variant % 2 == 0 and isinstance(type_value, str):
        out["type"] = [type_value]
    elif variant % 2 == 1 and isinstance(type_value, list) and len(type_value) == 1:
        out["type"] = type_value[0]
    if "required" in out and isinstance(out["required"], list):
        out["required"] = sorted(out["required"], reverse=(variant % 2 == 1))
    if isinstance(out.get("properties"), dict):
        props = out["properties"]
        keys = sorted(props.keys(), reverse=(variant % 2 == 1))
        out["properties"] = {
            key: _equivalent_schema(props[key], variant=variant)
            if isinstance(props[key], dict)
            else props[key]
            for key in keys
        }
    return _reorder_object_keys(out, reverse=(variant % 2 == 1))


def _transform_tool(
    tool: ToolContract,
    transform: FormatTransform,
    *,
    variant_index: int,
) -> ToolContract:
    params = list(tool.parameters)
    description = tool.description
    if transform == FormatTransform.PARAMETER_ORDER:
        params = (
            list(reversed(params))
            if variant_index % 2
            else sorted(params, key=lambda item: item.name, reverse=True)
        )
    elif transform == FormatTransform.DESCRIPTION_WHITESPACE:
        style = "expand" if variant_index % 2 else "collapse"
        description = _normalize_description_whitespace(description, style=style)
        new_params: list[ToolParameter] = []
        for param in params:
            desc = param.description
            if desc:
                desc = _normalize_description_whitespace(desc, style=style)
            new_params.append(param.model_copy(update={"description": desc}))
        params = new_params
    elif transform == FormatTransform.PROPERTY_ORDER:
        reverse = variant_index % 2 == 1
        params = [
            param.model_copy(
                update={"schema_": _reorder_object_keys(param.schema_, reverse=reverse)}
            )
            for param in params
        ]
    elif transform == FormatTransform.EQUIVALENT_JSON_SCHEMA:
        params = [
            param.model_copy(
                update={"schema_": _equivalent_schema(param.schema_, variant=variant_index)}
            )
            for param in params
        ]
    return tool.model_copy(update={"description": description, "parameters": params})


def apply_transform(
    snapshot: InterfaceSnapshot,
    transform: FormatTransform,
    *,
    variant_index: int = 0,
) -> InterfaceSnapshot:
    """Return a snapshot with one meaning-preserving presentation transform applied."""
    tools = [
        _transform_tool(tool, transform, variant_index=variant_index) for tool in snapshot.tools
    ]
    return snapshot.model_copy(
        update={
            "tools": tools,
            "metadata": {
                **snapshot.metadata,
                "format_fuzz": {
                    "transform": transform.value,
                    "variant_index": variant_index,
                    "doc": TRANSFORM_DOCS[transform],
                },
            },
        }
    )


def generate_format_variants(
    snapshot: InterfaceSnapshot,
    *,
    transforms: list[FormatTransform] | None = None,
    variants_per_transform: int = 2,
) -> list[tuple[FormatTransform, InterfaceSnapshot]]:
    """Generate multiple equivalent schema presentation variants."""
    selected = transforms or list(FormatTransform)
    out: list[tuple[FormatTransform, InterfaceSnapshot]] = []
    for transform in selected:
        for index in range(max(1, variants_per_transform)):
            out.append((transform, apply_transform(snapshot, transform, variant_index=index)))
    return out


def canonicalize_snapshot_schemas(snapshot: InterfaceSnapshot) -> list[dict[str, Any]]:
    """Canonical form used to assert transforms preserve schema meaning."""

    def canon_schema(schema: dict[str, Any]) -> dict[str, Any]:
        data = copy.deepcopy(schema)
        type_value = data.get("type")
        if isinstance(type_value, list) and len(type_value) == 1:
            data["type"] = type_value[0]
        if isinstance(data.get("required"), list):
            data["required"] = sorted(data["required"])
        if isinstance(data.get("properties"), dict):
            props = data["properties"]
            data["properties"] = {
                key: canon_schema(props[key]) if isinstance(props[key], dict) else props[key]
                for key in sorted(props)
            }
        return _reorder_object_keys(data)

    tools = []
    for tool in sorted(snapshot.tools, key=lambda item: item.name):
        params = []
        for param in sorted(tool.parameters, key=lambda item: item.name):
            desc = re.sub(r"\s+", " ", (param.description or "").strip())
            params.append(
                {
                    "name": param.name,
                    "required": param.required,
                    "description": desc,
                    "schema": canon_schema(param.schema_),
                }
            )
        tools.append(
            {
                "name": tool.name,
                "description": re.sub(r"\s+", " ", tool.description.strip()),
                "parameters": params,
                "risk": tool.risk.value,
            }
        )
    return tools


def schemas_semantically_equal(left: InterfaceSnapshot, right: InterfaceSnapshot) -> bool:
    return canonicalize_snapshot_schemas(left) == canonicalize_snapshot_schemas(right)


class FormatVariantResult(BaseModel):
    transform: str
    variant_index: int = 0
    metrics: ProbeMetrics = Field(default_factory=ProbeMetrics)
    accuracy_delta: float | None = None


class FormatSensitivityReport(BaseModel):
    baseline: ProbeMetrics = Field(default_factory=ProbeMetrics)
    variants: list[FormatVariantResult] = Field(default_factory=list)
    threshold: float = 0.05
    warning: bool = False
    warning_message: str = ""
    max_abs_delta: float | None = None

    @property
    def passed(self) -> bool:
        return not self.warning


def _warning_message(max_delta: float, threshold: float) -> str:
    return (
        f"FORMAT SENSITIVITY WARNING: tool-selection accuracy moved by "
        f"{max_delta:+.1%} (threshold ±{threshold:.0%}) under meaning-preserving "
        f"schema formatting changes."
    )


def run_format_sensitivity(
    snapshot: InterfaceSnapshot,
    probes: list[Probe],
    runner_factory: Callable[[], ModelRunner],
    *,
    threshold: float = 0.05,
    transforms: list[FormatTransform] | None = None,
    variants_per_transform: int = 1,
    config: RunnerConfig | None = None,
    require_approval: bool = False,
) -> FormatSensitivityReport:
    """Compare baseline vs format-perturbed selection accuracy.

    ``runner_factory`` builds a fresh runner per snapshot so stateful fakes reset.
    """
    baseline_report = evaluate_probes_with_model(
        snapshot,
        probes,
        runner_factory(),
        config=config,
        require_approval=require_approval,
    )
    baseline_metrics = compute_probe_metrics(baseline_report.results)
    baseline_acc = baseline_metrics.tool_selection_accuracy

    variants: list[FormatVariantResult] = []
    max_delta: float | None = None
    for transform, variant_snap in generate_format_variants(
        snapshot,
        transforms=transforms,
        variants_per_transform=variants_per_transform,
    ):
        variant_report = evaluate_probes_with_model(
            variant_snap,
            probes,
            runner_factory(),
            config=config,
            require_approval=require_approval,
        )
        metrics = compute_probe_metrics(variant_report.results)
        delta = None
        if baseline_acc is not None and metrics.tool_selection_accuracy is not None:
            delta = metrics.tool_selection_accuracy - baseline_acc
            if max_delta is None or abs(delta) > abs(max_delta):
                max_delta = delta
        meta = variant_snap.metadata.get("format_fuzz") or {}
        variants.append(
            FormatVariantResult(
                transform=transform.value,
                variant_index=int(meta.get("variant_index", 0)),
                metrics=metrics,
                accuracy_delta=delta,
            )
        )

    warning = bool(max_delta is not None and abs(max_delta) > threshold)
    return FormatSensitivityReport(
        baseline=baseline_metrics,
        variants=variants,
        threshold=threshold,
        warning=warning,
        warning_message=_warning_message(max_delta, threshold)
        if warning and max_delta is not None
        else "",
        max_abs_delta=abs(max_delta) if max_delta is not None else None,
    )


class FormatAwareFakeRunner:
    """Test double that flips selection when equivalent ``type: [string]`` appears.

    CI harnesses use plain ``FakeModelRunner`` only.
    """

    def __init__(self, *, preferred_tool: str, fallback_tool: str) -> None:
        self.preferred_tool = preferred_tool
        self.fallback_tool = fallback_tool
        self.call_count = 0
        self._metadata = RunnerMetadata(
            provider="fake-format-aware", model="test", model_version="1"
        )

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
        del system, user, config
        self.call_count += 1
        serialized = json.dumps(tools)
        chosen = self.fallback_tool if '["string"]' in serialized else self.preferred_tool
        return ModelCompletion(
            tool_calls=[ToolCallRequest(name=chosen, arguments={"query": "x"})],
            metadata=self._metadata,
        )


def scripted_fake_factory(
    responses: list[ModelCompletion],
) -> Callable[[], FakeModelRunner]:
    """CI helper: each call gets a fresh FakeModelRunner with the same scripts."""

    def factory() -> FakeModelRunner:
        return FakeModelRunner(responses=list(responses))

    return factory


def render_format_sensitivity_markdown(report: FormatSensitivityReport) -> str:
    lines = [
        "## FORMAT SENSITIVITY",
        "",
        f"Threshold: ±{report.threshold:.0%}",
        "",
    ]
    if report.warning:
        lines.append(f"**{report.warning_message}**")
        lines.append("")
    else:
        lines.append("No format-sensitivity warning.")
        lines.append("")
    lines.extend(
        [
            "| Transform | Variant | Selection accuracy | Δ vs baseline |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    base = report.baseline.tool_selection_accuracy
    base_s = "n/a" if base is None else f"{base:.0%}"
    lines.append(f"| `baseline` | — | {base_s} | — |")
    for item in report.variants:
        acc = item.metrics.tool_selection_accuracy
        acc_s = "n/a" if acc is None else f"{acc:.0%}"
        delta_s = "n/a" if item.accuracy_delta is None else f"{item.accuracy_delta:+.0%}"
        lines.append(f"| `{item.transform}` | {item.variant_index} | {acc_s} | {delta_s} |")
    lines.append("")
    lines.append("### Meaning-preserving transforms")
    lines.append("")
    for transform, doc in TRANSFORM_DOCS.items():
        lines.append(f"- `{transform.value}`: {doc}")
    lines.append("")
    return "\n".join(lines)
