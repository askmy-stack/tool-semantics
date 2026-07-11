from pathlib import Path

from tool_semantics.adapters import (
    ArgumentMap,
    CompatibilityProxy,
    EnumMap,
    MigrationAdapter,
    OutputWrapper,
    ToolAlias,
)
from tool_semantics.config import load_config
from tool_semantics.diff import Change, CompatibilityReport, Severity
from tool_semantics.policy import FailSeverity, ReleasePolicy, policy_from_name
from tool_semantics.probes import Probe, ProbeKind, evaluate_probes
from tool_semantics.scanner import capture_manifest


def test_release_policy_strict_fails_on_warning() -> None:
    report = CompatibilityReport(
        baseline="1",
        candidate="2",
        changes=[
            Change(
                severity=Severity.WARNING,
                code="tool.description_changed",
                subject="t",
                message="changed",
            )
        ],
    )
    assert report.is_compatible
    assert ReleasePolicy(fail_at_or_above=FailSeverity.WARNING).should_fail(report)
    assert not ReleasePolicy(fail_at_or_above=FailSeverity.BREAKING).should_fail(report)


def test_policy_from_name_aliases() -> None:
    assert policy_from_name("strict").fail_at_or_above is FailSeverity.WARNING
    assert policy_from_name("permissive").fail_at_or_above is FailSeverity.NONE


def test_config_loads_policy(tmp_path: Path) -> None:
    path = tmp_path / "rules.toml"
    path.write_text('[policy]\nfail_at_or_above = "warning"\n', encoding="utf-8")
    config = load_config(path)
    assert config.policy.fail_at_or_above is FailSeverity.WARNING


def test_compatibility_proxy_translates_call_and_output() -> None:
    adapter = MigrationAdapter(
        aliases=[ToolAlias(**{"from": "search_issues", "to": "find_work_items"})],
        arguments=[
            ArgumentMap(
                tool="find_work_items",
                rename={"state": "status"},
                defaults={"limit": 10},
            )
        ],
        enums=[
            EnumMap(
                tool="find_work_items",
                parameter="status",
                values={"open": "todo", "closed": "done"},
            )
        ],
        outputs=[
            OutputWrapper(
                tool="find_work_items",
                rename_fields={"items": "results"},
                wrap_as="data",
            )
        ],
    )
    proxy = CompatibilityProxy(adapter)
    tool, args = proxy.route_call("search_issues", {"query": "bug", "state": "open"})
    assert tool == "find_work_items"
    assert args == {"query": "bug", "status": "todo", "limit": 10}
    wrapped = proxy.route_result("find_work_items", {"items": [1, 2], "extra": True})
    assert wrapped == {"data": {"extra": True, "results": [1, 2]}}


def test_probe_side_effect_max_risk() -> None:
    snapshot = capture_manifest(Path("examples/github_server_v1.json"))
    report = evaluate_probes(
        snapshot,
        [
            Probe(
                id="read-only-create",
                intent="create issue",
                expected_tool="create_issue",
                max_risk="read_only",
            )
        ],
    )
    assert not report.passed
    assert "exceeds" in report.failures[0].message


def test_probe_requires_confirmation_message() -> None:
    snapshot = capture_manifest(Path("examples/github_server_v1.json"))
    report = evaluate_probes(
        snapshot,
        [
            Probe(
                id="confirm-create",
                intent="create issue",
                expected_tool="create_issue",
                requires_confirmation=True,
                kind=ProbeKind.POSITIVE,
            )
        ],
    )
    assert report.passed
    assert "confirmation required" in report.results[0].message.lower()
