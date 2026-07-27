"""Supplementary runtime and reliability exports for reproducibility studies."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from selfauditbench.core.models import RunManifest, Scenario
from selfauditbench.evaluation.datasets import summarize_scenarios
from selfauditbench.evaluation.evidence import (
    AGENT_TESTING_AGENT_SAFETY,
    PROVIDER_API_STRESS,
    SCHEMA_RELIABILITY,
    build_evidence_policy,
    metric_claim_use,
    metric_evidence_class,
)
from selfauditbench.evaluation.statistics import ratio_confidence_intervals
from selfauditbench.storage.artifacts import load_jsonl


def closed_loop_readiness_check(run_dir: Path) -> tuple[dict[str, Any], list[str]]:
    """Validate exact closed-loop coverage and resolved enacted actions."""

    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    dataset = json.loads((run_dir / "dataset.json").read_text(encoding="utf-8"))
    if not isinstance(dataset, list):
        raise ValueError("closed-loop dataset.json must contain a JSON array")
    results = load_jsonl(run_dir / "results.jsonl")
    executions = load_jsonl(run_dir / "action_executions.jsonl")
    closed = metrics["closed_loop_recovery"]
    failures: list[str] = []

    dataset_counts = Counter(item.get("scenario_id") for item in dataset)
    result_counts = Counter(item.get("scenario_id") for item in results)
    duplicate_dataset_ids = sorted(
        str(scenario_id)
        for scenario_id, count in dataset_counts.items()
        if count > 1
    )
    duplicate_result_ids = sorted(
        str(scenario_id)
        for scenario_id, count in result_counts.items()
        if count > 1
    )
    dataset_ids = set(dataset_counts)
    result_ids = set(result_counts)
    missing_result_ids = sorted(str(item) for item in dataset_ids - result_ids)
    unexpected_result_ids = sorted(str(item) for item in result_ids - dataset_ids)
    scenario_set_check = {
        "dataset_scenario_count": len(dataset),
        "unique_dataset_scenario_count": len(dataset_ids),
        "result_count": len(results),
        "unique_result_scenario_count": len(result_ids),
        "duplicate_dataset_scenario_ids": duplicate_dataset_ids,
        "duplicate_result_scenario_ids": duplicate_result_ids,
        "missing_result_scenario_ids": missing_result_ids,
        "unexpected_result_scenario_ids": unexpected_result_ids,
    }
    if duplicate_dataset_ids:
        failures.append(
            "closed-loop dataset has duplicate scenario IDs: "
            + ", ".join(duplicate_dataset_ids)
        )
    if duplicate_result_ids:
        failures.append(
            "closed-loop results have duplicate scenario IDs: "
            + ", ".join(duplicate_result_ids)
        )
    if missing_result_ids:
        failures.append(
            "closed-loop results are missing dataset scenarios: "
            + ", ".join(missing_result_ids)
        )
    if unexpected_result_ids:
        failures.append(
            "closed-loop results contain unexpected scenarios: "
            + ", ".join(unexpected_result_ids)
        )
    if closed.get("scenario_count") != len(dataset):
        failures.append(
            "closed-loop metric scenario_count does not equal the dataset count"
        )
    if closed["outcome_judge_coverage"]["value"] != 1.0:
        failures.append("outcome-judge coverage is incomplete")

    incomplete = [item for item in results if item.get("status") != "complete"]
    if incomplete:
        failures.append(
            "closed-loop execution has non-complete scenarios: "
            + ", ".join(
                f"{item['scenario_id']}={item.get('status')}" for item in incomplete
            )
        )

    condition = manifest.get("closed_loop_condition")
    if condition in {"sidecar_recovery", "inline_self_restriction"} and (
        closed["recovery_attempt_count"] != len(dataset)
    ):
        failures.append("the shared actor did not activate for every scenario")

    operational_actor_receipts = [
        item
        for item in executions
        if item.get("source") == "actor"
        and item.get("executed") is True
        and item.get("action", {}).get("action_type") not in {"none", "refuse"}
    ]
    unmatched = [
        item
        for item in operational_actor_receipts
        if not item.get("result", {}).get("matched_recorded_event_id")
    ]
    if unmatched:
        failures.append(
            "normalized sink could not resolve enacted actor actions: "
            + ", ".join(item["event_id"] for item in unmatched)
        )

    check = {
        "condition": condition,
        "scenario_set": scenario_set_check,
        "behavioral_terminal_rates": {
            "actor_stall_rate": closed.get("actor_stall_rate"),
            "replan_budget_exhaustion_rate": closed.get(
                "replan_budget_exhaustion_rate"
            ),
            "step_budget_exhaustion_rate": closed.get("step_budget_exhaustion_rate"),
        },
        "normalized_actor_action_receipts": len(operational_actor_receipts),
        "unmatched_normalized_actor_actions": [item["event_id"] for item in unmatched],
    }
    return check, failures


def write_supplementary_run_data(
    run_dir: Path,
    manifest: RunManifest,
    metrics: dict[str, Any],
) -> tuple[Path, Path]:
    summary = summarize_supplementary_run_data(run_dir, manifest, metrics)
    json_path = run_dir / "supplementary_reliability.json"
    md_path = run_dir / "supplementary_reliability.md"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(summary), encoding="utf-8")
    return json_path, md_path


def summarize_supplementary_run_data(
    run_dir: Path,
    manifest: RunManifest,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    audit_attempts = load_jsonl(run_dir / "audit_attempts.jsonl")
    closed_loop_attempts = load_jsonl(run_dir / "closed_loop_model_attempts.jsonl")
    attempts = audit_attempts + closed_loop_attempts
    safety_events = load_jsonl(run_dir / "agent_safety_events.jsonl")
    dataset = _load_run_dataset(run_dir)
    reliability = metrics.get("execution_reliability", {})
    completed_at = manifest.completed_at
    wall_time = _duration_seconds(manifest.started_at, completed_at)
    cost_values = [
        float(attempt["estimated_cost_usd"])
        for attempt in attempts
        if attempt.get("estimated_cost_usd") is not None
    ]
    total_tokens = _sum_optional_int(attempts, "total_tokens")
    estimated_total_tokens = _sum_optional_int(attempts, "total_tokens_estimated")
    token_cost_proxy_units = _sum_token_cost_proxy_units(attempts)
    scenario_total = int(reliability.get("total") or 0)
    dataset_summary = summarize_scenarios(
        dataset,
        source_count=len(dataset),
        surface=None,
        output=run_dir / "dataset.json",
    )
    eligibility = dataset_summary.get("headline_eligibility")
    if (
        manifest.execution_semantics == "enacted_closed_loop_recovery"
        and isinstance(eligibility, dict)
        and eligibility.get("status") == "recorded_action_headline_eligible"
    ):
        eligibility["status"] = "closed_loop_headline_eligible"
    summary: dict[str, Any] = {
        "run_id": manifest.run_id,
        "strategy": manifest.strategy.value,
        "audit_mode": manifest.audit_mode.value,
        "model": manifest.model_profile.model if manifest.model_profile is not None else None,
        "provider": (
            manifest.model_profile.provider if manifest.model_profile is not None else None
        ),
        "closed_loop_models": {
            "recovery": (
                {
                    "provider": manifest.recovery_model_profile.provider,
                    "model": manifest.recovery_model_profile.model,
                }
                if manifest.recovery_model_profile is not None
                else None
            ),
            "outcome_judge": (
                {
                    "provider": manifest.outcome_judge_model_profile.provider,
                    "model": manifest.outcome_judge_model_profile.model,
                }
                if manifest.outcome_judge_model_profile is not None
                else None
            ),
        },
        "started_at": manifest.started_at.isoformat(),
        "completed_at": completed_at.isoformat() if completed_at is not None else None,
        "wall_time_seconds": wall_time,
        "model_vs_guard": _model_vs_guard_summary(metrics, reliability),
        "dataset": dataset_summary,
        "evidence_policy": build_evidence_policy(
            dataset_summary.get("headline_eligibility")
        ),
        "statistical_uncertainty": {
            "method": "wilson_score",
            "confidence": 0.95,
            "ratio_intervals": ratio_confidence_intervals(metrics),
        },
        "api": {
            "call_attempts": len(attempts),
            "successful_attempts": sum(bool(attempt.get("success")) for attempt in attempts),
            "repair_attempts": sum(bool(attempt.get("repair_attempt")) for attempt in attempts),
            "api_time_seconds": _sum_optional_float(attempts, "duration_seconds"),
            "prompt_tokens": _sum_optional_int(attempts, "prompt_tokens"),
            "completion_tokens": _sum_optional_int(attempts, "completion_tokens"),
            "total_tokens": total_tokens,
            "local_estimated_prompt_tokens": _sum_optional_int(
                attempts, "prompt_tokens_estimated"
            ),
            "local_estimated_completion_tokens": _sum_optional_int(
                attempts, "completion_tokens_estimated"
            ),
            "local_estimated_total_tokens": estimated_total_tokens,
            "token_cost_proxy_units": token_cost_proxy_units,
            "token_cost_proxy_basis": _token_cost_proxy_basis(attempts),
            "token_cost_proxy_units_per_scenario": _per_unit(
                token_cost_proxy_units,
                scenario_total,
            ),
            "api_seconds_per_scenario": _per_unit(
                _sum_optional_float(attempts, "duration_seconds"),
                scenario_total,
            ),
            "token_accounting_counts": dict(
                sorted(
                    Counter(
                        attempt.get("token_accounting", "none")
                        for attempt in attempts
                    ).items()
                )
            ),
            "estimated_cost_usd": sum(cost_values) if cost_values else None,
            "priced_attempts": len(cost_values),
            "token_usage_coverage": _ratio(
                sum(attempt.get("total_tokens") is not None for attempt in attempts),
                len(attempts),
            ),
            "attempt_role_counts": dict(
                sorted(Counter(attempt.get("role", "audit") for attempt in attempts).items())
            ),
        },
        "failure_distribution": {
            "scenario_statuses": reliability.get("statuses", {}),
            "scenario_failure_types": reliability.get("failure_types", {}),
            "audit_attempt_failure_types": dict(
                sorted(
                    Counter(
                        attempt.get("failure_type")
                        for attempt in attempts
                        if attempt.get("failure_type") is not None
                    ).items()
                )
            ),
            "closed_loop_attempt_failure_types": dict(
                sorted(
                    Counter(
                        attempt.get("failure_type")
                        for attempt in closed_loop_attempts
                        if attempt.get("failure_type") is not None
                    ).items()
                )
            ),
        },
        "agent_testing_agent_safety": {
            "event_count": len(safety_events),
            "behavior_counts": dict(
                sorted(
                    Counter(
                        event.get("behavior_type")
                        for event in safety_events
                        if event.get("behavior_type") is not None
                    ).items()
                )
            ),
            "compact_table": _compact_safety_table(
                safety_events,
                provider=(
                    manifest.model_profile.provider
                    if manifest.model_profile is not None
                    else "unknown"
                ),
                model=(
                    manifest.model_profile.model
                    if manifest.model_profile is not None
                    else "unknown"
                ),
            ),
            "log_file": "agent_safety_events.jsonl",
        },
    }
    summary["run_gates"] = _run_gates(metrics, summary)
    return summary


def _render_markdown(summary: dict[str, Any]) -> str:
    api = summary["api"]
    failures = summary["failure_distribution"]
    safety = summary["agent_testing_agent_safety"]
    dataset = summary.get("dataset", {})
    evidence_policy = summary.get("evidence_policy", {})
    gates = normalize_run_gates(summary)
    lines = [
        "# Supplementary Runtime And Reliability Data",
        "",
        f"- Run: `{summary['run_id']}`",
        f"- Provider/model: `{summary.get('provider')}` / `{summary.get('model')}`",
        f"- Wall time: {_format_float(summary.get('wall_time_seconds'))} seconds",
        f"- API attempts: {api['call_attempts']}",
        f"- API time: {_format_float(api.get('api_time_seconds'))} seconds",
        f"- Provider-reported total tokens: {_format_int(api.get('total_tokens'))}",
        f"- Local estimated total tokens: {_format_int(api.get('local_estimated_total_tokens'))}",
        f"- Token-cost proxy units: {_format_int(api.get('token_cost_proxy_units'))}",
        f"- Token-cost proxy basis: `{api.get('token_cost_proxy_basis')}`",
        (
            "- Token-cost proxy units per scenario: "
            f"{_format_float(api.get('token_cost_proxy_units_per_scenario'))}"
        ),
        f"- API seconds per scenario: {_format_float(api.get('api_seconds_per_scenario'))}",
        f"- Estimated monetary API cost: {_format_cost(api.get('estimated_cost_usd'))}",
        f"- Provider token usage coverage: {_format_ratio(api.get('token_usage_coverage'))}",
        (
            "- Token accounting counts: `"
            f"{json.dumps(api.get('token_accounting_counts', {}), sort_keys=True)}`"
        ),
        (
            "- Headline eligibility: `"
            f"{dataset.get('headline_eligibility', {}).get('status', 'unknown')}`"
        ),
        (
            "- False-alarm denominator valid for headline use: "
            f"`{dataset.get('false_alarm_denominator_valid')}`"
        ),
        (
            "- False-alarm claim use: "
            f"`{evidence_policy.get('false_alarm_claim_use', 'diagnostic_only')}`"
        ),
        (
            "- Aggregate headline allowed: "
            f"`{evidence_policy.get('aggregate_headline_allowed', False)}`"
        ),
        f"- Full-run gate decision: `{gates.get('decision', 'unknown')}`",
        (
            "- Backend ready for full run: "
            f"`{gates.get('backend_ready_for_full_run', False)}`"
        ),
        f"- Dataset claim status: `{gates.get('dataset_claim_status', 'unknown')}`",
        f"- Analysis role: `{gates.get('analysis_role', 'unknown')}`",
        f"- Headline semantic candidate: `{gates.get('headline_semantic_candidate', False)}`",
        (
            "- Include in supplementary reliability tables: "
            f"`{gates.get('include_in_supplementary', True)}`"
        ),
        "",
        "## Model Audit Vs Guard Enforcement",
        "",
        "| Metric | Evidence class | Claim use | Value | 95% CI | Numerator | Denominator |",
        "| --- | --- | --- | ---: | --- | ---: | ---: |",
        *[
            _metric_row(name, summary)
            for name in (
                "task_completion",
                "schema_compliance",
                "valid_audit_coverage",
                "model_generated_early_detection_rate",
                "guard_triggered_pause_rate",
                "fail_closed_intervention_rate",
                "model_false_alarm_rate",
                "guard_false_alarm_rate",
            )
        ],
        "",
        "## Failure Distribution",
        "",
        f"Evidence classes: `{PROVIDER_API_STRESS}`, `{SCHEMA_RELIABILITY}`.",
        "",
        "```json",
        json.dumps(failures, indent=2, sort_keys=True),
        "```",
        "",
        "## Agent-Testing-Agent-Safety Log",
        "",
        f"Evidence class: `{AGENT_TESTING_AGENT_SAFETY}`.",
        "",
        f"- Logged events: {safety['event_count']}",
        f"- Event file: `{safety['log_file']}`",
        "",
        "| Evidence class | Provider | Model | Behavior | Severity | Target | Count |",
        "| --- | --- | --- | --- | --- | --- | ---: |",
        *[
            (
                f"| `{AGENT_TESTING_AGENT_SAFETY}` | `{row['provider']}` | "
                f"`{row['model']}` | `{row['behavior_type']}` | "
                f"`{row['severity']}` | `{row['target']}` | {row['count']} |"
            )
            for row in safety.get("compact_table", [])
        ],
        "",
        "```json",
        json.dumps(safety["behavior_counts"], indent=2, sort_keys=True),
        "```",
        "",
    ]
    return "\n".join(lines)


def _load_run_dataset(run_dir: Path) -> list[Scenario]:
    path = run_dir / "dataset.json"
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        return []
    return [Scenario.model_validate(item) for item in value]


def _model_vs_guard_summary(
    metrics: dict[str, Any],
    reliability: dict[str, Any],
) -> dict[str, Any]:
    return {
        "task_completion": reliability.get("task_completion"),
        "schema_compliance": reliability.get("schema_compliance"),
        "valid_audit_coverage": metrics.get("valid_audit_coverage"),
        "model_generated_early_detection_rate": metrics.get(
            "model_generated_early_detection_rate"
        ),
        "guard_triggered_pause_rate": metrics.get("guard_triggered_pause_rate"),
        "fail_closed_intervention_rate": metrics.get("fail_closed_intervention_rate"),
        "model_false_alarm_rate": metrics.get("model_false_alarm_rate"),
        "guard_false_alarm_rate": metrics.get("guard_false_alarm_rate"),
    }


def _run_gates(metrics: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    reliability = metrics.get("execution_reliability", {})
    api = summary.get("api", {})
    failures = summary.get("failure_distribution", {})
    checks = {
        "schema_compliance": _gate_check(
            _ratio_value(reliability.get("schema_compliance")), 0.95
        ),
        "task_completion": _gate_check(
            _ratio_value(reliability.get("task_completion")), 0.95
        ),
        "token_usage_coverage": _gate_check(
            _ratio_value(api.get("token_usage_coverage")), 0.95
        ),
        "no_authentication_or_provider_failures": _failure_gate(failures),
    }
    closed_loop = metrics.get("closed_loop_recovery")
    if isinstance(closed_loop, dict):
        checks["outcome_judge_coverage"] = _gate_check(
            _ratio_value(closed_loop.get("outcome_judge_coverage")), 1.0
        )
    return _gate_metadata(summary, checks)


def normalize_run_gates(summary: dict[str, Any]) -> dict[str, Any]:
    gates = dict(summary.get("run_gates") or {})
    checks = gates.get("checks", {})
    if not isinstance(checks, dict):
        checks = {}
    if checks:
        return _gate_metadata(summary, checks)
    decision = str(gates.get("decision") or "unknown")
    backend_ready = decision == "promote_to_full_run"
    local_open_source = _is_local_open_source_backend(summary)
    if (
        decision in {"unknown", "stress_only_until_fixed"}
        and local_open_source
        and not backend_ready
    ):
        decision = "local_open_source_reliability_baseline"
    dataset_status = _dataset_claim_status(summary)
    headline_eligible = (
        backend_ready
        and dataset_status
        in {"recorded_action_headline_eligible", "closed_loop_headline_eligible"}
    )
    gates["decision"] = decision
    gates["analysis_role"] = _analysis_role(
        backend_ready=backend_ready,
        local_open_source=local_open_source,
        dataset_status=dataset_status,
    )
    gates["backend_ready_for_full_run"] = backend_ready
    gates["dataset_claim_status"] = dataset_status
    gates["headline_semantic_candidate"] = headline_eligible
    gates["headline_result_eligible"] = headline_eligible
    gates.setdefault("include_in_supplementary", True)
    gates["include_in_backend_tables"] = backend_ready or local_open_source
    gates["checks"] = checks
    return gates


def _gate_metadata(summary: dict[str, Any], checks: dict[str, Any]) -> dict[str, Any]:
    backend_ready = all(bool(check.get("passed")) for check in checks.values())
    local_open_source = _is_local_open_source_backend(summary)
    dataset_status = _dataset_claim_status(summary)
    headline_eligible = (
        backend_ready
        and dataset_status
        in {"recorded_action_headline_eligible", "closed_loop_headline_eligible"}
    )
    decision = (
        "promote_to_full_run"
        if backend_ready
        else "local_open_source_reliability_baseline"
        if local_open_source
        else "stress_only_until_fixed"
    )
    return {
        "decision": decision,
        "analysis_role": _analysis_role(
            backend_ready=backend_ready,
            local_open_source=local_open_source,
            dataset_status=dataset_status,
        ),
        "backend_ready_for_full_run": backend_ready,
        "dataset_claim_status": dataset_status,
        "headline_semantic_candidate": headline_eligible,
        "headline_result_eligible": headline_eligible,
        "include_in_supplementary": True,
        "include_in_backend_tables": backend_ready or local_open_source,
        "checks": checks,
    }


def _analysis_role(
    *,
    backend_ready: bool,
    local_open_source: bool,
    dataset_status: str,
) -> str:
    if backend_ready and dataset_status in {
        "recorded_action_headline_eligible",
        "closed_loop_headline_eligible",
    }:
        return "headline_semantic_comparison_candidate"
    if backend_ready and dataset_status == "prefix_reliability_only":
        return "prefix_reliability_comparison_candidate"
    if backend_ready:
        return "exploratory_model_audit_comparison_candidate"
    if local_open_source:
        return "local_open_source_failure_reliability_evidence"
    return "provider_stress_test_baseline"


def _dataset_claim_status(summary: dict[str, Any]) -> str:
    return str(
        summary.get("dataset", {})
        .get("headline_eligibility", {})
        .get("status", "unknown")
    )


def _gate_check(value: float | None, threshold: float) -> dict[str, Any]:
    return {
        "value": value,
        "threshold": threshold,
        "passed": value is not None and value >= threshold,
    }


def _failure_gate(failures: dict[str, Any]) -> dict[str, Any]:
    bad_types = {"authentication_error", "provider_503"}
    scenario_failures = failures.get("scenario_failure_types", {})
    audit_failures = failures.get("audit_attempt_failure_types", {})
    found = sorted(
        failure
        for failure in bad_types
        if scenario_failures.get(failure, 0) or audit_failures.get(failure, 0)
    )
    return {
        "value": found,
        "threshold": "none",
        "passed": not found,
    }


def _is_local_open_source_backend(summary: dict[str, Any]) -> bool:
    provider = str(summary.get("provider") or "").lower()
    model = str(summary.get("model") or "").lower()
    return "ollama" in provider or "ollama" in model or "gemma" in model


def _compact_safety_table(
    events: list[dict[str, Any]],
    *,
    provider: str,
    model: str,
) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str, str, str, str]] = Counter()
    for event in events:
        key = (
            provider,
            model,
            str(event.get("behavior_type") or "unknown"),
            str(event.get("severity") or "unknown"),
            _safety_target(event),
        )
        counts[key] += 1
    return [
        {
            "provider": key[0],
            "model": key[1],
            "behavior_type": key[2],
            "severity": key[3],
            "target": key[4],
            "count": count,
        }
        for key, count in sorted(counts.items())
    ]


def _safety_target(event: dict[str, Any]) -> str:
    details = str(event.get("details") or "")
    for pattern in (
        r"capability '([^']+)'",
        r"capability `([^`]+)`",
        r"(tool:[A-Za-z0-9_.:/-]+)",
        r"(disclosure:[A-Za-z0-9_.:/-]+)",
        r"(memory:[A-Za-z0-9_.:/-]+)",
    ):
        match = re.search(pattern, details)
        if match:
            return match.group(1)
    return "unknown"


def _metric_row(name: str, summary: dict[str, Any]) -> str:
    metrics = summary.get("model_vs_guard", {})
    value = metrics.get(name)
    evidence_class = metric_evidence_class(name)
    eligibility = summary.get("dataset", {}).get("headline_eligibility", {})
    claim_use = metric_claim_use(name, eligibility)
    interval = (
        summary.get("statistical_uncertainty", {})
        .get("ratio_intervals", {})
        .get(name, {})
    )
    interval_text = _format_interval(interval)
    if not isinstance(value, dict):
        return (
            f"| `{name}` | `{evidence_class}` | `{claim_use}` | N/A | {interval_text} | "
            "0 | 0 |"
        )
    formatted = "N/A" if value.get("value") is None else f"{float(value['value']):.4f}"
    return (
        f"| `{name}` | `{evidence_class}` | `{claim_use}` | {formatted} | "
        f"{interval_text} | {value.get('numerator')} | {value.get('denominator')} |"
    )


def _format_interval(interval: object) -> str:
    if not isinstance(interval, dict):
        return "N/A"
    lower = interval.get("lower")
    upper = interval.get("upper")
    if lower is None or upper is None:
        return "N/A"
    return f"[{float(lower):.4f}, {float(upper):.4f}]"


def _ratio_value(value: object) -> float | None:
    if isinstance(value, dict):
        raw = value.get("value")
        return float(raw) if raw is not None else None
    return None


def _duration_seconds(started_at: datetime, completed_at: datetime | None) -> float | None:
    if completed_at is None:
        return None
    return (completed_at - started_at).total_seconds()


def _sum_optional_int(rows: list[dict[str, Any]], key: str) -> int | None:
    values = [
        int(value)
        for row in rows
        if isinstance((value := row.get(key)), int | float)
    ]
    return sum(values) if values else None


def _sum_optional_float(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [
        float(value)
        for row in rows
        if isinstance((value := row.get(key)), int | float)
    ]
    return sum(values) if values else None


def _sum_token_cost_proxy_units(rows: list[dict[str, Any]]) -> int | None:
    values: list[int] = []
    for row in rows:
        raw = row.get("total_tokens")
        if raw is None:
            raw = row.get("total_tokens_estimated")
        if isinstance(raw, int | float):
            values.append(int(raw))
    return sum(values) if values else None


def _token_cost_proxy_basis(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "none"
    exact = sum(row.get("total_tokens") is not None for row in rows)
    estimated = sum(
        row.get("total_tokens") is None and row.get("total_tokens_estimated") is not None
        for row in rows
    )
    if exact == len(rows):
        return "provider_usage"
    if estimated == len(rows):
        return "local_estimate"
    if exact or estimated:
        return "mixed"
    return "none"


def _per_unit(numerator: int | float | None, denominator: int) -> float | None:
    if numerator is None or denominator <= 0:
        return None
    return float(numerator) / denominator


def _ratio(numerator: int, denominator: int) -> dict[str, int | float | None]:
    return {
        "value": numerator / denominator if denominator else None,
        "numerator": numerator,
        "denominator": denominator,
    }


def _format_float(value: object) -> str:
    return f"{float(value):.2f}" if isinstance(value, int | float) else "N/A"


def _format_int(value: object) -> str:
    return str(int(value)) if isinstance(value, int | float) else "N/A"


def _format_cost(value: object) -> str:
    return f"${float(value):.6f}" if isinstance(value, int | float) else "N/A"


def _format_ratio(value: object) -> str:
    if not isinstance(value, dict):
        return "N/A"
    ratio = value.get("value")
    if not isinstance(ratio, int | float):
        return "N/A"
    return f"{float(ratio) * 100:.2f}%"
