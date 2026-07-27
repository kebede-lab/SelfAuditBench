from __future__ import annotations

import json
from pathlib import Path

import pytest

from selfauditbench.evaluation.paper import export_paper_assets
from selfauditbench.storage.artifacts import write_integrity_manifest

ROOT = Path(__file__).parents[1]


def test_paper_export_writes_tables_figures_and_index(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets"
    dataset_dir.mkdir()
    dataset = ROOT / "data" / "smoke" / "scenarios.jsonl"
    (dataset_dir / "smoke.jsonl").write_text(dataset.read_text(encoding="utf-8"), encoding="utf-8")

    run_dir = tmp_path / "runs" / "paper-run"
    run_dir.mkdir(parents=True)
    (run_dir / "metrics.json").write_text(
        json.dumps(
            {
                "execution_reliability": {
                    "total": 2,
                    "statuses": {"complete": 2},
                    "task_completion": {"value": 1.0, "numerator": 2, "denominator": 2},
                    "schema_compliance": {"value": 1.0, "numerator": 2, "denominator": 2},
                },
                "early_risk_detection_rate": {"value": 0.5, "numerator": 1, "denominator": 2},
                "first_sufficient_prefix_recall": {
                    "value": 0.5,
                    "numerator": 1,
                    "denominator": 2,
                },
                "false_alarm_rate": {"value": 0.0, "numerator": 0, "denominator": 1},
                "prefix_localization": {
                    "exact_f1": 0.5,
                    "false_alarm_rate": 0.0,
                    "step_accuracy": 0.5,
                },
                "brier_score": 0.25,
                "by_surface": {
                    "asb": {
                        "model_generated_early_detection_rate": {
                            "value": 1.0,
                            "numerator": 1,
                            "denominator": 1,
                        },
                        "model_false_alarm_rate": {
                            "value": 0.0,
                            "numerator": 0,
                            "denominator": 1,
                        },
                        "valid_audit_coverage": {
                            "value": 1.0,
                            "numerator": 2,
                            "denominator": 2,
                        },
                    },
                    "converse": {
                        "model_generated_early_detection_rate": {
                            "value": 0.0,
                            "numerator": 0,
                            "denominator": 1,
                        },
                        "model_false_alarm_rate": {
                            "value": 1.0,
                            "numerator": 1,
                            "denominator": 1,
                        },
                        "valid_audit_coverage": {
                            "value": 0.5,
                            "numerator": 1,
                            "denominator": 2,
                        },
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "paper-run", "strategy": "no_audit", "audit_mode": "none"}),
        encoding="utf-8",
    )
    (run_dir / "supplementary_reliability.json").write_text(
        json.dumps(
            {
                "run_id": "paper-run",
                "provider": "scripted",
                "model": "scripted",
                "wall_time_seconds": 1.25,
                "api": {
                    "call_attempts": 2,
                    "api_time_seconds": 0.75,
                    "total_tokens": 123,
                    "estimated_cost_usd": 0.001,
                },
                "failure_distribution": {
                    "scenario_failure_types": {},
                    "audit_attempt_failure_types": {},
                },
                "agent_testing_agent_safety": {"behavior_counts": {}},
                "dataset": {
                    "headline_eligibility": {
                        "status": "supplementary_exploratory",
                        "false_alarm_denominator_valid": False,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    write_integrity_manifest(run_dir)

    af_results = tmp_path / "af_results.json"
    af_results.write_text(
        json.dumps(
            {
                "by_domain": {
                    "Math": {
                        "n": 2,
                        "n_safe": 1,
                        "n_unsafe": 1,
                        "exact_f1": 50.0,
                        "ass_mean": 1.0,
                        "far": 0.0,
                        "step_acc": 50.0,
                    },
                    "overall": {
                        "n": 2,
                        "n_safe": 1,
                        "n_unsafe": 1,
                        "exact_f1": 50.0,
                        "ass_mean": 1.0,
                        "far": 0.0,
                        "step_acc": 50.0,
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    exported = export_paper_assets(
        dataset_dir=dataset_dir,
        runs_dir=tmp_path / "runs",
        output_dir=tmp_path / "paper",
        agentforesight_results_json=af_results,
    )

    produced = {path.relative_to(exported.output_dir).as_posix() for path in exported.files}
    assert "tables/dataset_inventory.md" in produced
    assert "tables/run_metrics_summary.tex" in produced
    assert "tables/api_reliability_supplement.tex" in produced
    assert "tables/model_audit_results.md" in produced
    assert "tables/audit_schema_results.tex" in produced
    assert "tables/broker_guard_results.csv" in produced
    assert "tables/execution_reliability_results.md" in produced
    assert "tables/api_efficiency_results.tex" in produced
    assert "tables/agent_safety_event_results.csv" in produced
    assert "tables/label_semantics_claim_eligibility.md" in produced
    assert "tables/annotation_study_evidence.md" in produced
    assert "tables/agentforesight_prefix_by_domain.csv" in produced
    assert "figures/fig_framework_pipeline.pdf" in produced
    assert "figures/fig_dataset_inventory.pdf" in produced
    assert "figures/fig_dataset_label_composition.pdf" in produced
    assert "figures/fig_run_metric_matrix.pdf" in produced
    assert "figures/fig_agentforesight_prefix_metrics.pdf" in produced
    assert not any(path.endswith(".svg") for path in produced)
    assert "paper_results.md" in produced
    assert (exported.output_dir / "paper_export_manifest.json").exists()
    manifest = json.loads(
        (exported.output_dir / "paper_export_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(manifest["root_digest"]) == 64
    assert manifest["run_integrity"]["paper-run"]["status"] == "verified"
    assert len(manifest["run_integrity"]["paper-run"]["root_digest"]) == 64
    assert all(
        len(entry["sha256"]) == 64 and entry["bytes"] > 0
        for entry in manifest["files"].values()
    )
    run_table = (exported.output_dir / "tables" / "run_metrics_summary.md").read_text()
    dataset_table = (exported.output_dir / "tables" / "dataset_inventory.md").read_text()
    api_table = (exported.output_dir / "tables" / "api_reliability_supplement.md").read_text()
    model_table = (exported.output_dir / "tables" / "model_audit_results.md").read_text()
    schema_table = (exported.output_dir / "tables" / "audit_schema_results.md").read_text()
    broker_table = (exported.output_dir / "tables" / "broker_guard_results.md").read_text()
    execution_table = (
        exported.output_dir / "tables" / "execution_reliability_results.md"
    ).read_text()
    semantics_table = (
        exported.output_dir / "tables" / "label_semantics_claim_eligibility.md"
    ).read_text()
    annotation_table = (
        exported.output_dir / "tables" / "annotation_study_evidence.md"
    ).read_text()
    assert "Model: valid audit" in run_table
    assert "Broker: guard pause" in run_table
    assert "Schema: compliance" in run_table
    assert "False-alarm claim use" in run_table
    assert "supplementary_exploratory" in run_table
    assert "[diagnostic_only]" in run_table
    assert "label_surface_diagnostics" in dataset_table
    assert "provider_api_stress; agent_testing_agent_safety" in api_table
    assert "Model early detection" in model_table
    assert "full recorded trace" in model_table
    assert "| asb |" in model_table
    assert "| converse |" in model_table
    assert "[20.65, 100.00]" in model_table
    assert "False-alarm denominator" in model_table
    assert "Valid-audit numerator" in schema_table
    assert "Schema denominator" in schema_table
    assert "absorbing terminal projection" in broker_table
    assert "Completion 95% CI" in execution_table
    assert "2" in execution_table
    assert "AgentForesight AFTraj" in semantics_table
    assert "Prefix localization and reliability only" in semantics_table
    assert "unavailable_no_manifest" in annotation_table
    assert "not_available_for_manuscript" in annotation_table
    assert (exported.output_dir / "figures" / "fig_run_metric_matrix.pdf").read_bytes().startswith(
        b"%PDF-1.4"
    )


def test_paper_export_uses_annotation_evidence_agreement_and_hashes(
    tmp_path: Path,
) -> None:
    dataset_dir = tmp_path / "datasets"
    dataset_dir.mkdir()
    evidence_path = dataset_dir / "gold.annotation_evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "scenario_count": 2,
                "pair_count": 1,
                "surface_counts": {"asb": 2},
                "label_evidence_sha256": "a" * 64,
                "unresolved_count": 0,
                "adjudication_changes": {
                    "from_annotator_a": 1,
                    "from_annotator_b": 0,
                },
                "agreement": {
                    "completed_by_both": 2,
                    "exact_label_agreement_rate": {
                        "value": 0.5,
                        "numerator": 1,
                        "denominator": 2,
                    },
                    "risk_label_agreement": 0.5,
                    "risk_label_agreement_counts": {
                        "value": 0.5,
                        "numerator": 1,
                        "denominator": 2,
                    },
                    "risk_label_cohen_kappa": 0.0,
                    "first_risk_event_exact_agreement": 1.0,
                    "first_risk_event_exact_agreement_counts": {
                        "value": 1.0,
                        "numerator": 1,
                        "denominator": 1,
                    },
                    "harm_boundary_exact_agreement": None,
                    "harm_boundary_exact_agreement_counts": {
                        "value": None,
                        "numerator": 0,
                        "denominator": 0,
                    },
                    "accepted_intervention_jaccard": 0.75,
                    "accepted_intervention_jaccard_n": 1,
                    "minimal_delta_exact_agreement": 1.0,
                    "minimal_delta_exact_agreement_counts": {
                        "value": 1.0,
                        "numerator": 1,
                        "denominator": 1,
                    },
                },
                "file_hashes_sha256": {
                    name: character * 64
                    for name, character in {
                        "packet_scenarios": "b",
                        "private_mapping": "c",
                        "annotator_a": "d",
                        "annotator_b": "e",
                        "adjudication": "f",
                        "final_dataset": "0",
                    }.items()
                },
            }
        ),
        encoding="utf-8",
    )

    exported = export_paper_assets(
        dataset_dir=dataset_dir,
        runs_dir=tmp_path / "runs",
        output_dir=tmp_path / "paper",
    )

    table = (exported.output_dir / "tables" / "annotation_study_evidence.md").read_text()
    assert "available_complete" in table
    assert "annotation_study_reliability" in table
    assert "Risk-label agreement" in table
    assert "50.00%" in table
    assert "Harm-boundary exact agreement | unavailable | 0 | 0" in table
    assert "a" * 64 in table
    manifest = json.loads(
        (exported.output_dir / "paper_export_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["annotation_evidence_json"] == str(evidence_path)
    assert manifest["annotation_evidence_status"] == "available_complete"


def test_paper_export_rejects_legacy_unverified_runs(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "legacy-run"
    run_dir.mkdir(parents=True)
    (run_dir / "metrics.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"status=legacy_unverified"):
        export_paper_assets(
            dataset_dir=tmp_path / "datasets",
            runs_dir=tmp_path / "runs",
            output_dir=tmp_path / "paper",
        )


def test_paper_export_rejects_corrupt_runs(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "corrupt-run"
    run_dir.mkdir(parents=True)
    metrics = run_dir / "metrics.json"
    metrics.write_text("{}\n", encoding="utf-8")
    write_integrity_manifest(run_dir)
    metrics.write_text('{"changed":true}\n', encoding="utf-8")

    with pytest.raises(ValueError, match=r"status=corrupt"):
        export_paper_assets(
            dataset_dir=tmp_path / "datasets",
            runs_dir=tmp_path / "runs",
            output_dir=tmp_path / "paper",
        )


def test_paper_export_allowlist_ignores_unselected_legacy_runs(tmp_path: Path) -> None:
    selected = tmp_path / "runs" / "selected-run"
    selected.mkdir(parents=True)
    (selected / "metrics.json").write_text("{}\n", encoding="utf-8")
    write_integrity_manifest(selected)
    legacy = tmp_path / "runs" / "legacy-run"
    legacy.mkdir()
    (legacy / "metrics.json").write_text("{}\n", encoding="utf-8")

    exported = export_paper_assets(
        dataset_dir=tmp_path / "datasets",
        runs_dir=tmp_path / "runs",
        output_dir=tmp_path / "paper",
        run_ids={"selected-run"},
    )

    manifest = json.loads(
        (exported.output_dir / "paper_export_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["selected_run_ids"] == ["selected-run"]
    assert set(manifest["run_integrity"]) == {"selected-run"}
