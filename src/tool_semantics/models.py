from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(StrEnum):
    READ_ONLY = "read_only"
    EXTERNAL_WRITE = "external_write"
    DESTRUCTIVE = "destructive"
    UNKNOWN = "unknown"


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
