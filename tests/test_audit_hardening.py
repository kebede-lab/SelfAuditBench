from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from selfauditbench.actors.clients import ScriptedModelClient
from selfauditbench.actors.strategies import ModelAuditStrategy, classify_exception
from selfauditbench.adapters.io import read_scenarios
from selfauditbench.config import RunConfig
from selfauditbench.core.models import (
    AuditEmissionMode,
    Checkpoint,
    FailureType,
    Intervention,
    ModelProfile,
    RunStatus,
    StrategyId,
)
from selfauditbench.evaluation.runner import ReplayRunner
from selfauditbench.storage.artifacts import load_jsonl

ROOT = Path(__file__).parents[1]
FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _valid_continue_audit(event_id: str) -> dict[str, object]:
    return {
        "risk_level": "none",
        "risk_types": [],
        "evidence_refs": [event_id],
        "confidence": 0.0,
        "intervention": "continue",
        "permission_delta": {},
        "rationale": "No observable risk requiring intervention.",
    }


def test_model_audit_strategy_repairs_invalid_enum_once() -> None:
    scenario = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[0]
    event = scenario.events[0]
    client = ScriptedModelClient(
        [
            {
                "risk_level": "none",
                "risk_types": [],
                "evidence_refs": [event.event_id],
                "confidence": 0.0,
                "intervention": "none",
                "permission_delta": {},
                "rationale": "No intervention is needed.",
            },
            {
                "risk_level": "none",
                "risk_types": [],
                "evidence_refs": [event.event_id],
                "confidence": 0.0,
                "intervention": "continue",
                "permission_delta": {},
                "rationale": "No observable risk requiring intervention.",
            },
        ]
    )
    strategy = ModelAuditStrategy(
        client,
        actor_id="self_audit_broker",
        emission_mode=AuditEmissionMode.SIDECAR,
    )

    audit = strategy.audit(event, (), scenario.initial_permissions)
    attempts = strategy.drain_attempts()

    assert audit.intervention == Intervention.CONTINUE
    assert audit.raw_response_ref == f"audit_attempts:{event.event_id}:2"
    assert len(client.messages) == 2
    assert "allowed_values" in client.messages[0][1]["content"]
    assert "minimal_valid_example" in client.messages[0][1]["content"]
    assert attempts[0].failure_type == FailureType.ENUM_VALIDATION_ERROR
    assert attempts[0].repair_attempt is False
    assert attempts[1].success is True
    assert attempts[1].repair_attempt is True


def test_model_audit_strategy_accepts_fenced_json_without_repair() -> None:
    scenario = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[0]
    event = scenario.events[0]
    response = json.dumps(_valid_continue_audit(event.event_id), sort_keys=True)
    client = ScriptedModelClient([f"```json\n{response}\n```"])
    strategy = ModelAuditStrategy(
        client,
        actor_id="self_audit_broker",
        emission_mode=AuditEmissionMode.SIDECAR,
    )

    audit = strategy.audit(event, (), scenario.initial_permissions)
    attempts = strategy.drain_attempts()

    assert audit.intervention == Intervention.CONTINUE
    assert len(attempts) == 1
    assert attempts[0].success is True
    assert attempts[0].repair_attempt is False


def test_model_audit_strategy_accepts_thinking_preamble_and_audit_record_wrapper() -> None:
    scenario = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[0]
    event = scenario.events[0]
    wrapped = {"audit_record": _valid_continue_audit(event.event_id)}
    raw = f"<think>brief private scratchpad</think>\n\n{json.dumps(wrapped, sort_keys=True)}"
    client = ScriptedModelClient([raw])
    strategy = ModelAuditStrategy(
        client,
        actor_id="self_audit_broker",
        emission_mode=AuditEmissionMode.SIDECAR,
    )

    audit = strategy.audit(event, (), scenario.initial_permissions)
    attempts = strategy.drain_attempts()

    assert audit.intervention == Intervention.CONTINUE
    assert len(attempts) == 1
    assert attempts[0].success is True
    assert attempts[0].repair_attempt is False


def test_model_audit_strategy_rejects_misspelled_permission_delta_field() -> None:
    scenario = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[0]
    event = scenario.events[0]
    bad = _valid_continue_audit(event.event_id)
    bad.pop("permission_delta")
    bad["permission__delta"] = {}
    client = ScriptedModelClient([bad, _valid_continue_audit(event.event_id)])
    strategy = ModelAuditStrategy(
        client,
        actor_id="self_audit_broker",
        emission_mode=AuditEmissionMode.SIDECAR,
    )

    audit = strategy.audit(event, (), scenario.initial_permissions)
    attempts = strategy.drain_attempts()

    assert audit.intervention == Intervention.CONTINUE
    assert attempts[0].success is False
    assert attempts[0].failure_type == FailureType.SCHEMA_VALIDATION_ERROR
    assert attempts[1].success is True
    assert attempts[1].repair_attempt is True


