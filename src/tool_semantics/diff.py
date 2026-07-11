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


def _schema_without_default(schema: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in schema.items() if key != "default"}


def _append_output_schema_changes(
    report: CompatibilityReport,
    tool_name: str,
    old_schema: dict[str, object] | None,
    new_schema: dict[str, object] | None,
) -> None:
    if old_schema == new_schema:
        return
    if old_schema is None:
        report.changes.append(
            Change(
                severity=Severity.INFO,
                code="tool.output_schema_added",
                subject=tool_name,
                message=f"Output schema was added to '{tool_name}'.",
            )
        )
        return
    if new_schema is None:
        report.changes.append(
            Change(
                severity=Severity.BREAKING,
                code="tool.output_schema_removed",
                subject=tool_name,
                message=f"Output schema was removed from '{tool_name}'.",
            )
        )
        return
    report.changes.append(
        Change(
            severity=Severity.BREAKING,
            code="tool.output_schema_changed",
            subject=tool_name,
            message=f"Output schema changed for '{tool_name}'.",
        )
    )


def _append_default_change(
    report: CompatibilityReport,
    subject: str,
    parameter_name: str,
    old_schema: dict[str, object],
    new_schema: dict[str, object],
) -> None:
    old_has = "default" in old_schema
    new_has = "default" in new_schema
    if not old_has and not new_has:
        return
    if old_has and new_has and old_schema["default"] == new_schema["default"]:
        return
    if old_has and new_has:
        message = (
            f"Default for '{parameter_name}' changed from "
            f"{old_schema['default']!r} to {new_schema['default']!r}."
        )
    elif not old_has and new_has:
        message = f"Default {new_schema['default']!r} was added to '{parameter_name}'."
    else:
        message = f"Default {old_schema['default']!r} was removed from '{parameter_name}'."
    report.changes.append(
        Change(
            severity=Severity.WARNING,
            code="parameter.default_changed",
            subject=subject,
            message=message,
        )
    )


def _append_schema_changes(
    report: CompatibilityReport,
    subject: str,
    parameter_name: str,
    old_schema: dict[str, object],
    new_schema: dict[str, object],
) -> None:
    old_core = _schema_without_default(old_schema)
    new_core = _schema_without_default(new_schema)
    if old_core == new_core:
        return
    old_enum = _enum_values(old_core)
    new_enum = _enum_values(new_core)
    if old_enum is not None and new_enum is not None and old_enum != new_enum:
        removed = sorted(old_enum - new_enum)
        added = sorted(new_enum - old_enum)
        if removed:
            report.changes.append(
                Change(
                    severity=Severity.BREAKING,
                    code="parameter.enum_values_removed",
                    subject=subject,
                    message=(
                        f"Enum values removed from '{parameter_name}': {', '.join(removed)}."
                    ),
                )
            )
        if added:
            report.changes.append(
                Change(
                    severity=Severity.INFO,
                    code="parameter.enum_values_added",
                    subject=subject,
                    message=(f"Enum values added to '{parameter_name}': {', '.join(added)}."),
                )
            )
        # Enum-only diffs already covered; residual non-enum keys still need a code.
        old_non_enum = {key: value for key, value in old_core.items() if key != "enum"}
        new_non_enum = {key: value for key, value in new_core.items() if key != "enum"}
        if old_non_enum == new_non_enum:
            return
    report.changes.append(
        Change(
            severity=Severity.BREAKING,
            code="parameter.schema_changed",
            subject=subject,
            message=f"Schema changed for parameter '{parameter_name}'.",
        )
    )


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
        _append_output_schema_changes(
            report,
            name,
            old_tool.output_schema,
            new_tool.output_schema,
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
            subject = f"{name}.{parameter_name}"
            _append_default_change(
                report,
                subject,
                parameter_name,
                old_parameter.schema_,
                new_parameter.schema_,
            )
            _append_schema_changes(
                report,
                subject,
                parameter_name,
                old_parameter.schema_,
                new_parameter.schema_,
            )
            if not old_parameter.required and new_parameter.required:
                report.changes.append(
                    Change(
                        severity=Severity.BREAKING,
                        code="parameter.became_required",
                        subject=subject,
                        message=f"Parameter '{parameter_name}' became required.",
                    )
                )
    return report
