import csv
import json
from pathlib import Path

import pytest

from selfauditbench.adapters.io import read_scenarios, write_scenarios
from selfauditbench.adapters.asb import ASBReplayAdapter
from selfauditbench.core.models import (
    Annotation,
    AnnotationStatus,
    Intervention,
    LabelProvenance,
)
from selfauditbench.evaluation.annotations import (
    GoldManifest,
    GoldPair,
    apply_adjudicated_labels,
    build_adjudication_queue,
    carry_forward_annotations,
    export_annotation_templates,
    materialize_annotation_packet,
    materialize_calibration_pilot,
    read_gold_manifest,
    read_private_mapping,
    validate_annotation_file,
    validate_completed_annotations,
    validate_gold_manifest,
    _normalize_source_ref,
    _scenario_content_fingerprint,
    _select_asb_pairs,
    _source_content_fingerprints,
    verify_annotation_freeze_manifest,
    write_annotation_freeze_manifest,
)
from selfauditbench.storage.hashing import canonical_json

ROOT = Path(__file__).parents[1]


def test_tracked_gold_candidate_manifest_has_24_plus_24_pairs() -> None:
    manifest = read_gold_manifest(ROOT / "data" / "gold" / "candidates.yaml")
    validate_gold_manifest(manifest)
    assert len(manifest.pairs) == 48
    assert sum(pair.source_dataset == "asb" for pair in manifest.pairs) == 24
    assert sum(pair.source_dataset == "converse" for pair in manifest.pairs) == 24
    asb_tags = {tag for pair in manifest.pairs if pair.source_dataset == "asb" for tag in pair.tags}
    assert "pot_backdoor" in asb_tags
    assert len({tag for tag in asb_tags if tag.startswith("example/")}) >= 5


def test_export_writes_two_blank_96_row_annotation_templates(tmp_path: Path) -> None:
    manifest = read_gold_manifest(ROOT / "data" / "gold" / "candidates.yaml")
    export_annotation_templates(manifest, tmp_path)
    first = validate_annotation_file(tmp_path / "annotator_a.jsonl")
    second = validate_annotation_file(tmp_path / "annotator_b.jsonl")
    assert len(first) == len(second) == 96
    assert all(annotation.label is None for annotation in first + second)


def test_materialized_annotation_packet_is_blinded(tmp_path: Path) -> None:
    scenarios = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")
    benign, risky = scenarios
    manifest = GoldManifest(
        pairs=(
            GoldPair(
                pair_id="test-pair",
                source_dataset="asb",
                attack_source=risky.source_ref,
                control_source=benign.source_ref,
                control_provenance="test",
            ),
        )
    )

    summary = materialize_annotation_packet(
        manifest,
        scenarios,
        (),
        tmp_path,
        seed=7,
        allow_missing=True,
    )
    packet = read_scenarios(tmp_path / "scenarios.jsonl")

    assert summary["materialized_items"] == 2
    assert summary["final_ready"] is False
    assert summary["pilot_escape_used"] is True
    assert all(scenario.scenario_id.startswith("sab-gold-") for scenario in packet)
    assert all(scenario.source_ref.startswith("blinded:") for scenario in packet)
    assert all(scenario.pair_id is None for scenario in packet)
    assert all(scenario.tags == ("annotation-item",) for scenario in packet)
    assert all(scenario.label is None for scenario in packet)
    assert all(event.raw_artifact_ref is None for scenario in packet for event in scenario.events)
    private_mapping = (tmp_path / "private_mapping.jsonl").read_text(encoding="utf-8")
    assert "test-pair" in private_mapping
    assert "attack" in private_mapping


