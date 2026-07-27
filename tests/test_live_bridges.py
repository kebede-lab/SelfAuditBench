from __future__ import annotations

from dataclasses import dataclass

import pytest

from selfauditbench.actors.clients import ScriptedModelClient
from selfauditbench.actors.strategies import (
    CombinedAuditStrategy,
    ModelAuditStrategy,
    NoAuditStrategy,
    ScriptedAuditStrategy,
)
from selfauditbench.adapters.live import (
    ASBLiveBridge,
    BrokerRuntime,
    ConVerseLiveBridge,
    instrument_asb_agent,
)
from selfauditbench.core.models import (
    ActionProposal,
    ActionType,
    AuditEmissionMode,
    AuditEnvelope,
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
    RiskType,
    TrajectoryEvent,
)


class VectorStore:
    def __init__(self) -> None:
        self.writes = []

    def add_documents(self, documents: object) -> list[str]:
        self.writes.append(documents)
        return ["stored"]


def asb_permissions(include_write: bool = True) -> PermissionState:
    grants = {
        "tool:lookup": CapabilityGrant(
            capability="tool:lookup", operations=(ActionType.TOOL_CALL.value,)
        )
    }
    if include_write:
        grants["memory:write"] = CapabilityGrant(
            capability="memory:write", operations=(ActionType.MEMORY_WRITE.value,)
        )
    return PermissionState(grants=grants)


def converse_permissions(include_disclosure: bool = True) -> PermissionState:
    grants = {
        "environment:query": CapabilityGrant(
            capability="environment:query", operations=(ActionType.ENVIRONMENT_QUERY.value,)
        ),
        "commit:final": CapabilityGrant(
            capability="commit:final", operations=(ActionType.COMMIT.value,)
        ),
    }
    if include_disclosure:
        grants["disclosure:external_agent"] = CapabilityGrant(
            capability="disclosure:external_agent", operations=(ActionType.DISCLOSURE.value,)
        )
    return PermissionState(grants=grants)


def test_asb_vector_store_write_is_mediated() -> None:
    store = VectorStore()
    bridge = ASBLiveBridge(BrokerRuntime("asb", asb_permissions(), NoAuditStrategy()))
    wrapped = bridge.wrap_vectorstore(store)
    assert wrapped.add_documents(["workflow"]) == ["stored"]
    assert store.writes == [["workflow"]]


def test_asb_vector_store_write_is_blocked_without_permission() -> None:
    store = VectorStore()
    bridge = ASBLiveBridge(
        BrokerRuntime("asb", asb_permissions(include_write=False), NoAuditStrategy())
    )
    wrapped = bridge.wrap_vectorstore(store)
    assert wrapped.add_documents(["workflow"]) == []
    assert store.writes == []


def test_asb_live_bridge_covers_every_declared_checkpoint() -> None:
    bridge = ASBLiveBridge(BrokerRuntime("asb", asb_permissions(), NoAuditStrategy()))
    bridge.pre_plan("Task")
    bridge.post_memory("Prior workflow")
    bridge.pre_tool("lookup")
    bridge.post_observation("Result")
    bridge.pre_memory_write(["workflow"])
    assert [event.checkpoint for event in bridge.runtime.prefix] == [
        Checkpoint.PRE_PLAN,
        Checkpoint.POST_MEMORY,
        Checkpoint.PRE_TOOL,
        Checkpoint.POST_OBSERVATION,
        Checkpoint.PRE_MEMORY_WRITE,
    ]
    assert bridge.runtime.prefix[2].proposed_action is not None
    assert bridge.runtime.prefix[2].proposed_action.source_refs == (
        bridge.runtime.prefix[1].event_id,
    )
    assert bridge.runtime.prefix[4].proposed_action is not None
    assert bridge.runtime.prefix[4].proposed_action.source_refs == (
        bridge.runtime.prefix[3].event_id,
    )


