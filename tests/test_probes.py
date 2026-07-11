from pathlib import Path

from tool_semantics.models import InterfaceSnapshot, ToolContract, ToolParameter
from tool_semantics.probes import Probe, ProbeKind, evaluate_probes
from tool_semantics.scanner import capture_manifest


def test_positive_probe_passes_when_tool_and_params_exist() -> None:
    snapshot = capture_manifest(Path("examples/github_server_v1.json"))
    report = evaluate_probes(
        snapshot,
        [
            Probe(
                id="search",
                intent="find open github issues",
                kind=ProbeKind.POSITIVE,
                expected_tool="search_issues",
                required_params=["query"],
            )
        ],
    )
    assert report.passed


def test_positive_probe_fails_when_tool_missing() -> None:
    snapshot = InterfaceSnapshot(server_name="empty", tools=[])
    report = evaluate_probes(
        snapshot,
        [Probe(id="x", intent="do thing", expected_tool="missing")],
    )
    assert not report.passed
    assert "not found" in report.failures[0].message


def test_negative_probe_fails_when_forbidden_present() -> None:
    snapshot = capture_manifest(Path("examples/github_server_v1.json"))
    report = evaluate_probes(
        snapshot,
        [
            Probe(
                id="no-create",
                intent="must not create issues",
                kind=ProbeKind.NEGATIVE,
                forbidden_tools=["create_issue"],
            )
        ],
    )
    assert not report.passed


def test_ambiguous_probe_notes_collisions() -> None:
    snapshot = InterfaceSnapshot(
        server_name="demo",
        tools=[
            ToolContract(
                name="search_a",
                description="Search GitHub issues by query",
                parameters=[ToolParameter(name="query", schema={"type": "string"})],
            ),
            ToolContract(
                name="search_b",
                description="Search GitHub issues with filters",
                parameters=[ToolParameter(name="query", schema={"type": "string"})],
            ),
        ],
    )
    report = evaluate_probes(
        snapshot,
        [
            Probe(
                id="amb",
                intent="search github issues",
                kind=ProbeKind.AMBIGUOUS,
                expected_tool="search_a",
            )
        ],
    )
    assert report.passed
    assert "collisions" in report.results[0].message.lower()
