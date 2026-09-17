"""Provider-neutral model runner for opt-in model-backed probes.

Deterministic offline users never need a provider SDK: this module depends only
on the standard library plus pydantic (already a core dependency). Provider
adapters speak HTTP directly (OpenAI-compatible chat completions).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from tool_semantics.redact import redact_mapping


class RunnerConfig(BaseModel):
    """Configurable timeouts, retries, and cost-sensitive limits."""

    timeout_seconds: float = 30.0
    max_retries: int = 2
    max_calls: int = 50
    temperature: float = 0.0
    seed: int | None = None
    # Persist provider JSON on ModelCompletion.raw (redacted). Default off (#66).
    include_raw: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class RunnerMetadata(BaseModel):
    provider: str
    model: str
    model_version: str | None = None
    run_config: dict[str, Any] = Field(default_factory=dict)


class ToolCallRequest(BaseModel):
    """A single tool call proposed by a model."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ModelCompletion(BaseModel):
    """Normalized runner output — transport-agnostic."""

    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    text: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    metadata: RunnerMetadata


class RunnerError(RuntimeError):
    """Raised when a model runner fails after retries / limits."""


@runtime_checkable
class ModelRunner(Protocol):
    """Separates provider transport from probe evaluation."""

    @property
    def metadata(self) -> RunnerMetadata: ...

    def complete(
        self,
        *,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
        config: RunnerConfig | None = None,
    ) -> ModelCompletion: ...


class FakeModelRunner:
    """Deterministic in-memory runner for unit tests (no network)."""

    def __init__(
        self,
        responses: list[ModelCompletion] | None = None,
        *,
        provider: str = "fake",
        model: str = "fake-model",
        model_version: str = "test",
    ) -> None:
        self._responses = list(responses or [])
        self._index = 0
        self._metadata = RunnerMetadata(
            provider=provider,
            model=model,
            model_version=model_version,
            run_config={},
        )
        self.call_count = 0

    @property
    def metadata(self) -> RunnerMetadata:
        return self._metadata

    def complete(
        self,
        *,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
        config: RunnerConfig | None = None,
    ) -> ModelCompletion:
        del system, user, tools  # unused — scripted responses
        cfg = config or RunnerConfig()
        self.call_count += 1
        if self.call_count > cfg.max_calls:
            raise RunnerError(f"Exceeded max_calls={cfg.max_calls}")
        if self._index >= len(self._responses):
            raise RunnerError("FakeModelRunner has no remaining scripted responses")
        completion = self._responses[self._index]
        self._index += 1
        # Preserve scripted metadata but attach active run config.
        return completion.model_copy(
            update={
                "metadata": completion.metadata.model_copy(
                    update={
                        "run_config": {
                            "timeout_seconds": cfg.timeout_seconds,
                            "max_retries": cfg.max_retries,
                            "max_calls": cfg.max_calls,
                            "temperature": cfg.temperature,
                            "seed": cfg.seed,
                            **cfg.extra,
                        }
                    }
                )
            }
        )


class OpenAICompatibleRunner:
    """HTTP adapter for OpenAI-compatible chat completions (stdlib only)."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        provider: str = "openai-compatible",
        model_version: str | None = None,
    ) -> None:
        if not model:
            raise ValueError("model is required")
        if not api_key:
            raise ValueError("api_key is required")
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._metadata = RunnerMetadata(
            provider=provider,
            model=model,
            model_version=model_version,
            run_config={"base_url": self._base_url},
        )

    @property
    def metadata(self) -> RunnerMetadata:
        return self._metadata

    def complete(
        self,
        *,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
        config: RunnerConfig | None = None,
    ) -> ModelCompletion:
        cfg = config or RunnerConfig()
        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": cfg.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": tools,
            "tool_choice": "auto",
        }
        if cfg.seed is not None:
            payload["seed"] = cfg.seed
        payload.update(cfg.extra)

        last_error: Exception | None = None
        attempts = max(1, cfg.max_retries + 1)
        for _ in range(attempts):
            try:
                raw = self._post(payload, timeout=cfg.timeout_seconds)
                return self._parse(raw, cfg)
            except (RunnerError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                time.sleep(0.05)
        raise RunnerError(
            f"OpenAI-compatible runner failed after retries: {last_error}"
        ) from last_error

    def _post(self, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                parsed: dict[str, Any] = json.loads(response.read().decode("utf-8"))
                return parsed
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RunnerError(f"HTTP {exc.code}: {detail}") from exc

    def _parse(self, raw: dict[str, Any], cfg: RunnerConfig) -> ModelCompletion:
        choices = raw.get("choices") or []
        message: dict[str, Any] = {}
        if choices and isinstance(choices[0], dict):
            maybe = choices[0].get("message")
            if isinstance(maybe, dict):
                message = maybe
        tool_calls: list[ToolCallRequest] = []
        for item in message.get("tool_calls") or []:
            if not isinstance(item, dict):
                continue
            function_obj = item.get("function")
            function: dict[str, Any] = function_obj if isinstance(function_obj, dict) else {}
            name = function.get("name")
            if not isinstance(name, str) or not name:
                continue
            arguments_raw = function.get("arguments", "{}")
            try:
                if isinstance(arguments_raw, str):
                    arguments = json.loads(arguments_raw)
                else:
                    arguments = arguments_raw
            except json.JSONDecodeError:
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            tool_calls.append(ToolCallRequest(name=name, arguments=arguments))
        content = message.get("content")
        persisted_raw: dict[str, Any] = {}
        if cfg.include_raw:
            persisted_raw = redact_mapping(raw) if isinstance(raw, dict) else {}
        return ModelCompletion(
            tool_calls=tool_calls,
            text=content if isinstance(content, str) else None,
            raw=persisted_raw,
            metadata=RunnerMetadata(
                provider=self._metadata.provider,
                model=self._model,
                model_version=self._metadata.model_version,
                run_config={
                    "timeout_seconds": cfg.timeout_seconds,
                    "max_retries": cfg.max_retries,
                    "max_calls": cfg.max_calls,
                    "temperature": cfg.temperature,
                    "seed": cfg.seed,
                    "include_raw": cfg.include_raw,
                    "base_url": self._base_url,
                    **cfg.extra,
                },
            ),
        )


__all__ = [
    "FakeModelRunner",
    "ModelCompletion",
    "ModelRunner",
    "OpenAICompatibleRunner",
    "RunnerConfig",
    "RunnerError",
    "RunnerMetadata",
    "ToolCallRequest",
]
