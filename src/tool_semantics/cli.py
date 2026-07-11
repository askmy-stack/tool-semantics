from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from tool_semantics import __version__
from tool_semantics.config import apply_ignore_rules, load_config
from tool_semantics.diff import compare_snapshots
from tool_semantics.mcp_capture import McpCaptureError, capture_mcp_sse, capture_mcp_stdio
from tool_semantics.policy import policy_from_name
from tool_semantics.report import render_markdown, severity_style
from tool_semantics.scanner import ManifestError, capture_manifest, read_snapshot, write_snapshot

app = typer.Typer(
    no_args_is_help=True,
    help=(
        "Tool-Semantics: behavioral compatibility testing for MCP tools and AI-agent interfaces. "
        "Exit codes: 0=compatible, 1=breaking/critical, 2=input error."
    ),
)
console = Console()
err_console = Console(stderr=True)


def version_callback(value: bool) -> None:
    if value:
        console.print(f"tool-semantics {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None, typer.Option("--version", callback=version_callback, is_eager=True)
    ] = None,
) -> None:
    """Tool-Semantics command-line interface."""


def _log_verbose(verbose: bool, message: str) -> None:
    if verbose:
        err_console.print(f"[dim]{message}[/dim]")


@app.command()
def capture(
    manifest: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            help="Path to a JSON tool manifest (MCP-style tools array).",
        ),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Where to write the normalized snapshot JSON.",
        ),
    ] = Path(".tool-semantics/snapshot.json"),
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Log capture steps to stderr (paths and tool counts).",
        ),
    ] = False,
) -> None:
    """Normalize a JSON tool manifest into a Tool-Semantics snapshot."""
    _log_verbose(verbose, f"Reading manifest {manifest.resolve()}")
    try:
        snapshot = capture_manifest(manifest)
        write_snapshot(snapshot, output)
    except ManifestError as exc:
        console.print(f"[red]Capture failed:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    _log_verbose(
        verbose,
        f"Wrote snapshot {output.resolve()} with {len(snapshot.tools)} tools "
        f"(server={snapshot.server_name})",
    )
    console.print(
        f"[green]Captured[/green] {len(snapshot.tools)} tools from "
        f"[bold]{snapshot.server_name}[/bold] into {output}"
    )


@app.command("capture-mcp")
def capture_mcp(
    command: Annotated[
        list[str] | None,
        typer.Argument(
            help="MCP server command after `--`, e.g. `python fake_server.py`.",
        ),
    ] = None,
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Where to write the normalized snapshot JSON.",
        ),
    ] = Path(".tool-semantics/snapshot.json"),
    sse_url: Annotated[
        str | None,
        typer.Option("--sse", help="SSE MCP endpoint URL (not implemented yet)."),
    ] = None,
    server_name: Annotated[
        str | None,
        typer.Option("--server-name", help="Override captured server name."),
    ] = None,
    no_redact: Annotated[
        bool,
        typer.Option("--no-redact", help="Disable secret redaction (not recommended)."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Log capture steps to stderr."),
    ] = False,
) -> None:
    """Capture a live MCP server over stdio (or attempt SSE)."""
    try:
        if sse_url:
            snapshot = capture_mcp_sse(sse_url)
        else:
            if not command:
                console.print(
                    "[red]Provide an MCP command after `--` or pass --sse <url>.[/red]\n"
                    "Example: tool-semantics capture-mcp -o snap.json -- python server.py"
                )
                raise typer.Exit(code=2)
            _log_verbose(verbose, f"Starting MCP stdio server: {command}")
            snapshot = capture_mcp_stdio(
                command,
                server_name=server_name,
                redact=not no_redact,
            )
        write_snapshot(snapshot, output)
    except (McpCaptureError, ManifestError) as exc:
        console.print(f"[red]MCP capture failed:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    _log_verbose(
        verbose,
        (
            f"Captured tools={len(snapshot.tools)} prompts={len(snapshot.prompts)} "
            f"resources={len(snapshot.resources)} → {output.resolve()}"
        ),
    )
    console.print(
        f"[green]Captured[/green] {len(snapshot.tools)} tools / "
        f"{len(snapshot.prompts)} prompts / {len(snapshot.resources)} resources from "
        f"[bold]{snapshot.server_name}[/bold] into {output}"
    )


