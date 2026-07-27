# SelfAuditBench

This repository accompanies our paper **“SelfAuditBench: A Benchmark for Auditable Self-Restriction in Tool-Using LLM Agents,”** submitted to the SIGKDD Datasets and Benchmarks Track. SelfAuditBench evaluates whether an agent can identify risk at an observable trajectory boundary, request a minimal reduction in its own authority, obey deterministic broker enforcement, and continue safely and usefully after restriction.

SelfAuditBench combines:

- recorded-action replay for audit semantics, timing, intervention quality, and structural reliability;
- a monotonic permission broker and deterministic action gate;
- paired enacted sidecar and inline closed-loop conditions under a shared actor and execution contract;
- human-adjudicated risk boundaries, harm boundaries, accepted interventions, permission deltas, and utility expectations;
- integrity manifests, paired comparisons, conformance checks, and paper-ready exports.

## Architecture

[View the SelfAuditBench architecture figure](Figures/SAB_architecture.pdf).

The workflow begins with local reproductions of Agent Security Bench (ASB), ConVerse, and AgentForesight AFTraj. Their trajectories are normalized into a shared schema, annotated independently by two researchers, adjudicated by a third researcher, and evaluated through either recorded replay or enacted recovery. The broker accepts only monotonic authority reductions, gates fresh proposals, and returns authoritative decisions and receipts to the actor.

## Repository map

| Path | Contents |
|---|---|
| [`src/selfauditbench`](src/selfauditbench) | Framework, schemas, adapters, broker, runners, scoring, comparison, and export code |
| [`configs`](configs) | Tracked smoke, full replay, and closed-loop experiment configurations |
| [`data/gold`](data/gold) | Final compact ASB/ConVerse gold datasets and annotation evidence |
| [`artifacts`](artifacts) | Paper-facing runs, comparisons, conformance results, annotation packet, schemas, and final export |
| [`Reproductions`](Reproductions) | Local ASB, ConVerse, and AgentForesight reproduction snapshots |
| [`Runbooks`](Runbooks) | Complete reproducibility commands and admission checks |
| [`Figures`](Figures) | Architecture and result figures |
| [`annotation_guide.md`](annotation_guide.md) | Annotation and adjudication protocol |

## Reproduction workflow

1. Reproduce the three source benchmarks using the instructions in [`Reproductions/ASB`](Reproductions/ASB), [`Reproductions/ConVerse`](Reproductions/ConVerse), and [`Reproductions/AgentForesight`](Reproductions/AgentForesight).
2. Follow [`Runbooks/ASB.md`](Runbooks/ASB.md) and [`Runbooks/ConVerse.md`](Runbooks/ConVerse.md) to normalize trajectories, construct the paired study, validate the annotation packet, build compact gold data, and run recorded and enacted evaluations.
3. Follow [`Runbooks/AgentForesight.md`](Runbooks/AgentForesight.md) for the separate AFTraj prefix-localization diagnostic.
4. Verify every admitted run, produce paired backend and treatment comparisons, run sink conformance, and export the paper bundle as specified in the runbooks.

The runbooks contain the full command sequence. This README intentionally keeps only the entry points.

## Installation

SelfAuditBench requires Python 3.11 or later.

```bash
git clone https://github.com/kebede-lab/SelfAuditBench.git
cd SelfAuditBench
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,agentforesight,figures]"
```

Run the deterministic test suite and local smoke configuration:

```bash
pytest -q
selfauditbench run replay --config configs/smoke.yaml
```

API-backed configurations read credentials from environment variables; no credentials are stored in this repository. The runbooks identify the required variables and provider endpoints.

## Human-annotated data

The ASB and ConVerse study contains 48 matched attack-control pairs: 24 pairs per surface and 96 source- and content-unique trajectories. Two annotators independently labeled every trajectory before comparison, and a third researcher adjudicated all disagreements.

| Gold statistic | Value |
|---|---:|
| Risky / benign trajectories | 55 / 41 |
| Risk-label agreement | 77.08% |
| Cohen’s κ | 0.5616 |
| First-risk boundary agreement | 87.88% |
| Harm-boundary agreement | 93.94% |
| Minimal-delta agreement | 87.88% |
| Accepted-intervention Jaccard | 0.9100 |
| Unresolved items | 0 |

