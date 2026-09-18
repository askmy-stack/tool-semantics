from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from tool_semantics.models import InterfaceSnapshot, RiskLevel, ToolContract
from tool_semantics.runner import ModelRunner, RunnerConfig, RunnerMetadata


class ProbeKind(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    AMBIGUOUS = "ambiguous"


class Probe(BaseModel):
    """Behavioral probe — offline by default; model-backed when a runner is supplied."""

    id: str
    intent: str
    kind: ProbeKind = ProbeKind.POSITIVE
    expected_tool: str | None = None
    forbidden_tools: list[str] = Field(default_factory=list)
    required_params: list[str] = Field(default_factory=list)
    # Side-effect / confirmation expectations (Milestone 3).
    max_risk: str | None = None  # read_only | external_write | destructive | unknown
    requires_confirmation: bool = False
    # Human-reviewed approval gate for model-backed execution (#44).
    approved: bool = False
    approved_by: str | None = None
    # Optional expected argument keys/values for model-backed validity checks.
    expected_arguments: dict[str, Any] = Field(default_factory=dict)


class ProbeResult(BaseModel):
    probe_id: str
    passed: bool
    message: str


class ProbeReport(BaseModel):
    results: list[ProbeResult] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def failures(self) -> list[ProbeResult]:
        return [result for result in self.results if not result.passed]


class ModelProbeOutcome(StrEnum):
    OK = "ok"
    ERROR = "error"
    MISSING_DATA = "missing_data"
    FAILED_EVALUATION = "failed_evaluation"
    SKIPPED = "skipped"


class ModelProbeResult(BaseModel):
    probe_id: str
    passed: bool
    message: str
    selected_tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    outcome: ModelProbeOutcome = ModelProbeOutcome.OK
    error: str | None = None
    tool_selection_correct: bool | None = None
    arguments_valid: bool | None = None
    risk_compliant: bool | None = None
    confirmation_compliant: bool | None = None
    runner: RunnerMetadata | None = None
    trial_index: int | None = None


class ModelProbeReport(BaseModel):
    results: list[ModelProbeResult] = Field(default_factory=list)
    opt_in: bool = True

    @property
    def passed(self) -> bool:
        return all(
            result.passed for result in self.results if result.outcome != ModelProbeOutcome.SKIPPED
        )


class ProbeMetrics(BaseModel):
    """Aggregate metrics for model-backed behavioral runs (#46)."""

    probe_count: int = 0
    evaluated_count: int = 0
    missing_data_count: int = 0
    failed_evaluation_count: int = 0
    tool_selection_accuracy: float | None = None
    argument_validity_rate: float | None = None
    risk_compliance_rate: float | None = None
    confirmation_compliance_rate: float | None = None
    per_probe: dict[str, dict[str, Any]] = Field(default_factory=dict)


class TrialDetail(BaseModel):
    trial_index: int
    selected_tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    passed: bool
    outcome: ModelProbeOutcome
    message: str
    error: str | None = None


class StabilityProbeSummary(BaseModel):
    probe_id: str
    trials: list[TrialDetail] = Field(default_factory=list)
    stability_score: float
    unstable: bool
    deterministic_failure: bool
    aggregate_passed: bool
    message: str
    # First-class reliability (#106): pass@k (≥1 success) and pass^k (all succeed).
    k: int = 0
    pass_at_k: bool = False
    pass_hat_k: bool = False
    pass_rate: float | None = None
    pass_variance: float | None = None


class ReliabilityMetrics(BaseModel):
    """Aggregate pass@k / pass^k across probes (#106)."""

    k: int = 0
    probe_count: int = 0
    pass_at_k_rate: float | None = None
    pass_hat_k_rate: float | None = None
    mean_pass_rate: float | None = None
    mean_stability_score: float | None = None
    unstable_count: int = 0
    deterministic_failure_count: int = 0


class StabilityReport(BaseModel):
    trial_count: int
    seed: int | None = None
    summaries: list[StabilityProbeSummary] = Field(default_factory=list)
    metrics: ProbeMetrics = Field(default_factory=ProbeMetrics)
    reliability: ReliabilityMetrics = Field(default_factory=ReliabilityMetrics)
    runner: RunnerMetadata | None = None


def evaluate_probes(snapshot: InterfaceSnapshot, probes: list[Probe]) -> ProbeReport:
    """Evaluate probes against a snapshot without calling an LLM.

    Positive probes require the expected tool (and optional required params) to exist.
    Negative probes fail if a forbidden tool is present.
    Ambiguous probes pass when the expected tool exists but record a soft warning message
    if additional candidate tools share overlapping description tokens.
    """
    tools = {tool.name: tool for tool in snapshot.tools}
    report = ProbeReport()
    for probe in probes:
        if probe.kind == ProbeKind.NEGATIVE:
            present = [name for name in probe.forbidden_tools if name in tools]
            if present:
                report.results.append(
                    ProbeResult(
                        probe_id=probe.id,
                        passed=False,
                        message=f"Forbidden tools still present: {', '.join(present)}",
                    )
                )
            else:
                report.results.append(
                    ProbeResult(
                        probe_id=probe.id,
                        passed=True,
                        message="Forbidden tools absent.",
                    )
                )
            continue

        if probe.expected_tool is None:
            report.results.append(
                ProbeResult(
                    probe_id=probe.id,
                    passed=False,
                    message="Probe is missing expected_tool.",
                )
            )
            continue
        tool = tools.get(probe.expected_tool)
        if tool is None:
            report.results.append(
                ProbeResult(
                    probe_id=probe.id,
                    passed=False,
                    message=f"Expected tool '{probe.expected_tool}' not found.",
                )
            )
            continue
        missing = [
            name
            for name in probe.required_params
            if name not in {parameter.name for parameter in tool.parameters}
        ]
        if missing:
            report.results.append(
                ProbeResult(
                    probe_id=probe.id,
                    passed=False,
                    message=f"Missing required params on '{tool.name}': {', '.join(missing)}",
                )
            )
            continue
        if probe.max_risk is not None:
            try:
                allowed = RiskLevel(probe.max_risk)
            except ValueError:
                report.results.append(
                    ProbeResult(
                        probe_id=probe.id,
                        passed=False,
                        message=f"Invalid max_risk '{probe.max_risk}'.",
                    )
                )
                continue
            rank = {
                RiskLevel.READ_ONLY: 0,
                RiskLevel.UNKNOWN: 1,
                RiskLevel.EXTERNAL_WRITE: 2,
                RiskLevel.DESTRUCTIVE: 3,
            }
            if rank[tool.risk] > rank[allowed]:
                report.results.append(
                    ProbeResult(
                        probe_id=probe.id,
                        passed=False,
                        message=(
                            f"Tool '{tool.name}' risk '{tool.risk}' exceeds "
                            f"max_risk '{probe.max_risk}'."
                        ),
                    )
                )
                continue
        if probe.requires_confirmation and tool.risk in {
            RiskLevel.EXTERNAL_WRITE,
            RiskLevel.DESTRUCTIVE,
        }:
            # Offline harness can only assert that confirmation is *required by policy*;
            # it cannot observe a runtime confirmation UI.
            message_prefix = (
                f"Expected tool '{tool.name}' present; confirmation required for "
                f"risk '{tool.risk}'."
            )
        else:
            message_prefix = f"Expected tool '{tool.name}' present."
        message = message_prefix
        if probe.kind == ProbeKind.AMBIGUOUS:
            intent_tokens = {token.lower() for token in probe.intent.split() if len(token) > 3}
            collisions = []
            for other in snapshot.tools:
                if other.name == tool.name:
                    continue
                desc_tokens = {
                    token.lower() for token in other.description.split() if len(token) > 3
                }
                if intent_tokens & desc_tokens:
                    collisions.append(other.name)
            if collisions:
                message += f" Potential selection collisions: {', '.join(collisions)}."
        report.results.append(ProbeResult(probe_id=probe.id, passed=True, message=message))
    return report


def _tools_as_openai_schemas(snapshot: InterfaceSnapshot) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for tool in snapshot.tools:
        properties = {parameter.name: parameter.schema_ for parameter in tool.parameters}
        required = [parameter.name for parameter in tool.parameters if parameter.required]
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
        )
    return tools


