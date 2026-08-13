from pathlib import Path


def test_compare_action_can_upload_candidate_and_reports() -> None:
    action = Path(".github/actions/compare/action.yml").read_text(encoding="utf-8")

    assert "upload-artifacts:" in action
    assert 'default: "false"' in action
    assert "name: Upload report artifact" in action
    assert "if: ${{ always() && inputs.upload-artifacts == 'true' }}" in action
    assert "${{ steps.artifact-paths.outputs.candidate-path }}" in action
    assert "${{ steps.compare.outputs.report-path }}" in action


def test_compare_action_resolves_artifact_candidate_from_working_directory() -> None:
    action = Path(".github/actions/compare/action.yml").read_text(encoding="utf-8")

    assert "name: Resolve artifact paths" in action
    assert "id: artifact-paths" in action
    assert "working-directory: ${{ inputs.working-directory }}" in action
    assert 'Path(os.environ["CANDIDATE"]).resolve()' in action
