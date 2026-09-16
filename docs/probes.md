# Human-reviewed model-backed probes

Offline probes (`evaluate_probes`) remain the default and require no model
provider. Model-backed execution is **opt-in** via
`evaluate_probes_with_model` / `run_probe_trials` and a `ModelRunner`.

## CLI

```bash
# Offline (default) — no provider required
tool-semantics capture examples/github_server_v1.json -o .tool-semantics/v1.json
tool-semantics probe .tool-semantics/v1.json \
  --probes examples/probes/github_v1_offline.json \
  --markdown-output probe-report.md \
  --json-output probe-report.json

# Opt-in model-backed (approved probes only by default)
export TOOL_SEMANTICS_API_KEY=…          # or OPENAI_API_KEY
export TOOL_SEMANTICS_MODEL=gpt-4o-mini  # optional
tool-semantics probe .tool-semantics/v1.json \
  --probes examples/probes/github_v1_offline.json \
  --model

# Stability trials (implies model mode)
tool-semantics probe .tool-semantics/v1.json \
  --probes examples/probes/github_v1_offline.json \
  --trials 4 --seed 1
```

Exit codes: `0` pass, `1` probe / stability failure, `2` input / config error.

Probe files may be JSON or YAML: a list of probes, or `{ "probes": [ … ] }`.

Shipped fixtures: [`examples/probes/`](../examples/probes/) (see that folder's
README for offline CLI + `FakeModelRunner` walkthrough). Live providers remain
opt-in via env secrets — never commit API keys.

## Approval workflow

1. Author a `Probe` with `intent`, expectations (`expected_tool`,
   `required_params`, `max_risk`, …).
2. Human review the probe text and expected behavior.
3. Set `approved=True` (and optionally `approved_by`) only after review.
4. Run model-backed evaluation. Unapproved probes are skipped when
   `require_approval=True` (the default). Use `--allow-unapproved` only for
   local experiments.

```python
from tool_semantics.probes import Probe, ProbeKind, evaluate_probes_with_model
from tool_semantics.runner import FakeModelRunner, ModelCompletion, ToolCallRequest, RunnerMetadata

probe = Probe(
    id="search-issues",
    intent="find open bugs in the repo",
    kind=ProbeKind.POSITIVE,
    expected_tool="search_issues",
    required_params=["query"],
    approved=True,
    approved_by="reviewer@example.com",
)
```

## Runner configuration (env)

| Variable | Purpose |
| --- | --- |
| `TOOL_SEMANTICS_API_KEY` / `OPENAI_API_KEY` | Required for `--model` |
| `TOOL_SEMANTICS_MODEL` / `OPENAI_MODEL` | Model id (default `gpt-4o-mini`) |
| `TOOL_SEMANTICS_BASE_URL` / `OPENAI_BASE_URL` | OpenAI-compatible base URL |

## Safety

- Do not embed secrets in probe intents or expected arguments.
- Tool metadata from captures may be untrusted; runners must not echo it into
  logs beyond selected tool name / argument keys needed for scoring.
- Provider SDKs are optional — `OpenAICompatibleRunner` uses stdlib HTTP only.
- Never auto-execute discovered MCP tools during probe evaluation.
