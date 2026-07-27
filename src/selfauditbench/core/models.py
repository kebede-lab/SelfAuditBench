"""Immutable data contracts for trajectories, audits, permissions, and runs."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FrozenModel(BaseModel):
    """Base model for persisted benchmark records."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"


class Checkpoint(StrEnum):
    PRE_PLAN = "pre_plan"
    POST_MEMORY = "post_memory"
    POST_OBSERVATION = "post_observation"
    POST_MESSAGE = "post_message"
    PRE_ENVIRONMENT_QUERY = "pre_environment_query"
    PRE_DISCLOSURE = "pre_disclosure"
    PRE_TOOL = "pre_tool"
    PRE_COMMIT = "pre_commit"
    PRE_MEMORY_WRITE = "pre_memory_write"


class EventKind(StrEnum):
    TASK_RECEIVED = "task_received"
    PLAN_PROPOSAL = "plan_proposal"
    MEMORY_READ = "memory_read"
    OBSERVATION = "observation"
    MESSAGE = "message"
    ENVIRONMENT_QUERY = "environment_query"
    TOOL_PROPOSAL = "tool_proposal"
    DISCLOSURE_PROPOSAL = "disclosure_proposal"
    COMMIT_PROPOSAL = "commit_proposal"
    MEMORY_WRITE_PROPOSAL = "memory_write_proposal"
    POLICY_CHANGE = "policy_change"
    ACTION_RESULT = "action_result"
    AUDIT_RESULT = "audit_result"
    EXECUTION_FAILURE = "execution_failure"


class Provenance(StrEnum):
    USER = "user"
    AGENT = "agent"
    TOOL = "tool"
    MEMORY = "memory"
    ENVIRONMENT = "environment"
    EXTERNAL_AGENT = "external_agent"
    CONTROLLER = "controller"
    UNKNOWN = "unknown"


class Sensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class ActionType(StrEnum):
    NONE = "none"
    TOOL_CALL = "tool_call"
    ENVIRONMENT_QUERY = "environment_query"
    DISCLOSURE = "disclosure"
    MEMORY_WRITE = "memory_write"
    COMMIT = "commit"
    REFUSE = "refuse"


class RiskLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskType(StrEnum):
    PRIVACY = "privacy"
    PROMPT_INJECTION = "prompt_injection"
    MEMORY_POISONING = "memory_poisoning"
    OVERPRIVILEGE = "overprivilege"
    EXTERNAL_PRESSURE = "external_pressure"
    STALE_STATE = "stale_state"
    IRREVERSIBLE_ACTION = "irreversible_action"
    POLICY_CONFLICT = "policy_conflict"
    UNKNOWN = "unknown"


class Intervention(StrEnum):
    CONTINUE = "continue"
    SANITIZE = "sanitize"
    REVERIFY = "reverify"
    ASK_USER = "ask_user"
    DOWNGRADE = "downgrade"
    QUARANTINE = "quarantine"
    PAUSE = "pause"
    REFUSE = "refuse"


class BrokerOutcome(StrEnum):
    ALLOW = "allow"
    BLOCK_AND_REPLAN = "block_and_replan"
    PAUSE = "pause"
    REFUSE = "refuse"


class AuditEmissionMode(StrEnum):
    NONE = "none"
    SIDECAR = "sidecar"
    INLINE = "inline"
    EXTERNAL = "external"


class ClosedLoopCondition(StrEnum):
    SIDECAR_RECOVERY = "sidecar_recovery"
    INLINE_SELF_RESTRICTION = "inline_self_restriction"


class ClosedLoopTerminalReason(StrEnum):
    RECORDED_TRACE_COMPLETE = "recorded_trace_complete"
    ACTOR_COMPLETED = "actor_completed"
    ACTOR_REFUSED = "actor_refused"
    BROKER_PAUSED = "broker_paused"
    BROKER_REFUSED = "broker_refused"
    REPLAN_BUDGET_EXHAUSTED = "replan_budget_exhausted"
    STEP_BUDGET_EXHAUSTED = "step_budget_exhausted"
    ACTOR_STALLED = "actor_stalled"
    ACTOR_ERROR = "actor_error"
    JUDGE_ERROR = "judge_error"


class StrategyId(StrEnum):
    NO_AUDIT = "no_audit"
    SELF_AUDIT_LOG_ONLY = "self_audit_log_only"
    EXTERNAL_AUDITOR = "external_auditor"
    PRETOOL_GUARDRAIL = "pretool_guardrail"
    FIXED_POLICY = "fixed_policy"
    SELF_AUDIT_BROKER = "self_audit_broker"
    COMBINED_MONITOR_BROKER = "combined_monitor_broker"


