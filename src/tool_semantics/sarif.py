"""Optional SARIF 2.1.0 export for compatibility findings (#99).

Default Markdown/JSON reports remain the primary outputs. SARIF is for
enterprise CI dashboards (GitHub code scanning, etc.).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tool_semantics import __version__
from tool_semantics.diff import Change, CompatibilityReport, Severity

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"

# SARIF levels for gateable findings (breaking/critical → error).
_LEVEL = {
    Severity.CRITICAL: "error",
    Severity.BREAKING: "error",
    Severity.WARNING: "warning",
    Severity.INFO: "note",
}

GATEABLE = frozenset({Severity.BREAKING, Severity.CRITICAL})


def _rule_id(change: Change) -> str:
    return change.code


def _help_uri(code: str) -> str:
    del code
    return "https://github.com/askmy-stack/tool-semantics/blob/main/docs/change-codes.md"


def build_sarif(
    report: CompatibilityReport,
    *,
    include_warnings: bool = False,
    tool_version: str | None = None,
) -> dict[str, Any]:
    """Build a SARIF 2.1.0 document for breaking/critical (optionally warning) findings."""
    selected = [
        change
        for change in report.changes
        if change.severity in GATEABLE or (include_warnings and change.severity == Severity.WARNING)
    ]
    rules_by_id: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for index, change in enumerate(selected):
        rule_id = _rule_id(change)
        if rule_id not in rules_by_id:
            rules_by_id[rule_id] = {
                "id": rule_id,
                "name": rule_id,
                "shortDescription": {"text": rule_id},
                "fullDescription": {"text": f"Tool-Semantics change code `{rule_id}`."},
                "helpUri": _help_uri(rule_id),
                "defaultConfiguration": {
                    "level": _LEVEL.get(change.severity, "warning"),
                },
                "properties": {
                    "tags": ["tool-semantics", change.severity.value],
                },
            }
        results.append(
            {
                "ruleId": rule_id,
                "level": _LEVEL.get(change.severity, "warning"),
                "message": {
                    "text": f"[{change.severity.value}] {change.subject}: {change.message}"
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": report.candidate or "candidate",
                                "description": {"text": f"Subject `{change.subject}`"},
                            },
                            "region": {"startLine": index + 1},
                        }
                    }
                ],
                "properties": {
                    "severity": change.severity.value,
                    "subject": change.subject,
                    "code": change.code,
                },
            }
        )

    rule_ids = list(rules_by_id)
    for result in results:
        result["ruleIndex"] = rule_ids.index(result["ruleId"])

    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "tool-semantics",
                        "version": tool_version or __version__,
                        "informationUri": "https://github.com/askmy-stack/tool-semantics",
                        "rules": [rules_by_id[rule_id] for rule_id in rule_ids],
                    }
                },
                "invocations": [
                    {
                        "executionSuccessful": True,
                    }
                ],
                "results": results,
                "properties": {
                    "baseline": report.baseline,
                    "candidate": report.candidate,
                    "is_compatible": report.is_compatible,
                    "counts": report.counts_by_severity(),
                },
            }
        ],
    }


def render_sarif_json(
    report: CompatibilityReport,
    *,
    include_warnings: bool = False,
    tool_version: str | None = None,
) -> str:
    return (
        json.dumps(
            build_sarif(report, include_warnings=include_warnings, tool_version=tool_version),
            indent=2,
        )
        + "\n"
    )


def write_sarif(
    report: CompatibilityReport,
    path: Path,
    *,
    include_warnings: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_sarif_json(report, include_warnings=include_warnings),
        encoding="utf-8",
    )
