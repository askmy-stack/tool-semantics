from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from tool_semantics import __version__
from tool_semantics.diff import compare_snapshots
from tool_semantics.report import render_markdown, severity_style
from tool_semantics.scanner import ManifestError, capture_manifest, read_snapshot, write_snapshot

app = typer.Typer(
    no_args_is_help=True,
    help="Behavioral compatibility testing for MCP tools and AI-agent interfaces.",
)
console = Console()


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


@app.command()
def capture(
    manifest: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path(".tool-semantics/snapshot.json"),
) -> None:
    """Normalize a JSON tool manifest into a Tool-Semantics snapshot."""
    try:
        snapshot = capture_manifest(manifest)
        write_snapshot(snapshot, output)
    except ManifestError as exc:
        console.print(f"[red]Capture failed:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    console.print(
        f"[green]Captured[/green] {len(snapshot.tools)} tools from "
        f"[bold]{snapshot.server_name}[/bold] into {output}"
    )


@app.command()
def compare(
    baseline: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    candidate: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    json_output: Annotated[Path | None, typer.Option("--json-output")] = None,
    markdown_output: Annotated[Path | None, typer.Option("--markdown-output")] = None,
) -> None:
    """Compare two Tool-Semantics snapshots."""
    try:
        report = compare_snapshots(read_snapshot(baseline), read_snapshot(candidate))
    except ManifestError as exc:
        console.print(f"[red]Comparison failed:[/red] {exc}")
        raise typer.Exit(code=2) from exc

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
    console.print(f"Result: [bold]{'compatible' if report.is_compatible else 'breaking'}[/bold]")

    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
        )
    if markdown_output is not None:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(render_markdown(report), encoding="utf-8")
    if not report.is_compatible:
        raise typer.Exit(code=1)
