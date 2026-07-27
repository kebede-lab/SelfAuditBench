from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from selfauditbench.actors.strategies import NoAuditStrategy
from selfauditbench.adapters.io import read_scenarios
from selfauditbench.config import RunConfig
from selfauditbench.core.models import AuditEmissionMode, RunStatus, StrategyId
from selfauditbench.evaluation.runner import ReplayRunner
from selfauditbench.evaluation.statistics import (
    compare_run_directories,
    ratio_confidence_intervals,
    wilson_interval,
)
from selfauditbench.storage.artifacts import load_jsonl, write_integrity_manifest

ROOT = Path(__file__).parents[1]
FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def test_wilson_interval_and_metric_collection() -> None:
    interval = wilson_interval(5, 10)
    assert interval["lower"] is not None
    assert interval["upper"] is not None
    assert float(interval["lower"]) < 0.5 < float(interval["upper"])

    intervals = ratio_confidence_intervals(
        {
            "model_generated_early_detection_rate": {
                "value": 0.5,
                "numerator": 5,
                "denominator": 10,
            },
            "execution_reliability": {
                "task_completion": {
                    "value": 0.8,
                    "numerator": 8,
                    "denominator": 10,
                }
            },
            "closed_loop_recovery": {
                "safe_task_success_rate": {
                    "value": 0.7,
                    "numerator": 7,
                    "denominator": 10,
                }
            },
        }
    )
    assert set(intervals) == {
        "model_generated_early_detection_rate",
        "task_completion",
        "closed_loop_recovery.safe_task_success_rate",
    }


def test_paired_run_comparison_requires_exact_scenarios_and_clusters_pairs(
    tmp_path: Path,
) -> None:
    scenarios = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")
    for run_id in ("run-a", "run-b"):
        config = RunConfig(
            run_id=run_id,
            strategy=StrategyId.NO_AUDIT,
            audit_mode=AuditEmissionMode.NONE,
            dataset=ROOT / "data" / "smoke" / "scenarios.jsonl",
            output_root=tmp_path,
        )
        ReplayRunner(config, NoAuditStrategy(), clock=lambda: FIXED_TIME).run(scenarios)

    run_b_results = load_jsonl(tmp_path / "run-b" / "results.jsonl")
    run_b_results[0]["status"] = RunStatus.SCHEMA_ERROR.value
    with (tmp_path / "run-b" / "results.jsonl").open("w", encoding="utf-8") as handle:
        for row in run_b_results:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    write_integrity_manifest(tmp_path / "run-b")

    comparison = compare_run_directories(
        tmp_path / "run-a",
        tmp_path / "run-b",
        bootstrap_samples=100,
        seed=7,
    )

    assert comparison["shared_scenarios"] == 2
    assert len(comparison["evaluation_contract_hash"]) == 64
    assert comparison["integrity"]["run_a"]["status"] == "verified"
    assert comparison["integrity"]["run_b"]["status"] == "verified"
    task = comparison["metrics"]["task_completion"]
    assert task["run_a_rate"] == 1.0
    assert task["run_b_rate"] == 0.5
    assert task["difference"] == 0.5
    assert task["clusters"] == 1
    assert task["evidence_class"] == "schema_reliability"


