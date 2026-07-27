from __future__ import annotations

import pytest

from selfauditbench.core.broker import PolicyBroker
from selfauditbench.core.models import (
    ActionProposal,
    ActionType,
    AuditEmissionMode,
    AuditRecord,
    BrokerOutcome,
    CapabilityGrant,
    Checkpoint,
    DecisionSource,
    EventKind,
    Intervention,
    PermissionDelta,
    PermissionState,
    Provenance,
    RiskLevel,
    Sensitivity,
    TrajectoryEvent,
)
from selfauditbench.core.permissions import PermissionDeltaError, apply_delta


def state() -> PermissionState:
    return PermissionState(
        grants={
            "tool:lookup": CapabilityGrant(
                capability="tool:lookup",
                operations=(ActionType.TOOL_CALL.value,),
                resources=("public-weather",),
                fields=("temperature", "wind"),
                max_sensitivity=Sensitivity.PERSONAL,
                remaining_calls=1,
                requires_confirmation=True,
            )
        },
        disclosure_ceiling=Sensitivity.PERSONAL,
    )


def tool_event(arguments: dict[str, object] | None = None) -> TrajectoryEvent:
    return TrajectoryEvent(
        event_id="scenario:event:0",
        scenario_id="scenario",
        sequence=0,
        event_kind=EventKind.TOOL_PROPOSAL,
        source=Provenance.AGENT,
        checkpoint=Checkpoint.PRE_TOOL,
        proposed_action=ActionProposal(
            action_type=ActionType.TOOL_CALL,
            capability="tool:lookup",
            name="lookup",
            arguments=(
                arguments
                if arguments is not None
                else {
                    "resource": "public-weather",
                    "fields": ["temperature"],
                    "_confirmed": True,
                }
            ),
        ),
    )


def test_actor_can_narrow_but_not_expand_permissions() -> None:
    current = state()
    narrowed = CapabilityGrant(
        capability="tool:lookup",
        operations=(ActionType.TOOL_CALL.value,),
        resources=("public-weather",),
        fields=("temperature",),
        max_sensitivity=Sensitivity.INTERNAL,
        remaining_calls=0,
        requires_confirmation=True,
    )
    updated = apply_delta(current, PermissionDelta(narrow={"tool:lookup": narrowed}))
    assert updated.grants["tool:lookup"] == narrowed
    assert updated.revision == 1

    expanded = narrowed.model_copy(update={"fields": ("*",)})
    with pytest.raises(PermissionDeltaError):
        apply_delta(updated, PermissionDelta(narrow={"tool:lookup": expanded}))


def test_actor_cannot_restore_missing_capability_or_raise_disclosure_ceiling() -> None:
    removed = apply_delta(state(), PermissionDelta(remove=("tool:lookup",)))
    with pytest.raises(PermissionDeltaError):
        apply_delta(
            removed,
            PermissionDelta(
                narrow={"tool:lookup": CapabilityGrant(capability="tool:lookup")}
            ),
        )
    with pytest.raises(PermissionDeltaError):
        apply_delta(state(), PermissionDelta(disclosure_ceiling=Sensitivity.RESTRICTED))


def test_allowed_action_consumes_budget_and_second_call_is_blocked() -> None:
    broker = PolicyBroker(state())
    first = broker.mediate(tool_event(), trusted_confirmation=True)
    assert first.outcome == BrokerOutcome.ALLOW
    assert broker.permissions.grants["tool:lookup"].remaining_calls == 0

    second = broker.mediate(tool_event(), trusted_confirmation=True)
    assert second.outcome == BrokerOutcome.BLOCK_AND_REPLAN
    assert "exhausted" in second.reason


