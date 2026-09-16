"""Mutation generator and precision/recall detection metrics (#93).

Inject controlled regressions into snapshots and measure whether compare
(or metadata checks for capability drop) detects the expected findings.
"""

from __future__ import annotations

import copy
import json
import random
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from tool_semantics.diff import CompatibilityReport, Severity, compare_snapshots
from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract, ToolParameter
from tool_semantics.scanner import read_snapshot, write_snapshot


class MutationKind(StrEnum):
    RENAME = "rename"
    REMOVE_TOOL = "remove_tool"
    ADD_REQUIRED_PARAM = "add_required_param"
    CONFUSING_TWIN = "confusing_twin"
    RISK_ESCALATION = "risk_escalation"
    CAPABILITY_DROP = "capability_drop"


# Fixed-seed CI subset (all operators).
CI_MUTATION_KINDS: tuple[MutationKind, ...] = tuple(MutationKind)


class MutationSpec(BaseModel):
    kind: MutationKind
    tool: str | None = None
    new_name: str | None = None
    parameter: str | None = None
    seed: int = 0


class MutationResult(BaseModel):
    kind: MutationKind
    baseline: InterfaceSnapshot
    mutated: InterfaceSnapshot
    expected_codes: list[str] = Field(default_factory=list)
    expected_subjects: list[str] = Field(default_factory=list)
    notes: str = ""
    # For capability_drop: key removed from server_capabilities.
    dropped_capability: str | None = None


class DetectionCaseResult(BaseModel):
    case_id: str
    kind: str
    detected: bool
    expected_codes: list[str] = Field(default_factory=list)
    observed_codes: list[str] = Field(default_factory=list)
    missed_codes: list[str] = Field(default_factory=list)
    false_positive_codes: list[str] = Field(default_factory=list)
    message: str = ""


class DetectionMetrics(BaseModel):
    cases: int = 0
    detected: int = 0
    missed: int = 0
    false_positives: int = 0
    precision: float | None = None
    recall: float | None = None
    detection_rate: float | None = None
    case_results: list[DetectionCaseResult] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.missed == 0


def _rng(seed: int) -> random.Random:
    return random.Random(seed)


def _pick_tool(snapshot: InterfaceSnapshot, name: str | None, rng: random.Random) -> ToolContract:
    if not snapshot.tools:
        raise ValueError("Snapshot has no tools to mutate")
    if name:
        for tool in snapshot.tools:
            if tool.name == name:
                return tool
        raise ValueError(f"Tool not found: {name}")
    return rng.choice(list(snapshot.tools))


def _clone(snapshot: InterfaceSnapshot) -> InterfaceSnapshot:
    return InterfaceSnapshot.model_validate(snapshot.model_dump(mode="python"))


