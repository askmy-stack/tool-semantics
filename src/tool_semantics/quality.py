"""Tool description / schema / risk quality lint and server audit (#97)."""

from __future__ import annotations

import re
from collections import Counter
from enum import StrEnum

from pydantic import BaseModel, Field

from tool_semantics.diff import _jaccard, _token_set
from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract

_VAGUE_PHRASES = frozenset(
    {
        "do something",
        "helper",
        "utility",
        "misc",
        "miscellaneous",
        "various",
        "stuff",
        "things",
        "todo",
        "tbd",
        "placeholder",
        "test tool",
        "example",
    }
)

_DESTRUCTIVE_HINTS = frozenset(
    {"delete", "destroy", "remove", "drop", "purge", "wipe", "erase", "kill"}
)
_WRITE_HINTS = frozenset(
    {"create", "update", "write", "post", "put", "patch", "send", "publish", "upload"}
)
_READ_HINTS = frozenset({"get", "list", "search", "find", "read", "fetch", "view", "show"})


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class QualityFinding(BaseModel):
    severity: FindingSeverity
    code: str
    subject: str
    message: str


class LintReport(BaseModel):
    findings: list[QualityFinding] = Field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == FindingSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == FindingSeverity.WARNING)

    def should_fail(self, *, fail_on_warning: bool = False) -> bool:
        if self.error_count:
            return True
        return fail_on_warning and self.warning_count > 0


class AmbiguousPair(BaseModel):
    left: str
    right: str
    score: float


class AuditReport(BaseModel):
    tool_count: int = 0
    finding_counts: dict[str, int] = Field(default_factory=dict)
    unknown_risk_count: int = 0
    missing_description_count: int = 0
    vague_description_count: int = 0
    ambiguous_pairs: list[AmbiguousPair] = Field(default_factory=list)
    findings: list[QualityFinding] = Field(default_factory=list)

    def should_fail(self, *, fail_on_warning: bool = False) -> bool:
        errors = sum(1 for item in self.findings if item.severity == FindingSeverity.ERROR)
        warnings = sum(1 for item in self.findings if item.severity == FindingSeverity.WARNING)
        if errors:
            return True
        return fail_on_warning and warnings > 0


def _is_poor_name(name: str) -> bool:
    if len(name) < 3:
        return True
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        return True
    if name in {"tool", "fn", "func", "tmp", "test", "foo", "bar"}:
        return True
    return False


def _description_vague(description: str) -> bool:
    text = description.strip().lower()
    if len(text) < 12:
        return True
    if text in _VAGUE_PHRASES:
        return True
    return any(phrase in text for phrase in _VAGUE_PHRASES)


def _schema_param_names(tool: ToolContract) -> set[str]:
    return {parameter.name for parameter in tool.parameters}


def _description_mentions_unknown_params(tool: ToolContract) -> list[str]:
    """Flag backtick/`name=` style mentions that are not in the schema."""
    desc = tool.description
    mentioned = set(re.findall(r"`([a-zA-Z_][a-zA-Z0-9_]*)`", desc))
    mentioned |= set(re.findall(r"\b([a-z_][a-z0-9_]{2,})\s*=", desc))
    known = _schema_param_names(tool) | {tool.name}
    return sorted(name for name in mentioned if name not in known)


def _risk_vs_description(tool: ToolContract) -> str | None:
    tokens = _token_set(f"{tool.name} {tool.description}")
    destructive = bool(tokens & _DESTRUCTIVE_HINTS)
    writes = bool(tokens & _WRITE_HINTS)
    reads = bool(tokens & _READ_HINTS)
    if tool.risk == RiskLevel.READ_ONLY and (destructive or writes):
        return (
            f"Risk is read_only but name/description suggests "
            f"{'destructive' if destructive else 'write'} behavior."
        )
    if tool.risk == RiskLevel.DESTRUCTIVE and not destructive and reads and not writes:
        return "Risk is destructive but name/description looks read-oriented."
    return None


