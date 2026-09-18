"""Versioned agent trace schema for capture and replay (#83).

Traces record real tool-calling behavior: intent, selected tool, arguments,
and optional outcomes / model metadata / multi-step turns.

Version field: ``tool_semantics_trace_version`` (currently ``\"1.0\"``).
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from tool_semantics.redact import redact_mapping

TRACE_VERSION: Literal["1.0"] = "1.0"


class TraceOutcome(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


class TraceModelMetadata(BaseModel):
    """Optional model / runner metadata attached to a trace."""

    model_config = ConfigDict(extra="allow")

    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    seed: int | None = None
    request_id: str | None = None


class TraceStep(BaseModel):
    """One tool call within a multi-step trace."""

    model_config = ConfigDict(extra="allow")

    selected_tool: str = Field(min_length=1, description="Tool name chosen for this step.")
    arguments: dict[str, Any] = Field(default_factory=dict)
    intent: str | None = Field(
        default=None,
        description="Step-level intent; defaults to the parent trace intent when omitted.",
    )
    outcome: TraceOutcome | None = None
    error: str | None = None
    timestamp: datetime | None = None
    latency_ms: float | None = Field(default=None, ge=0)


class AgentTrace(BaseModel):
    """A versioned agent tool-calling trace suitable for replay (#84).

    **Single-step:** set ``intent``, ``selected_tool``, and ``arguments`` at the root.
    **Multi-step:** set root ``intent`` and a non-empty ``turns`` list (each turn
    requires ``selected_tool`` + ``arguments``).
    """

    model_config = ConfigDict(extra="allow")

    tool_semantics_trace_version: Literal["1.0"] = TRACE_VERSION
    id: str | None = None
    intent: str = Field(min_length=1, description="User / agent goal for this trace.")
    selected_tool: str | None = Field(
        default=None,
        description="Required for single-step traces when turns is empty.",
    )
    arguments: dict[str, Any] = Field(default_factory=dict)
    turns: list[TraceStep] = Field(default_factory=list)
    outcome: TraceOutcome | None = None
    error: str | None = None
    model: TraceModelMetadata | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    server_name: str | None = None
    snapshot_ref: str | None = Field(
        default=None,
        description="Optional path or id of the InterfaceSnapshot used during capture.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_call_shape(self) -> AgentTrace:
        if self.turns:
            return self
        if not self.selected_tool or not self.selected_tool.strip():
            raise ValueError(
                "AgentTrace requires 'selected_tool' when 'turns' is empty. "
                "Provide selected_tool + arguments for a single-step trace, "
                "or a non-empty turns list for multi-step traces."
            )
        return self

    def effective_steps(self) -> list[TraceStep]:
        """Normalize to a list of steps (single-step → one synthetic turn)."""
        if self.turns:
            return list(self.turns)
        assert self.selected_tool is not None
        return [
            TraceStep(
                selected_tool=self.selected_tool,
                arguments=dict(self.arguments),
                intent=self.intent,
                outcome=self.outcome,
                error=self.error,
                timestamp=self.started_at,
            )
        ]


class TraceValidationError(ValueError):
    """Raised when a trace document fails schema validation."""

    def __init__(self, message: str, *, path: Path | None = None) -> None:
        self.path = path
        prefix = f"{path}: " if path is not None else ""
        super().__init__(f"{prefix}{message}")


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        loc = ".".join(str(item) for item in error.get("loc", ())) or "(root)"
        msg = error.get("msg", "invalid value")
        parts.append(f"{loc}: {msg}")
    return "Trace validation failed — " + "; ".join(parts)


def validate_trace(data: dict[str, Any]) -> AgentTrace:
    """Validate a trace mapping; raises ``TraceValidationError`` with actionable detail."""
    try:
        return AgentTrace.model_validate(data)
    except ValidationError as exc:
        raise TraceValidationError(_format_validation_error(exc)) from exc


def _parse_document(text: str, *, path: Path, suffix: str) -> Any:
    try:
        if suffix in {".yaml", ".yml"}:
            import yaml

            return yaml.safe_load(text)
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise TraceValidationError(
            f"Could not parse trace file ({type(exc).__name__}): {exc}",
            path=path,
        ) from exc
    except Exception as exc:
        if exc.__class__.__name__ in {"YAMLError", "ScannerError", "ParserError"}:
            raise TraceValidationError(
                f"Could not parse trace file ({type(exc).__name__}): {exc}",
                path=path,
            ) from exc
        raise


def load_trace(path: Path) -> AgentTrace:
    """Load and validate a JSON (or YAML) agent trace file."""
    if not path.is_file():
        raise TraceValidationError(f"Trace file not found: {path}", path=path)
    raw = _parse_document(path.read_text(encoding="utf-8"), path=path, suffix=path.suffix.lower())
    if not isinstance(raw, dict):
        raise TraceValidationError(
            "Trace document must be a JSON object at the root.",
            path=path,
        )
    try:
        return validate_trace(raw)
    except TraceValidationError as exc:
        raise TraceValidationError(str(exc), path=path) from exc


def load_traces(path: Path) -> list[AgentTrace]:
    """Load a single trace file or a JSON array / directory of traces."""
    if path.is_dir():
        files = sorted(
            [*path.glob("*.json"), *path.glob("*.yaml"), *path.glob("*.yml")],
            key=lambda item: item.name,
        )
        return [load_trace(file) for file in files]
    if not path.is_file():
        raise TraceValidationError(f"Trace path not found: {path}", path=path)
    raw = _parse_document(path.read_text(encoding="utf-8"), path=path, suffix=path.suffix.lower())
    if isinstance(raw, list):
        traces: list[AgentTrace] = []
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                raise TraceValidationError(
                    f"Trace array item [{index}] must be an object.",
                    path=path,
                )
            try:
                traces.append(validate_trace(item))
            except TraceValidationError as exc:
                raise TraceValidationError(f"[{index}] {exc}", path=path) from exc
        return traces
    if isinstance(raw, dict):
        return [load_trace(path)]
    raise TraceValidationError(
        "Trace document must be an object or an array of objects.",
        path=path,
    )


def write_trace(trace: AgentTrace, path: Path) -> None:
    """Write a trace as pretty-printed JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(trace.model_dump_json(exclude_none=True))
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def redact_trace(trace: AgentTrace) -> AgentTrace:
    """Return a copy with secret-like argument / metadata fields redacted."""
    payload = json.loads(trace.model_dump_json())
    if isinstance(payload.get("arguments"), dict):
        payload["arguments"] = redact_mapping(payload["arguments"])
    if isinstance(payload.get("metadata"), dict):
        payload["metadata"] = redact_mapping(payload["metadata"])
    for turn in payload.get("turns") or []:
        if isinstance(turn, dict) and isinstance(turn.get("arguments"), dict):
            turn["arguments"] = redact_mapping(turn["arguments"])
    return AgentTrace.model_validate(payload)


def trace_json_schema() -> dict[str, Any]:
    """JSON Schema for ``AgentTrace`` (draft for docs / external validators)."""
    return AgentTrace.model_json_schema()