def test_adjudication_queue_reports_agreement_and_applies_labels(tmp_path: Path) -> None:
    scenarios = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")
    first = [
        Annotation(
            scenario_id=scenario.scenario_id,
            annotator_id="a",
            status=AnnotationStatus.INDEPENDENT,
            label=scenario.label,
        )
        for scenario in scenarios
    ]
    second = [
        annotation.model_copy(update={"annotator_id": "b"}) for annotation in first
    ]

    tasks, summary = build_adjudication_queue(first, second, scenarios=scenarios)
    mapping = [
        {
            "item_id": scenarios[0].scenario_id,
            "pair_id": "gold-pair",
            "role": "control",
            "source_dataset": "asb",
            "source_ref": "private/control.json",
        },
        {
            "item_id": scenarios[1].scenario_id,
            "pair_id": "gold-pair",
            "role": "attack",
            "source_dataset": "asb",
            "source_ref": "private/attack.json",
        },
    ]
    adjudicated = apply_adjudicated_labels(scenarios, tasks, mapping)

    assert summary["completed_by_both"] == 2
    assert summary["exact_label_agreements"] == 2
    assert summary["risk_label_agreement"] == 1.0
    assert summary["risk_label_agreement_counts"] == {
        "value": 1.0,
        "numerator": 2,
        "denominator": 2,
    }
    assert all(not scenario.weak_label for scenario in adjudicated)
    assert all(
        scenario.label_provenance == LabelProvenance.HUMAN_ADJUDICATED
        for scenario in adjudicated
    )
    assert len({scenario.label_evidence_sha256 for scenario in adjudicated}) == 1
    assert {scenario.source_ref for scenario in adjudicated} == {
        "gold/asb/gold-pair/attack",
        "gold/asb/gold-pair/control",
    }
    assert [scenario.label for scenario in adjudicated] == [
        scenario.label for scenario in scenarios
    ]


def test_carry_forward_reuses_only_unchanged_frozen_surface_rows(
    tmp_path: Path,
) -> None:
    smoke = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")
    prior_scenarios = [
        smoke[0].model_copy(
            update={"source_dataset": "asb", "source_ref": "asb/source"}
        ),
        smoke[1].model_copy(
            update={"source_dataset": "converse", "source_ref": "converse/source"}
        ),
    ]
    mapping = [
        {
            "item_id": prior_scenarios[0].scenario_id,
            "pair_id": "asb-pair",
            "role": "control",
            "source_dataset": "asb",
            "source_ref": "asb/source",
        },
        {
            "item_id": prior_scenarios[1].scenario_id,
            "pair_id": "converse-pair",
            "role": "attack",
            "source_dataset": "converse",
            "source_ref": "converse/source",
        },
    ]
    prior = tmp_path / "prior"
    packet = tmp_path / "packet"
    prior.mkdir()
    packet.mkdir()
    write_scenarios(prior / "scenarios.jsonl", prior_scenarios)
    (prior / "private_mapping.jsonl").write_text(
        "".join(canonical_json(item) + "\n" for item in mapping),
        encoding="utf-8",
    )
    for filename, annotator_id in (
        ("annotator_a.jsonl", "researcher-a"),
        ("annotator_b.jsonl", "researcher-b"),
    ):
        values = [
            Annotation(
                scenario_id=scenario.scenario_id,
                annotator_id=annotator_id,
                status=AnnotationStatus.INDEPENDENT,
                label=scenario.label,
            )
            for scenario in prior_scenarios
        ]
        (prior / filename).write_text(
            "".join(
                canonical_json(item.model_dump(mode="json")) + "\n"
                for item in values
            ),
            encoding="utf-8",
        )
    write_annotation_freeze_manifest(
        prior / "independent_annotations.freeze.json",
        packet_scenarios=prior / "scenarios.jsonl",
        private_mapping=prior / "private_mapping.jsonl",
        annotator_a=prior / "annotator_a.jsonl",
        annotator_b=prior / "annotator_b.jsonl",
    )

    changed_event = prior_scenarios[0].events[0].model_copy(
        update={"visible_payload": {"content": "chronology-clean action context"}}
    )
    packet_scenarios = [
        prior_scenarios[0].model_copy(
            update={"events": (changed_event, *prior_scenarios[0].events[1:])}
        ),
        prior_scenarios[1],
    ]
    write_scenarios(packet / "scenarios.jsonl", packet_scenarios)
    (packet / "private_mapping.jsonl").write_text(
        "".join(canonical_json(item) + "\n" for item in mapping),
        encoding="utf-8",
    )
    for filename, template_id in (
        ("annotator_a.jsonl", "annotator_a"),
        ("annotator_b.jsonl", "annotator_b"),
    ):
        values = [
            Annotation(scenario_id=scenario.scenario_id, annotator_id=template_id)
            for scenario in packet_scenarios
        ]
        (packet / filename).write_text(
            "".join(
                canonical_json(item.model_dump(mode="json")) + "\n"
                for item in values
            ),
            encoding="utf-8",
        )

    summary = carry_forward_annotations(prior, packet, surface="converse")

    assert summary["copied_item_count"] == 1
    assert summary["pending_item_count"] == 1
    first = validate_annotation_file(
        packet / "annotator_a.jsonl", scenarios=packet_scenarios
    )
    assert first[0].status == AnnotationStatus.PENDING
    assert first[0].label is None
    assert first[1].status == AnnotationStatus.INDEPENDENT
    assert first[1].label == prior_scenarios[1].label
    assert (packet / "carry_forward.json").is_file()


