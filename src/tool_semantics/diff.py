from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from tool_semantics.models import InterfaceSnapshot, ToolContract, ToolParameter


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BREAKING = "breaking"
    CRITICAL = "critical"


class Change(BaseModel):
    severity: Severity
    code: str
    subject: str
    message: str


class CompatibilityReport(BaseModel):
    baseline: str
    candidate: str
    changes: list[Change] = Field(default_factory=list)

    @property
    def is_compatible(self) -> bool:
        return not any(
            change.severity in {Severity.BREAKING, Severity.CRITICAL} for change in self.changes
        )

    def counts_by_severity(self) -> dict[str, int]:
        counts = {severity.value: 0 for severity in Severity}
        for change in self.changes:
            counts[change.severity.value] += 1
        return counts


def _parameter_map(tool: ToolContract) -> dict[str, ToolParameter]:
    return {parameter.name: parameter for parameter in tool.parameters}


def _enum_values(schema: dict[str, object]) -> set[str] | None:
    values = schema.get("enum")
    if values is None:
        return None
    if not isinstance(values, list):
        return None
    return {str(value) for value in values}


def compare_snapshots(
    baseline: InterfaceSnapshot,
    candidate: InterfaceSnapshot,
) -> CompatibilityReport:
    report = CompatibilityReport(
        baseline=baseline.server_version or baseline.server_name,
        candidate=candidate.server_version or candidate.server_name,
    )
    before = {tool.name: tool for tool in baseline.tools}
    after = {tool.name: tool for tool in candidate.tools}

    for name in sorted(before.keys() - after.keys()):
        report.changes.append(
            Change(
                severity=Severity.BREAKING,
                code="tool.removed",
                subject=name,
                message=f"Tool '{name}' was removed.",
            )
        )
    for name in sorted(after.keys() - before.keys()):
        report.changes.append(
            Change(
                severity=Severity.INFO,
                code="tool.added",
                subject=name,
                message=(f"Tool '{name}' was added; behavioral collision testing is pending."),
            )
        )

    for name in sorted(before.keys() & after.keys()):
        old_tool = before[name]
        new_tool = after[name]
        if old_tool.description != new_tool.description:
            report.changes.append(
                Change(
                    severity=Severity.WARNING,
                    code="tool.description_changed",
                    subject=name,
                    message=("Tool description changed; behavioral selection testing is required."),
                )
            )
        if old_tool.risk != new_tool.risk:
            severity = (
                Severity.CRITICAL
                if new_tool.risk.value in {"destructive", "external_write"}
                and old_tool.risk.value == "read_only"
                else Severity.WARNING
            )
            report.changes.append(
                Change(
                    severity=severity,
                    code="tool.risk_changed",
                    subject=name,
                    message=f"Risk level changed from '{old_tool.risk}' to '{new_tool.risk}'.",
                )
            )

        old_params = _parameter_map(old_tool)
        new_params = _parameter_map(new_tool)
        for parameter_name in sorted(old_params.keys() - new_params.keys()):
            report.changes.append(
                Change(
                    severity=Severity.BREAKING,
                    code="parameter.removed",
                    subject=f"{name}.{parameter_name}",
                    message=f"Parameter '{parameter_name}' was removed from '{name}'.",
                )
            )
        for parameter_name in sorted(new_params.keys() - old_params.keys()):
            parameter = new_params[parameter_name]
            severity = Severity.BREAKING if parameter.required else Severity.INFO
            report.changes.append(
                Change(
                    severity=severity,
                    code="parameter.added_required" if parameter.required else "parameter.added",
                    subject=f"{name}.{parameter_name}",
                    message=(
                        f"{'Required' if parameter.required else 'Optional'} parameter "
                        f"'{parameter_name}' was added to '{name}'."
                    ),
                )
            )
        for parameter_name in sorted(old_params.keys() & new_params.keys()):
            old_parameter = old_params[parameter_name]
            new_parameter = new_params[parameter_name]
            if old_parameter.schema_ != new_parameter.schema_:
                old_enum = _enum_values(old_parameter.schema_)
                new_enum = _enum_values(new_parameter.schema_)
                if old_enum is not None and new_enum is not None and old_enum != new_enum:
                    removed = sorted(old_enum - new_enum)
                    added = sorted(new_enum - old_enum)
                    if removed:
                        report.changes.append(
                            Change(
                                severity=Severity.BREAKING,
                                code="parameter.enum_values_removed",
                                subject=f"{name}.{parameter_name}",
                                message=(
                                    f"Enum values removed from '{parameter_name}': "
                                    f"{', '.join(removed)}."
                                ),
                            )
                        )
                    if added:
                        report.changes.append(
                            Change(
                                severity=Severity.INFO,
                                code="parameter.enum_values_added",
                                subject=f"{name}.{parameter_name}",
                                message=(
                                    f"Enum values added to '{parameter_name}': {', '.join(added)}."
                                ),
                            )
                        )
                else:
                    report.changes.append(
                        Change(
                            severity=Severity.BREAKING,
                            code="parameter.schema_changed",
                            subject=f"{name}.{parameter_name}",
                            message=f"Schema changed for parameter '{parameter_name}'.",
                        )
                    )
            if not old_parameter.required and new_parameter.required:
                report.changes.append(
                    Change(
                        severity=Severity.BREAKING,
                        code="parameter.became_required",
                        subject=f"{name}.{parameter_name}",
                        message=f"Parameter '{parameter_name}' became required.",
                    )
                )
    return report
