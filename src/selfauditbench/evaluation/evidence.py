"""Evidence classes and claim boundaries for benchmark outputs."""

from __future__ import annotations

from typing import Any

MODEL_AUDIT_QUALITY = "model_audit_quality"
BROKER_GUARD_BEHAVIOR = "broker_guard_behavior"
SCHEMA_RELIABILITY = "schema_reliability"
PROVIDER_API_STRESS = "provider_api_stress"
LABEL_SURFACE_DIAGNOSTICS = "label_surface_diagnostics"
AGENT_TESTING_AGENT_SAFETY = "agent_testing_agent_safety"
ANNOTATION_STUDY_RELIABILITY = "annotation_study_reliability"
ENACTED_CLOSED_LOOP_RECOVERY = "enacted_closed_loop_recovery"

# Claim scopes stay separate from evidence classes: recorded-action projection,
# enacted recovery, live sink conformance, and AFTraj prefix localization each have
# their own execution contract.
RECORDED_ACTION_REPLAY = "recorded_action_replay"
ABSORBING_TERMINAL_PROJECTION = "absorbing_terminal_projection"
ENACTED_SINK_CONFORMANCE = "enacted_live_sink_conformance"
AFTRAJ_PREFIX_ONLY = "aftraj_prefix_only"
ENACTED_RECOVERY = "enacted_closed_loop_recovery"

_CLOSED_LOOP_METRICS = {
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
    "closed_loop_safety",
    "closed_loop_task_success",
    "closed_loop_safe_task_success",
    "closed_loop_recovery_success",
    "closed_loop_harm_avoidance",
    "closed_loop_benign_noninterference",
    "closed_loop_no_repeated_denied_action",
    "closed_loop_permission_compliance",
    "closed_loop_actor_stalled",
}

_MODEL_METRICS = {
    "valid_audit_coverage",
    "model_generated_early_detection_rate",
    "model_generated_first_sufficient_prefix_recall",
    "model_false_alarm_rate",
    "model_intervention_acceptability_rate",
    "evidence_reference_validity",
    "flagged_audit_evidence_coverage",
    "intended_action_binding_rate",
    "audit_action_consistency",
    "brier_score",
    "expected_calibration_error",
}
_BROKER_METRICS = {
    "early_risk_detection_rate",
    "first_sufficient_prefix_recall",
    "pre_harm_intervention_rate",
    "fail_closed_intervention_rate",
    "false_alarm_rate",
    "guard_false_alarm_rate",
    "broker_policy_false_alarm_rate",
    "benign_noninterference_rate",
    "guard_triggered_pause_rate",
    "guard_triggered_pause_scenario_rate",
    "least_restriction_accuracy",
    "enforced_intervention_acceptability_rate",
    "terminal_projection_harm_rate",
    "terminal_projection_harm_avoidance_rate",
    "label_concordant_outcome_rate",
    "permission_reduction_latency",
    "over_restriction_magnitude",
    "permission_delta_component_excess",
    "utility_retention",
}
_SCHEMA_METRICS = {
    "task_completion",
    "replay_processing_completion",
    "schema_compliance",
    "execution_reliability",
}
_LABEL_METRICS = {
    "prefix_localization",
    "model_prefix_localization",
    "prefix_exact_f1",
    "model_prefix_exact_f1",
    "prefix_false_alarm_rate",
    "prefix_step_accuracy",
}
_FALSE_ALARM_METRICS = {
    "false_alarm_rate",
    "model_false_alarm_rate",
    "guard_false_alarm_rate",
    "broker_policy_false_alarm_rate",
}


def metric_evidence_class(metric: str) -> str:
    if metric in _CLOSED_LOOP_METRICS:
        return ENACTED_CLOSED_LOOP_RECOVERY
    if metric in _MODEL_METRICS:
        return MODEL_AUDIT_QUALITY
    if metric in _BROKER_METRICS:
        return BROKER_GUARD_BEHAVIOR
    if metric in _SCHEMA_METRICS:
        return SCHEMA_RELIABILITY
    if metric in _LABEL_METRICS:
        return LABEL_SURFACE_DIAGNOSTICS
    return LABEL_SURFACE_DIAGNOSTICS