def _validate_arguments(tool: ToolContract | None, arguments: dict[str, Any], probe: Probe) -> bool:
    if tool is None:
        return False
    param_names = {parameter.name for parameter in tool.parameters}
    required = {parameter.name for parameter in tool.parameters if parameter.required}
    if any(name not in param_names for name in arguments):
        return False
    if not required.issubset(arguments):
        return False
    for name in probe.required_params:
        if name not in arguments:
            return False
    for key, expected in probe.expected_arguments.items():
        if arguments.get(key) != expected:
            return False
    return True


def _risk_compliant(tool: ToolContract | None, probe: Probe) -> bool | None:
    if probe.max_risk is None:
        return None
    if tool is None:
        return False
    try:
        allowed = RiskLevel(probe.max_risk)
    except ValueError:
        return False
    rank = {
        RiskLevel.READ_ONLY: 0,
        RiskLevel.UNKNOWN: 1,
        RiskLevel.EXTERNAL_WRITE: 2,
        RiskLevel.DESTRUCTIVE: 3,
    }
    return rank[tool.risk] <= rank[allowed]


def _confirmation_compliant(tool: ToolContract | None, probe: Probe) -> bool | None:
    if not probe.requires_confirmation:
        return None
    if tool is None:
        return False
    # Model-backed path treats selecting a high-risk tool while requires_confirmation
    # is set as compliant only when the probe explicitly opts into that risk.
    return tool.risk in {RiskLevel.EXTERNAL_WRITE, RiskLevel.DESTRUCTIVE, RiskLevel.UNKNOWN}


