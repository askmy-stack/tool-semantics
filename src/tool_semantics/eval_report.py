"""Unified evaluation report — structural + semantic + behavioral + safety (#76)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tool_semantics.diff import Change, CompatibilityReport, Severity
from tool_semantics.policy import ReleasePolicy
from tool_semantics.probe_gate import ProbeGateReport

# Soft / model-selection signals (optional semantic section).
SEMANTIC_CODES = frozenset(
    {
        "tool.description_changed",
        "tool.renamed",
        "parameter.default_changed",
        "parameter.constraints_tightened",
    }
)
# Declared risk / confirmation surface (safety section).
SAFETY_CODES = frozenset({"tool.risk_changed"})


@dataclass
class EvalSection:
    name: str
    changes: list[Change] = field(default_factory=list)

    @property
    def breaking_count(self) -> int:
        return sum(
            1
            for change in self.changes
            if change.severity in {Severity.BREAKING, Severity.CRITICAL}
        )

    @property
    def warning_count(self) -> int:
        return sum(1 for change in self.changes if change.severity is Severity.WARNING)


@dataclass
class EvalReport:
    """One-shot evaluation across structural / semantic / probe / safety layers."""

    baseline: str
    candidate: str
    structural: EvalSection
    semantic: EvalSection
    safety: EvalSection
    counts: dict[str, int]
    is_compatible: bool
    policy_name: str
    structural_failed: bool
    probe_failed: bool
    probe_gate: ProbeGateReport
    passed: bool

    @property
    def final_result(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": "eval",
            "baseline": self.baseline,
            "candidate": self.candidate,
            "final_result": self.final_result,
            "passed": self.passed,
            "is_compatible": self.is_compatible,
            "counts": self.counts,
            "policy": {
                "fail_at_or_above": self.policy_name,
                "failed": not self.passed,
                "structural_failed": self.structural_failed,
                "probe_failed": self.probe_failed,
            },
            "sections": {
                "structural": _section_json(self.structural),
                "semantic": _section_json(self.semantic),
                "safety": _section_json(self.safety),
                "behavioral": self.probe_gate.to_json(),
                "stability": _stability_summary(self.probe_gate),
            },
            "probes": self.probe_gate.to_json(),
        }


def _section_json(section: EvalSection) -> dict[str, Any]:
    return {
        "name": section.name,
        "breaking": section.breaking_count,
        "warnings": section.warning_count,
        "changes": [change.model_dump(mode="json") for change in section.changes],
    }


def _stability_summary(probe_gate: ProbeGateReport) -> dict[str, Any]:
    if not probe_gate.enabled:
        return {"enabled": False, "targets": []}
    targets = []
    for outcome in probe_gate.targets:
        if outcome.stability is None:
            continue
        targets.append(
            {
                "target": outcome.target,
                "trial_count": outcome.stability.trial_count,
                "seed": outcome.stability.seed,
                "unstable": [
                    item.probe_id for item in outcome.stability.summaries if item.unstable
                ],
                "deterministic_failures": [
                    item.probe_id
                    for item in outcome.stability.summaries
                    if item.deterministic_failure
                ],
                "passed": outcome.passed,
            }
        )
    return {"enabled": bool(targets), "targets": targets}


def partition_changes(report: CompatibilityReport) -> tuple[EvalSection, EvalSection, EvalSection]:
    structural: list[Change] = []
    semantic: list[Change] = []
    safety: list[Change] = []
    for change in report.changes:
        if change.code in SAFETY_CODES:
            safety.append(change)
        elif change.code in SEMANTIC_CODES:
            semantic.append(change)
        else:
            structural.append(change)
    return (
        EvalSection(name="structural", changes=structural),
        EvalSection(name="semantic", changes=semantic),
        EvalSection(name="safety", changes=safety),
    )


def build_eval_report(
    report: CompatibilityReport,
    *,
    release_policy: ReleasePolicy,
    probe_gate: ProbeGateReport,
) -> EvalReport:
    structural, semantic, safety = partition_changes(report)
    structural_failed = release_policy.should_fail(report)
    probe_failed = probe_gate.failed
    return EvalReport(
        baseline=report.baseline,
        candidate=report.candidate,
        structural=structural,
        semantic=semantic,
        safety=safety,
        counts=report.counts_by_severity(),
        is_compatible=report.is_compatible,
        policy_name=release_policy.fail_at_or_above.value,
        structural_failed=structural_failed,
        probe_failed=probe_failed,
        probe_gate=probe_gate,
        passed=not (structural_failed or probe_failed),
    )


def render_eval_markdown(eval_report: EvalReport) -> str:
    """Unified Markdown: Structural, Semantic, Behavioral, Safety, Stability, FINAL RESULT."""
    counts = eval_report.counts
    lines = [
        f"# Tool-Semantics eval: {eval_report.baseline} → {eval_report.candidate}",
        "",
        f"**FINAL RESULT:** `{eval_report.final_result}`",
        "",
        "| Severity | Count |",
        "| --- | ---: |",
        f"| critical | {counts.get('critical', 0)} |",
        f"| breaking | {counts.get('breaking', 0)} |",
        f"| warning | {counts.get('warning', 0)} |",
        f"| info | {counts.get('info', 0)} |",
        "",
        f"- Structural policy failed: `{'yes' if eval_report.structural_failed else 'no'}`",
        f"- Probe gate failed: `{'yes' if eval_report.probe_failed else 'no'}`",
        f"- Policy threshold: `{eval_report.policy_name}`",
        "",
    ]

    lines.extend(_render_change_section("Structural", eval_report.structural))
    lines.extend(_render_change_section("Semantic", eval_report.semantic))
    lines.extend(_render_change_section("Safety", eval_report.safety))

    # Behavioral + Stability from probe gate
    if eval_report.probe_gate.enabled:
        from tool_semantics.report import render_probe_gate_markdown

        lines.append(render_probe_gate_markdown(eval_report.probe_gate).rstrip())
        lines.append("")
        stability = _stability_summary(eval_report.probe_gate)
        lines.append("## Stability")
        lines.append("")
        if not stability["enabled"]:
            lines.append("_No stability trials (trials=1 or offline mode)._")
            lines.append("")
        else:
            for target in stability["targets"]:
                lines.append(f"### Target: `{target['target']}`")
                lines.append("")
                lines.append(f"- Trials: `{target['trial_count']}`")
                lines.append(f"- Seed: `{target['seed'] if target['seed'] is not None else 'n/a'}`")
                lines.append(f"- Passed: `{'yes' if target['passed'] else 'no'}`")
                if target["unstable"]:
                    lines.append(
                        "- Unstable: " + ", ".join(f"`{pid}`" for pid in target["unstable"])
                    )
                if target["deterministic_failures"]:
                    lines.append(
                        "- Deterministic failures: "
                        + ", ".join(f"`{pid}`" for pid in target["deterministic_failures"])
                    )
                lines.append("")
    else:
        lines.extend(
            [
                "## Behavioral probes",
                "",
                "_Probes not enabled. Pass `--probes` or set `[probes]` in config._",
                "",
                "## Stability",
                "",
                "_Not run (requires model-backed `--probe-trials` > 1)._",
                "",
            ]
        )

    lines.extend(
        [
            "## FINAL RESULT",
            "",
            f"**`{eval_report.final_result}`** — "
            f"compatible=`{str(eval_report.is_compatible).lower()}`, "
            f"breaking={counts.get('breaking', 0)}, "
            f"warnings={counts.get('warning', 0)}, "
            f"probe_failed=`{str(eval_report.probe_failed).lower()}`",
            "",
        ]
    )
    return "\n".join(lines)


def _render_change_section(title: str, section: EvalSection) -> list[str]:
    lines = [
        f"## {title}",
        "",
        f"- Breaking/critical: `{section.breaking_count}`",
        f"- Warnings: `{section.warning_count}`",
        "",
    ]
    if not section.changes:
        lines.append(f"_No {title.lower()} changes._")
        lines.append("")
        return lines
    lines.extend(
        [
            "| Severity | Code | Subject | Change |",
            "| --- | --- | --- | --- |",
        ]
    )
    for change in section.changes:
        message = change.message.replace("|", "\\|")
        lines.append(
            f"| `{change.severity.value}` | `{change.code}` | `{change.subject}` | {message} |"
        )
    lines.append("")
    return lines