class RunStatus(StrEnum):
    COMPLETE = "complete"
    TIMEOUT = "timeout"
    SCHEMA_ERROR = "schema_error"
    ADAPTER_ERROR = "adapter_error"
    BROKER_ERROR = "broker_error"
    ACTOR_ERROR = "actor_error"
    JUDGE_ERROR = "judge_error"


class FailureType(StrEnum):
    AUTHENTICATION_ERROR = "authentication_error"
    PROVIDER_503 = "provider_503"
    TIMEOUT = "timeout"
    EMPTY_RESPONSE = "empty_response"
    JSON_PARSE_ERROR = "json_parse_error"
    ENUM_VALIDATION_ERROR = "enum_validation_error"
    PERMISSION_DELTA_ERROR = "permission_delta_error"
    SCHEMA_VALIDATION_ERROR = "schema_validation_error"
    UNEXPECTED_EXCEPTION = "unexpected_exception"


class RiskyBehaviorType(StrEnum):
    SELF_AUDIT_LOOP = "self_audit_loop"
    PERMISSION_ESCALATION_ATTEMPT = "permission_escalation_attempt"
    REPEATED_FORBIDDEN_ACTION = "repeated_forbidden_action"
    EXCESSIVE_DISCLOSURE = "excessive_disclosure"
    SCHEMA_GUARD_LOOP = "schema_guard_loop"


class AnnotationStatus(StrEnum):
    PENDING = "pending"
    INDEPENDENT = "independent"
    ADJUDICATED = "adjudicated"


class LabelProvenance(StrEnum):
    """Evidence class supporting a scenario label."""

    UNLABELED = "unlabeled"
    WEAK_IMPORT = "weak_import"
    SOURCE_CURATED = "source_curated"
    SYNTHETIC_FIXTURE = "synthetic_fixture"
    HUMAN_CALIBRATION = "human_calibration"
    HUMAN_ADJUDICATED = "human_adjudicated"


class DecisionSource(StrEnum):
    """Controller-assigned cause of a broker decision."""

    ALLOW = "allow"
    AUDIT_INTERVENTION = "audit_intervention"
    SCHEMA_GUARD = "schema_guard"
    PERMISSION_POLICY = "permission_policy"
    MONOTONICITY_REJECTION = "monotonicity_rejection"
    MONITOR_ONLY = "monitor_only"


class CapabilityGrant(FrozenModel):
    """One namespaced permission and its mechanically comparable bounds."""

    capability: str = Field(pattern=r"^[a-z][a-z0-9_]*:[A-Za-z0-9_.:/-]+$")
    operations: tuple[str, ...] = ("*",)
    resources: tuple[str, ...] = ("*",)
    fields: tuple[str, ...] = ("*",)
    max_sensitivity: Sensitivity = Sensitivity.RESTRICTED
    remaining_calls: int | None = Field(default=None, ge=0)
    requires_confirmation: bool = False

    @field_validator("operations", "resources", "fields")
    @classmethod
    def normalize_unique_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(value)))


class PermissionDelta(FrozenModel):
    """A proposed monotonic permission reduction."""

    remove: tuple[str, ...] = ()
    narrow: dict[str, CapabilityGrant] = Field(default_factory=dict)
    quarantine_sources: tuple[str, ...] = ()
    disclosure_ceiling: Sensitivity | None = None

    @field_validator("remove", "quarantine_sources")
    @classmethod
    def normalize_unique_items(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(value)))


class PermissionState(FrozenModel):
    """Current enforceable permissions for one task execution."""

    grants: dict[str, CapabilityGrant] = Field(default_factory=dict)
    quarantined_sources: tuple[str, ...] = ()
    disclosure_ceiling: Sensitivity = Sensitivity.RESTRICTED
    revision: int = Field(default=0, ge=0)

    @field_validator("grants")
    @classmethod
    def grant_keys_match_capabilities(
        cls, grants: dict[str, CapabilityGrant]
    ) -> dict[str, CapabilityGrant]:
        for key, grant in grants.items():
            if key != grant.capability:
                raise ValueError(
                    f"grant key {key!r} does not match capability {grant.capability!r}"
                )
        return grants

    @field_validator("quarantined_sources")
    @classmethod
    def normalize_quarantined_sources(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(value)))


class ActionProposal(FrozenModel):
    action_type: ActionType
    capability: str | None = None
    name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    content: str | None = None
    source_refs: tuple[str, ...] = ()
    sensitivity: Sensitivity = Sensitivity.PUBLIC
    irreversible: bool = False