def test_model_audit_strategy_uses_second_bounded_repair_for_alias_drift() -> None:
    scenario = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[0]
    event = scenario.events[0]
    first = _valid_continue_audit(event.event_id)
    first["event_id"] = event.event_id
    second = _valid_continue_audit(event.event_id)
    second["intention"] = event.event_id
    client = ScriptedModelClient([first, second, _valid_continue_audit(event.event_id)])
    strategy = ModelAuditStrategy(
        client,
        actor_id="self_audit_broker",
        emission_mode=AuditEmissionMode.SIDECAR,
    )

    audit = strategy.audit(event, (), scenario.initial_permissions)
    attempts = strategy.drain_attempts()

    assert audit.intended_action_ref == event.event_id
    assert [attempt.attempt_index for attempt in attempts] == [1, 2, 3]
    assert [attempt.repair_attempt for attempt in attempts] == [False, True, True]
    assert [attempt.success for attempt in attempts] == [False, False, True]
    for messages in client.messages[1:]:
        repair = json.loads(messages[1]["content"])["repair_directive"]
        assert repair["exact_context_fields"]["intended_action_ref"] == event.event_id
        assert "intended_action_ref" in repair["allowed_top_level_fields"]
        assert repair["forbidden_top_level_aliases"] == [
            "event_id",
            "intention",
            "intended_action",
            "action_ref",
        ]


def test_model_audit_strategy_stops_after_two_schema_repairs() -> None:
    scenario = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[0]
    event = scenario.events[0]
    invalid = []
    for alias in ("event_id", "intention", "action_ref"):
        response = _valid_continue_audit(event.event_id)
        response[alias] = event.event_id
        invalid.append(response)
    client = ScriptedModelClient(invalid)
    strategy = ModelAuditStrategy(
        client,
        actor_id="self_audit_broker",
        emission_mode=AuditEmissionMode.SIDECAR,
    )

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        strategy.audit(event, (), scenario.initial_permissions)
    attempts = strategy.drain_attempts()

    assert [attempt.attempt_index for attempt in attempts] == [1, 2, 3]
    assert [attempt.repair_attempt for attempt in attempts] == [False, True, True]
    assert all(not attempt.success for attempt in attempts)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("actor_id", "spoofed-auditor"),
        ("checkpoint", "pre_tool"),
        ("emission_mode", "external"),
        ("intended_action_ref", "other:event"),
        ("evidence_refs", ["other:event"]),
    ],
)
def test_model_audit_strategy_repairs_unbound_context_fields(field: str, value: object) -> None:
    scenario = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[0]
    event = scenario.events[0]
    bad = _valid_continue_audit(event.event_id)
    bad[field] = value
    client = ScriptedModelClient([bad, _valid_continue_audit(event.event_id)])
    strategy = ModelAuditStrategy(
        client,
        actor_id="self_audit_broker",
        emission_mode=AuditEmissionMode.SIDECAR,
    )

    audit = strategy.audit(event, (), scenario.initial_permissions)
    attempts = strategy.drain_attempts()

    assert audit.actor_id == "self_audit_broker"
    assert audit.checkpoint == Checkpoint.PRE_PLAN
    assert audit.emission_mode == AuditEmissionMode.SIDECAR
    assert audit.intended_action_ref == event.event_id
    assert attempts[0].failure_type == FailureType.SCHEMA_VALIDATION_ERROR
    assert attempts[1].success is True


def test_model_audit_strategy_rejects_ungrounded_quarantine() -> None:
    scenario = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[0]
    event = scenario.events[0]
    bad = _valid_continue_audit(event.event_id)
    bad.update(
        {
            "risk_level": "high",
            "intervention": "quarantine",
            "permission_delta": {"quarantine_sources": ["other:event"]},
        }
    )
    client = ScriptedModelClient([bad, _valid_continue_audit(event.event_id)])
    strategy = ModelAuditStrategy(
        client,
        actor_id="self_audit_broker",
        emission_mode=AuditEmissionMode.SIDECAR,
    )

    strategy.audit(event, (), scenario.initial_permissions)
    attempts = strategy.drain_attempts()

    assert attempts[0].failure_type == FailureType.SCHEMA_VALIDATION_ERROR
    assert attempts[1].success is True


def test_model_audit_strategy_rejects_non_monotonic_delta_before_success() -> None:
    scenario = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[0]
    event = scenario.events[0]
    bad = _valid_continue_audit(event.event_id)
    bad.update(
        {
            "risk_level": "high",
            "intervention": "downgrade",
            "permission_delta": {"remove": ["tool:missing"]},
        }
    )
    client = ScriptedModelClient([bad, _valid_continue_audit(event.event_id)])
    strategy = ModelAuditStrategy(
        client,
        actor_id="self_audit_broker",
        emission_mode=AuditEmissionMode.SIDECAR,
    )

    strategy.audit(event, (), scenario.initial_permissions)
    attempts = strategy.drain_attempts()

    assert attempts[0].failure_type == FailureType.PERMISSION_DELTA_ERROR
    assert attempts[1].success is True


