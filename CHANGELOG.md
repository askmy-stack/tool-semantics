# Changelog

All notable changes to Tool-Semantics will be documented in this file.

## [Unreleased]

### Added
- `tool.output_schema_added` / `removed` / `changed` detection (#8)
- `parameter.default_changed` warning when defaults are added, removed, or changed (#15)
- Default-only schema edits no longer emit `parameter.schema_changed`
- Snapshot `tool_semantics_version` validation on read (#7)
- `--verbose` logging and `.tool-semantics.toml` ignore rules (#9, #10)
- Composite GitHub Action for PR compatibility comments (#13)
- PyPI trusted-publishing workflow (`publish.yml`) (#23)
- Live MCP stdio capture (`capture-mcp`) with prompts/resources + redaction (#11)
- Offline behavioral probe harness (#12)
- Large-manifest benchmark helper (#14)
- Heuristic `tool.renamed` detection (#24)
- `parameter.type_widened` / `type_narrowed` / `type_changed` / `constraints_tightened` (#25)
- Example manifest with `outputSchema` (`examples/weather_with_output.json`)
- Release policies (`--policy`, `[policy]` in config, Action `policy` input)
- Migration adapters + in-process compatibility proxy (`docs/adapters.md`)
- Probe side-effect gates (`max_risk`, `requires_confirmation`)

## [0.1.0] — 2026-07-11

### Added
- Initial `tool-semantics` package with `capture` and `compare` CLI commands
- Manifest scanner and normalized `InterfaceSnapshot` model
- Structural diff engine with severity levels and stable change codes
- Enum removal/addition detection and tool risk-change detection
- Markdown report renderer (`--markdown-output`)
- JSON reports with `is_compatible` and severity `counts`
- Change-code catalog (`docs/change-codes.md`) and `py.typed` marker
- Example GitHub-style MCP manifests and pytest suite
- OSS docs: README, architecture, contributing, CoC, security policy
