"""Semantic distance matrix and tool clustering (#82).

Deterministic default (token Jaccard via ``diff._tool_similarity``). Optional
embedding blend when a provider is supplied. Large catalogs (N≥500) require an
explicit flag or are subsampled for the pairwise matrix.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from tool_semantics.diff import _tool_similarity
from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract

DEFAULT_SIMILAR_PAIR_THRESHOLD = 0.55
LARGE_CATALOG_N = 500
_EMBEDDING_BLEND = 0.5


class ActionFamily(StrEnum):
    """Documented heuristic action families for catalog browsing."""

    SEARCH = "SEARCH"
    WRITE = "WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"
    OTHER = "OTHER"


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...


class SimilarPair(BaseModel):
    left: str
    right: str
    score: float
    layer: str = "token"  # token | mixed


class ToolCluster(BaseModel):
    family: ActionFamily | None = None
    label: str
    tools: list[str] = Field(default_factory=list)


class SemanticMatrixReport(BaseModel):
    tool_names: list[str] = Field(default_factory=list)
    # Dense upper-triangle encoded as list of (i, j, score) with i < j.
    pairs: list[SimilarPair] = Field(default_factory=list)
    top_similar: list[SimilarPair] = Field(default_factory=list)
    action_families: list[ToolCluster] = Field(default_factory=list)
    similarity_clusters: list[ToolCluster] = Field(default_factory=list)
    subsampled: bool = False
    subsample_note: str = ""
    tool_count: int = 0
    compared_count: int = 0


_SEARCH_TOKENS = frozenset(
    {
        "search",
        "find",
        "list",
        "get",
        "read",
        "fetch",
        "query",
        "lookup",
        "show",
        "describe",
    }
)
_WRITE_TOKENS = frozenset(
    {
        "create",
        "add",
        "update",
        "edit",
        "write",
        "set",
        "put",
        "post",
        "patch",
        "send",
        "upload",
        "insert",
    }
)
_DESTRUCTIVE_TOKENS = frozenset(
    {
        "delete",
        "remove",
        "drop",
        "destroy",
        "purge",
        "revoke",
        "cancel",
        "archive",
        "force",
    }
)


def _name_tokens(name: str) -> set[str]:
    return {tok for tok in name.lower().replace("-", "_").split("_") if tok}


def classify_action_family(tool: ToolContract) -> ActionFamily:
    """Heuristic SEARCH / WRITE / DESTRUCTIVE / OTHER from name tokens + risk."""
    tokens = _name_tokens(tool.name) | {
        tok
        for tok in "".join(ch.lower() if ch.isalnum() else " " for ch in tool.description).split()
        if tok
    }
    if tool.risk == RiskLevel.DESTRUCTIVE or tokens & _DESTRUCTIVE_TOKENS:
        return ActionFamily.DESTRUCTIVE
    if tool.risk == RiskLevel.EXTERNAL_WRITE or tokens & _WRITE_TOKENS:
        return ActionFamily.WRITE
    if tool.risk == RiskLevel.READ_ONLY or tokens & _SEARCH_TOKENS:
        return ActionFamily.SEARCH
    return ActionFamily.OTHER


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


def pairwise_similarity(
    left: ToolContract,
    right: ToolContract,
    *,
    embeddings: EmbeddingProvider | None = None,
) -> tuple[float, str]:
    layer1 = _tool_similarity(left, right)
    if embeddings is None:
        return round(layer1, 4), "token"
    vectors = embeddings.embed_texts([_tool_text(left), _tool_text(right)])
    if len(vectors) != 2:
        raise ValueError("embed_texts must return one vector per input")
    layer2 = _cosine(vectors[0], vectors[1])
    blended = ((1.0 - _EMBEDDING_BLEND) * layer1) + (_EMBEDDING_BLEND * layer2)
    return round(blended, 4), "mixed"


def _subsample_tools(
    tools: list[ToolContract],
    *,
    max_tools: int,
) -> list[ToolContract]:
    """Deterministic stride subsample preserving name order."""
    if len(tools) <= max_tools:
        return tools
    step = len(tools) / max_tools
    indexes = sorted({min(len(tools) - 1, int(index * step)) for index in range(max_tools)})
    return [tools[index] for index in indexes]


def compute_semantic_matrix(
    snapshot: InterfaceSnapshot,
    *,
    top_k: int = 20,
    similar_threshold: float = DEFAULT_SIMILAR_PAIR_THRESHOLD,
    embeddings: EmbeddingProvider | None = None,
    allow_large: bool = False,
    max_tools: int = 250,
) -> SemanticMatrixReport:
    """Compute pairwise similarities and cluster tools for a snapshot.

    For N≥500, either pass ``allow_large=True`` (full O(N²) matrix — expensive)
    or the catalog is deterministically subsampled to ``max_tools`` (default 250).
    """
    ordered = sorted(snapshot.tools, key=lambda tool: tool.name)
    tool_count = len(ordered)
    subsampled = False
    note = ""
    working = ordered
    if tool_count >= LARGE_CATALOG_N and not allow_large:
        working = _subsample_tools(ordered, max_tools=max_tools)
        subsampled = True
        note = (
            f"Catalog has {tool_count} tools (≥{LARGE_CATALOG_N}); "
            f"pairwise matrix subsampled to {len(working)}. "
            "Pass allow_large=True / --allow-large for the full matrix."
        )
    elif tool_count >= LARGE_CATALOG_N and allow_large:
        note = (
            f"Computing full pairwise matrix for {tool_count} tools "
            f"(O(N²) ≈ {tool_count * (tool_count - 1) // 2} pairs)."
        )

    names = [tool.name for tool in working]
    pairs: list[SimilarPair] = []
    for index, left in enumerate(working):
        for right in working[index + 1 :]:
            score, layer = pairwise_similarity(left, right, embeddings=embeddings)
            pairs.append(SimilarPair(left=left.name, right=right.name, score=score, layer=layer))

    ranked = sorted(pairs, key=lambda item: (-item.score, item.left, item.right))
    top_similar = [item for item in ranked if item.score >= similar_threshold][:top_k]
    if not top_similar:
        top_similar = ranked[:top_k]

    # Action-family clusters (heuristic).
    family_buckets: dict[ActionFamily, list[str]] = {family: [] for family in ActionFamily}
    for tool in ordered:
        family_buckets[classify_action_family(tool)].append(tool.name)
    action_families = [
        ToolCluster(family=family, label=family.value, tools=sorted(members))
        for family, members in family_buckets.items()
        if members
    ]

    # Similarity clusters: connected components of pairs ≥ threshold.
    parent: dict[str, str] = {}

    def find(name: str) -> str:
        parent.setdefault(name, name)
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    def union(left: str, right: str) -> None:
        root_l, root_r = find(left), find(right)
        if root_l != root_r:
            parent[root_r] = root_l

    for pair in pairs:
        if pair.score >= similar_threshold:
            union(pair.left, pair.right)
    buckets: dict[str, set[str]] = {}
    for name in names:
        buckets.setdefault(find(name), set()).add(name)
    similarity_clusters = [
        ToolCluster(
            family=None,
            label=f"cluster-{index + 1}",
            tools=sorted(members),
        )
        for index, members in enumerate(
            sorted(buckets.values(), key=lambda group: (-len(group), sorted(group)[0]))
        )
        if len(members) > 1
    ]

    return SemanticMatrixReport(
        tool_names=names,
        pairs=pairs,
        top_similar=top_similar,
        action_families=action_families,
        similarity_clusters=similarity_clusters,
        subsampled=subsampled,
        subsample_note=note,
        tool_count=tool_count,
        compared_count=len(working),
    )


def render_semantic_matrix_markdown(report: SemanticMatrixReport) -> str:
    lines = [
        "## Semantic distance / clustering",
        "",
        f"Tools in snapshot: **{report.tool_count}**; compared: **{report.compared_count}**.",
        "",
    ]
    if report.subsample_note:
        lines.append(f"_{report.subsample_note}_")
        lines.append("")

    lines.extend(
        [
            "### Top similar pairs",
            "",
            "| Left | Right | Score | Layer |",
            "| --- | --- | ---: | --- |",
        ]
    )
    if not report.top_similar:
        lines.append("| — | — | — | — |")
    for pair in report.top_similar:
        lines.append(f"| `{pair.left}` | `{pair.right}` | {pair.score:.2f} | `{pair.layer}` |")
    lines.append("")

    lines.extend(
        [
            "### Action families",
            "",
            "| Family | Tools |",
            "| --- | --- |",
        ]
    )
    for cluster in report.action_families:
        tools = ", ".join(f"`{name}`" for name in cluster.tools) or "—"
        lines.append(f"| `{cluster.label}` | {tools} |")
    lines.append("")

    if report.similarity_clusters:
        lines.extend(
            [
                "### Similarity clusters",
                "",
                "| Cluster | Tools |",
                "| --- | --- |",
            ]
        )
        for cluster in report.similarity_clusters:
            tools = ", ".join(f"`{name}`" for name in cluster.tools)
            lines.append(f"| `{cluster.label}` | {tools} |")
        lines.append("")

    lines.append(
        "_Deterministic token Jaccard by default; embeddings optional. "
        "Action families are documented heuristics (SEARCH / WRITE / DESTRUCTIVE / OTHER)._"
    )
    lines.append("")
    return "\n".join(lines)


# Optional hook for callers that want a custom scorer.
SimilarityFn = Callable[[ToolContract, ToolContract], tuple[float, str]]


def matrix_as_dict(report: SemanticMatrixReport) -> dict[str, Any]:
    return report.model_dump(mode="json")
