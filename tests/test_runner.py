import json
from io import BytesIO

import pytest

from tool_semantics.runner import (
    FakeModelRunner,
    ModelCompletion,
    OpenAICompatibleRunner,
    RunnerConfig,
    RunnerError,
    RunnerMetadata,
    ToolCallRequest,
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


def test_fake_runner_exhausts_scripted_responses() -> None:
    runner = FakeModelRunner([])
    with pytest.raises(RunnerError, match="no remaining"):
        runner.complete(system="s", user="u", tools=[])


def test_openai_compatible_runner_requires_credentials() -> None:
    with pytest.raises(ValueError, match="api_key"):
        OpenAICompatibleRunner(model="gpt-test", api_key="")
    with pytest.raises(ValueError, match="model"):
        OpenAICompatibleRunner(model="", api_key="k")


def test_openai_compatible_runner_success(monkeypatch: pytest.MonkeyPatch) -> None:
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
        ]
    }

    class FakeResponse:
        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        "tool_semantics.runner.urllib.request.urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )
    runner = OpenAICompatibleRunner(model="gpt-test", api_key="sk-test", base_url="http://example/")
    assert runner.metadata.model == "gpt-test"
    completion = runner.complete(
        system="sys",
        user="find bugs",
        tools=[{"type": "function", "function": {"name": "search_issues"}}],
        config=RunnerConfig(seed=9, max_retries=0),
    )
    assert completion.tool_calls[0].name == "search_issues"
    assert completion.tool_calls[0].arguments == {"query": "bugs"}
    assert completion.metadata.run_config["seed"] == 9


def test_openai_compatible_runner_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    def boom(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError(
            "http://example/chat/completions",
            500,
            "err",
            hdrs=None,  # type: ignore[arg-type]
            fp=BytesIO(b"upstream failed"),
        )

    monkeypatch.setattr("tool_semantics.runner.urllib.request.urlopen", boom)
    monkeypatch.setattr("tool_semantics.runner.time.sleep", lambda *_: None)
    runner = OpenAICompatibleRunner(model="gpt-test", api_key="sk-test")
    with pytest.raises(RunnerError, match="failed after retries"):
        runner.complete(
            system="s",
            user="u",
            tools=[],
            config=RunnerConfig(max_retries=1),
        )


def test_openai_compatible_runner_parse_malformed_tool_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "echo", "arguments": "{not-json"}},
                        {"function": {"name": "", "arguments": "{}"}},
                        "skip-me",
                    ]
                }
            }
        ]
    }

    class FakeResponse:
        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        "tool_semantics.runner.urllib.request.urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )
    runner = OpenAICompatibleRunner(model="gpt-test", api_key="sk-test")
    completion = runner.complete(system="s", user="u", tools=[], config=RunnerConfig(max_retries=0))
    assert len(completion.tool_calls) == 1
    assert completion.tool_calls[0].name == "echo"
    assert completion.tool_calls[0].arguments == {}


def test_openai_compatible_runner_parse_dict_and_non_dict_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": "ok",
                    "tool_calls": [
                        {"function": {"name": "echo", "arguments": {"text": "hi"}}},
                        {"function": {"name": "bad", "arguments": ["not", "a", "dict"]}},
                    ],
                }
            }
        ]
    }

    class FakeResponse:
        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        "tool_semantics.runner.urllib.request.urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )
    runner = OpenAICompatibleRunner(model="gpt-test", api_key="sk-test")
    completion = runner.complete(system="s", user="u", tools=[], config=RunnerConfig(max_retries=0))
    assert completion.text == "ok"
    assert len(completion.tool_calls) == 2
    assert completion.tool_calls[0].arguments == {"text": "hi"}
    assert completion.tool_calls[1].arguments == {}
