"""Replay adapter for Agent Security Bench CSV artifacts."""

from __future__ import annotations

import ast
import csv
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from selfauditbench.adapters.common import REPLAY_TIMESTAMP, relative_ref, slug, stable_id
from selfauditbench.core.models import (
    ActionProposal,
    ActionType,
    CapabilityGrant,
    Checkpoint,
    EventKind,
    Intervention,
    LabelProvenance,
    PermissionState,
    Provenance,
    Scenario,
    ScenarioLabel,
    TrajectoryEvent,
)
from selfauditbench.core.sanitize import strip_hidden_reasoning

TOOL_NAME = re.compile(r'"name"\s*:\s*"([A-Za-z0-9_.-]+)"')
ACTION = re.compile(r"\[Action\]:\s*I will call the ([A-Za-z0-9_.-]+)", re.IGNORECASE)
OBSERVATION = re.compile(r"\[Observation\]:\s*(.*)", re.IGNORECASE | re.DOTALL)


class ASBReplayAdapter:
    """Normalize ASB CSV rows into observable event trajectories."""

    source_dataset = "asb"

    def load(self, source: Path) -> Iterable[Scenario]:
        root = source if source.is_dir() else source.parent
        paths = sorted(source.rglob("*.csv")) if source.is_dir() else [source]
        for path in paths:
            yield from self._load_csv(path, root)

    def _load_csv(self, path: Path, root: Path) -> Iterator[Scenario]:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row_number, row in enumerate(csv.DictReader(handle), start=2):
                yield self._scenario_from_row(path, root, row_number, row)

    def _scenario_from_row(
        self,
        path: Path,
        root: Path,
        row_number: int,
        row: dict[str, str],
    ) -> Scenario:
        raw_ref = f"{relative_ref(path, root)}#row={row_number}"
        scenario_id = stable_id("asb", raw_ref, row.get("Agent Name", "unknown"))
        messages = self._parse_messages(row.get("messages", "[]"), raw_ref)
        capabilities = self._discover_tools(messages)
        grants = {
            f"tool:{name}": CapabilityGrant(
                capability=f"tool:{name}", operations=(ActionType.TOOL_CALL.value,)
            )
            for name in sorted(capabilities)
        }
        grants["memory:write"] = CapabilityGrant(
            capability="memory:write", operations=(ActionType.MEMORY_WRITE.value,)
        )
        permissions = PermissionState(grants=grants)

        events: list[TrajectoryEvent] = []
        last_external_ref: str | None = None
        memory = row.get("Memory Found", "")
        if memory and memory not in {"N/A", "None"}:
            memory_event = self._event(
                scenario_id,
                len(events),
                EventKind.MEMORY_READ,
                Provenance.MEMORY,
                Checkpoint.POST_MEMORY,
                {"content": strip_hidden_reasoning(memory)},
                raw_ref,
            )
            events.append(memory_event)
            last_external_ref = memory_event.event_id

        for message_index, message in enumerate(messages):
            role = str(message.get("role", "unknown"))
            content = strip_hidden_reasoning(str(message.get("content", "")))
            if role == "user" and not any(
                item.event_kind == EventKind.TASK_RECEIVED for item in events
            ):
                events.append(
                    self._event(
                        scenario_id,
                        len(events),
                        EventKind.TASK_RECEIVED,
                        Provenance.USER,
                        Checkpoint.PRE_PLAN,
                        {"content": content, "message_index": message_index},
                        raw_ref,
                    )
                )
            if role != "assistant":
                continue

            action_match = ACTION.search(content)
            if action_match:
                tool_name = action_match.group(1)
                proposal_content = _proposal_content(content, action_match.start())
                action = ActionProposal(
                    action_type=ActionType.TOOL_CALL,
                    capability=f"tool:{tool_name}",
                    name=tool_name,
                    source_refs=(last_external_ref,) if last_external_ref is not None else (),
                )
                events.append(
                    self._event(
                        scenario_id,
                        len(events),
                        EventKind.TOOL_PROPOSAL,
                        Provenance.AGENT,
                        Checkpoint.PRE_TOOL,
                        {
                            "content": proposal_content,
                            "message_index": message_index,
                        },
                        raw_ref,
                        proposed_action=action,
                    )
                )

            observation_match = OBSERVATION.search(content)
            if observation_match:
                observation_event = self._event(
                    scenario_id,
                    len(events),
                    EventKind.OBSERVATION,
                    Provenance.TOOL,
                    Checkpoint.POST_OBSERVATION,
                    {"content": observation_match.group(1), "message_index": message_index},
                    raw_ref,
                )
                events.append(observation_event)
                last_external_ref = observation_event.event_id

        risky = "clean" not in {part.lower() for part in path.parts}
        attack_tool = row.get("Attack Tool", "")
        harm_boundary = self._first_tool_sequence(events, attack_tool)
        label = ScenarioLabel(
            risky=risky,
            first_risk_sufficient_event=None,
            harm_boundary_event=harm_boundary,
            accepted_interventions=(
                Intervention.REVERIFY,
                Intervention.DOWNGRADE,
                Intervention.QUARANTINE,
                Intervention.PAUSE,
                Intervention.REFUSE,
            )
            if risky
            else (),
            utility_expectation=(
                "Preserve the original task while preventing attacker-directed tools."
            ),
        )
        tags = tuple(
            sorted(
                {
                    "weak-label",
                    slug(path.parent.name),
                    slug(row.get("Agent Name", "unknown")),
                    slug(attack_tool or "no-attack-tool"),
                }
            )
        )
        return Scenario(
            scenario_id=scenario_id,
            source_dataset=self.source_dataset,
            source_ref=raw_ref,
            tags=tags,
            weak_label=True,
            label_provenance=LabelProvenance.WEAK_IMPORT,
            initial_permissions=permissions,
            events=tuple(events),
            label=label,
        )
    @staticmethod
    def _parse_messages(value: str, raw_ref: str) -> list[dict[str, Any]]:
        try:
            messages = ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"invalid ASB messages literal at {raw_ref}") from exc
        if not isinstance(messages, list) or not all(isinstance(item, dict) for item in messages):
            raise ValueError(f"ASB messages must be a list of mappings at {raw_ref}")
        return messages

    @staticmethod
    def _discover_tools(messages: list[dict[str, Any]]) -> set[str]:
        tools: set[str] = set()
        for message in messages:
            tools.update(TOOL_NAME.findall(str(message.get("content", ""))))
        return tools

    @staticmethod
    def _first_tool_sequence(events: list[TrajectoryEvent], tool_name: str) -> int | None:
        for event in events:
            if event.proposed_action is not None and event.proposed_action.name == tool_name:
                return event.sequence
        return None

    @staticmethod
    def _event(
        scenario_id: str,
        sequence: int,
        event_kind: EventKind,
        source: Provenance,
        checkpoint: Checkpoint,
        payload: dict[str, Any],
        raw_ref: str,
        proposed_action: ActionProposal | None = None,
    ) -> TrajectoryEvent:
        return TrajectoryEvent(
            event_id=f"{scenario_id}:event:{sequence}",
            scenario_id=scenario_id,
            sequence=sequence,
            event_kind=event_kind,
            source=source,
            checkpoint=checkpoint,
            visible_payload=payload,
            proposed_action=proposed_action,
            raw_artifact_ref=raw_ref,
            created_at=REPLAY_TIMESTAMP,
        )


def _proposal_content(content: str, action_start: int) -> str:
    """Return only assistant text observable before the recorded tool result."""

    observation = OBSERVATION.search(content, action_start)
    action_end = observation.start() if observation is not None else len(content)
    return content[action_start:action_end].rstrip(" \t\r\n;")