def test_paired_run_comparison_rejects_missing_result(tmp_path: Path) -> None:
    scenarios = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")
    for run_id in ("run-a", "run-b"):
        config = RunConfig(
            run_id=run_id,
            strategy=StrategyId.NO_AUDIT,
            audit_mode=AuditEmissionMode.NONE,
            dataset=ROOT / "data" / "smoke" / "scenarios.jsonl",
            output_root=tmp_path,
        )
        ReplayRunner(config, NoAuditStrategy(), clock=lambda: FIXED_TIME).run(scenarios)
    rows = load_jsonl(tmp_path / "run-b" / "results.jsonl")[:-1]
    with (tmp_path / "run-b" / "results.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    write_integrity_manifest(tmp_path / "run-b")

    with pytest.raises(ValueError, match="one result per"):
        compare_run_directories(tmp_path / "run-a", tmp_path / "run-b")


def test_paired_run_comparison_rejects_duplicate_result(tmp_path: Path) -> None:
    run_a, run_b = _paired_runs(tmp_path)
    rows = load_jsonl(run_b / "results.jsonl")
    with (run_b / "results.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(rows[0], sort_keys=True) + "\n")
    write_integrity_manifest(run_b)

    with pytest.raises(ValueError, match="duplicate scenario_id in comparison results"):
        compare_run_directories(run_a, run_b)


def test_paired_run_comparison_rejects_corrupt_integrity(tmp_path: Path) -> None:
    run_a, run_b = _paired_runs(tmp_path)
    with (run_b / "metrics.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")

    with pytest.raises(ValueError, match=r"verified integrity.*status=corrupt"):
        compare_run_directories(run_a, run_b)


def test_paired_run_comparison_rejects_legacy_unverified_run(tmp_path: Path) -> None:
    run_a, run_b = _paired_runs(tmp_path)
    (run_b / "integrity.json").unlink()

    with pytest.raises(ValueError, match=r"status=legacy_unverified"):
        compare_run_directories(run_a, run_b)


def test_paired_run_comparison_requires_matching_contract_hashes(
    tmp_path: Path,
) -> None:
    run_a, run_b = _paired_runs(tmp_path)
    manifest_path = run_b / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    current = str(manifest["evaluation_contract_hash"])
    manifest["evaluation_contract_hash"] = ("0" if current[0] != "0" else "1") + current[1:]
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    write_integrity_manifest(run_b)

    with pytest.raises(ValueError, match="identical evaluation_contract_hash"):
        compare_run_directories(run_a, run_b)


def test_paired_run_comparison_requires_recorded_contract_hash(tmp_path: Path) -> None:
    run_a, run_b = _paired_runs(tmp_path)
    manifest_path = run_b / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("evaluation_contract_hash")
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    write_integrity_manifest(run_b)

    with pytest.raises(ValueError, match="recorded evaluation_contract_hash"):
        compare_run_directories(run_a, run_b)


def test_treatment_comparison_uses_shared_comparison_contract(tmp_path: Path) -> None:
    run_a, run_b = _paired_runs(tmp_path)
    shared = "a" * 64
    for index, run_dir in enumerate((run_a, run_b)):
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["comparison_contract_hash"] = shared
        manifest["evaluation_contract_hash"] = str(index) * 64
        manifest["treatment"] = {"condition": f"condition-{index}"}
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_integrity_manifest(run_dir)

    comparison = compare_run_directories(
        run_a,
        run_b,
        bootstrap_samples=10,
        allow_treatment_difference=True,
    )

    assert comparison["comparison_mode"] == "paired_treatment_ablation"
    assert comparison["comparison_contract_hash"] == shared
    assert comparison["treatments"]["run_a"]["condition"] == "condition-0"


def test_statistics_module_imports_in_fresh_process() -> None:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from selfauditbench.evaluation.statistics import wilson_interval; "
                "from selfauditbench.adapters import ASBReplayAdapter; "
                "assert wilson_interval(1, 2)['lower'] is not None; "
                "assert ASBReplayAdapter is not None"
            ),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def _paired_runs(tmp_path: Path) -> tuple[Path, Path]:
    scenarios = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")
    for run_id in ("run-a", "run-b"):
        config = RunConfig(
            run_id=run_id,
            strategy=StrategyId.NO_AUDIT,
            audit_mode=AuditEmissionMode.NONE,
            dataset=ROOT / "data" / "smoke" / "scenarios.jsonl",
            output_root=tmp_path,
        )
        ReplayRunner(config, NoAuditStrategy(), clock=lambda: FIXED_TIME).run(scenarios)
    return tmp_path / "run-a", tmp_path / "run-b"
