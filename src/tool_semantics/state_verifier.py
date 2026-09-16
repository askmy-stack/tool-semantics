"""Final-state verification independent of tool trajectory (#105)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StateCheck(BaseModel):
    """One expected_state key compared against observed state."""

    key: str
    expected: Any = None
    actual: Any = None
    matched: bool
    message: str


class FinalStateResult(BaseModel):
    """Outcome of comparing expected vs observed task state."""

    passed: bool
    partial: bool = False
    matched_count: int = 0
    total_count: int = 0
    checks: list[StateCheck] = Field(default_factory=list)
    missing_observed: bool = False
    message: str = ""

    @property
    def failures(self) -> list[StateCheck]:
        return [check for check in self.checks if not check.matched]


def verify_final_state(
    expected_state: dict[str, Any],
    observed_state: dict[str, Any] | None,
    *,
    require_observed: bool = True,
) -> FinalStateResult:
    """Compare deterministic key/value expectations to an observed state.

    Different tool trajectories that reach the same ``observed_state`` pass the
    same checks — trajectory shape is intentionally out of scope here.
    """
    if not expected_state:
        return FinalStateResult(
            passed=True,
            partial=False,
            matched_count=0,
            total_count=0,
            message="No expected_state configured.",
        )

    if observed_state is None:
        if not require_observed:
            return FinalStateResult(
                passed=True,
                total_count=len(expected_state),
                missing_observed=True,
                message="expected_state present but observed state not supplied (skipped).",
            )
        checks = [
            StateCheck(
                key=key,
                expected=expected,
                actual=None,
                matched=False,
                message=f"State key '{key}' not verified: observed state missing.",
            )
            for key, expected in expected_state.items()
        ]
        return FinalStateResult(
            passed=False,
            partial=False,
            matched_count=0,
            total_count=len(checks),
            checks=checks,
            missing_observed=True,
            message="Observed state was not provided for final-state verification.",
        )

    checks_out: list[StateCheck] = []
    for key, expected in expected_state.items():
        if key not in observed_state:
            checks_out.append(
                StateCheck(
                    key=key,
                    expected=expected,
                    actual=None,
                    matched=False,
                    message=f"Expected state key '{key}' is missing from observed state.",
                )
            )
            continue
        actual = observed_state[key]
        matched = actual == expected
        checks_out.append(
            StateCheck(
                key=key,
                expected=expected,
                actual=actual,
                matched=matched,
                message=(
                    f"State '{key}' matched."
                    if matched
                    else f"State '{key}' expected {expected!r} but observed {actual!r}."
                ),
            )
        )

    matched_count = sum(1 for check in checks_out if check.matched)
    total = len(checks_out)
    passed = matched_count == total
    partial = 0 < matched_count < total
    if passed:
        message = f"All {total} expected state condition(s) held."
    elif partial:
        failed = [check.key for check in checks_out if not check.matched]
        message = (
            f"Partial final state: {matched_count}/{total} keys matched; "
            f"failed: {', '.join(failed)}."
        )
    else:
        failed = [check.key for check in checks_out if not check.matched]
        message = f"Final state failed for: {', '.join(failed)}."

    return FinalStateResult(
        passed=passed,
        partial=partial,
        matched_count=matched_count,
        total_count=total,
        checks=checks_out,
        message=message,
    )


def render_final_state_markdown(result: FinalStateResult, *, probe_id: str | None = None) -> str:
    title = f"Final state (`{probe_id}`)" if probe_id else "Final state"
    status = "PASS" if result.passed else ("PARTIAL" if result.partial else "FAIL")
    lines = [
        f"### {title}",
        "",
        f"**Result:** `{status}` — {result.message}",
        "",
    ]
    if not result.checks:
        return "\n".join(lines)
    lines.extend(
        [
            "| Key | Matched | Expected | Observed | Message |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for check in result.checks:
        expected = repr(check.expected).replace("|", "\\|")
        actual = "n/a" if check.actual is None and not check.matched else repr(check.actual)
        actual = actual.replace("|", "\\|")
        message = check.message.replace("|", "\\|")
        lines.append(
            f"| `{check.key}` | {'yes' if check.matched else 'no'} | "
            f"{expected} | {actual} | {message} |"
        )
    lines.append("")
    return "\n".join(lines)
