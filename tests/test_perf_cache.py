"""Tests for parallel probes, completion cache, cost, and scale harness (#100)."""

from __future__ import annotations

from pathlib import Path

from tool_semantics.benchmarks import (
    render_scale_benchmark_markdown,
    run_scale_benchmark,
    time_compare,
    time_offline_probes,
    time_snapshot_build,
)
from tool_semantics.cache import (
    ProbeCompletionCache,
    build_cache_key,
    snapshot_hash,
)
from tool_semantics.cost import extract_usage, summarize_costs
from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract, ToolParameter
from tool_semantics.probes import Probe, ProbeKind, evaluate_probes_with_model
from tool_semantics.runner import (
    FakeModelRunner,
    ModelCompletion,
    RunnerConfig,
    RunnerMetadata,
    ToolCallRequest,
)


def _snap() -> InterfaceSnapshot:
    return InterfaceSnapshot(
        server_name="demo",
        tools=[
            ToolContract(
                name="search_issues",
                description="Search",
                parameters=[ToolParameter(name="query", schema={"type": "string"}, required=True)],
                risk=RiskLevel.READ_ONLY,
            ),
            ToolContract(
                name="create_issue",
                description="Create",
                parameters=[ToolParameter(name="title", schema={"type": "string"}, required=True)],
                risk=RiskLevel.EXTERNAL_WRITE,
            ),
        ],
    )


def _probe(pid: str, intent: str, tool: str) -> Probe:
    return Probe(
        id=pid,
        intent=intent,
        kind=ProbeKind.POSITIVE,
        expected_tool=tool,
        required_params=["query"] if tool == "search_issues" else ["title"],
        approved=True,
        approved_by="ci",
    )


def _completion(tool: str, args: dict, *, usage: dict | None = None) -> ModelCompletion:
    raw = {"usage": usage} if usage else {}
    return ModelCompletion(
        tool_calls=[ToolCallRequest(name=tool, arguments=args)],
        raw=raw,
        metadata=RunnerMetadata(provider="fake", model="fake-model"),
    )


def test_cache_hit_and_miss(tmp_path: Path) -> None:
    cache = ProbeCompletionCache(tmp_path / "cache")
    snap = _snap()
    probes = [_probe("s", "find bugs", "search_issues")]
    usage = {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
    runner = FakeModelRunner([_completion("search_issues", {"query": "bugs"}, usage=usage)])
    first = evaluate_probes_with_model(snap, probes, runner, cache=cache)
    assert first.results[0].cache_hit is False
    assert first.cache is not None
    assert first.cache["misses"] == 1
    assert first.cost is not None
    assert first.cost["total_tokens"] == 12

    # Second run should hit cache and not consume another scripted response.
    runner2 = FakeModelRunner([])  # would fail if complete() called
    second = evaluate_probes_with_model(snap, probes, runner2, cache=cache)
    assert second.results[0].cache_hit is True
    assert second.results[0].selected_tool == "search_issues"
    assert second.cache["hits"] >= 1


def test_cache_key_includes_seed_and_temperature() -> None:
    tools = [{"type": "function", "function": {"name": "x"}}]
    key_a = build_cache_key(
        model="m",
        system="s",
        user="u",
        tools=tools,
        snapshot_digest="abc",
        config=RunnerConfig(temperature=0.0, seed=1),
    )
    key_b = build_cache_key(
        model="m",
        system="s",
        user="u",
        tools=tools,
        snapshot_digest="abc",
        config=RunnerConfig(temperature=0.2, seed=1),
    )
    key_c = build_cache_key(
        model="m",
        system="s",
        user="u",
        tools=tools,
        snapshot_digest="abc",
        config=RunnerConfig(temperature=0.0, seed=2),
    )
    assert key_a != key_b
    assert key_a != key_c
    assert len(snapshot_hash(_snap())) == 64


def test_parallel_workers_preserve_order() -> None:
    snap = _snap()
    probes = [
        _probe("a", "find bugs", "search_issues"),
        _probe("b", "open ticket", "create_issue"),
        _probe("c", "search again", "search_issues"),
    ]

    class IntentRunner:
        def __init__(self) -> None:
            self._metadata = RunnerMetadata(provider="fake", model="intent")

        @property
        def metadata(self) -> RunnerMetadata:
            return self._metadata

        def complete(
            self,
            *,
            system: str,
            user: str,
            tools: list,
            config: RunnerConfig | None = None,
        ) -> ModelCompletion:
            del system, tools, config
            if "ticket" in user:
                return _completion("create_issue", {"title": "t"})
            return _completion("search_issues", {"query": "bugs"})

    report = evaluate_probes_with_model(snap, probes, IntentRunner(), workers=3)
    assert [item.probe_id for item in report.results] == ["a", "b", "c"]
    assert [item.selected_tool for item in report.results] == [
        "search_issues",
        "create_issue",
        "search_issues",
    ]
    assert all(item.passed for item in report.results)


def test_cost_summary_missing_usage() -> None:
    completion = _completion("search_issues", {"query": "x"})
    assert extract_usage(completion) == {}
    summary = summarize_costs([completion])
    assert summary.calls_missing_usage == 1
    assert summary.total_tokens is None


def test_scale_benchmark_helpers_small() -> None:
    # Keep sizes tiny so CI stays fast; full 5k run is via scripts/bench_scale.py.
    snap = time_snapshot_build(10)
    assert snap["tools"] == 10
    assert snap["elapsed_seconds"] >= 0
    cmp = time_compare(10)
    assert cmp["change_count"] >= 1
    probes = time_offline_probes(10, probe_count=3)
    assert probes["passed"] == 1
    rows = run_scale_benchmark((10, 25), include_probes=True)
    assert len(rows) == 2
    md = render_scale_benchmark_markdown(rows)
    assert "Scale benchmark" in md
    assert "10" in md
