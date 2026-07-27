"""Semantic action identity for normalized closed-loop execution."""

from __future__ import annotations

import json
from typing import Any

from selfauditbench.core.models import ActionProposal, Scenario, TrajectoryEvent

ACTION_MATCH_CONTRACT: dict[str, Any] = {
    "identity_fields": ["action_type", "capability", "name", "arguments", "content"],
    "candidate_missing_name": "recorded_name_when_unique",
    "recorded_empty_arguments": "actor_supplied",
    "recorded_nonempty_arguments": "exact",
    "recorded_empty_content": "actor_supplied",
    "recorded_nonempty_content": "exact",
    "catalog_scope": "supported_transitions_without_outcomes",
    "broker_validates_complete_proposal": True,
    "repeated_completed_transition": "one_repair_then_actor_stalled",
}


def action_semantics(action: ActionProposal) -> dict[str, Any]:
    """Return the fields that identify an enacted normalized transition."""

    return {
        "action_type": action.action_type.value,
        "capability": action.capability,
        "name": action.name,
        "arguments": action.arguments,
        "content": action.content,
    }


def action_matches_recorded_transition(
    candidate: ActionProposal,
    recorded: ActionProposal,
) -> bool:
    """Match a fresh proposal to a recorded transition without provenance metadata.

    Source adapters sometimes preserve empty arguments or content. Those empty fields do
    not constrain a fresh proposal. A missing candidate name is resolved separately only
    when all matching source transitions imply one recorded name.
    """

    candidate_fields = action_semantics(candidate)
    recorded_fields = action_semantics(recorded)
    for field in ("action_type", "capability"):
        if candidate_fields[field] != recorded_fields[field]:
            return False
    if candidate.name is not None and candidate.name != recorded.name:
        return False
    if recorded.content not in {None, ""} and candidate.content != recorded.content:
        return False
    return not recorded.arguments or candidate.arguments == recorded.arguments


def normalized_action_catalog(scenario: Scenario) -> list[dict[str, Any]]:
    """List the operational transitions supported by the normalized action sink."""

    catalog: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in scenario.events:
        action = event.proposed_action
        if action is None:
            continue
        entry = action_semantics(action)
        entry["arguments_policy"] = "exact" if action.arguments else "actor_supplied"
        entry["content_policy"] = (
            "exact" if action.content not in {None, ""} else "actor_supplied"
        )
        key = json.dumps(entry, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        catalog.append(entry)
    return catalog


def action_is_catalogued(candidate: ActionProposal, scenario: Scenario) -> bool:
    """Return whether the sink can resolve an operational proposal in this scenario."""

    matches = _matching_recorded_actions(candidate, scenario)
    return bool(matches) and _missing_name_is_unambiguous(candidate, matches)


def matching_recorded_event_ids(
    candidate: ActionProposal,
    scenario: Scenario,
) -> set[str]:
    """Return recorded transitions that the sink can resolve for a proposal."""

    matches = _matching_recorded_actions(candidate, scenario)
    if not _missing_name_is_unambiguous(candidate, matches):
        return set()
    return {event.event_id for event in matches}


def closest_catalog_mismatch_fields(
    candidate: ActionProposal,
    scenario: Scenario,
) -> tuple[str, ...]:
    """Describe the smallest exact-policy mismatch for a repair prompt."""

    matches = _matching_recorded_actions(candidate, scenario)
    if matches and not _missing_name_is_unambiguous(candidate, matches):
        return ("name",)
    candidates = [
        _action_mismatch_fields(candidate, event.proposed_action)
        for event in scenario.events
        if event.proposed_action is not None
    ]
    return min(candidates, key=len) if candidates else ("catalog_empty",)


def _matching_recorded_actions(
    candidate: ActionProposal,
    scenario: Scenario,
) -> list[TrajectoryEvent]:
    return [
        event
        for event in scenario.events
        if event.proposed_action is not None
        and action_matches_recorded_transition(candidate, event.proposed_action)
    ]


def _action_mismatch_fields(
    candidate: ActionProposal,
    recorded: ActionProposal,
) -> tuple[str, ...]:
    mismatches: list[str] = []
    if candidate.action_type != recorded.action_type:
        mismatches.append("action_type")
    if candidate.capability != recorded.capability:
        mismatches.append("capability")
    if candidate.name is not None and candidate.name != recorded.name:
        mismatches.append("name")
    if recorded.arguments and candidate.arguments != recorded.arguments:
        mismatches.append("arguments")
    if recorded.content not in {None, ""} and candidate.content != recorded.content:
        mismatches.append("content")
    return tuple(mismatches)


def _missing_name_is_unambiguous(
    candidate: ActionProposal,
    matches: list[TrajectoryEvent],
) -> bool:
    if candidate.name is not None:
        return True
    recorded_names = {
        event.proposed_action.name
        for event in matches
        if event.proposed_action is not None
    }
    return len(recorded_names) == 1
