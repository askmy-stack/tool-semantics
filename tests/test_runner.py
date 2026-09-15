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


def test_openai_compatible_runner_requires_credentials() -> None:
    with pytest.raises(ValueError, match="api_key"):
        OpenAICompatibleRunner(model="gpt-test", api_key="")
