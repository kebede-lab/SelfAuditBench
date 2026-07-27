# Supplementary Runtime And Reliability Data

- Run: `agentforesight-paper-split-official-deepseek-sidecar`
- Provider/model: `deepseek-openai-compatible` / `deepseek-v4-flash`
- Wall time: 6984.14 seconds
- API attempts: 3821
- API time: 6941.25 seconds
- Provider-reported total tokens: 18323132
- Local estimated total tokens: 14633659
- Token-cost proxy units: 18323132
- Token-cost proxy basis: `provider_usage`
- Token-cost proxy units per scenario: 55190.16
- API seconds per scenario: 20.91
- Estimated monetary API cost: N/A
- Provider token usage coverage: 100.00%
- Token accounting counts: `{"provider_usage": 3821}`
- Headline eligibility: `prefix_reliability_only`
- False-alarm denominator valid for headline use: `False`
- False-alarm claim use: `diagnostic_only`
- Aggregate headline allowed: `False`
- Full-run gate decision: `promote_to_full_run`
- Backend ready for full run: `True`
- Dataset claim status: `prefix_reliability_only`
- Analysis role: `prefix_reliability_comparison_candidate`
- Headline semantic candidate: `False`
- Include in supplementary reliability tables: `True`

## Model Audit Vs Guard Enforcement

| Metric | Evidence class | Claim use | Value | 95% CI | Numerator | Denominator |
| --- | --- | --- | ---: | --- | ---: | ---: |
| `task_completion` | `schema_reliability` | `supplementary_reliability` | 1.0000 | [0.9886, 1.0000] | 332 | 332 |
| `schema_compliance` | `schema_reliability` | `supplementary_reliability` | 1.0000 | [0.9886, 1.0000] | 332 | 332 |
| `valid_audit_coverage` | `model_audit_quality` | `prefix_reliability_only` | 1.0000 | [0.9990, 1.0000] | 3821 | 3821 |
| `model_generated_early_detection_rate` | `model_audit_quality` | `prefix_reliability_only` | N/A | N/A | 0 | 0 |
| `guard_triggered_pause_rate` | `broker_guard_behavior` | `prefix_reliability_only` | 0.0000 | [0.0000, 0.0010] | 0 | 3821 |
| `fail_closed_intervention_rate` | `broker_guard_behavior` | `prefix_reliability_only` | N/A | N/A | 0 | 0 |
| `model_false_alarm_rate` | `model_audit_quality` | `diagnostic_only` | 0.0000 | [0.0000, 0.0222] | 0 | 169 |
| `guard_false_alarm_rate` | `broker_guard_behavior` | `diagnostic_only` | 0.0000 | [0.0000, 0.0222] | 0 | 169 |

## Failure Distribution

Evidence classes: `provider_api_stress`, `schema_reliability`.

```json
{
  "audit_attempt_failure_types": {},
  "closed_loop_attempt_failure_types": {},
  "scenario_failure_types": {},
  "scenario_statuses": {
    "complete": 332
  }
}
```

## Agent-Testing-Agent-Safety Log

Evidence class: `agent_testing_agent_safety`.

- Logged events: 0
- Event file: `agent_safety_events.jsonl`

| Evidence class | Provider | Model | Behavior | Severity | Target | Count |
| --- | --- | --- | --- | --- | --- | ---: |

```json
{}
```
