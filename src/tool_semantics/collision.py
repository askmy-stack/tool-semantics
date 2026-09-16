"""Tool collision / confusability detection (#79).

Layer-1 (default): deterministic weighted Jaccard over name tokens,
description tokens, and parameter names — same heuristic as rename detection.

Layer-2 (optional): blend in embedding cosine similarity when an
``EmbeddingProvider`` is supplied. No embedding SDK is required for the
default install; see the ``embeddings`` optional extra.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from tool_semantics.models import ToolContract

DEFAULT_COLLISION_THRESHOLD = 0.55
# When embeddings are present, blend Layer-1 and Layer-2 equally.
_EMBEDDING_BLEND = 0.5


class EmbeddingProvider(Protocol):
    """Minimal embedding interface for Layer-2 confusability."""

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding vector per input text (same order)."""


@dataclass(frozen=True)
class CollisionPair:
    left: str
    right: str
    score: float
    layer: str  # "token" | "mixed"


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_l = math.sqrt(sum(a * a for a in left))
    norm_r = math.sqrt(sum(b * b for b in right))
    if norm_l == 0.0 or norm_r == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_l * norm_r)))


def _tool_text(tool: ToolContract) -> str:
    return f"{tool.name}\n{tool.description}"


def confusability_score(
    left: ToolContract,
    right: ToolContract,
    *,
    embeddings: EmbeddingProvider | None = None,
) -> tuple[float, str]:
    """Return (score in [0, 1], layer label)."""
    # Import locally to avoid an import cycle with diff.py.
    from tool_semantics.diff import _tool_similarity

    layer1 = _tool_similarity(left, right)
    if embeddings is None:
        return (round(layer1, 4), "token")
    vectors = embeddings.embed_texts([_tool_text(left), _tool_text(right)])
    if len(vectors) != 2:
        raise ValueError("EmbeddingProvider.embed_texts must return one vector per input")
    layer2 = _cosine(vectors[0], vectors[1])
    blended = ((1.0 - _EMBEDDING_BLEND) * layer1) + (_EMBEDDING_BLEND * layer2)
    return (round(blended, 4), "mixed")


def detect_collisions(
    tools: Sequence[ToolContract],
    *,
    threshold: float = DEFAULT_COLLISION_THRESHOLD,
    embeddings: EmbeddingProvider | None = None,
) -> list[CollisionPair]:
    """Find unordered tool pairs with confusability >= threshold."""
    if threshold < 0.0 or threshold > 1.0:
        raise ValueError("collision threshold must be in [0, 1]")
    ordered = sorted(tools, key=lambda tool: tool.name)
    pairs: list[CollisionPair] = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            score, layer = confusability_score(left, right, embeddings=embeddings)
            if score >= threshold:
                pairs.append(
                    CollisionPair(left=left.name, right=right.name, score=score, layer=layer)
                )
    pairs.sort(key=lambda item: (-item.score, item.left, item.right))
    return pairs


def collision_clusters(pairs: Sequence[CollisionPair]) -> list[frozenset[str]]:
    """Connected components of colliding tools (for report grouping)."""
    parent: dict[str, str] = {}

    def find(name: str) -> str:
        parent.setdefault(name, name)
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    def union(a: str, b: str) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    for pair in pairs:
        union(pair.left, pair.right)
    buckets: dict[str, set[str]] = {}
    for name in parent:
        buckets.setdefault(find(name), set()).add(name)
    return [frozenset(members) for members in buckets.values() if len(members) > 1]


def try_load_default_embeddings() -> EmbeddingProvider | None:
    """Load a default embedding provider when one is registered.

    Default install returns ``None`` (Layer-1 only). Callers may still pass a
    custom ``EmbeddingProvider``.
    """
    try:
        from tool_semantics import embeddings as emb_mod
    except ImportError:
        return None
    factory = emb_mod.get_registered_factory()
    if factory is None:
        return None
    return factory()
