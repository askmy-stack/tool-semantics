from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(StrEnum):
    READ_ONLY = "read_only"
    EXTERNAL_WRITE = "external_write"
    DESTRUCTIVE = "destructive"
    UNKNOWN = "unknown"


class PermissionScope(StrEnum):
    """Declared blast radius for a tool (#87).

    Ordered from narrowest to widest for escalation checks. ``unknown`` means
    the field was absent — never invent a scope during capture.
    """

    UNKNOWN = "unknown"
    RESOURCE = "resource"
    PROJECT = "project"
    WORKSPACE = "workspace"
    ORGANIZATION = "organization"
    ACCOUNT = "account"
    GLOBAL = "global"


SCOPE_RANK: dict[PermissionScope, int] = {
    PermissionScope.UNKNOWN: 0,
    PermissionScope.RESOURCE: 1,
    PermissionScope.PROJECT: 2,
    PermissionScope.WORKSPACE: 3,
    PermissionScope.ORGANIZATION: 4,
    PermissionScope.ACCOUNT: 5,
    PermissionScope.GLOBAL: 6,
}


# Documented side-effect vocabulary (open set — unknown strings are allowed).
KNOWN_SIDE_EFFECTS = frozenset(
    {
        "read",
        "write",
        "delete",
        "network",
        "email",
        "payment",
        "admin",
        "execute",
        "identity",
    }
)


class ToolParameter(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    schema_: dict[str, Any] = Field(alias="schema")
    required: bool = False
    description: str | None = None


class ToolContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    description: str = ""
    parameters: list[ToolParameter] = Field(default_factory=list)
    output_schema: dict[str, Any] | None = None
    risk: RiskLevel = RiskLevel.UNKNOWN
    scope: PermissionScope = PermissionScope.UNKNOWN
    side_effects: list[str] = Field(default_factory=list)
    requires_confirmation: bool | None = None


def parse_permission_scope(value: Any) -> PermissionScope:
    """Parse a scope annotation; unknown/invalid → ``unknown`` (never invent)."""
    if not isinstance(value, str) or not value.strip():
        return PermissionScope.UNKNOWN
    try:
        return PermissionScope(value.strip().lower())
    except ValueError:
        return PermissionScope.UNKNOWN


def parse_side_effects(value: Any) -> list[str]:
    """Parse a side-effects list; absent/invalid → empty (undeclared)."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        effect = item.strip().lower()
        if not effect or effect in seen:
            continue
        seen.add(effect)
        normalized.append(effect)
    return normalized


def parse_requires_confirmation(value: Any) -> bool | None:
    """Parse confirmation flag; absent/invalid → ``None`` (unknown)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return None


def extract_safety_annotations(raw: dict[str, Any]) -> dict[str, Any]:
    """Pull safety fields from a tool dict and optional ``annotations`` object.

    Never invent values — only copy what the source declares.
    """
    annotations = raw.get("annotations")
    ann = annotations if isinstance(annotations, dict) else {}

    risk_raw = raw.get("risk", ann.get("risk"))
    scope_raw = raw.get("scope", ann.get("scope"))
    side_raw = raw.get(
        "side_effects",
        raw.get("sideEffects", ann.get("side_effects", ann.get("sideEffects"))),
    )
    confirm_raw = raw.get(
        "requires_confirmation",
        raw.get(
            "requiresConfirmation",
            ann.get("requires_confirmation", ann.get("requiresConfirmation")),
        ),
    )

    try:
        risk = RiskLevel(risk_raw) if isinstance(risk_raw, str) else RiskLevel.UNKNOWN
    except ValueError:
        risk = RiskLevel.UNKNOWN

    return {
        "risk": risk,
        "scope": parse_permission_scope(scope_raw),
        "side_effects": parse_side_effects(side_raw),
        "requires_confirmation": parse_requires_confirmation(confirm_raw),
    }


class PromptContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    description: str = ""
    arguments: list[dict[str, Any]] = Field(default_factory=list)


class ResourceContract(BaseModel):
    model_config = ConfigDict(extra="allow")

    uri: str
    name: str
    description: str = ""
    mime_type: str | None = None


class InterfaceSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    tool_semantics_version: str = "0.1"
    protocol: str = "manifest"
    server_name: str
    server_version: str | None = None
    tools: list[ToolContract] = Field(default_factory=list)
    prompts: list[PromptContract] = Field(default_factory=list)
    resources: list[ResourceContract] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
