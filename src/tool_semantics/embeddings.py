"""Optional embedding similarity for semantic tool comparisons (#117).

Deterministic token-overlap diffs remain the default. Embeddings are opt-in via
an ``EmbeddingProvider`` (fake/stub in CI; live providers behind an optional
extra). Results carry model/provider metadata and a ``HYBRID`` / ``MODEL-BASED``
label for reports.
"""

from __future__ import annotations

import hashlib
import math
import re
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from tool_semantics.models import ToolContract


class SimilaritySource(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    HYBRID = "HYBRID"
    MODEL_BASED = "MODEL-BASED"


class EmbeddingMetadata(BaseModel):
    provider: str
    model: str
    dimensions: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ToolSimilarityScore(BaseModel):
    left: str
    right: str
    score: float
    token_score: float | None = None
    embedding_score: float | None = None
    source: SimilaritySource = SimilaritySource.DETERMINISTIC
    metadata: EmbeddingMetadata | None = None


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def metadata(self) -> EmbeddingMetadata: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _tokenize(text: str) -> list[str]:
    return [tok for tok in re.split(r"[^a-z0-9]+", text.lower()) if tok]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_l = math.sqrt(sum(a * a for a in left))
    norm_r = math.sqrt(sum(b * b for b in right))
    if norm_l == 0.0 or norm_r == 0.0:
        return 0.0
    return dot / (norm_l * norm_r)


class FakeEmbeddingProvider:
    """Deterministic bag-of-hash embedding for CI (no network / SDK)."""

    def __init__(self, *, dimensions: int = 32, model: str = "fake-hash-v1") -> None:
        self._dimensions = dimensions
        self._metadata = EmbeddingMetadata(
            provider="fake",
            model=model,
            dimensions=dimensions,
        )

    @property
    def metadata(self) -> EmbeddingMetadata:
        return self._metadata

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self._dimensions
            for token in _tokenize(text):
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                index = digest[0] % self._dimensions
                sign = 1.0 if digest[1] % 2 == 0 else -1.0
                vec[index] += sign
            # L2 normalize
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


def tool_embedding_text(tool: ToolContract) -> str:
    params = " ".join(parameter.name for parameter in tool.parameters)
    return f"{tool.name} {tool.description} {params}".strip()


def embedding_similarity(
    left: ToolContract,
    right: ToolContract,
    provider: EmbeddingProvider,
) -> ToolSimilarityScore:
    vectors = provider.embed([tool_embedding_text(left), tool_embedding_text(right)])
    score = cosine_similarity(vectors[0], vectors[1])
    return ToolSimilarityScore(
        left=left.name,
        right=right.name,
        score=round(score, 4),
        embedding_score=round(score, 4),
        source=SimilaritySource.MODEL_BASED,
        metadata=provider.metadata,
    )


def hybrid_tool_similarity(
    left: ToolContract,
    right: ToolContract,
    provider: EmbeddingProvider,
    *,
    token_score: float,
    embedding_weight: float = 0.5,
) -> ToolSimilarityScore:
    """Blend deterministic token similarity with embedding cosine similarity."""
    weight = min(1.0, max(0.0, embedding_weight))
    emb = embedding_similarity(left, right, provider)
    blended = ((1.0 - weight) * token_score) + (weight * (emb.embedding_score or 0.0))
    return ToolSimilarityScore(
        left=left.name,
        right=right.name,
        score=round(blended, 4),
        token_score=round(token_score, 4),
        embedding_score=emb.embedding_score,
        source=SimilaritySource.HYBRID,
        metadata=provider.metadata,
    )


def similarity_matrix(
    tools: list[ToolContract],
    provider: EmbeddingProvider,
) -> list[ToolSimilarityScore]:
    """Pairwise MODEL-BASED similarities (upper triangle)."""
    texts = [tool_embedding_text(tool) for tool in tools]
    vectors = provider.embed(texts)
    scores: list[ToolSimilarityScore] = []
    for i, left in enumerate(tools):
        for j in range(i + 1, len(tools)):
            score = cosine_similarity(vectors[i], vectors[j])
            scores.append(
                ToolSimilarityScore(
                    left=left.name,
                    right=tools[j].name,
                    score=round(score, 4),
                    embedding_score=round(score, 4),
                    source=SimilaritySource.MODEL_BASED,
                    metadata=provider.metadata,
                )
            )
    scores.sort(key=lambda item: item.score, reverse=True)
    return scores
