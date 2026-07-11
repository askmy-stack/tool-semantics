from pathlib import Path

from tool_semantics.config import (
    IgnoreRules,
    ToolSemanticsConfig,
    apply_ignore_rules,
    load_config,
)
from tool_semantics.diff import Change, CompatibilityReport, Severity, compare_snapshots
from tool_semantics.scanner import capture_manifest


def test_load_config_missing_returns_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = load_config()
    assert config.ignore.codes == ()
    assert config.ignore.subjects == ()


def test_load_config_from_path(tmp_path: Path) -> None:
    path = tmp_path / "rules.toml"
    path.write_text(
        (
            "[ignore]\n"
            'codes = ["tool.description_changed"]\n'
            'subjects = ["experimental_*", "*.debug"]\n'
        ),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.ignore.codes == ("tool.description_changed",)
    assert config.ignore.subjects == ("experimental_*", "*.debug")


def test_ignore_by_code_downgrades_breaking() -> None:
    baseline = capture_manifest(Path("examples/github_server_v1.json"))
    candidate = capture_manifest(Path("examples/github_server_v2.json"))
    report = compare_snapshots(baseline, candidate)
    assert not report.is_compatible
    filtered = apply_ignore_rules(
        report,
        ToolSemanticsConfig(ignore=IgnoreRules(codes=("tool.removed", "parameter.added_required"))),
    )
    # Other breaks may remain; ensure ignored codes are info and prefixed.
    for change in filtered.changes:
        if change.code in {"tool.removed", "parameter.added_required"}:
            assert change.severity == Severity.INFO
            assert change.message.startswith("[ignored]")


def test_ignore_by_subject_glob() -> None:
    report = CompatibilityReport(
        baseline="1",
        candidate="2",
        changes=[
            Change(
                severity=Severity.BREAKING,
                code="tool.removed",
                subject="experimental_search",
                message="gone",
            ),
            Change(
                severity=Severity.BREAKING,
                code="tool.removed",
                subject="search_issues",
                message="gone",
            ),
        ],
    )
    filtered = apply_ignore_rules(
        report,
        ToolSemanticsConfig(ignore=IgnoreRules(subjects=("experimental_*",))),
    )
    by_subject = {change.subject: change for change in filtered.changes}
    assert by_subject["experimental_search"].severity == Severity.INFO
    assert by_subject["search_issues"].severity == Severity.BREAKING
    assert not filtered.is_compatible
