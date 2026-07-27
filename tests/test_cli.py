import json
from pathlib import Path

from typer.testing import CliRunner

from selfauditbench.adapters.io import read_scenarios, write_scenarios
from selfauditbench.cli import app
from selfauditbench.core.models import Annotation, AnnotationStatus, LabelProvenance
from selfauditbench.evaluation.annotations import (
    build_adjudication_queue,
    write_adjudication_queue,
)
from selfauditbench.storage.hashing import sha256_file

ROOT = Path(__file__).parents[1]


def test_blank_annotation_templates_are_pending_not_agreements() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "annotate",
            "adjudicate",
            str(ROOT / "data" / "gold" / "annotations" / "annotator_a.jsonl"),
            str(ROOT / "data" / "gold" / "annotations" / "annotator_b.jsonl"),
        ],
    )
    assert result.exit_code == 0
    assert "completed pairs: 0" in result.output
    assert "pending pairs: 96" in result.output
    assert "exact agreements: 0" in result.output


def test_agentforesight_ingest_command_is_exposed() -> None:
    result = CliRunner().invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "agentforesight" in result.output
    assert "agentforesight-results" in result.output


def test_statistics_and_annotation_workflows_are_exposed() -> None:
    runner = CliRunner()
    compare_result = runner.invoke(app, ["compare", "--help"])
    annotate_result = runner.invoke(app, ["annotate", "--help"])

    assert compare_result.exit_code == 0, compare_result.output
    assert "bootstrap" in compare_result.output.lower()
    assert annotate_result.exit_code == 0, annotate_result.output
    assert "packet" in annotate_result.output
    assert "apply" in annotate_result.output


def test_compact_annotation_export_rejects_unprovenanced_fixture(tmp_path: Path) -> None:
    output = tmp_path / "compact.jsonl"
    result = CliRunner().invoke(
        app,
        [
            "annotate",
            "compact",
            str(ROOT / "data" / "smoke" / "scenarios.jsonl"),
            str(output),
            "--limit",
            "2",
        ],
    )
    assert result.exit_code != 0
    assert "not final human-adjudicated gold" in result.output
    assert not output.exists()


def test_compact_defaults_to_all_and_partial_limit_is_explicit(tmp_path: Path) -> None:
    smoke = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")
    evidence = "a" * 64
    gold = [
        scenario.model_copy(
            update={
                "scenario_id": f"gold-{index}",
                "source_dataset": "asb",
                "source_ref": f"gold/asb/pair/{role}",
                "pair_id": "pair",
                "tags": ("gold", f"role:{role}", "surface:asb"),
                "label_provenance": LabelProvenance.HUMAN_ADJUDICATED,
                "label_evidence_sha256": evidence,
                "events": tuple(
                    event.model_copy(
                        update={
                            "scenario_id": f"gold-{index}",
                            "event_id": f"gold-{index}:event:{event.sequence}",
                            "proposed_action": (
                                event.proposed_action.model_copy(
                                    update={
                                        "source_refs": tuple(
                                            f"gold-{index}:event:0"
                                            if ref.endswith(":event:0")
                                            else ref
                                            for ref in event.proposed_action.source_refs
                                        )
                                    }
                                )
                                if event.proposed_action is not None
                                else None
                            ),
                        }
                    )
                    for event in scenario.events
                ),
            }
        )
        for index, (scenario, role) in enumerate(
            zip(smoke, ("control", "attack"), strict=True)
        )
    ]
    source = tmp_path / "gold.jsonl"
    output = tmp_path / "compact.jsonl"
    write_scenarios(source, gold)

    complete = CliRunner().invoke(
        app,
        [
            "annotate",
            "compact",
            str(source),
            str(output),
            "--allow-subset",
        ],
    )
    partial = CliRunner().invoke(
        app,
        ["annotate", "compact", str(source), str(tmp_path / "partial.jsonl"), "--limit", "1"],
    )

    assert complete.exit_code == 0, complete.output
    assert len(read_scenarios(output)) == 2
    integrity_path = tmp_path / "compact.integrity.json"
    assert integrity_path.exists()
    integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
    assert integrity["compact_dataset_sha256"] == sha256_file(output)
    assert integrity["scenario_count"] == 2
    assert integrity["pair_count"] == 1
    assert integrity["surface_scope"] == "asb"
    assert integrity["shared_annotation_evidence_sha256"] == evidence
    assert integrity["subset_export"] is True
    verified = CliRunner().invoke(
        app, ["annotate", "verify-compact", str(integrity_path)]
    )
    assert verified.exit_code == 0, verified.output
    assert '"status": "verified"' in verified.output
    frozen = integrity_path.read_text(encoding="utf-8")
    repeat = CliRunner().invoke(
        app,
        [
            "annotate",
            "compact",
            str(source),
            str(output),
            "--allow-subset",
        ],
    )
    assert repeat.exit_code == 0, repeat.output
    assert integrity_path.read_text(encoding="utf-8") == frozen
    output.write_text(output.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    corrupt = CliRunner().invoke(
        app, ["annotate", "verify-compact", str(integrity_path)]
    )
    assert corrupt.exit_code == 1
    assert '"status": "corrupt"' in corrupt.output
    assert partial.exit_code != 0
    assert "--allow-subset" in partial.output


def test_freeze_and_apply_restore_pairs_and_write_evidence(tmp_path: Path) -> None:
    packet = tmp_path / "packet"
    packet.mkdir()
    scenarios = read_scenarios(ROOT / "data" / "smoke" / "scenarios.jsonl")
    scenarios_path = packet / "scenarios.jsonl"
    write_scenarios(scenarios_path, scenarios)
    first = [
        Annotation(
            scenario_id=scenario.scenario_id,
            annotator_id="annotator_a",
            status=AnnotationStatus.INDEPENDENT,
            label=scenario.label,
        )
        for scenario in scenarios
    ]
    second = [item.model_copy(update={"annotator_id": "annotator_b"}) for item in first]
    for name, annotations in (("annotator_a", first), ("annotator_b", second)):
        (packet / f"{name}.jsonl").write_text(
            "".join(
                json.dumps(annotation.model_dump(mode="json"), sort_keys=True) + "\n"
                for annotation in annotations
            ),
            encoding="utf-8",
        )
    mapping = [
        {
            "item_id": scenarios[0].scenario_id,
            "pair_id": "pair",
            "role": "control",
            "source_dataset": "asb",
            "source_ref": "private/control",
        },
        {
            "item_id": scenarios[1].scenario_id,
            "pair_id": "pair",
            "role": "attack",
            "source_dataset": "asb",
            "source_ref": "private/attack",
        },
    ]
    mapping_path = packet / "private_mapping.jsonl"
    mapping_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in mapping),
        encoding="utf-8",
    )
    tasks, summary = build_adjudication_queue(first, second, scenarios=scenarios)
    queue = packet / "adjudication.jsonl"
    write_adjudication_queue(queue, tasks, summary)

    runner = CliRunner()
    freeze = runner.invoke(app, ["annotate", "freeze", str(packet)])
    output = tmp_path / "gold.jsonl"
    apply = runner.invoke(
        app,
        [
            "annotate",
            "apply",
            str(scenarios_path),
            str(queue),
            str(mapping_path),
            str(output),
        ],
    )

    assert freeze.exit_code == 0, freeze.output
    assert apply.exit_code == 0, apply.output
    gold = read_scenarios(output)
    assert {scenario.pair_id for scenario in gold} == {"pair"}
    assert all(
        scenario.label_provenance == LabelProvenance.HUMAN_ADJUDICATED
        for scenario in gold
    )
    assert (tmp_path / "gold.annotation_evidence.json").exists()


