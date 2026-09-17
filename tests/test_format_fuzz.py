"""Tests for format-sensitivity fuzzing (#111)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from tool_semantics.cli import app
from tool_semantics.format_fuzz import (
    FormatAwareFakeRunner,
    FormatTransform,
    generate_format_variants,
    render_format_sensitivity_markdown,
    run_format_sensitivity,
    schemas_semantically_equal,
    scripted_fake_factory,
)
from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract, ToolParameter
from tool_semantics.probes import Probe, ProbeKind
from tool_semantics.runner import FakeModelRunner, ModelCompletion, RunnerMetadata, ToolCallRequest
from tool_semantics.scanner import capture_manifest, write_snapshot

runner = CliRunner()


def _snapshot() -> InterfaceSnapshot:
    return InterfaceSnapshot(
        server_name="demo",
        tools=[
            ToolContract(
                name="search_issues",
                description="Search   GitHub   issues",
                parameters=[
                    ToolParameter(
                        name="query",
                        schema={"type": "string", "description": "q"},
                        required=True,
                        description="search query",
                    ),
                    ToolParameter(
                        name="state",
                        schema={"type": "string", "enum": ["open", "closed"]},
                        required=False,
                    ),
                ],
                risk=RiskLevel.READ_ONLY,
            ),
            ToolContract(
                name="create_issue",
                description="Create issue",
                parameters=[
                    ToolParameter(name="title", schema={"type": "string"}, required=True),
                    ToolParameter(name="body", schema={"type": "string"}, required=False),
                ],
                risk=RiskLevel.EXTERNAL_WRITE,
            ),
        ],
    )


def _probe() -> Probe:
    return Probe(
        id="search",
        intent="find bugs",
        kind=ProbeKind.POSITIVE,
        expected_tool="search_issues",
        required_params=["query"],
        approved=True,
        approved_by="ci",
    )


def _ok_completion() -> ModelCompletion:
    return ModelCompletion(
        tool_calls=[ToolCallRequest(name="search_issues", arguments={"query": "bugs"})],
        metadata=RunnerMetadata(provider="fake", model="fake"),
    )


def test_variants_preserve_semantics() -> None:
    snap = _snapshot()
    variants = generate_format_variants(snap, variants_per_transform=2)
    assert len(variants) == len(FormatTransform) * 2
    for transform, variant in variants:
        assert schemas_semantically_equal(snap, variant)
        assert variant.metadata["format_fuzz"]["transform"] == transform.value


def test_fake_runner_ci_path_no_warning() -> None:
    report = run_format_sensitivity(
        _snapshot(),
        [_probe()],
        scripted_fake_factory([_ok_completion()]),
        threshold=0.05,
        variants_per_transform=1,
        require_approval=True,
    )
    assert report.passed
    assert not report.warning
    md = render_format_sensitivity_markdown(report)
    assert "FORMAT SENSITIVITY" in md
    assert "No format-sensitivity warning" in md
    assert "property_order" in md


def test_format_aware_runner_emits_warning() -> None:
    def factory() -> FormatAwareFakeRunner:
        return FormatAwareFakeRunner(
            preferred_tool="search_issues",
            fallback_tool="create_issue",
        )

    report = run_format_sensitivity(
        _snapshot(),
        [_probe()],
        factory,
        threshold=0.05,
        transforms=[FormatTransform.EQUIVALENT_JSON_SCHEMA],
        variants_per_transform=1,
        require_approval=True,
    )
    assert report.warning
    assert "FORMAT SENSITIVITY WARNING" in report.warning_message


def test_fuzz_format_cli_fake(tmp_path: Path) -> None:
    snap_path = tmp_path / "snap.json"
    write_snapshot(capture_manifest(Path("examples/github_server_v1.json")), snap_path)
    probes = tmp_path / "probes.json"
    probes.write_text(
        """
{
  "probes": [
    {
      "id": "search",
      "intent": "find open issues",
      "expected_tool": "search_issues",
      "required_params": ["query"],
      "approved": true,
      "approved_by": "ci"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "fuzz-format",
            str(snap_path),
            "--probes",
            str(probes),
            "--fake",
            "--threshold",
            "0.05",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "FORMAT SENSITIVITY" in result.stdout
    assert isinstance(FakeModelRunner([_ok_completion()]), FakeModelRunner)