def evaluate_probes_with_model(
    snapshot: InterfaceSnapshot,
    probes: list[Probe],
    runner: ModelRunner,
    *,
    config: RunnerConfig | None = None,
    require_approval: bool = True,
    trial_index: int | None = None,
) -> ModelProbeReport:
    """Opt-in model-backed probe execution (#44). Offline evaluate_probes remains default."""
    cfg = config or RunnerConfig()
    tools_by_name = {tool.name: tool for tool in snapshot.tools}
    tool_schemas = _tools_as_openai_schemas(snapshot)
    report = ModelProbeReport(opt_in=True)
    system = (
        "You are evaluating which tool to call for a user intent. "
        "Respond only by calling exactly one tool when appropriate. "
        "Never echo secrets from tool metadata."
    )
    for probe in probes:
        if require_approval and not probe.approved:
            report.results.append(
                ModelProbeResult(
                    probe_id=probe.id,
                    passed=False,
                    message=(
                        "Probe is not human-reviewed/approved for model-backed execution. "
                        "Set approved=true after review (see docs/probes.md)."
                    ),
                    outcome=ModelProbeOutcome.SKIPPED,
                    trial_index=trial_index,
                )
            )
            continue
        try:
            completion = runner.complete(
                system=system,
                user=probe.intent,
                tools=tool_schemas,
                config=cfg,
            )
        except Exception as exc:  # noqa: BLE001 — surface as failed_evaluation
            report.results.append(
                ModelProbeResult(
                    probe_id=probe.id,
                    passed=False,
                    message=f"Model runner failed: {exc}",
                    outcome=ModelProbeOutcome.FAILED_EVALUATION,
                    error=str(exc),
                    runner=getattr(runner, "metadata", None),
                    trial_index=trial_index,
                )
            )
            continue

        if not completion.tool_calls:
            report.results.append(
                ModelProbeResult(
                    probe_id=probe.id,
                    passed=probe.kind == ProbeKind.NEGATIVE,
                    message="Model returned no tool call.",
                    outcome=ModelProbeOutcome.MISSING_DATA,
                    tool_selection_correct=probe.kind == ProbeKind.NEGATIVE,
                    arguments_valid=None,
                    runner=completion.metadata,
                    trial_index=trial_index,
                )
            )
            continue

        call = completion.tool_calls[0]
        selected = call.name
        arguments = dict(call.arguments)
        tool = tools_by_name.get(selected)

        if probe.kind == ProbeKind.NEGATIVE:
            forbidden_hit = selected in probe.forbidden_tools
            report.results.append(
                ModelProbeResult(
                    probe_id=probe.id,
                    passed=not forbidden_hit,
                    message=(
                        f"Model selected forbidden tool '{selected}'."
                        if forbidden_hit
                        else f"Model avoided forbidden tools (selected '{selected}')."
                    ),
                    selected_tool=selected,
                    arguments=arguments,
                    outcome=ModelProbeOutcome.OK,
                    tool_selection_correct=not forbidden_hit,
                    arguments_valid=_validate_arguments(tool, arguments, probe) if tool else False,
                    risk_compliant=_risk_compliant(tool, probe),
                    confirmation_compliant=_confirmation_compliant(tool, probe),
                    runner=completion.metadata,
                    trial_index=trial_index,
                )
            )
            continue

        selection_ok = probe.expected_tool is None or selected == probe.expected_tool
        args_ok = _validate_arguments(tool, arguments, probe)
        risk_ok = _risk_compliant(tool, probe)
        confirm_ok = _confirmation_compliant(tool, probe)
        checks = [selection_ok, args_ok]
        if risk_ok is not None:
            checks.append(risk_ok)
        if confirm_ok is not None:
            checks.append(confirm_ok)
        passed = all(checks)
        report.results.append(
            ModelProbeResult(
                probe_id=probe.id,
                passed=passed,
                message=(
                    f"Selected '{selected}' with args {arguments}."
                    if passed
                    else f"Selection/args mismatch: selected '{selected}', "
                    f"expected '{probe.expected_tool}', args={arguments}."
                ),
                selected_tool=selected,
                arguments=arguments,
                outcome=ModelProbeOutcome.OK,
                tool_selection_correct=selection_ok,
                arguments_valid=args_ok,
                risk_compliant=risk_ok,
                confirmation_compliant=confirm_ok,
                runner=completion.metadata,
                trial_index=trial_index,
            )
        )
    return report