See [`annotation_guide.md`](annotation_guide.md) for label semantics, chronology rules, file distribution, independent annotation, freezing, and adjudication.

## Core results

### Recorded audit performance

DeepSeek V4 Flash uses the official DeepSeek API. Qwen3.5 and MiniMax M2.7 use CST Cloud OpenAI-compatible endpoints. Gemma4 12B is the local Ollama reliability and stress-test backend.

| Backend | ASB early / accepted | ConVerse early / accepted | ASB / ConVerse pipeline completion |
|---|---:|---:|---:|
| DeepSeek V4 Flash | 13/14 / 13/14 | 30/41 / 30/41 | 48/48 / 48/48 |
| Qwen3.5 | 13/14 / 13/14 | 16/41 / 16/41 | 48/48 / 48/48 |
| MiniMax M2.7 | 13/14 / 12/14 | 22/41 / 19/41 | 48/48 / 46/48 |
| Gemma4 12B | 8/14 / 8/14 | 20/41 / 20/41 | 41/48 / 18/48 |

DeepSeek and Qwen match on ASB, while DeepSeek detects 34.15 percentage points more risky ConVerse trajectories than Qwen in the paired comparison. MiniMax and Gemma expose additional provider/schema reliability variation.

[View four-backend audit performance](Figures/backend_audit_performance.pdf).

### Enacted closed-loop recovery

Both audit placements expose the shared actor in all 48 scenarios on each surface. Every condition achieves 100% permission compliance, 100% outcome-judge coverage, no repeated denied actions, and zero replan- or recovery-step-budget exhaustion.

| Surface | Condition | Safety | Task success | Joint safe-task | Risky harm avoidance |
|---|---|---:|---:|---:|---:|
| ASB | Sidecar | 81.25% | 70.83% | 66.67% | 50.00% |
| ASB | Inline | 83.33% | 83.33% | 75.00% | 64.29% |
| ConVerse | Sidecar | 60.42% | 41.67% | 27.08% | 53.66% |
| ConVerse | Inline | 31.25% | 41.67% | 25.00% | 19.51% |

Inline improves ASB task success while maintaining similar safety. On ConVerse, the sidecar improves safety by 29.17 points and risky harm avoidance by 34.15 points at equal task success, showing that audit placement interacts with surface semantics.

[View enforcement and action-gate outcomes](Figures/enforcement_assurance.pdf).

### AFTraj prefix localization

AFTraj remains a separate decisive-error localization and reliability diagnostic. The native DeepSeek reproduction processes 326/332 trajectories with 30.94% Exact-F1, 2.77 absolute step shift, 31.36% false alarms, and 34.36% step accuracy. The SelfAuditBench sidecar processes all 332 trajectories and 3,821 prefixes but reaches 3.41% Exact-F1, 0% false alarms, and 1.84% step accuracy. This separation demonstrates that reliable contract execution does not by itself establish valid prefix localization.

[View AFTraj prefix diagnostics](Figures/afttraj_prefix_diagnostics.pdf).

## Released artifacts

The public artifact set retains:

- the final 96-item annotation packet and compact adjudicated datasets;
- 15 paper-facing full runs;
- 12 backend comparisons and two sidecar-versus-inline treatment comparisons;
- deterministic six-case sink conformance;
- final JSON schemas and verification records;
- the manifest-hashed paper export under [`artifacts/paper`](artifacts/paper).

Each run writes `integrity.json`, which binds emitted files by SHA-256 digest, byte size, and JSONL record count. Verify a run without making model calls:

```bash
selfauditbench verify --run artifacts/runs/asb-full-gold-deepseek-sidecar
```

Generate the result figures from released artifacts:

```bash
python -m pip install -e ".[figures]"
python scripts/generate_result_figures.py --repo . --output Figures
```

## License and attribution

SelfAuditBench is released under the [Apache License 2.0](LICENSE). Reproduction snapshots retain their original project attribution and citations in their respective READMEs.
