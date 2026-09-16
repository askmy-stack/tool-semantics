from __future__ import annotations

import fnmatch
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tool_semantics.diff import Change, CompatibilityReport, Severity
from tool_semantics.policy import FailSeverity, ReleasePolicy
from tool_semantics.probe_gate import ProbeGateSettings, ProbeMode, ProbeTarget, ProbeThresholds

DEFAULT_CONFIG_NAME = ".tool-semantics.toml"


@dataclass(frozen=True)
class IgnoreRules:
    codes: tuple[str, ...] = ()
    subjects: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolSemanticsConfig:
    ignore: IgnoreRules = field(default_factory=IgnoreRules)
    policy: ReleasePolicy = field(default_factory=ReleasePolicy)
    probes: ProbeGateSettings = field(default_factory=ProbeGateSettings)
    # Directory used to resolve relative probe file paths (config parent, or cwd).
    config_dir: Path | None = None


def _as_str_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Config field '{field_name}' must be an array of strings")
    return tuple(value)


def _as_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Config field '{field_name}' must be a number")
    return float(value)


def _as_optional_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    return _as_float(value, field_name)


def _as_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"Config field '{field_name}' must be a boolean")
    return value


def _as_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Config field '{field_name}' must be an integer")
    return value


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


def _parse_thresholds(raw: dict[str, Any]) -> ProbeThresholds:
    return ProbeThresholds(
        min_pass_rate=_as_float(raw.get("min_pass_rate", 1.0), "probes.thresholds.min_pass_rate"),
        min_tool_selection_accuracy=_as_optional_float(
            raw.get("min_tool_selection_accuracy"),
            "probes.thresholds.min_tool_selection_accuracy",
        ),
        min_argument_validity_rate=_as_optional_float(
            raw.get("min_argument_validity_rate"),
            "probes.thresholds.min_argument_validity_rate",
        ),
        min_stability_score=_as_optional_float(
            raw.get("min_stability_score"),
            "probes.thresholds.min_stability_score",
        ),
        fail_on_unstable=_as_bool(
            raw.get("fail_on_unstable", True),
            "probes.thresholds.fail_on_unstable",
        ),
        fail_on_deterministic_failure=_as_bool(
            raw.get("fail_on_deterministic_failure", True),
            "probes.thresholds.fail_on_deterministic_failure",
        ),
    )


def _parse_probes(raw: dict[str, Any], *, config_dir: Path) -> ProbeGateSettings:
    file_raw = raw.get("file")
    probe_file: Path | None = None
    if file_raw is not None:
        if not isinstance(file_raw, str) or not file_raw.strip():
            raise ValueError("Config field 'probes.file' must be a non-empty string")
        candidate = Path(file_raw)
        probe_file = candidate if candidate.is_absolute() else (config_dir / candidate)

    target_raw = raw.get("target", "candidate")
    if not isinstance(target_raw, str):
        raise ValueError("Config field 'probes.target' must be a string")
    target_norm = target_raw.strip().lower()
    if target_norm not in {"baseline", "candidate", "both"}:
        raise ValueError("probes.target must be one of: baseline, candidate, both")
    target: ProbeTarget = target_norm  # type: ignore[assignment]

    mode_raw = raw.get("mode", "offline")
    if not isinstance(mode_raw, str):
        raise ValueError("Config field 'probes.mode' must be a string")
    mode_norm = mode_raw.strip().lower()
    if mode_norm not in {"offline", "model"}:
        raise ValueError("probes.mode must be one of: offline, model")
    mode: ProbeMode = mode_norm  # type: ignore[assignment]

    trials = _as_int(raw.get("trials", 1), "probes.trials")
    if trials < 1:
        raise ValueError("probes.trials must be >= 1")

    seed_raw = raw.get("seed")
    seed: int | None
    if seed_raw is None:
        seed = None
    else:
        seed = _as_int(seed_raw, "probes.seed")

    allow_unapproved = _as_bool(raw.get("allow_unapproved", False), "probes.allow_unapproved")

    thresholds_raw = raw.get("thresholds", {})
    if thresholds_raw is None:
        thresholds_raw = {}
    if not isinstance(thresholds_raw, dict):
        raise ValueError("Config field 'probes.thresholds' must be a table")

    return ProbeGateSettings(
        file=probe_file,
        target=target,
        mode=mode,
        trials=trials,
        seed=seed,
        allow_unapproved=allow_unapproved,
        thresholds=_parse_thresholds(thresholds_raw),
    )


def load_config(path: Path | None = None) -> ToolSemanticsConfig:
    """Load `.tool-semantics.toml` (or an explicit path). Missing file → empty config."""
    config_path = path
    if config_path is None:
        candidate = Path.cwd() / DEFAULT_CONFIG_NAME
        if not candidate.is_file():
            return ToolSemanticsConfig(config_dir=Path.cwd())
        config_path = candidate
    elif not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    config_dir = config_path.parent.resolve()
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
    probes_raw = raw.get("probes", {})
    if probes_raw is None:
        probes_raw = {}
    if not isinstance(probes_raw, dict):
        raise ValueError("Config field 'probes' must be a table")
    return ToolSemanticsConfig(
        ignore=IgnoreRules(
            codes=_as_str_tuple(ignore_raw.get("codes"), "ignore.codes"),
            subjects=_as_str_tuple(ignore_raw.get("subjects"), "ignore.subjects"),
        ),
        policy=_parse_policy(policy_raw),
        probes=_parse_probes(probes_raw, config_dir=config_dir),
        config_dir=config_dir,
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
