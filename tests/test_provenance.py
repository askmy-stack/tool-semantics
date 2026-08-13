import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from tool_semantics.provenance import write_provenance


def test_write_provenance_hashes_snapshot_and_redacts_source(tmp_path: Path) -> None:
    """Catch a sidecar that leaks source secrets or hashes transformed bytes."""
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text('{"server_name":"demo"}\n', encoding="utf-8")
    output = tmp_path / "provenance.json"

    write_provenance(
        snapshot,
        output,
        {
            "kind": "mcp-stdio",
            "authorization": "Bearer secret",
            "command": ["server", "--token=secret", "--api-key", "another-secret"],
        },
        captured_at=datetime(2026, 8, 13, tzinfo=UTC),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["provenance_version"] == "0.1"
    assert payload["snapshot_sha256"] == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert payload["source"]["authorization"] == "***REDACTED***"
    assert payload["source"]["command"][1] == "***REDACTED***"
    assert payload["source"]["command"][3] == "***REDACTED***"
    assert payload["captured_at"] == "2026-08-13T00:00:00+00:00"


def test_write_provenance_never_serializes_environment_values(tmp_path: Path) -> None:
    """Catch a provenance sidecar that preserves environment variable values."""
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "nested" / "provenance.json"

    write_provenance(snapshot, output, {"environment": {"API_TOKEN": "secret"}})

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source"]["environment"] == "***REDACTED***"


def test_write_provenance_never_serializes_nested_environment_values(tmp_path: Path) -> None:
    """Catch nested source configuration that exposes environment names or values."""
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "provenance.json"

    write_provenance(
        snapshot,
        output,
        {"connection": {"environment": {"DATABASE_URL": "postgres://user:secret@host/db"}}},
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source"]["connection"]["environment"] == "***REDACTED***"


def test_write_provenance_redacts_command_header_values(tmp_path: Path) -> None:
    """Catch command headers that would serialize authorization credentials."""
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "provenance.json"

    write_provenance(
        snapshot,
        output,
        {
            "command": [
                "server",
                "-H",
                "Authorization: Bearer first-secret",
                "--header=Authorization: Bearer second-secret",
                "--header",
                "Authorization: Bearer third-secret",
            ]
        },
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source"]["command"][2] == "***REDACTED***"
    assert payload["source"]["command"][3] == "***REDACTED***"
    assert payload["source"]["command"][5] == "***REDACTED***"


def test_write_provenance_redacts_auth_options_and_environment_assignments(tmp_path: Path) -> None:
    """Catch credential-bearing command forms that bypass snapshot redaction."""
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text("{}\n", encoding="utf-8")
    output = tmp_path / "provenance.json"

    write_provenance(
        snapshot,
        output,
        {
            "command": [
                "API_TOKEN=secret",
                "GITHUB_PAT=secret",
                "AWS_ACCESS_KEY_ID=secret",
                "export",
                "API_TOKEN=export-secret",
                "--env",
                "API_TOKEN=environment-secret",
                "--env=API_TOKEN=inline-secret",
                "-e",
                "API_TOKEN=short-option-secret",
                "server",
                "--auth=secret",
                "--bearer-token=secret",
            ]
        },
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source"]["command"] == [
        "***REDACTED***",
        "***REDACTED***",
        "***REDACTED***",
        "export",
        "***REDACTED***",
        "--env",
        "***REDACTED***",
        "--env=***REDACTED***",
        "-e",
        "***REDACTED***",
        "server",
        "***REDACTED***",
        "***REDACTED***",
    ]
