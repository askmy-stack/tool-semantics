"""Standard `.tool-semantics/` project layout (#85).

Predictable locations for baselines, probes, behaviors, traces, and policy so
eval/replay/compare can discover defaults when flags are omitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Project-root policy config (existing convention).
DEFAULT_CONFIG_NAME = ".tool-semantics.toml"

# Behavioral baseline directory under the project root.
LAYOUT_DIRNAME = ".tool-semantics"

BASELINES_DIR = "baselines"
PROBES_DIR = "probes"
TRACES_DIR = "traces"
BEHAVIORS_FILE = "behaviors.toml"
CANDIDATE_SNAPSHOT = "candidate.json"
LAYOUT_README = "README.md"


@dataclass(frozen=True)
class ProjectPaths:
    """Resolved paths for a Tool-Semantics project root."""

    root: Path
    layout: Path
    baselines: Path
    probes: Path
    traces: Path
    behaviors: Path
    candidate: Path
    config: Path

    def baseline_snapshot(self, name: str = "baseline.json") -> Path:
        return self.baselines / name


def project_paths(root: Path | None = None) -> ProjectPaths:
    base = (root or Path.cwd()).resolve()
    layout = base / LAYOUT_DIRNAME
    return ProjectPaths(
        root=base,
        layout=layout,
        baselines=layout / BASELINES_DIR,
        probes=layout / PROBES_DIR,
        traces=layout / TRACES_DIR,
        behaviors=layout / BEHAVIORS_FILE,
        candidate=layout / CANDIDATE_SNAPSHOT,
        config=base / DEFAULT_CONFIG_NAME,
    )


_CONFIG_STUB = """\
# Tool-Semantics project config — see docs/config.md
# Ignored changes stay visible as info with an [ignored] prefix.

[ignore]
codes = []
subjects = []

[policy]
# info | warning | breaking | critical | none
fail_at_or_above = "breaking"
"""

_BEHAVIORS_STUB = """\
# Behavioral gate thresholds for eval / probe CI (#58 / #76).
# Adjust after reviewing offline + model-backed probe baselines.

[probes]
# Minimum tool-selection accuracy (0.0–1.0); omit to disable.
# min_tool_selection_accuracy = 0.8
# min_argument_validity_rate = 0.8

[stability]
# Mark probes unstable below this trial pass rate.
# min_stability_score = 0.75
"""

_PROBES_STUB = """\
{
  "probes": [
    {
      "id": "example-positive",
      "intent": "Replace with a real user intent for your tools",
      "kind": "positive",
      "expected_tool": "example_tool",
      "approved": false
    }
  ]
}
"""

_LAYOUT_README = """\
# Tool-Semantics project layout

This directory is the **behavioral baseline** home for Tool-Semantics (#85).

| Path | Purpose |
| --- | --- |
| `baselines/` | Reviewed baseline snapshots (check these in) |
| `candidate.json` | Working candidate snapshot from capture (optional) |
| `probes/` | Offline / model-backed probe fixtures |
| `behaviors.toml` | Probe / stability threshold stubs for CI gates |
| `traces/` | Agent traces for replay (#83 / #84) |

Policy and ignore rules live in `../.tool-semantics.toml` at the project root.

```bash
tool-semantics capture <manifest-or-mcp> -o .tool-semantics/baselines/baseline.json
tool-semantics probe .tool-semantics/baselines/baseline.json
tool-semantics compare .tool-semantics/baselines/baseline.json .tool-semantics/candidate.json
```

See [docs/project-layout.md](../docs/project-layout.md) when developing this repo.
"""


def scaffold_project(
    root: Path | None = None,
    *,
    force: bool = False,
) -> ProjectPaths:
    """Create the standard `.tool-semantics/` layout and root config stub.

    Existing files are left untouched unless ``force=True``.
    """
    paths = project_paths(root)
    paths.layout.mkdir(parents=True, exist_ok=True)
    paths.baselines.mkdir(parents=True, exist_ok=True)
    paths.probes.mkdir(parents=True, exist_ok=True)
    paths.traces.mkdir(parents=True, exist_ok=True)

    def _write(path: Path, content: str) -> None:
        if path.exists() and not force:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    _write(paths.config, _CONFIG_STUB)
    _write(paths.behaviors, _BEHAVIORS_STUB)
    _write(paths.probes / "example.json", _PROBES_STUB)
    _write(paths.layout / LAYOUT_README, _LAYOUT_README)
    # Keep traces/ discoverable in git via .gitkeep when empty.
    _write(paths.traces / ".gitkeep", "")
    return paths


def discover_default_probes(root: Path | None = None) -> Path | None:
    """Return a default probes file when present under `.tool-semantics/probes/`."""
    probes_dir = project_paths(root).probes
    if not probes_dir.is_dir():
        return None
    preferred = [
        probes_dir / "probes.json",
        probes_dir / "example.json",
    ]
    for path in preferred:
        if path.is_file():
            return path
    json_files = sorted(probes_dir.glob("*.json"))
    if json_files:
        return json_files[0]
    yaml_files = sorted(list(probes_dir.glob("*.yaml")) + list(probes_dir.glob("*.yml")))
    if yaml_files:
        return yaml_files[0]
    return None


def discover_default_baseline(root: Path | None = None) -> Path | None:
    """Return `.tool-semantics/baselines/baseline.json` when it exists."""
    path = project_paths(root).baseline_snapshot()
    return path if path.is_file() else None


def discover_default_candidate(root: Path | None = None) -> Path | None:
    path = project_paths(root).candidate
    return path if path.is_file() else None
