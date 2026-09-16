"""Deterministic probe draft generation from snapshots (#98).

Drafts are always ``approved: false`` — humans must review before model-backed use.
Optional LLM enrichment is not enabled by default; when added later it must keep
the same approval gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from tool_semantics.diff import _jaccard, _token_set
from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract
from tool_semantics.probes import Probe, ProbeKind


def _slug(name: str) -> str:
    return name.replace("_", "-").lower()


def _intent_for_tool(tool: ToolContract) -> str:
    desc = tool.description.strip()
    if desc:
        # Use description as a human-readable intent seed (still requires review).
        first = desc.split(".")[0].strip()
        if first:
            return first[0].lower() + first[1:] if first[0].isupper() else first
    return f"Use the '{tool.name}' tool appropriately"


def _required_params(tool: ToolContract) -> list[str]:
    return [parameter.name for parameter in tool.parameters if parameter.required]


def _positive_probe(tool: ToolContract) -> Probe:
    requires_confirmation = tool.risk in {
        RiskLevel.EXTERNAL_WRITE,
        RiskLevel.DESTRUCTIVE,
    }
    return Probe(
        id=f"draft-positive-{_slug(tool.name)}",
        intent=_intent_for_tool(tool),
        kind=ProbeKind.POSITIVE,
        expected_tool=tool.name,
        required_params=_required_params(tool),
        max_risk=tool.risk.value,
        requires_confirmation=requires_confirmation,
        approved=False,
    )


def _negative_probes(tools: list[ToolContract]) -> list[Probe]:
    """One negative draft per high-risk tool (must not be selected for a safe intent)."""
    drafts: list[Probe] = []
    risky = [
        tool for tool in tools if tool.risk in {RiskLevel.DESTRUCTIVE, RiskLevel.EXTERNAL_WRITE}
    ]
    for tool in risky:
        drafts.append(
            Probe(
                id=f"draft-negative-{_slug(tool.name)}",
                intent=(f"Complete a read-only inspection task without calling '{tool.name}'"),
                kind=ProbeKind.NEGATIVE,
                forbidden_tools=[tool.name],
                approved=False,
            )
        )
    # If no risky tools, still emit a placeholder negative for a missing dangerous name.
    if not drafts and tools:
        drafts.append(
            Probe(
                id="draft-negative-no-delete",
                intent="Must not expose a destructive delete tool",
                kind=ProbeKind.NEGATIVE,
                forbidden_tools=["delete_repository"],
                approved=False,
            )
        )
    return drafts


def _ambiguous_probes(tools: list[ToolContract], *, threshold: float = 0.45) -> list[Probe]:
    drafts: list[Probe] = []
    for index, left in enumerate(tools):
        left_tokens = _token_set(f"{left.name.replace('_', ' ')} {left.description}")
        for right in tools[index + 1 :]:
            right_tokens = _token_set(f"{right.name.replace('_', ' ')} {right.description}")
            score = _jaccard(left_tokens, right_tokens)
            if score < threshold:
                continue
            drafts.append(
                Probe(
                    id=f"draft-ambiguous-{_slug(left.name)}-vs-{_slug(right.name)}",
                    intent=_intent_for_tool(left),
                    kind=ProbeKind.AMBIGUOUS,
                    expected_tool=left.name,
                    required_params=_required_params(left),
                    approved=False,
                )
            )
            # One draft per left tool is enough for a starting suite.
            break
    return drafts


def generate_probe_drafts(
    snapshot: InterfaceSnapshot,
    *,
    include_negative: bool = True,
    include_ambiguous: bool = True,
) -> list[Probe]:
    """Build deterministic probe drafts. Every draft has ``approved=False``."""
    tools = list(snapshot.tools)
    drafts: list[Probe] = [_positive_probe(tool) for tool in tools]
    if include_negative:
        drafts.extend(_negative_probes(tools))
    if include_ambiguous:
        drafts.extend(_ambiguous_probes(tools))
    return drafts


def probes_to_json_document(probes: list[Probe]) -> dict[str, Any]:
    return {
        "probes": [probe.model_dump(mode="json") for probe in probes],
        "_meta": {
            "generated_by": "tool-semantics generate-probes",
            "approved_default": False,
            "note": (
                "Draft probes only. Review intents and expectations, then set "
                "approved=true before model-backed runs."
            ),
        },
    }


def probes_to_yaml_text(probes: list[Probe]) -> str:
    """Serialize drafts as YAML (requires PyYAML)."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise ValueError("PyYAML is required to write YAML probe drafts") from exc
    payload = probes_to_json_document(probes)
    # Prefer block style for reviewability.
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def write_probe_drafts(
    probes: list[Probe],
    output: Path,
    *,
    fmt: Literal["json", "yaml"] | None = None,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    resolved = fmt
    if resolved is None:
        suffix = output.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            resolved = "yaml"
        else:
            resolved = "json"
    if resolved == "yaml":
        output.write_text(probes_to_yaml_text(probes), encoding="utf-8")
    else:
        output.write_text(
            json.dumps(probes_to_json_document(probes), indent=2) + "\n", encoding="utf-8"
        )
