from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from selfauditbench.adapters.io import read_scenarios, write_scenarios
from selfauditbench.cli import app
from selfauditbench.core.models import LabelProvenance, Scenario, ScenarioLabel
from selfauditbench.evaluation.datasets import (
    headline_eligibility,
    write_diagnostic_slice,
)

ROOT = Path(__file__).parents[1]


def test_some_50_cli_is_deterministic_and_writes_matching_summary(tmp_path: Path) -> None:
    scenarios = _synthetic_scenarios("asb", count=60, weak=True)
    source = tmp_path / "asb.jsonl"
    first = tmp_path / "asb-some-50.jsonl"
    second = tmp_path / "asb-some-50-repeat.jsonl"
    summary = tmp_path / "asb-some-50.dataset_summary.json"
    write_scenarios(source, scenarios)

    runner = CliRunner()
    args = [
        "dataset",
        "some-50",
        "asb",
        str(source),
        str(first),
        "--summary",
        str(summary),
    ]
    result = runner.invoke(app, args)
    repeat = runner.invoke(
        app,
        [
            "dataset",
            "some-50",
            "asb",
            str(source),
            str(second),
            "--summary",
            str(tmp_path / "repeat.dataset_summary.json"),
        ],
    )

    selected = read_scenarios(first)
    metadata = json.loads(summary.read_text(encoding="utf-8"))
    assert result.exit_code == 0, result.output
    assert repeat.exit_code == 0, repeat.output
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert len(selected) == 50
    assert metadata["scenario_count"] == 50
    assert metadata["source_count"] == 60
    assert metadata["weak_label_count"] == 50
    assert metadata["risky_count"] == 25
    assert metadata["control_count"] == 25
    assert metadata["headline_eligibility"]["status"] == "supplementary_exploratory"
    assert metadata["false_alarm_denominator_valid"] is False


def test_agentforesight_some_50_balances_labels_and_domains(tmp_path: Path) -> None:
    scenarios = _synthetic_scenarios("agentforesight", count=90, weak=False)
    output = tmp_path / "af-some-50.jsonl"
    count, summary_path = write_diagnostic_slice(
        scenarios,
        surface="agentforesight",
        output=output,
        limit=50,
    )

    selected = read_scenarios(output)
    metadata = json.loads(summary_path.read_text(encoding="utf-8"))
    assert count == 50
    assert sum(scenario.label.risky for scenario in selected if scenario.label) == 25
    assert sum(not scenario.label.risky for scenario in selected if scenario.label) == 25
    assert set(metadata["strata_counts"]["domain"]) == {"Agentic", "Coding", "Math"}
    assert metadata["headline_eligibility"]["status"] == "prefix_reliability_only"
    assert metadata["false_alarm_denominator_valid"] is False


def test_converse_some_50_prefers_attack_control_pairs(tmp_path: Path) -> None:
    scenarios = _synthetic_scenarios("converse", count=60, weak=True, paired=True)
    output = tmp_path / "converse-some-50.jsonl"
    _, summary_path = write_diagnostic_slice(
        scenarios,
        surface="converse",
        output=output,
        limit=50,
    )

    selected = read_scenarios(output)
    metadata = json.loads(summary_path.read_text(encoding="utf-8"))
    pair_ids = {scenario.pair_id for scenario in selected}
    assert len(selected) == 50
    assert None not in pair_ids
    assert len(pair_ids) == 25
    assert metadata["selection"]["selected_attack_control_pairs"] == 25
    assert sum(scenario.label.risky for scenario in selected if scenario.label) == 25
    assert sum(not scenario.label.risky for scenario in selected if scenario.label) == 25


def test_headline_eligibility_separates_gold_prefix_and_exploratory_data() -> None:
    smoke = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")
    candidates = _synthetic_scenarios("asb", count=48, weak=False, paired=True)
    human_gold = [
        scenario.model_copy(
            update={
                "source_ref": f"gold/asb/{scenario.pair_id}/{role}",
                "tags": ("gold", f"role:{role}", "surface:asb"),
                "label_provenance": LabelProvenance.HUMAN_ADJUDICATED,
                "label_evidence_sha256": "a" * 64,
            }
        )
        for scenario, role in zip(
            candidates,
            ("control", "attack") * 24,
            strict=True,
        )
    ]
    gold = headline_eligibility(human_gold)
    weak = headline_eligibility(
        [scenario.model_copy(update={"weak_label": True}) for scenario in human_gold]
    )
    af = headline_eligibility(
        [
            scenario.model_copy(
                update={
                    "source_dataset": "agentforesight",
                    "weak_label": False,
                    "label_provenance": LabelProvenance.SOURCE_CURATED,
                    "label_evidence_sha256": None,
                }
            )
            for scenario in smoke
        ]
    )

    assert gold["status"] == "recorded_action_headline_eligible"
    assert gold["false_alarm_denominator_valid"] is True
    assert weak["status"] == "supplementary_exploratory"
    assert af["status"] == "prefix_reliability_only"


def _synthetic_scenarios(
    source_dataset: str,
    *,
    count: int,
    weak: bool,
    paired: bool = False,
) -> list[Scenario]:
    smoke = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")
    benign, risky = smoke
    domains = ("Math", "Coding", "Agentic")
    scenarios: list[Scenario] = []
    for index in range(count):
        base = benign if index % 2 == 0 else risky
        risky_label = index % 2 == 1
        domain = domains[index % len(domains)]
        scenario_id = f"{source_dataset}-{index:03d}"
        events = tuple(
            event.model_copy(
                update={
                    "scenario_id": scenario_id,
                    "event_id": f"{scenario_id}:event:{event.sequence}",
                }
            )
            for event in base.events
        )
        label = base.label
        assert label is not None
        updated_label = ScenarioLabel.model_validate(
            label.model_dump(mode="json") | {"risky": risky_label}
        )
        scenarios.append(
            base.model_copy(
                update={
                    "scenario_id": scenario_id,
                    "source_dataset": source_dataset,
                    "source_ref": f"{source_dataset}/{domain}/case-{index:03d}",
                    "pair_id": f"{source_dataset}-pair-{index // 2:03d}" if paired else None,
                    "tags": (f"domain:{domain}", f"case-{index % 5}"),
                    "weak_label": weak,
                    "label_provenance": (
                        LabelProvenance.SOURCE_CURATED
                        if source_dataset == "agentforesight"
                        else LabelProvenance.WEAK_IMPORT
                    ),
                    "events": events,
                    "label": updated_label,
                }
            )
        )
    return scenarios
