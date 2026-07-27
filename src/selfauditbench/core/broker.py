"""Deterministic external broker for monotonic agent self-restriction."""

from __future__ import annotations

from collections.abc import Iterable

from selfauditbench.core.models import (
    AuditRecord,
    BrokerDecision,
    BrokerOutcome,
    DecisionSource,
    Intervention,
    PermissionDelta,
    PermissionState,
    TrajectoryEvent,
)
from selfauditbench.core.permissions import (
    PermissionDeltaError,
    action_violations,
    apply_delta,
    consume_action,
)
from selfauditbench.core.protocols import PolicyRule

REPLAN_INTERVENTIONS = {
    Intervention.SANITIZE,
    Intervention.REVERIFY,
    Intervention.DOWNGRADE,
    Intervention.QUARANTINE,
}
SCHEMA_GUARD_ACTOR_ID = "selfauditbench-schema-guard"


class PolicyBroker:
    """Apply actor-requested downgrades and enforce the resulting permissions."""

    def __init__(
        self,
        initial_permissions: PermissionState,
        rules: Iterable[PolicyRule] = (),
    ) -> None:
        self._permissions = initial_permissions
        self._rules = tuple(rules)

    @property
    def permissions(self) -> PermissionState:
        return self._permissions

    def mediate(
        self,
        event: TrajectoryEvent,
        audit: AuditRecord | None = None,
        *,
        trusted_confirmation: bool = False,
    ) -> BrokerDecision:
        before = self._permissions
        delta = audit.permission_delta if audit is not None else PermissionDelta()

        if audit is not None and event.checkpoint != audit.checkpoint:
            return self._blocked(
                event,
                before,
                before,
                requested_delta=delta,
                applied_delta=PermissionDelta(),
                violations=("audit checkpoint does not match event checkpoint",),
                decision_source=DecisionSource.MONOTONICITY_REJECTION,
            )
        if (
            audit is not None
            and audit.intended_action_ref is not None
            and audit.intended_action_ref != event.event_id
        ):
            return self._blocked(
                event,
                before,
                before,
                requested_delta=delta,
                applied_delta=PermissionDelta(),
                violations=("audit intended action does not match event",),
                decision_source=DecisionSource.MONOTONICITY_REJECTION,
            )
        if audit is not None and not set(delta.quarantine_sources) <= set(
            audit.evidence_refs
        ):
            return self._blocked(
                event,
                before,
                before,
                requested_delta=delta,
                applied_delta=PermissionDelta(),
                violations=("quarantined sources must be cited as audit evidence",),
                decision_source=DecisionSource.MONOTONICITY_REJECTION,
            )

        try:
            after_delta = apply_delta(before, delta)
        except PermissionDeltaError as exc:
            return self._blocked(
                event,
                before,
                before,
                requested_delta=delta,
                applied_delta=PermissionDelta(),
                violations=(str(exc),),
                decision_source=DecisionSource.MONOTONICITY_REJECTION,
            )

        self._permissions = after_delta
        if audit is not None:
            if audit.intervention == Intervention.REFUSE:
                return self._decision(
                    event,
                    BrokerOutcome.REFUSE,
                    before,
                    after_delta,
                    requested_delta=delta,
                    applied_delta=delta,
                    decision_source=_audit_decision_source(audit),
                )
            if audit.intervention in {Intervention.PAUSE, Intervention.ASK_USER}:
                return self._decision(
                    event,
                    BrokerOutcome.PAUSE,
                    before,
                    after_delta,
                    requested_delta=delta,
                    applied_delta=delta,
                    decision_source=_audit_decision_source(audit),
                )
            if audit.intervention in REPLAN_INTERVENTIONS:
                return self._decision(
                    event,
                    BrokerOutcome.BLOCK_AND_REPLAN,
                    before,
                    after_delta,
                    requested_delta=delta,
                    applied_delta=delta,
                    decision_source=_audit_decision_source(audit),
                )

        violations = list(
            action_violations(
                event.proposed_action,
                after_delta,
                trusted_confirmation=trusted_confirmation,
            )
        )
        for rule in self._rules:
            violations.extend(rule.evaluate(event, after_delta))
        if violations:
            return self._blocked(
                event,
                before,
                after_delta,
                requested_delta=delta,
                applied_delta=delta,
                violations=tuple(violations),
                decision_source=DecisionSource.PERMISSION_POLICY,
            )

        consumed = consume_action(after_delta, event.proposed_action)
        self._permissions = consumed
        return self._decision(
            event,
            BrokerOutcome.ALLOW,
            before,
            consumed,
            requested_delta=delta,
            applied_delta=delta,
            decision_source=DecisionSource.ALLOW,
        )

    def _blocked(
        self,
        event: TrajectoryEvent,
        before: PermissionState,
        after: PermissionState,
        *,
        requested_delta: PermissionDelta,
        applied_delta: PermissionDelta,
        violations: tuple[str, ...],
        decision_source: DecisionSource,
    ) -> BrokerDecision:
        self._permissions = after
        return BrokerDecision(
            event_id=event.event_id,
            outcome=BrokerOutcome.BLOCK_AND_REPLAN,
            decision_source=decision_source,
            reason="; ".join(violations),
            violations=violations,
            permission_before=before,
            permission_after=after,
            requested_delta=requested_delta,
            applied_delta=applied_delta,
        )

    def _decision(
        self,
        event: TrajectoryEvent,
        outcome: BrokerOutcome,
        before: PermissionState,
        after: PermissionState,
        *,
        requested_delta: PermissionDelta,
        applied_delta: PermissionDelta,
        decision_source: DecisionSource,
    ) -> BrokerDecision:
        reason = {
            BrokerOutcome.ALLOW: "proposal is permitted",
            BrokerOutcome.BLOCK_AND_REPLAN: "audit requires actor replanning",
            BrokerOutcome.PAUSE: "audit requires trusted input",
            BrokerOutcome.REFUSE: "actor refused the transition",
        }[outcome]
        return BrokerDecision(
            event_id=event.event_id,
            outcome=outcome,
            decision_source=decision_source,
            reason=reason,
            permission_before=before,
            permission_after=after,
            requested_delta=requested_delta,
            applied_delta=applied_delta,
        )


def _audit_decision_source(audit: AuditRecord) -> DecisionSource:
    if audit.actor_id == SCHEMA_GUARD_ACTOR_ID:
        return DecisionSource.SCHEMA_GUARD
    return DecisionSource.AUDIT_INTERVENTION
