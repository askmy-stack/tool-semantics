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
