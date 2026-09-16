from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from tool_semantics import __version__
from tool_semantics.config import apply_ignore_rules, load_config
from tool_semantics.diff import compare_snapshots
from tool_semantics.mcp_capture import (
    McpCaptureError,
    capture_mcp_http,
    capture_mcp_remote,
    capture_mcp_sse,
    capture_mcp_stdio,
)
from tool_semantics.policy import policy_from_name
from tool_semantics.probes import (
    evaluate_probes,
    evaluate_probes_with_model,
    load_probes,
    run_probe_trials,
)
from tool_semantics.provenance import write_provenance
from tool_semantics.report import (
    render_markdown,
    render_model_probe_report_markdown,
    render_offline_probe_report_json,
    render_offline_probe_report_markdown,
    render_stability_json,
    render_stability_markdown,
    severity_style,
)
from tool_semantics.runner import OpenAICompatibleRunner, RunnerConfig
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


def _parse_headers(raw_headers: list[str] | None) -> dict[str, str]:
    """Parse CLI `--header 'Name: value'` options into a mapping."""
    headers: dict[str, str] = {}
    if not raw_headers:
        return headers
    for item in raw_headers:
        if ":" not in item:
            console.print(f"[red]Invalid --header (expected 'Name: value'):[/red] {item!r}")
            raise typer.Exit(code=2)
        name, value = item.split(":", 1)
        name = name.strip()
        if not name:
            console.print(f"[red]Invalid --header name in:[/red] {item!r}")
            raise typer.Exit(code=2)
        headers[name] = value.lstrip()
    return headers