def test_annotation_freeze_manifest_survives_packet_archive_and_path_reuse(
    tmp_path: Path,
) -> None:
    packet = tmp_path / "packet"
    packet.mkdir()
    names = {
        "packet_scenarios": "scenarios.jsonl",
        "private_mapping": "private_mapping.jsonl",
        "annotator_a": "annotator_a.jsonl",
        "annotator_b": "annotator_b.jsonl",
        "annotation_protocol": "ANNOTATION_PROTOCOL.md",
    }
    for name in names.values():
        (packet / name).write_text(f"frozen {name}\n", encoding="utf-8")

    freeze = packet / "independent_annotations.freeze.json"
    write_annotation_freeze_manifest(
        freeze,
        packet_scenarios=packet / names["packet_scenarios"],
        private_mapping=packet / names["private_mapping"],
        annotator_a=packet / names["annotator_a"],
        annotator_b=packet / names["annotator_b"],
    )
    value = json.loads(freeze.read_text(encoding="utf-8"))
    assert value["schema_version"] == "1.1"
    assert all(not Path(raw_path).is_absolute() for raw_path in value["files"].values())

    # Simulate a legacy frozen packet whose absolute paths are later archived.
    value["schema_version"] = "1.0"
    value["files"] = {
        name: str((packet / filename).resolve()) for name, filename in names.items()
    }
    freeze.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    archived = tmp_path / "archived"
    packet.rename(archived)

    # Reusing the original pathname must not redirect verification into the new packet.
    packet.mkdir()
    for name in names.values():
        (packet / name).write_text(f"new {name}\n", encoding="utf-8")
    verified = verify_annotation_freeze_manifest(
        archived / "independent_annotations.freeze.json"
    )
    assert verified["schema_version"] == "1.0"

    (archived / "ANNOTATION_PROTOCOL.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frozen annotation input changed"):
        verify_annotation_freeze_manifest(archived / "independent_annotations.freeze.json")


def test_final_packet_rejects_unresolved_pair_specific_controls(tmp_path: Path) -> None:
    source_manifest = read_gold_manifest(ROOT / "data" / "gold" / "candidates.yaml")
    converse_index = 0
    pairs = []
    for pair in source_manifest.pairs:
        if pair.source_dataset == "converse":
            converse_index += 1
            if converse_index <= 21:
                pair = pair.model_copy(
                    update={
                        "control_source": (
                            "regenerate:test/converse-control-"
                            f"{converse_index:02d}"
                        ),
                        "control_provenance": (
                            "official_benign_regeneration_required"
                        ),
                    }
                )
            else:
                pair = pair.model_copy(
                    update={
                        "control_source": (
                            "synthetic:resolved/converse-control-"
                            f"{converse_index:02d}"
                        ),
                        "control_provenance": "synthetic_test_fixture",
                    }
                )
        pairs.append(pair)
    manifest = source_manifest.model_copy(update={"pairs": tuple(pairs)})

    with pytest.raises(ValueError, match="final annotation packet is not ready"):
        materialize_annotation_packet(manifest, (), (), tmp_path)

    summary = json.loads((tmp_path / "packet_summary.json").read_text(encoding="utf-8"))
    assert summary["requested_items"] == 96
    assert summary["final_ready"] is False
    assert summary["duplicate_source_count"] == 0
    assert summary["unresolved_control_count"] == 21


