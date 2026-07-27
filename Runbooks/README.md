# SelfAuditBench runbooks

The runbooks define the complete artifact workflow:

1. [`ASB.md`](ASB.md): ASB ingestion, shared 96-item annotation study, compact gold data, recorded replay, enacted recovery, conformance, comparisons, and paper export.
2. [`ConVerse.md`](ConVerse.md): ConVerse control materialization, ingestion, recorded replay, and enacted recovery.
3. [`AgentForesight.md`](AgentForesight.md): AFTraj normalization, native-baseline import, no-audit processing, sidecar prefix diagnostic, and verification.

The [`annotation guide`](annotation_guide.md) defines the human-study roles, evidence boundary, labels, independence protocol, and adjudication procedure.

Replace `/path/to/SelfAuditBench` with the absolute repository path. Run tracked configurations without editing them during an experiment.
