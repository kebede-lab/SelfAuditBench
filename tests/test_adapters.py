from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from selfauditbench.adapters.asb import ASBReplayAdapter
from selfauditbench.adapters.converse import ConVerseReplayAdapter
from selfauditbench.adapters.io import write_scenarios
from selfauditbench.core.models import Checkpoint, EventKind, LabelProvenance


def test_asb_adapter_decodes_literal_and_removes_hidden_reasoning(tmp_path: Path) -> None:
    path = tmp_path / "direct_prompt_injection" / "naive-full.csv"
    path.parent.mkdir()
    messages = [
        {
            "role": "system",
            "content": 'tools: [{"name": "lookup"}]',
        },
        {"role": "user", "content": "Find weather."},
        {
            "role": "assistant",
            "content": (
                "[Thinking]: private plan;"
                "[Action]: I will call the lookup with the params as None;"
                "[Observation]: public result"
            ),
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["Agent Name", "Attack Tool", "Memory Found", "messages"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "Agent Name": "weather",
                "Attack Tool": "lookup",
                "Memory Found": "Previously retrieved workflow",
                "messages": repr(messages),
            }
        )

    scenario = list(ASBReplayAdapter().load(path))[0]
    kinds = [event.event_kind for event in scenario.events]
    assert EventKind.TOOL_PROPOSAL in kinds
    assert EventKind.OBSERVATION in kinds
    assert "private plan" not in json.dumps(scenario.model_dump(mode="json"))
    assert scenario.label_provenance == LabelProvenance.WEAK_IMPORT
    assert "tool:lookup" in scenario.initial_permissions.grants
    memory_event = next(
        event for event in scenario.events if event.event_kind == EventKind.MEMORY_READ
    )
    tool_event = next(
        event for event in scenario.events if event.event_kind == EventKind.TOOL_PROPOSAL
    )
    assert tool_event.proposed_action is not None
    assert tool_event.proposed_action.source_refs == (memory_event.event_id,)
    assert tool_event.visible_payload["content"] == (
        "[Action]: I will call the lookup with the params as None"
    )
    assert "Observation" not in tool_event.visible_payload["content"]
    observation_event = next(
        event for event in scenario.events if event.event_kind == EventKind.OBSERVATION
    )
    assert observation_event.visible_payload["content"] == "public result"


def test_converse_adapter_maps_disclosure_and_commit_boundaries(tmp_path: Path) -> None:
    path = tmp_path / "insurance" / "privacy" / "output_case.json"
    path.parent.mkdir(parents=True)
    turns = [
        {
            "from": "environment",
            "to": "assistant",
            "short_answer": "<scratch_pad>private</scratch_pad>Record returned",
        },
        {"from": "assistant", "to": "external_agent", "short_answer": "Share record"},
        {"from": "assistant", "to": "assistant", "short_answer": "THE TASK IS NOW COMPLETED"},
    ]
    path.write_text(json.dumps(turns), encoding="utf-8")

    scenario = list(ConVerseReplayAdapter().load(path))[0]
    assert [event.checkpoint for event in scenario.events] == [
        Checkpoint.POST_OBSERVATION,
        Checkpoint.PRE_DISCLOSURE,
        Checkpoint.PRE_COMMIT,
    ]
    assert scenario.label is not None and scenario.label.risky
    assert scenario.label_provenance == LabelProvenance.WEAK_IMPORT
    assert "private" not in json.dumps(scenario.model_dump(mode="json"))
    assert not scenario.initial_permissions.grants["commit:final"].requires_confirmation
    observation = scenario.events[0]
    assert scenario.events[1].proposed_action is not None
    assert scenario.events[2].proposed_action is not None
    assert scenario.events[1].proposed_action.source_refs == (observation.event_id,)
    assert scenario.events[2].proposed_action.source_refs == (observation.event_id,)


def test_write_scenarios_does_not_clobber_existing_file_on_adapter_failure(
    tmp_path: Path,
) -> None:
    target = tmp_path / "scenarios.jsonl"
    target.write_text("previous\n", encoding="utf-8")

    def broken_scenarios():
        raise RuntimeError("adapter failed before yielding")
        yield

    with pytest.raises(RuntimeError, match="adapter failed"):
        write_scenarios(target, broken_scenarios())

    assert target.read_text(encoding="utf-8") == "previous\n"
    assert not (tmp_path / ".scenarios.jsonl.tmp").exists()
