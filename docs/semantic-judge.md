# Optional LLM semantic judge (#81)

Opt-in MODEL-BASED judgments for ambiguous tool pairs (“same user task?”).
The default compare / eval path is unchanged until you explicitly call the
judge with a `ModelRunner`.

## When to use which layer

| Layer | Use when |
| --- | --- |
| Deterministic token Jaccard | Default CI; rename / collision heuristics |
| Embeddings (#117) | Optional numeric similarity without free-form text |
| **LLM judge (this)** | Hard ambiguous cases after deterministic + embeddings |

The judge **never overrides** deterministic breaking/critical findings. If a
tool is involved in `tool.removed` / other breaking codes, a model claim that
the tools are the “same task” is forced to `different_task` and flagged
`blocked_by_deterministic`.

## Library

```python
from tool_semantics.judge import judge_tool_pair, render_judge_markdown, JudgeReport
from tool_semantics.runner import FakeModelRunner, ModelCompletion, RunnerMetadata

runner = FakeModelRunner(
    [
        ModelCompletion(
            text='{"same_user_task": true, "confidence": 0.8, "rationale": "Both search."}',
            metadata=RunnerMetadata(provider="fake", model="fake"),
        )
    ]
)
verdict = judge_tool_pair(tool_a, tool_b, runner, deterministic_report=compare_report)
assert verdict.label == "MODEL-BASED"
print(render_judge_markdown(JudgeReport(verdicts=[verdict])))
```

Pass `deterministic_report=compare_snapshots(...)` so breaking subjects block
same-task overrides.

## Safety

- Prompts include only tool **name**, short **description**, **risk**, and
  parameter **names** — not full schemas (reduces untrusted metadata / secrets).
- CI must use `FakeModelRunner` (no live calls).

## Related

- Provider runners (#45 / #60)
- Untrusted metadata hardening (#66)
- Embeddings (#117), collisions (#79)
