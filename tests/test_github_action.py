from pathlib import Path


def test_compare_action_can_upload_candidate_and_reports() -> None:
    action = Path(".github/actions/compare/action.yml").read_text(encoding="utf-8")

    assert "upload-artifacts:" in action
    assert 'default: "false"' in action
    assert "name: Upload report artifact" in action
    assert "inputs.upload-artifacts == 'true'" in action
    assert "${{ inputs.candidate }}" in action
    assert "${{ steps.compare.outputs.report-path }}" in action