def test_non_smoke_replay_exports_timestamped_paper_bundle(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets"
    dataset_dir.mkdir()
    dataset = dataset_dir / "scenarios.jsonl"
    dataset.write_text(
        (ROOT / "data" / "smoke" / "scenarios.jsonl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    output_root = tmp_path / "runs"
    config = tmp_path / "paper-run.yaml"
    config.write_text(
        "\n".join(
            [
                "run_id: paper-cli-run",
                "strategy: no_audit",
                "audit_mode: none",
                f'dataset: "{dataset.as_posix()}"',
                f'output_root: "{output_root.as_posix()}"',
                "random_seed: 7",
                "fail_closed: true",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["run", "replay", "--config", str(config)])

    assert result.exit_code == 0, result.output
    bundles = list((tmp_path / "paper").glob("*-paper-cli-run"))
    assert len(bundles) == 1
    assert (bundles[0] / "figures" / "fig_run_metric_matrix.pdf").exists()
    assert "timestamped paper assets" in result.output

    run_dir = output_root / "paper-cli-run"
    supplementary_path = run_dir / "supplementary_reliability.json"
    supplementary = json.loads(supplementary_path.read_text(encoding="utf-8"))
    supplementary.pop("evidence_policy")
    supplementary_path.write_text(json.dumps(supplementary), encoding="utf-8")

    report_result = CliRunner().invoke(app, ["report", "--run", str(run_dir)])

    assert report_result.exit_code == 0, report_result.output
    refreshed = json.loads(supplementary_path.read_text(encoding="utf-8"))
    assert refreshed["evidence_policy"]["aggregate_headline_allowed"] is False

    verify_result = CliRunner().invoke(app, ["verify", "--run", str(run_dir)])
    assert verify_result.exit_code == 0, verify_result.output
    assert '"status": "verified"' in verify_result.output


def test_verify_returns_failure_for_legacy_unverified_run(tmp_path: Path) -> None:
    run_dir = tmp_path / "legacy-run"
    run_dir.mkdir()

    result = CliRunner().invoke(app, ["verify", "--run", str(run_dir)])

    assert result.exit_code == 1
    assert '"status": "legacy_unverified"' in result.output


def test_live_conformance_command_writes_evidence(tmp_path: Path) -> None:
    output = tmp_path / "live-conformance.json"

    result = CliRunner().invoke(
        app,
        ["conformance", "live", "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    assert "6/6 passed" in result.output
    assert json.loads(output.read_text(encoding="utf-8"))["summary"][
        "all_passed"
    ] is True

    verified = CliRunner().invoke(app, ["conformance", "verify", str(output)])
    assert verified.exit_code == 0, verified.output
    assert "verified" in verified.output

    output.write_text("{}", encoding="utf-8")
    corrupt = CliRunner().invoke(app, ["conformance", "verify", str(output)])
    assert corrupt.exit_code == 1
    assert "corrupt" in corrupt.output
