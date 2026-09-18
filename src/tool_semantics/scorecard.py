"""Compatibility scorecard and human-readable change explanations (#77)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from tool_semantics.diff import Change, CompatibilityReport, Severity

# Soft / selection-drift codes (deterministic structural warnings).
SEMANTIC_CODES = frozenset(
    {
        "tool.description_changed",
        "tool.renamed",
        "parameter.default_changed",
        "parameter.constraints_tightened",
    }
)
SAFETY_CODES = frozenset({"tool.risk_changed"})
BEHAVIOR_PREFIX = "behavior."

_WHY: dict[str, str] = {
    "tool.removed": "Agents that previously selected this tool will fail or choose a substitute.",
    "tool.added": "New tools can collide with existing descriptions and steal selection.",
    "tool.description_changed": "Models often re-route based on description text alone.",
    "tool.renamed": "Cached workflows and prompts may still use the old name.",
    "tool.risk_changed": "Side-effect / confirmation expectations may no longer match policy.",
    "tool.output_schema_removed": "Downstream parsers expecting structured output will break.",
    "tool.output_schema_changed": "Structured-output consumers may reject or misread results.",
    "parameter.removed": "Calls that still send the old parameter may error or drop data.",
    "parameter.added_required": "Prior argument patterns omit the new required field.",
    "parameter.became_required": "Previously optional omissions become hard failures.",
    "parameter.type_narrowed": "Wider values the model used to emit become invalid.",
    "parameter.type_changed": "Argument shapes agents learned no longer validate.",
    "parameter.schema_changed": "Schema constraints agents relied on have shifted.",
    "parameter.enum_values_removed": "Models may keep emitting removed enum values.",
    "protocol.version_changed": "Clients negotiating the old protocol version may fail initialize.",
    "transport.changed": "Connection setup / URL shape may need client updates.",
    "capability.removed": "Dependent MCP features (prompts/resources/tools) become unavailable.",
    "capability.changed": "Capability options (e.g. listChanged) may no longer match clients.",
    "behavior.tool_selection_failed": "The model no longer picks the intended tool.",
    "behavior.arguments_invalid": "Even with the right tool, arguments fail validation.",
    "behavior.unstable_probe": "Repeated runs disagree — reliability is too low to ship.",
    "behavior.deterministic_failure": "Every trial fails the same way — a hard regression.",
    "behavior.risk_expectation_failed": "The model chose a tool riskier than the probe allows.",
}

_FIX: dict[str, str] = {
    "tool.removed": "Restore the tool, add an adapter/alias, or update agent prompts and probes.",
    "tool.added": "Differentiate descriptions; add collision probes before relying on selection.",
    "tool.description_changed": "Keep selection-critical phrasing stable or refresh probes.",
    "tool.renamed": "Publish a migration adapter mapping old→new names; update baselines.",
    "tool.risk_changed": "Confirm the new risk is intentional; require confirmation if escalating.",
    "tool.output_schema_removed": "Keep outputSchema or update consumers to untyped content.",
    "tool.output_schema_changed": "Version the schema or adapt downstream parsers.",
    "parameter.removed": "Keep the parameter deprecated or translate args in an adapter.",
    "parameter.added_required": "Provide a default, make it optional, or teach agents the new arg.",
    "parameter.became_required": "Supply a default or update all callers/probes.",
    "parameter.type_narrowed": "Widen the type again or coerce in an adapter.",
    "parameter.type_changed": "Document the new type and update argument fixtures.",
    "parameter.schema_changed": "Review constraint deltas; update expected_arguments probes.",
    "parameter.enum_values_removed": "Keep legacy values or map them in an adapter.",
    "protocol.version_changed": "Align client and server protocol generations before cutting over.",
    "transport.changed": "Update capture/client config for the new transport.",
    "capability.removed": "Restore the capability or gate features that depend on it.",
    "capability.changed": "Verify clients tolerate the new capability object.",
    "behavior.tool_selection_failed": "Tighten descriptions, reduce collisions, or adjust probes.",
    "behavior.arguments_invalid": "Fix schema/examples or expected_arguments on the probe.",
    "behavior.unstable_probe": "Improve determinism (seed/temperature) or clarify the catalog.",
    "behavior.deterministic_failure": "Fix the underlying tool/schema regression before release.",
    "behavior.risk_expectation_failed": "Lower tool risk or raise the probe max_risk.",
}


class DimensionName(StrEnum):
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    BEHAVIORAL = "behavioral"
    SAFETY = "safety"
    STABILITY = "stability"


class DimensionStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    NA = "n/a"


class EvidenceLabel(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    MODEL_BASED = "MODEL-BASED"
    MIXED = "MIXED"
    NA = "N/A"


@dataclass
class DimensionScore:
    name: DimensionName
    status: DimensionStatus
    score: float | None  # None means N/A — never coerce missing behavioral data to 0%
    finding_count: int = 0
    breaking_count: int = 0
    warning_count: int = 0
    evidence: EvidenceLabel = EvidenceLabel.NA
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name.value,
            "status": self.status.value,
            "score": self.score,
            "finding_count": self.finding_count,
            "breaking_count": self.breaking_count,
            "warning_count": self.warning_count,
            "evidence": self.evidence.value,
            "note": self.note,
        }


@dataclass
class FindingExplanation:
    code: str
    subject: str
    severity: str
    what_changed: str
    why_it_matters: str
    remediation: str
    evidence: EvidenceLabel

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "subject": self.subject,
            "severity": self.severity,
            "what_changed": self.what_changed,
            "why_it_matters": self.why_it_matters,
            "remediation": self.remediation,
            "evidence": self.evidence.value,
        }


@dataclass
class CompatibilityScorecard:
    dimensions: list[DimensionScore] = field(default_factory=list)
    explanations: list[FindingExplanation] = field(default_factory=list)
    final_result: str = "PASS"
    forced_fail: bool = False
    forced_fail_reason: str | None = None
    counts: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "final_result": self.final_result,
            "forced_fail": self.forced_fail,
            "forced_fail_reason": self.forced_fail_reason,
            "counts": self.counts,
            "dimensions": [item.to_json() for item in self.dimensions],
            "explanations": [item.to_json() for item in self.explanations],
        }


def _partition(change: Change) -> DimensionName:
    if change.code.startswith(BEHAVIOR_PREFIX):
        if change.code in {
            "behavior.unstable_probe",
            "behavior.deterministic_failure",
        }:
            return DimensionName.STABILITY
        return DimensionName.BEHAVIORAL
    if change.code in SAFETY_CODES:
        return DimensionName.SAFETY
    if change.code in SEMANTIC_CODES:
        return DimensionName.SEMANTIC
    return DimensionName.STRUCTURAL


def _evidence_for_code(code: str) -> EvidenceLabel:
    if code.startswith(BEHAVIOR_PREFIX):
        return EvidenceLabel.MODEL_BASED
    return EvidenceLabel.DETERMINISTIC


def explain_change(change: Change) -> FindingExplanation:
    why = _WHY.get(
        change.code,
        "This interface change may affect agent tool selection or execution.",
    )
    fix = _FIX.get(
        change.code,
        "Review the diff, update baselines/probes, or add a migration adapter.",
    )
    return FindingExplanation(
        code=change.code,
        subject=change.subject,
        severity=change.severity.value,
        what_changed=change.message,
        why_it_matters=why,
        remediation=fix,
        evidence=_evidence_for_code(change.code),
    )


def _score_dimension(
    name: DimensionName,
    changes: list[Change],
    *,
    ran: bool,
    evidence: EvidenceLabel,
    empty_note: str,
) -> DimensionScore:
    if not ran:
        return DimensionScore(
            name=name,
            status=DimensionStatus.NA,
            score=None,
            evidence=EvidenceLabel.NA,
            note=empty_note,
        )
    breaking = sum(
        1 for change in changes if change.severity in {Severity.BREAKING, Severity.CRITICAL}
    )
    warnings = sum(1 for change in changes if change.severity is Severity.WARNING)
    total = len(changes)
    if breaking:
        status = DimensionStatus.FAIL
        # Score penalizes breaking findings but never uses "missing data = 0".
        score = max(0.0, 1.0 - (breaking / max(total, 1)))
    elif warnings:
        status = DimensionStatus.WARNING
        score = max(0.0, 1.0 - (0.25 * warnings / max(total, 1)))
    else:
        status = DimensionStatus.PASS
        score = 1.0
    return DimensionScore(
        name=name,
        status=status,
        score=round(score, 4),
        finding_count=total,
        breaking_count=breaking,
        warning_count=warnings,
        evidence=evidence,
        note="" if total else "No findings in this dimension.",
    )


def build_scorecard(
    report: CompatibilityReport,
    *,
    probe_gate: Any | None = None,
    behavioral_ran: bool | None = None,
    stability_ran: bool | None = None,
) -> CompatibilityScorecard:
    """Build a multi-dimension scorecard from a compatibility report.

    Optional ``probe_gate`` (from #58) or explicit ``behavioral_ran`` /
    ``stability_ran`` flags mark dimensions as N/A when probes were not run —
    never as 0%.
    """
    buckets: dict[DimensionName, list[Change]] = {name: [] for name in DimensionName}
    for change in report.changes:
        buckets[_partition(change)].append(change)

    probes_enabled = False
    stability_enabled = False
    if probe_gate is not None:
        enabled = bool(getattr(probe_gate, "enabled", False))
        probes_enabled = enabled
        if enabled:
            settings = getattr(probe_gate, "settings", {}) or {}
            trials = int(settings.get("trials", 1) or 1)
            mode = str(settings.get("mode", "offline"))
            stability_enabled = trials > 1 or mode == "stability"
    if behavioral_ran is not None:
        probes_enabled = behavioral_ran
    if stability_ran is not None:
        stability_enabled = stability_ran

    # Behavior codes in the report imply behavioral evidence was attached (#61).
    if buckets[DimensionName.BEHAVIORAL] or buckets[DimensionName.STABILITY]:
        probes_enabled = True
    if buckets[DimensionName.STABILITY]:
        stability_enabled = True

    dimensions = [
        _score_dimension(
            DimensionName.STRUCTURAL,
            buckets[DimensionName.STRUCTURAL],
            ran=True,
            evidence=EvidenceLabel.DETERMINISTIC,
            empty_note="",
        ),
        _score_dimension(
            DimensionName.SEMANTIC,
            buckets[DimensionName.SEMANTIC],
            ran=True,
            evidence=EvidenceLabel.DETERMINISTIC,
            empty_note="",
        ),
        _score_dimension(
            DimensionName.BEHAVIORAL,
            buckets[DimensionName.BEHAVIORAL],
            ran=probes_enabled,
            evidence=EvidenceLabel.MODEL_BASED if probes_enabled else EvidenceLabel.NA,
            empty_note="Behavioral probes not run (N/A, not 0%).",
        ),
        _score_dimension(
            DimensionName.SAFETY,
            buckets[DimensionName.SAFETY],
            ran=True,
            evidence=EvidenceLabel.DETERMINISTIC,
            empty_note="",
        ),
        _score_dimension(
            DimensionName.STABILITY,
            buckets[DimensionName.STABILITY],
            ran=stability_enabled,
            evidence=EvidenceLabel.MODEL_BASED if stability_enabled else EvidenceLabel.NA,
            empty_note="Stability trials not run (N/A, not 0%).",
        ),
    ]

    explanations = [
        explain_change(change)
        for change in report.changes
        if change.severity in {Severity.BREAKING, Severity.CRITICAL}
    ]

    # Critical safety or any breaking/critical → force FINAL FAIL (no average hide).
    critical_safety = [
        change for change in buckets[DimensionName.SAFETY] if change.severity is Severity.CRITICAL
    ]
    any_breaking = any(
        change.severity in {Severity.BREAKING, Severity.CRITICAL} for change in report.changes
    )
    forced_fail = bool(critical_safety) or any_breaking
    reason = None
    if critical_safety:
        reason = (
            f"Critical safety finding: {critical_safety[0].code} on {critical_safety[0].subject}"
        )
    elif any_breaking:
        first = next(
            change
            for change in report.changes
            if change.severity in {Severity.BREAKING, Severity.CRITICAL}
        )
        reason = f"Breaking/critical finding: {first.code} on {first.subject}"

    return CompatibilityScorecard(
        dimensions=dimensions,
        explanations=explanations,
        final_result="FAIL" if forced_fail else "PASS",
        forced_fail=forced_fail,
        forced_fail_reason=reason,
        counts=report.counts_by_severity(),
    )


def render_scorecard_markdown(scorecard: CompatibilityScorecard) -> str:
    lines = [
        "## Compatibility scorecard",
        "",
        f"**FINAL RESULT:** `{scorecard.final_result}`",
        "",
    ]
    if scorecard.forced_fail_reason:
        lines.append(f"_Forced fail:_ {scorecard.forced_fail_reason}")
        lines.append("")
    lines.extend(
        [
            "| Dimension | Status | Score | Evidence | Findings | Note |",
            "| --- | --- | ---: | --- | ---: | --- |",
        ]
    )
    for dim in scorecard.dimensions:
        score = "n/a" if dim.score is None else f"{dim.score:.0%}"
        note = dim.note.replace("|", "\\|")
        lines.append(
            f"| `{dim.name.value}` | `{dim.status.value}` | {score} | "
            f"`{dim.evidence.value}` | {dim.finding_count} | {note} |"
        )
    lines.append("")
    if scorecard.explanations:
        lines.append("## Breaking / critical explanations")
        lines.append("")
        for item in scorecard.explanations:
            lines.append(f"### `{item.code}` on `{item.subject}` ({item.severity})")
            lines.append("")
            lines.append(f"- **Evidence:** `{item.evidence.value}`")
            lines.append(f"- **What changed:** {item.what_changed}")
            lines.append(f"- **Why it matters:** {item.why_it_matters}")
            lines.append(f"- **Possible fix:** {item.remediation}")
            lines.append("")
    return "\n".join(lines)


def scorecard_from_json(payload: dict[str, Any]) -> CompatibilityScorecard:
    """Rebuild a scorecard view from compare JSON (no Change objects required)."""
    dims: list[DimensionScore] = []
    for item in payload.get("dimensions") or []:
        dims.append(
            DimensionScore(
                name=DimensionName(item["name"]),
                status=DimensionStatus(item["status"]),
                score=item.get("score"),
                finding_count=int(item.get("finding_count") or 0),
                breaking_count=int(item.get("breaking_count") or 0),
                warning_count=int(item.get("warning_count") or 0),
                evidence=EvidenceLabel(item.get("evidence") or "N/A"),
                note=str(item.get("note") or ""),
            )
        )
    explanations: list[FindingExplanation] = []
    for item in payload.get("explanations") or []:
        explanations.append(
            FindingExplanation(
                code=str(item.get("code") or ""),
                subject=str(item.get("subject") or ""),
                severity=str(item.get("severity") or ""),
                what_changed=str(item.get("what_changed") or ""),
                why_it_matters=str(item.get("why_it_matters") or ""),
                remediation=str(item.get("remediation") or ""),
                evidence=EvidenceLabel(item.get("evidence") or "DETERMINISTIC"),
            )
        )
    return CompatibilityScorecard(
        dimensions=dims,
        explanations=explanations,
        final_result=str(payload.get("final_result") or "PASS"),
        forced_fail=bool(payload.get("forced_fail")),
        forced_fail_reason=payload.get("forced_fail_reason"),
        counts=dict(payload.get("counts") or {}),
    )


def render_pr_comment_markdown(
    *,
    report_payload: dict[str, Any] | None = None,
    scorecard: CompatibilityScorecard | None = None,
    full_report_markdown: str | None = None,
) -> str:
    """Eval-style GitHub PR comment summary (#78).

    Prefer ``report_payload`` from compare JSON (includes counts, scorecard,
    optional probes). Falls back to a ``CompatibilityScorecard`` instance.
    When probes are omitted, Behavioral/Stability remain N/A — structural-only.
    """
    card = scorecard
    counts: dict[str, int] = {}
    probes_enabled = False
    probe_failed = False
    if report_payload is not None:
        counts = dict(report_payload.get("counts") or {})
        raw_card = report_payload.get("scorecard")
        if card is None and isinstance(raw_card, dict):
            card = scorecard_from_json(raw_card)
            if not counts:
                counts = dict(card.counts)
        probes = report_payload.get("probes") or {}
        probes_enabled = bool(probes.get("enabled"))
        probe_failed = bool(
            (report_payload.get("policy") or {}).get("probe_failed") or probes.get("failed")
        )

    if card is None:
        raise ValueError("render_pr_comment_markdown requires report_payload or scorecard")

    if not counts:
        counts = dict(card.counts)

    status = "FAIL" if probe_failed else card.final_result

    lines = [
        "## Tool-Semantics eval summary",
        "",
        f"**STATUS:** `{status}`",
        "",
        "### Counts",
        "",
        f"- critical: `{counts.get('critical', 0)}`",
        f"- breaking: `{counts.get('breaking', 0)}`",
        f"- warning: `{counts.get('warning', 0)}`",
        f"- info: `{counts.get('info', 0)}`",
        "",
        "### Scorecard",
        "",
        "| Dimension | Status | Score | Evidence |",
        "| --- | --- | ---: | --- |",
    ]
    for dim in card.dimensions:
        score = "n/a" if dim.score is None else f"{dim.score:.0%}"
        lines.append(
            f"| `{dim.name.value}` | `{dim.status.value}` | {score} | `{dim.evidence.value}` |"
        )
    lines.append("")

    if not probes_enabled:
        lines.append(
            "_Behavioral / stability probes were not configured — "
            "structural-only summary (behavioral/stability show n/a)._"
        )
        lines.append("")
    elif probe_failed:
        lines.append("_Probe gate failed — see behavioral section in the full report._")
        lines.append("")

    safety = next((dim for dim in card.dimensions if dim.name is DimensionName.SAFETY), None)
    if safety is not None and safety.status is DimensionStatus.FAIL:
        lines.extend(
            [
                "### Safety",
                "",
                (f"**Safety status:** `{safety.status.value}` (breaking/critical risk changes)."),
                "",
            ]
        )

    if card.explanations:
        lines.extend(["### Top breaking findings", ""])
        for item in card.explanations[:5]:
            lines.append(
                f"- `{item.code}` on `{item.subject}` (`{item.evidence.value}`) — "
                f"{item.what_changed}"
            )
        lines.append("")

    if full_report_markdown:
        lines.extend(
            [
                "<details>",
                "<summary>Full Tool-Semantics report</summary>",
                "",
                full_report_markdown.rstrip(),
                "",
                "</details>",
                "",
            ]
        )
    return "\n".join(lines)