def lint_snapshot(snapshot: InterfaceSnapshot) -> LintReport:
    """Per-tool description / schema / risk quality checks."""
    findings: list[QualityFinding] = []
    desc_counts: Counter[str] = Counter(
        tool.description.strip().lower() for tool in snapshot.tools if tool.description.strip()
    )

    for tool in snapshot.tools:
        if _is_poor_name(tool.name):
            findings.append(
                QualityFinding(
                    severity=FindingSeverity.WARNING,
                    code="lint.poor_name",
                    subject=tool.name,
                    message="Tool name is too short, non-snake_case, or generic.",
                )
            )
        if not tool.description.strip():
            findings.append(
                QualityFinding(
                    severity=FindingSeverity.ERROR,
                    code="lint.missing_description",
                    subject=tool.name,
                    message="Tool description is missing.",
                )
            )
        elif _description_vague(tool.description):
            findings.append(
                QualityFinding(
                    severity=FindingSeverity.WARNING,
                    code="lint.vague_description",
                    subject=tool.name,
                    message="Tool description is vague or too short.",
                )
            )
        normalized = tool.description.strip().lower()
        if normalized and desc_counts[normalized] > 1:
            findings.append(
                QualityFinding(
                    severity=FindingSeverity.WARNING,
                    code="lint.duplicate_description",
                    subject=tool.name,
                    message="Tool description is duplicated on another tool.",
                )
            )
        for param in _description_mentions_unknown_params(tool):
            findings.append(
                QualityFinding(
                    severity=FindingSeverity.WARNING,
                    code="lint.schema_description_mismatch",
                    subject=f"{tool.name}.{param}",
                    message=(f"Description mentions '{param}' which is not a declared parameter."),
                )
            )
        risk_msg = _risk_vs_description(tool)
        if risk_msg:
            findings.append(
                QualityFinding(
                    severity=FindingSeverity.WARNING,
                    code="lint.risk_description_mismatch",
                    subject=tool.name,
                    message=risk_msg,
                )
            )
        if tool.risk == RiskLevel.UNKNOWN:
            findings.append(
                QualityFinding(
                    severity=FindingSeverity.INFO,
                    code="lint.unknown_risk",
                    subject=tool.name,
                    message="Tool risk is unknown (consider declaring risk).",
                )
            )

    return LintReport(findings=findings)


def _ambiguous_pairs(
    snapshot: InterfaceSnapshot, *, threshold: float = 0.45, limit: int = 10
) -> list[AmbiguousPair]:
    tools = snapshot.tools
    pairs: list[AmbiguousPair] = []
    for index, left in enumerate(tools):
        left_tokens = _token_set(f"{left.name.replace('_', ' ')} {left.description}")
        for right in tools[index + 1 :]:
            right_tokens = _token_set(f"{right.name.replace('_', ' ')} {right.description}")
            score = _jaccard(left_tokens, right_tokens)
            if score >= threshold:
                pairs.append(AmbiguousPair(left=left.name, right=right.name, score=round(score, 4)))
    pairs.sort(key=lambda item: item.score, reverse=True)
    return pairs[:limit]


def audit_snapshot(snapshot: InterfaceSnapshot, *, pair_limit: int = 10) -> AuditReport:
    """Server-wide quality aggregates plus top ambiguous tool pairs."""
    lint = lint_snapshot(snapshot)
    counts: Counter[str] = Counter(item.code for item in lint.findings)
    return AuditReport(
        tool_count=len(snapshot.tools),
        finding_counts=dict(counts),
        unknown_risk_count=counts.get("lint.unknown_risk", 0),
        missing_description_count=counts.get("lint.missing_description", 0),
        vague_description_count=counts.get("lint.vague_description", 0),
        ambiguous_pairs=_ambiguous_pairs(snapshot, limit=pair_limit),
        findings=lint.findings,
    )


def render_lint_markdown(report: LintReport) -> str:
    lines = [
        "# Tool lint report",
        "",
        f"- Errors: {report.error_count}",
        f"- Warnings: {report.warning_count}",
        "",
    ]
    if not report.findings:
        lines.append("_No lint findings._")
        lines.append("")
        return "\n".join(lines)
    lines.extend(
        [
            "| Severity | Code | Subject | Message |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in report.findings:
        message = item.message.replace("|", "\\|")
        lines.append(f"| `{item.severity.value}` | `{item.code}` | `{item.subject}` | {message} |")
    lines.append("")
    return "\n".join(lines)


def render_audit_markdown(report: AuditReport) -> str:
    lines = [
        "# Tool audit report",
        "",
        f"- Tools: {report.tool_count}",
        f"- Missing descriptions: {report.missing_description_count}",
        f"- Vague descriptions: {report.vague_description_count}",
        f"- Unknown risk: {report.unknown_risk_count}",
        "",
        "### Finding counts",
        "",
    ]
    if report.finding_counts:
        for code, count in sorted(report.finding_counts.items()):
            lines.append(f"- `{code}`: {count}")
    else:
        lines.append("_No findings._")
    lines.extend(["", "### Top ambiguous pairs", ""])
    if not report.ambiguous_pairs:
        lines.append("_No ambiguous pairs above threshold._")
    else:
        lines.extend(["| Left | Right | Score |", "| --- | --- | ---: |"])
        for pair in report.ambiguous_pairs:
            lines.append(f"| `{pair.left}` | `{pair.right}` | {pair.score:.2f} |")
    lines.append("")
    return "\n".join(lines)
