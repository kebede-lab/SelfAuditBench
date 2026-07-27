from __future__ import annotations

import json
from pathlib import Path

from selfauditbench.evaluation.conformance import (
    run_live_enforcement_conformance,
    verify_live_enforcement_conformance,
    write_live_enforcement_conformance,
)


def test_live_enforcement_conformance_covers_sinks_and_persistence() -> None:
    result = run_live_enforcement_conformance()

    assert result["execution_semantics"] == "enacted_live_mediation"
    assert result["summary"]["all_passed"] is True
    assert result["summary"]["total"] == 6
    assert {item["sink"] for item in result["cases"]} == {
        "tool_call",
        "memory_write",
        "environment_query",
        "disclosure",
        "commit",
        "persistent_permission_state",
    }


def test_live_enforcement_conformance_writes_hashed_artifact(tmp_path: Path) -> None:
    output = write_live_enforcement_conformance(tmp_path / "live.json")
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert len(payload["evidence_sha256"]) == 64
    assert payload["summary"]["passed"] == payload["summary"]["total"]
    assert verify_live_enforcement_conformance(output)

    payload["claim_scope"] = "tampered"
    output.write_text(json.dumps(payload), encoding="utf-8")
    assert not verify_live_enforcement_conformance(output)
