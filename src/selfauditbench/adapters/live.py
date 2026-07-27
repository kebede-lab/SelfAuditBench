"""Live mediation without modifying reproduced benchmark snapshots."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from selfauditbench.actors.strategies import fail_closed_audit
from selfauditbench.core.broker import PolicyBroker
from selfauditbench.core.models import (
    ActionProposal,
    ActionType,
    AuditEnvelope,
    AuditRecord,
    BrokerDecision,
    BrokerOutcome,
    Checkpoint,
    EventKind,
    PermissionState,
    Provenance,
    Sensitivity,
    TrajectoryEvent,
)
from selfauditbench.core.protocols import AuditStrategy
from selfauditbench.core.sanitize import sanitize_payload, strip_hidden_reasoning
from selfauditbench.storage.artifacts import ArtifactStore

T = TypeVar("T")


class BrokerRuntime:
    """Stateful live checkpoint mediator shared by supported bridges."""

    def __init__(
        self,
        scenario_id: str,
        initial_permissions: PermissionState,
        audit_strategy: AuditStrategy,
        artifacts: ArtifactStore | None = None,
        fail_closed: bool = True,
    ) -> None:
        self.scenario_id = scenario_id
        self.broker = PolicyBroker(initial_permissions)
        self.audit_strategy = audit_strategy
        self.artifacts = artifacts
        self.fail_closed = fail_closed
        self.prefix: list[TrajectoryEvent] = []

    def event(
        self,
        kind: EventKind,
        source: Provenance,
        checkpoint: Checkpoint,
        payload: dict[str, Any],
        action: ActionProposal | None = None,
    ) -> TrajectoryEvent:
        sequence = len(self.prefix)
        if action is not None:
            action = action.model_copy(
                update={
                    "source_refs": tuple(
                        sorted(set(action.source_refs) | set(self.recent_external_source_refs()))
                    )
                }
            )
        return TrajectoryEvent(
            event_id=f"{self.scenario_id}:live:{sequence}",
            scenario_id=self.scenario_id,
            sequence=sequence,
            event_kind=kind,
            source=source,
            checkpoint=checkpoint,
            visible_payload=sanitize_payload(payload),
            proposed_action=action,
            permission_revision=self.broker.permissions.revision,
            created_at=datetime.now(UTC),
        )

    def mediate(
        self,
        event: TrajectoryEvent,
        *,
        trusted_confirmation: bool = False,
    ) -> BrokerDecision:
        self._validate_event_context(event)
        audit = None
        try:
            audit = self.audit_strategy.audit(event, tuple(self.prefix), self.broker.permissions)
            audit = self._bind_audit_context(event, audit)
        except Exception as exc:
            if not self.fail_closed:
                raise
            audit = fail_closed_audit(event, str(exc))
        return self._record(event, audit, trusted_confirmation=trusted_confirmation)

    def mediate_inline(
        self,
        event: TrajectoryEvent,
        envelope: AuditEnvelope,
        *,
        trusted_confirmation: bool = False,
    ) -> BrokerDecision:
        """Mediate a native action-plus-audit envelope from an instrumented actor."""

        self._validate_event_context(event)
        if event.proposed_action is not None and event.proposed_action != envelope.action:
            raise ValueError("inline envelope action does not match the checkpoint event")
        bound_action = envelope.action.model_copy(
            update={
                "source_refs": tuple(
                    sorted(
                        set(envelope.action.source_refs)
                        | set(self.recent_external_source_refs())
                    )
                )
            }
        )
        event_with_action = event.model_copy(update={"proposed_action": bound_action})
        try:
            audit = self._bind_audit_context(event_with_action, envelope.audit)
        except Exception as exc:
            if not self.fail_closed:
                raise
            audit = fail_closed_audit(event_with_action, str(exc))
        return self._record(
            event_with_action,
            audit,
            trusted_confirmation=trusted_confirmation,
        )

    def recent_external_source_refs(self) -> tuple[str, ...]:
        """Return the latest controller-observed untrusted input dependency."""

        external_sources = {
            Provenance.MEMORY,
            Provenance.TOOL,
            Provenance.ENVIRONMENT,
            Provenance.EXTERNAL_AGENT,
        }
        for event in reversed(self.prefix):
            if event.source in external_sources:
                return (event.event_id,)
        return ()

    def _record(
        self,
        event: TrajectoryEvent,
        audit: AuditRecord | None,
        *,
        trusted_confirmation: bool = False,
    ) -> BrokerDecision:
        self._validate_event_context(event)
        audit = self._bind_audit_context(event, audit)
        decision = self.broker.mediate(
            event,
            audit,
            trusted_confirmation=trusted_confirmation,
        )
        self.prefix.append(event)
        if self.artifacts is not None:
            self.artifacts.record_event(event)
            if audit is not None:
                self.artifacts.record_audit(audit)
            self.artifacts.record_decision(decision)
        return decision

    def _validate_event_context(self, event: TrajectoryEvent) -> None:
        if event.scenario_id != self.scenario_id:
            raise ValueError("live event scenario_id does not match the broker runtime")
        if event.sequence != len(self.prefix):
            raise ValueError("live event sequence does not match the broker runtime")
        if event.permission_revision != self.broker.permissions.revision:
            raise ValueError("live event permission revision is stale")
        if any(item.event_id == event.event_id for item in self.prefix):
            raise ValueError("live event_id has already been mediated")

    def _bind_audit_context(
        self,
        event: TrajectoryEvent,
        audit: AuditRecord | None,
    ) -> AuditRecord | None:
        if audit is None:
            return None
        if audit.checkpoint != event.checkpoint:
            raise ValueError("audit checkpoint does not match the live event")
        if audit.intended_action_ref not in {None, event.event_id}:
            raise ValueError("audit intended_action_ref does not match the live event")
        known_event_ids = {item.event_id for item in self.prefix} | {event.event_id}
        unknown_evidence = set(audit.evidence_refs) - known_event_ids
        if unknown_evidence:
            raise ValueError("audit evidence_refs contain unknown live event IDs")
        quarantined = set(audit.permission_delta.quarantine_sources)
        if not quarantined <= set(audit.evidence_refs):
            raise ValueError("quarantined sources must be cited as audit evidence")
        if not quarantined <= known_event_ids:
            raise ValueError("audit attempts to quarantine an unknown live event")
        return audit.model_copy(update={"intended_action_ref": event.event_id})


class ASBLiveBridge:
    """Checkpoint constructors for an immutable ASB runtime integration."""

    def __init__(self, runtime: BrokerRuntime) -> None:
        self.runtime = runtime

    def pre_plan(self, task: str) -> BrokerDecision:
        return self.runtime.mediate(
            self.runtime.event(
                EventKind.PLAN_PROPOSAL,
                Provenance.AGENT,
                Checkpoint.PRE_PLAN,
                {"task": task},
            )
        )

    def post_memory(self, memory: str) -> BrokerDecision:
        return self.runtime.mediate(
            self.runtime.event(
                EventKind.MEMORY_READ,
                Provenance.MEMORY,
                Checkpoint.POST_MEMORY,
                {"content": strip_hidden_reasoning(memory)},
            )
        )

    def pre_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        trusted_confirmation: bool = False,
    ) -> BrokerDecision:
        action = ActionProposal(
            action_type=ActionType.TOOL_CALL,
            capability=f"tool:{name}",
            name=name,
            arguments=arguments or {},
        )
        return self.runtime.mediate(
            self.runtime.event(
                EventKind.TOOL_PROPOSAL,
                Provenance.AGENT,
                Checkpoint.PRE_TOOL,
                {"tool": name, "arguments": arguments or {}},
                action,
            ),
            trusted_confirmation=trusted_confirmation,
        )

    def post_observation(self, observation: str) -> BrokerDecision:
        return self.runtime.mediate(
            self.runtime.event(
                EventKind.OBSERVATION,
                Provenance.TOOL,
                Checkpoint.POST_OBSERVATION,
                {"content": strip_hidden_reasoning(observation)},
            )
        )

    def pre_memory_write(
        self,
        documents: Any,
        *,
        trusted_confirmation: bool = False,
    ) -> BrokerDecision:
        action = ActionProposal(
            action_type=ActionType.MEMORY_WRITE,
            capability="memory:write",
            name="vectorstore.add_documents",
        )
        return self.runtime.mediate(
            self.runtime.event(
                EventKind.MEMORY_WRITE_PROPOSAL,
                Provenance.AGENT,
                Checkpoint.PRE_MEMORY_WRITE,
                {"documents": sanitize_payload(str(documents))},
                action,
            ),
            trusted_confirmation=trusted_confirmation,
        )

    def wrap_vectorstore(self, vectorstore: T) -> ASBVectorStoreBridge:
        return ASBVectorStoreBridge(vectorstore, self)


class ASBVectorStoreBridge:
    """Proxy Chroma writes through a pre-memory-write checkpoint."""

    def __init__(self, vectorstore: Any, bridge: ASBLiveBridge) -> None:
        self._vectorstore = vectorstore
        self._bridge = bridge

    def add_documents(self, documents: Any, *args: Any, **kwargs: Any) -> Any:
        decision = self._bridge.pre_memory_write(documents)
        if decision.outcome != BrokerOutcome.ALLOW:
            return []
        return self._vectorstore.add_documents(*args, documents=documents, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._vectorstore, name)


def instrument_asb_agent(base_agent_class: type[T], bridge: ASBLiveBridge) -> type[T]:
    """Create an ASB subclass with mediated checkpoints and no snapshot edits."""

    class InstrumentedASBAgent(base_agent_class):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            bridge.pre_plan(str(self.task_input))
            vectorstore = getattr(self, "vectorstore", None)
            if vectorstore is not None:
                self.vectorstore = bridge.wrap_vectorstore(vectorstore)

        def search_memory_instruction(self) -> str:
            instruction = super().search_memory_instruction()
            decision = bridge.post_memory(str(self.memory_found or instruction))
            if decision.outcome != BrokerOutcome.ALLOW:
                return "Retrieved memory was quarantined. Generate a fresh workflow."
            return str(instruction)

        def call_tools(self, tool_calls: Any, final_stage: bool = False) -> Any:
            normalized = self.normalize_tool_calls(tool_calls)
            allowed = []
            for tool_call in normalized:
                decision = bridge.pre_tool(
                    str(tool_call.get("name", "")),
                    tool_call.get("parameters") if isinstance(tool_call, dict) else None,
                )
                if decision.outcome == BrokerOutcome.ALLOW:
                    allowed.append(tool_call)
            if not allowed:
                return (
                    ["SelfAuditBench blocked the proposed tool call."],
                    ["The broker requires replanning under reduced permissions."],
                    False,
                )
            actions, observations, success = super().call_tools(allowed, final_stage=final_stage)
            for observation in observations:
                bridge.post_observation(str(observation))
            return actions, observations, success

    InstrumentedASBAgent.__name__ = f"SelfAudit{base_agent_class.__name__}"
    return InstrumentedASBAgent


class ConVerseLiveBridge:
    """Mediate ConVerse responses before the outer runner routes them."""

    def __init__(self, runtime: BrokerRuntime) -> None:
        self.runtime = runtime

    def observe_received(self, response: Any) -> BrokerDecision | None:
        if response is None or response.type not in {"environment_return", "external_agent_return"}:
            return None
        source = (
            Provenance.ENVIRONMENT
            if response.type == "environment_return"
            else Provenance.EXTERNAL_AGENT
        )
        return self.runtime.mediate(
            self.runtime.event(
                EventKind.OBSERVATION,
                source,
                Checkpoint.POST_OBSERVATION,
                {"content": strip_hidden_reasoning(str(response.answer))},
            )
        )

    def mediate_response(
        self,
        response: Any,
        *,
        trusted_confirmation: bool = False,
    ) -> BrokerDecision:
        content = strip_hidden_reasoning(str(response.answer))
        if response.type == "to_environment":
            kind = EventKind.ENVIRONMENT_QUERY
            checkpoint = Checkpoint.PRE_ENVIRONMENT_QUERY
            action = ActionProposal(
                action_type=ActionType.ENVIRONMENT_QUERY,
                capability="environment:query",
                name="environment_query",
                content=content,
                sensitivity=Sensitivity.PERSONAL,
            )
        elif response.type == "to_external_agent":
            kind = EventKind.DISCLOSURE_PROPOSAL
            checkpoint = Checkpoint.PRE_DISCLOSURE
            action = ActionProposal(
                action_type=ActionType.DISCLOSURE,
                capability="disclosure:external_agent",
                name="external_agent_message",
                content=content,
                sensitivity=Sensitivity.PERSONAL,
            )
        elif response.type == "assistant_return":
            kind = EventKind.COMMIT_PROPOSAL
            checkpoint = Checkpoint.PRE_COMMIT
            action = ActionProposal(
                action_type=ActionType.COMMIT,
                capability="commit:final",
                name="final_commit",
                content=content,
                irreversible=True,
            )
        else:
            raise ValueError(f"unsupported ConVerse assistant response type {response.type!r}")
        return self.runtime.mediate(
            self.runtime.event(kind, Provenance.AGENT, checkpoint, {"content": content}, action),
            trusted_confirmation=trusted_confirmation,
        )

    def route(
        self,
        response: Any,
        to_environment: Callable[[Any], T],
        to_external_agent: Callable[[Any], T],
        on_commit: Callable[[Any], T],
        *,
        trusted_confirmation: bool = False,
    ) -> T | None:
        decision = self.mediate_response(
            response,
            trusted_confirmation=trusted_confirmation,
        )
        if decision.outcome != BrokerOutcome.ALLOW:
            return None
        if response.type == "to_environment":
            return to_environment(response)
        if response.type == "to_external_agent":
            return to_external_agent(response)
        return on_commit(response)
