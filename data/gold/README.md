# SelfAuditBench Gold Data

This directory contains the adjudicated 96-trajectory SelfAuditBench gold study: 48 ASB trajectories and 48 ConVerse trajectories organized as 48 matched pairs.

## Released files

- `candidates.yaml`: deterministic paired-source manifest.
- `selfauditbench-gold.jsonl`: full adjudicated trajectories and labels.
- `selfauditbench-gold-compact.jsonl`: compact combined benchmark input.
- `selfauditbench-gold-asb.jsonl` and `selfauditbench-gold-converse.jsonl`: surface-specific compact inputs used by the replay and closed-loop configurations.
- `*.integrity.json`: hashes, counts, scope, label-evidence linkage, and subset status for each compact export.
- `selfauditbench-gold.annotation_evidence.json`: annotation provenance, agreement statistics, adjudication metadata, and file hashes.
- `annotations/`: completed independent annotation files.

Two annotators independently labeled risk status, the first risk-sufficient event, the materialized-harm boundary, accepted interventions, the minimal permission delta, and expected utility. Human adjudication resolved every disagreement. Risk-label agreement was 77.08% (Cohen's \(\kappa=0.562\)); agreement on the first risk-sufficient event, harm boundary, and minimal permission delta was 87.88%, 93.94%, and 87.88%, respectively. Accepted-intervention Jaccard similarity was 0.910.

Verify compact inputs before model execution:

```bash
selfauditbench annotate verify-compact data/gold/selfauditbench-gold-asb.integrity.json
selfauditbench annotate verify-compact data/gold/selfauditbench-gold-converse.integrity.json
```

See [`../../Runbooks/annotation_guide.md`](../../Runbooks/annotation_guide.md) for label semantics and study procedure. Complete construction, validation, replay, and closed-loop commands are in [`../../Runbooks`](../../Runbooks).
