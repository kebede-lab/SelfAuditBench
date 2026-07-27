"""Generate concise Markdown result reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from selfauditbench.evaluation.evidence import (
    LABEL_SURFACE_DIAGNOSTICS,
    PROVIDER_API_STRESS,
    SCHEMA_RELIABILITY,
    metric_claim_scope,
    metric_claim_use,
    metric_evidence_class,
)
from selfauditbench.evaluation.supplementary import normalize_run_gates


def render_report(
    metrics: dict[str, Any],
    title: str = "SelfAuditBench Run Report",
    supplementary: dict[str, Any] | None = None,
) -> str:
    reliability = metrics["execution_reliability"]
    eligibility = (
        supplementary.get("dataset", {}).get("headline_eligibility", {})
        if supplementary
        else {}
    )
    intervals = (
        supplementary.get("statistical_uncertainty", {}).get("ratio_intervals", {})
        if supplementary
        else {}
    )
    closed_loop = metrics.get("closed_loop_recovery")
    enacted = isinstance(closed_loop, dict)
    lines = [
        f"# {title}",
        "",
        "## Execution-Evidence Scope",
        "",
        (
            "This run enacts controller feedback, fresh actor proposals, monotonic "
            "permission state, broker-gated sink execution, and role-separated outcome "
            "judgment. Recorded-prefix and broker-projection measures remain separately "
            "identified."
            if enacted
            else "The model auditor is evaluated over the full recorded trace. Broker "
            "metrics use an absorbing terminal projection at the first non-`allow` "
            "decision. Live sink conformance and AFTraj prefix evidence retain their "
            "separate execution contracts."
        ),
        "",
        "## Model Audit Vs Guard Enforcement",
        "",
        "These metrics separate semantic model audits from fail-closed broker protection.",
        "",
        (
            "| Metric | Evidence class | Claim scope | Claim use | Value | 95% CI | "
            "Numerator | Denominator |"
        ),
        "| --- | --- | --- | --- | ---: | --- | ---: | ---: |",
    ]
    model_vs_guard = supplementary.get("model_vs_guard", {}) if supplementary else {}
    top_summary = {
        "task_completion": reliability.get("task_completion"),
        "schema_compliance": reliability.get("schema_compliance"),
        **{
            key: model_vs_guard.get(key, metrics.get(key))
            for key in (
                "valid_audit_coverage",
                "model_generated_early_detection_rate",
                "guard_triggered_pause_rate",
                "fail_closed_intervention_rate",
                "model_false_alarm_rate",
                "guard_false_alarm_rate",
            )
        },
    }
    for key in (
        "task_completion",
        "schema_compliance",
        "valid_audit_coverage",
        "model_generated_early_detection_rate",
        "guard_triggered_pause_rate",
        "fail_closed_intervention_rate",
        "model_false_alarm_rate",
        "guard_false_alarm_rate",
    ):
        value = top_summary.get(key)
        if not isinstance(value, dict):
            continue
        formatted = "N/A" if value["value"] is None else f"{value['value']:.4f}"
        lines.append(
            _metric_row(
                key,
                formatted,
                value["numerator"],
                value["denominator"],
                eligibility,
                intervals.get(key),
            )
        )

    if supplementary is not None:
        eligibility = supplementary.get("dataset", {}).get("headline_eligibility", {})
        gates = normalize_run_gates(supplementary)
        lines.extend(
            [
                "",
                "## Headline Eligibility And Full-Run Gates",
                "",
                f"- Headline status: `{eligibility.get('status', 'unknown')}`",
                (
                    "- False-alarm denominator valid for headline use: "
                    f"`{eligibility.get('false_alarm_denominator_valid')}`"
                ),
                f"- Full-run gate decision: `{gates.get('decision', 'unknown')}`",
                (
                    "- Backend ready for full run: "
                    f"`{gates.get('backend_ready_for_full_run', False)}`"
                ),
                f"- Dataset claim status: `{gates.get('dataset_claim_status', 'unknown')}`",
                f"- Analysis role: `{gates.get('analysis_role', 'unknown')}`",
                (
                    "- Recorded-action semantic candidate: "
                    f"`{gates.get('headline_semantic_candidate', False)}`"
                ),
                (
                    "- Include in supplementary reliability tables: "
                    f"`{gates.get('include_in_supplementary', True)}`"
                ),
                "",
            ]
        )

    if enacted:
        assert isinstance(closed_loop, dict)
        lines.extend(
            [
                "## Enacted Closed-Loop Recovery",
                "",
                (
                    "These outcomes use broker feedback, sink receipts, and the "
                    "role-separated outcome judgment."
                ),
                "",
                (
                    "| Metric | Evidence class | Claim scope | Claim use | Value | "
                    "95% CI | Numerator | Denominator |"
                ),
                "| --- | --- | --- | --- | ---: | --- | ---: | ---: |",
            ]
        )
        for key in (
            "intervention_exposure_rate",
            "recovery_success_rate",
            "safety_success_rate",
            "task_success_rate",
            "safe_task_success_rate",
            "risky_harm_avoidance_rate",
            "benign_task_success_rate",
            "benign_noninterference_rate",
            "permission_compliance_rate",
            "no_repeated_denied_action_rate",
            "outcome_judge_coverage",
            "replan_budget_exhaustion_rate",
            "step_budget_exhaustion_rate",
            "actor_stall_rate",
        ):
            value = closed_loop.get(key)
            if not isinstance(value, dict):
                continue
            formatted = "N/A" if value["value"] is None else f"{value['value']:.4f}"
            lines.append(
                _metric_row(
                    key,
                    formatted,
                    value["numerator"],
                    value["denominator"],
                    eligibility,
                    intervals.get(f"closed_loop_recovery.{key}"),
                )
            )
        lines.extend(
            [
                "",
                "Closed-loop counts, terminal reasons, and burden scalars:",
                "",
                "```json",
                json.dumps(closed_loop, indent=2, sort_keys=True),
                "```",
                "",
            ]
        )

    lines.extend(
        [
            "## Recorded-Action Replay Metrics",
            "",
            (
                "These include fail-closed schema-guard interventions in the absorbing "
                "terminal projection. Use the model-vs-guard section above to "
                "distinguish model-generated detections from broker protection."
            ),
            "",
        (
            "| Metric | Evidence class | Claim scope | Claim use | Value | 95% CI | "
            "Numerator | Denominator |"
        ),
        "| --- | --- | --- | --- | ---: | --- | ---: | ---: |",
        ]
    )
    for key in (
        "early_risk_detection_rate",
        "model_generated_early_detection_rate",
        "first_sufficient_prefix_recall",
        "model_generated_first_sufficient_prefix_recall",
        "pre_harm_intervention_rate",
        "fail_closed_intervention_rate",
        "false_alarm_rate",
        "model_false_alarm_rate",
        "guard_false_alarm_rate",
        "broker_policy_false_alarm_rate",
        "benign_noninterference_rate",
        "model_intervention_acceptability_rate",
        "enforced_intervention_acceptability_rate",
        "terminal_projection_harm_rate",
        "terminal_projection_harm_avoidance_rate",
        "label_concordant_outcome_rate",
        "evidence_reference_validity",
        "flagged_audit_evidence_coverage",
        "intended_action_binding_rate",
        "least_restriction_accuracy",
        "audit_action_consistency",
    ):
        if key not in metrics:
            continue
        value = metrics[key]
        formatted = "N/A" if value["value"] is None else f"{value['value']:.4f}"
        lines.append(
            _metric_row(
                key,
                formatted,
                value["numerator"],
                value["denominator"],
                eligibility,
                intervals.get(key),
            )
        )

    lines.extend(
        [
            "",
            "## Scalar metrics",
            "",
            (
                "`utility_retention` is the current replay pass-through proxy; it is not "
                "post-intervention task utility."
            ),
            "",
            "| Metric | Evidence class | Claim scope | Claim use | Value |",
            "| --- | --- | --- | --- | ---: |",
        ]
    )
    for key in (
        "brier_score",
        "expected_calibration_error",
        "utility_retention",
        "permission_reduction_latency",
        "over_restriction_magnitude",
        "permission_delta_component_excess",
    ):
        if key not in metrics:
            continue
        value = metrics[key]
        formatted = "N/A" if value is None else f"{value:.4f}"
        lines.append(
            f"| `{key}` | `{metric_evidence_class(key)}` | "
            f"`{metric_claim_scope(key, eligibility)}` | "
            f"`{metric_claim_use(key, eligibility)}` | {formatted} |"
        )

    lines.extend(
        [
            "",
            "## Prefix localization",
            "",
            f"Evidence class: `{LABEL_SURFACE_DIAGNOSTICS}`. ",
            f"Claim use: `{metric_claim_use('prefix_localization', eligibility)}`.",
            "",
            "Recorded-trace prefix localization, including fail-closed guard audits:",
            "",
            "```json",
            json.dumps(metrics["prefix_localization"], indent=2, sort_keys=True),
            "```",
            "",
            "Model-generated prefix localization, excluding fail-closed guard audits:",
            "",
            "```json",
            json.dumps(metrics.get("model_prefix_localization", {}), indent=2, sort_keys=True),
            "```",
            "",
            "## Reliability",
            "",
            f"Evidence classes: `{SCHEMA_RELIABILITY}`, `{PROVIDER_API_STRESS}`.",
            "",
            f"Total scenarios: **{reliability['total']}**",
            "",
            (
                "The persisted `task_completion` field means audit-pipeline completion, "
                "not completion of a rerun native task after intervention."
            ),
            "",
            "```json",
            json.dumps(reliability, indent=2, sort_keys=True),
            "```",
            "",
            "## Supplementary Data",
            "",
            (
                "- `supplementary_reliability.json` and `supplementary_reliability.md` "
                "record per-run API time, provider token usage, local estimated token-cost "
                "proxies, optional estimated monetary cost, and failure distributions."
            ),
            (
                "- `agent_safety_events.jsonl` records the separate "
                "agent-testing-agent-safety log for behaviors such as schema-guard loops, "
                "self-audit repair loops, permission escalation attempts, repeated "
                "forbidden actions, and excessive disclosure proposals."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _metric_row(
    name: str,
    formatted: str,
    numerator: object,
    denominator: object,
    eligibility: dict[str, Any],
    interval: object,
) -> str:
    interval_text = _format_interval(interval)
    return (
        f"| `{name}` | `{metric_evidence_class(name)}` | "
        f"`{metric_claim_scope(name, eligibility)}` | "
        f"`{metric_claim_use(name, eligibility)}` | {formatted} | {interval_text} | "
        f"{numerator} | {denominator} |"
    )


def _format_interval(interval: object) -> str:
    if not isinstance(interval, dict):
        return "N/A"
    lower = interval.get("lower")
    upper = interval.get("upper")
    if lower is None or upper is None:
        return "N/A"
    return f"[{float(lower):.4f}, {float(upper):.4f}]"


def write_report(run_dir: Path, metrics: dict[str, Any]) -> Path:
    path = run_dir / "report.md"
    supplementary_path = run_dir / "supplementary_reliability.json"
    supplementary = (
        json.loads(supplementary_path.read_text(encoding="utf-8"))
        if supplementary_path.exists()
        else None
    )
    path.write_text(render_report(metrics, supplementary=supplementary), encoding="utf-8")
    return path