def compute_probe_metrics(results: list[ModelProbeResult]) -> ProbeMetrics:
    """Derive selection / validity / compliance rates (#46)."""
    metrics = ProbeMetrics(probe_count=len(results))
    _unevaluated = {
        ModelProbeOutcome.SKIPPED,
        ModelProbeOutcome.MISSING_DATA,
        ModelProbeOutcome.FAILED_EVALUATION,
    }
    evaluated = [item for item in results if item.outcome not in _unevaluated]
    missing = [item for item in results if item.outcome == ModelProbeOutcome.MISSING_DATA]
    failed = [item for item in results if item.outcome == ModelProbeOutcome.FAILED_EVALUATION]
    metrics.evaluated_count = len(evaluated)
    metrics.missing_data_count = len(missing)
    metrics.failed_evaluation_count = len(failed)

    def _rate(values: list[bool | None]) -> float | None:
        known = [value for value in values if value is not None]
        if not known:
            return None
        return sum(1 for value in known if value) / len(known)

    metrics.tool_selection_accuracy = _rate([item.tool_selection_correct for item in evaluated])
    metrics.argument_validity_rate = _rate([item.arguments_valid for item in evaluated])
    metrics.risk_compliance_rate = _rate([item.risk_compliant for item in evaluated])
    metrics.confirmation_compliance_rate = _rate(
        [item.confirmation_compliant for item in evaluated]
    )

    per_probe: dict[str, list[ModelProbeResult]] = {}
    for item in results:
        per_probe.setdefault(item.probe_id, []).append(item)
    for probe_id, group in per_probe.items():
        group_evaluated = [item for item in group if item.outcome not in _unevaluated]
        metrics.per_probe[probe_id] = {
            "evaluated": len(group_evaluated),
            "missing_data": sum(
                1 for item in group if item.outcome == ModelProbeOutcome.MISSING_DATA
            ),
            "failed_evaluation": sum(
                1 for item in group if item.outcome == ModelProbeOutcome.FAILED_EVALUATION
            ),
            "tool_selection_accuracy": _rate(
                [item.tool_selection_correct for item in group_evaluated]
            ),
            "argument_validity_rate": _rate([item.arguments_valid for item in group_evaluated]),
            "passed": all(item.passed for item in group_evaluated) if group_evaluated else False,
        }
    return metrics


