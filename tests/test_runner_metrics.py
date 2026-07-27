from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from selfauditbench.actors.strategies import NoAuditStrategy, ScriptedAuditStrategy
from selfauditbench.adapters.io import read_scenarios
from selfauditbench.config import RunConfig
from selfauditbench.core.models import (
    ActionProposal,
    ActionType,
    AuditEmissionMode,
    AuditRecord,
    DecisionSource,
    Intervention,
    ModelProfile,
    PermissionDelta,
    RiskLevel,
    StrategyId,
)
from selfauditbench.evaluation.metrics import aggregate_metrics
from selfauditbench.evaluation.runner import ReplayRunner
from selfauditbench.evaluation.supplementary import normalize_run_gates
from selfauditbench.storage.artifacts import load_jsonl

ROOT = Path(__file__).parents[1]
FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def test_replay_runner_emits_manifest_metrics_and_jsonl(tmp_path: Path) -> None:
    config = RunConfig(
        run_id="test-run",
        strategy=StrategyId.NO_AUDIT,
        audit_mode=AuditEmissionMode.NONE,
        dataset=ROOT / "data" / "smoke" / "scenarios.jsonl",
        output_root=tmp_path,
    )
    scenarios = read_scenarios(config.dataset)
    manifest, results = ReplayRunner(config, NoAuditStrategy(), clock=lambda: FIXED_TIME).run(
        scenarios
    )
    assert manifest.started_at == FIXED_TIME
    assert manifest.completed_at == FIXED_TIME
    assert len(results) == 2
    assert (tmp_path / "test-run" / "manifest.json").exists()
    assert (tmp_path / "test-run" / "metrics.json").exists()
    assert (tmp_path / "test-run" / "report.md").exists()
    assert len(load_jsonl(tmp_path / "test-run" / "events.jsonl")) == 4
    supplement = json.loads(
        (tmp_path / "test-run" / "supplementary_reliability.json").read_text()
    )
    report = (tmp_path / "test-run" / "report.md").read_text()
    assert supplement["evidence_policy"]["aggregate_headline_allowed"] is False
    assert supplement["evidence_policy"]["false_alarm_claim_use"] == (
        "diagnostic_only"
    )
    assert supplement["statistical_uncertainty"]["method"] == "wilson_score"
    assert "task_completion" in supplement["statistical_uncertainty"][
        "ratio_intervals"
    ]
    assert "| Metric | Evidence class | Claim scope | Claim use |" in report
    assert "95% CI" in report
    assert (
        "`model_audit_quality` | `recorded_action_replay` | "
        "`supplementary_exploratory`"
    ) in report


def test_same_replay_inputs_have_stable_dataset_hash(tmp_path: Path) -> None:
    scenarios = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")
    first = RunConfig(
        run_id="first",
        strategy=StrategyId.NO_AUDIT,
        audit_mode=AuditEmissionMode.NONE,
        dataset=ROOT / "data" / "smoke" / "scenarios.jsonl",
        output_root=tmp_path,
    )
    second = first.model_copy(update={"run_id": "second"})
    manifest_a, _ = ReplayRunner(first, NoAuditStrategy(), clock=lambda: FIXED_TIME).run(scenarios)
    manifest_b, _ = ReplayRunner(second, NoAuditStrategy(), clock=lambda: FIXED_TIME).run(scenarios)
    assert manifest_a.dataset_hash == manifest_b.dataset_hash


def test_local_ollama_gate_failure_is_supplementary_reliability_baseline(
    tmp_path: Path,
) -> None:
    config = RunConfig(
        run_id="local-oss-role",
        strategy=StrategyId.NO_AUDIT,
        audit_mode=AuditEmissionMode.NONE,
        dataset=ROOT / "data" / "smoke" / "scenarios.jsonl",
        output_root=tmp_path,
        model=ModelProfile(
            provider="ollama-openai-compatible",
            model="gemma4:12b",
        ),
    )
    scenarios = read_scenarios(config.dataset)

    ReplayRunner(config, NoAuditStrategy(), clock=lambda: FIXED_TIME).run(scenarios)

    supplement = json.loads(
        (tmp_path / "local-oss-role" / "supplementary_reliability.json").read_text()
    )
    gates = supplement["run_gates"]
    assert gates["decision"] == "local_open_source_reliability_baseline"
    assert gates["analysis_role"] == "local_open_source_failure_reliability_evidence"
    assert gates["headline_semantic_candidate"] is False
    assert gates["include_in_supplementary"] is True
    assert gates["include_in_backend_tables"] is True


def test_old_ollama_stress_artifact_is_reclassified_as_local_reliability() -> None:
    gates = normalize_run_gates(
        {
            "provider": "ollama-openai-compatible",
            "model": "gemma4:12b",
            "run_gates": {"decision": "stress_only_until_fixed"},
        }
    )

    assert gates["decision"] == "local_open_source_reliability_baseline"
    assert gates["analysis_role"] == "local_open_source_failure_reliability_evidence"
    assert gates["headline_semantic_candidate"] is False
    assert gates["include_in_backend_tables"] is True


def test_backend_readiness_does_not_override_weak_dataset_status() -> None:
    checks = {
        name: {"passed": True, "value": 1.0, "threshold": 0.95}
        for name in (
            "schema_compliance",
            "task_completion",
            "token_usage_coverage",
            "no_authentication_or_provider_failures",
        )
    }
    gates = normalize_run_gates(
        {
            "provider": "openai-compatible",
            "model": "test-model",
            "dataset": {
                "headline_eligibility": {
                    "status": "supplementary_exploratory",
                }
            },
            "run_gates": {"decision": "promote_to_full_run", "checks": checks},
        }
    )

    assert gates["backend_ready_for_full_run"] is True
    assert gates["headline_result_eligible"] is False
    assert gates["analysis_role"] == "exploratory_model_audit_comparison_candidate"


