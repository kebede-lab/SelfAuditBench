"""Import reproduced AgentForesight API outputs as SelfAuditBench results."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from selfauditbench.adapters.common import REPLAY_TIMESTAMP, relative_ref, stable_id
from selfauditbench.core.models import (
    AuditEmissionMode,
    AuditRecord,
    Checkpoint,
    Intervention,
    ModelProfile,
    RiskLevel,
    RiskType,
    RunManifest,
    RunStatus,
    Scenario,
    ScenarioResult,
    StrategyId,
)
from selfauditbench.evaluation.metrics import aggregate_metrics
from selfauditbench.evaluation.report import write_report
from selfauditbench.evaluation.supplementary import write_supplementary_run_data
from selfauditbench.storage.artifacts import ArtifactStore
from selfauditbench.storage.hashing import sha256_json


@dataclass(frozen=True)
class AFTrajReproductionImport:
    """Parsed AgentForesight reproduction rows matched to normalized scenarios."""

    configs: tuple[dict[str, Any], ...]
    scenarios: tuple[Scenario, ...]
    results: tuple[ScenarioResult, ...]

    @property
    def latest_config(self) -> dict[str, Any]:
        return self.configs[-1] if self.configs else {}


def load_agentforesight_reproduction_results(
    per_sample_path: Path,
    scenarios: Sequence[Scenario],
    *,
    allow_missing: bool = False,
) -> AFTrajReproductionImport:
    """Convert AgentForesight ``per_sample.jsonl`` rows into ScenarioResult objects."""

    by_id = {scenario.scenario_id: scenario for scenario in scenarios}
    configs: list[dict[str, Any]] = []
    matched_scenarios: list[Scenario] = []
    results: list[ScenarioResult] = []
    seen: set[str] = set()

    for line_number, row in _read_jsonl(per_sample_path):
        record_type = row.get("_record_type")
        if record_type == "config":
            configs.append(dict(row))
            continue
        if record_type is not None:
            continue

        split = str(row.get("label", ""))
        conv_id = str(row.get("conv_id", ""))
        scenario_id = stable_id("agentforesight", split, conv_id)
        scenario = by_id.get(scenario_id)
        if scenario is None:
            if allow_missing:
                continue
            raise ValueError(
                f"AgentForesight result {conv_id!r} ({split}) has no matching scenario"
            )
        if scenario_id in seen:
            raise ValueError(f"duplicate AgentForesight result for scenario {scenario_id}")
        seen.add(scenario_id)
        matched_scenarios.append(scenario)
        results.append(_result_from_row(row, scenario, per_sample_path, line_number))

    return AFTrajReproductionImport(
        configs=tuple(configs),
        scenarios=tuple(matched_scenarios),
        results=tuple(results),
    )


def write_agentforesight_reproduction_run(
    per_sample_path: Path,
    scenarios: Sequence[Scenario],
    run_dir: Path,
    *,
    allow_missing: bool = False,
) -> AFTrajReproductionImport:
    """Persist a reproduced AgentForesight API baseline as a SelfAuditBench run."""

    imported = load_agentforesight_reproduction_results(
        per_sample_path,
        scenarios,
        allow_missing=allow_missing,
    )
    store = ArtifactStore(run_dir.parent, run_dir.name)
    store.reset_replay_outputs()
    for audit in (audit for result in imported.results for audit in result.audits):
        store.record_audit(audit)
    for result in imported.results:
        store.record_result(result)

    dataset = [scenario.model_dump(mode="json") for scenario in imported.scenarios]
    store.write_json("dataset.json", dataset)
    metrics = aggregate_metrics(imported.results, imported.scenarios)
    store.write_json("metrics.json", metrics)
    store.write_json("agentforesight_reproduction_config.json", list(imported.configs))
    manifest = _manifest(run_dir.name, imported)
    store.write_manifest(manifest)
    write_report(store.run_dir, metrics)
    write_supplementary_run_data(store.run_dir, manifest, metrics)
    store.write_integrity_manifest()
    return imported


def _result_from_row(
    row: dict[str, Any],
    scenario: Scenario,
    per_sample_path: Path,
    line_number: int,
) -> ScenarioResult:
    status = RunStatus.COMPLETE
    error_message = None
    if row.get("format_valid") is False:
        status = RunStatus.SCHEMA_ERROR
        error_message = "AgentForesight parser marked the response format invalid."

    pred_step = int(row.get("pred_step", -1))
    if pred_step < 0:
        return ScenarioResult(
            scenario_id=scenario.scenario_id,
            status=status,
            audit_opportunities=1,
            error_message=error_message,
        )
    if pred_step >= len(scenario.events):
        return ScenarioResult(
            scenario_id=scenario.scenario_id,
            status=RunStatus.ADAPTER_ERROR,
            audit_opportunities=1,
            error_message=f"pred_step {pred_step} is outside {len(scenario.events)} events",
        )

    event = scenario.events[pred_step]
    audit = AuditRecord(
        checkpoint=event.checkpoint or Checkpoint.POST_MESSAGE,
        actor_id=_actor_id(row),
        risk_level=RiskLevel.HIGH,
        risk_types=(RiskType.UNKNOWN,),
        evidence_refs=(event.event_id,),
        intended_action_ref=event.event_id,
        confidence=1.0,
        intervention=Intervention.PAUSE,
        rationale=_rationale(row, pred_step),
        emission_mode=AuditEmissionMode.EXTERNAL,
        raw_response_ref=(
            f"{relative_ref(per_sample_path, per_sample_path.parent)}#line={line_number}"
        ),
    )
    return ScenarioResult(
        scenario_id=scenario.scenario_id,
        status=status,
        audits=(audit,),
        audit_event_ids=(event.event_id,),
        audit_opportunities=1,
        error_message=error_message,
    )


def _actor_id(row: dict[str, Any]) -> str:
    agent = str(row.get("pred_agent") or "").strip()
    return f"agentforesight:{agent}" if agent else "agentforesight"


def _rationale(row: dict[str, Any], pred_step: int) -> str:
    reason = str(row.get("pred_reason") or "").strip()
    if not reason:
        reason = f"AgentForesight reproduced API baseline flagged step {pred_step}."
    return reason[:1000]


def _manifest(run_id: str, imported: AFTrajReproductionImport) -> RunManifest:
    config = imported.latest_config
    dataset_hash = sha256_json(
        [scenario.model_dump(mode="json") for scenario in imported.scenarios]
    )
    execution_semantics = "imported_observer_result"
    model = None
    if config.get("model"):
        model = ModelProfile(
            provider="openai-compatible",
            model=str(config["model"]),
            base_url=str(config["base_url"]) if config.get("base_url") else None,
            timeout_seconds=float(config.get("timeout_seconds", 60.0)),
            max_retries=int(config.get("max_retries", 0)),
        )
    return RunManifest(
        run_id=run_id,
        strategy=StrategyId.EXTERNAL_AUDITOR,
        audit_mode=AuditEmissionMode.EXTERNAL,
        config_hash=sha256_json(config),
        dataset_hash=dataset_hash,
        random_seed=0,
        model_profile=model,
        execution_semantics=execution_semantics,
        evaluation_contract_hash=sha256_json(
            {
                "schema_version": "1.0",
                "strategy": StrategyId.EXTERNAL_AUDITOR,
                "audit_mode": AuditEmissionMode.EXTERNAL,
                "random_seed": 0,
                "dataset_hash": dataset_hash,
                "execution_semantics": execution_semantics,
                "paper_test_split": bool(config.get("paper_test_split", True)),
                "splits": config.get("splits", ["safe", "unsafe"]),
                "domains": config.get("domains"),
                "temperature": config.get("temperature", 0.0),
                "max_tokens": config.get("max_tokens", 2048),
            }
        ),
        environment={
            "source": "reproduced-agentforesight-api",
            "samples": str(len(imported.results)),
            "config_records": str(len(imported.configs)),
        },
        started_at=REPLAY_TIMESTAMP,
        completed_at=REPLAY_TIMESTAMP,
    )


def _read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append((line_number, json.loads(line)))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
    return rows