def metric_claim_use(metric: str, eligibility: dict[str, Any] | None) -> str:
    status = str((eligibility or {}).get("status") or "unknown")
    false_alarm_valid = bool(
        (eligibility or {}).get("false_alarm_denominator_valid", False)
    )
    evidence_class = metric_evidence_class(metric)
    if evidence_class == SCHEMA_RELIABILITY:
        return "supplementary_reliability"
    if metric in _FALSE_ALARM_METRICS and not false_alarm_valid:
        return "diagnostic_only"
    if status in {
        "recorded_action_headline_eligible",
        "closed_loop_headline_eligible",
    }:
        return "headline_eligible"
    if status == "prefix_reliability_only":
        return "prefix_reliability_only"
    if status == "supplementary_exploratory":
        return "supplementary_exploratory"
    return "diagnostic_only"


def metric_claim_scope(metric: str, eligibility: dict[str, Any] | None) -> str:
    """Return the execution-evidence boundary attached to a reported metric."""

    status = str((eligibility or {}).get("status") or "unknown")
    if metric in _CLOSED_LOOP_METRICS:
        return ENACTED_RECOVERY
    if status == "prefix_reliability_only" or metric in _LABEL_METRICS:
        return AFTRAJ_PREFIX_ONLY if status == "prefix_reliability_only" else RECORDED_ACTION_REPLAY
    if metric in _BROKER_METRICS:
        return ABSORBING_TERMINAL_PROJECTION
    return RECORDED_ACTION_REPLAY


def build_evidence_policy(eligibility: dict[str, Any] | None) -> dict[str, Any]:
    eligibility = dict(eligibility or {})
    status = str(eligibility.get("status") or "unknown")
    false_alarm_valid = bool(eligibility.get("false_alarm_denominator_valid", False))
    source_datasets = eligibility.get("source_datasets")
    cross_surface = isinstance(source_datasets, (list, tuple, set)) and len(source_datasets) > 1
    return {
        "dataset_status": status,
        "false_alarm_denominator_valid": false_alarm_valid,
        "false_alarm_claim_use": (
            "headline_eligible" if false_alarm_valid else "diagnostic_only"
        ),
        "metric_classes": {
            MODEL_AUDIT_QUALITY: sorted(_MODEL_METRICS),
            BROKER_GUARD_BEHAVIOR: sorted(_BROKER_METRICS),
            SCHEMA_RELIABILITY: sorted(_SCHEMA_METRICS),
            PROVIDER_API_STRESS: [
                "api_attempts",
                "api_time",
                "failure_distribution",
                "token_cost_proxy",
            ],
            LABEL_SURFACE_DIAGNOSTICS: sorted(_LABEL_METRICS),
            AGENT_TESTING_AGENT_SAFETY: ["agent_safety_events"],
            ANNOTATION_STUDY_RELIABILITY: [
                "independent_annotation_agreement",
                "adjudication_completeness",
                "annotation_artifact_hashes",
            ],
            ENACTED_CLOSED_LOOP_RECOVERY: sorted(_CLOSED_LOOP_METRICS),
        },
        "aggregate_headline_allowed": (
            status
            in {"recorded_action_headline_eligible", "closed_loop_headline_eligible"}
            and not cross_surface
        ),
        "recorded_action_headline_allowed": status
        in {"recorded_action_headline_eligible", "closed_loop_headline_eligible"},
        "enacted_behavior_headline_allowed": status == "closed_loop_headline_eligible",
        "cross_surface_headline_pooling_allowed": False,
        "claim_scopes": {
            "primary": RECORDED_ACTION_REPLAY,
            "broker_projection": ABSORBING_TERMINAL_PROJECTION,
            "secondary": ENACTED_SINK_CONFORMANCE,
            "closed_loop": ENACTED_RECOVERY,
            "agentforesight": AFTRAJ_PREFIX_ONLY,
        },
        "scope_note": (
            "Recorded-action runs report full-trace audits and absorbing terminal "
            "projection. Closed-loop runs report enacted broker feedback, fresh actor "
            "proposals, sink-gated execution, and independently judged outcomes."
        ),
    }
