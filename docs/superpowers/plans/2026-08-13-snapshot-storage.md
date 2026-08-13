# Snapshot Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional provenance sidecars for captured snapshots and optional GitHub Actions artifacts for compare outputs.

**Architecture:** Keep `InterfaceSnapshot` unchanged so compatibility comparison remains deterministic. A new provenance module hashes the exact snapshot bytes and writes a separate, redacted JSON sidecar. The composite Action conditionally uploads candidate and compare-report files as a diagnostic artifact; Git-tracked snapshot JSON remains the approved baseline.

**Tech Stack:** Python 3.11+, Pydantic, Typer, pytest, GitHub composite Actions, `actions/upload-artifact@v4`.

**Spec:** `docs/superpowers/specs/2026-08-13-snapshot-storage-design.md`

## Global Constraints

- Do not add a database, object-storage client, or new runtime dependency.
- Do not change the `InterfaceSnapshot` schema or include changing provenance fields in snapshot comparisons.
- Provenance must never serialize authorization headers, environment variables, or unredacted secret-like source values.
- Git baselines remain normal user-managed JSON files; artifacts are optional diagnostics.
- Preserve existing stdio and manifest capture behavior when provenance is not requested.

---

## File Structure

- Create `src/tool_semantics/provenance.py`: pure provenance creation and JSON writing.
- Create `tests/test_provenance.py`: deterministic digest and redaction behavior.
- Modify `src/tool_semantics/cli.py`: add `--provenance-output` to both capture commands.
- Modify `tests/test_cli.py`: verify both CLI capture paths write usable sidecars.
- Modify `.github/actions/compare/action.yml`: add optional artifact upload.
- Modify `docs/github-action.md` and `README.md`: document baseline, provenance, and artifacts.

### Task 1: Provenance sidecar module

**Files:**
- Create: `src/tool_semantics/provenance.py`
- Test: `tests/test_provenance.py`

**Interfaces:**
- Produces: `write_provenance(snapshot_path: Path, output_path: Path, source: dict[str, Any], captured_at: datetime | None = None) -> None`
- Produces: `snapshot_sha256(snapshot_path: Path) -> str`
- Consumes: `tool_semantics.redact.redact_mapping`

- [ ] **Step 1: Write the failing digest and redaction tests**

```python
from datetime import UTC, datetime
import json

from tool_semantics.provenance import write_provenance


def test_write_provenance_hashes_snapshot_and_redacts_source(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text('{"server_name":"demo"}\n', encoding="utf-8")
    output = tmp_path / "provenance.json"

    write_provenance(
        snapshot,
        output,
        {"kind": "mcp-stdio", "command": ["server", "--token=secret"]},
        captured_at=datetime(2026, 8, 13, tzinfo=UTC),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["provenance_version"] == "0.1"
    assert payload["snapshot_sha256"] == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert payload["source"]["command"][1] == "***REDACTED***"
    assert payload["captured_at"] == "2026-08-13T00:00:00+00:00"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_provenance.py::test_write_provenance_hashes_snapshot_and_redacts_source -v`

Expected: FAIL because `tool_semantics.provenance` does not exist.

- [ ] **Step 3: Implement the smallest provenance API**

```python
def snapshot_sha256(snapshot_path: Path) -> str:
    return hashlib.sha256(snapshot_path.read_bytes()).hexdigest()


def write_provenance(
    snapshot_path: Path,
    output_path: Path,
    source: dict[str, Any],
    captured_at: datetime | None = None,
) -> None:
    timestamp = captured_at or datetime.now(UTC)
    payload = {
        "provenance_version": "0.1",
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": snapshot_sha256(snapshot_path),
        "captured_at": timestamp.isoformat(),
        "source": redact_mapping(source),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
```

Use a redaction helper that also detects token-bearing command arguments such as
`--token=secret`, not only mapping keys.

- [ ] **Step 4: Run the provenance tests to verify they pass**

Run: `pytest tests/test_provenance.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the provenance module**

```bash
git add src/tool_semantics/provenance.py tests/test_provenance.py
git commit -m "add snapshot provenance sidecars"
```

### Task 2: Capture CLI provenance output

**Files:**
- Modify: `src/tool_semantics/cli.py:50-160`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `write_provenance(snapshot_path, output_path, source)` from Task 1.
- Produces: `capture --provenance-output PATH` and `capture-mcp --provenance-output PATH`.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_capture_writes_requested_provenance(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.json"
    provenance = tmp_path / "snapshot.provenance.json"
    result = runner.invoke(
        app,
        [
            "capture", "examples/github_server_v1.json", "-o", str(snapshot),
            "--provenance-output", str(provenance),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(provenance.read_text(encoding="utf-8"))
    assert payload["source"] == {"kind": "manifest", "location": "examples/github_server_v1.json"}
```

