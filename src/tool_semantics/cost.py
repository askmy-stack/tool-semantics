"""Optional token / cost aggregation from provider metadata (#100)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from tool_semantics.runner import ModelCompletion


class CostSummary(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    calls_with_usage: int = 0
    calls_missing_usage: int = 0
    source: str = "provider_metadata"
    notes: list[str] = Field(default_factory=list)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def extract_usage(completion: ModelCompletion) -> dict[str, int]:
    """Pull token counts from OpenAI-style ``raw.usage`` when present."""
    usage = completion.raw.get("usage") if isinstance(completion.raw, dict) else None
    if not isinstance(usage, dict):
        # Some adapters stash usage under metadata.run_config.
        usage = completion.metadata.run_config.get("usage")
    if not isinstance(usage, dict):
        return {}
    out: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        parsed = _as_int(usage.get(key))
        if parsed is not None:
            out[key] = parsed
    if "total_tokens" not in out and out:
        out["total_tokens"] = out.get("prompt_tokens", 0) + out.get("completion_tokens", 0)
    return out


def estimate_cost_usd(
    *,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    prompt_rate_per_mtok: float | None = None,
    completion_rate_per_mtok: float | None = None,
) -> float | None:
    """Optional USD estimate when per-million-token rates are supplied."""
    if prompt_rate_per_mtok is None and completion_rate_per_mtok is None:
        return None
    cost = 0.0
    if prompt_tokens is not None and prompt_rate_per_mtok is not None:
        cost += (prompt_tokens / 1_000_000.0) * prompt_rate_per_mtok
    if completion_tokens is not None and completion_rate_per_mtok is not None:
        cost += (completion_tokens / 1_000_000.0) * completion_rate_per_mtok
    return round(cost, 6)


def summarize_costs(
    completions: list[ModelCompletion],
    *,
    prompt_rate_per_mtok: float | None = None,
    completion_rate_per_mtok: float | None = None,
) -> CostSummary:
    prompt_total = 0
    completion_total = 0
    total_tokens = 0
    with_usage = 0
    missing = 0
    for completion in completions:
        usage = extract_usage(completion)
        if not usage:
            missing += 1
            continue
        with_usage += 1
        prompt_total += usage.get("prompt_tokens", 0)
        completion_total += usage.get("completion_tokens", 0)
        total_tokens += usage.get("total_tokens", 0)
    summary = CostSummary(
        prompt_tokens=prompt_total if with_usage else None,
        completion_tokens=completion_total if with_usage else None,
        total_tokens=total_tokens if with_usage else None,
        calls_with_usage=with_usage,
        calls_missing_usage=missing,
        estimated_cost_usd=estimate_cost_usd(
            prompt_tokens=prompt_total if with_usage else None,
            completion_tokens=completion_total if with_usage else None,
            prompt_rate_per_mtok=prompt_rate_per_mtok,
            completion_rate_per_mtok=completion_rate_per_mtok,
        ),
    )
    if missing and not with_usage:
        summary.notes.append("No provider usage metadata present on completions.")
    elif missing:
        summary.notes.append(f"{missing} completion(s) lacked usage metadata.")
    return summary
