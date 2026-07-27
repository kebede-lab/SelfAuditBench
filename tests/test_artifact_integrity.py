from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from selfauditbench.actors.strategies import NoAuditStrategy
from selfauditbench.adapters.io import read_scenarios
from selfauditbench.config import RunConfig
from selfauditbench.core.models import AuditEmissionMode, StrategyId
from selfauditbench.evaluation.runner import ReplayRunner
from selfauditbench.storage.artifacts import (
    ArtifactStore,
    RunLeaseError,
    verify_integrity_manifest,
)

ROOT = Path(__file__).parents[1]
FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _run(tmp_path: Path) -> Path:
    dataset = ROOT / "data" / "smoke" / "scenarios.jsonl"
    config = RunConfig(
        run_id="integrity-test",
        strategy=StrategyId.NO_AUDIT,
        audit_mode=AuditEmissionMode.NONE,
        dataset=dataset,
        output_root=tmp_path,
    )
    ReplayRunner(config, NoAuditStrategy(), clock=lambda: FIXED_TIME).run(
        read_scenarios(dataset)
    )
    return tmp_path / "integrity-test"


def test_fresh_run_integrity_verifies(tmp_path: Path) -> None:
    run_dir = _run(tmp_path)

    result = verify_integrity_manifest(run_dir)

    assert result["status"] == "verified"
    assert result["verified"] is True
    assert result["artifact_count"] >= 8


def test_mutated_artifact_fails_integrity(tmp_path: Path) -> None:
    run_dir = _run(tmp_path)
    with (run_dir / "metrics.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")

    result = verify_integrity_manifest(run_dir)

    assert result["status"] == "corrupt"
    assert "artifact mismatch: metrics.json" in result["errors"]


def test_unmanifested_run_is_legacy_not_corrupt(tmp_path: Path) -> None:
    run_dir = tmp_path / "old-run"
    run_dir.mkdir()

    result = verify_integrity_manifest(run_dir)

    assert result["status"] == "legacy_unverified"
    assert result["verified"] is False


def test_run_lease_rejects_concurrent_writer_and_releases_cleanly(
    tmp_path: Path,
) -> None:
    first = ArtifactStore(tmp_path, "shared-run")
    second = ArtifactStore(tmp_path, "shared-run")

    with first.run_lease():
        with pytest.raises(RunLeaseError, match="already active"):
            with second.run_lease():
                raise AssertionError("a second writer acquired the same run lease")

    with second.run_lease():
        second.write_json("metrics.json", {"status": "complete"})
        second.write_integrity_manifest()

    assert verify_integrity_manifest(second.run_dir)["verified"] is True
