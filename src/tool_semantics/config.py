from __future__ import annotations

import fnmatch
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tool_semantics.diff import Change, CompatibilityReport, Severity
from tool_semantics.policy import FailSeverity, ReleasePolicy

DEFAULT_CONFIG_NAME = ".tool-semantics.toml"


@dataclass(frozen=True)
class IgnoreRules:
    codes: tuple[str, ...] = ()
    subjects: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolSemanticsConfig:
    ignore: IgnoreRules = field(default_factory=IgnoreRules)
    policy: ReleasePolicy = field(default_factory=ReleasePolicy)


def _as_str_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Config field '{field_name}' must be an array of strings")
    return tuple(value)


def _parse_policy(raw: dict[str, Any]) -> ReleasePolicy:
    fail_at = raw.get("fail_at_or_above", "breaking")
    if not isinstance(fail_at, str):
        raise ValueError("Config field 'policy.fail_at_or_above' must be a string")
    try:
        severity = FailSeverity(fail_at.strip().lower())
    except ValueError as exc:
        raise ValueError(
            "policy.fail_at_or_above must be one of: info, warning, breaking, critical, none"
        ) from exc
    return ReleasePolicy(fail_at_or_above=severity)


def load_config(path: Path | None = None) -> ToolSemanticsConfig:
    """Load `.tool-semantics.toml` (or an explicit path). Missing file → empty config."""
    config_path = path
    if config_path is None:
        candidate = Path.cwd() / DEFAULT_CONFIG_NAME
        if not candidate.is_file():
            return ToolSemanticsConfig()
        config_path = candidate
    elif not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Config root must be a table")
    ignore_raw = raw.get("ignore", {})
    if ignore_raw is None:
        ignore_raw = {}
    if not isinstance(ignore_raw, dict):
        raise ValueError("Config field 'ignore' must be a table")
    policy_raw = raw.get("policy", {})
    if policy_raw is None:
        policy_raw = {}
    if not isinstance(policy_raw, dict):
        raise ValueError("Config field 'policy' must be a table")
    return ToolSemanticsConfig(
        ignore=IgnoreRules(
            codes=_as_str_tuple(ignore_raw.get("codes"), "ignore.codes"),
            subjects=_as_str_tuple(ignore_raw.get("subjects"), "ignore.subjects"),
        ),
        policy=_parse_policy(policy_raw),
    )


def _is_ignored(change: Change, rules: IgnoreRules) -> bool:
    if change.code in rules.codes:
        return True
    return any(fnmatch.fnmatchcase(change.subject, pattern) for pattern in rules.subjects)


def apply_ignore_rules(
    report: CompatibilityReport, config: ToolSemanticsConfig
) -> CompatibilityReport:
    """Downgrade ignored changes to info so they stay visible but do not fail CI."""
    if not config.ignore.codes and not config.ignore.subjects:
        return report
    adjusted: list[Change] = []
    for change in report.changes:
        if _is_ignored(change, config.ignore) and change.severity in {
            Severity.WARNING,
            Severity.BREAKING,
            Severity.CRITICAL,
        }:
            adjusted.append(
                Change(
                    severity=Severity.INFO,
                    code=change.code,
                    subject=change.subject,
                    message=f"[ignored] {change.message}",
                )
            )
        else:
            adjusted.append(change)
    return CompatibilityReport(
        baseline=report.baseline,
        candidate=report.candidate,
        changes=adjusted,
    )