class TrajectoryEvent(FrozenModel):
    event_id: str
    scenario_id: str
    sequence: int = Field(ge=0)
    event_kind: EventKind
    source: Provenance
    checkpoint: Checkpoint | None = None
    sensitivity: Sensitivity = Sensitivity.PUBLIC
    reversible: bool = True
    visible_payload: dict[str, Any] = Field(default_factory=dict)
    proposed_action: ActionProposal | None = None
    raw_artifact_ref: str | None = None
    permission_revision: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditRecord(FrozenModel):
    checkpoint: Checkpoint
    actor_id: str
    risk_level: RiskLevel
    risk_types: tuple[RiskType, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    intended_action_ref: str | None = None
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Probability that observable risk requiring intervention is present.",
    )
    intervention: Intervention
    permission_delta: PermissionDelta = Field(default_factory=PermissionDelta)
    rationale: str = Field(min_length=1, max_length=1000)
    emission_mode: AuditEmissionMode
    raw_response_ref: str | None = None


class AuditAttempt(FrozenModel):
    event_id: str
    scenario_id: str
    checkpoint: Checkpoint
    actor_id: str
    emission_mode: AuditEmissionMode
    attempt_index: int = Field(ge=1)
    repair_attempt: bool = False
    success: bool = False
    failure_type: FailureType | None = None
    error_message: str | None = None
    raw_response_excerpt: str = Field(default="", max_length=2000)
    raw_response_sha256: str | None = None
    provider: str | None = None
    model: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    prompt_tokens_estimated: int | None = Field(default=None, ge=0)
    completion_tokens_estimated: int | None = Field(default=None, ge=0)
    total_tokens_estimated: int | None = Field(default=None, ge=0)
    token_accounting: Literal["provider_usage", "local_estimate", "none"] = "none"
    estimated_cost_usd: float | None = Field(default=None, ge=0)


class AuditEnvelope(FrozenModel):
    action: ActionProposal
    audit: AuditRecord


class RecoveryTurn(FrozenModel):
    """One fresh action proposed after control enters the enacted agent loop."""

    scenario_id: str
    event_id: str
    turn_index: int = Field(ge=0)
    condition: ClosedLoopCondition
    action: ActionProposal
    audit: AuditRecord | None = None
    task_complete_after_execution: bool = False
    completion_summary: str = Field(default="", max_length=1000)
    completion_summary_source: Literal["model", "framework_normalized"] = "model"


class ControllerFeedback(FrozenModel):
    """Controller observation returned to the actor before its next proposal."""

    scenario_id: str
    event_id: str
    turn_index: int = Field(ge=0)
    outcome: BrokerOutcome
    reason: str
    violations: tuple[str, ...] = ()
    permission_after: PermissionState
    action_result: dict[str, Any] = Field(default_factory=dict)


class ActionExecution(FrozenModel):
    """Action-sink receipt proving whether a proposed transition was enacted."""

    scenario_id: str
    event_id: str
    turn_index: int | None = Field(default=None, ge=0)
    origin_sequence: int | None = Field(default=None, ge=0)
    source: Literal["recorded", "actor"]
    action: ActionProposal
    broker_outcome: BrokerOutcome
    executed: bool
    permission_revision: int = Field(ge=0)
    result: dict[str, Any] = Field(default_factory=dict)


class ClosedLoopModelAttempt(FrozenModel):
    """Inspectible recovery-actor or outcome-judge model call."""

    scenario_id: str
    role: Literal["recovery_actor", "outcome_judge"]
    condition: ClosedLoopCondition
    attempt_index: int = Field(ge=1)
    turn_index: int | None = Field(default=None, ge=0)
    repair_attempt: bool = False
    success: bool = False
    failure_type: FailureType | None = None
    error_message: str | None = None
    raw_response_excerpt: str = Field(default="", max_length=2000)
    raw_response_sha256: str | None = None
    provider: str | None = None
    model: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    prompt_tokens_estimated: int | None = Field(default=None, ge=0)
    completion_tokens_estimated: int | None = Field(default=None, ge=0)
    total_tokens_estimated: int | None = Field(default=None, ge=0)
    token_accounting: Literal["provider_usage", "local_estimate", "none"] = "none"
    estimated_cost_usd: float | None = Field(default=None, ge=0)


class OutcomeJudgment(FrozenModel):
    """Independent end-state judgment for an enacted closed-loop trajectory."""

    scenario_id: str
    condition: ClosedLoopCondition
    safety_satisfied: bool
    task_satisfied: bool
    utility_score: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=2000)
    judge_id: str


class BrokerDecision(FrozenModel):
    event_id: str
    outcome: BrokerOutcome
    decision_source: DecisionSource = DecisionSource.ALLOW
    reason: str
    violations: tuple[str, ...] = ()
    permission_before: PermissionState
    permission_after: PermissionState
    requested_delta: PermissionDelta = Field(default_factory=PermissionDelta)
    applied_delta: PermissionDelta = Field(default_factory=PermissionDelta)


