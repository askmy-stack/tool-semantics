"""Optional embedding provider registry for rename / collision Layer-2 (#80 / #117)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tool_semantics.rename import EmbeddingProvider

_provider_factory: Callable[[], EmbeddingProvider] | None = None


def register_provider(factory: Callable[[], EmbeddingProvider]) -> None:
    global _provider_factory
    _provider_factory = factory


def clear_provider() -> None:
    global _provider_factory
    _provider_factory = None


def get_registered_factory() -> Callable[[], EmbeddingProvider] | None:
    return _provider_factory