def run_probe_trials(
    snapshot: InterfaceSnapshot,
    probes: list[Probe],
    runner: ModelRunner,
    *,
    trial_count: int = 3,
    config: RunnerConfig | None = None,
    require_approval: bool = True,
    seed: int | None = None,
) -> StabilityReport:
    """Repeat model-backed probes and summarize stability (#47)."""
    if trial_count < 1:
        raise ValueError("trial_count must be >= 1")
    base = config or RunnerConfig()
    if seed is not None:
        base = base.model_copy(update={"seed": seed})

    all_results: list[ModelProbeResult] = []
    by_probe: dict[str, list[ModelProbeResult]] = {probe.id: [] for probe in probes}
    for index in range(trial_count):
        trial_config = base
        if base.seed is not None:
            trial_config = base.model_copy(update={"seed": base.seed + index})
        trial_report = evaluate_probes_with_model(
            snapshot,
            probes,
            runner,
            config=trial_config,
            require_approval=require_approval,
            trial_index=index,
        )
        for result in trial_report.results:
            all_results.append(result)
            by_probe.setdefault(result.probe_id, []).append(result)

    summaries: list[StabilityProbeSummary] = []
    for probe_id, group in by_probe.items():
        if not group:
            continue
        # Reliability metrics ignore skipped trials (unapproved probes).
        evaluated = [item for item in group if item.outcome != ModelProbeOutcome.SKIPPED]
        scored = evaluated if evaluated else group
        selections = tuple((item.selected_tool, json_freeze(item.arguments)) for item in scored)
        unique = len(set(selections))
        # Consistency-only score: 1.0 = identical selection+args every trial.
        stability = 1.0 if len(scored) <= 1 else max(0.0, 1.0 - ((unique - 1) / (len(scored) - 1)))
        # Blend in selection/arg agreement rates when present (still 1.0 when all agree,
        # including agreeing on the wrong tool).
        selection_flags = [
            item.tool_selection_correct
            for item in scored
            if item.tool_selection_correct is not None
        ]
        arg_flags = [item.arguments_valid for item in scored if item.arguments_valid is not None]
        agreement_parts = [stability]
        if selection_flags:
            # Agreement among trials, not correctness vs expected.
            agreement_parts.append(
                1.0
                if len(set(selection_flags)) == 1
                else sum(1 for flag in selection_flags if flag == selection_flags[0])
                / len(selection_flags)
            )
        if arg_flags:
            agreement_parts.append(
                1.0
                if len(set(arg_flags)) == 1
                else sum(1 for flag in arg_flags if flag == arg_flags[0]) / len(arg_flags)
            )
        stability = sum(agreement_parts) / len(agreement_parts)

        all_failed_same = (
            len(scored) > 0
            and all(not item.passed for item in scored)
            and unique == 1
            and all(item.outcome == scored[0].outcome for item in scored)
        )
        unstable = unique > 1
        deterministic_failure = all_failed_same and not unstable
        k = len(scored)
        passes = [item.passed for item in scored]
        pass_count = sum(1 for flag in passes if flag)
        pass_rate = (pass_count / k) if k else None
        # Bernoulli variance of the empirical pass rate across trials.
        pass_variance = (pass_rate * (1.0 - pass_rate)) if pass_rate is not None else None
        pass_at_k = pass_count >= 1
        pass_hat_k = k > 0 and pass_count == k
        summaries.append(
            StabilityProbeSummary(
                probe_id=probe_id,
                trials=[
                    TrialDetail(
                        trial_index=item.trial_index if item.trial_index is not None else idx,
                        selected_tool=item.selected_tool,
                        arguments=item.arguments,
                        passed=item.passed,
                        outcome=item.outcome,
                        message=item.message,
                        error=item.error,
                    )
                    for idx, item in enumerate(group)
                ],
                stability_score=round(stability, 4),
                unstable=unstable,
                deterministic_failure=deterministic_failure,
                aggregate_passed=pass_hat_k,
                message=(
                    "Deterministic failure across trials."
                    if deterministic_failure
                    else ("Unstable across trials." if unstable else "Stable across trials.")
                ),
                k=k,
                pass_at_k=pass_at_k,
                pass_hat_k=pass_hat_k,
                pass_rate=round(pass_rate, 4) if pass_rate is not None else None,
                pass_variance=round(pass_variance, 4) if pass_variance is not None else None,
            )
        )

    runner_meta = getattr(runner, "metadata", None)
    return StabilityReport(
        trial_count=trial_count,
        seed=base.seed,
        summaries=summaries,
        metrics=compute_probe_metrics(all_results),
        reliability=compute_reliability_metrics(summaries, k=trial_count),
        runner=runner_meta,
    )