def test_packet_summary_detects_duplicate_trajectory_content(tmp_path: Path) -> None:
    benign = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[0]
    attack = benign.model_copy(update={"source_ref": "private/attack"})
    control = benign.model_copy(update={"source_ref": "private/control"})
    manifest = GoldManifest(
        pairs=(
            GoldPair(
                pair_id="pair",
                source_dataset="asb",
                attack_source=attack.source_ref,
                control_source=control.source_ref,
                control_provenance="test",
            ),
        )
    )

    summary = materialize_annotation_packet(
        manifest,
        (attack, control),
        (),
        tmp_path,
        allow_missing=True,
    )

    assert summary["unique_source_count"] == 2
    assert summary["duplicate_source_count"] == 0
    assert summary["unique_content_count"] == 1
    assert summary["duplicate_content_count"] == 1


def test_asb_selection_skips_distinct_rows_with_duplicate_content(
    tmp_path: Path,
) -> None:
    fieldnames = ["Agent Name", "Attack Tool", "Memory Found", "messages"]
    attack_path = tmp_path / "pot_backdoor" / "attacks.csv"
    clean_path = tmp_path / "clean" / "model" / "controls_full.csv"
    attack_path.parent.mkdir(parents=True)
    clean_path.parent.mkdir(parents=True)

    with attack_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index in range(24):
            writer.writerow(
                {
                    "Agent Name": "agent",
                    "Attack Tool": f"attack_tool_{index}",
                    "Memory Found": "N/A",
                    "messages": repr(
                        [
                            {"role": "user", "content": f"attack task {index}"},
                            {
                                "role": "assistant",
                                "content": (
                                    "[Action]: I will call the "
                                    f"attack_tool_{index}"
                                ),
                            },
                        ]
                    ),
                }
            )

    with clean_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index in range(24):
            # Two different source rows deliberately normalize to each content value.
            for _ in range(2):
                writer.writerow(
                    {
                        "Agent Name": "agent",
                        "Attack Tool": "",
                        "Memory Found": "N/A",
                        "messages": repr(
                            [{"role": "user", "content": f"clean task {index}"}]
                        ),
                    }
                )

    scenarios = tuple(ASBReplayAdapter().load(tmp_path))
    fingerprints = _source_content_fingerprints(scenarios)
    used_content: set[str] = set()
    pairs = _select_asb_pairs(
        tmp_path,
        content_by_source=fingerprints,
        used_content=used_content,
    )

    assert len(pairs) == 24
    selected_fingerprints = []
    for pair in pairs:
        selected_fingerprints.extend(
            (
                fingerprints[_normalize_source_ref(pair.attack_source)],
                fingerprints[_normalize_source_ref(pair.control_source)],
            )
        )
    assert len(selected_fingerprints) == len(set(selected_fingerprints)) == 48
    assert used_content == set(selected_fingerprints)


def test_completed_annotation_semantics_are_scenario_aware() -> None:
    scenarios = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")
    benign, risky = scenarios
    assert risky.label is not None
    invalid = risky.label.model_copy(
        update={
            "first_risk_sufficient_event": 1,
            "harm_boundary_event": 0,
        }
    )
    annotations = [
        Annotation(
            scenario_id=benign.scenario_id,
            annotator_id="a",
            status=AnnotationStatus.INDEPENDENT,
            label=benign.label,
        ),
        Annotation(
            scenario_id=risky.scenario_id,
            annotator_id="a",
            status=AnnotationStatus.INDEPENDENT,
            label=invalid,
        ),
    ]

    with pytest.raises(ValueError, match="at or before"):
        validate_completed_annotations(annotations, scenarios)


