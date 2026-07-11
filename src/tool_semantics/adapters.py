from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolAlias(BaseModel):
    """Map a legacy tool name to a current tool name."""

    model_config = ConfigDict(populate_by_name=True)

    from_name: str = Field(alias="from")
    to_name: str = Field(alias="to")


class ArgumentMap(BaseModel):
    """Rename or drop arguments when translating a call to a new tool."""

    tool: str
    rename: dict[str, str] = Field(default_factory=dict)
    drop: list[str] = Field(default_factory=list)
    defaults: dict[str, Any] = Field(default_factory=dict)


class EnumMap(BaseModel):
    """Translate enum values for a parameter on a tool."""

    tool: str
    parameter: str
    values: dict[str, str] = Field(default_factory=dict)


class OutputWrapper(BaseModel):
    """Describe how to reshape a new tool's output into a legacy shape."""

    tool: str
    # JSON-path-like simple key remaps: new_key -> legacy_key
    rename_fields: dict[str, str] = Field(default_factory=dict)
    wrap_as: str | None = None


class MigrationAdapter(BaseModel):
    """Declarative compatibility layer between baseline and candidate tool surfaces."""

    aliases: list[ToolAlias] = Field(default_factory=list)
    arguments: list[ArgumentMap] = Field(default_factory=list)
    enums: list[EnumMap] = Field(default_factory=list)
    outputs: list[OutputWrapper] = Field(default_factory=list)

    def resolve_tool(self, name: str) -> str:
        for alias in self.aliases:
            if alias.from_name == name:
                return alias.to_name
        return name

    def translate_arguments(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        resolved = self.resolve_tool(tool)
        result = dict(arguments)
        for mapping in self.arguments:
            if mapping.tool not in {tool, resolved}:
                continue
            for legacy, modern in mapping.rename.items():
                if legacy in result:
                    result[modern] = result.pop(legacy)
            for key in mapping.drop:
                result.pop(key, None)
            for key, value in mapping.defaults.items():
                result.setdefault(key, value)
        for enum_map in self.enums:
            if enum_map.tool not in {tool, resolved}:
                continue
            if enum_map.parameter in result:
                current = result[enum_map.parameter]
                if isinstance(current, str) and current in enum_map.values:
                    result[enum_map.parameter] = enum_map.values[current]
        return result

    def wrap_output(self, tool: str, payload: dict[str, Any]) -> dict[str, Any]:
        resolved = self.resolve_tool(tool)
        result = dict(payload)
        for wrapper in self.outputs:
            if wrapper.tool not in {tool, resolved}:
                continue
            remapped: dict[str, Any] = {}
            for new_key, legacy_key in wrapper.rename_fields.items():
                if new_key in result:
                    remapped[legacy_key] = result.pop(new_key)
            result.update(remapped)
            if wrapper.wrap_as:
                result = {wrapper.wrap_as: result}
        return result


class CompatibilityProxy:
    """Apply a MigrationAdapter to inbound tool calls and outbound payloads."""

    def __init__(self, adapter: MigrationAdapter) -> None:
        self.adapter = adapter

    def route_call(self, tool: str, arguments: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        modern_tool = self.adapter.resolve_tool(tool)
        modern_args = self.adapter.translate_arguments(tool, arguments)
        return modern_tool, modern_args

    def route_result(self, tool: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.adapter.wrap_output(tool, payload)