def apply_mutation(snapshot: InterfaceSnapshot, spec: MutationSpec) -> MutationResult:
    """Apply a named mutation operator; return baseline/mutated + expected findings."""
    rng = _rng(spec.seed)
    baseline = _clone(snapshot)
    mutated = _clone(snapshot)
    tool = _pick_tool(mutated, spec.tool, rng)
    expected_codes: list[str] = []
    expected_subjects: list[str] = []
    notes = ""
    dropped_capability: str | None = None

    if spec.kind == MutationKind.RENAME:
        new_name = spec.new_name or f"{tool.name}_v2"
        if any(item.name == new_name for item in mutated.tools):
            new_name = f"{new_name}_{spec.seed}"
        old_name = tool.name
        tools = [
            item.model_copy(update={"name": new_name}) if item.name == old_name else item
            for item in mutated.tools
        ]
        mutated = mutated.model_copy(update={"tools": tools})
        expected_codes = ["tool.renamed"]
        expected_subjects = [f"{old_name}->{new_name}"]
        notes = f"Renamed {old_name} → {new_name}"

    elif spec.kind == MutationKind.REMOVE_TOOL:
        mutated = mutated.model_copy(
            update={"tools": [item for item in mutated.tools if item.name != tool.name]}
        )
        expected_codes = ["tool.removed"]
        expected_subjects = [tool.name]
        notes = f"Removed tool {tool.name}"

    elif spec.kind == MutationKind.ADD_REQUIRED_PARAM:
        param_name = spec.parameter or "mut_required"
        updated: list[ToolContract] = []
        for item in mutated.tools:
            if item.name != tool.name:
                updated.append(item)
                continue
            params = list(item.parameters)
            if any(param.name == param_name for param in params):
                param_name = f"{param_name}_{spec.seed}"
            params.append(
                ToolParameter(
                    name=param_name,
                    schema={"type": "string"},
                    required=True,
                    description="Mutation-injected required parameter",
                )
            )
            updated.append(item.model_copy(update={"parameters": params}))
        mutated = mutated.model_copy(update={"tools": updated})
        expected_codes = ["parameter.added_required"]
        expected_subjects = [f"{tool.name}.{param_name}"]
        notes = f"Added required param {tool.name}.{param_name}"

    elif spec.kind == MutationKind.CONFUSING_TWIN:
        twin_name = spec.new_name or f"{tool.name}_similar"
        twin = tool.model_copy(
            update={
                "name": twin_name,
                "description": tool.description or f"Similar to {tool.name}",
            }
        )
        mutated = mutated.model_copy(update={"tools": list(mutated.tools) + [twin]})
        expected_codes = ["tool.added"]
        expected_subjects = [twin_name]
        notes = f"Added confusing twin {twin_name}"

    elif spec.kind == MutationKind.RISK_ESCALATION:
        target = tool
        if target.risk == RiskLevel.DESTRUCTIVE:
            candidates = [item for item in mutated.tools if item.risk != RiskLevel.DESTRUCTIVE]
            if not candidates:
                raise ValueError("No non-destructive tool available for risk escalation")
            target = rng.choice(candidates)
        tools = [
            item.model_copy(update={"risk": RiskLevel.DESTRUCTIVE})
            if item.name == target.name
            else item
            for item in mutated.tools
        ]
        mutated = mutated.model_copy(update={"tools": tools})
        expected_codes = ["tool.risk_changed"]
        expected_subjects = [target.name]
        notes = f"Escalated risk on {target.name} → destructive"

    elif spec.kind == MutationKind.CAPABILITY_DROP:
        # Ensure both sides have server_capabilities; drop one key on the candidate.
        base_meta = copy.deepcopy(baseline.metadata)
        caps = base_meta.get("server_capabilities")
        if not isinstance(caps, dict) or not caps:
            caps = {"tools": {}, "prompts": {}, "resources": {}}
            base_meta["server_capabilities"] = caps
            baseline = baseline.model_copy(update={"metadata": base_meta})
        drop_key = "prompts" if "prompts" in caps else next(iter(caps))
        mut_meta = copy.deepcopy(baseline.metadata)
        mut_caps = dict(mut_meta.get("server_capabilities") or {})
        mut_caps.pop(drop_key, None)
        mut_meta["server_capabilities"] = mut_caps
        mutated = mutated.model_copy(update={"metadata": mut_meta})
        dropped_capability = drop_key
        # Detected via metadata check (protocol capability diffs may land separately).
        expected_codes = ["capability.removed"]
        expected_subjects = [drop_key]
        notes = f"Dropped server capability '{drop_key}'"

    else:
        raise ValueError(f"Unknown mutation kind: {spec.kind}")

    return MutationResult(
        kind=spec.kind,
        baseline=baseline,
        mutated=mutated,
        expected_codes=expected_codes,
        expected_subjects=expected_subjects,
        notes=notes,
        dropped_capability=dropped_capability,
    )


def _codes(report: CompatibilityReport) -> set[str]:
    return {change.code for change in report.changes}


def evaluate_detection(
    case_id: str,
    mutation: MutationResult,
    *,
    detect_renames: bool = True,
) -> DetectionCaseResult:
    if mutation.kind == MutationKind.CAPABILITY_DROP:
        base_caps = mutation.baseline.metadata.get("server_capabilities") or {}
        cand_caps = mutation.mutated.metadata.get("server_capabilities") or {}
        base_keys = set(base_caps) if isinstance(base_caps, dict) else set()
        cand_keys = set(cand_caps) if isinstance(cand_caps, dict) else set()
        dropped = base_keys - cand_keys
        detected = bool(mutation.dropped_capability and mutation.dropped_capability in dropped)
        observed_codes = ["capability.removed"] if detected else []
        missed = [] if detected else list(mutation.expected_codes)
        return DetectionCaseResult(
            case_id=case_id,
            kind=mutation.kind.value,
            detected=detected,
            expected_codes=mutation.expected_codes,
            observed_codes=observed_codes,
            missed_codes=missed,
            false_positive_codes=[],
            message=mutation.notes,
        )

    report = compare_snapshots(
        mutation.baseline,
        mutation.mutated,
        detect_renames=detect_renames,
    )
    observed = _codes(report)
    expected = set(mutation.expected_codes)
    detected = bool(expected & observed)
    if mutation.kind == MutationKind.RENAME and not detected:
        if "tool.removed" in observed and "tool.added" in observed:
            detected = True

    missed = sorted(expected - observed) if not detected else []
    expected_family = set(mutation.expected_codes)
    if mutation.kind == MutationKind.RENAME:
        expected_family |= {"tool.removed", "tool.added", "tool.renamed"}
    # Parameter diffs often accompany rename when comparing tool pairs — allow those.
    if mutation.kind == MutationKind.RENAME:
        expected_family |= {code for code in observed if code.startswith("parameter.")}
    fps = sorted(
        {
            change.code
            for change in report.changes
            if change.severity in {Severity.BREAKING, Severity.CRITICAL}
            and change.code not in expected_family
        }
    )

    return DetectionCaseResult(
        case_id=case_id,
        kind=mutation.kind.value,
        detected=detected,
        expected_codes=mutation.expected_codes,
        observed_codes=sorted(observed),
        missed_codes=missed,
        false_positive_codes=fps,
        message=mutation.notes,
    )


