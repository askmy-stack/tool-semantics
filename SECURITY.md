# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.4.x | Yes (current) |
| 0.3.x | Yes (security fixes) |
| 0.2.x | Yes (security fixes) |
| 0.1.x | No |

Use the latest `0.4.x` release for new installs. Older `0.2.x` / `0.3.x`
lines receive security fixes only until they are retired in a future notice.

## Reporting a vulnerability

Treat MCP metadata, tool descriptions, outputs, and generated probes as
**untrusted input**.

Tool-Semantics must not automatically execute discovered tools during capture
or probe evaluation.

### Model-backed probes

When `--model` / `evaluate_probes_with_model` is used, tool schemas and
descriptions are sent to a provider. Assume prompt-injection risk via tool
descriptions and secret leakage via schema field names or defaults. Tool-Semantics
omits secret-like parameter names from outbound tool JSON and does not persist
provider `raw` payloads unless `RunnerConfig.include_raw` is explicitly enabled
(then redacted). Details: [docs/probes.md](docs/probes.md#threat-model-model-backed-probes-66).

Please report security issues privately via
[GitHub Security Advisories](https://github.com/askmy-stack/tool-semantics/security/advisories/new).
Do not open a public issue for vulnerabilities that could enable remote code
execution, secret leakage, or unsafe tool invocation.

We aim to acknowledge reports within 7 days.
