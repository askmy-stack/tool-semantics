"""Suggest reviewable MigrationAdapter drafts from compatibility diffs (#62).

Suggestions are never applied automatically — emit JSON/YAML for human review.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from tool_semantics.adapters import (
    ArgumentMap,
    EnumMap,
    MigrationAdapter,
    ToolAlias,
)
from tool_semantics.diff import (
    CompatibilityReport,
    _detect_renames,
    _jaccard,
    _token_set,
    _tool_similarity,
    compare_snapshots,
)
from tool_semantics.models import InterfaceSnapshot, ToolContract, ToolParameter


class SuggestionConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    SKIPPED = "skipped"


class SuggestionNote(BaseModel):
    """Why a mapping was included or skipped."""

    subject: str
    confidence: SuggestionConfidence
    message: str


class AdapterSuggestion(BaseModel):
    """Reviewable adapter draft plus confidence notes (never auto-applied)."""

    adapter: MigrationAdapter = Field(default_factory=MigrationAdapter)
    notes: list[SuggestionNote] = Field(default_factory=list)
    baseline: str = ""
    candidate: str = ""
    auto_apply: bool = False  # Always false; CI must not apply without explicit opt-in.


def _param_similarity(left: str, right: str) -> float:
    token = _jaccard(_token_set(left.replace("_", " ")), _token_set(right.replace("_", " ")))
    seq = SequenceMatcher(None, left.lower(), right.lower()).ratio()
    return max(token, seq)


def _enum_values(parameter: ToolParameter) -> set[str] | None:
    values = parameter.schema_.get("enum")
    if values is None or not isinstance(values, list):
        return None
    return {str(value) for value in values}


def _suggest_argument_renames(
    old_tool: ToolContract,
    new_tool: ToolContract,
    *,
    threshold: float = 0.5,
) -> tuple[dict[str, str], list[SuggestionNote]]:
    old_only = {p.name: p for p in old_tool.parameters}
    new_only = {p.name: p for p in new_tool.parameters}
    shared = old_only.keys() & new_only.keys()
    removed = {name: old_only[name] for name in old_only.keys() - shared}
    added = {name: new_only[name] for name in new_only.keys() - shared}
    pairs: list[tuple[float, str, str]] = []
    for old_name, old_param in removed.items():
        for new_name, new_param in added.items():
            score = _param_similarity(old_name, new_name)
            # Slight boost when both are required or both optional.
            if old_param.required == new_param.required:
                score = min(1.0, score + 0.05)
            if old_param.schema_.get("type") == new_param.schema_.get("type"):
                score = min(1.0, score + 0.05)
            if score >= threshold:
                pairs.append((score, old_name, new_name))
    # Equal cardinality with no high-score pairs: greedy unique pairing.
    if not pairs and len(removed) == len(added) and removed:
        candidates: list[tuple[float, str, str]] = []
        for old_name in removed:
            for new_name in added:
                score = max(_param_similarity(old_name, new_name), 0.45)
                candidates.append((score, old_name, new_name))
        candidates.sort(reverse=True)
        used_old: set[str] = set()
        used_new: set[str] = set()
        for score, old_name, new_name in candidates:
            if old_name in used_old or new_name in used_new:
                continue
            used_old.add(old_name)
            used_new.add(new_name)
            pairs.append((score, old_name, new_name))
    pairs.sort(reverse=True)
    matched_old: set[str] = set()
    matched_new: set[str] = set()
    renames: dict[str, str] = {}
    notes: list[SuggestionNote] = []
    for score, old_name, new_name in pairs:
        if old_name in matched_old or new_name in matched_new:
            continue
        matched_old.add(old_name)
        matched_new.add(new_name)
        renames[old_name] = new_name
        confidence = (
            SuggestionConfidence.HIGH
            if score >= 0.75
            else SuggestionConfidence.MEDIUM
            if score >= 0.55
            else SuggestionConfidence.LOW
        )
        notes.append(
            SuggestionNote(
                subject=f"{old_tool.name}.{old_name}->{new_tool.name}.{new_name}",
                confidence=confidence,
                message=f"Parameter rename suggested (similarity={score:.2f}).",
            )
        )
    # Sole leftover remove+add: low-confidence pairing.
    leftover_old = sorted(removed.keys() - matched_old)
    leftover_new = sorted(added.keys() - matched_new)
    if len(leftover_old) == 1 and len(leftover_new) == 1:
        old_name, new_name = leftover_old[0], leftover_new[0]
        renames[old_name] = new_name
        matched_old.add(old_name)
        matched_new.add(new_name)
        notes.append(
            SuggestionNote(
                subject=f"{old_tool.name}.{old_name}->{new_tool.name}.{new_name}",
                confidence=SuggestionConfidence.LOW,
                message="Parameter rename suggested as sole leftover remove+add pair.",
            )
        )
    for old_name in sorted(removed.keys() - matched_old):
        notes.append(
            SuggestionNote(
                subject=f"{old_tool.name}.{old_name}",
                confidence=SuggestionConfidence.SKIPPED,
                message="Removed parameter has no unambiguous rename target; skipped.",
            )
        )
    return renames, notes


def _suggest_enum_map(
    tool_name: str,
    old_param: ToolParameter,
    new_param: ToolParameter,
) -> tuple[dict[str, str] | None, SuggestionNote]:
    old_vals = _enum_values(old_param)
    new_vals = _enum_values(new_param)
    if old_vals is None or new_vals is None:
        return None, SuggestionNote(
            subject=f"{tool_name}.{new_param.name}",
            confidence=SuggestionConfidence.SKIPPED,
            message="Enum remap skipped (one side is not an enum).",
        )
    # Identity overlap only when names match exactly — unambiguous.
    identity = old_vals & new_vals
    if identity == old_vals == new_vals:
        return None, SuggestionNote(
            subject=f"{tool_name}.{new_param.name}",
            confidence=SuggestionConfidence.SKIPPED,
            message="Enum values unchanged; no remap needed.",
        )
    # Unambiguous 1:1 only when equal cardinality and each old value has a
    # unique best match above threshold with no ties.
    if len(old_vals) != len(new_vals) or not old_vals:
        return None, SuggestionNote(
            subject=f"{tool_name}.{new_param.name}",
            confidence=SuggestionConfidence.SKIPPED,
            message=(
                "Enum remap skipped (cardinality differs or empty); human authoring required."
            ),
        )
    mapping: dict[str, str] = {}
    used_new: set[str] = set()
    for old in sorted(old_vals):
        ranked = sorted(
            (
                (_jaccard(_token_set(old), _token_set(new)), new)
                for new in new_vals
                if new not in used_new
            ),
            reverse=True,
        )
        if not ranked or ranked[0][0] < 0.5:
            return None, SuggestionNote(
                subject=f"{tool_name}.{new_param.name}",
                confidence=SuggestionConfidence.SKIPPED,
                message=f"No unambiguous enum target for '{old}'; skipped.",
            )
        if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
            return None, SuggestionNote(
                subject=f"{tool_name}.{new_param.name}",
                confidence=SuggestionConfidence.SKIPPED,
                message=f"Tied enum targets for '{old}'; skipped.",
            )
        mapping[old] = ranked[0][1]
        used_new.add(ranked[0][1])
    return mapping, SuggestionNote(
        subject=f"{tool_name}.{new_param.name}",
        confidence=SuggestionConfidence.MEDIUM,
        message="Enum value remap suggested from token similarity; review before use.",
    )


def suggest_adapter(
    baseline: InterfaceSnapshot,
    candidate: InterfaceSnapshot,
    *,
    report: CompatibilityReport | None = None,
    rename_threshold: float = 0.55,
    suggestion_rename_threshold: float = 0.4,
) -> AdapterSuggestion:
    """Build a reviewable MigrationAdapter draft from baseline/candidate snapshots.

    Uses ``tool.renamed`` when present; may also propose aliases for remaining
    remove+add pairs above ``suggestion_rename_threshold`` (marked low/medium
    confidence). Parameter and enum maps are only emitted when unambiguous.
    """
    report = report or compare_snapshots(baseline, candidate, detect_renames=True)
    before = {tool.name: tool for tool in baseline.tools}
    after = {tool.name: tool for tool in candidate.tools}
    notes: list[SuggestionNote] = []
    aliases: list[ToolAlias] = []
    arguments: list[ArgumentMap] = []
    enums: list[EnumMap] = []

    renamed_pairs: list[tuple[str, str]] = []
    for change in report.changes:
        if change.code == "tool.renamed" and "->" in change.subject:
            old_name, new_name = change.subject.split("->", 1)
            renamed_pairs.append((old_name, new_name))
            aliases.append(ToolAlias(**{"from": old_name, "to": new_name}))
            notes.append(
                SuggestionNote(
                    subject=change.subject,
                    confidence=SuggestionConfidence.HIGH,
                    message="Alias from diff engine tool.renamed.",
                )
            )

    renamed_from = {old for old, _ in renamed_pairs}
    renamed_to = {new for _, new in renamed_pairs}
    remaining_removed = {
        name: before[name] for name in before.keys() - after.keys() - renamed_from if name in before
    }
    remaining_added = {
        name: after[name] for name in after.keys() - before.keys() - renamed_to if name in after
    }
    if remaining_removed and remaining_added:
        extra = _detect_renames(
            remaining_removed,
            remaining_added,
            threshold=suggestion_rename_threshold,
        )
        # Sole remove+add of matching risk: low-confidence alias even when
        # token similarity is weak (common intentional rename pattern).
        if not extra and len(remaining_removed) == 1 and len(remaining_added) == 1:
            old_name = next(iter(remaining_removed))
            new_name = next(iter(remaining_added))
            if remaining_removed[old_name].risk == remaining_added[new_name].risk:
                extra = [(old_name, new_name)]
        for old_name, new_name in extra:
            score = _tool_similarity(before[old_name], after[new_name])
            if (
                score <= 0.0
                and (old_name, new_name)
                in [(next(iter(remaining_removed)), next(iter(remaining_added)))]
                and len(remaining_removed) == 1
            ):
                confidence = SuggestionConfidence.LOW
                detail = (
                    "Alias suggested as sole remove+add pair with matching risk; "
                    "similarity was low — review carefully."
                )
            else:
                confidence = (
                    SuggestionConfidence.HIGH
                    if score >= rename_threshold
                    else SuggestionConfidence.MEDIUM
                    if score >= suggestion_rename_threshold
                    else SuggestionConfidence.LOW
                )
                detail = (
                    f"Alias suggested from remove+add similarity ({score:.2f}); "
                    "not emitted as tool.renamed in the structural report."
                )
            aliases.append(ToolAlias(**{"from": old_name, "to": new_name}))
            renamed_pairs.append((old_name, new_name))
            notes.append(
                SuggestionNote(
                    subject=f"{old_name}->{new_name}",
                    confidence=confidence,
                    message=detail,
                )
            )

    # Parameter / enum maps for renamed pairs and same-name tools.
    pairs_to_inspect: list[tuple[str, ToolContract, ToolContract]] = []
    for old_name, new_name in renamed_pairs:
        if old_name in before and new_name in after:
            pairs_to_inspect.append((new_name, before[old_name], after[new_name]))
    for name in sorted(before.keys() & after.keys()):
        pairs_to_inspect.append((name, before[name], after[name]))

    for target_name, old_tool, new_tool in pairs_to_inspect:
        renames, rename_notes = _suggest_argument_renames(old_tool, new_tool)
        notes.extend(rename_notes)
        if renames:
            arguments.append(ArgumentMap(tool=target_name, rename=renames))
        # Enum maps on shared or renamed parameters.
        old_params = {p.name: p for p in old_tool.parameters}
        new_params = {p.name: p for p in new_tool.parameters}
        for old_name, new_name in renames.items():
            if old_name in old_params and new_name in new_params:
                mapping, note = _suggest_enum_map(
                    target_name, old_params[old_name], new_params[new_name]
                )
                notes.append(note)
                if mapping:
                    enums.append(EnumMap(tool=target_name, parameter=new_name, values=mapping))
        for shared in old_params.keys() & new_params.keys():
            mapping, note = _suggest_enum_map(target_name, old_params[shared], new_params[shared])
            notes.append(note)
            if mapping:
                enums.append(EnumMap(tool=target_name, parameter=shared, values=mapping))

    # Document non-goals / skips for required-param adds without defaults.
    for change in report.changes:
        if change.code == "parameter.added_required":
            notes.append(
                SuggestionNote(
                    subject=change.subject,
                    confidence=SuggestionConfidence.SKIPPED,
                    message=(
                        "Required parameter added — no safe default; adapter suggestion skipped."
                    ),
                )
            )

    return AdapterSuggestion(
        adapter=MigrationAdapter(aliases=aliases, arguments=arguments, enums=enums),
        notes=notes,
        baseline=report.baseline,
        candidate=report.candidate,
        auto_apply=False,
    )


def adapter_suggestion_to_json(suggestion: AdapterSuggestion) -> dict[str, Any]:
    """Serialize suggestion for disk (adapter + notes; auto_apply always false)."""
    return suggestion.model_dump(mode="json", by_alias=True)
