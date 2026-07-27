"""Export manuscript-ready tables and lightweight figures."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from selfauditbench.adapters.io import read_scenarios
from selfauditbench.evaluation.datasets import headline_eligibility
from selfauditbench.evaluation.evidence import (
    AGENT_TESTING_AGENT_SAFETY,
    ANNOTATION_STUDY_RELIABILITY,
    BROKER_GUARD_BEHAVIOR,
    ENACTED_CLOSED_LOOP_RECOVERY,
    LABEL_SURFACE_DIAGNOSTICS,
    MODEL_AUDIT_QUALITY,
    PROVIDER_API_STRESS,
    SCHEMA_RELIABILITY,
    metric_claim_use,
)
from selfauditbench.evaluation.statistics import ratio_confidence_intervals, wilson_interval
from selfauditbench.evaluation.supplementary import normalize_run_gates
from selfauditbench.storage.artifacts import verify_integrity_manifest
from selfauditbench.storage.hashing import sha256_file, sha256_json


@dataclass(frozen=True)
class DatasetSummary:
    dataset: str
    file: str
    scenarios: int
    risky: int
    benign: int
    unlabeled: int
    weak_labels: int
    events: int
    headline_status: str
    false_alarm_denominator_valid: bool

    @property
    def avg_events(self) -> float:
        return self.events / self.scenarios if self.scenarios else 0.0


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    surface: str
    strategy: str
    audit_mode: str
    headline_status: str
    false_alarm_claim_use: str
    analysis_role: str
    confidence_intervals: dict[str, dict[str, int | float | None]]
    ratios: dict[str, dict[str, int | float | None]]
    by_surface: dict[str, dict[str, Any]]
    eligibility: dict[str, Any]
    total: int
    complete: int
    schema_errors: int
    task_completion: float | None
    schema_compliance: float | None
    valid_audit_coverage: float | None
    guard_pause_rate: float | None
    early_detection: float | None
    model_early_detection: float | None
    first_prefix_recall: float | None
    model_first_prefix_recall: float | None
    false_alarm_rate: float | None
    model_false_alarm_rate: float | None
    guard_false_alarm_rate: float | None
    prefix_exact_f1: float | None
    model_prefix_exact_f1: float | None
    prefix_false_alarm_rate: float | None
    prefix_step_accuracy: float | None
    brier_score: float | None


@dataclass(frozen=True)
class SupplementaryRunSummary:
    run_id: str
    provider: str
    model: str
    gate_decision: str
    backend_ready_for_full_run: bool
    dataset_claim_status: str
    analysis_role: str
    headline_semantic_candidate: bool
    pipeline_completion: dict[str, int | float | None]
    wall_time_seconds: float | None
    api_attempts: int
    repair_attempts: int
    api_time_seconds: float | None
    api_time_seconds_per_scenario: float | None
    total_tokens: int | None
    token_cost_proxy_units: int | None
    token_cost_proxy_basis: str
    token_cost_proxy_units_per_scenario: float | None
    estimated_cost_usd: float | None
    token_usage_coverage: dict[str, int | float | None]
    scenario_failure_counts: dict[str, int]
    audit_failure_counts: dict[str, int]
    safety_event_count: int
    safety_behavior_counts: dict[str, int]
    scenario_failure_types: str
    audit_failure_types: str
    safety_behaviors: str


@dataclass(frozen=True)
class ClosedLoopRunSummary:
    run_id: str
    surface: str
    condition: str
    scenarios: int
    exposed: int
    recovery_success: float | None
    safety_success: float | None
    task_success: float | None
    safe_task_success: float | None
    risky_harm_avoidance: float | None
    benign_task_success: float | None
    benign_noninterference: float | None
    permission_compliance: float | None
    no_repeated_denial: float | None
    judge_coverage: float | None
    mean_replans: float | None
    mean_recovery_steps: float | None
    executed_actions: int
    denied_actions: int
    ratio_records: dict[str, dict[str, int | float | None]]
    confidence_intervals: dict[str, dict[str, int | float | None]]


@dataclass(frozen=True)
class PaperExport:
    output_dir: Path
    files: tuple[Path, ...]


@dataclass(frozen=True)
class AnnotationEvidenceSummary:
    status: str
    path: Path | None
    manifest_sha256: str | None
    manifest: dict[str, Any]


STALE_SVG_FIGURES = (
    "fig_framework_pipeline.svg",
    "fig_dataset_inventory.svg",
    "fig_run_reliability.svg",
    "fig_agentforesight_prefix_metrics.svg",
)


def export_paper_assets(
    dataset_dir: Path,
    runs_dir: Path,
    output_dir: Path,
    agentforesight_results_json: Path | None = None,
    include_smoke: bool = False,
    annotation_evidence_json: Path | None = None,
    run_ids: set[str] | None = None,
) -> PaperExport:
    """Create paper-facing tables and figures from normalized artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    figures_dir = output_dir / "figures"
    tables_dir.mkdir(exist_ok=True)
    figures_dir.mkdir(exist_ok=True)
    _remove_stale_svg_figures(figures_dir)

    written: list[Path] = []
    run_integrity = _verify_paper_run_inputs(
        runs_dir,
        include_smoke=include_smoke,
        run_ids=run_ids,
    )
    dataset_summaries = summarize_datasets(dataset_dir)
    run_summaries = summarize_runs(
        runs_dir,
        include_smoke=include_smoke,
        run_ids=run_ids,
    )
    supplementary_summaries = summarize_supplementary_runs(
        runs_dir,
        include_smoke=include_smoke,
        run_ids=run_ids,
    )
    closed_loop_summaries = summarize_closed_loop_runs(
        runs_dir,
        include_smoke=include_smoke,
        run_ids=run_ids,
    )
    annotation_evidence = summarize_annotation_evidence(
        dataset_dir,
        annotation_evidence_json=annotation_evidence_json,
    )

    written.extend(_write_dataset_tables(tables_dir, dataset_summaries))
    written.extend(_write_run_tables(tables_dir, run_summaries))
    written.extend(_write_separated_result_tables(tables_dir, run_summaries))
    written.extend(_write_label_semantics_tables(tables_dir))
    written.extend(_write_annotation_study_tables(tables_dir, annotation_evidence))
    if closed_loop_summaries:
        written.extend(_write_closed_loop_tables(tables_dir, closed_loop_summaries))
    if supplementary_summaries:
        written.extend(_write_supplementary_run_tables(tables_dir, supplementary_summaries))
        written.extend(
            _write_separated_supplementary_tables(tables_dir, supplementary_summaries)
        )

    af_domains: list[dict[str, str]] = []
    if agentforesight_results_json is None:
        agentforesight_results_json = _default_agentforesight_results_path(dataset_dir)
    if agentforesight_results_json is not None and agentforesight_results_json.exists():
        af_domains = agentforesight_domain_rows(agentforesight_results_json)
        written.extend(_write_agentforesight_tables(tables_dir, af_domains))

    written.append(_write_framework_figure_pdf(figures_dir / "fig_framework_pipeline.pdf"))
    if dataset_summaries:
        written.append(
            _write_bar_chart_pdf(
                figures_dir / "fig_dataset_inventory.pdf",
                "Normalized Scenario Inventory",
                [(item.dataset, float(item.scenarios)) for item in dataset_summaries],
                y_label="Scenarios",
                percent=False,
            )
        )
        written.append(
            _write_label_composition_pdf(
                figures_dir / "fig_dataset_label_composition.pdf",
                dataset_summaries,
            )
        )
    if run_summaries:
        written.append(
            _write_reliability_figure_pdf(
                figures_dir / "fig_run_reliability.pdf",
                run_summaries,
            )
        )
        written.append(
            _write_metric_matrix_pdf(figures_dir / "fig_run_metric_matrix.pdf", run_summaries)
        )
    if closed_loop_summaries:
        written.append(
            _write_bar_chart_pdf(
                figures_dir / "fig_closed_loop_safety_task.pdf",
                "Enacted Closed-Loop Safety and Task Outcomes",
                [
                    (f"{item.run_id}: safety", item.safety_success)
                    for item in closed_loop_summaries
                    if item.safety_success is not None
                ]
                + [
                    (f"{item.run_id}: task", item.task_success)
                    for item in closed_loop_summaries
                    if item.task_success is not None
                ]
                + [
                    (f"{item.run_id}: joint", item.safe_task_success)
                    for item in closed_loop_summaries
                    if item.safe_task_success is not None
                ],
                y_label="Rate",
                percent=True,
            )
        )
        written.append(
            _write_bar_chart_pdf(
                figures_dir / "fig_closed_loop_replan_burden.pdf",
                "Closed-Loop Recovery Burden",
                [
                    (item.run_id, item.mean_replans)
                    for item in closed_loop_summaries
                    if item.mean_replans is not None
                ],
                y_label="Mean replans per exposed scenario",
                percent=False,
            )
        )
    if af_domains:
        written.append(
            _write_grouped_agentforesight_figure_pdf(
                figures_dir / "fig_agentforesight_prefix_metrics.pdf",
                af_domains,
            )
        )

    written.append(
        _write_index(
            output_dir,
            dataset_summaries,
            run_summaries,
            af_domains,
            supplementary_summaries,
            annotation_evidence,
            closed_loop_summaries,
        )
    )
    file_entries = {
        str(path.relative_to(output_dir)): {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in written
    }
    written.append(
        _write_json(
            output_dir / "paper_export_manifest.json",
            {
                "dataset_dir": str(dataset_dir),
                "runs_dir": str(runs_dir),
                "agentforesight_results_json": (
                    str(agentforesight_results_json) if agentforesight_results_json else None
                ),
                "annotation_evidence_json": (
                    str(annotation_evidence.path) if annotation_evidence.path else None
                ),
                "annotation_evidence_status": annotation_evidence.status,
                "include_smoke": include_smoke,
                "selected_run_ids": sorted(run_ids) if run_ids is not None else None,
                "run_integrity": run_integrity,
                "files": file_entries,
                "root_digest": sha256_json(file_entries),
            },
        )
    )
    return PaperExport(output_dir=output_dir, files=tuple(written))


def _remove_stale_svg_figures(figures_dir: Path) -> None:
    for name in STALE_SVG_FIGURES:
        path = figures_dir / name
        if path.exists():
            path.unlink()


def summarize_annotation_evidence(
    dataset_dir: Path,
    *,
    annotation_evidence_json: Path | None = None,
) -> AnnotationEvidenceSummary:
    """Load one annotation-study manifest without synthesizing missing evidence."""

    selected = annotation_evidence_json
    if selected is None:
        candidates = sorted(dataset_dir.glob("*.annotation_evidence.json"))
        if not candidates:
            return AnnotationEvidenceSummary(
                status="unavailable_no_manifest",
                path=None,
                manifest_sha256=None,
                manifest={},
            )
        if len(candidates) > 1:
            return AnnotationEvidenceSummary(
                status="unavailable_ambiguous_manifests",
                path=None,
                manifest_sha256=None,
                manifest={},
            )
        selected = candidates[0]
    if not selected.is_file():
        return AnnotationEvidenceSummary(
            status="unavailable_missing_manifest",
            path=selected,
            manifest_sha256=None,
            manifest={},
        )
    try:
        manifest = _read_json(selected)
    except (OSError, ValueError, json.JSONDecodeError):
        return AnnotationEvidenceSummary(
            status="unavailable_invalid_manifest",
            path=selected,
            manifest_sha256=sha256_file(selected),
            manifest={},
        )
    agreement = manifest.get("agreement")
    file_hashes = manifest.get("file_hashes_sha256")
    required_file_hashes = {
        "packet_scenarios",
        "private_mapping",
        "annotator_a",
        "annotator_b",
        "adjudication",
        "final_dataset",
    }
    required_ratio_records = {
        "exact_label_agreement_rate",
        "risk_label_agreement_counts",
        "first_risk_event_exact_agreement_counts",
        "harm_boundary_exact_agreement_counts",
        "minimal_delta_exact_agreement_counts",
    }
    required_agreement_fields = {
        "completed_by_both",
        "risk_label_agreement",
        "risk_label_cohen_kappa",
        "first_risk_event_exact_agreement",
        "harm_boundary_exact_agreement",
        "accepted_intervention_jaccard",
        "accepted_intervention_jaccard_n",
        "minimal_delta_exact_agreement",
    }
    complete_fields = (
        isinstance(agreement, dict)
        and required_agreement_fields <= set(agreement)
        and all(isinstance(agreement.get(name), dict) for name in required_ratio_records)
        and isinstance(manifest.get("scenario_count"), int)
        and manifest["scenario_count"] > 0
        and isinstance(manifest.get("pair_count"), int)
        and manifest["pair_count"] > 0
        and isinstance(manifest.get("unresolved_count"), int)
        and _is_sha256(manifest.get("label_evidence_sha256"))
        and isinstance(file_hashes, dict)
        and all(_is_sha256(file_hashes.get(name)) for name in required_file_hashes)
    )
    return AnnotationEvidenceSummary(
        status="available_complete" if complete_fields else "available_incomplete",
        path=selected,
        manifest_sha256=sha256_file(selected),
        manifest=manifest,
    )


def summarize_datasets(dataset_dir: Path) -> list[DatasetSummary]:
    """Summarize every normalized scenario JSONL under a directory."""

    summaries: list[DatasetSummary] = []
    for path in sorted(dataset_dir.glob("*.jsonl")):
        scenarios = read_scenarios(path)
        by_dataset: dict[str, list[Any]] = {}
        for scenario in scenarios:
            by_dataset.setdefault(scenario.source_dataset, []).append(scenario)
        for dataset, values in sorted(by_dataset.items()):
            risky = 0
            benign = 0
            unlabeled = 0
            weak = 0
            events = 0
            for scenario in values:
                events += len(scenario.events)
                weak += int(scenario.weak_label)
                if scenario.label is None:
                    unlabeled += 1
                elif scenario.label.risky:
                    risky += 1
                else:
                    benign += 1
            eligibility = headline_eligibility(values)
            summaries.append(
                DatasetSummary(
                    dataset=dataset,
                    file=path.as_posix(),
                    scenarios=len(values),
                    risky=risky,
                    benign=benign,
                    unlabeled=unlabeled,
                    weak_labels=weak,
                    events=events,
                    headline_status=str(eligibility["status"]),
                    false_alarm_denominator_valid=bool(
                        eligibility["false_alarm_denominator_valid"]
                    ),
                )
            )
    return summaries


def _verify_paper_run_inputs(
    runs_dir: Path,
    *,
    include_smoke: bool,
    run_ids: set[str] | None,
) -> dict[str, dict[str, Any]]:
    candidates = {
        path.parent
        for pattern in ("*/metrics.json", "*/supplementary_reliability.json")
        for path in runs_dir.glob(pattern)
        if include_smoke or "smoke" not in path.parent.name.lower()
        if run_ids is None or path.parent.name in run_ids
    }
    if run_ids is not None:
        missing = sorted(run_ids - {path.name for path in candidates})
        if missing:
            raise ValueError(
                "paper export run allowlist did not resolve: " + ", ".join(missing)
            )
    verified: dict[str, dict[str, Any]] = {}
    rejected: list[str] = []
    for run_dir in sorted(candidates):
        integrity = verify_integrity_manifest(run_dir)
        status = str(integrity.get("status") or "unknown")
        if status == "verified" and integrity.get("verified") is True:
            verified[run_dir.name] = {
                "status": status,
                "root_digest": integrity.get("root_digest"),
            }
            continue
        errors = integrity.get("errors")
        detail = (
            "; ".join(str(item) for item in errors)
            if isinstance(errors, list) and errors
            else "verification did not succeed"
        )
        rejected.append(f"{run_dir} (status={status}): {detail}")
    if rejected:
        raise ValueError(
            "paper export rejected unverified run inputs "
            f"(verified={len(verified)}, rejected={len(rejected)}): "
            + " | ".join(rejected)
        )
    return dict(sorted(verified.items()))


def summarize_runs(
    runs_dir: Path,
    *,
    include_smoke: bool = False,
    run_ids: set[str] | None = None,
) -> list[RunSummary]:
    """Summarize every run directory with a metrics.json file."""

    summaries: list[RunSummary] = []
    for metrics_path in sorted(runs_dir.glob("*/metrics.json")):
        run_dir = metrics_path.parent
        if not include_smoke and "smoke" in run_dir.name.lower():
            continue
        if run_ids is not None and run_dir.name not in run_ids:
            continue
        integrity = verify_integrity_manifest(run_dir)
        _require_verified_paper_run(run_dir, integrity)
        metrics = _read_json(metrics_path)
        manifest = _read_optional_json(run_dir / "manifest.json")
        if manifest.get("execution_semantics") == "enacted_closed_loop_recovery":
            continue
        supplementary = _read_optional_json(run_dir / "supplementary_reliability.json")
        eligibility = supplementary.get("dataset", {}).get("headline_eligibility", {})
        surface = _surface_label(supplementary)
        gates = normalize_run_gates(supplementary)
        reliability = metrics.get("execution_reliability", {})
        statuses = reliability.get("statuses", {})
        prefix = metrics.get("prefix_localization", {})
        model_prefix = metrics.get("model_prefix_localization", {})
        summaries.append(
            RunSummary(
                run_id=str(manifest.get("run_id") or run_dir.name),
                surface=surface,
                strategy=str(manifest.get("strategy") or "unknown"),
                audit_mode=str(manifest.get("audit_mode") or "unknown"),
                headline_status=str(eligibility.get("status") or "unknown"),
                false_alarm_claim_use=metric_claim_use(
                    "model_false_alarm_rate", eligibility
                ),
                analysis_role=str(gates.get("analysis_role") or "unknown"),
                confidence_intervals=ratio_confidence_intervals(metrics),
                ratios=_ratio_records(metrics),
                by_surface=_metrics_by_surface(metrics),
                eligibility=dict(eligibility),
                total=int(reliability.get("total") or 0),
                complete=int(statuses.get("complete") or 0),
                schema_errors=int(statuses.get("schema_error") or 0),
                task_completion=_ratio_value(reliability.get("task_completion")),
                schema_compliance=_ratio_value(reliability.get("schema_compliance")),
                valid_audit_coverage=_ratio_value(metrics.get("valid_audit_coverage")),
                guard_pause_rate=_ratio_value(metrics.get("guard_triggered_pause_rate")),
                early_detection=_ratio_value(metrics.get("early_risk_detection_rate")),
                model_early_detection=_ratio_value(
                    metrics.get("model_generated_early_detection_rate")
                ),
                first_prefix_recall=_ratio_value(metrics.get("first_sufficient_prefix_recall")),
                model_first_prefix_recall=_ratio_value(
                    metrics.get("model_generated_first_sufficient_prefix_recall")
                ),
                false_alarm_rate=_ratio_value(metrics.get("false_alarm_rate")),
                model_false_alarm_rate=_ratio_value(metrics.get("model_false_alarm_rate")),
                guard_false_alarm_rate=_ratio_value(metrics.get("guard_false_alarm_rate")),
                prefix_exact_f1=_float_or_none(prefix.get("exact_f1")),
                model_prefix_exact_f1=_float_or_none(model_prefix.get("exact_f1")),
                prefix_false_alarm_rate=_float_or_none(prefix.get("false_alarm_rate")),
                prefix_step_accuracy=_float_or_none(prefix.get("step_accuracy")),
                brier_score=_float_or_none(metrics.get("brier_score")),
            )
        )
    return summaries


def summarize_supplementary_runs(
    runs_dir: Path,
    *,
    include_smoke: bool = False,
    run_ids: set[str] | None = None,
) -> list[SupplementaryRunSummary]:
    summaries: list[SupplementaryRunSummary] = []
    for summary_path in sorted(runs_dir.glob("*/supplementary_reliability.json")):
        run_dir = summary_path.parent
        if not include_smoke and "smoke" in run_dir.name.lower():
            continue
        if run_ids is not None and run_dir.name not in run_ids:
            continue
        _require_verified_paper_run(run_dir, verify_integrity_manifest(run_dir))
        summary = _read_json(summary_path)
        api = summary.get("api", {})
        failures = summary.get("failure_distribution", {})
        safety = summary.get("agent_testing_agent_safety", {})
        model_vs_guard = summary.get("model_vs_guard", {})
        pipeline_completion = _ratio_dict(model_vs_guard.get("task_completion"))
        if not pipeline_completion:
            run_metrics = _read_optional_json(run_dir / "metrics.json")
            pipeline_completion = _ratio_dict(
                run_metrics.get("execution_reliability", {}).get("task_completion")
            )
        gates = normalize_run_gates(summary)
        recovery_model = summary.get("closed_loop_models", {}).get("recovery")
        recovery_model = recovery_model if isinstance(recovery_model, dict) else {}
        summaries.append(
            SupplementaryRunSummary(
                run_id=str(summary.get("run_id") or run_dir.name),
                provider=str(
                    summary.get("provider")
                    or recovery_model.get("provider")
                    or "unknown"
                ),
                model=str(
                    summary.get("model")
                    or recovery_model.get("model")
                    or "unknown"
                ),
                gate_decision=str(gates.get("decision") or "unknown"),
                backend_ready_for_full_run=bool(
                    gates.get("backend_ready_for_full_run", False)
                ),
                dataset_claim_status=str(gates.get("dataset_claim_status") or "unknown"),
                analysis_role=str(gates.get("analysis_role") or "unknown"),
                headline_semantic_candidate=bool(
                    gates.get("headline_semantic_candidate", False)
                ),
                pipeline_completion=pipeline_completion,
                wall_time_seconds=_float_or_none(summary.get("wall_time_seconds")),
                api_attempts=int(api.get("call_attempts") or 0),
                repair_attempts=int(api.get("repair_attempts") or 0),
                api_time_seconds=_float_or_none(api.get("api_time_seconds")),
                api_time_seconds_per_scenario=_float_or_none(
                    api.get("api_seconds_per_scenario")
                ),
                total_tokens=_int_or_none(api.get("total_tokens")),
                token_cost_proxy_units=_int_or_none(api.get("token_cost_proxy_units")),
                token_cost_proxy_basis=str(api.get("token_cost_proxy_basis") or "unknown"),
                token_cost_proxy_units_per_scenario=_float_or_none(
                    api.get("token_cost_proxy_units_per_scenario")
                ),
                estimated_cost_usd=_float_or_none(api.get("estimated_cost_usd")),
                token_usage_coverage=_ratio_dict(api.get("token_usage_coverage")),
                scenario_failure_counts=_int_dict(failures.get("scenario_failure_types")),
                audit_failure_counts=_int_dict(failures.get("audit_attempt_failure_types")),
                safety_event_count=int(safety.get("event_count") or 0),
                safety_behavior_counts=_int_dict(safety.get("behavior_counts")),
                scenario_failure_types=_compact_json(failures.get("scenario_failure_types")),
                audit_failure_types=_compact_json(failures.get("audit_attempt_failure_types")),
                safety_behaviors=_compact_json(safety.get("behavior_counts")),
            )
        )
    return summaries


def summarize_closed_loop_runs(
    runs_dir: Path,
    *,
    include_smoke: bool = False,
    run_ids: set[str] | None = None,
) -> list[ClosedLoopRunSummary]:
    """Collect enacted recovery measures from verified run artifacts."""

    summaries: list[ClosedLoopRunSummary] = []
    for metrics_path in sorted(runs_dir.glob("*/metrics.json")):
        run_dir = metrics_path.parent
        if not include_smoke and "smoke" in run_dir.name.lower():
            continue
        if run_ids is not None and run_dir.name not in run_ids:
            continue
        manifest = _read_optional_json(run_dir / "manifest.json")
        if manifest.get("execution_semantics") != "enacted_closed_loop_recovery":
            continue
        integrity = verify_integrity_manifest(run_dir)
        _require_verified_paper_run(run_dir, integrity)
        metrics = _read_json(metrics_path)
        values = metrics.get("closed_loop_recovery")
        if not isinstance(values, dict):
            continue
        by_surface = values.get("by_surface")
        surfaces = sorted(by_surface) if isinstance(by_surface, dict) else []
        summaries.append(
            ClosedLoopRunSummary(
                run_id=str(manifest.get("run_id") or run_dir.name),
                surface=", ".join(surfaces) if surfaces else "unknown",
                condition=str(manifest.get("closed_loop_condition") or "unknown"),
                scenarios=int(values.get("scenario_count") or 0),
                exposed=int(values.get("recovery_attempt_count") or 0),
                recovery_success=_ratio_value(values.get("recovery_success_rate")),
                safety_success=_ratio_value(values.get("safety_success_rate")),
                task_success=_ratio_value(values.get("task_success_rate")),
                safe_task_success=_ratio_value(values.get("safe_task_success_rate")),
                risky_harm_avoidance=_ratio_value(values.get("risky_harm_avoidance_rate")),
                benign_task_success=_ratio_value(values.get("benign_task_success_rate")),
                benign_noninterference=_ratio_value(values.get("benign_noninterference_rate")),
                permission_compliance=_ratio_value(values.get("permission_compliance_rate")),
                no_repeated_denial=_ratio_value(values.get("no_repeated_denied_action_rate")),
                judge_coverage=_ratio_value(values.get("outcome_judge_coverage")),
                mean_replans=_float_or_none(values.get("mean_replans_per_exposed_scenario")),
                mean_recovery_steps=_float_or_none(
                    values.get("mean_recovery_steps_per_exposed_scenario")
                ),
                executed_actions=int(values.get("executed_actions") or 0),
                denied_actions=int(values.get("denied_actions") or 0),
                ratio_records={
                    name: ratio
                    for name, value in values.items()
                    if (ratio := _ratio_dict(value))
                },
                confidence_intervals=ratio_confidence_intervals(
                    {"closed_loop_recovery": values}
                ),
            )
        )
    return summaries


def _write_closed_loop_tables(
    output_dir: Path, summaries: list[ClosedLoopRunSummary]
) -> list[Path]:
    headers = [
        "Evidence class",
        "Run",
        "Surface",
        "Condition",
        "n",
        "Exposed",
        "Recovery success",
        "Safety",
        "Task",
        "Safe-task",
        "Risky harm avoidance",
        "Benign task",
        "Benign noninterference",
        "Permission compliance",
        "No repeated denial",
        "Judge coverage",
        "Mean replans",
        "Mean recovery steps",
        "Executed actions",
        "Denied actions",
    ]
    rows = [
        [
            ENACTED_CLOSED_LOOP_RECOVERY,
            item.run_id,
            item.surface,
            item.condition,
            str(item.scenarios),
            str(item.exposed),
            _format_percent(item.recovery_success),
            _format_percent(item.safety_success),
            _format_percent(item.task_success),
            _format_percent(item.safe_task_success),
            _format_percent(item.risky_harm_avoidance),
            _format_percent(item.benign_task_success),
            _format_percent(item.benign_noninterference),
            _format_percent(item.permission_compliance),
            _format_percent(item.no_repeated_denial),
            _format_percent(item.judge_coverage),
            _format_float(item.mean_replans),
            _format_float(item.mean_recovery_steps),
            str(item.executed_actions),
            str(item.denied_actions),
        ]
        for item in summaries
    ]
    written = _write_table_bundle(
        output_dir / "closed_loop_recovery_results",
        headers,
        rows,
        "Enacted broker-feedback recovery with sink-gated actions and judged outcomes.",
        "tab:closed-loop-recovery-results",
    )
    metric_headers = [
        "Evidence class",
        "Run",
        "Surface",
        "Condition",
        "Metric",
        "Value",
        "95% CI",
        "Numerator",
        "Denominator",
    ]
    metric_rows: list[list[str]] = []
    for item in summaries:
        for name, record in sorted(item.ratio_records.items()):
            interval = item.confidence_intervals.get(f"closed_loop_recovery.{name}")
            metric_rows.append(
                [
                    ENACTED_CLOSED_LOOP_RECOVERY,
                    item.run_id,
                    item.surface,
                    item.condition,
                    name,
                    _format_percent(_ratio_value(record)),
                    _format_interval_only(interval),
                    _format_int(_int_or_none(record.get("numerator"))),
                    _format_int(_int_or_none(record.get("denominator"))),
                ]
            )
    written.extend(
        _write_table_bundle(
            output_dir / "closed_loop_metric_records",
            metric_headers,
            metric_rows,
            "Closed-loop ratio records with explicit denominators and Wilson intervals.",
            "tab:closed-loop-metric-records",
        )
    )
    return written


def agentforesight_domain_rows(results_json: Path) -> list[dict[str, str]]:
    """Extract the official AgentForesight by-domain result table."""

    result = _read_json(results_json)
    by_domain = result.get("by_domain", {})
    rows: list[dict[str, str]] = []
    order = ["Math", "Coding", "Agentic", "overall"]
    for domain in order:
        metrics = by_domain.get(domain)
        if isinstance(metrics, dict):
            rows.append(_agentforesight_domain_row(domain, metrics))
    for domain, metrics in sorted(by_domain.items()):
        if domain not in order and isinstance(metrics, dict):
            rows.append(_agentforesight_domain_row(domain, metrics))
    return rows


def _agentforesight_domain_row(domain: str, metrics: dict[str, Any]) -> dict[str, str]:
    return {
        "Domain": "Overall" if domain == "overall" else domain,
        "n": str(metrics.get("n", "")),
        "Safe": str(metrics.get("n_safe", "")),
        "Unsafe": str(metrics.get("n_unsafe", "")),
        "Exact-F1": _format_percent(_percent_to_unit(metrics.get("exact_f1"))),
        "ASS": _format_float(_float_or_none(metrics.get("ass_mean"))),
        "FAR": _format_percent(_percent_to_unit(metrics.get("far"))),
        "StepAcc": _format_percent(_percent_to_unit(metrics.get("step_acc"))),
    }


def _write_dataset_tables(output_dir: Path, summaries: list[DatasetSummary]) -> list[Path]:
    headers = [
        "Evidence class",
        "Dataset",
        "File",
        "Scenarios",
        "Risky",
        "Benign",
        "Unlabeled",
        "Weak labels",
        "Events",
        "Avg events",
        "Headline status",
        "False-alarm headline valid",
    ]
    rows = [
        [
            LABEL_SURFACE_DIAGNOSTICS,
            item.dataset,
            item.file,
            str(item.scenarios),
            str(item.risky),
            str(item.benign),
            str(item.unlabeled),
            str(item.weak_labels),
            str(item.events),
            _format_float(item.avg_events),
            item.headline_status,
            "yes" if item.false_alarm_denominator_valid else "no",
        ]
        for item in summaries
    ]
    return _write_table_bundle(
        output_dir / "dataset_inventory",
        headers,
        rows,
        "Label-surface diagnostics with headline eligibility flags.",
        "tab:dataset-inventory",
    )


def _write_run_tables(output_dir: Path, summaries: list[RunSummary]) -> list[Path]:
    headers = [
        "Run",
        "Surface",
        "Strategy",
        "Mode",
        "Label status",
        "Analysis role",
        "False-alarm claim use",
        "n",
        "Complete",
        "Schema errors",
        "Schema: audit-pipeline completion",
        "Schema: compliance",
        "Model: valid audit",
        "Broker: guard pause",
        "Broker: recorded-action early",
        "Model: early",
        "Broker: recorded-action prefix recall",
        "Model: prefix recall",
        "Broker: recorded-action false alarm",
        "Model: false alarm",
        "Broker: guard false alarm",
        "Label: Prefix Exact-F1",
        "Label: Model Prefix Exact-F1",
        "Label: Prefix FAR",
        "Label: Prefix StepAcc",
        "Model: Brier",
    ]
    rows = [
        [
            item.run_id,
            item.surface,
            item.strategy,
            item.audit_mode,
            item.headline_status,
            item.analysis_role,
            item.false_alarm_claim_use,
            str(item.total),
            str(item.complete),
            str(item.schema_errors),
            _format_percent_interval(
                item.task_completion, item.confidence_intervals.get("task_completion")
            ),
            _format_percent_interval(
                item.schema_compliance,
                item.confidence_intervals.get("schema_compliance"),
            ),
            _format_percent_interval(
                item.valid_audit_coverage,
                item.confidence_intervals.get("valid_audit_coverage"),
            ),
            _format_percent_interval(
                item.guard_pause_rate,
                item.confidence_intervals.get("guard_triggered_pause_rate"),
            ),
            _format_percent_interval(
                item.early_detection,
                item.confidence_intervals.get("early_risk_detection_rate"),
            ),
            _format_percent_interval(
                item.model_early_detection,
                item.confidence_intervals.get("model_generated_early_detection_rate"),
            ),
            _format_percent_interval(
                item.first_prefix_recall,
                item.confidence_intervals.get("first_sufficient_prefix_recall"),
            ),
            _format_percent_interval(
                item.model_first_prefix_recall,
                item.confidence_intervals.get(
                    "model_generated_first_sufficient_prefix_recall"
                ),
            ),
            _format_claim_metric(
                item.false_alarm_rate,
                item.false_alarm_claim_use,
                item.confidence_intervals.get("false_alarm_rate"),
            ),
            _format_claim_metric(
                item.model_false_alarm_rate,
                item.false_alarm_claim_use,
                item.confidence_intervals.get("model_false_alarm_rate"),
            ),
            _format_claim_metric(
                item.guard_false_alarm_rate,
                item.false_alarm_claim_use,
                item.confidence_intervals.get("guard_false_alarm_rate"),
            ),
            _format_percent(item.prefix_exact_f1),
            _format_percent(item.model_prefix_exact_f1),
            _format_percent(item.prefix_false_alarm_rate),
            _format_percent(item.prefix_step_accuracy),
            _format_float(item.brier_score),
        ]
        for item in summaries
    ]
    return _write_table_bundle(
        output_dir / "run_metrics_summary",
        headers,
        rows,
        (
            "Run metrics labeled by model audit quality, broker guard behavior, schema "
            "reliability, and label-surface diagnostics."
        ),
        "tab:run-metrics",
    )


def _write_separated_result_tables(
    output_dir: Path,
    summaries: list[RunSummary],
) -> list[Path]:
    """Write model, contract, and broker estimands without conflating them."""

    written: list[Path] = []
    common = ["Run", "Surface", "Label status", "Analysis role"]

    model_headers = [
        *common,
        "Evidence class",
        "Evaluation scope",
        "Model early detection",
        "Early 95% CI",
        "Early numerator",
        "Early denominator",
        "Early claim use",
        "Model false alarm",
        "False-alarm 95% CI",
        "False-alarm numerator",
        "False-alarm denominator",
        "False-alarm claim use",
        "Accepted intervention",
        "Accepted-intervention 95% CI",
        "Accepted-intervention numerator",
        "Accepted-intervention denominator",
        "Accepted-intervention claim use",
        "Flagged-audit evidence coverage",
        "Evidence-coverage 95% CI",
        "Evidence-coverage numerator",
        "Evidence-coverage denominator",
        "Evidence-coverage claim use",
        "Intended-action binding",
        "Binding 95% CI",
        "Binding numerator",
        "Binding denominator",
        "Binding claim use",
    ]
    model_rows = [
        [
            *_run_identity_cells(item, surface),
            MODEL_AUDIT_QUALITY,
            "full recorded trace",
            *_metric_cells(
                item,
                "model_generated_early_detection_rate",
                ratios=ratios,
                intervals=intervals,
                surface=surface,
            ),
            *_metric_cells(
                item,
                "model_false_alarm_rate",
                ratios=ratios,
                intervals=intervals,
                surface=surface,
            ),
            *_metric_cells(
                item,
                "model_intervention_acceptability_rate",
                ratios=ratios,
                intervals=intervals,
                surface=surface,
            ),
            *_metric_cells(
                item,
                "flagged_audit_evidence_coverage",
                ratios=ratios,
                intervals=intervals,
                surface=surface,
            ),
            *_metric_cells(
                item,
                "intended_action_binding_rate",
                ratios=ratios,
                intervals=intervals,
                surface=surface,
            ),
        ]
        for item, surface, ratios, intervals in _surface_views(summaries)
    ]
    written.extend(
        _write_table_bundle(
            output_dir / "model_audit_results",
            model_headers,
            model_rows,
            (
                "Model-generated recorded-trace audit quality. Fail-closed schema-guard "
                "audits are excluded; a model false alarm is a medium-or-higher model "
                "risk flag on an adjudicated benign trajectory."
            ),
            "tab:model-audit-results",
        )
    )

    schema_headers = [
        *common,
        "Evidence classes",
        "Valid-audit coverage",
        "Valid-audit 95% CI",
        "Valid-audit numerator",
        "Valid-audit denominator",
        "Valid-audit claim use",
        "Schema compliance",
        "Schema 95% CI",
        "Schema numerator",
        "Schema denominator",
        "Schema claim use",
    ]
    schema_rows = [
        [
            *_run_identity_cells(item, surface),
            f"{MODEL_AUDIT_QUALITY}; {SCHEMA_RELIABILITY}",
            *_metric_cells(
                item,
                "valid_audit_coverage",
                ratios=ratios,
                intervals=intervals,
                surface=surface,
            ),
            *_metric_cells(
                item,
                "schema_compliance",
                ratios=ratios,
                intervals=intervals,
                surface=surface,
            ),
        ]
        for item, surface, ratios, intervals in _surface_views(summaries)
    ]
    written.extend(
        _write_table_bundle(
            output_dir / "audit_schema_results",
            schema_headers,
            schema_rows,
            "Valid-audit coverage and schema compliance with explicit denominators.",
            "tab:audit-schema-results",
        )
    )

    broker_headers = [
        *common,
        "Evidence class",
        "Projection scope",
        "Fail-closed intervention",
        "Intervention 95% CI",
        "Intervention numerator",
        "Intervention denominator",
        "Intervention claim use",
        "Guard pause",
        "Guard-pause 95% CI",
        "Guard-pause numerator",
        "Guard-pause denominator",
        "Guard-pause claim use",
        "Guard false alarm",
        "Guard-FA 95% CI",
        "Guard-FA numerator",
        "Guard-FA denominator",
        "Guard-FA claim use",
        "Terminal harm avoidance",
        "Harm-avoidance 95% CI",
        "Harm-avoidance numerator",
        "Harm-avoidance denominator",
        "Harm-avoidance claim use",
        "Benign noninterference",
        "Noninterference 95% CI",
        "Noninterference numerator",
        "Noninterference denominator",
        "Noninterference claim use",
        "Accepted enforced intervention",
        "Accepted-enforcement 95% CI",
        "Accepted-enforcement numerator",
        "Accepted-enforcement denominator",
        "Accepted-enforcement claim use",
    ]
    broker_rows = [
        [
            *_run_identity_cells(item, surface),
            BROKER_GUARD_BEHAVIOR,
            "absorbing terminal projection",
            *_metric_cells(
                item,
                "fail_closed_intervention_rate",
                ratios=ratios,
                intervals=intervals,
                surface=surface,
            ),
            *_metric_cells(
                item,
                "guard_triggered_pause_rate",
                ratios=ratios,
                intervals=intervals,
                surface=surface,
            ),
            *_metric_cells(
                item,
                "guard_false_alarm_rate",
                ratios=ratios,
                intervals=intervals,
                surface=surface,
            ),
            *_metric_cells(
                item,
                "terminal_projection_harm_avoidance_rate",
                ratios=ratios,
                intervals=intervals,
                surface=surface,
            ),
            *_metric_cells(
                item,
                "benign_noninterference_rate",
                ratios=ratios,
                intervals=intervals,
                surface=surface,
            ),
            *_metric_cells(
                item,
                "enforced_intervention_acceptability_rate",
                ratios=ratios,
                intervals=intervals,
                surface=surface,
            ),
        ]
        for item, surface, ratios, intervals in _surface_views(summaries)
    ]
    written.extend(
        _write_table_bundle(
            output_dir / "broker_guard_results",
            broker_headers,
            broker_rows,
            (
                "Broker and schema-guard results under an absorbing terminal projection "
                "over recorded proposals. Enacted recovery outcomes appear in the "
                "closed-loop table."
            ),
            "tab:broker-guard-results",
        )
    )
    return written


def _write_label_semantics_tables(output_dir: Path) -> list[Path]:
    headers = [
        "Surface",
        "Original label meaning",
        "SelfAuditBench annotations",
        "Risk boundary",
        "Harm boundary",
        "Intervention label",
        "Valid denominator",
        "Evidence class",
        "Claim eligibility",
    ]
    rows = [
        [
            "ASB",
            "Attack/control condition and native attack/task outcomes",
            (
                "Blinded human risk, first-sufficient event, harm event, accepted "
                "interventions, minimal delta"
            ),
            "Earliest observable attack-sufficient checkpoint",
            "Pre-execution tool or memory transition annotated by SelfAuditBench",
            "Human-accepted intervention set and minimal monotonic delta",
            "Source-unique adjudicated ASB attack/control trajectories",
            f"{MODEL_AUDIT_QUALITY}; {BROKER_GUARD_BEHAVIOR}",
            "Recorded-action headline eligible only after adjudication; otherwise diagnostic",
        ],
        [
            "ConVerse",
            "Native privacy/security/benign condition and judge outcome",
            (
                "Blinded human risk, first-sufficient event, harm event, accepted "
                "interventions, minimal delta"
            ),
            "Earliest context-sufficient disclosure or commitment risk checkpoint",
            "Pre-execution disclosure, query, or commitment annotated by SelfAuditBench",
            "Human-accepted intervention set and minimal monotonic delta",
            "Source-unique adjudicated ConVerse attack/control trajectories",
            f"{MODEL_AUDIT_QUALITY}; {BROKER_GUARD_BEHAVIOR}",
            "Recorded-action headline eligible only after adjudication; otherwise diagnostic",
        ],
        [
            "AgentForesight AFTraj",
            "Curated safe/unsafe trajectory and earliest decisive-error step",
            "Observable-prefix normalization and audit-contract reliability",
            "Native decisive-error prefix",
            "Not supplied by native labels",
            "Not supplied; no native minimal permission delta",
            "Official safe/unsafe prefix-labeled trajectories",
            f"{LABEL_SURFACE_DIAGNOSTICS}; {SCHEMA_RELIABILITY}",
            "Prefix localization and reliability only",
        ],
    ]
    return _write_table_bundle(
        output_dir / "label_semantics_claim_eligibility",
        headers,
        rows,
        "Dataset-specific label semantics and the claims each surface can support.",
        "tab:label-semantics-claims",
    )


def _write_annotation_study_tables(
    output_dir: Path,
    evidence: AnnotationEvidenceSummary,
) -> list[Path]:
    headers = [
        "Evidence class",
        "Evidence status",
        "Record",
        "Value or SHA-256",
        "Numerator",
        "Denominator / n",
        "Claim use",
    ]
    if not evidence.manifest:
        rows = [
            [
                ANNOTATION_STUDY_RELIABILITY,
                evidence.status,
                "Annotation-study evidence",
                "unavailable",
                "unavailable",
                "unavailable",
                "not_available_for_manuscript",
            ]
        ]
    else:
        manifest = evidence.manifest
        agreement = manifest.get("agreement")
        agreement = agreement if isinstance(agreement, dict) else {}
        scenario_count = _int_or_none(manifest.get("scenario_count"))
        unresolved = _int_or_none(manifest.get("unresolved_count"))
        completed_by_both = _int_or_none(agreement.get("completed_by_both"))
        study_complete = (
            evidence.status == "available_complete"
            and scenario_count is not None
            and scenario_count > 0
            and completed_by_both == scenario_count
            and unresolved == 0
        )
        agreement_claim = (
            "manuscript_annotation_reliability"
            if study_complete
            else "diagnostic_incomplete_annotation_study"
        )
        provenance = "provenance_only"
        rows = []

        def add(
            record: str,
            value: str,
            numerator: str = "unavailable",
            denominator: str = "unavailable",
            claim_use: str = agreement_claim,
        ) -> None:
            rows.append(
                [
                    ANNOTATION_STUDY_RELIABILITY,
                    evidence.status,
                    record,
                    value,
                    numerator,
                    denominator,
                    claim_use,
                ]
            )

        add(
            "Evidence manifest file",
            evidence.path.name if evidence.path else "unavailable",
            claim_use=provenance,
        )
        add(
            "Evidence manifest SHA-256",
            evidence.manifest_sha256 or "unavailable",
            claim_use=provenance,
        )
        add(
            "Shared label-evidence SHA-256",
            _annotation_sha256(manifest.get("label_evidence_sha256")),
            claim_use=provenance,
        )
        add("Study scenarios", _annotation_integer(scenario_count), claim_use="study_accounting")
        add(
            "Attack-control pairs",
            _annotation_integer(_int_or_none(manifest.get("pair_count"))),
            claim_use="study_accounting",
        )
        add(
            "Surface counts",
            _annotation_json(manifest.get("surface_counts")),
            claim_use="study_accounting",
        )
        add(
            "Completed independently by both annotators",
            _annotation_integer(completed_by_both),
            denominator=_annotation_integer(scenario_count),
            claim_use="study_accounting",
        )
        add(
            "Exact full-label agreement",
            *_annotation_ratio_cells(agreement.get("exact_label_agreement_rate")),
        )
        add(
            "Risk-label agreement",
            *_annotation_ratio_cells(
                agreement.get("risk_label_agreement_counts"),
                explicit_value=agreement.get("risk_label_agreement"),
            ),
        )
        risk_counts = agreement.get("risk_label_agreement_counts")
        risk_counts = risk_counts if isinstance(risk_counts, dict) else {}
        add(
            "Risk-label Cohen kappa",
            _annotation_number(agreement.get("risk_label_cohen_kappa")),
            denominator=_annotation_integer(_int_or_none(risk_counts.get("denominator"))),
        )
        add(
            "First-risk-event exact agreement",
            *_annotation_ratio_cells(
                agreement.get("first_risk_event_exact_agreement_counts"),
                explicit_value=agreement.get("first_risk_event_exact_agreement"),
            ),
        )
        add(
            "Harm-boundary exact agreement",
            *_annotation_ratio_cells(
                agreement.get("harm_boundary_exact_agreement_counts"),
                explicit_value=agreement.get("harm_boundary_exact_agreement"),
            ),
        )
        add(
            "Accepted-intervention Jaccard",
            _annotation_number(agreement.get("accepted_intervention_jaccard")),
            denominator=_annotation_integer(
                _int_or_none(agreement.get("accepted_intervention_jaccard_n"))
            ),
        )
        add(
            "Minimal-delta exact agreement",
            *_annotation_ratio_cells(
                agreement.get("minimal_delta_exact_agreement_counts"),
                explicit_value=agreement.get("minimal_delta_exact_agreement"),
            ),
        )
        add(
            "Unresolved adjudications",
            _annotation_integer(unresolved),
            denominator=_annotation_integer(scenario_count),
            claim_use="must_be_zero_for_final_gold",
        )
        changes = manifest.get("adjudication_changes")
        changes = changes if isinstance(changes, dict) else {}
        for key, label in (
            ("from_annotator_a", "Adjudication changes from annotator A"),
            ("from_annotator_b", "Adjudication changes from annotator B"),
        ):
            add(
                label,
                _annotation_integer(_int_or_none(changes.get(key))),
                denominator=_annotation_integer(scenario_count),
                claim_use="study_accounting",
            )
        hashes = manifest.get("file_hashes_sha256")
        hashes = hashes if isinstance(hashes, dict) else {}
        expected_hashes = {
            "packet_scenarios",
            "private_mapping",
            "annotator_a",
            "annotator_b",
            "adjudication",
            "final_dataset",
        }
        for name in sorted(expected_hashes | set(str(key) for key in hashes)):
            add(
                f"Artifact SHA-256: {name}",
                _annotation_sha256(hashes.get(name)),
                claim_use=provenance,
            )
    return _write_table_bundle(
        output_dir / "annotation_study_evidence",
        headers,
        rows,
        (
            "Independent-annotation agreement, adjudication accounting, and artifact "
            "hashes. Unavailable cells denote missing evidence and never zero results."
        ),
        "tab:annotation-study-evidence",
    )


def _write_agentforesight_tables(output_dir: Path, rows: list[dict[str, str]]) -> list[Path]:
    headers = [
        "Evidence class",
        "Domain",
        "n",
        "Safe",
        "Unsafe",
        "Exact-F1",
        "ASS",
        "FAR",
        "StepAcc",
    ]
    values = [
        [LABEL_SURFACE_DIAGNOSTICS, *[row[header] for header in headers[1:]]]
        for row in rows
    ]
    return _write_table_bundle(
        output_dir / "agentforesight_prefix_by_domain",
        headers,
        values,
        "Prefix-only label-surface diagnostics for the AgentForesight paper split.",
        "tab:agentforesight-prefix",
    )


def _write_supplementary_run_tables(
    output_dir: Path,
    summaries: list[SupplementaryRunSummary],
) -> list[Path]:
    headers = [
        "Evidence classes",
        "Run",
        "Provider",
        "Model",
        "Gate decision",
        "Backend ready",
        "Dataset claim status",
        "Analysis role",
        "Headline semantic",
        "Wall seconds",
        "API attempts",
        "API seconds",
        "Provider tokens",
        "Token-cost proxy",
        "Token basis",
        "Estimated cost USD",
        "Scenario failure types",
        "Audit failure types",
        "Safety behaviors",
    ]
    rows = [
        [
            f"{PROVIDER_API_STRESS}; {AGENT_TESTING_AGENT_SAFETY}",
            item.run_id,
            item.provider,
            item.model,
            item.gate_decision,
            "yes" if item.backend_ready_for_full_run else "no",
            item.dataset_claim_status,
            item.analysis_role,
            "yes" if item.headline_semantic_candidate else "no",
            _format_float(item.wall_time_seconds),
            str(item.api_attempts),
            _format_float(item.api_time_seconds),
            _format_int(item.total_tokens),
            _format_int(item.token_cost_proxy_units),
            item.token_cost_proxy_basis,
            _format_float(item.estimated_cost_usd),
            item.scenario_failure_types,
            item.audit_failure_types,
            item.safety_behaviors,
        ]
        for item in summaries
    ]
    return _write_table_bundle(
        output_dir / "api_reliability_supplement",
        headers,
        rows,
        (
            "Provider/API stress and agent-testing-agent-safety data: runtime, token "
            "accounting, failures, and contained behaviors."
        ),
        "tab:api-reliability-supplement",
    )


def _write_separated_supplementary_tables(
    output_dir: Path,
    summaries: list[SupplementaryRunSummary],
) -> list[Path]:
    written: list[Path] = []

    execution_headers = [
        "Run",
        "Provider",
        "Model",
        "Gate decision",
        "Evidence classes",
        "Audit-pipeline completion",
        "Completion 95% CI",
        "Completion numerator",
        "Completion denominator",
        "Completion claim use",
        "Scenario provider errors",
        "Audit-attempt provider errors",
        "Scenario timeouts",
        "Audit-attempt timeouts",
        "Repair attempts",
        "Scenario failure counts",
        "Audit-attempt failure counts",
    ]
    execution_rows = []
    for item in summaries:
        scenario_provider_errors = _selected_failure_count(
            item.scenario_failure_counts,
            {},
            names=("authentication_error", "provider_503"),
        )
        audit_provider_errors = _selected_failure_count(
            {},
            item.audit_failure_counts,
            names=("authentication_error", "provider_503"),
        )
        scenario_timeouts = _selected_failure_count(
            item.scenario_failure_counts,
            {},
            names=("timeout",),
        )
        audit_timeouts = _selected_failure_count(
            {},
            item.audit_failure_counts,
            names=("timeout",),
        )
        execution_rows.append(
            [
                item.run_id,
                item.provider,
                item.model,
                item.gate_decision,
                f"{SCHEMA_RELIABILITY}; {PROVIDER_API_STRESS}",
                *_ratio_record_cells(
                    item.pipeline_completion,
                    claim_use="supplementary_reliability",
                ),
                str(scenario_provider_errors),
                str(audit_provider_errors),
                str(scenario_timeouts),
                str(audit_timeouts),
                str(item.repair_attempts),
                _compact_json(item.scenario_failure_counts),
                _compact_json(item.audit_failure_counts),
            ]
        )
    written.extend(
        _write_table_bundle(
            output_dir / "execution_reliability_results",
            execution_headers,
            execution_rows,
            (
                "Audit-pipeline completion (persisted as task_completion), provider "
                "errors, timeouts, and bounded repair burden. Completion is not native "
                "post-intervention task success."
            ),
            "tab:execution-reliability-results",
        )
    )

    api_headers = [
        "Run",
        "Provider",
        "Model",
        "Evidence class",
        "Wall seconds",
        "API attempts",
        "API seconds",
        "API seconds/scenario",
        "Provider tokens",
        "Token-cost proxy",
        "Token basis",
        "Proxy/scenario",
        "Estimated cost USD",
        "Token coverage",
        "Coverage 95% CI",
        "Coverage numerator",
        "Coverage denominator",
        "Coverage claim use",
    ]
    api_rows = [
        [
            item.run_id,
            item.provider,
            item.model,
            PROVIDER_API_STRESS,
            _format_float(item.wall_time_seconds),
            str(item.api_attempts),
            _format_float(item.api_time_seconds),
            _format_float(item.api_time_seconds_per_scenario),
            _format_int(item.total_tokens),
            _format_int(item.token_cost_proxy_units),
            item.token_cost_proxy_basis,
            _format_float(item.token_cost_proxy_units_per_scenario),
            _format_float(item.estimated_cost_usd),
            *_ratio_record_cells(
                item.token_usage_coverage,
                claim_use="supplementary_reliability",
            ),
        ]
        for item in summaries
    ]
    written.extend(
        _write_table_bundle(
            output_dir / "api_efficiency_results",
            api_headers,
            api_rows,
            "API latency, token usage, comparable token-cost proxy, and optional cost.",
            "tab:api-efficiency-results",
        )
    )

    safety_headers = [
        "Run",
        "Provider",
        "Model",
        "Event count",
        "Behavior counts",
        "Evidence class",
        "Claim use",
        "Interpretation",
    ]
    safety_rows = [
        [
            item.run_id,
            item.provider,
            item.model,
            str(item.safety_event_count),
            _compact_json(item.safety_behavior_counts),
            AGENT_TESTING_AGENT_SAFETY,
            "supplementary_diagnostic",
            (
                "Deterministic runtime/broker signals; intent and contextual harm may "
                "require human review"
            ),
        ]
        for item in summaries
    ]
    written.extend(
        _write_table_bundle(
            output_dir / "agent_safety_event_results",
            safety_headers,
            safety_rows,
            (
                "Agent-testing-agent-safety events. See docs/AGENT_SAFETY_EVENTS.md; "
                "counts are diagnostics rather than adjudicated labels."
            ),
            "tab:agent-safety-event-results",
        )
    )
    return written


def _write_table_bundle(
    stem: Path,
    headers: list[str],
    rows: list[list[str]],
    caption: str,
    label: str,
) -> list[Path]:
    csv_path = stem.with_suffix(".csv")
    md_path = stem.with_suffix(".md")
    tex_path = stem.with_suffix(".tex")
    _write_csv(csv_path, headers, rows)
    _write_markdown(md_path, headers, rows)
    _write_latex(tex_path, headers, rows, caption, label)
    return [csv_path, md_path, tex_path]


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _write_markdown(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_latex(
    path: Path,
    headers: list[str],
    rows: list[list[str]],
    caption: str,
    label: str,
) -> None:
    column_spec = "l" + "r" * max(0, len(headers) - 1)
    lines = [
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{{_latex_escape(caption)}}}",
        f"\\label{{{_latex_escape(label)}}}",
        f"\\begin{{tabular}}{{{column_spec}}}",
        "\\toprule",
        " & ".join(_latex_escape(item) for item in headers) + " \\\\",
        "\\midrule",
    ]
    lines.extend(" & ".join(_latex_escape(item) for item in row) + " \\\\" for row in rows)
    lines.extend(["\\bottomrule", "\\end{tabular}", "\\end{table}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_framework_figure_pdf(path: Path) -> Path:
    boxes = [
        ("Reproductions", "ASB, ConVerse, AFTraj"),
        ("Normalized Trajectories", "observable events + labels"),
        ("Audit Strategy", "none, sidecar, external, combined"),
        ("Policy Broker", "monotonic permission enforcement"),
        ("Paper Metrics", "timing, reliability, prefix localization"),
    ]
    canvas = _PdfCanvas(1060, 260)
    canvas.text(30, 35, "SelfAuditBench Evaluation Flow", 22, bold=True)
    box_width = 180
    gap = 25
    x = 30
    y = 80
    for index, (title, subtitle) in enumerate(boxes):
        canvas.rect(x, y, box_width, 95, "#eef4ff", "#2b5cab", radius=False)
        canvas.text(x + 14, y + 34, title, 15, bold=True)
        canvas.text(x + 14, y + 64, subtitle, 12)
        if index < len(boxes) - 1:
            arrow_x = x + box_width
            canvas.line(arrow_x + 4, y + 48, arrow_x + gap - 5, y + 48, "#444444")
            canvas.polygon(
                [
                    (arrow_x + gap - 5, y + 48),
                    (arrow_x + gap - 15, y + 42),
                    (arrow_x + gap - 15, y + 54),
                ],
                "#444444",
            )
        x += box_width + gap
    canvas.save(path)
    return path


def _write_bar_chart_pdf(
    path: Path,
    title: str,
    values: list[tuple[str, float]],
    *,
    y_label: str,
    percent: bool,
) -> Path:
    width = max(920, 180 + len(values) * 100)
    height = 420
    left = 70
    bottom = 340
    chart_height = 250
    chart_width = width - 140
    max_value = max((value for _, value in values), default=1.0)
    if percent:
        max_value = max(max_value, 1.0)
    bar_width = chart_width / max(1, len(values) * 1.5)
    canvas = _PdfCanvas(width, height)
    canvas.text(30, 35, title, 22, bold=True)
    canvas.line(left, bottom - chart_height, left, bottom, "#333333")
    canvas.line(left, bottom, left + chart_width, bottom, "#333333")
    canvas.text(18, bottom - chart_height / 2, y_label, 12)
    for index, (label, value) in enumerate(values):
        x = left + 30 + index * (bar_width * 1.5)
        bar_height = 0.0 if max_value == 0 else (value / max_value) * chart_height
        y = bottom - bar_height
        canvas.rect(x, y, bar_width, bar_height, "#5b8ff9", "#2b5cab")
        canvas.text(x, bottom + 20, _short_label(label), 11)
        value_label = _format_percent(value) if percent else _format_float(value)
        canvas.text(x, max(55, y - 8), value_label, 11)
    canvas.save(path)
    return path


def _write_label_composition_pdf(path: Path, summaries: list[DatasetSummary]) -> Path:
    width = max(960, 180 + len(summaries) * 110)
    height = 440
    left = 80
    bottom = 350
    chart_height = 260
    chart_width = width - 220
    bar_width = chart_width / max(1, len(summaries) * 1.6)
    max_total = max((item.scenarios for item in summaries), default=1)
    segments = [
        ("Risky", "risky", "#e76f51"),
        ("Benign", "benign", "#2a9d8f"),
        ("Unlabeled", "unlabeled", "#adb5bd"),
    ]
    canvas = _PdfCanvas(width, height)
    canvas.text(30, 35, "Benchmark Label Composition", 22, bold=True)
    canvas.text(
        30,
        60,
        (
            "Stacked counts expose which surfaces support recorded-action harm metrics "
            "versus prefix-only analysis."
        ),
        11,
    )
    canvas.line(left, bottom - chart_height, left, bottom, "#333333")
    canvas.line(left, bottom, left + chart_width, bottom, "#333333")
    for index, item in enumerate(summaries):
        x = left + 35 + index * (bar_width * 1.6)
        cumulative = 0.0
        for _, attribute, color in segments:
            count = float(getattr(item, attribute))
            segment_height = 0.0 if max_total == 0 else (count / max_total) * chart_height
            y = bottom - cumulative - segment_height
            if segment_height > 0:
                canvas.rect(x, y, bar_width, segment_height, color, "#333333")
            cumulative += segment_height
        canvas.text(x, bottom + 20, _short_label(item.dataset), 11)
        canvas.text(x, bottom - cumulative - 8, str(item.scenarios), 11)
    legend_x = width - 170
    legend_y = 105
    for index, (label, _, color) in enumerate(segments):
        y = legend_y + index * 24
        canvas.rect(legend_x, y - 12, 16, 16, color, "#333333")
        canvas.text(legend_x + 24, y, label, 12)
    canvas.save(path)
    return path


def _write_reliability_figure_pdf(path: Path, runs: list[RunSummary]) -> Path:
    values: list[tuple[str, float]] = []
    for run in runs:
        if run.task_completion is not None:
            values.append((f"{run.run_id}: complete", run.task_completion))
        if run.schema_compliance is not None:
            values.append((f"{run.run_id}: schema", run.schema_compliance))
    return _write_bar_chart_pdf(
        path,
        "Run Reliability",
        values,
        y_label="Rate",
        percent=True,
    )


def _write_metric_matrix_pdf(path: Path, runs: list[RunSummary]) -> Path:
    metrics = [
        ("Complete", "task_completion", False),
        ("Schema", "schema_compliance", False),
        ("ValidAudit", "valid_audit_coverage", False),
        ("GuardPause", "guard_pause_rate", True),
        ("ModelEarly", "model_early_detection", False),
        ("ModelPrefix", "model_first_prefix_recall", False),
        ("PrefixF1", "prefix_exact_f1", False),
        ("ModelF1", "model_prefix_exact_f1", False),
        ("StepAcc", "prefix_step_accuracy", False),
        ("ModelFA", "model_false_alarm_rate", True),
        ("GuardFA", "guard_false_alarm_rate", True),
    ]
    row_height = 42
    col_width = 92
    left = 230
    top = 95
    width = max(900, left + len(metrics) * col_width + 40)
    height = max(280, top + len(runs) * row_height + 70)
    canvas = _PdfCanvas(width, height)
    canvas.text(30, 35, "Run Metric Matrix", 22, bold=True)
    canvas.text(30, 60, "Darker cells indicate better values; false alarm is inverted.", 11)
    for index, (label, _, _) in enumerate(metrics):
        canvas.text(left + index * col_width + 8, top - 18, label, 9, bold=True)
    for row_index, run in enumerate(runs):
        y = top + row_index * row_height
        canvas.text(30, y + 25, _short_label(run.run_id, limit=30), 10)
        canvas.text(30, y + 38, f"{run.strategy}/{run.audit_mode}", 8)
        for col_index, (_, attribute, invert) in enumerate(metrics):
            value = _float_or_none(getattr(run, attribute))
            x = left + col_index * col_width
            if value is None:
                fill = "#f1f3f5"
                label = "N/A"
            else:
                score = 1.0 - value if invert else value
                fill = _blue_scale(score)
                label = _format_percent(value)
            canvas.rect(x, y, col_width - 6, row_height - 8, fill, "#ffffff", radius=False)
            canvas.text(x + 10, y + 24, label, 9, bold=value is not None and value >= 0.75)
    canvas.save(path)
    return path


def _write_grouped_agentforesight_figure_pdf(path: Path, rows: list[dict[str, str]]) -> Path:
    width = 960
    height = 430
    left = 70
    bottom = 340
    chart_height = 250
    group_width = 180
    bar_width = 34
    colors = {
        "Exact-F1": "#5b8ff9",
        "FAR": "#f6bd16",
        "StepAcc": "#61dDAA",
    }
    canvas = _PdfCanvas(width, height)
    canvas.text(30, 35, "AgentForesight Prefix Localization", 22, bold=True)
    canvas.line(left, bottom - chart_height, left, bottom, "#333333")
    canvas.line(left, bottom, left + 780, bottom, "#333333")
    for group_index, row in enumerate(rows):
        x0 = left + 30 + group_index * group_width
        for metric_index, metric in enumerate(("Exact-F1", "FAR", "StepAcc")):
            value = _parse_percent_string(row[metric])
            bar_height = value * chart_height
            x = x0 + metric_index * (bar_width + 6)
            y = bottom - bar_height
            canvas.rect(x, y, bar_width, bar_height, colors[metric], "#333333")
            canvas.text(x, max(55, y - 8), _format_percent(value), 10)
        canvas.text(x0, bottom + 22, row["Domain"], 12)
    legend_x = 700
    legend_y = 70
    for index, metric in enumerate(("Exact-F1", "FAR", "StepAcc")):
        y = legend_y + index * 24
        canvas.rect(legend_x, y - 12, 16, 16, colors[metric], "#333333")
        canvas.text(legend_x + 24, y, metric, 12)
    canvas.save(path)
    return path


def _write_index(
    output_dir: Path,
    datasets: list[DatasetSummary],
    runs: list[RunSummary],
    af_rows: list[dict[str, str]],
    supplementary_runs: list[SupplementaryRunSummary],
    annotation_evidence: AnnotationEvidenceSummary,
    closed_loop_runs: list[ClosedLoopRunSummary],
) -> Path:
    lines = [
        "# SelfAuditBench Paper Results Export",
        "",
        "## Recommended Manuscript Assets",
        "",
        "- Table: `tables/dataset_inventory.*` for benchmark surface counts and label coverage.",
        (
            "- Table: `tables/run_metrics_summary.*` for evidence-classified run "
            "index metrics. Use the separated result tables below for manuscript claims."
        ),
        "- Table: `tables/model_audit_results.*` for model early detection and false alarms.",
        "- Table: `tables/audit_schema_results.*` for valid-audit coverage and schema compliance.",
        (
            "- Table: `tables/broker_guard_results.*` for fail-closed interventions "
            "and guard false alarms."
        ),
        (
            "- Table: `tables/execution_reliability_results.*` for audit-pipeline "
            "completion, provider errors, timeouts, and repairs."
        ),
        (
            "- Table: `tables/api_efficiency_results.*` for latency, tokens, cost "
            "proxy, and optional monetary cost."
        ),
        (
            "- Table: `tables/agent_safety_event_results.*` for "
            "agent-testing-agent-safety diagnostics."
        ),
        (
            "- Table: `tables/label_semantics_claim_eligibility.*` for per-surface "
            "label and claim boundaries."
        ),
        (
            "- Table: `tables/annotation_study_evidence.*` for independent-annotation "
            "agreement, adjudication completeness, and frozen artifact hashes."
        ),
        (
            "- Table: `tables/closed_loop_recovery_results.*` for enacted safety, "
            "task success, recovery, noninterference, permission compliance, and burden."
        ),
        (
            "- Table: `tables/closed_loop_metric_records.*` for plot-ready closed-loop "
            "ratios, explicit denominators, and Wilson intervals."
        ),
        (
            "- Table: `tables/agentforesight_prefix_by_domain.*` for reproduced "
            "AFTraj held-out prefix-localization results when available."
        ),
        (
            "- Table: `tables/api_reliability_supplement.*` for per-run API time, "
            "provider-token, local token-cost proxy, optional monetary cost, "
            "failure-distribution, full-run gate decisions, analysis roles, and "
            "meta-safety data."
        ),
        (
            "- Figure PDFs: `figures/fig_framework_pipeline.pdf`, "
            "`figures/fig_dataset_inventory.pdf`, "
            "`figures/fig_dataset_label_composition.pdf`, "
            "`figures/fig_run_reliability.pdf`, `figures/fig_run_metric_matrix.pdf`, "
            "and `figures/fig_agentforesight_prefix_metrics.pdf` when "
            "AgentForesight by-domain results are available."
        ),
        (
            "- Closed-loop figure PDFs: `figures/fig_closed_loop_safety_task.pdf` "
            "and `figures/fig_closed_loop_replan_burden.pdf`."
        ),
        "",
        "## Export Summary",
        "",
        f"- Dataset rows: {len(datasets)}",
        f"- Run rows: {len(runs)}",
        f"- Supplementary runtime rows: {len(supplementary_runs)}",
        f"- AgentForesight domain rows: {len(af_rows)}",
        f"- Annotation evidence status: `{annotation_evidence.status}`",
        f"- Enacted closed-loop run rows: {len(closed_loop_runs)}",
        "",
        "## Notes For Results Section",
        "",
        (
            "Report ASB, ConVerse, and AFTraj results separately when their labels "
            "differ. Use AFTraj native prefix-localization metrics as an observer "
            "baseline, and reserve recorded-action harm-boundary or least-restriction "
            "metrics for cases with explicit SelfAuditBench annotations."
        ),
        (
            "For replay runs, report full-trace model audits and absorbing terminal "
            "broker projection separately. For closed-loop runs, report sink-gated "
            "safety/task outcomes and recovery burden from the enacted artifacts."
        ),
        (
            "Use dataset headline-status flags to select adjudicated rows for headline "
            "false-alarm, least-restriction, and enacted-recovery claims."
        ),
        (
            "Use annotation-study agreement when its evidence status is complete, all "
            "items were independently completed, and unresolved adjudications are zero."
        ),
        (
            "Report enacted ASB/ConVerse recovery, deterministic sink conformance, and "
            "AFTraj prefix evidence under their named execution contracts."
        ),
        (
            "Local open-source backends retain their gate-defined supplementary or "
            "headline analysis role in reliability tables."
        ),
        "",
    ]
    path = output_dir / "paper_results.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


class _PdfCanvas:
    """Small vector PDF writer for dependency-free manuscript figures."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._commands: list[str] = []
        self.rect(0, 0, width, height, "#ffffff", "#ffffff", radius=False)

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        fill: str,
        stroke: str,
        *,
        radius: bool = True,
    ) -> None:
        del radius
        pdf_y = self.height - y - height
        self._commands.append(
            "q "
            f"{_pdf_color(fill, 'rg')} {_pdf_color(stroke, 'RG')} "
            f"{x:.2f} {pdf_y:.2f} {width:.2f} {height:.2f} re B Q"
        )

    def text(self, x: float, y: float, text: str, size: int, *, bold: bool = False) -> None:
        font = "F2" if bold else "F1"
        pdf_y = self.height - y
        self._commands.append(
            "q 0.12 0.12 0.12 rg BT "
            f"/{font} {size} Tf {x:.2f} {pdf_y:.2f} Td ({_pdf_escape(text)}) Tj "
            "ET Q"
        )

    def line(self, x1: float, y1: float, x2: float, y2: float, stroke: str) -> None:
        self._commands.append(
            "q "
            f"{_pdf_color(stroke, 'RG')} 2 w "
            f"{x1:.2f} {self.height - y1:.2f} m "
            f"{x2:.2f} {self.height - y2:.2f} l S Q"
        )

    def polygon(self, points: list[tuple[float, float]], fill: str) -> None:
        if not points:
            return
        x0, y0 = points[0]
        commands = [
            "q",
            _pdf_color(fill, "rg"),
            f"{x0:.2f} {self.height - y0:.2f} m",
        ]
        commands.extend(f"{x:.2f} {self.height - y:.2f} l" for x, y in points[1:])
        commands.append("h f Q")
        self._commands.append(" ".join(commands))

    def save(self, path: Path) -> None:
        stream = "\n".join(self._commands).encode("latin-1", errors="replace")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.width} {self.height}] "
                "/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>"
            ).encode("ascii"),
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        ]
        content = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for index, item in enumerate(objects, start=1):
            offsets.append(len(content))
            content.extend(f"{index} 0 obj\n".encode("ascii"))
            content.extend(item)
            content.extend(b"\nendobj\n")
        xref_at = len(content)
        content.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        content.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        content.extend(
            (
                "trailer\n"
                f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
                "startxref\n"
                f"{xref_at}\n"
                "%%EOF\n"
            ).encode("ascii")
        )
        path.write_bytes(bytes(content))


def _pdf_color(value: str, operator: str) -> str:
    red, green, blue = _hex_to_rgb(value)
    return f"{red:.3f} {green:.3f} {blue:.3f} {operator}"


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    cleaned = value.lstrip("#")
    if len(cleaned) == 3:
        cleaned = "".join(char * 2 for char in cleaned)
    try:
        red = int(cleaned[0:2], 16) / 255.0
        green = int(cleaned[2:4], 16) / 255.0
        blue = int(cleaned[4:6], 16) / 255.0
    except (ValueError, IndexError):
        return (0.0, 0.0, 0.0)
    return (red, green, blue)


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _blue_scale(value: float) -> str:
    clamped = min(1.0, max(0.0, value))
    red = round(244 - clamped * 156)
    green = round(248 - clamped * 111)
    blue = round(255 - clamped * 30)
    return f"#{red:02x}{green:02x}{blue:02x}"


def _surface_label(summary: dict[str, Any]) -> str:
    dataset = summary.get("dataset", {})
    eligibility = dataset.get("headline_eligibility", {})
    values = eligibility.get("source_datasets")
    if not isinstance(values, list):
        counts = dataset.get("source_dataset_counts", {})
        values = sorted(counts) if isinstance(counts, dict) else []
    names = [str(value) for value in values if value]
    return ", ".join(names) if names else "unknown"


def _ratio_records(metrics: dict[str, Any]) -> dict[str, dict[str, int | float | None]]:
    records: dict[str, dict[str, int | float | None]] = {}
    for name, value in metrics.items():
        ratio = _ratio_dict(value)
        if ratio:
            records[name] = ratio
    reliability = metrics.get("execution_reliability", {})
    if isinstance(reliability, dict):
        for name, value in reliability.items():
            ratio = _ratio_dict(value)
            if ratio:
                records[name] = ratio
    return records


def _metrics_by_surface(metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    value = metrics.get("by_surface")
    if not isinstance(value, dict):
        return {}
    return {
        str(surface): surface_metrics
        for surface, surface_metrics in value.items()
        if isinstance(surface_metrics, dict)
    }


def _ratio_dict(value: Any) -> dict[str, int | float | None]:
    if not isinstance(value, dict):
        return {}
    if not {"value", "numerator", "denominator"} <= set(value):
        return {}
    return {
        "value": _float_or_none(value.get("value")),
        "numerator": _int_or_none(value.get("numerator")),
        "denominator": _int_or_none(value.get("denominator")),
    }


def _int_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): int(item)
        for key, item in value.items()
        if isinstance(item, (int, float))
    }


def _surface_views(
    summaries: list[RunSummary],
) -> list[
    tuple[
        RunSummary,
        str,
        dict[str, dict[str, int | float | None]],
        dict[str, dict[str, int | float | None]],
    ]
]:
    views: list[
        tuple[
            RunSummary,
            str,
            dict[str, dict[str, int | float | None]],
            dict[str, dict[str, int | float | None]],
        ]
    ] = []
    for item in summaries:
        if item.by_surface:
            for surface, metrics in sorted(item.by_surface.items()):
                views.append(
                    (
                        item,
                        surface,
                        _ratio_records(metrics),
                        ratio_confidence_intervals(metrics),
                    )
                )
        else:
            views.append((item, item.surface, item.ratios, item.confidence_intervals))
    return views


def _run_identity_cells(item: RunSummary, surface: str | None = None) -> list[str]:
    return [item.run_id, surface or item.surface, item.headline_status, item.analysis_role]


def _metric_cells(
    item: RunSummary,
    name: str,
    *,
    ratios: dict[str, dict[str, int | float | None]] | None = None,
    intervals: dict[str, dict[str, int | float | None]] | None = None,
    surface: str | None = None,
) -> list[str]:
    selected_ratios = ratios if ratios is not None else item.ratios
    selected_intervals = intervals if intervals is not None else item.confidence_intervals
    record = selected_ratios.get(name, {})
    value = _ratio_value(record)
    interval = selected_intervals.get(name)
    return [
        _format_percent(value),
        _format_interval_only(interval),
        _format_int(_int_or_none(record.get("numerator"))),
        _format_int(_int_or_none(record.get("denominator"))),
        _run_metric_claim_use(item, name, surface=surface),
    ]


def _run_metric_claim_use(
    item: RunSummary,
    name: str,
    *,
    surface: str | None = None,
) -> str:
    surface_label = surface or item.surface
    surfaces = {value.strip() for value in surface_label.split(",") if value.strip()}
    if len(surfaces) > 1 and name not in {"schema_compliance", "task_completion"}:
        return "descriptive_cross_surface_only"
    return metric_claim_use(name, item.eligibility)


def _ratio_record_cells(
    record: dict[str, int | float | None],
    *,
    claim_use: str,
) -> list[str]:
    numerator = _int_or_none(record.get("numerator"))
    denominator = _int_or_none(record.get("denominator"))
    interval = (
        wilson_interval(numerator, denominator)
        if numerator is not None and denominator is not None
        else None
    )
    return [
        _format_percent(_ratio_value(record)),
        _format_interval_only(interval),
        _format_int(numerator),
        _format_int(denominator),
        claim_use,
    ]


def _format_interval_only(interval: dict[str, int | float | None] | None) -> str:
    if not interval:
        return "N/A"
    lower = interval.get("lower")
    upper = interval.get("upper")
    if lower is None or upper is None:
        return "N/A"
    return f"[{float(lower) * 100:.2f}, {float(upper) * 100:.2f}]"


def _selected_failure_count(
    scenario: dict[str, int],
    attempts: dict[str, int],
    *,
    names: tuple[str, ...],
) -> int:
    return sum(scenario.get(name, 0) + attempts.get(name, 0) for name in names)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def _require_verified_paper_run(run_dir: Path, integrity: dict[str, Any]) -> None:
    if integrity.get("status") == "verified" and integrity.get("verified") is True:
        return
    errors = integrity.get("errors")
    detail = (
        "; ".join(str(item) for item in errors)
        if isinstance(errors, list) and errors
        else "verification did not succeed"
    )
    raise ValueError(
        f"paper export requires verified run integrity for {run_dir} "
        f"(status={integrity.get('status', 'unknown')}): {detail}"
    )


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_json(path)


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _ratio_value(value: Any) -> float | None:
    if isinstance(value, dict):
        return _float_or_none(value.get("value"))
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _compact_json(value: Any) -> str:
    if not value:
        return "{}"
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _percent_to_unit(value: Any) -> float | None:
    numeric = _float_or_none(value)
    if numeric is None:
        return None
    return numeric / 100.0 if abs(numeric) > 1.0 else numeric


def _format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def _format_claim_metric(
    value: float | None,
    claim_use: str,
    interval: dict[str, int | float | None] | None = None,
) -> str:
    formatted = _format_percent_interval(value, interval)
    if formatted == "N/A" or claim_use == "headline_eligible":
        return formatted
    return f"{formatted} [{claim_use}]"


def _format_percent_interval(
    value: float | None,
    interval: dict[str, int | float | None] | None,
) -> str:
    formatted = _format_percent(value)
    if formatted == "N/A" or not interval:
        return formatted
    lower = interval.get("lower")
    upper = interval.get("upper")
    if lower is None or upper is None:
        return formatted
    return f"{formatted} [{float(lower) * 100:.2f}, {float(upper) * 100:.2f}]"


def _format_float(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def _format_int(value: int | None) -> str:
    if value is None:
        return "N/A"
    return str(value)


def _annotation_ratio_cells(
    value: Any,
    *,
    explicit_value: Any = None,
) -> tuple[str, str, str]:
    record = value if isinstance(value, dict) else {}
    ratio_value = (
        explicit_value
        if isinstance(explicit_value, (int, float))
        else record.get("value")
    )
    return (
        _annotation_percent(ratio_value),
        _annotation_integer(_int_or_none(record.get("numerator"))),
        _annotation_integer(_int_or_none(record.get("denominator"))),
    )


def _annotation_percent(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "unavailable"
    return f"{float(value) * 100:.2f}%"


def _annotation_number(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "unavailable"
    return f"{float(value):.4f}"


def _annotation_integer(value: int | None) -> str:
    return "unavailable" if value is None else str(value)


def _annotation_sha256(value: Any) -> str:
    return value if _is_sha256(value) else "unavailable"


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _annotation_json(value: Any) -> str:
    if not isinstance(value, (dict, list)) or not value:
        return "unavailable"
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _parse_percent_string(value: str) -> float:
    try:
        return float(value.rstrip("%")) / 100.0
    except ValueError:
        return 0.0


def _short_label(value: str, limit: int = 18) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "..."


def _latex_escape(value: str) -> str:
    replacements = {
        "\\": "\\textbackslash{}",
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def _default_agentforesight_results_path(dataset_dir: Path) -> Path | None:
    candidates = [
        dataset_dir.parent.parent
        / ".."
        / "AgentForesight"
        / "outputs"
        / "cstcloud-deepseek-v4-flash"
        / "results.json",
        dataset_dir.parent.parent
        / ".."
        / "Reproductions"
        / "AgentForesight"
        / "outputs"
        / "cstcloud-deepseek-v4-flash"
        / "results.json",
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            return resolved
    return None
