from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from tool_semantics.diff import CompatibilityReport, Severity


class FailSeverity(StrEnum):
    """Highest severity that is still allowed without failing a gate."""

    INFO = "info"
    WARNING = "warning"
    BREAKING = "breaking"
    CRITICAL = "critical"
    NONE = "none"  # never fail on severity (input errors still fail)


_ORDER = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.BREAKING: 2,
    Severity.CRITICAL: 3,
}


@dataclass(frozen=True)
class ReleasePolicy:
    """Release / CI gate for compatibility reports."""

    # Fail when any change is at or above this severity.
    fail_at_or_above: FailSeverity = FailSeverity.BREAKING

    def should_fail(self, report: CompatibilityReport) -> bool:
        if self.fail_at_or_above is FailSeverity.NONE:
            return False
        threshold = {
            FailSeverity.INFO: 0,
            FailSeverity.WARNING: 1,
            FailSeverity.BREAKING: 2,
            FailSeverity.CRITICAL: 3,
        }[self.fail_at_or_above]
        return any(_ORDER[change.severity] >= threshold for change in report.changes)


def policy_from_name(name: str) -> ReleasePolicy:
    normalized = name.strip().lower()
    aliases = {
        "compatible": FailSeverity.BREAKING,
        "breaking": FailSeverity.BREAKING,
        "strict": FailSeverity.WARNING,
        "warning": FailSeverity.WARNING,
        "critical-only": FailSeverity.CRITICAL,
        "critical": FailSeverity.CRITICAL,
        "info": FailSeverity.INFO,
        "permissive": FailSeverity.NONE,
        "none": FailSeverity.NONE,
    }
    if normalized not in aliases:
        raise ValueError(
            f"Unknown release policy {name!r}. Expected one of: {', '.join(sorted(aliases))}"
        )
    return ReleasePolicy(fail_at_or_above=aliases[normalized])
