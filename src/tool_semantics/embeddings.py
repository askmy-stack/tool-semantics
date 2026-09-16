"""Optional Layer-2 embedding hooks for collision detection (#79 / #117).

Install ``pip install 'tool-semantics[embeddings]'`` to mark embedding support
as intentional. This module does **not** vendor a cloud embedding SDK; register
a provider via ``register_provider`` or pass ``EmbeddingProvider`` into
``compare_snapshots`` / ``detect_collisions`` directly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tool_semantics.collision import EmbeddingProvider

_provider_factory: Callable[[], EmbeddingProvider] | None = None


def register_provider(factory: Callable[[], EmbeddingProvider]) -> None:
    """Register a process-wide default embedding provider factory."""
    global _provider_factory
    _provider_factory = factory


def clear_provider() -> None:
    """Clear the process-wide embedding provider (tests / teardown)."""
    global _provider_factory
    _provider_factory = None


def get_registered_factory() -> Callable[[], EmbeddingProvider] | None:
    """Return the registered factory, if any."""
    return _provider_factory


def default_provider() -> EmbeddingProvider:
    """Return the registered provider, or raise if none is configured."""
    if _provider_factory is None:
        raise RuntimeError(
            "No embedding provider registered. Call "
            "tool_semantics.embeddings.register_provider(...) or pass "
            "embeddings= into compare_snapshots / detect_collisions."
        )
    return _provider_factory()