def compute_detection_metrics(results: list[DetectionCaseResult]) -> DetectionMetrics:
    cases = len(results)
    detected = sum(1 for item in results if item.detected)
    missed = sum(1 for item in results if not item.detected)
    false_positives = sum(1 for item in results if item.false_positive_codes)
    denom_p = detected + false_positives
    precision = (detected / denom_p) if denom_p else None
    recall = (detected / cases) if cases else None
    return DetectionMetrics(
        cases=cases,
        detected=detected,
        missed=missed,
        false_positives=false_positives,
        precision=round(precision, 4) if precision is not None else None,
        recall=round(recall, 4) if recall is not None else None,
        detection_rate=round(recall, 4) if recall is not None else None,
        case_results=results,
    )


def run_seeded_mutations(
    snapshot: InterfaceSnapshot,
    *,
    seed: int = 0,
    kinds: list[MutationKind] | None = None,
) -> DetectionMetrics:
    """CI-friendly fixed-seed subset covering each operator once."""
    selected = kinds or list(CI_MUTATION_KINDS)
    results: list[DetectionCaseResult] = []
    for index, kind in enumerate(selected):
        spec = MutationSpec(kind=kind, seed=seed + index)
        try:
            mutation = apply_mutation(snapshot, spec)
        except ValueError as exc:
            results.append(
                DetectionCaseResult(
                    case_id=f"{kind.value}-{seed + index}",
                    kind=kind.value,
                    detected=False,
                    missed_codes=[kind.value],
                    message=str(exc),
                )
            )
            continue
        results.append(evaluate_detection(f"{kind.value}-{seed + index}", mutation))
    return compute_detection_metrics(results)


def write_mutation_case(
    output_dir: Path,
    mutation: MutationResult,
    *,
    case_id: str,
) -> None:
    """Write before/after/expected finding folder for the regression corpus."""
    output_dir.mkdir(parents=True, exist_ok=True)
    write_snapshot(mutation.baseline, output_dir / "before.json")
    write_snapshot(mutation.mutated, output_dir / "after.json")
    expected = {
        "case_id": case_id,
        "kind": mutation.kind.value,
        "expected_codes": mutation.expected_codes,
        "expected_subjects": mutation.expected_subjects,
        "notes": mutation.notes,
        "dropped_capability": mutation.dropped_capability,
    }
    (output_dir / "expected-finding.json").write_text(
        json.dumps(expected, indent=2) + "\n",
        encoding="utf-8",
    )


def load_and_evaluate_case(case_dir: Path) -> DetectionCaseResult:
    expected = json.loads((case_dir / "expected-finding.json").read_text(encoding="utf-8"))
    baseline = read_snapshot(case_dir / "before.json")
    mutated = read_snapshot(case_dir / "after.json")
    mutation = MutationResult(
        kind=MutationKind(expected["kind"]),
        baseline=baseline,
        mutated=mutated,
        expected_codes=list(expected.get("expected_codes") or []),
        expected_subjects=list(expected.get("expected_subjects") or []),
        notes=str(expected.get("notes") or ""),
        dropped_capability=expected.get("dropped_capability"),
    )
    return evaluate_detection(str(expected.get("case_id") or case_dir.name), mutation)


def discover_mutation_cases(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [
        child
        for child in sorted(root.iterdir())
        if child.is_dir() and (child / "expected-finding.json").is_file()
    ]


def run_mutation_corpus(root: Path) -> DetectionMetrics:
    results = [load_and_evaluate_case(path) for path in discover_mutation_cases(root)]
    return compute_detection_metrics(results)


def render_detection_metrics_markdown(metrics: DetectionMetrics) -> str:
    lines = [
        "## Mutation detection metrics",
        "",
        f"- Cases: {metrics.cases}",
        f"- Detected: {metrics.detected}",
        f"- Missed: {metrics.missed}",
        f"- False-positive cases: {metrics.false_positives}",
        f"- Precision: {metrics.precision if metrics.precision is not None else 'n/a'}",
        f"- Recall / detection rate: {metrics.recall if metrics.recall is not None else 'n/a'}",
        "",
        "| Case | Kind | Detected | Missed | FP codes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in metrics.case_results:
        missed = ", ".join(f"`{code}`" for code in item.missed_codes) or "—"
        fps = ", ".join(f"`{code}`" for code in item.false_positive_codes) or "—"
        lines.append(
            f"| `{item.case_id}` | `{item.kind}` | "
            f"{'yes' if item.detected else 'no'} | {missed} | {fps} |"
        )
    lines.append("")
    return "\n".join(lines)
