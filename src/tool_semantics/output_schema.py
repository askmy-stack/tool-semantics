"""Field-level output-schema compatibility helpers (#89)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def schema_properties(schema: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Return object ``properties`` when present; otherwise empty."""
    if not isinstance(schema, dict):
        return {}
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for name, value in properties.items():
        if isinstance(name, str) and isinstance(value, dict):
            result[name] = value
    return result


def property_type(schema: dict[str, Any]) -> str:
    raw = schema.get("type")
    if isinstance(raw, str) and raw:
        return raw
    if isinstance(raw, list):
        return "|".join(str(item) for item in raw)
    return "unknown"


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


def field_name_similarity(old_name: str, new_name: str) -> float:
    """Deterministic similarity for likely field renames."""
    if old_name == new_name:
        return 1.0
    old_l = old_name.lower()
    new_l = new_name.lower()
    # Containment heuristics: user_id → id, name → display_name
    if old_l in new_l or new_l in old_l:
        shorter = min(len(old_l), len(new_l))
        longer = max(len(old_l), len(new_l))
        containment = shorter / longer if longer else 0.0
    else:
        containment = 0.0
    token = _jaccard(
        _token_set(old_name.replace("_", " ")),
        _token_set(new_name.replace("_", " ")),
    )
    return round(max(containment, token), 4)


@dataclass(frozen=True)
class FieldRename:
    old_name: str
    new_name: str
    confidence: float  # 0..1


def detect_field_renames(
    removed: dict[str, dict[str, Any]],
    added: dict[str, dict[str, Any]],
    *,
    threshold: float = 0.55,
) -> list[FieldRename]:
    """Greedy 1:1 rename matches among removed/added output fields."""
    pairs: list[tuple[float, str, str]] = []
    for old_name, old_schema in removed.items():
        for new_name, new_schema in added.items():
            name_score = field_name_similarity(old_name, new_name)
            type_bonus = 0.15 if property_type(old_schema) == property_type(new_schema) else 0.0
            score = min(1.0, name_score + type_bonus)
            if score >= threshold:
                pairs.append((score, old_name, new_name))
    pairs.sort(reverse=True)
    matched_old: set[str] = set()
    matched_new: set[str] = set()
    renames: list[FieldRename] = []
    for score, old_name, new_name in pairs:
        if old_name in matched_old or new_name in matched_new:
            continue
        matched_old.add(old_name)
        matched_new.add(new_name)
        renames.append(
            FieldRename(old_name=old_name, new_name=new_name, confidence=round(score, 4))
        )
    return renames


def validate_output_payload(
    payload: Any,
    schema: dict[str, Any] | None,
) -> list[str]:
    """Fixture-friendly runtime check of a result against an output schema.

    Returns a list of human-readable errors (empty means OK). Only object
    property presence/types are checked in v1 — not full JSON Schema.
    """
    if schema is None:
        return []
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(payload, dict):
            return [f"Expected object payload, got {type(payload).__name__}"]
        properties = schema_properties(schema)
        required = schema.get("required")
        required_names = {str(item) for item in required} if isinstance(required, list) else set()
        for name in sorted(required_names):
            if name not in payload:
                errors.append(f"Missing required output field '{name}'")
        for name, value in payload.items():
            if name not in properties:
                continue
            expected = property_type(properties[name])
            if expected == "string" and not isinstance(value, str):
                errors.append(f"Field '{name}' expected string")
            elif expected == "integer" and not isinstance(value, int):
                errors.append(f"Field '{name}' expected integer")
            elif expected == "number" and not isinstance(value, int | float):
                errors.append(f"Field '{name}' expected number")
            elif expected == "boolean" and not isinstance(value, bool):
                errors.append(f"Field '{name}' expected boolean")
            elif expected == "array" and not isinstance(value, list):
                errors.append(f"Field '{name}' expected array")
            elif expected == "object" and not isinstance(value, dict):
                errors.append(f"Field '{name}' expected object")
    return errors