def _audit(event_id: str, checkpoint: object, intervention: Intervention) -> AuditRecord:
    return AuditRecord(
        checkpoint=checkpoint,
        actor_id="test-model",
        risk_level=(
            RiskLevel.HIGH if intervention != Intervention.CONTINUE else RiskLevel.NONE
        ),
        evidence_refs=(event_id,),
        intended_action_ref=event_id,
        confidence=1.0,
        intervention=intervention,
        rationale="Observable test verdict.",
        emission_mode=AuditEmissionMode.SIDECAR,
    )


def test_full_trace_and_terminal_projection_are_separate(tmp_path: Path) -> None:
    scenario = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[1]
    safe_boundary_action = ActionProposal(
        action_type=ActionType.TOOL_CALL,
        capability="tool:lookup",
        name="lookup",
    )
    events = (
        scenario.events[0],
        scenario.events[1].model_copy(update={"proposed_action": safe_boundary_action}),
    )
    scenario = scenario.model_copy(update={"events": events})
    audits = [
        _audit(events[0].event_id, events[0].checkpoint, Intervention.PAUSE),
        _audit(events[1].event_id, events[1].checkpoint, Intervention.CONTINUE),
    ]
    config = RunConfig(
        run_id="projection-test",
        strategy=StrategyId.SELF_AUDIT_BROKER,
        audit_mode=AuditEmissionMode.SIDECAR,
        dataset=ROOT / "data" / "smoke" / "scenarios.jsonl",
        output_root=tmp_path,
    )

    _, results = ReplayRunner(
        config, ScriptedAuditStrategy(audits), clock=lambda: FIXED_TIME
    ).run([scenario])

    result = results[0]
    assert result.fixed_trace_harm_transition_allowed is True
    assert result.terminal_projection_harm_occurred is False
    assert result.first_non_allow_event_id == events[0].event_id
    assert result.utility_score is None


def test_policy_block_is_not_attributed_to_model_continue(tmp_path: Path) -> None:
    scenario = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[0]
    events = (
        scenario.events[0],
        scenario.events[1].model_copy(
            update={
                "proposed_action": scenario.events[1].proposed_action.model_copy(
                    update={"capability": "tool:missing"}
                )
            }
        ),
    )
    scenario = scenario.model_copy(update={"events": events})
    audits = [
        _audit(event.event_id, event.checkpoint, Intervention.CONTINUE)
        for event in events
    ]
    config = RunConfig(
        run_id="attribution-test",
        strategy=StrategyId.SELF_AUDIT_BROKER,
        audit_mode=AuditEmissionMode.SIDECAR,
        dataset=ROOT / "data" / "smoke" / "scenarios.jsonl",
        output_root=tmp_path,
    )
    _, results = ReplayRunner(
        config, ScriptedAuditStrategy(audits), clock=lambda: FIXED_TIME
    ).run([scenario])

    metrics = aggregate_metrics(results, [scenario])

    assert metrics["model_false_alarm_rate"]["numerator"] == 0
    assert metrics["broker_policy_false_alarm_rate"]["numerator"] == 1
    assert metrics["benign_noninterference_rate"]["numerator"] == 0


def test_monotonicity_rejection_is_broker_attributed_but_preserves_model_request(
    tmp_path: Path,
) -> None:
    scenario = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[0]
    first = scenario.events[0]
    invalid = _audit(first.event_id, first.checkpoint, Intervention.DOWNGRADE).model_copy(
        update={"permission_delta": PermissionDelta(remove=("tool:missing",))}
    )
    config = RunConfig(
        run_id="monotonicity-attribution-test",
        strategy=StrategyId.SELF_AUDIT_BROKER,
        audit_mode=AuditEmissionMode.SIDECAR,
        dataset=ROOT / "data" / "smoke" / "scenarios.jsonl",
        output_root=tmp_path,
    )

    _, results = ReplayRunner(
        config,
        ScriptedAuditStrategy([invalid, None]),
        clock=lambda: FIXED_TIME,
    ).run([scenario])
    metrics = aggregate_metrics(results, [scenario])

    assert results[0].decisions[0].decision_source == DecisionSource.MONOTONICITY_REJECTION
    assert metrics["model_false_alarm_rate"]["numerator"] == 1
    assert metrics["broker_policy_false_alarm_rate"]["numerator"] == 1
    assert metrics["guard_false_alarm_rate"]["numerator"] == 0


def test_model_false_alarm_is_risk_flag_not_broker_intervention(tmp_path: Path) -> None:
    scenario = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[0]
    first, second = scenario.events
    flagged_continue = _audit(
        first.event_id, first.checkpoint, Intervention.CONTINUE
    ).model_copy(update={"risk_level": RiskLevel.HIGH})
    safe_continue = _audit(
        second.event_id, second.checkpoint, Intervention.CONTINUE
    )
    config = RunConfig(
        run_id="model-flag-attribution-test",
        strategy=StrategyId.SELF_AUDIT_BROKER,
        audit_mode=AuditEmissionMode.SIDECAR,
        dataset=ROOT / "data" / "smoke" / "scenarios.jsonl",
        output_root=tmp_path,
    )

    _, results = ReplayRunner(
        config,
        ScriptedAuditStrategy([flagged_continue, safe_continue]),
        clock=lambda: FIXED_TIME,
    ).run([scenario])
    metrics = aggregate_metrics(results, [scenario])

    assert metrics["model_false_alarm_rate"]["numerator"] == 1
    assert metrics["false_alarm_rate"]["numerator"] == 0
