"""Extension protocols for actors, adapters, rules, bridges, and metrics."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Literal, Protocol

from selfauditbench.core.models import (
    ActionExecution,
    ActionProposal,
    AuditRecord,
    BrokerDecision,
    ControllerFeedback,
    OutcomeJudgment,
    PermissionState,
    RecoveryTurn,
    Scenario,
    ScenarioResult,
    TrajectoryEvent,
)


class AuditStrategy(Protocol):
    strategy_id: str

    def audit(
        self,
        event: TrajectoryEvent,
        prefix: Sequence[TrajectoryEvent],
        permissions: PermissionState,
    ) -> AuditRecord | None: ...


class ScenarioAdapter(Protocol):
    source_dataset: str

    def load(self, source: Path) -> Iterable[Scenario]: ...


class LiveBridge(Protocol):
    def mediate(self, event: TrajectoryEvent) -> BrokerDecision: ...


class ModelClient(Protocol):
    def complete_text(
        self,
        messages: Sequence[dict[str, str]],
        *,
        json_mode: bool = True,
        max_tokens_override: int | None = None,
    ) -> str: ...

    def last_call_usage(self) -> dict[str, Any]: ...

    def preflight(self) -> None: ...

    def complete_json(self, messages: Sequence[dict[str, str]]) -> dict[str, Any]: ...


class PolicyRule(Protocol):
    def evaluate(self, event: TrajectoryEvent, permissions: PermissionState) -> Iterable[str]: ...


class Metric(Protocol):
    name: str

    def compute(
        self, results: Sequence[ScenarioResult], scenarios: Sequence[Scenario]
    ) -> float: ...


class RecoveryActor(Protocol):
    def propose(
        self,
        *,
        scenario: Scenario,
        event_id: str,
        turn_index: int,
        prefix: Sequence[TrajectoryEvent],
        permissions: PermissionState,
        feedback: Sequence[ControllerFeedback],
    ) -> RecoveryTurn: ...


class OutcomeJudge(Protocol):
    def judge(
        self,
        *,
        scenario: Scenario,
        executions: Sequence[ActionExecution],
        feedback: Sequence[ControllerFeedback],
    ) -> OutcomeJudgment: ...


class ActionSink(Protocol):
    sink_id: str

    def execute(
        self,
        *,
        scenario: Scenario,
        event_id: str,
        action: ActionProposal,
        turn_index: int | None,
        source: Literal["recorded", "actor"],
        permission_revision: int,
        origin_sequence: int | None = None,
    ) -> ActionExecution: ...
