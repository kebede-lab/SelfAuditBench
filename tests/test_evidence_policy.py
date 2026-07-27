from selfauditbench.evaluation.evidence import (
    ABSORBING_TERMINAL_PROJECTION,
    AFTRAJ_PREFIX_ONLY,
    ANNOTATION_STUDY_RELIABILITY,
    RECORDED_ACTION_REPLAY,
    build_evidence_policy,
    metric_claim_scope,
    metric_claim_use,
    metric_evidence_class,
)


def test_weak_false_alarm_metrics_are_diagnostic_only() -> None:
    eligibility = {
        "status": "supplementary_exploratory",
        "false_alarm_denominator_valid": False,
    }

    policy = build_evidence_policy(eligibility)

    assert policy["aggregate_headline_allowed"] is False
    assert policy["enacted_behavior_headline_allowed"] is False
    assert policy["cross_surface_headline_pooling_allowed"] is False
    assert policy["claim_scopes"]["primary"] == RECORDED_ACTION_REPLAY
    assert policy["metric_classes"][ANNOTATION_STUDY_RELIABILITY] == [
        "independent_annotation_agreement",
        "adjudication_completeness",
        "annotation_artifact_hashes",
    ]
    assert policy["false_alarm_claim_use"] == "diagnostic_only"
    assert metric_claim_use("model_false_alarm_rate", eligibility) == "diagnostic_only"
    assert metric_evidence_class("model_false_alarm_rate") == "model_audit_quality"
    assert metric_evidence_class("guard_false_alarm_rate") == "broker_guard_behavior"


def test_agentforesight_metrics_remain_prefix_only() -> None:
    eligibility = {
        "status": "prefix_reliability_only",
        "false_alarm_denominator_valid": False,
    }

    assert metric_claim_use("model_generated_early_detection_rate", eligibility) == (
        "prefix_reliability_only"
    )
    assert metric_claim_use("prefix_localization", eligibility) == (
        "prefix_reliability_only"
    )
    assert metric_claim_scope("prefix_localization", eligibility) == AFTRAJ_PREFIX_ONLY


def test_adjudicated_recorded_action_metrics_can_be_headline_eligible() -> None:
    eligibility = {
        "status": "recorded_action_headline_eligible",
        "false_alarm_denominator_valid": True,
    }

    policy = build_evidence_policy(eligibility)

    assert policy["aggregate_headline_allowed"] is True
    assert policy["recorded_action_headline_allowed"] is True
    assert policy["enacted_behavior_headline_allowed"] is False
    assert metric_claim_scope("least_restriction_accuracy", eligibility) == (
        ABSORBING_TERMINAL_PROJECTION
    )
    assert policy["false_alarm_claim_use"] == "headline_eligible"
    assert metric_claim_use("least_restriction_accuracy", eligibility) == (
        "headline_eligible"
    )


def test_adjudicated_surfaces_must_not_be_pooled_for_headline_use() -> None:
    policy = build_evidence_policy(
        {
            "status": "recorded_action_headline_eligible",
            "false_alarm_denominator_valid": True,
            "source_datasets": ["asb", "converse"],
        }
    )

    assert policy["recorded_action_headline_allowed"] is True
    assert policy["aggregate_headline_allowed"] is False
    assert policy["cross_surface_headline_pooling_allowed"] is False
