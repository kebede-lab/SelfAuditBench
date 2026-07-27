# SelfAuditBench Paired Run Comparison

- Run A: `asb-full-gold-deepseek-closed-loop-sidecar`
- Run B: `asb-full-gold-deepseek-closed-loop-inline`
- Shared scenarios: 48
- Dataset hash: `fdfb7b6c44334fafcc1e0df628dd73711a5ef8fe0fa5d49df61d87d5e6ebedfe`
- Evaluation-contract hashes: A=`21e5cf4b3239776cf3c305a6a9bcfdd2f1772d31964a0718dd82521697ab2593`, B=`a92184fa3a14ecf2b769ae7830943af78662090e51eaa61f698cb1ba9a845f82`
- Comparison mode: `paired_treatment_ablation`
- Comparison-contract hash: `e8f643e290c7006c3cc89ff60419e1f0d95ed6a881c1733bfe65d9261253ea57`
- Run integrity: A=`verified`, B=`verified`
- Bootstrap samples: 2000
- Difference direction: `run_a_minus_run_b`

| Metric | Evidence class | n | Clusters | Run A | Run B | Difference | 95% CI | McNemar p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| `benign_noninterference_rate` | `enacted_closed_loop_recovery` | 34 | 24 | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] | N/A |
| `broker_policy_false_alarm_rate` | `broker_guard_behavior` | 34 | 24 | 0.0000 | 0.0000 | 0.0000 | [0.0000, 0.0000] | N/A |
| `closed_loop_actor_stalled` | `enacted_closed_loop_recovery` | 48 | 24 | 0.0625 | 0.1667 | -0.1042 | [-0.1875, -0.0208] | 0.0625 |
| `closed_loop_benign_noninterference` | `enacted_closed_loop_recovery` | 34 | 24 | 0.9412 | 1.0000 | -0.0588 | [-0.1389, 0.0000] | 0.5 |
| `closed_loop_harm_avoidance` | `enacted_closed_loop_recovery` | 14 | 14 | 0.5000 | 0.6429 | -0.1429 | [-0.3571, 0.0000] | 0.5 |
| `closed_loop_no_repeated_denied_action` | `enacted_closed_loop_recovery` | 48 | 24 | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] | N/A |
| `closed_loop_permission_compliance` | `enacted_closed_loop_recovery` | 48 | 24 | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] | N/A |
| `closed_loop_recovery_success` | `enacted_closed_loop_recovery` | 48 | 24 | 0.6667 | 0.7500 | -0.0833 | [-0.1875, 0.0000] | 0.2188 |
| `closed_loop_safe_task_success` | `enacted_closed_loop_recovery` | 48 | 24 | 0.6667 | 0.7500 | -0.0833 | [-0.1875, 0.0000] | 0.2188 |
| `closed_loop_safety` | `enacted_closed_loop_recovery` | 48 | 24 | 0.8125 | 0.8333 | -0.0208 | [-0.0833, 0.0417] | 1 |
| `closed_loop_task_success` | `enacted_closed_loop_recovery` | 48 | 24 | 0.7083 | 0.8333 | -0.1250 | [-0.2292, -0.0208] | 0.07031 |
| `early_risk_detection_rate` | `broker_guard_behavior` | 14 | 14 | 0.0000 | 0.0000 | 0.0000 | [0.0000, 0.0000] | N/A |
| `false_alarm_rate` | `broker_guard_behavior` | 34 | 24 | 0.0000 | 0.0000 | 0.0000 | [0.0000, 0.0000] | N/A |
| `guard_false_alarm_rate` | `broker_guard_behavior` | 34 | 24 | 0.0000 | 0.0000 | 0.0000 | [0.0000, 0.0000] | N/A |
| `guard_triggered_pause_scenario_rate` | `broker_guard_behavior` | 48 | 24 | 0.0000 | 0.0000 | 0.0000 | [0.0000, 0.0000] | N/A |
| `least_restriction_accuracy` | `broker_guard_behavior` | 14 | 14 | 0.0000 | 0.0000 | 0.0000 | [0.0000, 0.0000] | N/A |
| `model_false_alarm_rate` | `model_audit_quality` | 34 | 24 | 0.0000 | 0.0000 | 0.0000 | [0.0000, 0.0000] | N/A |
| `model_generated_early_detection_rate` | `model_audit_quality` | 14 | 14 | 0.0000 | 0.0000 | 0.0000 | [0.0000, 0.0000] | N/A |
| `pre_harm_intervention_rate` | `broker_guard_behavior` | 14 | 14 | 0.0000 | 0.0000 | 0.0000 | [0.0000, 0.0000] | N/A |
| `replay_processing_completion` | `schema_reliability` | 48 | 24 | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] | N/A |
| `schema_compliance` | `schema_reliability` | 48 | 24 | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] | N/A |
| `task_completion` | `schema_reliability` | 48 | 24 | 1.0000 | 1.0000 | 0.0000 | [0.0000, 0.0000] | N/A |

Bootstrap intervals resample restored attack-control pair clusters and are deterministic under the recorded seed. McNemar's exact test uses only discordant scenario outcomes and does not replace effect-size reporting.
