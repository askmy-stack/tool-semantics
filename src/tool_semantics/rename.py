"""Multi-signal rename detection with confidence scoring (#80).

Weights (Layer-1, sum to 1.0 when embeddings are absent):

| Signal | Weight | Notes |
| --- | ---: | --- |
| parameter names | 0.35 | Jaccard over parameter names |
| description tokens | 0.25 | Token Jaccard |
| name tokens | 0.20 | ``_`` → space, then token Jaccard |
| output schema | 0.20 | Both absent → 1.0; one absent → 0.0; else key Jaccard |

When an embedding provider is supplied, an embedding cosine signal is blended
in at weight 0.15 and the Layer-1 weights are renormalized to 0.85.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from tool_semantics.models import ToolContract

# Layer-1 weights (must sum to 1.0).
WEIGHT_PARAMS = 0.35
WEIGHT_DESCRIPTION = 0.25
WEIGHT_NAME = 0.20
WEIGHT_OUTPUT = 0.20
# Optional embedding blend.
WEIGHT_EMBEDDING = 0.15

DEFAULT_RENAME_THRESHOLD = 0.55


class RenameConfidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""


@dataclass(frozen=True)
class SignalScores:
    name: float
    description: float
    parameters: float
    output_schema: float
    embedding: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "output_schema": self.output_schema,
            "embedding": self.embedding,
        }


@dataclass(frozen=True)
class RenameCandidate:
    old_name: str
    new_name: str
    score: float
    confidence: RenameConfidence
    signals: SignalScores


def _token_set(text: str) -> set[str]:
    return {
        token
        for token in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split()
        if token
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_l = math.sqrt(sum(a * a for a in left))
    norm_r = math.sqrt(sum(b * b for b in right))
    if norm_l == 0.0 or norm_r == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_l * norm_r)))


def _output_schema_similarity(left: ToolContract, right: ToolContract) -> float:
    left_schema = left.output_schema
    right_schema = right.output_schema
    if left_schema is None and right_schema is None:
        return 1.0
    if left_schema is None or right_schema is None:
        return 0.0
    if left_schema == right_schema:
        return 1.0
    left_keys = {str(key) for key in left_schema}
    right_keys = {str(key) for key in right_schema}
    key_score = _jaccard(left_keys, right_keys)
    # Soften with serialized-token overlap for nested shape drift.
    left_tokens = _token_set(json.dumps(left_schema, sort_keys=True, default=str))
    right_tokens = _token_set(json.dumps(right_schema, sort_keys=True, default=str))
    return round(0.5 * key_score + 0.5 * _jaccard(left_tokens, right_tokens), 4)


def confidence_for_score(score: float) -> RenameConfidence:
    if score >= 0.80:
        return RenameConfidence.HIGH
    if score >= 0.60:
        return RenameConfidence.MEDIUM
    return RenameConfidence.LOW


def score_rename_pair(
    left: ToolContract,
    right: ToolContract,
    *,
    embeddings: EmbeddingProvider | None = None,
) -> tuple[float, SignalScores]:
    """Return overall score and per-signal similarities for a candidate rename."""
    name = _jaccard(
        _token_set(left.name.replace("_", " ")),
        _token_set(right.name.replace("_", " ")),
    )
    description = _jaccard(_token_set(left.description), _token_set(right.description))
    parameters = _jaccard(
        {parameter.name for parameter in left.parameters},
        {parameter.name for parameter in right.parameters},
    )
    output = _output_schema_similarity(left, right)

    embedding_score: float | None = None
    if embeddings is not None:
        vectors = embeddings.embed_texts(
            [f"{left.name}\n{left.description}", f"{right.name}\n{right.description}"]
        )
        if len(vectors) != 2:
            raise ValueError("EmbeddingProvider.embed_texts must return one vector per input")
        embedding_score = _cosine(vectors[0], vectors[1])

    if embedding_score is None:
        overall = (
            WEIGHT_PARAMS * parameters
            + WEIGHT_DESCRIPTION * description
            + WEIGHT_NAME * name
            + WEIGHT_OUTPUT * output
        )
    else:
        scale = 1.0 - WEIGHT_EMBEDDING
        overall = (
            scale
            * (
                WEIGHT_PARAMS * parameters
                + WEIGHT_DESCRIPTION * description
                + WEIGHT_NAME * name
                + WEIGHT_OUTPUT * output
            )
            + WEIGHT_EMBEDDING * embedding_score
        )

    signals = SignalScores(
        name=round(name, 4),
        description=round(description, 4),
        parameters=round(parameters, 4),
        output_schema=round(output, 4),
        embedding=None if embedding_score is None else round(embedding_score, 4),
    )
    return (round(overall, 4), signals)


def detect_rename_candidates(
    removed: dict[str, ToolContract],
    added: dict[str, ToolContract],
    *,
    threshold: float = DEFAULT_RENAME_THRESHOLD,
    embeddings: EmbeddingProvider | None = None,
) -> list[RenameCandidate]:
    """Greedy one-to-one rename matches above ``threshold`` with confidence."""
    if threshold < 0.0 or threshold > 1.0:
        raise ValueError("rename threshold must be in [0, 1]")
    pairs: list[RenameCandidate] = []
    for old_name, old_tool in removed.items():
        for new_name, new_tool in added.items():
            score, signals = score_rename_pair(old_tool, new_tool, embeddings=embeddings)
            if score >= threshold:
                pairs.append(
                    RenameCandidate(
                        old_name=old_name,
                        new_name=new_name,
                        score=score,
                        confidence=confidence_for_score(score),
                        signals=signals,
                    )
                )
    pairs.sort(key=lambda item: (-item.score, item.old_name, item.new_name))
    matched_old: set[str] = set()
    matched_new: set[str] = set()
    selected: list[RenameCandidate] = []
    for candidate in pairs:
        if candidate.old_name in matched_old or candidate.new_name in matched_new:
            continue
        matched_old.add(candidate.old_name)
        matched_new.add(candidate.new_name)
        selected.append(candidate)
    return selected


def format_rename_message(candidate: RenameCandidate) -> str:
    signals = candidate.signals
    parts = [
        f"name={signals.name:.2f}",
        f"description={signals.description:.2f}",
        f"parameters={signals.parameters:.2f}",
        f"output_schema={signals.output_schema:.2f}",
    ]
    if signals.embedding is not None:
        parts.append(f"embedding={signals.embedding:.2f}")
    return (
        f"Tool '{candidate.old_name}' → '{candidate.new_name}' "
        f"(rename confidence {candidate.confidence.value}, score={candidate.score:.2f}; "
        f"signals: {', '.join(parts)})."
    )
