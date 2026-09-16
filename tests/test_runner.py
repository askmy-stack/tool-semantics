"""Tests for provider-neutral model runners (no live network)."""

from __future__ import annotations

import json
from io import BytesIO

import pytest

from tool_semantics.runner import (
    HTTP_PROVIDER_PROFILES,
    FakeModelRunner,
    ModelCompletion,
    OpenAICompatibleRunner,
    RunnerConfig,
    RunnerError,
    RunnerMetadata,
    ToolCallRequest,
    openai_compatible_from_profile,
)


def test_fake_runner_records_run_config() -> None:
    runner = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[ToolCallRequest(name="echo", arguments={"text": "hi"})],
                metadata=RunnerMetadata(provider="fake", model="fake-model", model_version="t"),
            )
        ]
    )
    completion = runner.complete(
        system="s",
        user="u",
        tools=[],
        config=RunnerConfig(timeout_seconds=1.5, max_retries=1, seed=42),
    )
    assert completion.metadata.provider == "fake"
    assert completion.metadata.model == "fake-model"
    assert completion.metadata.run_config["seed"] == 42
    assert completion.metadata.run_config["timeout_seconds"] == 1.5
    assert completion.metadata.run_config["retry_backoff_seconds"] == 0.05


def test_fake_runner_respects_max_calls() -> None:
    runner = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[],
                metadata=RunnerMetadata(provider="fake", model="m"),
            )
            for _ in range(3)
        ]
    )
    with pytest.raises(RunnerError, match="max_calls"):
        runner.complete(system="s", user="u", tools=[], config=RunnerConfig(max_calls=0))


def test_fake_runner_respects_max_tokens_and_cost() -> None:
    runner = FakeModelRunner(
        [
            ModelCompletion(
                tool_calls=[],
                prompt_tokens=80,
                completion_tokens=20,
                metadata=RunnerMetadata(provider="fake", model="m"),
            ),
            ModelCompletion(
                tool_calls=[],
                prompt_tokens=10,
                completion_tokens=10,
                metadata=RunnerMetadata(provider="fake", model="m"),
            ),
        ]
    )
    cfg = RunnerConfig(
        max_tokens=100,
        max_cost_usd=0.001,
        prompt_cost_per_1m=5.0,
        completion_cost_per_1m=15.0,
    )
    first = runner.complete(system="s", user="u", tools=[], config=cfg)
    assert first.metadata.run_config["total_tokens"] == 100
    assert first.estimated_cost_usd > 0
    with pytest.raises(RunnerError, match="max_tokens|max_cost_usd"):
        runner.complete(system="s", user="u", tools=[], config=cfg)


def test_openai_compatible_runner_requires_credentials() -> None:
    with pytest.raises(ValueError, match="api_key"):
        OpenAICompatibleRunner(model="gpt-test", api_key="")
    with pytest.raises(ValueError, match="model"):
        OpenAICompatibleRunner(model="", api_key="k")


def test_openai_compatible_runner_success_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "function": {
                                "name": "search_issues",
                                "arguments": '{"query": "bugs"}',
                            }
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3},
    }
    captured: dict[str, object] = {}

    class FakeResponse:
        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(request: object, timeout: float = 0) -> FakeResponse:
        captured["timeout"] = timeout
        captured["url"] = getattr(request, "full_url", None)
        captured["headers"] = dict(getattr(request, "headers", {}))
        return FakeResponse()

    monkeypatch.setattr("tool_semantics.runner.urllib.request.urlopen", fake_urlopen)
    runner = OpenAICompatibleRunner(
        model="gpt-test",
        api_key="sk-test",
        base_url="http://example/",
    )
    completion = runner.complete(
        system="sys",
        user="find bugs",
        tools=[{"type": "function", "function": {"name": "search_issues"}}],
        config=RunnerConfig(
            seed=9,
            max_retries=0,
            max_output_tokens=128,
            prompt_cost_per_1m=1.0,
            completion_cost_per_1m=2.0,
        ),
    )
    assert completion.tool_calls[0].name == "search_issues"
    assert completion.tool_calls[0].arguments == {"query": "bugs"}
    assert completion.prompt_tokens == 12
    assert completion.completion_tokens == 3
    assert completion.metadata.run_config["total_tokens"] == 15
    assert completion.metadata.run_config["max_output_tokens"] == 128
    assert "Authorization" in captured["headers"] or "authorization" in {
        k.lower() for k in captured["headers"]
    }


