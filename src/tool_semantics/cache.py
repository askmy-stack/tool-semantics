"""Disk cache for model-backed probe completions (#100).

Cache key: model + prompt/tools hash + snapshot hash + temperature + seed.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from tool_semantics.runner import ModelCompletion, RunnerConfig


class CacheStats(BaseModel):
    hits: int = 0
    misses: int = 0
    stores: int = 0

    @property
    def lookups(self) -> int:
        return self.hits + self.misses


def stable_hash(payload: Any) -> str:
    """SHA-256 of canonical JSON (sorted keys)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def snapshot_hash(snapshot: Any) -> str:
    """Hash an InterfaceSnapshot or any pydantic/dict-like object."""
    if hasattr(snapshot, "model_dump"):
        payload = snapshot.model_dump(mode="json")
    else:
        payload = snapshot
    return stable_hash(payload)


def build_cache_key(
    *,
    model: str,
    system: str,
    user: str,
    tools: list[dict[str, Any]],
    snapshot_digest: str,
    config: RunnerConfig | None = None,
) -> str:
    cfg = config or RunnerConfig()
    material = {
        "model": model,
        "prompt": {"system": system, "user": user},
        "tools": tools,
        "snapshot_hash": snapshot_digest,
        "temperature": cfg.temperature,
        "seed": cfg.seed,
    }
    return stable_hash(material)


class ProbeCompletionCache:
    """Thread-safe filesystem cache for ``ModelCompletion`` payloads."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.stats = CacheStats()
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> ModelCompletion | None:
        path = self._path(key)
        with self._lock:
            if not path.is_file():
                self.stats.misses += 1
                return None
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                completion = ModelCompletion.model_validate(payload)
            except (OSError, ValueError, TypeError):
                self.stats.misses += 1
                return None
            self.stats.hits += 1
            return completion

    def put(self, key: str, completion: ModelCompletion) -> None:
        path = self._path(key)
        tmp = path.with_suffix(".tmp")
        with self._lock:
            tmp.write_text(
                json.dumps(completion.model_dump(mode="json"), indent=2) + "\n",
                encoding="utf-8",
            )
            tmp.replace(path)
            self.stats.stores += 1


class CacheStatsReport(BaseModel):
    hits: int = 0
    misses: int = 0
    stores: int = 0
    hit_rate: float | None = None

    @classmethod
    def from_stats(cls, stats: CacheStats) -> CacheStatsReport:
        lookups = stats.lookups
        return cls(
            hits=stats.hits,
            misses=stats.misses,
            stores=stats.stores,
            hit_rate=(stats.hits / lookups) if lookups else None,
        )
