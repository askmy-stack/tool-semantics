"""Provider-neutral model runner for opt-in model-backed probes.

Deterministic offline users never need a provider SDK: this module depends only
on the standard library plus pydantic (already a core dependency). Provider
adapters speak HTTP directly (OpenAI-compatible chat completions).

Optional extras such as ``tool-semantics[openai]`` are install markers only —
they do not pull SDKs. See ``docs/probes.md`` for the HTTP profile matrix
(OpenAI, Azure OpenAI, local OpenAI-compatible servers).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class RunnerConfig(BaseModel):
    """Configurable timeouts, retries, and cost-sensitive limits."""

    timeout_seconds: float = 30.0
    max_retries: int = 2
    """Number of retries after the first attempt (total attempts = max_retries + 1)."""
    retry_backoff_seconds: float = 0.05
    """Fixed sleep between attempts; tests monkeypatch ``time.sleep``."""
    max_calls: int = 50
    """Hard cap on ``complete()`` invocations for this config / runner session."""
    max_tokens: int | None = None
    """Optional cumulative prompt+completion token budget across calls."""
    max_cost_usd: float | None = None
    """Optional cumulative USD budget when per-1M token rates are set."""
    prompt_cost_per_1m: float | None = None
    completion_cost_per_1m: float | None = None
    temperature: float = 0.0
    seed: int | None = None
    max_output_tokens: int | None = None
    """Forwarded as ``max_tokens`` on the chat-completions request when set."""
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
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0


class RunnerError(RuntimeError):
    """Raised when a model runner fails after retries / limits."""


class HttpProviderProfile(BaseModel):
    """Documented generic HTTP profile for OpenAI-compatible endpoints."""

    name: str
    base_url: str
    auth_mode: Literal["bearer", "api-key"] = "bearer"
    api_key_header: str = "api-key"
    query_params: dict[str, str] = Field(default_factory=dict)
    provider: str = "openai-compatible"
    notes: str = ""


# Public profile matrix — no SDKs required.
HTTP_PROVIDER_PROFILES: dict[str, HttpProviderProfile] = {
    "openai": HttpProviderProfile(
        name="openai",
        base_url="https://api.openai.com/v1",
        auth_mode="bearer",
        provider="openai",
        notes="Official OpenAI Chat Completions API.",
    ),
    "azure-openai": HttpProviderProfile(
        name="azure-openai",
        base_url=("https://{resource}.openai.azure.com/openai/deployments/{deployment}"),
        auth_mode="api-key",
        api_key_header="api-key",
        query_params={"api-version": "2024-02-15-preview"},
        provider="azure-openai",
        notes=(
            "Replace {resource} and {deployment}. Path already includes the "
            "deployment; requests go to /chat/completions?api-version=…"
        ),
    ),
    "local": HttpProviderProfile(
        name="local",
        base_url="http://127.0.0.1:11434/v1",
        auth_mode="bearer",
        provider="local-openai-compatible",
        notes="Ollama, vLLM, LM Studio, and other OpenAI-compatible local servers.",
    ),
}


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


def _run_config_dict(cfg: RunnerConfig, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "timeout_seconds": cfg.timeout_seconds,
        "max_retries": cfg.max_retries,
        "retry_backoff_seconds": cfg.retry_backoff_seconds,
        "max_calls": cfg.max_calls,
        "max_tokens": cfg.max_tokens,
        "max_cost_usd": cfg.max_cost_usd,
        "prompt_cost_per_1m": cfg.prompt_cost_per_1m,
        "completion_cost_per_1m": cfg.completion_cost_per_1m,
        "temperature": cfg.temperature,
        "seed": cfg.seed,
        "max_output_tokens": cfg.max_output_tokens,
        **cfg.extra,
        **extra,
    }
    return payload


def _usage_from_raw(raw: dict[str, Any]) -> tuple[int, int]:
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        return 0, 0
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    prompt_n = prompt if isinstance(prompt, int) else 0
    completion_n = completion if isinstance(completion, int) else 0
    return prompt_n, completion_n


def _estimate_cost_usd(
    cfg: RunnerConfig,
    *,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    cost = 0.0
    if cfg.prompt_cost_per_1m is not None:
        cost += (prompt_tokens / 1_000_000.0) * cfg.prompt_cost_per_1m
    if cfg.completion_cost_per_1m is not None:
        cost += (completion_tokens / 1_000_000.0) * cfg.completion_cost_per_1m
    return cost


def _enforce_budgets(
    *,
    call_count: int,
    total_tokens: int,
    total_cost_usd: float,
    cfg: RunnerConfig,
) -> None:
    if call_count > cfg.max_calls:
        raise RunnerError(f"Exceeded max_calls={cfg.max_calls}")
    if cfg.max_tokens is not None and total_tokens > cfg.max_tokens:
        raise RunnerError(f"Exceeded max_tokens={cfg.max_tokens} (used {total_tokens})")
    if cfg.max_cost_usd is not None and total_cost_usd > cfg.max_cost_usd:
        raise RunnerError(f"Exceeded max_cost_usd={cfg.max_cost_usd} (used {total_cost_usd:.6f})")


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
        self.total_tokens = 0
        self.total_cost_usd = 0.0

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
        _enforce_budgets(
            call_count=self.call_count,
            total_tokens=self.total_tokens,
            total_cost_usd=self.total_cost_usd,
            cfg=cfg,
        )
        if self._index >= len(self._responses):
            raise RunnerError("FakeModelRunner has no remaining scripted responses")
        completion = self._responses[self._index]
        self._index += 1
        prompt_tokens = completion.prompt_tokens
        completion_tokens = completion.completion_tokens
        if prompt_tokens == 0 and completion_tokens == 0:
            prompt_tokens, completion_tokens = _usage_from_raw(completion.raw)
        cost = completion.estimated_cost_usd or _estimate_cost_usd(
            cfg, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        )
        self.total_tokens += prompt_tokens + completion_tokens
        self.total_cost_usd += cost
        _enforce_budgets(
            call_count=self.call_count,
            total_tokens=self.total_tokens,
            total_cost_usd=self.total_cost_usd,
            cfg=cfg,
        )
        return completion.model_copy(
            update={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "estimated_cost_usd": cost,
                "metadata": completion.metadata.model_copy(
                    update={
                        "run_config": _run_config_dict(
                            cfg,
                            total_tokens=self.total_tokens,
                            total_cost_usd=self.total_cost_usd,
                        )
                    }
                ),
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
        auth_mode: Literal["bearer", "api-key"] = "bearer",
        api_key_header: str = "api-key",
        query_params: dict[str, str] | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        if not model:
            raise ValueError("model is required")
        if not api_key:
            raise ValueError("api_key is required")
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._auth_mode = auth_mode
        self._api_key_header = api_key_header
        self._query_params = dict(query_params or {})
        self._default_headers = dict(default_headers or {})
        self.call_count = 0
        self.total_tokens = 0
        self.total_cost_usd = 0.0
        self._metadata = RunnerMetadata(
            provider=provider,
            model=model,
            model_version=model_version,
            run_config={
                "base_url": self._base_url,
                "auth_mode": auth_mode,
                "query_params": self._query_params,
            },
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
        self.call_count += 1
        _enforce_budgets(
            call_count=self.call_count,
            total_tokens=self.total_tokens,
            total_cost_usd=self.total_cost_usd,
            cfg=cfg,
        )
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
        if cfg.max_output_tokens is not None:
            payload["max_tokens"] = cfg.max_output_tokens
        payload.update(cfg.extra)

        last_error: Exception | None = None
        attempts = max(1, cfg.max_retries + 1)
        for attempt in range(attempts):
            try:
                raw = self._post(payload, timeout=cfg.timeout_seconds)
                return self._parse(raw, cfg)
            except (RunnerError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(cfg.retry_backoff_seconds)
        raise RunnerError(
            f"OpenAI-compatible runner failed after retries: {last_error}"
        ) from last_error

    def _auth_headers(self) -> dict[str, str]:
        headers = dict(self._default_headers)
        if self._auth_mode == "api-key":
            headers[self._api_key_header] = self._api_key
        else:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _post(self, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        url = f"{self._base_url}/chat/completions"
        if self._query_params:
            url = f"{url}?{urllib.parse.urlencode(self._query_params)}"
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                **self._auth_headers(),
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
        prompt_tokens, completion_tokens = _usage_from_raw(raw)
        cost = _estimate_cost_usd(
            cfg, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        )
        self.total_tokens += prompt_tokens + completion_tokens
        self.total_cost_usd += cost
        _enforce_budgets(
            call_count=self.call_count,
            total_tokens=self.total_tokens,
            total_cost_usd=self.total_cost_usd,
            cfg=cfg,
        )
        return ModelCompletion(
            tool_calls=tool_calls,
            text=content if isinstance(content, str) else None,
            raw=raw,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=cost,
            metadata=RunnerMetadata(
                provider=self._metadata.provider,
                model=self._model,
                model_version=self._metadata.model_version,
                run_config=_run_config_dict(
                    cfg,
                    base_url=self._base_url,
                    auth_mode=self._auth_mode,
                    total_tokens=self.total_tokens,
                    total_cost_usd=self.total_cost_usd,
                ),
            ),
        )


def openai_compatible_from_profile(
    profile: str | HttpProviderProfile,
    *,
    model: str,
    api_key: str,
    base_url: str | None = None,
    model_version: str | None = None,
    resource: str | None = None,
    deployment: str | None = None,
) -> OpenAICompatibleRunner:
    """Build a runner from a named or concrete :class:`HttpProviderProfile`."""
    if isinstance(profile, str):
        try:
            resolved = HTTP_PROVIDER_PROFILES[profile]
        except KeyError as exc:
            known = ", ".join(sorted(HTTP_PROVIDER_PROFILES))
            raise ValueError(f"Unknown HTTP provider profile {profile!r}; known: {known}") from exc
    else:
        resolved = profile
    url = base_url or resolved.base_url
    if "{resource}" in url or "{deployment}" in url:
        if not resource or not deployment:
            raise ValueError(
                "Azure OpenAI profile requires resource= and deployment= "
                "(or pass an already-expanded base_url=)"
            )
        url = url.format(resource=resource, deployment=deployment)
    return OpenAICompatibleRunner(
        model=model,
        api_key=api_key,
        base_url=url,
        provider=resolved.provider,
        model_version=model_version,
        auth_mode=resolved.auth_mode,
        api_key_header=resolved.api_key_header,
        query_params=resolved.query_params,
    )


__all__ = [
    "HTTP_PROVIDER_PROFILES",
    "FakeModelRunner",
    "HttpProviderProfile",
    "ModelCompletion",
    "ModelRunner",
    "OpenAICompatibleRunner",
    "RunnerConfig",
    "RunnerError",
    "RunnerMetadata",
    "ToolCallRequest",
    "openai_compatible_from_profile",
]