def test_adjudication_requires_distinct_annotators_and_named_resolution() -> None:
    scenarios = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")
    first = [
        Annotation(
            scenario_id=scenario.scenario_id,
            annotator_id="same",
            status=AnnotationStatus.INDEPENDENT,
            label=scenario.label,
        )
        for scenario in scenarios
    ]
    with pytest.raises(ValueError, match="distinct annotator"):
        build_adjudication_queue(first, first, scenarios=scenarios)

    second = [item.model_copy(update={"annotator_id": "b"}) for item in first]
    risky = second[1]
    assert risky.label is not None
    second[1] = risky.model_copy(
        update={
            "label": risky.label.model_copy(
                update={"accepted_interventions": (Intervention.PAUSE,)}
            )
        }
    )
    tasks, _ = build_adjudication_queue(first, second, scenarios=scenarios)
    mapping = [
        {
            "item_id": scenarios[0].scenario_id,
            "pair_id": "pair",
            "role": "control",
            "source_dataset": "asb",
            "source_ref": "control",
        },
        {
            "item_id": scenarios[1].scenario_id,
            "pair_id": "pair",
            "role": "attack",
            "source_dataset": "asb",
            "source_ref": "attack",
        },
    ]
    unresolved = next(task for task in tasks if not task.exact_agreement)
    resolved = unresolved.model_copy(update={"adjudicated_label": first[1].label})
    completed = [resolved if task.scenario_id == resolved.scenario_id else task for task in tasks]

    with pytest.raises(ValueError, match="named adjudicator"):
        apply_adjudicated_labels(scenarios, completed, mapping)


def test_calibration_pilot_is_deterministic_blank_and_surface_balanced(
    tmp_path: Path,
) -> None:
    benign = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")[0]
    scenarios = []
    for surface in ("asb", "converse"):
        for index in range(6):
            scenario_id = f"sab-gold-{surface}-{index}"
            events = tuple(
                event.model_copy(
                    update={
                        "scenario_id": scenario_id,
                        "event_id": f"{scenario_id}:event:{event.sequence}",
                    }
                )
                for event in benign.events
            )
            scenarios.append(
                benign.model_copy(
                    update={
                        "scenario_id": scenario_id,
                        "source_dataset": surface,
                        "source_ref": f"blinded:{scenario_id}",
                        "pair_id": None,
                        "tags": ("annotation-item",),
                        "events": events,
                        "label": None,
                    }
                )
            )

    mapping = [
        {
            "item_id": scenario.scenario_id,
            "pair_id": f"pilot-pair-{index}",
            "role": "attack" if index % 2 == 0 else "control",
            "source_dataset": scenario.source_dataset,
            "source_ref": f"pilot-source-{index}",
        }
        for index, scenario in enumerate(scenarios)
    ]
    first = materialize_calibration_pilot(
        scenarios, tmp_path / "first", mapping
    )
    second = materialize_calibration_pilot(
        scenarios, tmp_path / "second", mapping
    )

    assert first["scenario_ids"] == second["scenario_ids"]
    assert first["pilot_items"] == 10
    assert first["surface_counts"] == {"asb": 5, "converse": 5}
    assert first["role_counts"] == {"attack": 5, "control": 5}
    annotations = validate_annotation_file(tmp_path / "first" / "annotator_a.jsonl")
    assert all(annotation.label is None for annotation in annotations)
    pilot_mapping = read_private_mapping(tmp_path / "first" / "private_mapping.jsonl")
    assert len(pilot_mapping) == 10
    assert first["hashes"]["private_mapping_sha256"]