def _require_snapshot_file(path: Path, label: str) -> Path:
    if not path.is_file():
        console.print(
            f"[red]{label} snapshot not found:[/red] {path}\n"
            "Run [bold]tool-semantics capture <manifest.json> -o "
            f"{path}[/bold] first, then compare."
        )
        raise typer.Exit(code=2)
    return path


@app.command()
def compare(
    baseline: Annotated[
        Path,
        typer.Argument(dir_okay=False, help="Baseline snapshot JSON from `capture`."),
    ],
    candidate: Annotated[
        Path,
        typer.Argument(dir_okay=False, help="Candidate snapshot JSON from `capture`."),
    ],
    json_output: Annotated[
        Path | None,
        typer.Option(
            "--json-output",
            help="Write a JSON report including changes, counts, and is_compatible.",
        ),
    ] = None,
    markdown_output: Annotated[
        Path | None,
        typer.Option(
            "--markdown-output",
            help="Write a GitHub-friendly Markdown report.",
        ),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to `.tool-semantics.toml` (default: look in cwd).",
        ),
    ] = None,
    policy: Annotated[
        str | None,
        typer.Option(
            "--policy",
            help=(
                "Release policy override: compatible|strict|critical-only|permissive "
                "(default: config policy or breaking)."
            ),
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Log compare steps to stderr (paths, tool counts, change totals).",
        ),
    ] = False,
) -> None:
    """Compare two Tool-Semantics snapshots (exit 1 when release policy fails)."""
    _require_snapshot_file(baseline, "Baseline")
    _require_snapshot_file(candidate, "Candidate")
    _log_verbose(verbose, f"Loading baseline {baseline.resolve()}")
    _log_verbose(verbose, f"Loading candidate {candidate.resolve()}")
    try:
        config_data = load_config(config)
        release_policy = policy_from_name(policy) if policy else config_data.policy
        baseline_snap = read_snapshot(baseline)
        candidate_snap = read_snapshot(candidate)
        _log_verbose(
            verbose,
            f"Tools: baseline={len(baseline_snap.tools)} candidate={len(candidate_snap.tools)}",
        )
        report = apply_ignore_rules(
            compare_snapshots(baseline_snap, candidate_snap),
            config_data,
        )
    except (ManifestError, FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Comparison failed:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    counts = report.counts_by_severity()
    fails_policy = release_policy.should_fail(report)
    _log_verbose(
        verbose,
        f"Changes={len(report.changes)} counts={counts} "
        f"compatible={report.is_compatible} policy_fail={fails_policy}",
    )

    table = Table(title=f"Tool-Semantics: {report.baseline} → {report.candidate}")
    for heading in ("Severity", "Code", "Subject", "Change"):
        table.add_column(heading)
    for change in report.changes:
        table.add_row(
            f"[{severity_style(change.severity)}]{change.severity.value}[/]",
            change.code,
            change.subject,
            change.message,
        )
    console.print(table if report.changes else "[green]No structural changes detected.[/green]")
    console.print(
        f"Result: [bold]{'compatible' if report.is_compatible else 'breaking'}[/bold] "
        f"(policy={release_policy.fail_at_or_above.value})"
    )

    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        payload = report.model_dump(mode="json")
        payload["is_compatible"] = report.is_compatible
        payload["counts"] = report.counts_by_severity()
        payload["policy"] = {
            "fail_at_or_above": release_policy.fail_at_or_above.value,
            "failed": fails_policy,
        }
        json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if markdown_output is not None:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(render_markdown(report), encoding="utf-8")
    if fails_policy:
        raise typer.Exit(code=1)