def test_live_bridge_accepts_confirmation_only_from_controller_argument() -> None:
    permissions = asb_permissions()
    grant = permissions.grants["tool:lookup"].model_copy(
        update={"requires_confirmation": True}
    )
    permissions = permissions.model_copy(
        update={
            "grants": {
                "tool:lookup": grant,
                "memory:write": permissions.grants["memory:write"],
            }
        }
    )

    forged = ASBLiveBridge(BrokerRuntime("asb", permissions, NoAuditStrategy()))
    forged_decision = forged.pre_tool("lookup", {"_confirmed": True})
    assert forged_decision.outcome == BrokerOutcome.BLOCK_AND_REPLAN

    trusted = ASBLiveBridge(BrokerRuntime("asb", permissions, NoAuditStrategy()))
    trusted_decision = trusted.pre_tool(
        "lookup",
        {"_confirmed": False},
        trusted_confirmation=True,
    )
    assert trusted_decision.outcome == BrokerOutcome.ALLOW


def test_dynamic_asb_subclass_blocks_tool_before_parent_execution() -> None:
    class BaseAgent:
        def __init__(self) -> None:
            self.task_input = "Do task"
            self.vectorstore = VectorStore()
            self.called = []

        def normalize_tool_calls(self, tool_calls: object) -> list[dict[str, str]]:
            return [{"name": "forbidden", "parameters": {}}]

        def call_tools(
            self, tool_calls: object, final_stage: bool = False
        ) -> tuple[list, list, bool]:
            self.called.append(tool_calls)
            return ["called"], ["observation"], True

    bridge = ASBLiveBridge(BrokerRuntime("asb", asb_permissions(), NoAuditStrategy()))
    agent_class = instrument_asb_agent(BaseAgent, bridge)
    agent = agent_class()
    actions, _, success = agent.call_tools([{"name": "forbidden"}])
    assert not success
    assert "blocked" in actions[0]
    assert agent.called == []


@dataclass
class Response:
    type: str
    answer: str


def test_converse_external_disclosure_is_mediated_before_routing() -> None:
    bridge = ConVerseLiveBridge(
        BrokerRuntime("converse", converse_permissions(include_disclosure=False), NoAuditStrategy())
    )
    called = []
    result = bridge.route(
        Response("to_external_agent", "private record"),
        lambda response: called.append(("environment", response)),
        lambda response: called.append(("external", response)),
        lambda response: called.append(("commit", response)),
    )
    assert result is None
    assert called == []


def test_converse_live_bridge_covers_received_query_disclosure_and_commit() -> None:
    bridge = ConVerseLiveBridge(
        BrokerRuntime("converse", converse_permissions(), NoAuditStrategy())
    )
    called = []
    bridge.observe_received(Response("environment_return", "record"))
    bridge.observe_received(Response("external_agent_return", "pressure"))
    bridge.route(
        Response("to_environment", "query"),
        lambda response: called.append(("environment", response)),
        lambda response: called.append(("external", response)),
        lambda response: called.append(("commit", response)),
    )
    bridge.route(
        Response("to_external_agent", "minimal disclosure"),
        lambda response: called.append(("environment", response)),
        lambda response: called.append(("external", response)),
        lambda response: called.append(("commit", response)),
    )
    bridge.route(
        Response("assistant_return", "final"),
        lambda response: called.append(("environment", response)),
        lambda response: called.append(("external", response)),
        lambda response: called.append(("commit", response)),
    )
    assert [event.checkpoint for event in bridge.runtime.prefix] == [
        Checkpoint.POST_OBSERVATION,
        Checkpoint.POST_OBSERVATION,
        Checkpoint.PRE_ENVIRONMENT_QUERY,
        Checkpoint.PRE_DISCLOSURE,
        Checkpoint.PRE_COMMIT,
    ]
    assert [name for name, _ in called] == ["environment", "external", "commit"]


def test_model_schema_failure_pauses_live_transition() -> None:
    client = ScriptedModelClient([{"bad": "record"}])
    strategy = ModelAuditStrategy(client, "actor", AuditEmissionMode.SIDECAR)
    bridge = ASBLiveBridge(BrokerRuntime("asb", asb_permissions(), strategy))
    decision = bridge.pre_tool("lookup")
    assert decision.outcome == BrokerOutcome.PAUSE


