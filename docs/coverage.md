# Coverage targets (#64)

CI runs `pytest --cov=tool_semantics`. After this work:

- **Target:** no module below **80%** without an explicit waiver below.
- Hotspots historically: `runner.py` (HTTP adapter), `mcp_capture.py` (SSE
  error branches), `cli.py` (header / SSE UX), `report.py` (model/stability
  renderers).

## Waivers

| Module | Notes |
| --- | --- |
| `cli.py` | Remaining gaps are interactive Rich error paths and rare provenance races; covered by happy-path + header/SSE CLI tests. Raise further when adding commands. |
| `mcp_capture.py` | Deep stdio/HTTP notification and protocol-edge branches; SSE timeout / empty endpoint / POST auth are covered. Full matrix needs more fixture modes. |
