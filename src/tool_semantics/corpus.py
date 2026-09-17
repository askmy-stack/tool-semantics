"""Offline multi-domain benchmark corpus runner (#92) with split filter (#116).

Deterministic: manifests + probes + expected detection codes. No network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from tool_semantics.diff import CompatibilityReport, compare_snapshots
from tool_semantics.probes import evaluate_probes, load_probes
from tool_semantics.scanner import capture_manifest
from tool_semantics.splits import (
    DEFAULT_SPLITS_PATH,
    CorpusSplit,
    SplitsManifest,
    filter_case_dirs,
    load_splits_manifest,
    render_splits_markdown,
    resolve_split,
)

DEFAULT_CORPUS_ROOT = Path("benchmarks")

REQUIRED_CASE_FILES = (
    "baseline.json",
    "safe-change.json",
    "breaking-change.json",
    "probes.json",
    "expected-results.json",
)


class ExpectedSide(BaseModel):
    must_be_compatible: bool | None = None
    required_codes: list[str] = Field(default_factory=list)
    forbidden_codes: list[str] = Field(default_factory=list)
    required_subjects: list[str] = Field(default_factory=list)
    offline_probes_must_pass: bool | None = None


class ExpectedResults(BaseModel):
    safe_change: ExpectedSide = Field(default_factory=ExpectedSide)
    breaking_change: ExpectedSide = Field(default_factory=ExpectedSide)


class CaseResult(BaseModel):
    domain: str
    split: str | None = None
    passed: bool
    failures: list[str] = Field(default_factory=list)
    safe_codes: list[str] = Field(default_factory=list)
    breaking_codes: list[str] = Field(default_factory=list)


class CorpusReport(BaseModel):
    split: str | None = None
    results: list[CaseResult] = Field(default_factory=list)
    stubbed_domains: list[str] = Field(default_factory=list)
    skipped_domains: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.results)


def _is_full_case(path: Path) -> bool:
    return all((path / name).is_file() for name in REQUIRED_CASE_FILES)


def discover_corpus_cases(root: Path = DEFAULT_CORPUS_ROOT) -> tuple[list[Path], list[str]]:
    """Return (full case dirs, stubbed domain names). Ignores non-case files."""
    if not root.is_dir():
        return [], []
    cases: list[Path] = []
    stubs: list[str] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if _is_full_case(child):
            cases.append(child)
        else:
            # Ignore meta dirs / readme-only stubs without case files.
            stubs.append(child.name)
    return cases, stubs


def _check_side(
    label: str,
    report: CompatibilityReport,
    expected: ExpectedSide,
) -> list[str]:
    failures: list[str] = []
    codes = {change.code for change in report.changes}
    subjects = {change.subject for change in report.changes}
    if expected.must_be_compatible is True and not report.is_compatible:
        failures.append(f"{label}: expected compatible but got breaking/critical changes")
    if expected.must_be_compatible is False and report.is_compatible:
        failures.append(f"{label}: expected incompatible but report is compatible")
    for code in expected.required_codes:
        if code not in codes:
            failures.append(f"{label}: missing required change code `{code}`")
    for code in expected.forbidden_codes:
        if code in codes:
            failures.append(f"{label}: forbidden change code `{code}` present")
    for subject in expected.required_subjects:
        if subject not in subjects:
            failures.append(f"{label}: missing required subject `{subject}`")
    return failures


def run_corpus_case(case_dir: Path, *, split: str | None = None) -> CaseResult:
    domain = case_dir.name
    expected = ExpectedResults.model_validate(
        json.loads((case_dir / "expected-results.json").read_text(encoding="utf-8"))
    )
    baseline = capture_manifest(case_dir / "baseline.json")
    safe = capture_manifest(case_dir / "safe-change.json")
    breaking = capture_manifest(case_dir / "breaking-change.json")
    probes = load_probes(case_dir / "probes.json")

    safe_report = compare_snapshots(baseline, safe)
    breaking_report = compare_snapshots(baseline, breaking)
    probe_report = evaluate_probes(baseline, probes)

    failures: list[str] = []
    failures.extend(_check_side("safe-change", safe_report, expected.safe_change))
    failures.extend(_check_side("breaking-change", breaking_report, expected.breaking_change))
    if expected.safe_change.offline_probes_must_pass is True and not probe_report.passed:
        failures.append("baseline offline probes were expected to pass")
    if expected.safe_change.offline_probes_must_pass is False and probe_report.passed:
        failures.append("baseline offline probes were expected to fail")

    return CaseResult(
        domain=domain,
        split=split,
        passed=not failures,
        failures=failures,
        safe_codes=sorted({change.code for change in safe_report.changes}),
        breaking_codes=sorted({change.code for change in breaking_report.changes}),
    )


def run_corpus(
    root: Path = DEFAULT_CORPUS_ROOT,
    *,
    split: str | CorpusSplit | None = None,
    splits_path: Path = DEFAULT_SPLITS_PATH,
    require_splits: bool = True,
) -> CorpusReport:
    """Run corpus cases, optionally filtered to a DEV/TEST/VERIFIED partition."""
    cases, stubs = discover_corpus_cases(root)
    active: CorpusSplit | None = None
    skipped: list[str] = []
    manifest: SplitsManifest | None = None

    if require_splits or split is not None or splits_path.is_file():
        manifest = load_splits_manifest(splits_path)
        active = resolve_split(split)
        selected = filter_case_dirs(cases, active, manifest)
        skipped = sorted({path.name for path in cases} - {path.name for path in selected})
        cases = selected

    results = [
        run_corpus_case(case_dir, split=active.value if active else None) for case_dir in cases
    ]
    return CorpusReport(
        split=active.value if active else None,
        results=results,
        stubbed_domains=stubs,
        skipped_domains=skipped,
    )


def render_corpus_markdown(report: CorpusReport, *, manifest: SplitsManifest | None = None) -> str:
    stubbed = ", ".join(report.stubbed_domains) or "none"
    skipped = ", ".join(f"`{name}`" for name in report.skipped_domains) or "none"
    lines = [
        "## Benchmark corpus",
        "",
        f"Split: `{report.split or 'all'}` · cases: {len(report.results)} · "
        f"skipped: {skipped} · stubbed: {stubbed}.",
        "",
        "| Domain | Split | Passed | Failures |",
        "| --- | --- | --- | --- |",
    ]
    for item in report.results:
        fails = "; ".join(item.failures) if item.failures else "—"
        safe_fails = fails.replace("|", r"\|")
        passed = "yes" if item.passed else "no"
        lines.append(f"| `{item.domain}` | `{item.split or '—'}` | {passed} | {safe_fails} |")
    lines.append("")
    if manifest is not None:
        lines.append(render_splits_markdown(manifest).rstrip())
        lines.append("")
    return "\n".join(lines)


def load_case_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Case manifest must be a JSON object: {path}")
    return payload
