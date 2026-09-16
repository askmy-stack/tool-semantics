"""DEV / TEST / VERIFIED corpus partitions (#116).

Calibrate heuristics on DEV only. Default CI runs TEST. VERIFIED is
release/research-gated — never the day-to-day PR gate.
"""

from __future__ import annotations

import json
import os
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

DEFAULT_SPLITS_PATH = Path("benchmarks/splits.json")
ENV_SPLIT = "TOOL_SEMANTICS_CORPUS_SPLIT"
DEFAULT_CI_SPLIT = "test"


class CorpusSplit(StrEnum):
    DEV = "dev"
    TEST = "test"
    VERIFIED = "verified"


SPLIT_GUIDANCE: dict[CorpusSplit, str] = {
    CorpusSplit.DEV: (
        "Calibrate thresholds, rename heuristics, and detector knobs here only. "
        "Do not report DEV scores as final published results."
    ),
    CorpusSplit.TEST: (
        "Default CI / PR gate. Use a fixed seed subset when the partition is large. "
        "Safe for routine regression without contaminating published claims."
    ),
    CorpusSplit.VERIFIED: (
        "Release and research publication only. Run explicitly "
        f"(e.g. {ENV_SPLIT}=verified); never the default PR gate."
    ),
}


class SplitsManifest(BaseModel):
    version: int = 1
    partitions: dict[str, list[str]] = Field(default_factory=dict)
    notes: dict[str, str] = Field(default_factory=dict)

    def domains_for(self, split: CorpusSplit | str) -> list[str]:
        key = CorpusSplit(split).value
        return list(self.partitions.get(key, []))

    def split_for_domain(self, domain: str) -> CorpusSplit | None:
        for name, domains in self.partitions.items():
            if domain in domains:
                return CorpusSplit(name)
        return None


def load_splits_manifest(path: Path = DEFAULT_SPLITS_PATH) -> SplitsManifest:
    if not path.is_file():
        raise FileNotFoundError(f"Splits manifest not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Splits manifest must be a JSON object: {path}")
    manifest = SplitsManifest.model_validate(payload)
    _validate_manifest(manifest)
    return manifest


def _validate_manifest(manifest: SplitsManifest) -> None:
    seen: dict[str, str] = {}
    for name, domains in manifest.partitions.items():
        try:
            CorpusSplit(name)
        except ValueError as exc:
            raise ValueError(
                f"Unknown partition {name!r}; expected {[s.value for s in CorpusSplit]}"
            ) from exc
        for domain in domains:
            if domain in seen:
                raise ValueError(f"Domain {domain!r} appears in both {seen[domain]!r} and {name!r}")
            seen[domain] = name
    for required in CorpusSplit:
        if required.value not in manifest.partitions:
            raise ValueError(f"Splits manifest missing required partition {required.value!r}")


def resolve_split(
    explicit: str | CorpusSplit | None = None,
    *,
    default: str = DEFAULT_CI_SPLIT,
) -> CorpusSplit:
    """Resolve active split: explicit arg → env → default (TEST for CI)."""
    if explicit is not None:
        return CorpusSplit(str(explicit).strip().lower())
    env = os.environ.get(ENV_SPLIT, "").strip().lower()
    if env:
        return CorpusSplit(env)
    return CorpusSplit(default)


def filter_case_dirs(
    case_dirs: list[Path],
    split: CorpusSplit | str,
    manifest: SplitsManifest,
) -> list[Path]:
    allowed = set(manifest.domains_for(split))
    return [path for path in case_dirs if path.name in allowed]


def render_splits_markdown(manifest: SplitsManifest) -> str:
    lines = [
        "## Corpus splits (DEV / TEST / VERIFIED)",
        "",
        "Calibrate on **DEV** only. CI defaults to **TEST**. "
        "**VERIFIED** is release/research-gated.",
        "",
        "| Partition | Domains | Guidance |",
        "| --- | --- | --- |",
    ]
    for split in CorpusSplit:
        domains = ", ".join(f"`{name}`" for name in manifest.domains_for(split)) or "—"
        note = manifest.notes.get(split.value) or SPLIT_GUIDANCE[split]
        lines.append(f"| `{split.value}` | {domains} | {note} |")
    lines.append("")
    lines.append(f"Override with `{ENV_SPLIT}=dev|test|verified` or `--split`.")
    lines.append("")
    return "\n".join(lines)


def splits_payload(manifest: SplitsManifest) -> dict[str, Any]:
    return manifest.model_dump(mode="json")
