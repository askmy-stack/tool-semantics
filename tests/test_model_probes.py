from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract, ToolParameter
from tool_semantics.probes import (
    Probe,
    ProbeKind,
    compute_probe_metrics,
    evaluate_probes,
    evaluate_probes_with_model,
    run_probe_trials,
)
from tool_semantics.report import (
    render_probe_metrics_json,
    render_probe_metrics_markdown,
    render_stability_markdown,
)
from tool_semantics.runner import (
    FakeModelRunner,
    ModelCompletion,
    RunnerMetadata,
    ToolCallRequest,
)


def _snapshot() -> InterfaceSnapshot:
    return InterfaceSnapshot(
        server_name="demo",
        tools=[
            ToolContract(
                name="search_issues",
                description="Search GitHub issues by query",
                parameters=[
                    ToolParameter(name="query", schema={"type": "string"}, required=True)
                ],
                risk=RiskLevel.READ_ONLY,
            ),
            ToolContract(
                name="create_issue",
                description="Create a GitHub issue",
                parameters=[
                    ToolParameter(name="title", schema={"type": "string"}, required=True)
                ],
                risk=RiskLevel.EXTERNAL_WRITE,
            ),
        ],
    )


def test_offline_probes_still_work() -> None:
    report = evaluate_probes(
        _snapshot(),
        [
            Probe(
                id="search",
                intent="find bugs",
                expected_tool="search_issues",
                required_params=["query"],
            )
        ],
    )
    assert report.passed


def test_model_backed_requires_approval() -> None:
    runner = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "bugs"})],
                metadata=RunnerMetadata(provider="fake", model="fake-model"),
            )
        ]
    )
    report = evaluate_probes_with_model(
        _snapshot(),
        [Probe(id="search", intent="find bugs", expected_tool="search_issues")],
        runner,
    )
    assert report.results[0].outcome.value == "skipped"
    assert runner.call_count == 0


def test_model_backed_positive_and_negative() -> None:
    runner = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "bugs"})],
                metadata=RunnerMetadata(provider="fake", model="fake-model", model_version="1"),
            ),
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "x"})],
                metadata=RunnerMetadata(provider="fake", model="fake-model"),
            ),
        ]
    )
    report = evaluate_probes_with_model(
        _snapshot(),
        [
            Probe(
                id="pos",
                intent="find bugs",
                expected_tool="search_issues",
                required_params=["query"],
                approved=True,
                approved_by="reviewer",
            ),
            Probe(
                id="neg",
                intent="do not create",
                kind=ProbeKind.NEGATIVE,
                forbidden_tools=["create_issue"],
                approved=True,
            ),
        ],
        runner,
    )
    assert report.passed
    assert report.results[0].selected_tool == "search_issues"
    assert report.results[0].arguments == {"query": "bugs"}
    assert report.results[0].runner is not None
    assert report.results[0].runner.model == "fake-model"


def test_probe_metrics_distinguish_missing_data() -> None:
    runner = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[],
                metadata=RunnerMetadata(provider="fake", model="m"),
            ),
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "a"})],
                metadata=RunnerMetadata(provider="fake", model="m"),
            ),
        ]
    )
    report = evaluate_probes_with_model(
        _snapshot(),
        [
            Probe(id="missing", intent="?", expected_tool="search_issues", approved=True),
            Probe(
                id="ok",
                intent="search",
                expected_tool="search_issues",
                required_params=["query"],
                approved=True,
            ),
        ],
        runner,
    )
    metrics = compute_probe_metrics(report.results)
    assert metrics.missing_data_count == 1
    assert metrics.evaluated_count == 1
    assert metrics.tool_selection_accuracy == 1.0
    assert metrics.argument_validity_rate == 1.0
    md = render_probe_metrics_markdown(metrics)
    assert "Missing data: 1" in md
    assert "n/a" not in md or "Tool-selection accuracy" in md
    payload = render_probe_metrics_json(metrics)
    assert payload["missing_data_count"] == 1


def test_stability_stable_unstable_and_deterministic_failure() -> None:
    # Stable success
    stable_runner = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "a"})],
                metadata=RunnerMetadata(provider="fake", model="m"),
            )
            for _ in range(3)
        ]
    )
    stable = run_probe_trials(
        _snapshot(),
        [
            Probe(
                id="stable",
                intent="search",
                expected_tool="search_issues",
                required_params=["query"],
                approved=True,
            )
        ],
        stable_runner,
        trial_count=3,
        seed=7,
    )
    assert stable.summaries[0].stability_score == 1.0
    assert not stable.summaries[0].unstable
    assert stable.seed == 7

    # Unstable selections
    unstable_runner = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "a"})],
                metadata=RunnerMetadata(provider="fake", model="m"),
            ),
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="create_issue", arguments={"title": "x"})],
                metadata=RunnerMetadata(provider="fake", model="m"),
            ),
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "b"})],
                metadata=RunnerMetadata(provider="fake", model="m"),
            ),
        ]
    )
    unstable = run_probe_trials(
        _snapshot(),
        [
            Probe(
                id="unstable",
                intent="search",
                expected_tool="search_issues",
                required_params=["query"],
                approved=True,
            )
        ],
        unstable_runner,
        trial_count=3,
    )
    assert unstable.summaries[0].unstable
    md = render_stability_markdown(unstable)
    assert "Unstable probes" in md

    # Deterministic wrong tool
    fail_runner = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="create_issue", arguments={"title": "x"})],
                metadata=RunnerMetadata(provider="fake", model="m"),
            )
            for _ in range(3)
        ]
    )
    failed = run_probe_trials(
        _snapshot(),
        [
            Probe(
                id="det-fail",
                intent="search",
                expected_tool="search_issues",
                approved=True,
            )
        ],
        fail_runner,
        trial_count=3,
    )
    assert failed.summaries[0].deterministic_failure
    assert not failed.summaries[0].unstable
    assert "Deterministic failures" in render_stability_markdown(failed)
