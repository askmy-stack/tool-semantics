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

## Packaging extras (SDK-free)

Core `pip install tool-semantics` never requires a provider SDK.
`OpenAICompatibleRunner` speaks HTTP with the standard library only.

Optional extras are **markers** (empty dependency sets) so teams can declare
intent without pulling SDKs:

```bash
pip install "tool-semantics[openai]"
# or
pip install "tool-semantics[providers]"
```

## HTTP provider profile matrix

| Profile | Base URL pattern | Auth | Notes |
| --- | --- | --- | --- |
| `openai` | `https://api.openai.com/v1` | Bearer | Official Chat Completions |
| `azure-openai` | `https://{resource}.openai.azure.com/openai/deployments/{deployment}` | `api-key` header + `api-version` query | Pass `resource=` / `deployment=` |
| `local` | `http://127.0.0.1:11434/v1` | Bearer (often ignored) | Ollama, vLLM, LM Studio, etc. |

```python
from tool_semantics.runner import (
    RunnerConfig,
    openai_compatible_from_profile,
)

runner = openai_compatible_from_profile(
    "openai",
    model="gpt-4o-mini",
    api_key="…",
)
azure = openai_compatible_from_profile(
    "azure-openai",
    model="gpt-4o-mini",  # deployment name
    api_key="…",
    resource="my-resource",
    deployment="gpt-4o-mini",
)
local = openai_compatible_from_profile(
    "local",
    model="llama3.2",
    api_key="ollama",  # placeholder for local servers that expect a key
    base_url="http://127.0.0.1:11434/v1",
)

cfg = RunnerConfig(
    max_retries=2,
    retry_backoff_seconds=0.05,
    max_calls=20,
    max_tokens=50_000,
    max_cost_usd=0.50,
    prompt_cost_per_1m=0.15,
    completion_cost_per_1m=0.60,
    max_output_tokens=1024,
    seed=1,
)
```

Limits (`max_calls`, `max_tokens`, `max_cost_usd`) are enforced on the runner
and recorded on `ModelCompletion.metadata.run_config` together with cumulative
`total_tokens` / `total_cost_usd`.

### Retry / backoff

`OpenAICompatibleRunner.complete` attempts `max_retries + 1` times. Between
attempts it sleeps `retry_backoff_seconds` (fixed backoff; default `0.05`).
Unit tests monkeypatch `time.sleep` and never open a live network socket.

## Safety

- Do not embed secrets in probe intents or expected arguments.
- Tool metadata from captures may be untrusted; runners must not echo it into
  logs beyond selected tool name / argument keys needed for scoring.
- Provider SDKs are optional — `OpenAICompatibleRunner` uses stdlib HTTP only.
- Never auto-execute discovered MCP tools during probe evaluation.