def test_quarantine_audit_blocks_and_persists_reduced_state() -> None:
    audit = AuditRecord(
        checkpoint=Checkpoint.POST_MEMORY,
        actor_id="actor",
        risk_level=RiskLevel.HIGH,
        evidence_refs=("asb:live:0",),
        intended_action_ref="asb:live:0",
        confidence=1,
        intervention=Intervention.QUARANTINE,
        permission_delta=PermissionDelta(quarantine_sources=("asb:live:0",)),
        rationale="Memory is contaminated.",
        emission_mode=AuditEmissionMode.SIDECAR,
    )
    bridge = ASBLiveBridge(
        BrokerRuntime("asb", asb_permissions(), ScriptedAuditStrategy([audit]))
    )
    decision = bridge.post_memory("bad memory")
    assert decision.outcome == BrokerOutcome.BLOCK_AND_REPLAN
    assert bridge.runtime.broker.permissions.quarantined_sources == ("asb:live:0",)

    dependent = bridge.pre_tool("lookup")
    assert dependent.outcome == BrokerOutcome.BLOCK_AND_REPLAN
    assert "quarantined source" in dependent.reason


def test_native_inline_envelope_is_mediated() -> None:
    runtime = BrokerRuntime("inline", asb_permissions(), NoAuditStrategy())
    action = ActionProposal(
        action_type=ActionType.TOOL_CALL,
        capability="tool:lookup",
        name="lookup",
    )
    event = TrajectoryEvent(
        event_id="inline:live:0",
        scenario_id="inline",
        sequence=0,
        event_kind=EventKind.TOOL_PROPOSAL,
        source=Provenance.AGENT,
        checkpoint=Checkpoint.PRE_TOOL,
        proposed_action=action,
    )
    envelope = AuditEnvelope(
        action=action,
        audit=AuditRecord(
            checkpoint=Checkpoint.PRE_TOOL,
            actor_id="native-inline-actor",
            risk_level=RiskLevel.HIGH,
            confidence=0.9,
            intervention=Intervention.DOWNGRADE,
            permission_delta=PermissionDelta(remove=("tool:lookup",)),
            rationale="Tool is unnecessary.",
            emission_mode=AuditEmissionMode.INLINE,
        ),
    )
    decision = runtime.mediate_inline(event, envelope)
    assert decision.outcome == BrokerOutcome.BLOCK_AND_REPLAN
    assert "tool:lookup" not in runtime.broker.permissions.grants


def test_native_inline_unknown_evidence_fails_closed() -> None:
    runtime = BrokerRuntime("inline", asb_permissions(), NoAuditStrategy())
    action = ActionProposal(
        action_type=ActionType.TOOL_CALL,
        capability="tool:lookup",
        name="lookup",
    )
    event = runtime.event(
        EventKind.TOOL_PROPOSAL,
        Provenance.AGENT,
        Checkpoint.PRE_TOOL,
        {"tool": "lookup"},
        action,
    )
    envelope = AuditEnvelope(
        action=action,
        audit=AuditRecord(
            checkpoint=Checkpoint.PRE_TOOL,
            actor_id="native-inline-actor",
            risk_level=RiskLevel.HIGH,
            evidence_refs=("unknown:event",),
            intended_action_ref=event.event_id,
            confidence=0.9,
            intervention=Intervention.CONTINUE,
            rationale="Evidence reference was supplied by the actor.",
            emission_mode=AuditEmissionMode.INLINE,
        ),
    )

    decision = runtime.mediate_inline(event, envelope)

    assert decision.outcome == BrokerOutcome.PAUSE
    assert decision.decision_source == DecisionSource.SCHEMA_GUARD