def compute_reliability_metrics(
    summaries: list[StabilityProbeSummary], *, k: int
) -> ReliabilityMetrics:
    """Aggregate pass@k / pass^k rates across probe summaries (#106)."""
    if not summaries:
        return ReliabilityMetrics(k=k)
    pass_at = [item.pass_at_k for item in summaries]
    pass_hat = [item.pass_hat_k for item in summaries]
    rates = [item.pass_rate for item in summaries if item.pass_rate is not None]
    scores = [item.stability_score for item in summaries]
    return ReliabilityMetrics(
        k=k,
        probe_count=len(summaries),
        pass_at_k_rate=sum(1 for flag in pass_at if flag) / len(pass_at),
        pass_hat_k_rate=sum(1 for flag in pass_hat if flag) / len(pass_hat),
        mean_pass_rate=(sum(rates) / len(rates)) if rates else None,
        mean_stability_score=(sum(scores) / len(scores)) if scores else None,
        unstable_count=sum(1 for item in summaries if item.unstable),
        deterministic_failure_count=sum(1 for item in summaries if item.deterministic_failure),
    )


def load_probes(path: Path) -> list[Probe]:
    """Load probes from a JSON or YAML file.

    Accepted shapes:
    - a list of probe objects
    - an object with a ``probes`` list
    """
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    raw: Any
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover — declared dependency
            raise ValueError(
                "YAML probe files require PyYAML. Install tool-semantics with its "
                "declared dependencies, or use a .json probe file."
            ) from exc
        raw = yaml.safe_load(text)
    elif suffix == ".json":
        import json

        raw = json.loads(text)
    else:
        # Try JSON first, then YAML for extensionless / .probes files.
        import json

        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            try:
                import yaml
            except ImportError as exc:  # pragma: no cover
                raise ValueError(f"Unsupported probe file {path}: use .json or .yaml/.yml") from exc
            raw = yaml.safe_load(text)

    if isinstance(raw, dict):
        items = raw.get("probes")
        if not isinstance(items, list):
            raise ValueError(f"Probe file {path} must be a list or an object with a 'probes' array")
    elif isinstance(raw, list):
        items = raw
    else:
        raise ValueError(f"Probe file {path} must be a list or object, got {type(raw).__name__}")

    if not items:
        raise ValueError(f"Probe file {path} contains no probes")

    probes: list[Probe] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Probe entry {index} in {path} must be an object")
        try:
            probes.append(Probe.model_validate(item))
        except Exception as exc:  # noqa: BLE001 — pydantic ValidationError + clarity
            raise ValueError(f"Invalid probe entry {index} in {path}: {exc}") from exc
    return probes


def json_freeze(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"))