def test_actor_confirmation_argument_is_not_trusted() -> None:
    forged = PolicyBroker(state()).mediate(tool_event())
    assert forged.outcome == BrokerOutcome.BLOCK_AND_REPLAN
    assert forged.decision_source == DecisionSource.PERMISSION_POLICY
    assert "trusted confirmation" in forged.reason

    trusted = PolicyBroker(state()).mediate(tool_event(), trusted_confirmation=True)
    assert trusted.outcome == BrokerOutcome.ALLOW


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"fields": ["temperature"]}, "explicit resource"),
        ({"resource": "public-weather"}, "explicit field list"),
    ],
)
def test_bounded_scope_metadata_cannot_be_omitted(
    arguments: dict[str, object], message: str
) -> None:
    decision = PolicyBroker(state()).mediate(
        tool_event(arguments),
        trusted_confirmation=True,
    )
    assert decision.outcome == BrokerOutcome.BLOCK_AND_REPLAN
    assert message in decision.reason


def test_rejected_delta_is_requested_but_not_applied() -> None:
    broker = PolicyBroker(state())
    requested = PermissionDelta(remove=("tool:missing",))
    audit = AuditRecord(
        checkpoint=Checkpoint.PRE_TOOL,
        actor_id="actor",
        risk_level=RiskLevel.HIGH,
        evidence_refs=("scenario:event:0",),
        intended_action_ref="scenario:event:0",
        confidence=0.9,
        intervention=Intervention.DOWNGRADE,
        permission_delta=requested,
        rationale="Remove an unavailable capability.",
        emission_mode=AuditEmissionMode.SIDECAR,
    )

    decision = broker.mediate(tool_event(), audit, trusted_confirmation=True)

    assert decision.outcome == BrokerOutcome.BLOCK_AND_REPLAN
    assert decision.decision_source == DecisionSource.MONOTONICITY_REJECTION
    assert decision.requested_delta == requested
    assert decision.applied_delta == PermissionDelta()


def test_requested_downgrade_is_applied_before_block_and_replan() -> None:
    broker = PolicyBroker(state())
    audit = AuditRecord(
        checkpoint=Checkpoint.PRE_TOOL,
        actor_id="actor",
        risk_level=RiskLevel.HIGH,
        confidence=0.9,
        intervention=Intervention.DOWNGRADE,
        permission_delta=PermissionDelta(remove=("tool:lookup",)),
        rationale="The observation is untrusted.",
        emission_mode=AuditEmissionMode.SIDECAR,
    )
    decision = broker.mediate(tool_event(), audit)
    assert decision.outcome == BrokerOutcome.BLOCK_AND_REPLAN
    assert "tool:lookup" not in decision.permission_after.grants


def test_checkpoint_mismatch_fails_closed() -> None:
    broker = PolicyBroker(state())
    audit = AuditRecord(
        checkpoint=Checkpoint.POST_OBSERVATION,
        actor_id="actor",
        risk_level=RiskLevel.HIGH,
        confidence=1,
        intervention=Intervention.CONTINUE,
        rationale="Mismatched checkpoint.",
        emission_mode=AuditEmissionMode.SIDECAR,
    )
    decision = broker.mediate(tool_event(), audit)
    assert decision.outcome == BrokerOutcome.BLOCK_AND_REPLAN
    assert "checkpoint" in decision.reason


def test_disclosure_above_ceiling_is_blocked() -> None:
    broker = PolicyBroker(
        PermissionState(
            grants={
                "disclosure:external_agent": CapabilityGrant(
                    capability="disclosure:external_agent",
                    operations=(ActionType.DISCLOSURE.value,),
                )
            },
            disclosure_ceiling=Sensitivity.INTERNAL,
        )
    )
    event = TrajectoryEvent(
        event_id="scenario:event:disclosure",
        scenario_id="scenario",
        sequence=0,
        event_kind=EventKind.DISCLOSURE_PROPOSAL,
        source=Provenance.AGENT,
        checkpoint=Checkpoint.PRE_DISCLOSURE,
        proposed_action=ActionProposal(
            action_type=ActionType.DISCLOSURE,
            capability="disclosure:external_agent",
            sensitivity=Sensitivity.SENSITIVE,
        ),
    )
    decision = broker.mediate(event)
    assert decision.outcome == BrokerOutcome.BLOCK_AND_REPLAN
    assert "disclosure ceiling" in decision.reason