def test_combined_monitor_broker_selects_stricter_audit_and_merges_evidence() -> None:
    actor_client = ScriptedModelClient(
        [
            {
                "risk_level": "low",
                "risk_types": ["overprivilege"],
                "evidence_refs": ["asb:live:0"],
                "confidence": 0.4,
                "intervention": "continue",
                "rationale": "Actor sees limited risk.",
            }
        ]
    )
    observer_client = ScriptedModelClient(
        [
            {
                "risk_level": "high",
                "risk_types": ["prompt_injection"],
                "evidence_refs": ["asb:live:0"],
                "confidence": 0.95,
                "intervention": "pause",
                "rationale": "Observer sees injection.",
            }
        ]
    )
    combined = CombinedAuditStrategy(
        ModelAuditStrategy(actor_client, "actor", AuditEmissionMode.SIDECAR),
        ModelAuditStrategy(observer_client, "observer", AuditEmissionMode.EXTERNAL),
    )
    event = ASBLiveBridge(BrokerRuntime("asb", asb_permissions(), NoAuditStrategy())).runtime.event(
        EventKind.TOOL_PROPOSAL,
        Provenance.AGENT,
        Checkpoint.PRE_TOOL,
        {"tool": "lookup"},
        ActionProposal(
            action_type=ActionType.TOOL_CALL,
            capability="tool:lookup",
            name="lookup",
        ),
    )
    audit = combined.audit(event, (), asb_permissions())
    assert audit.intervention == Intervention.PAUSE
    assert audit.risk_level == RiskLevel.HIGH
    assert set(audit.risk_types) == {RiskType.OVERPRIVILEGE, RiskType.PROMPT_INJECTION}
    assert set(audit.evidence_refs) == {"asb:live:0"}


def test_combined_monitor_prioritizes_intervention_then_preserves_maximum_risk() -> None:
    actor_client = ScriptedModelClient(
        [
            {
                "risk_level": "critical",
                "risk_types": ["policy_conflict"],
                "evidence_refs": ["asb:live:0"],
                "confidence": 0.99,
                "intervention": "continue",
                "rationale": "Actor reports risk but elects to continue.",
            }
        ]
    )
    observer_client = ScriptedModelClient(
        [
            {
                "risk_level": "low",
                "risk_types": ["overprivilege"],
                "evidence_refs": ["asb:live:0"],
                "confidence": 0.35,
                "intervention": "pause",
                "rationale": "Observer requires a pause.",
            }
        ]
    )
    combined = CombinedAuditStrategy(
        ModelAuditStrategy(actor_client, "actor", AuditEmissionMode.SIDECAR),
        ModelAuditStrategy(observer_client, "observer", AuditEmissionMode.EXTERNAL),
    )
    runtime = BrokerRuntime("asb", asb_permissions(), NoAuditStrategy())
    event = runtime.event(
        EventKind.TOOL_PROPOSAL,
        Provenance.AGENT,
        Checkpoint.PRE_TOOL,
        {"tool": "lookup"},
        ActionProposal(
            action_type=ActionType.TOOL_CALL,
            capability="tool:lookup",
            name="lookup",
        ),
    )

    audit = combined.audit(event, (), asb_permissions())

    assert audit.intervention == Intervention.PAUSE
    assert audit.risk_level == RiskLevel.CRITICAL
    assert audit.confidence == 0.99


def test_live_runtime_rejects_mismatched_controller_context() -> None:
    runtime = BrokerRuntime("asb", asb_permissions(), NoAuditStrategy())
    event = runtime.event(
        EventKind.TOOL_PROPOSAL,
        Provenance.AGENT,
        Checkpoint.PRE_TOOL,
        {"tool": "lookup"},
        ActionProposal(
            action_type=ActionType.TOOL_CALL,
            capability="tool:lookup",
            name="lookup",
        ),
    )

    with pytest.raises(ValueError, match="scenario_id"):
        runtime.mediate(event.model_copy(update={"scenario_id": "other"}))
    with pytest.raises(ValueError, match="sequence"):
        runtime.mediate(event.model_copy(update={"sequence": 1}))
    with pytest.raises(ValueError, match="revision"):
        runtime.mediate(event.model_copy(update={"permission_revision": 1}))