Add a second test that invokes `capture-mcp` with the existing fake server and
asserts its source kind is `mcp-stdio` and command values are redacted.

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/test_cli.py -v`

Expected: FAIL because `--provenance-output` is not recognized.

- [ ] **Step 3: Add the CLI option and write the sidecar after each snapshot write**

```python
provenance_output: Annotated[
    Path | None,
    typer.Option("--provenance-output", help="Write capture provenance JSON separately."),
] = None,
```

After `write_snapshot(snapshot, output)`, call `write_provenance` only when the
option is supplied. For `capture`, pass `{"kind": "manifest", "location": str(manifest)}`.
For stdio capture, pass `{"kind": "mcp-stdio", "command": command}`. Route
provenance exceptions through the existing capture error handler as exit code 2.

- [ ] **Step 4: Run CLI tests to verify they pass**

Run: `pytest tests/test_cli.py -v`

Expected: PASS.

- [ ] **Step 5: Commit CLI support**

```bash
git add src/tool_semantics/cli.py tests/test_cli.py
git commit -m "add capture provenance output"
```

### Task 3: Optional compare artifacts

**Files:**
- Modify: `.github/actions/compare/action.yml`
- Test: `.github/actions/compare/action.yml` static assertions in a new `tests/test_github_action.py`

**Interfaces:**
- Produces: Action input `upload-artifacts`, default `"false"`.
- Produces: Artifact named `tool-semantics-report` containing candidate snapshot,
  `report.md`, and `report.json` when enabled.

- [ ] **Step 1: Write a failing Action contract test**

```python
def test_compare_action_can_upload_candidate_and_reports() -> None:
    action = yaml.safe_load(Path(".github/actions/compare/action.yml").read_text())
    assert action["inputs"]["upload-artifacts"]["default"] == "false"
    upload = next(step for step in action["runs"]["steps"] if step["name"] == "Upload report artifact")
    assert "inputs.upload-artifacts == 'true'" in upload["if"]
    assert "${{ inputs.candidate }}" in upload["with"]["path"]
    assert "${{ steps.compare.outputs.report-path }}" in upload["with"]["path"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_github_action.py::test_compare_action_can_upload_candidate_and_reports -v`

Expected: FAIL because the action has no artifact input or upload step.

- [ ] **Step 3: Add the optional artifact input and upload step**

```yaml
  upload-artifacts:
    description: Upload candidate snapshot and generated reports as a workflow artifact.
    required: false
    default: "false"
```

Add a final `actions/upload-artifact@v4` step named `Upload report artifact`:

```yaml
    - name: Upload report artifact
      if: ${{ inputs.upload-artifacts == 'true' }}
      uses: actions/upload-artifact@v4
      with:
        name: tool-semantics-report
        if-no-files-found: error
        path: |
          ${{ inputs.candidate }}
          ${{ steps.compare.outputs.report-path }}
          ${{ runner.temp }}/tool-semantics/report.json
```

- [ ] **Step 4: Run the Action contract test to verify it passes**

Run: `pytest tests/test_github_action.py -v`

Expected: PASS.

- [ ] **Step 5: Commit Action artifact support**

```bash
git add .github/actions/compare/action.yml tests/test_github_action.py
git commit -m "add optional compare artifacts"
```

### Task 4: Documentation and full verification

**Files:**
- Modify: `README.md:127-151`
- Modify: `docs/github-action.md:35-82`
- Modify: `docs/architecture.md:34-62`

**Interfaces:**
- Documents: Git-tracked baselines as the source of truth, optional provenance
  sidecars, and diagnostic Action artifacts.

- [ ] **Step 1: Document the baseline and provenance command**

Add this README example:

```bash
tool-semantics capture examples/github_server_v1.json \
  -o .tool-semantics/baselines/github.json \
  --provenance-output .tool-semantics/baselines/github.provenance.json
```

Explain that the snapshot is committed as the approved contract, while the
separate provenance file records capture context and digest without affecting
compatibility comparisons.

- [ ] **Step 2: Document Action artifacts**

Add `upload-artifacts: "true"` to the GitHub Action example and state that the
artifact includes the candidate snapshot plus Markdown and JSON reports. State
that artifacts are diagnostic and do not replace Git baselines.

- [ ] **Step 3: Update architecture output labels**

Add provenance sidecars and optional CI artifacts to the architecture output
description, while retaining JSON snapshots as the canonical compare input.

- [ ] **Step 4: Run full verification**

Run:

```bash
python -m pytest --cov=tool_semantics --cov-report=term-missing
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m build
```

Expected: all commands succeed.

- [ ] **Step 5: Commit documentation and verification changes**

```bash
git add README.md docs/github-action.md docs/architecture.md
git commit -m "document snapshot storage workflow"
```

## Plan Self-Review

- Spec coverage: Git baselines are documented in Task 4; provenance sidecars and
  secret handling are implemented in Tasks 1-2; optional CI artifacts are added
  in Task 3; no database or object storage is introduced.
- Placeholder scan: no deferred implementation markers or undefined tasks remain.
- Type consistency: Task 1 defines `write_provenance`; Task 2 consumes that exact
  function signature. Artifact input and output paths are defined before use.
