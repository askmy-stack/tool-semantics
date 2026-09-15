"""Human-reviewed model-backed probes

Offline probes (`evaluate_probes`) remain the default and require no model
provider. Model-backed execution is **opt-in** via
`evaluate_probes_with_model` / `run_probe_trials` and a `ModelRunner`.

## Approval workflow

1. Author a `Probe` with `intent`, expectations (`expected_tool`,
   `required_params`, `max_risk`, …).
2. Human review the probe text and expected behavior.
3. Set `approved=True` (and optionally `approved_by`) only after review.
4. Run model-backed evaluation. Unapproved probes are skipped when
   `require_approval=True` (the default).

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

## Safety

- Do not embed secrets in probe intents or expected arguments.
- Tool metadata from captures may be untrusted; runners must not echo it into
  logs beyond selected tool name / argument keys needed for scoring.
- Provider SDKs are optional — `OpenAICompatibleRunner` uses stdlib HTTP only.
"""