def _reject_equivalent_output_paths(snapshot_path: Path, provenance_path: Path | None) -> None:
    """Prevent a provenance sidecar from replacing the newly captured snapshot."""
    if provenance_path is not None and snapshot_path.resolve() == provenance_path.resolve():
        console.print(
            "[red]Capture failed:[/red] Snapshot and provenance output paths must be different."
        )
        raise typer.Exit(code=2)


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
    provenance_output: Annotated[
        Path | None,
        typer.Option("--provenance-output", help="Write capture provenance JSON separately."),
    ] = None,
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
    _reject_equivalent_output_paths(output, provenance_output)
    _log_verbose(verbose, f"Reading manifest {manifest.resolve()}")
    try:
        snapshot = capture_manifest(manifest)
        write_snapshot(snapshot, output)
    except ManifestError as exc:
        console.print(f"[red]Capture failed:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    if provenance_output:
        try:
            write_provenance(
                output,
                provenance_output,
                {"kind": "manifest", "location": str(manifest)},
            )
        except OSError as exc:
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
            help=(
                "MCP server command after `--`, or a bare http(s) URL for remote "
                "auto-detect (Streamable HTTP, then legacy SSE)."
            ),
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
    provenance_output: Annotated[
        Path | None,
        typer.Option("--provenance-output", help="Write capture provenance JSON separately."),
    ] = None,
    sse_url: Annotated[
        str | None,
        typer.Option(
            "--sse",
            help="Remote MCP legacy SSE endpoint URL (JSON-RPC over SSE + message POST).",
        ),
    ] = None,
    http_url: Annotated[
        str | None,
        typer.Option(
            "--http",
            help="Remote MCP Streamable HTTP endpoint URL (single MCP endpoint POST).",
        ),
    ] = None,
    header: Annotated[
        list[str] | None,
        typer.Option(
            "--header",
            "-H",
            help=(
                "HTTP header for remote capture as 'Name: value' (repeatable). "
                "Auth header values are never written to snapshot metadata."
            ),
        ),
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
    """Capture a live MCP server over stdio, Streamable HTTP, or legacy SSE."""
    _reject_equivalent_output_paths(output, provenance_output)
    modes = sum(1 for flag in (sse_url, http_url) if flag)
    bare_url: str | None = None
    stdio_command: list[str] | None = None
    if command:
        if (
            len(command) == 1
            and isinstance(command[0], str)
            and command[0].startswith(("http://", "https://"))
        ):
            bare_url = command[0]
        else:
            stdio_command = command
    if modes + (1 if bare_url else 0) + (1 if stdio_command else 0) > 1:
        console.print(
            "[red]Specify only one capture target:[/red] a stdio command, "
            "a bare URL, --http <url>, or --sse <url>."
        )
        raise typer.Exit(code=2)

    provenance_source: dict[str, object]
    try:
        if http_url:
            headers = _parse_headers(header)
            _log_verbose(verbose, f"Connecting to MCP Streamable HTTP endpoint: {http_url}")
            snapshot = capture_mcp_http(
                http_url,
                headers=headers,
                server_name=server_name,
                redact=not no_redact,
            )
            provenance_source = {"kind": "mcp-http", "endpoint": http_url}
        elif sse_url:
            headers = _parse_headers(header)
            _log_verbose(verbose, f"Connecting to MCP SSE endpoint: {sse_url}")
            snapshot = capture_mcp_sse(
                sse_url,
                headers=headers,
                server_name=server_name,
                redact=not no_redact,
            )
            provenance_source = {"kind": "mcp-sse", "endpoint": sse_url}
        elif bare_url:
            headers = _parse_headers(header)
            _log_verbose(
                verbose,
                f"Auto-detecting remote MCP transport for: {bare_url}",
            )
            snapshot = capture_mcp_remote(
                bare_url,
                headers=headers,
                server_name=server_name,
                redact=not no_redact,
            )
            provenance_source = {
                "kind": snapshot.protocol,
                "endpoint": bare_url,
            }
        else:
            if not stdio_command:
                console.print(
                    "[red]Provide an MCP command after `--`, a bare http(s) URL, "
                    "--http <url>, or --sse <url>.[/red]\n"
                    "Examples:\n"
                    "  tool-semantics capture-mcp -o snap.json -- python server.py\n"
                    "  tool-semantics capture-mcp -o snap.json https://example.com/mcp\n"
                    "  tool-semantics capture-mcp -o snap.json --http https://example.com/mcp"
                )
                raise typer.Exit(code=2)
            _log_verbose(verbose, f"Starting MCP stdio server: {stdio_command}")
            snapshot = capture_mcp_stdio(
                stdio_command,
                server_name=server_name,
                redact=not no_redact,
            )
            provenance_source = {"kind": "mcp-stdio", "command": stdio_command}
        write_snapshot(snapshot, output)
    except (McpCaptureError, ManifestError) as exc:
        console.print(f"[red]MCP capture failed:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    if provenance_output:
        try:
            write_provenance(output, provenance_output, provenance_source)
        except OSError as exc:
            console.print(f"[red]MCP capture failed:[/red] {exc}")
            raise typer.Exit(code=2) from exc
    _log_verbose(
        verbose,
        (
            f"Captured tools={len(snapshot.tools)} prompts={len(snapshot.prompts)} "
            f"resources={len(snapshot.resources)} "
            f"protocol_version={snapshot.metadata.get('protocol_version')} "
            f"→ {output.resolve()}"
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


def _openai_runner_from_env(
    *,
    model: str | None,
    api_key: str | None,
    base_url: str | None,
) -> OpenAICompatibleRunner:
    resolved_model = (
        model
        or os.environ.get("TOOL_SEMANTICS_MODEL")
        or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    )
    resolved_key = (
        api_key or os.environ.get("TOOL_SEMANTICS_API_KEY") or os.environ.get("OPENAI_API_KEY")
    )
    resolved_base = (
        base_url
        or os.environ.get("TOOL_SEMANTICS_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    )
    if not resolved_key:
        console.print(
            "[red]Model-backed probes require an API key.[/red]\n"
            "Set TOOL_SEMANTICS_API_KEY or OPENAI_API_KEY, or pass --api-key.\n"
            "See docs/probes.md."
        )
        raise typer.Exit(code=2)
    try:
        return OpenAICompatibleRunner(
            model=resolved_model,
            api_key=resolved_key,
            base_url=resolved_base,
        )
    except ValueError as exc:
        console.print(f"[red]Invalid model runner config:[/red] {exc}")
        raise typer.Exit(code=2) from exc


@app.command()
def probe(
    snapshot: Annotated[
        Path,
        typer.Argument(dir_okay=False, help="Snapshot JSON from `capture` / `capture-mcp`."),
    ],
    probes_file: Annotated[
        Path,
        typer.Option(
            "--probes",
            "-p",
            help="Probe suite JSON or YAML (list or {probes: [...]}).",
        ),
    ],
    model: Annotated[
        bool,
        typer.Option(
            "--model",
            help="Opt-in model-backed evaluation (requires approved probes + API key).",
        ),
    ] = False,
    trials: Annotated[
        int,
        typer.Option(
            "--trials",
            help="Repeat model-backed probes for stability (implies --model when > 1).",
        ),
    ] = 1,
    seed: Annotated[
        int | None,
        typer.Option("--seed", help="Base seed for model-backed trials (optional)."),
    ] = None,
    model_name: Annotated[
        str | None,
        typer.Option("--model-name", help="Model id (or TOOL_SEMANTICS_MODEL / OPENAI_MODEL)."),
    ] = None,
    api_key: Annotated[
        str | None,
        typer.Option(
            "--api-key",
            help="API key (prefer TOOL_SEMANTICS_API_KEY / OPENAI_API_KEY env).",
        ),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option(
            "--base-url",
            help="OpenAI-compatible base URL (or TOOL_SEMANTICS_BASE_URL).",
        ),
    ] = None,
    allow_unapproved: Annotated[
        bool,
        typer.Option(
            "--allow-unapproved",
            help="Allow model-backed runs without approved=true (not recommended).",
        ),
    ] = False,
    json_output: Annotated[
        Path | None,
        typer.Option("--json-output", help="Write a JSON probe report."),
    ] = None,
    markdown_output: Annotated[
        Path | None,
        typer.Option("--markdown-output", help="Write a Markdown probe report."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Log probe steps to stderr."),
    ] = False,
) -> None:
    """Run offline (default) or opt-in model-backed behavioral probes."""
    _require_snapshot_file(snapshot, "Probe")
    if not probes_file.is_file():
        console.print(f"[red]Probe file not found:[/red] {probes_file}")
        raise typer.Exit(code=2)
    if trials < 1:
        console.print("[red]--trials must be >= 1[/red]")
        raise typer.Exit(code=2)

    use_model = model or trials > 1
    _log_verbose(verbose, f"Loading snapshot {snapshot.resolve()}")
    _log_verbose(verbose, f"Loading probes {probes_file.resolve()}")
    try:
        snap = read_snapshot(snapshot)
        probes = load_probes(probes_file)
    except (ManifestError, FileNotFoundError, ValueError, OSError) as exc:
        console.print(f"[red]Probe load failed:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    _log_verbose(verbose, f"Probes={len(probes)} tools={len(snap.tools)} model={use_model}")

    if not use_model:
        report = evaluate_probes(snap, probes)
        table = Table(title=f"Offline probes: {snap.server_name}")
        table.add_column("Probe")
        table.add_column("Passed")
        table.add_column("Message")
        for result in report.results:
            color = "green" if result.passed else "red"
            table.add_row(
                result.probe_id,
                f"[{color}]{'yes' if result.passed else 'no'}[/]",
                result.message,
            )
        console.print(table)
        console.print(f"Result: [bold]{'PASS' if report.passed else 'FAIL'}[/bold]")
        if json_output is not None:
            json_output.parent.mkdir(parents=True, exist_ok=True)
            payload = render_offline_probe_report_json(report)
            payload["snapshot"] = str(snapshot)
            json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        if markdown_output is not None:
            markdown_output.parent.mkdir(parents=True, exist_ok=True)
            markdown_output.write_text(
                render_offline_probe_report_markdown(report, snapshot_label=str(snapshot)),
                encoding="utf-8",
            )
        if not report.passed:
            raise typer.Exit(code=1)
        return

    runner = _openai_runner_from_env(model=model_name, api_key=api_key, base_url=base_url)
    require_approval = not allow_unapproved
    cfg = RunnerConfig(seed=seed)
    if trials > 1:
        stability = run_probe_trials(
            snap,
            probes,
            runner,
            trial_count=trials,
            config=cfg,
            require_approval=require_approval,
            seed=seed,
        )
        failed = [
            item
            for item in stability.summaries
            if item.deterministic_failure or (not item.aggregate_passed and not item.unstable)
        ]
        unstable = [item for item in stability.summaries if item.unstable]
        # Treat unstable or deterministic failure as exit 1.
        failed_policy = bool(failed or unstable)
        table = Table(title=f"Stability probes ({trials} trials): {snap.server_name}")
        table.add_column("Probe")
        table.add_column("Stability")
        table.add_column("Unstable")
        table.add_column("Det. fail")
        table.add_column("Passed")
        for summary in stability.summaries:
            table.add_row(
                summary.probe_id,
                f"{summary.stability_score:.2f}",
                "yes" if summary.unstable else "no",
                "yes" if summary.deterministic_failure else "no",
                "yes" if summary.aggregate_passed else "no",
            )
        console.print(table)
        console.print(
            f"Result: [bold]{'PASS' if not failed_policy else 'FAIL'}[/bold] "
            f"(unstable={len(unstable)} deterministic_failures={len(failed)})"
        )
        if json_output is not None:
            json_output.parent.mkdir(parents=True, exist_ok=True)
            json_output.write_text(render_stability_json(stability), encoding="utf-8")
        if markdown_output is not None:
            markdown_output.parent.mkdir(parents=True, exist_ok=True)
            markdown_output.write_text(render_stability_markdown(stability), encoding="utf-8")
        if failed_policy:
            raise typer.Exit(code=1)
        return

    model_report = evaluate_probes_with_model(
        snap,
        probes,
        runner,
        config=cfg,
        require_approval=require_approval,
    )
    table = Table(title=f"Model-backed probes: {snap.server_name}")
    table.add_column("Probe")
    table.add_column("Passed")
    table.add_column("Outcome")
    table.add_column("Selected")
    table.add_column("Message")
    for item in model_report.results:
        if item.passed:
            color = "green"
        elif item.outcome.value == "skipped":
            color = "yellow"
        else:
            color = "red"
        table.add_row(
            item.probe_id,
            f"[{color}]{'yes' if item.passed else 'no'}[/]",
            item.outcome.value,
            item.selected_tool or "",
            item.message,
        )
    console.print(table)
    console.print(f"Result: [bold]{'PASS' if model_report.passed else 'FAIL'}[/bold]")
    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "mode": "model",
            "passed": model_report.passed,
            "opt_in": model_report.opt_in,
            "results": [item.model_dump(mode="json") for item in model_report.results],
        }
        json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if markdown_output is not None:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(
            render_model_probe_report_markdown(model_report),
            encoding="utf-8",
        )
    if not model_report.passed:
        raise typer.Exit(code=1)


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


@app.command("corpus")
def corpus_cmd(
    root: Annotated[
        Path,
        typer.Option("--root", help="Corpus root directory (default: benchmarks/)."),
    ] = Path("benchmarks"),
    json_output: Annotated[
        Path | None,
        typer.Option("--json-output", help="Write JSON corpus report."),
    ] = None,
    markdown_output: Annotated[
        Path | None,
        typer.Option("--markdown-output", help="Write Markdown corpus report."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Log corpus steps to stderr."),
    ] = False,
) -> None:
    """Run the offline multi-domain benchmark corpus (#92)."""
    from tool_semantics.corpus import render_corpus_markdown, run_corpus

    if not root.is_dir():
        console.print(f"[red]Corpus root not found:[/red] {root}")
        raise typer.Exit(code=2)

    _log_verbose(verbose, f"corpus root={root.resolve()}")
    report = run_corpus(root)
    console.print(render_corpus_markdown(report))
    if not report.passed:
        for item in report.results:
            if not item.passed:
                for failure in item.failures:
                    console.print(f"[red]{item.domain}:[/red] {failure}")

    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
    if markdown_output is not None:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(render_corpus_markdown(report), encoding="utf-8")

    if not report.passed:
        raise typer.Exit(code=1)
