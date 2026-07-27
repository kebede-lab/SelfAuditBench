"""Command-line interface for ingestion, annotation, execution, and reporting."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from typing import Annotated, Literal, TypeVar, cast

import typer

from selfauditbench.actors.clients import OpenAICompatibleModelClient
from selfauditbench.actors.recovery import ModelOutcomeJudge, ModelRecoveryActor
from selfauditbench.actors.strategies import (
    CombinedAuditStrategy,
    ModelAuditStrategy,
    NoAuditStrategy,
    PreToolGuardrailStrategy,
    classify_exception,
)
from selfauditbench.adapters.agentforesight import AFTrajReplayAdapter
from selfauditbench.adapters.agentforesight_results import (
    write_agentforesight_reproduction_run,
)
from selfauditbench.adapters.asb import ASBReplayAdapter
from selfauditbench.adapters.converse import ConVerseReplayAdapter
from selfauditbench.adapters.io import read_scenarios, write_scenarios
from selfauditbench.config import (
    ClosedLoopConfig,
    RunConfig,
    load_closed_loop_config,
    load_run_config,
)
from selfauditbench.core.models import (
    ActionExecution,
    AuditAttempt,
    AuditEmissionMode,
    AuditEnvelope,
    AuditRecord,
    BrokerDecision,
    ClosedLoopModelAttempt,
    ControllerFeedback,
    LabelProvenance,
    OutcomeJudgment,
    PermissionDelta,
    PermissionState,
    RecoveryTurn,
    RiskyBehaviorRecord,
    RunManifest,
    Scenario,
    ScenarioResult,
    StrategyId,
    TrajectoryEvent,
)
from selfauditbench.core.protocols import AuditStrategy, ScenarioAdapter
from selfauditbench.evaluation.annotations import (
    apply_adjudicated_labels,
    build_adjudication_queue,
    build_gold_candidates,
    carry_forward_annotations,
    export_annotation_templates,
    materialize_annotation_packet,
    materialize_calibration_pilot,
    read_adjudication_queue,
    read_gold_manifest,
    read_private_mapping,
    validate_annotation_file,
    validate_gold_manifest,
    verify_annotation_freeze_manifest,
    verify_compact_gold_integrity_manifest,
    write_adjudication_queue,
    write_annotation_evidence_manifest,
    write_annotation_freeze_manifest,
    write_compact_gold_integrity_manifest,
    write_gold_manifest,
)
from selfauditbench.evaluation.conformance import (
    verify_live_enforcement_conformance,
    write_live_enforcement_conformance,
)
from selfauditbench.evaluation.datasets import (
    SurfaceName,
    default_summary_path,
    summarize_scenarios,
    write_diagnostic_slice,
)
from selfauditbench.evaluation.closed_loop import (
    ClosedLoopRunner,
    aggregate_closed_loop_metrics,
)
from selfauditbench.evaluation.metrics import aggregate_metrics
from selfauditbench.evaluation.paper import export_paper_assets
from selfauditbench.evaluation.report import write_report
from selfauditbench.evaluation.runner import ReplayRunner
from selfauditbench.evaluation.statistics import (
    compare_run_directories,
    write_paired_comparison,
)
from selfauditbench.evaluation.supplementary import write_supplementary_run_data
from selfauditbench.storage.artifacts import (
    load_jsonl,
    verify_integrity_manifest,
    write_integrity_manifest,
)

app = typer.Typer(help="Benchmark auditable self-restriction in tool-using agents.")
ingest_app = typer.Typer(help="Normalize source benchmark artifacts.")
annotate_app = typer.Typer(help="Prepare and validate two-annotator gold labels.")
run_app = typer.Typer(help="Execute replay, enacted recovery, or live bridge validation.")
schema_app = typer.Typer(help="Export machine-readable contract schemas.")
paper_app = typer.Typer(help="Export manuscript-ready tables and figures.")
dataset_app = typer.Typer(help="Summarize and slice normalized scenario datasets.")
conformance_app = typer.Typer(help="Emit deterministic live-enforcement evidence.")
app.add_typer(ingest_app, name="ingest")
app.add_typer(annotate_app, name="annotate")
app.add_typer(run_app, name="run")
app.add_typer(schema_app, name="schema")
app.add_typer(paper_app, name="paper")
app.add_typer(dataset_app, name="dataset")
app.add_typer(conformance_app, name="conformance")
T = TypeVar("T")


def _ingest(adapter: ScenarioAdapter, source: Path, output: Path, limit: int | None) -> None:
    scenarios = adapter.load(source)
    if limit is not None:
        scenarios = _take(scenarios, limit)
    count = write_scenarios(output, scenarios)
    typer.echo(f"Wrote {count} normalized {adapter.source_dataset} scenarios to {output}")


def _take(values: Iterable[T], limit: int) -> Iterator[T]:
    return islice(values, limit)


def _surface_name(value: str) -> SurfaceName:
    if value not in {"asb", "converse", "agentforesight"}:
        raise typer.BadParameter("surface must be one of: asb, converse, agentforesight")
    return cast(SurfaceName, value)


def _maybe_export_paper_after_run(
    *,
    dataset_path: Path,
    runs_dir: Path,
    run_id: str,
    skip: bool,
) -> None:
    if skip or "smoke" in run_id.lower():
        return
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_dir = runs_dir.parent / "paper" / f"{stamp}-{run_id}"
    exported = export_paper_assets(
        dataset_dir=dataset_path.parent,
        runs_dir=runs_dir,
        output_dir=output_dir,
        run_ids={run_id},
    )
    typer.echo(f"Wrote {len(exported.files)} timestamped paper assets to {exported.output_dir}")


@ingest_app.command("asb")
def ingest_asb(
    source: Annotated[Path, typer.Argument(help="ASB log directory or CSV file.")],
    output: Annotated[Path, typer.Argument(help="Destination scenario JSONL file.")],
    limit: Annotated[int | None, typer.Option(min=1)] = None,
) -> None:
    _ingest(ASBReplayAdapter(), source, output, limit)


@ingest_app.command("converse")
def ingest_converse(
    source: Annotated[Path, typer.Argument(help="ConVerse log directory or transcript JSON.")],
    output: Annotated[Path, typer.Argument(help="Destination scenario JSONL file.")],
    limit: Annotated[int | None, typer.Option(min=1)] = None,
) -> None:
    _ingest(ConVerseReplayAdapter(), source, output, limit)


@ingest_app.command("agentforesight")
def ingest_agentforesight(
    source: Annotated[Path, typer.Argument(help="AFTraj directory or official parquet file.")],
    output: Annotated[Path, typer.Argument(help="Destination scenario JSONL file.")],
    limit: Annotated[int | None, typer.Option(min=1)] = None,
    domains: Annotated[
        str | None, typer.Option(help="Optional comma-separated AFTraj domain whitelist.")
    ] = None,
    paper_test_split: Annotated[
        bool, typer.Option(help="Restrict ingestion to AgentForesight's held-out paper split.")
    ] = False,
) -> None:
    selected_domains = (
        [domain.strip() for domain in domains.split(",") if domain.strip()] if domains else None
    )
    _ingest(
        AFTrajReplayAdapter(domains=selected_domains, paper_test_split=paper_test_split),
        source,
        output,
        limit,
    )


@ingest_app.command("agentforesight-results")
def ingest_agentforesight_results(
    per_sample: Annotated[
        Path, typer.Argument(help="AgentForesight reproduction per_sample.jsonl.")
    ],
    scenarios_path: Annotated[
        Path, typer.Argument(help="Normalized AFTraj scenario JSONL to match against.")
    ],
    run_dir: Annotated[
        Path, typer.Argument(help="Destination SelfAuditBench run artifact directory.")
    ],
    allow_missing: Annotated[
        bool, typer.Option(help="Skip reproduction rows without a matching scenario.")
    ] = False,
    skip_paper_export: Annotated[
        bool,
        typer.Option(
            help="Do not export timestamped manuscript assets after this non-smoke import."
        ),
    ] = False,
) -> None:
    scenarios = read_scenarios(scenarios_path)
    imported = write_agentforesight_reproduction_run(
        per_sample,
        scenarios,
        run_dir,
        allow_missing=allow_missing,
    )
    typer.echo(
        f"Imported {len(imported.results)} AgentForesight reproduction rows into {run_dir}"
    )
    _maybe_export_paper_after_run(
        dataset_path=scenarios_path,
        runs_dir=run_dir.parent,
        run_id=run_dir.name,
        skip=skip_paper_export,
    )


@dataset_app.command("summary")
def dataset_summary(
    source: Annotated[Path, typer.Argument(help="Normalized scenario JSONL file.")],
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Optional destination dataset_summary.json."),
    ] = None,
) -> None:
    scenarios = read_scenarios(source)
    path = output or default_summary_path(source)
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = summarize_scenarios(
        scenarios,
        source_count=len(scenarios),
        surface=None,
        output=source,
    )
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(f"Wrote dataset summary for {len(scenarios)} scenarios to {path}")


@dataset_app.command("some-50")
def dataset_some_50(
    surface: Annotated[str, typer.Argument(help="asb, converse, or agentforesight.")],
    source: Annotated[Path, typer.Argument(help="Normalized scenario JSONL file.")],
    output: Annotated[Path, typer.Argument(help="Destination diagnostic JSONL slice.")],
    summary: Annotated[
        Path | None,
        typer.Option("--summary", help="Optional destination dataset_summary.json."),
    ] = None,
    limit: Annotated[int, typer.Option(min=2, help="Diagnostic slice size.")] = 50,
) -> None:
    scenarios = read_scenarios(source)
    count, summary_path = write_diagnostic_slice(
        scenarios,
        surface=_surface_name(surface),
        output=output,
        summary_path=summary,
        limit=limit,
    )
    typer.echo(f"Wrote {count} {surface} diagnostic scenarios to {output}")
    typer.echo(f"Wrote dataset summary to {summary_path}")


@annotate_app.command("select")
def annotate_select(
    asb_root: Annotated[Path, typer.Option(help="ASB logs root.")],
    converse_root: Annotated[Path, typer.Option(help="ConVerse logs root.")],
    output: Annotated[Path, typer.Option(help="Gold candidate manifest YAML.")],
) -> None:
    manifest = build_gold_candidates(asb_root, converse_root)
    write_gold_manifest(output, manifest)
    typer.echo(f"Wrote {len(manifest.pairs)} gold candidate pairs to {output}")


@annotate_app.command("export")
def annotate_export(
    manifest_path: Annotated[Path, typer.Argument(help="Gold candidate manifest YAML.")],
    destination: Annotated[Path, typer.Argument(help="Annotation template directory.")],
) -> None:
    manifest = read_gold_manifest(manifest_path)
    validate_gold_manifest(manifest)
    export_annotation_templates(manifest, destination)
    typer.echo(f"Wrote two annotation templates to {destination}")


@annotate_app.command("packet")
def annotate_packet(
    manifest_path: Annotated[Path, typer.Argument(help="Gold candidate manifest YAML.")],
    asb_scenarios: Annotated[Path, typer.Argument(help="Normalized ASB scenario JSONL.")],
    converse_scenarios: Annotated[
        Path, typer.Argument(help="Normalized ConVerse scenario JSONL.")
    ],
    destination: Annotated[Path, typer.Argument(help="Blinded packet directory.")],
    seed: Annotated[int, typer.Option(help="Deterministic blinding seed.")] = 7,
    allow_missing: Annotated[
        bool,
        typer.Option(help="Write an incomplete pilot packet and list missing sources."),
    ] = False,
) -> None:
    manifest = read_gold_manifest(manifest_path)
    summary = materialize_annotation_packet(
        manifest,
        read_scenarios(asb_scenarios),
        read_scenarios(converse_scenarios),
        destination,
        seed=seed,
        allow_missing=allow_missing,
    )
    typer.echo(json.dumps(summary, indent=2, sort_keys=True))


@annotate_app.command("pilot")
def annotate_pilot(
    scenarios: Annotated[
        Path, typer.Argument(help="Already blinded full-packet scenario JSONL.")
    ],
    destination: Annotated[Path, typer.Argument(help="Calibration pilot directory.")],
    private_mapping: Annotated[
        Path | None,
        typer.Option(
            "--private-mapping",
            help="Coordinator mapping; defaults to the full packet's sibling mapping.",
        ),
    ] = None,
    seed: Annotated[int, typer.Option(help="Deterministic pilot selection seed.")] = 17,
) -> None:
    mapping_path = private_mapping or scenarios.parent / "private_mapping.jsonl"
    if not mapping_path.exists():
        raise typer.BadParameter(
            "the coordinator-only full-packet private mapping is required"
        )
    summary = materialize_calibration_pilot(
        read_scenarios(scenarios),
        destination,
        read_private_mapping(mapping_path),
        size=10,
        seed=seed,
    )
    typer.echo(json.dumps(summary, indent=2, sort_keys=True))


@annotate_app.command("carry-forward")
def annotate_carry_forward(
    prior_packet: Annotated[
        Path, typer.Argument(help="Frozen packet containing completed independent files.")
    ],
    packet: Annotated[
        Path, typer.Argument(help="New packet whose blank templates will be populated.")
    ],
    surface: Annotated[
        str, typer.Option(help="Unchanged surface whose independent rows may be reused.")
    ] = "converse",
) -> None:
    if surface not in {"asb", "converse"}:
        raise typer.BadParameter("--surface must be 'asb' or 'converse'")
    summary = carry_forward_annotations(
        prior_packet,
        packet,
        surface=cast(Literal["asb", "converse"], surface),
    )
    typer.echo(json.dumps(summary, indent=2, sort_keys=True))


@annotate_app.command("freeze")
def annotate_freeze(
    packet: Annotated[Path, typer.Argument(help="Completed annotation packet directory.")],
    output: Annotated[
        Path | None, typer.Option(help="Frozen-input hash manifest JSON.")
    ] = None,
) -> None:
    scenarios_path = packet / "scenarios.jsonl"
    mapping_path = packet / "private_mapping.jsonl"
    annotator_a_path = packet / "annotator_a.jsonl"
    annotator_b_path = packet / "annotator_b.jsonl"
    scenarios = read_scenarios(scenarios_path)
    first = validate_annotation_file(
        annotator_a_path,
        scenarios=scenarios,
        require_complete=True,
    )
    second = validate_annotation_file(
        annotator_b_path,
        scenarios=scenarios,
        require_complete=True,
    )
    if {item.annotator_id for item in first} == {item.annotator_id for item in second}:
        raise typer.BadParameter("independent files must use distinct annotator IDs")
    path = output or packet / "independent_annotations.freeze.json"
    write_annotation_freeze_manifest(
        path,
        packet_scenarios=scenarios_path,
        private_mapping=mapping_path,
        annotator_a=annotator_a_path,
        annotator_b=annotator_b_path,
    )
    typer.echo(f"Froze independent annotation hashes in {path}")


@annotate_app.command("validate")
def annotate_validate(
    path: Annotated[Path, typer.Argument(help="Manifest YAML or annotation JSONL file.")],
    scenarios: Annotated[
        Path | None,
        typer.Option(help="Packet scenarios for semantic label validation."),
    ] = None,
    require_complete: Annotated[
        bool,
        typer.Option(help="Require every annotation row to be independently complete."),
    ] = False,
    final_ready: Annotated[
        bool,
        typer.Option(
            help="Require a source-unique manifest with no regeneration placeholders."
        ),
    ] = False,
) -> None:
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            validate_gold_manifest(read_gold_manifest(path), final_ready=final_ready)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        qualifier = "final-ready" if final_ready else "planning"
        typer.echo(f"Gold candidate manifest is valid ({qualifier}).")
    else:
        packet = read_scenarios(scenarios) if scenarios is not None else None
        annotations = validate_annotation_file(
            path,
            scenarios=packet,
            require_complete=require_complete,
        )
        typer.echo(f"Validated {len(annotations)} annotation rows.")


@annotate_app.command("compact")
def annotate_compact(
    source: Annotated[Path, typer.Argument(help="Scenario JSONL with completed labels.")],
    output: Annotated[Path, typer.Argument(help="Destination compact gold scenario JSONL.")],
    limit: Annotated[
        int | None, typer.Option(min=1, help="Optional maximum scenarios to export.")
    ] = None,
    surface: Annotated[
        str | None,
        typer.Option(help="Optional gold surface: asb or converse."),
    ] = None,
    allow_subset: Annotated[
        bool,
        typer.Option(help="Explicitly permit exclusions or a pair-complete partial slice."),
    ] = False,
) -> None:
    if surface not in {None, "asb", "converse"}:
        raise typer.BadParameter("--surface must be 'asb' or 'converse'")
    candidates = [
        scenario
        for scenario in read_scenarios(source)
        if surface is None or scenario.source_dataset == surface
    ]
    if not candidates:
        raise typer.BadParameter("no scenarios match the requested gold surface")
    ineligible = [
        scenario.scenario_id
        for scenario in candidates
        if not _has_recorded_action_gold_label(scenario)
    ]
    if ineligible and not allow_subset:
        raise typer.BadParameter(
            f"{len(ineligible)} scenarios are not final human-adjudicated gold; "
            "fix them or pass --allow-subset for a non-headline slice"
        )
    scenarios = [
        scenario for scenario in candidates if _has_recorded_action_gold_label(scenario)
    ]
    if limit is not None and limit < len(scenarios):
        if not allow_subset:
            raise typer.BadParameter("--limit requires --allow-subset")
        scenarios = _pair_complete_subset(scenarios, limit)
    if not scenarios:
        raise typer.BadParameter(
            "no scenarios have final human-adjudicated recorded-action labels"
        )
    surfaces = {scenario.source_dataset for scenario in scenarios}
    expected_count = 96 if surfaces == {"asb", "converse"} else 48
    if len(scenarios) != expected_count and not allow_subset:
        raise typer.BadParameter(
            f"final compact export requires {expected_count} scenarios for "
            f"{sorted(surfaces)}; pass --allow-subset for a non-headline slice"
        )
    _validate_compact_pairs(scenarios)
    count = write_scenarios(output, scenarios)
    typer.echo(f"Wrote {count} compact recorded-action gold scenarios to {output}")
    integrity_path = output.with_name(f"{output.stem}.integrity.json")
    write_compact_gold_integrity_manifest(
        integrity_path,
        source_dataset=source,
        compact_dataset=output,
        scenarios=scenarios,
        requested_surface=surface,
        allow_subset=allow_subset,
        limit=limit,
    )
    typer.echo(f"Wrote compact gold integrity manifest to {integrity_path}")


@annotate_app.command("verify-compact")
def annotate_verify_compact(
    manifest: Annotated[
        Path,
        typer.Argument(help="Adjacent compact-gold integrity manifest JSON."),
    ],
) -> None:
    result = verify_compact_gold_integrity_manifest(manifest)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))
    if not result["verified"]:
        raise typer.Exit(code=1)


def _has_recorded_action_gold_label(scenario: Scenario) -> bool:
    if scenario.label is None:
        return False
    if scenario.label_provenance != LabelProvenance.HUMAN_ADJUDICATED:
        return False
    if scenario.label_evidence_sha256 is None:
        return False
    if not scenario.label.utility_expectation.strip():
        return False
    if not scenario.label.risky:
        return True
    return (
        scenario.label.first_risk_sufficient_event is not None
        and scenario.label.harm_boundary_event is not None
        and scenario.label.first_risk_sufficient_event
        <= scenario.label.harm_boundary_event
        and bool(scenario.label.accepted_interventions)
        and bool(scenario.label.minimal_permission_deltas)
    )


def _pair_complete_subset(scenarios: list[Scenario], limit: int) -> list[Scenario]:
    if limit % 2:
        raise typer.BadParameter("gold subsets must use an even --limit to retain pairs")
    grouped: dict[str, list[Scenario]] = {}
    for scenario in scenarios:
        if scenario.pair_id is None:
            raise typer.BadParameter("gold subset scenario is missing pair_id")
        grouped.setdefault(scenario.pair_id, []).append(scenario)
    selected_ids = set(sorted(grouped)[: limit // 2])
    selected = [
        scenario for scenario in scenarios if scenario.pair_id in selected_ids
    ]
    if len(selected) != min(limit, len(scenarios)):
        raise typer.BadParameter("--limit could not produce a complete-pair subset")
    return selected


def _validate_compact_pairs(scenarios: list[Scenario]) -> None:
    grouped: dict[str, list[Scenario]] = {}
    evidence_ids = {scenario.label_evidence_sha256 for scenario in scenarios}
    if len(evidence_ids) != 1 or None in evidence_ids:
        raise typer.BadParameter("compact gold must share one annotation evidence hash")
    for scenario in scenarios:
        if scenario.pair_id is None:
            raise typer.BadParameter("compact gold scenario is missing pair_id")
        grouped.setdefault(scenario.pair_id, []).append(scenario)
    for pair_id, pair in grouped.items():
        roles = {
            tag.removeprefix("role:")
            for scenario in pair
            for tag in scenario.tags
            if tag.startswith("role:")
        }
        if len(pair) != 2 or roles != {"attack", "control"}:
            raise typer.BadParameter(
                f"compact gold pair {pair_id!r} is not a complete attack-control pair"
            )


@annotate_app.command("adjudicate")
def annotate_adjudicate(
    annotator_a: Annotated[Path, typer.Argument(help="First completed annotation JSONL.")],
    annotator_b: Annotated[Path, typer.Argument(help="Second completed annotation JSONL.")],
    output: Annotated[
        Path | None,
        typer.Option(help="Optional adjudication queue JSONL output."),
    ] = None,
    scenarios: Annotated[
        Path | None,
        typer.Option(help="Blinded packet scenarios for semantic validation."),
    ] = None,
    freeze_manifest: Annotated[
        Path | None,
        typer.Option(help="Frozen independent-input hash manifest."),
    ] = None,
) -> None:
    first = validate_annotation_file(annotator_a)
    second = validate_annotation_file(annotator_b)
    any_completed = any(item.label is not None for item in first + second)
    freeze_path = freeze_manifest or annotator_a.parent / "independent_annotations.freeze.json"
    if any_completed and not freeze_path.exists():
        raise typer.BadParameter("freeze independent annotations before adjudication")
    if freeze_path.exists():
        verify_annotation_freeze_manifest(freeze_path)
    if any_completed and scenarios is None:
        raise typer.BadParameter(
            "completed annotations require --scenarios for semantic validation"
        )
    packet = read_scenarios(scenarios) if scenarios is not None else None
    tasks, summary = build_adjudication_queue(first, second, scenarios=packet)
    typer.echo(
        f"Shared rows: {summary['total_items']}; "
        f"completed pairs: {summary['completed_by_both']}; "
        f"pending pairs: {summary['pending_items']}; "
        f"exact agreements: {summary['exact_label_agreements']}"
    )
    typer.echo(json.dumps(summary, indent=2, sort_keys=True))
    if output is not None:
        queue_path, summary_path = write_adjudication_queue(output, tasks, summary)
        typer.echo(str(queue_path))
        typer.echo(str(summary_path))
    typer.echo("Disagreements require human adjudication; no labels were synthesized.")


@annotate_app.command("apply")
def annotate_apply(
    scenarios: Annotated[Path, typer.Argument(help="Blinded annotation scenario JSONL.")],
    adjudication_queue: Annotated[
        Path, typer.Argument(help="Completed adjudication queue JSONL.")
    ],
    private_mapping: Annotated[
        Path, typer.Argument(help="Coordinator-only private mapping JSONL.")
    ],
    output: Annotated[Path, typer.Argument(help="Adjudicated gold scenario JSONL.")],
    freeze_manifest: Annotated[
        Path | None,
        typer.Option(help="Frozen independent-input hash manifest."),
    ] = None,
    evidence_output: Annotated[
        Path | None,
        typer.Option(help="Annotation evidence manifest JSON output."),
    ] = None,
) -> None:
    freeze_path = freeze_manifest or scenarios.parent / "independent_annotations.freeze.json"
    if not freeze_path.exists():
        raise typer.BadParameter("freeze independent annotations before applying labels")
    verify_annotation_freeze_manifest(freeze_path)
    packet = read_scenarios(scenarios)
    annotator_a_path = scenarios.parent / "annotator_a.jsonl"
    annotator_b_path = scenarios.parent / "annotator_b.jsonl"
    first = validate_annotation_file(
        annotator_a_path, scenarios=packet, require_complete=True
    )
    second = validate_annotation_file(
        annotator_b_path, scenarios=packet, require_complete=True
    )
    tasks = read_adjudication_queue(adjudication_queue)
    first_by_id = {item.scenario_id: item for item in first}
    second_by_id = {item.scenario_id: item for item in second}
    if any(
        task.annotation_a != first_by_id.get(task.scenario_id)
        or task.annotation_b != second_by_id.get(task.scenario_id)
        for task in tasks
    ):
        raise typer.BadParameter("adjudication queue does not match frozen annotation files")
    resolved = apply_adjudicated_labels(
        packet,
        tasks,
        read_private_mapping(private_mapping),
    )
    count = write_scenarios(output, resolved)
    typer.echo(f"Wrote {count} adjudicated gold scenarios to {output}")
    evidence_path = evidence_output or output.with_name(
        f"{output.stem}.annotation_evidence.json"
    )
    write_annotation_evidence_manifest(
        evidence_path,
        packet_scenarios=scenarios,
        private_mapping=private_mapping,
        annotator_a=annotator_a_path,
        annotator_b=annotator_b_path,
        adjudication=adjudication_queue,
        final_dataset=output,
        tasks=tasks,
        resolved=resolved,
    )
    typer.echo(f"Wrote annotation evidence manifest to {evidence_path}")


def _strategy_from_config(config: RunConfig, allow_inline: bool = False) -> AuditStrategy:
    if config.strategy in {StrategyId.NO_AUDIT, StrategyId.FIXED_POLICY}:
        return NoAuditStrategy()
    if config.strategy == StrategyId.PRETOOL_GUARDRAIL:
        return PreToolGuardrailStrategy()
    if config.audit_mode == AuditEmissionMode.INLINE:
        if allow_inline:
            return NoAuditStrategy()
        raise typer.BadParameter("inline envelopes must be supplied by an instrumented live actor")
    if config.model is None:
        raise typer.BadParameter("this strategy requires a configured OpenAI-compatible model")
    client = OpenAICompatibleModelClient(config.model)
    _preflight_model_client(client, label="actor", model=config.model.model)
    emission_mode = (
        AuditEmissionMode.EXTERNAL
        if config.strategy == StrategyId.EXTERNAL_AUDITOR
        else AuditEmissionMode.SIDECAR
    )
    actor = ModelAuditStrategy(client, actor_id=config.strategy.value, emission_mode=emission_mode)
    if config.strategy != StrategyId.COMBINED_MONITOR_BROKER:
        return actor
    observer_profile = config.observer_model or config.model
    assert observer_profile is not None
    observer_client = OpenAICompatibleModelClient(observer_profile)
    _preflight_model_client(observer_client, label="observer", model=observer_profile.model)
    observer = ModelAuditStrategy(
        observer_client,
        actor_id="external_observer",
        emission_mode=AuditEmissionMode.EXTERNAL,
    )
    return CombinedAuditStrategy(actor, observer)


def _preflight_model_client(
    client: OpenAICompatibleModelClient,
    *,
    label: str,
    model: str,
) -> None:
    try:
        client.preflight()
    except Exception as exc:
        failure_type = classify_exception(exc)
        raise typer.BadParameter(
            f"{label} model preflight failed for {model}: {failure_type.value}: {exc}"
        ) from exc


@run_app.command("replay")
def run_replay(
    config_path: Annotated[Path, typer.Option("--config", help="Replay YAML configuration.")],
    skip_paper_export: Annotated[
        bool,
        typer.Option(
            help="Do not export timestamped manuscript assets after this non-smoke run."
        ),
    ] = False,
) -> None:
    config = load_run_config(config_path)
    scenarios = read_scenarios(config.dataset)
    manifest, results = ReplayRunner(config, _strategy_from_config(config)).run(scenarios)
    typer.echo(f"Completed {len(results)} scenarios in run {manifest.run_id}")
    typer.echo(str(config.output_root / config.run_id))
    _maybe_export_paper_after_run(
        dataset_path=config.dataset,
        runs_dir=config.output_root,
        run_id=manifest.run_id,
        skip=skip_paper_export,
    )


@run_app.command("closed-loop")
def run_closed_loop(
    config_path: Annotated[
        Path, typer.Option("--config", help="Enacted closed-loop YAML configuration.")
    ],
    skip_paper_export: Annotated[
        bool,
        typer.Option(
            help="Do not export timestamped manuscript assets after this non-smoke run."
        ),
    ] = False,
) -> None:
    config = load_closed_loop_config(config_path)
    scenarios = read_scenarios(config.dataset)
    audit_strategy = _strategy_from_config(config, allow_inline=True)
    recovery_client = OpenAICompatibleModelClient(config.recovery_model)
    judge_client = OpenAICompatibleModelClient(config.outcome_judge_model)
    _preflight_model_client(
        recovery_client,
        label="recovery actor",
        model=config.recovery_model.model,
    )
    _preflight_model_client(
        judge_client,
        label="outcome judge",
        model=config.outcome_judge_model.model,
    )
    actor = ModelRecoveryActor(recovery_client, config.condition)
    judge = ModelOutcomeJudge(judge_client, config.condition)
    manifest, results = ClosedLoopRunner(
        config,
        audit_strategy,
        actor,
        judge,
    ).run(scenarios)
    typer.echo(f"Completed {len(results)} enacted scenarios in run {manifest.run_id}")
    typer.echo(str(config.output_root / config.run_id))
    _maybe_export_paper_after_run(
        dataset_path=config.dataset,
        runs_dir=config.output_root,
        run_id=manifest.run_id,
        skip=skip_paper_export,
    )


@run_app.command("live")
def run_live(
    config_path: Annotated[Path, typer.Option("--config", help="Live YAML configuration.")],
    bridge: Annotated[str, typer.Option(help="Live bridge: asb or converse.")],
) -> None:
    config = load_run_config(config_path)
    if bridge not in {"asb", "converse"}:
        raise typer.BadParameter("bridge must be 'asb' or 'converse'")
    _strategy_from_config(config, allow_inline=True)
    typer.echo(f"Validated {bridge} live bridge configuration for run {config.run_id}.")
    typer.echo("Import the bridge from selfauditbench.adapters.live in the benchmark launcher.")


@conformance_app.command("live")
def conformance_live(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            help="Hashed live sink-enforcement conformance artifact.",
        ),
    ] = Path("artifacts/conformance/live-enforcement.json"),
) -> None:
    path = write_live_enforcement_conformance(output)
    payload = json.loads(path.read_text(encoding="utf-8"))
    typer.echo(
        f"Live enforcement conformance: {payload['summary']['passed']}/"
        f"{payload['summary']['total']} passed"
    )
    typer.echo(str(path))


@conformance_app.command("verify")
def conformance_verify(
    path: Annotated[
        Path,
        typer.Argument(help="Hashed live-enforcement conformance JSON artifact."),
    ],
) -> None:
    verified = verify_live_enforcement_conformance(path)
    typer.echo("verified" if verified else "corrupt")
    if not verified:
        raise typer.Exit(code=1)


@app.command("score")
def score(
    run_dir: Annotated[Path, typer.Option("--run", help="Existing run directory.")],
) -> None:
    dataset = json.loads((run_dir / "dataset.json").read_text())
    scenarios = [Scenario.model_validate(item) for item in dataset]
    results = [
        ScenarioResult.model_validate(item) for item in load_jsonl(run_dir / "results.jsonl")
    ]
    metrics = aggregate_metrics(results, scenarios)
    if any(result.closed_loop_condition is not None for result in results):
        metrics["closed_loop_recovery"] = aggregate_closed_loop_metrics(
            results, scenarios
        )
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest = RunManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        write_supplementary_run_data(run_dir, manifest, metrics)
    write_report(run_dir, metrics)
    write_integrity_manifest(run_dir)
    typer.echo(json.dumps(metrics, indent=2, sort_keys=True))


@app.command("report")
def report(
    run_dir: Annotated[Path, typer.Option("--run", help="Existing run directory.")],
) -> None:
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest = RunManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        write_supplementary_run_data(run_dir, manifest, metrics)
    path = write_report(run_dir, metrics)
    write_integrity_manifest(run_dir)
    typer.echo(str(path))


@app.command("verify")
def verify(
    run_dir: Annotated[Path, typer.Option("--run", help="Run artifact directory.")],
) -> None:
    result = verify_integrity_manifest(run_dir)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "verified":
        raise typer.Exit(code=1)


@app.command("compare")
def compare(
    run_a: Annotated[Path, typer.Option("--run-a", help="First run directory.")],
    run_b: Annotated[Path, typer.Option("--run-b", help="Second run directory.")],
    output: Annotated[
        Path,
        typer.Option("--output", help="Output stem for JSON and Markdown comparison."),
    ] = Path("artifacts/comparisons/paired-comparison"),
    bootstrap_samples: Annotated[
        int,
        typer.Option(min=1, help="Deterministic paired bootstrap samples."),
    ] = 2000,
    seed: Annotated[int, typer.Option(help="Bootstrap random seed.")] = 7,
    treatment_comparison: Annotated[
        bool,
        typer.Option(
            "--treatment-comparison",
            help="Compare paired closed-loop conditions under a shared comparison contract.",
        ),
    ] = False,
) -> None:
    comparison = compare_run_directories(
        run_a,
        run_b,
        bootstrap_samples=bootstrap_samples,
        seed=seed,
        allow_treatment_difference=treatment_comparison,
    )
    json_path, markdown_path = write_paired_comparison(output, comparison)
    typer.echo(str(json_path))
    typer.echo(str(markdown_path))


@paper_app.command("export")
def paper_export(
    output: Annotated[
        Path, typer.Option("--output", help="Destination directory for paper assets.")
    ] = Path("artifacts/paper"),
    dataset_dir: Annotated[
        Path, typer.Option("--dataset-dir", help="Directory of normalized scenario JSONL files.")
    ] = Path("artifacts/exploratory"),
    runs_dir: Annotated[
        Path, typer.Option("--runs-dir", help="Directory containing SelfAuditBench run folders.")
    ] = Path("artifacts/runs"),
    agentforesight_results_json: Annotated[
        Path | None,
        typer.Option(
            "--agentforesight-results-json",
            help="Optional AgentForesight reproduction results.json for by-domain table.",
        ),
    ] = None,
    include_smoke: Annotated[
        bool, typer.Option(help="Include run directories with 'smoke' in their name.")
    ] = False,
    run_ids: Annotated[
        str | None,
        typer.Option(
            "--run-ids",
            help="Optional comma-separated verified run-directory allowlist.",
        ),
    ] = None,
) -> None:
    selected_run_ids = (
        {item.strip() for item in run_ids.split(",") if item.strip()}
        if run_ids
        else None
    )
    exported = export_paper_assets(
        dataset_dir=dataset_dir,
        runs_dir=runs_dir,
        output_dir=output,
        agentforesight_results_json=agentforesight_results_json,
        include_smoke=include_smoke,
        run_ids=selected_run_ids,
    )
    typer.echo(f"Wrote {len(exported.files)} paper assets to {exported.output_dir}")


@schema_app.command("export")
def schema_export(
    destination: Annotated[Path, typer.Argument(help="Schema output directory.")] = Path("schemas"),
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    models = (
        TrajectoryEvent,
        AuditAttempt,
        AuditRecord,
        AuditEnvelope,
        RecoveryTurn,
        ControllerFeedback,
        ActionExecution,
        ClosedLoopModelAttempt,
        OutcomeJudgment,
        PermissionState,
        PermissionDelta,
        BrokerDecision,
        RiskyBehaviorRecord,
        Scenario,
        ScenarioResult,
        RunManifest,
        ClosedLoopConfig,
    )
    for model in models:
        path = destination / f"{model.__name__}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n")
    typer.echo(f"Wrote {len(models)} schemas to {destination}")


if __name__ == "__main__":
    app()
