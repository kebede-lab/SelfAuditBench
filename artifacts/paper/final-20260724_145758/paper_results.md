# SelfAuditBench Paper Results Export

## Recommended Manuscript Assets

- Table: `tables/dataset_inventory.*` for benchmark surface counts and label coverage.
- Table: `tables/run_metrics_summary.*` for evidence-classified run index metrics. Use the separated result tables below for manuscript claims.
- Table: `tables/model_audit_results.*` for model early detection and false alarms.
- Table: `tables/audit_schema_results.*` for valid-audit coverage and schema compliance.
- Table: `tables/broker_guard_results.*` for fail-closed interventions and guard false alarms.
- Table: `tables/execution_reliability_results.*` for audit-pipeline completion, provider errors, timeouts, and repairs.
- Table: `tables/api_efficiency_results.*` for latency, tokens, cost proxy, and optional monetary cost.
- Table: `tables/agent_safety_event_results.*` for agent-testing-agent-safety diagnostics.
- Table: `tables/label_semantics_claim_eligibility.*` for per-surface label and claim boundaries.
- Table: `tables/annotation_study_evidence.*` for independent-annotation agreement, adjudication completeness, and frozen artifact hashes.
- Table: `tables/closed_loop_recovery_results.*` for enacted safety, task success, recovery, noninterference, permission compliance, and burden.
- Table: `tables/closed_loop_metric_records.*` for plot-ready closed-loop ratios, explicit denominators, and Wilson intervals.
- Table: `tables/agentforesight_prefix_by_domain.*` for reproduced AFTraj held-out prefix-localization results when available.
- Table: `tables/api_reliability_supplement.*` for per-run API time, provider-token, local token-cost proxy, optional monetary cost, failure-distribution, full-run gate decisions, analysis roles, and meta-safety data.
- Figure PDFs: `figures/fig_framework_pipeline.pdf`, `figures/fig_dataset_inventory.pdf`, `figures/fig_dataset_label_composition.pdf`, `figures/fig_run_reliability.pdf`, `figures/fig_run_metric_matrix.pdf`, and `figures/fig_agentforesight_prefix_metrics.pdf` when AgentForesight by-domain results are available.
- Closed-loop figure PDFs: `figures/fig_closed_loop_safety_task.pdf` and `figures/fig_closed_loop_replan_burden.pdf`.

## Export Summary

- Dataset rows: 8
- Run rows: 11
- Supplementary runtime rows: 15
- AgentForesight domain rows: 4
- Annotation evidence status: `available_complete`
- Enacted closed-loop run rows: 4

## Notes For Results Section

Report ASB, ConVerse, and AFTraj results separately when their labels differ. Use AFTraj native prefix-localization metrics as an observer baseline, and reserve recorded-action harm-boundary or least-restriction metrics for cases with explicit SelfAuditBench annotations.
For replay runs, report full-trace model audits and absorbing terminal broker projection separately. For closed-loop runs, report sink-gated safety/task outcomes and recovery burden from the enacted artifacts.
Use dataset headline-status flags to select adjudicated rows for headline false-alarm, least-restriction, and enacted-recovery claims.
Use annotation-study agreement when its evidence status is complete, all items were independently completed, and unresolved adjudications are zero.
Report enacted ASB/ConVerse recovery, deterministic sink conformance, and AFTraj prefix evidence under their named execution contracts.
Local open-source backends retain their gate-defined supplementary or headline analysis role in reliability tables.