def test_runner_records_prevalidated_permission_delta_rejection(tmp_path: Path) -> None:
    scenario = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[0]
    first, second = scenario.events
    bad = _valid_continue_audit(first.event_id)
    bad.update(
        {
            "risk_level": "high",
            "intervention": "downgrade",
            "permission_delta": {"remove": ["tool:missing"]},
        }
    )
    client = ScriptedModelClient(
        [bad, _valid_continue_audit(first.event_id), _valid_continue_audit(second.event_id)]
    )
    strategy = ModelAuditStrategy(
        client,
        actor_id="self_audit_broker",
        emission_mode=AuditEmissionMode.SIDECAR,
    )
    config = RunConfig(
        run_id="permission-delta-safety-event",
        strategy=StrategyId.SELF_AUDIT_BROKER,
        audit_mode=AuditEmissionMode.SIDECAR,
        dataset=ROOT / "data" / "smoke" / "scenarios.jsonl",
        output_root=tmp_path,
        fail_closed=True,
    )

    ReplayRunner(config, strategy, clock=lambda: FIXED_TIME).run([scenario])
    safety_events = load_jsonl(
        tmp_path / "permission-delta-safety-event" / "agent_safety_events.jsonl"
    )

    assert [item["behavior_type"] for item in safety_events] == ["permission_escalation_attempt"]


def test_model_profile_accepts_output_budget_controls() -> None:
    profile = ModelProfile(
        provider="openai-compatible",
        model="test-model",
        temperature=0,
        max_tokens=900,
        concise_rationale_words=80,
    )

    assert profile.temperature == 0
    assert profile.max_tokens == 900
    assert profile.concise_rationale_words == 80


def test_scripted_client_preflight_accepts_thinking_preamble() -> None:
    client = ScriptedModelClient(['<think>checking</think>\n\n{"ok": true}'])

    client.preflight()

    assert client.last_call_usage()["total_tokens_estimated"] is not None


def test_runner_records_guard_failures_and_model_only_metrics(tmp_path: Path) -> None:
    scenarios = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")
    event_count = sum(len(scenario.events) for scenario in scenarios)
    client = ScriptedModelClient(
        ["<html><body><h1>503 Service Unavailable</h1></body></html>"] * event_count
    )
    strategy = ModelAuditStrategy(
        client,
        actor_id="self_audit_broker",
        emission_mode=AuditEmissionMode.SIDECAR,
    )
    config = RunConfig(
        run_id="guard-taxonomy",
        strategy=StrategyId.SELF_AUDIT_BROKER,
        audit_mode=AuditEmissionMode.SIDECAR,
        dataset=ROOT / "data" / "smoke" / "scenarios.jsonl",
        output_root=tmp_path,
        fail_closed=True,
    )

    _, results = ReplayRunner(config, strategy, clock=lambda: FIXED_TIME).run(scenarios)
    metrics = json.loads((tmp_path / "guard-taxonomy" / "metrics.json").read_text())
    supplement = json.loads(
        (tmp_path / "guard-taxonomy" / "supplementary_reliability.json").read_text()
    )
    attempts = load_jsonl(tmp_path / "guard-taxonomy" / "audit_attempts.jsonl")
    safety_events = load_jsonl(tmp_path / "guard-taxonomy" / "agent_safety_events.jsonl")

    assert {result.status for result in results} == {RunStatus.ACTOR_ERROR}
    assert {result.failure_type for result in results} == {FailureType.PROVIDER_503}
    assert len(attempts) == event_count
    assert {attempt["failure_type"] for attempt in attempts} == {"provider_503"}
    assert {attempt["token_accounting"] for attempt in attempts} == {"local_estimate"}
    assert all(attempt["total_tokens_estimated"] is not None for attempt in attempts)
    assert len(safety_events) == 2
    assert {event["behavior_type"] for event in safety_events} == {"schema_guard_loop"}
    assert metrics["valid_audit_coverage"]["value"] == 0.0
    assert metrics["guard_triggered_pause_rate"]["value"] == 1.0
    assert metrics["model_generated_early_detection_rate"]["value"] == 0.0
    assert metrics["guard_false_alarm_rate"]["value"] == 1.0
    assert metrics["execution_reliability"]["failure_types"] == {"provider_503": 2}
    assert supplement["api"]["call_attempts"] == event_count
    assert supplement["api"]["token_cost_proxy_basis"] == "local_estimate"
    assert (
        supplement["api"]["token_cost_proxy_units"]
        == supplement["api"]["local_estimated_total_tokens"]
    )
    assert supplement["failure_distribution"]["audit_attempt_failure_types"] == {
        "provider_503": event_count
    }
    assert supplement["agent_testing_agent_safety"]["behavior_counts"] == {"schema_guard_loop": 2}


def test_authentication_errors_are_classified_separately() -> None:
    error = RuntimeError("Error code: 401 - {'code': 401, 'message': 'Unauthorized'}")
    assert classify_exception(error) == FailureType.AUTHENTICATION_ERROR
