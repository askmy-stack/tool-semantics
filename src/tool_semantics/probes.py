from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from tool_semantics.models import InterfaceSnapshot, RiskLevel


class ProbeKind(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    AMBIGUOUS = "ambiguous"


class Probe(BaseModel):
    """Offline behavioral probe — no model calls required."""

    id: str
    intent: str
    kind: ProbeKind = ProbeKind.POSITIVE
    expected_tool: str | None = None
    forbidden_tools: list[str] = Field(default_factory=list)
    required_params: list[str] = Field(default_factory=list)
    # Side-effect / confirmation expectations (Milestone 3).
    max_risk: str | None = None  # read_only | external_write | destructive | unknown
    requires_confirmation: bool = False


class ProbeResult(BaseModel):
    probe_id: str
    passed: bool
    message: str


class ProbeReport(BaseModel):
    results: list[ProbeResult] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def failures(self) -> list[ProbeResult]:
        return [result for result in self.results if not result.passed]


def evaluate_probes(snapshot: InterfaceSnapshot, probes: list[Probe]) -> ProbeReport:
    """Evaluate probes against a snapshot without calling an LLM.

    Positive probes require the expected tool (and optional required params) to exist.
    Negative probes fail if a forbidden tool is present.
    Ambiguous probes pass when the expected tool exists but record a soft warning message
    if additional candidate tools share overlapping description tokens.
    """
    tools = {tool.name: tool for tool in snapshot.tools}
    report = ProbeReport()
    for probe in probes:
        if probe.kind == ProbeKind.NEGATIVE:
            present = [name for name in probe.forbidden_tools if name in tools]
            if present:
                report.results.append(
                    ProbeResult(
                        probe_id=probe.id,
                        passed=False,
                        message=f"Forbidden tools still present: {', '.join(present)}",
                    )
                )
            else:
                report.results.append(
                    ProbeResult(
                        probe_id=probe.id,
                        passed=True,
                        message="Forbidden tools absent.",
                    )
                )
            continue

        if probe.expected_tool is None:
            report.results.append(
                ProbeResult(
                    probe_id=probe.id,
                    passed=False,
                    message="Probe is missing expected_tool.",
                )
            )
            continue
        tool = tools.get(probe.expected_tool)
        if tool is None:
            report.results.append(
                ProbeResult(
                    probe_id=probe.id,
                    passed=False,
                    message=f"Expected tool '{probe.expected_tool}' not found.",
                )
            )
            continue
        missing = [
            name
            for name in probe.required_params
            if name not in {parameter.name for parameter in tool.parameters}
        ]
        if missing:
            report.results.append(
                ProbeResult(
                    probe_id=probe.id,
                    passed=False,
                    message=f"Missing required params on '{tool.name}': {', '.join(missing)}",
                )
            )
            continue
        if probe.max_risk is not None:
            try:
                allowed = RiskLevel(probe.max_risk)
            except ValueError:
                report.results.append(
                    ProbeResult(
                        probe_id=probe.id,
                        passed=False,
                        message=f"Invalid max_risk '{probe.max_risk}'.",
                    )
                )
                continue
            rank = {
                RiskLevel.READ_ONLY: 0,
                RiskLevel.UNKNOWN: 1,
                RiskLevel.EXTERNAL_WRITE: 2,
                RiskLevel.DESTRUCTIVE: 3,
            }
            if rank[tool.risk] > rank[allowed]:
                report.results.append(
                    ProbeResult(
                        probe_id=probe.id,
                        passed=False,
                        message=(
                            f"Tool '{tool.name}' risk '{tool.risk}' exceeds "
                            f"max_risk '{probe.max_risk}'."
                        ),
                    )
                )
                continue
        if probe.requires_confirmation and tool.risk in {
            RiskLevel.EXTERNAL_WRITE,
            RiskLevel.DESTRUCTIVE,
        }:
            # Offline harness can only assert that confirmation is *required by policy*;
            # it cannot observe a runtime confirmation UI.
            message_prefix = (
                f"Expected tool '{tool.name}' present; confirmation required for "
                f"risk '{tool.risk}'."
            )
        else:
            message_prefix = f"Expected tool '{tool.name}' present."
        message = message_prefix
        if probe.kind == ProbeKind.AMBIGUOUS:
            intent_tokens = {token.lower() for token in probe.intent.split() if len(token) > 3}
            collisions = []
            for other in snapshot.tools:
                if other.name == tool.name:
                    continue
                desc_tokens = {
                    token.lower() for token in other.description.split() if len(token) > 3
                }
                if intent_tokens & desc_tokens:
                    collisions.append(other.name)
            if collisions:
                message += f" Potential selection collisions: {', '.join(collisions)}."
        report.results.append(ProbeResult(probe_id=probe.id, passed=True, message=message))
    return report