def test_openai_compatible_runner_retries_with_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    sleeps: list[float] = []
    calls = {"n": 0}

    def boom(*args: object, **kwargs: object) -> None:
        calls["n"] += 1
        raise urllib.error.HTTPError(
            "http://example/chat/completions",
            500,
            "err",
            hdrs=None,  # type: ignore[arg-type]
            fp=BytesIO(b"upstream failed"),
        )

    monkeypatch.setattr("tool_semantics.runner.urllib.request.urlopen", boom)
    monkeypatch.setattr("tool_semantics.runner.time.sleep", lambda s: sleeps.append(s))
    runner = OpenAICompatibleRunner(model="gpt-test", api_key="sk-test")
    with pytest.raises(RunnerError, match="failed after retries"):
        runner.complete(
            system="s",
            user="u",
            tools=[],
            config=RunnerConfig(max_retries=2, retry_backoff_seconds=0.2),
        )
    assert calls["n"] == 3
    assert sleeps == [0.2, 0.2]


def test_openai_compatible_runner_max_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def read(self) -> bytes:
            return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        "tool_semantics.runner.urllib.request.urlopen",
        lambda *a, **k: FakeResponse(),
    )
    runner = OpenAICompatibleRunner(model="gpt-test", api_key="sk-test")
    runner.complete(system="s", user="u", tools=[], config=RunnerConfig(max_calls=1, max_retries=0))
    with pytest.raises(RunnerError, match="max_calls"):
        runner.complete(
            system="s", user="u", tools=[], config=RunnerConfig(max_calls=1, max_retries=0)
        )


def test_http_provider_profiles_and_azure_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    assert set(HTTP_PROVIDER_PROFILES) >= {"openai", "azure-openai", "local"}
    captured: dict[str, object] = {}

    class FakeResponse:
        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [{"message": {"content": "hi"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }
            ).encode()

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(request: object, timeout: float = 0) -> FakeResponse:
        captured["url"] = getattr(request, "full_url", None)
        headers = {str(k).lower(): v for k, v in dict(getattr(request, "headers", {})).items()}
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("tool_semantics.runner.urllib.request.urlopen", fake_urlopen)
    runner = openai_compatible_from_profile(
        "azure-openai",
        model="gpt-4o-mini",
        api_key="azure-key",
        resource="contoso",
        deployment="gpt-4o-mini",
    )
    assert runner.metadata.provider == "azure-openai"
    runner.complete(system="s", user="u", tools=[], config=RunnerConfig(max_retries=0))
    url = str(captured["url"])
    assert "contoso.openai.azure.com" in url
    assert "api-version=" in url
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers.get("api-key") == "azure-key"


def test_openai_compatible_from_profile_requires_azure_parts() -> None:
    with pytest.raises(ValueError, match="resource"):
        openai_compatible_from_profile(
            "azure-openai",
            model="m",
            api_key="k",
        )
    with pytest.raises(ValueError, match="Unknown HTTP provider profile"):
        openai_compatible_from_profile("nope", model="m", api_key="k")


def test_local_profile_factory() -> None:
    runner = openai_compatible_from_profile(
        "local",
        model="llama3.2",
        api_key="ollama",
    )
    assert runner.metadata.provider == "local-openai-compatible"
    assert "11434" in runner.metadata.run_config["base_url"]
