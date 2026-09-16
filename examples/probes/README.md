# Example probe suites

Fixture probes for the GitHub demo manifests (`examples/github_server_v1.json`).

| File | Purpose |
| --- | --- |
| `github_v1_offline.json` | Approved positive / negative / ambiguous probes |
| `github_v1_unapproved.yaml` | Same intents with `approved: false` (model path skips) |

## Offline CLI

```bash
tool-semantics capture examples/github_server_v1.json -o .tool-semantics/v1.json
tool-semantics probe .tool-semantics/v1.json \
  --probes examples/probes/github_v1_offline.json \
  --markdown-output .tool-semantics/probe-offline.md
```

## Fake model-backed (no API key)

Use `FakeModelRunner` for local / CI demos. Live providers need
`TOOL_SEMANTICS_API_KEY` / `OPENAI_API_KEY` — see [docs/probes.md](../../docs/probes.md).

```python
from pathlib import Path
from tool_semantics.probes import evaluate_probes, evaluate_probes_with_model, load_probes
from tool_semantics.runner import FakeModelRunner, ModelCompletion, RunnerMetadata, ToolCallRequest
from tool_semantics.scanner import capture_manifest

snapshot = capture_manifest(Path("examples/github_server_v1.json"))
probes = load_probes(Path("examples/probes/github_v1_offline.json"))

assert evaluate_probes(snapshot, probes).passed

runner = FakeModelRunner(
    [
        ModelCompletion(
            tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "login"})],
            metadata=RunnerMetadata(provider="fake", model="demo"),
        ),
        ModelCompletion(
            tool_calls=[
                ToolCallRequest(
                    name="create_issue",
                    arguments={"title": "flaky CI", "body": "repro"},
                )
            ],
            metadata=RunnerMetadata(provider="fake", model="demo"),
        ),
        # negative + ambiguous: script additional completions as needed
        ModelCompletion(
            tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "x"})],
            metadata=RunnerMetadata(provider="fake", model="demo"),
        ),
        ModelCompletion(
            tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "login"})],
            metadata=RunnerMetadata(provider="fake", model="demo"),
        ),
    ]
)
report = evaluate_probes_with_model(snapshot, probes, runner)
assert report.passed
```

Downstream metrics handoff: [docs/downstream.md](../../docs/downstream.md).
