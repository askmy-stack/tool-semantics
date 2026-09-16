# Optional SARIF and HTML reports (#99)

Markdown and JSON remain the **default** compare / eval outputs. SARIF and HTML
are opt-in for enterprise CI dashboards and shareable summaries.

## CLI

```bash
tool-semantics compare .tool-semantics/v1.json .tool-semantics/v2.json \
  --markdown-output report.md \
  --json-output report.json \
  --sarif-output report.sarif \
  --html-output report.html
```

| Flag | Purpose |
| --- | --- |
| `--sarif-output` | SARIF **2.1.0** with **breaking** / **critical** findings (`level: error`) |
| `--html-output` | Self-contained HTML (scorecard counts + findings table); **no JS framework** |

Pass `--policy permissive` (or a non-failing policy) if you only want artifacts
and a zero exit when exploring locally.

## Library

```python
from tool_semantics.sarif import build_sarif, write_sarif
from tool_semantics.html_report import render_html_report, write_html_report

sarif = build_sarif(report)  # breaking/critical only
sarif = build_sarif(report, include_warnings=True)
write_sarif(report, Path("report.sarif"))
write_html_report(report, Path("report.html"))
```

## Notes

- SARIF `$schema` points at the public 2.1.0 schema URL; rules map 1:1 to
  change codes in [change-codes.md](change-codes.md).
- HTML is a static file suitable for CI artifacts or email; it does not replace
  Markdown PR comments.
- These formats do **not** block Milestone 7–10 work; wire them into `eval`
  the same way once that command lands on your branch.