class RiskyBehaviorRecord(FrozenModel):
    scenario_id: str
    event_id: str | None = None
    behavior_type: RiskyBehaviorType
    actor_id: str
    severity: RiskLevel = RiskLevel.MEDIUM
    evidence_refs: tuple[str, ...] = ()
    details: str = Field(min_length=1, max_length=1000)


class ScenarioLabel(FrozenModel):
    risky: bool
    first_risk_sufficient_event: int | None = Field(default=None, ge=0)
    harm_boundary_event: int | None = Field(default=None, ge=0)
    accepted_interventions: tuple[Intervention, ...] = ()
    minimal_permission_deltas: tuple[PermissionDelta, ...] = ()
    utility_expectation: str = ""


class Scenario(FrozenModel):
    scenario_id: str
    source_dataset: str
    source_ref: str
    pair_id: str | None = None
    tags: tuple[str, ...] = ()
    weak_label: bool = False
    label_provenance: LabelProvenance = LabelProvenance.UNLABELED
    label_evidence_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    initial_permissions: PermissionState = Field(default_factory=PermissionState)
    events: tuple[TrajectoryEvent, ...]
    label: ScenarioLabel | None = None


class Annotation(FrozenModel):
    scenario_id: str
    annotator_id: str
    status: AnnotationStatus = AnnotationStatus.PENDING
    label: ScenarioLabel | None = None
    notes: str = ""


class Adjudication(FrozenModel):
    scenario_id: str
    annotation_refs: tuple[str, str]
    adjudicator_id: str
    label: ScenarioLabel
    disagreement_notes: str = ""


class ModelProfile(FrozenModel):
    provider: str
    model: str
    base_url: str | None = None
    api_key_env: str = Field(default="OPENAI_API_KEY", pattern=r"^[A-Z][A-Z0-9_]*$")
    thinking_mode: Literal["default", "disabled", "enabled"] = "default"
    timeout_seconds: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=2, ge=0)
    temperature: float | None = Field(default=0.0, ge=0, le=2)
    max_tokens: int | None = Field(default=900, ge=1)
    concise_rationale_words: int | None = Field(default=80, ge=1)
    input_cost_per_million_tokens_usd: float | None = Field(default=None, ge=0)
    output_cost_per_million_tokens_usd: float | None = Field(default=None, ge=0)


class RunManifest(FrozenModel):
    run_id: str
    strategy: StrategyId
    audit_mode: AuditEmissionMode
    config_hash: str
    dataset_hash: str
    random_seed: int
    model_profile: ModelProfile | None = None
    observer_model_profile: ModelProfile | None = None
    recovery_model_profile: ModelProfile | None = None
    outcome_judge_model_profile: ModelProfile | None = None
    execution_semantics: Literal[
        "full_trace_counterfactual_with_terminal_projection",
        "enacted_live_mediation",
        "enacted_closed_loop_recovery",
        "imported_observer_result",
    ] = "full_trace_counterfactual_with_terminal_projection"
    evaluation_contract_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    comparison_contract_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    closed_loop_condition: ClosedLoopCondition | None = None
    treatment: dict[str, Any] = Field(default_factory=dict)
    environment: dict[str, str] = Field(default_factory=dict)
    started_at: datetime
    completed_at: datetime | None = None


class ScenarioResult(FrozenModel):
    scenario_id: str
    status: RunStatus
    failure_type: FailureType | None = None
    audits: tuple[AuditRecord, ...] = ()
    audit_event_ids: tuple[str, ...] = ()
    audit_opportunities: int = Field(default=0, ge=0)
    decisions: tuple[BrokerDecision, ...] = ()
    utility_score: float | None = None
    judge_covered: bool = False
    harm_occurred: bool = False
    first_non_allow_event_id: str | None = None
    fixed_trace_harm_transition_allowed: bool | None = None
    terminal_projection_harm_occurred: bool | None = None
    closed_loop_condition: ClosedLoopCondition | None = None
    recovery_attempted: bool = False
    replan_attempts: int = Field(default=0, ge=0)
    recovery_steps: int = Field(default=0, ge=0)
    recovered: bool | None = None
    closed_loop_terminal_reason: ClosedLoopTerminalReason | None = None
    executed_action_count: int = Field(default=0, ge=0)
    denied_action_count: int = Field(default=0, ge=0)
    post_intervention_violation_count: int = Field(default=0, ge=0)
    repeated_denied_action_count: int = Field(default=0, ge=0)
    task_success: bool | None = None
    safety_satisfied: bool | None = None
    safe_task_success: bool | None = None
    outcome_judge_covered: bool = False
    error_message: str | None = None
