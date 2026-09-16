"""Environment and project sanity checks (`tool-semantics doctor`, #96)."""

from __future__ import annotations

import os
import sys
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from tool_semantics import __version__
from tool_semantics.config import DEFAULT_CONFIG_NAME, load_config
from tool_semantics.probes import load_probes
from tool_semantics.project import discover_default_probes, project_paths
from tool_semantics.scanner import ManifestError, read_snapshot


class CheckStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


class DoctorCheck(BaseModel):
    name: str
    status: CheckStatus
    message: str


class DoctorReport(BaseModel):
    checks: list[DoctorCheck] = Field(default_factory=list)
    tool_semantics_version: str = __version__

    @property
    def ok(self) -> bool:
        return not any(check.status == CheckStatus.ERROR for check in self.checks)

    @property
    def warnings(self) -> list[DoctorCheck]:
        return [check for check in self.checks if check.status == CheckStatus.WARNING]

    @property
    def errors(self) -> list[DoctorCheck]:
        return [check for check in self.checks if check.status == CheckStatus.ERROR]


def _check_python() -> DoctorCheck:
    major, minor = sys.version_info[:2]
    version = f"{major}.{minor}"
    if (major, minor) < (3, 11):
        return DoctorCheck(
            name="python",
            status=CheckStatus.ERROR,
            message=f"Python {version} is unsupported; require 3.11+.",
        )
    return DoctorCheck(
        name="python",
        status=CheckStatus.OK,
        message=f"Python {sys.version.split()[0]}",
    )


def _check_install() -> DoctorCheck:
    return DoctorCheck(
        name="install",
        status=CheckStatus.OK,
        message=f"tool-semantics {__version__} importable",
    )


def _check_config(root: Path) -> DoctorCheck:
    paths = project_paths(root)
    if not paths.config.is_file():
        return DoctorCheck(
            name="config",
            status=CheckStatus.WARNING,
            message=(
                f"No {DEFAULT_CONFIG_NAME} in project root "
                "(run `tool-semantics init` or continue with defaults)."
            ),
        )
    try:
        config = load_config(paths.config)
    except (OSError, ValueError) as exc:
        return DoctorCheck(
            name="config",
            status=CheckStatus.ERROR,
            message=f"Failed to parse {paths.config}: {exc}",
        )
    return DoctorCheck(
        name="config",
        status=CheckStatus.OK,
        message=(f"Loaded {paths.config.name} (policy={config.policy.fail_at_or_above.value})"),
    )


def _check_layout(root: Path) -> DoctorCheck:
    paths = project_paths(root)
    if not paths.layout.is_dir():
        return DoctorCheck(
            name="layout",
            status=CheckStatus.WARNING,
            message="No .tool-semantics/ directory (run `tool-semantics init`).",
        )
    missing = [
        name
        for name, path in (
            ("baselines", paths.baselines),
            ("probes", paths.probes),
            ("traces", paths.traces),
        )
        if not path.is_dir()
    ]
    if missing:
        return DoctorCheck(
            name="layout",
            status=CheckStatus.WARNING,
            message=f".tool-semantics/ missing subdirs: {', '.join(missing)}",
        )
    return DoctorCheck(
        name="layout",
        status=CheckStatus.OK,
        message=f"Layout present at {paths.layout}",
    )


def _check_baselines(root: Path) -> DoctorCheck:
    paths = project_paths(root)
    if not paths.baselines.is_dir():
        return DoctorCheck(
            name="baselines",
            status=CheckStatus.WARNING,
            message="No baselines/ directory yet.",
        )
    snapshots = sorted(paths.baselines.glob("*.json"))
    if not snapshots:
        return DoctorCheck(
            name="baselines",
            status=CheckStatus.WARNING,
            message="baselines/ is empty — capture a reviewed baseline when ready.",
        )
    errors: list[str] = []
    for path in snapshots:
        try:
            read_snapshot(path)
        except ManifestError as exc:
            errors.append(f"{path.name}: {exc}")
    if errors:
        return DoctorCheck(
            name="baselines",
            status=CheckStatus.ERROR,
            message="Invalid baseline snapshot(s): " + "; ".join(errors),
        )
    return DoctorCheck(
        name="baselines",
        status=CheckStatus.OK,
        message=f"{len(snapshots)} baseline snapshot(s) valid",
    )


def _check_probes(root: Path) -> DoctorCheck:
    discovered = discover_default_probes(root)
    paths = project_paths(root)
    if discovered is None:
        if paths.probes.is_dir():
            return DoctorCheck(
                name="probes",
                status=CheckStatus.WARNING,
                message="probes/ exists but no JSON/YAML probe suite found.",
            )
        return DoctorCheck(
            name="probes",
            status=CheckStatus.WARNING,
            message="No probe suite discovered under .tool-semantics/probes/.",
        )
    try:
        probes = load_probes(discovered)
    except (OSError, ValueError) as exc:
        return DoctorCheck(
            name="probes",
            status=CheckStatus.ERROR,
            message=f"Failed to load {discovered}: {exc}",
        )
    return DoctorCheck(
        name="probes",
        status=CheckStatus.OK,
        message=f"Loaded {len(probes)} probe(s) from {discovered.name}",
    )


def _check_model_env() -> DoctorCheck:
    key = os.environ.get("TOOL_SEMANTICS_API_KEY") or os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("TOOL_SEMANTICS_MODEL") or os.environ.get("OPENAI_MODEL")
    if not key:
        return DoctorCheck(
            name="model",
            status=CheckStatus.WARNING,
            message=(
                "No TOOL_SEMANTICS_API_KEY / OPENAI_API_KEY — "
                "offline probes still work; --model will fail."
            ),
        )
    detail = "API key present"
    if model:
        detail += f", model={model}"
    return DoctorCheck(name="model", status=CheckStatus.OK, message=detail)


def _check_mcp_endpoint(endpoint: str | None) -> DoctorCheck | None:
    if not endpoint:
        return None
    # Lightweight reachability: HTTP(S) HEAD/GET without full MCP handshake.
    import urllib.error
    import urllib.request

    try:
        request = urllib.request.Request(endpoint, method="GET")
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            status = getattr(response, "status", 200)
        return DoctorCheck(
            name="mcp",
            status=CheckStatus.OK,
            message=f"Endpoint reachable ({endpoint}, HTTP {status})",
        )
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return DoctorCheck(
            name="mcp",
            status=CheckStatus.WARNING,
            message=f"MCP endpoint check failed for {endpoint}: {exc}",
        )


def run_doctor(
    root: Path | None = None,
    *,
    mcp_endpoint: str | None = None,
) -> DoctorReport:
    """Collect doctor checks for the given project root."""
    base = (root or Path.cwd()).resolve()
    report = DoctorReport()
    report.checks.append(_check_python())
    report.checks.append(_check_install())
    report.checks.append(_check_config(base))
    report.checks.append(_check_layout(base))
    report.checks.append(_check_baselines(base))
    report.checks.append(_check_probes(base))
    report.checks.append(_check_model_env())
    mcp_check = _check_mcp_endpoint(mcp_endpoint)
    if mcp_check is not None:
        report.checks.append(mcp_check)
    return report
