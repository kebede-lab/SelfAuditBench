# ASB and Shared Gold-Data Runbook

This is the reproducibility runbook for ASB ingestion, the shared ASB/ConVerse annotation study, ASB replay, conformance, and final paper staging. Run commands from a Bash shell in the experiment environment unless a section says otherwise.

The workflow supports two manuscript evidence tracks: **recorded-action replay with broker-mediated absorbing terminal projection** and **enacted closed-loop recovery under self-requested monotonic restriction**. The closed-loop conditions return broker feedback and reduced permission state to an acting model, mediate fresh proposals, gate the action sink, and score the enacted outcome with a role-separated judge. Deterministic live conformance supplies a focused sink-enforcement result. Keep ASB and ConVerse as separate headline rows; the combined 96-item file supplies shared annotation provenance and descriptive summaries.

Never regenerate or rewrite files under `configs/` during a final run. They are tracked experiment inputs.

**EXECUTION ORDER — Run ASB Sections 0–1, then go to `ConVerse.md` and complete Sections 0–2. Return here for ASB Sections 2–4, which perform the one shared full annotation and adjudication. After Section 4 succeeds, continue with ASB Sections 5–9 and/or return to ConVerse Section 3. Stop whenever a bold instruction sends you to a file or directory.**

## 0. Environment and preflight

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab

python -m pip install -r requirements.txt
python -m pip install -e .
mkdir -p artifacts/{exploratory,annotations,runs,conformance,paper,comparisons} data/gold
pytest -q
```

Create the API environment once if it does not already exist. The tracked YAML files contain the endpoint and model identifiers; this file contains tokens only.

```bash
install -m 700 -d "$HOME/.config/api-env"
if [ ! -f "$HOME/.config/api-env/selfauditbench-apis.env" ]; then
  read -rsp 'Official DeepSeek API token: ' DEEPSEEK_TOKEN; echo
  read -rsp 'Qwen token: ' QWEN_TOKEN; echo
  read -rsp 'MiniMax token: ' MINIMAX_TOKEN; echo
  umask 077
  {
    printf 'export DEEPSEEK_API_KEY=%q\n' "$DEEPSEEK_TOKEN"
    printf 'export QWEN_API_KEY=%q\n' "$QWEN_TOKEN"
    printf 'export MINIMAX_API_KEY=%q\n' "$MINIMAX_TOKEN"
  } > "$HOME/.config/api-env/selfauditbench-apis.env"
  chmod 600 "$HOME/.config/api-env/selfauditbench-apis.env"
  unset DEEPSEEK_TOKEN QWEN_TOKEN MINIMAX_TOKEN
fi
. "$HOME/.config/api-env/selfauditbench-apis.env"
```

Prepare the local open-source reference backend only when that row will be run:

```bash
mkdir -p "$HOME/.cache"
pgrep -f 'ollama serve' >/dev/null || nohup ollama serve > "$HOME/.cache/ollama-serve.log" 2>&1 &
ollama pull gemma4:12b
```

## 1. Reingest ASB

Copy the complete ASB logs to `Reproductions/ASB/logs`, then ingest them with the tracked adapter. The adapter separates each source action from its co-located observation so every `pre_tool` checkpoint contains only pre-execution content and the result appears in a later `post_observation` event.

```bash
cd /path/to/SelfAuditBench
selfauditbench ingest asb Reproductions/ASB/logs artifacts/exploratory/asb.jsonl
selfauditbench dataset summary artifacts/exploratory/asb.jsonl \
  --output artifacts/exploratory/asb.summary.json

python - <<'PY'
from selfauditbench.adapters.io import read_scenarios

scenarios = read_scenarios("artifacts/exploratory/asb.jsonl")
proposals = [
    event
    for scenario in scenarios
    for event in scenario.events
    if event.proposed_action is not None
]
assert proposals, "ASB ingestion produced no proposals"
assert all(
    "[observation]:" not in str(event.visible_payload.get("content", "")).casefold()
    for event in proposals
), "a pre-execution proposal still contains a recorded observation"
print(f"pre-execution ASB proposals verified: {len(proposals)}")
PY
```

Model calls begin only after the shared gold dataset has been fully annotated, adjudicated, compacted, and verified.

**STOP — Do not continue to ASB Section 2 until ConVerse Section 2 passes `--final-ready`. Now go to `ConVerse.md` and complete Sections 0–2. When its final validation succeeds, return to ASB Section 2 below.**

## 2. Final candidate selection and blinded 96-item packet

Candidate selection reads and normalizes the original log roots, reserves each selected trajectory-content fingerprint across both surfaces, and skips different source rows or files that contain the same observable trajectory. Packet materialization joins those selections to the normalized datasets and independently rechecks all 96 source and content identities.

**RETURN POINT — Continue here only after `ConVerse.md` Section 2 reports that `selfauditbench annotate validate data/gold/candidates.yaml --final-ready` succeeded. If it has not succeeded, go back to ConVerse Section 1 or 2 and resolve the failed control or validation first.**

```bash
cd /path/to/SelfAuditBench
selfauditbench ingest converse Reproductions/ConVerse/logs artifacts/exploratory/converse.jsonl
selfauditbench dataset summary artifacts/exploratory/converse.jsonl \
  --output artifacts/exploratory/converse.summary.json

selfauditbench annotate select \
  --asb-root Reproductions/ASB/logs \
  --converse-root Reproductions/ConVerse/logs \
  --output data/gold/candidates.yaml
selfauditbench annotate validate data/gold/candidates.yaml --final-ready
```

**The complete blinded 96-item annotation packet, the two blank annotator files, and the coordinator-only private mapping are created by the following command. Run it only after `--final-ready` succeeds.**

```bash
if [ -e artifacts/annotations/final-96 ]; then
  echo 'Archive the existing final-96 packet before creating a new frozen study.' >&2
else
  selfauditbench annotate packet \
    data/gold/candidates.yaml \
    artifacts/exploratory/asb.jsonl \
    artifacts/exploratory/converse.jsonl \
    artifacts/annotations/final-96 \
    --seed 7
fi
```

If this command fails, it intentionally leaves `packet_summary.json` and the partial packet files for diagnosis. **Do not reuse a failed partial packet. After reading its summary and correcting selection, remove only that unannotated partial directory before rerunning the packet command:**

```bash
rm -rf -- /path/to/SelfAuditBench/artifacts/annotations/final-96
```

**STOP AND READ — Do not pass `--allow-missing`. Open `artifacts/annotations/final-96/packet_summary.json` and confirm that it contains all of the following values. Do not distribute annotation files if any value differs.**

```text
final_ready: true
materialized_items: 96
unique_source_count: 96
unique_content_count: 96
complete_pairs: 48
```

Keep `private_mapping.jsonl` coordinator-only. Give annotators only the complete blinded scenarios, their own blank full template, and the finalized `ANNOTATION_PROTOCOL.md`. Never prefill an annotation template from a sample or source label.

**STOP — Now go to `artifacts/annotations/final-96/`. Keep `private_mapping.jsonl` private. Give `scenarios.jsonl`, `ANNOTATION_PROTOCOL.md`, and `annotator_a.jsonl` to annotator A; give the same scenarios and protocol with `annotator_b.jsonl` to annotator B. Each annotator must independently annotate all 96 items. Do not execute Section 3 until both completed files have been returned.**

## 3. Independent annotation, freeze, adjudication, and apply for all 96

Both annotators independently complete their own full template. They must not compare answers or see the private mapping. Validate and freeze **before** computing agreement or generating the adjudication queue.

**STOP — Run the next validation commands only after both annotators have completed all 96 rows with distinct, non-placeholder `annotator_id` values. If either validation fails, return that file to its annotator and do not freeze anything.**

```bash
selfauditbench annotate validate \
  artifacts/annotations/final-96/annotator_a.jsonl \
  --scenarios artifacts/annotations/final-96/scenarios.jsonl \
  --require-complete
selfauditbench annotate validate \
  artifacts/annotations/final-96/annotator_b.jsonl \
  --scenarios artifacts/annotations/final-96/scenarios.jsonl \
  --require-complete
```

**The following command freezes both independent annotation files before any agreement comparison. After it succeeds, do not edit either annotator file.**

```bash
selfauditbench annotate freeze artifacts/annotations/final-96
```

**The following command creates `artifacts/annotations/final-96/adjudication.jsonl`, its summary, and the human disagreement queue. It identifies disagreements but does not resolve them.**

```bash
selfauditbench annotate adjudicate \
  artifacts/annotations/final-96/annotator_a.jsonl \
  artifacts/annotations/final-96/annotator_b.jsonl \
  --scenarios artifacts/annotations/final-96/scenarios.jsonl \
  --freeze-manifest artifacts/annotations/final-96/independent_annotations.freeze.json \
  --output artifacts/annotations/final-96/adjudication.jsonl
```

**STOP — Now go to `artifacts/annotations/final-96/adjudication.jsonl` and its adjudication summary. Following `ANNOTATION_PROTOCOL.md`, a human adjudicator must resolve every disagreement and identify themselves. Do not run `annotate apply` while any adjudication entry is unresolved.**

**The following command creates the final shared gold dataset and annotation-evidence manifest. Run it only after human adjudication is complete.**

```bash
selfauditbench annotate apply \
  artifacts/annotations/final-96/scenarios.jsonl \
  artifacts/annotations/final-96/adjudication.jsonl \
  artifacts/annotations/final-96/private_mapping.jsonl \
  data/gold/selfauditbench-gold.jsonl \
  --freeze-manifest artifacts/annotations/final-96/independent_annotations.freeze.json
```

This also writes `data/gold/selfauditbench-gold.annotation_evidence.json`, which binds the packet, mapping, two frozen annotation files, adjudication queue, final dataset, agreement summary, and adjudication changes by hash.

**Now continue directly to ASB Section 4. Do not start any smoke or full model run until every compact and integrity assertion in Section 4 succeeds.**

## 4. Freeze combined, surface, and smoke compacts

The surface compacts are the actual inputs of the tracked headline configs. The combined compact is provenance/descriptive only. The smoke compacts are deterministic, pair-complete 10-item subsets exported from the fully adjudicated gold set. They test runtime readiness and are not separate annotation datasets or manuscript result rows.

**The following commands create the combined 96-item compact, the full 48-item ASB and ConVerse compacts, and the two 10-item smoke subsets from the applied human-adjudicated gold dataset.**

```bash
selfauditbench annotate compact \
  data/gold/selfauditbench-gold.jsonl \
  data/gold/selfauditbench-gold-compact.jsonl
selfauditbench annotate compact \
  data/gold/selfauditbench-gold.jsonl \
  data/gold/selfauditbench-gold-asb.jsonl \
  --surface asb
selfauditbench annotate compact \
  data/gold/selfauditbench-gold.jsonl \
  data/gold/selfauditbench-gold-converse.jsonl \
  --surface converse
selfauditbench annotate compact \
  data/gold/selfauditbench-gold.jsonl \
  data/gold/selfauditbench-gold-readiness-asb.jsonl \
  --surface asb --limit 10 --allow-subset
selfauditbench annotate compact \
  data/gold/selfauditbench-gold.jsonl \
  data/gold/selfauditbench-gold-readiness-converse.jsonl \
  --surface converse --limit 10 --allow-subset
```

**Every compact command creates a sibling `.integrity.json`. Run the authoritative verifier and shape assertions below for all five outputs. Do not declare the annotation complete or make a model call if any command or assertion fails.**

```bash
for manifest in \
  data/gold/selfauditbench-gold-compact.integrity.json \
  data/gold/selfauditbench-gold-asb.integrity.json \
  data/gold/selfauditbench-gold-converse.integrity.json \
  data/gold/selfauditbench-gold-readiness-asb.integrity.json \
  data/gold/selfauditbench-gold-readiness-converse.integrity.json
do
  selfauditbench annotate verify-compact "$manifest"
done

python - <<'PY'
import json
from pathlib import Path

root = Path("data/gold")
expected = {
    "selfauditbench-gold-compact.integrity.json": ("combined", 96, 48, False),
    "selfauditbench-gold-asb.integrity.json": ("asb", 48, 24, False),
    "selfauditbench-gold-converse.integrity.json": ("converse", 48, 24, False),
    "selfauditbench-gold-readiness-asb.integrity.json": ("asb", 10, 5, True),
    "selfauditbench-gold-readiness-converse.integrity.json": ("converse", 10, 5, True),
}

for name, (scope, count, pairs, subset) in expected.items():
    manifest_path = root / name
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["surface_scope"] == scope, manifest_path
    assert manifest["scenario_count"] == count, manifest_path
    assert manifest["pair_count"] == pairs, manifest_path
    assert manifest["subset_export"] is subset, manifest_path
    assert manifest["headline_shape_complete"] is (not subset), manifest_path
    assert manifest["source_annotation_evidence_file"] == \
        "selfauditbench-gold.annotation_evidence.json", manifest_path
print("compact gold integrity and study shapes: verified")
PY
```

Archive the annotation evidence, freeze manifests, compact integrity manifests, final protocol, and adjudication summary with the paper artifacts. They are part of the benchmark release provenance.

**ANNOTATION COMPLETE — Continue to ASB Section 5 for ASB smoke/full execution. To run ConVerse, go back to `ConVerse.md` and resume at Section 3. The annotation and adjudication must not be repeated in the ConVerse runbook.**

## 5. Reusable backend and smoke checks

Every new terminal has its own shell state. The runnable terminal blocks below repeat this setup so each block can be pasted into a fresh terminal as written. The helper selects only the token; the tracked config is authoritative for all experiment settings.

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
type sab_run sab_closed_loop sab_check_run sab_check_smoke sab_check_closed_loop
```

The tracked DeepSeek configs use `https://api.deepseek.com` with thinking disabled. `DEEPSEEK_API_KEY` must therefore contain the official DeepSeek API token, not a CSTCloud token. Qwen and MiniMax use their tracked CSTCloud routes. Qwen3.5 thinking is disabled with its OpenAI-compatible `enable_thinking` control, and the Ollama Gemma configs disable thinking through the OpenAI-compatible reasoning control.

`selfauditbench verify` must report a verified run. Never use a `legacy_unverified` or `corrupt` run in a paper table.

## 6. ASB gold smoke and full replay

After the full annotation, adjudication, compact export, and integrity verification succeed, open four terminals. Run the Section 5 terminal setup in every terminal, then launch one smoke command in each terminal. These runs are safe to execute concurrently because the tracked configs have distinct run IDs and output directories.

**SMOKE STAGE ONLY — Start all desired smoke terminals in parallel, wait for every smoke and its check to finish, and do not start any full command yet.**

Terminal 1 — DeepSeek:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/asb-some-gold-deepseek-sidecar.yaml deepseek && \
  sab_check_smoke artifacts/runs/asb-some-gold-deepseek-sidecar
```

Terminal 2 — Qwen3.5:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/asb-some-gold-qwen35-sidecar.yaml qwen35 && \
  sab_check_smoke artifacts/runs/asb-some-gold-qwen35-sidecar
```

Terminal 3 — MiniMax M2.7:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/asb-some-gold-minimax-m27-sidecar.yaml minimax-m27 && \
  sab_check_smoke artifacts/runs/asb-some-gold-minimax-m27-sidecar
```

Terminal 4 — local Gemma 4 supplementary reference:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/asb-some-gold-ollama-gemma4-sidecar.yaml ollama-gemma4 && \
  sab_check_run artifacts/runs/asb-some-gold-ollama-gemma4-sidecar
```

Promote only hosted backends whose smoke command passes all reliability checks. A failing hosted backend is a stress/reliability result, not a headline semantic row. Gemma 4 is the prespecified local open-source reliability baseline and may be reported as supplementary even if it does not pass the hosted-backend smoke gate.

**FULL-RUN GATE — Continue only after all smoke terminals have ended and each hosted backend you intend to promote printed a passing smoke gate. Do not launch a hosted full run whose smoke failed.**

Reuse the four terminals, or open new terminals and repeat the Section 5 setup. Launch one full command per promoted backend so the eligible full runs execute concurrently.

Terminal 1 — DeepSeek, only if promoted:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/asb-full-gold-deepseek-sidecar.yaml deepseek && \
  sab_check_run artifacts/runs/asb-full-gold-deepseek-sidecar
```

Terminal 2 — Qwen3.5, only if promoted:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/asb-full-gold-qwen35-sidecar.yaml qwen35 && \
  sab_check_run artifacts/runs/asb-full-gold-qwen35-sidecar
```

Terminal 3 — MiniMax M2.7, only if promoted:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/asb-full-gold-minimax-m27-sidecar.yaml minimax-m27 && \
  sab_check_run artifacts/runs/asb-full-gold-minimax-m27-sidecar
```

Terminal 4 — local Gemma 4 supplementary reference, if included:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/asb-full-gold-ollama-gemma4-sidecar.yaml ollama-gemma4 && \
  sab_check_run artifacts/runs/asb-full-gold-ollama-gemma4-sidecar
```

Generate the complete pairwise backend-comparison matrix only after all four intended ASB
full runs exist and verify under the identical gold dataset and evaluation contract. This
stage reads completed artifacts and makes no model/API calls. DeepSeek versus Qwen is the
primary hosted contrast; DeepSeek/Qwen/MiniMax contrasts provide hosted-backend robustness.
Every contrast containing Gemma is supplementary and must be interpreted together with its
schema, completion, and failure-reliability results rather than promoted to a headline
semantic result.

```bash
set -euo pipefail
mkdir -p artifacts/comparisons

backends=(deepseek qwen35 minimax-m27 ollama-gemma4)
for backend in "${backends[@]}"; do
  selfauditbench verify \
    --run "artifacts/runs/asb-full-gold-${backend}-sidecar"
done

pairs=(
  "deepseek qwen35"
  "deepseek minimax-m27"
  "deepseek ollama-gemma4"
  "qwen35 minimax-m27"
  "qwen35 ollama-gemma4"
  "minimax-m27 ollama-gemma4"
)

for pair in "${pairs[@]}"; do
  read -r backend_a backend_b <<< "$pair"
  selfauditbench compare \
    --run-a "artifacts/runs/asb-full-gold-${backend_a}-sidecar" \
    --run-b "artifacts/runs/asb-full-gold-${backend_b}-sidecar" \
    --output "artifacts/comparisons/asb-${backend_a}-vs-${backend_b}.json"
done
```

This produces six ASB JSON files and six matching Markdown summaries. Preserve all twelve;
the structured files support plotting and statistical analysis, while the Markdown files
provide directly inspectable result summaries.

Comparison files bind the source runs' integrity roots. If `score`, `report`, or any other operation changes a source run's integrity root after comparison, regenerate every affected comparison before release staging.

Do not pool ASB and ConVerse into one headline estimate; their source semantics and sampling frames differ.

## 7. Enacted closed-loop recovery and condition ablation

Run the two conditions first on the 10-item pair-complete smoke subset derived from the full gold set. Both conditions activate the same DeepSeek actor immediately before the first recorded proposal and give it the same pre-action context, utility target, outcome-free transition catalog, permissions, budgets, seed, normalized sink, and Qwen outcome judge. The sidecar condition externally audits each fresh actor proposal; the inline condition requires the actor to emit a controller-bound self-audit with the same proposal.

Use a clean output directory for the study execution and preserve each verified run as immutable evidence.

Open two terminals and run the Section 5 setup in each.

Terminal 1 — sidecar closed-loop smoke:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_closed_loop configs/asb-some-gold-deepseek-closed-loop-sidecar.yaml && \
  sab_check_closed_loop artifacts/runs/asb-some-gold-deepseek-closed-loop-sidecar
```

Terminal 2 — inline closed-loop smoke:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_closed_loop configs/asb-some-gold-deepseek-closed-loop-inline.yaml && \
  sab_check_closed_loop artifacts/runs/asb-some-gold-deepseek-closed-loop-inline
```

The two conditions have distinct run IDs and may run concurrently, subject to the shared DeepSeek and Qwen account rate limits. Never start two processes with the same config/run ID: an exclusive run-directory lease rejects the second process before it can reset or append artifacts.

`sab_check_closed_loop` is the same general readiness check for smoke and full runs. It requires exactly one result per dataset scenario, complete outcome-judge coverage, shared-actor activation on every scenario in both conditions, and a recorded semantic transition for every enacted operational actor action. Duplicate, missing, or unexpected result IDs fail even when integrity hashes verify. The judge receives only initial pre-action context, enacted sink receipts, and controller feedback; recorded future events are excluded. A terminal `none` proposes no operation and may omit an inline audit, while operational actions and refusals are audit-bound. Refusal and no-op terminal actions do not require a recorded transition. Repeated completed or unsupported catalog proposals terminate as measured actor stalls after one repair and never reach the sink. Actor stalls and bounded replan/step exhaustion are behavioral terminal outcomes rather than infrastructure failures; the check prints their rates. A failure message lists exact scenario-set, incomplete-scenario, or unresolved-action details.

The two conditions may use the same DeepSeek and Qwen accounts concurrently. Run them sequentially only when the attempt artifacts or terminal output report provider, authentication, timeout, or rate-limit failures. Unmatched enacted actions, schema failures outside bounded actor adaptation, and permission-delta failures are deterministic infrastructure failures rather than evidence of backend concurrency. Repaired-or-stalled unsupported proposals, actor stalls, and bounded budget terminals are reportable agent outcomes.

**CLOSED-LOOP FULL GATE — Wait for both closed-loop smoke checks to pass before starting either 48-item condition.**

Then launch the two full conditions concurrently in the same two initialized terminals, or repeat Section 5 in two new terminals.

Terminal 1 — sidecar closed-loop full:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_closed_loop configs/asb-full-gold-deepseek-closed-loop-sidecar.yaml && \
  sab_check_closed_loop artifacts/runs/asb-full-gold-deepseek-closed-loop-sidecar
```

Terminal 2 — inline closed-loop full:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_closed_loop configs/asb-full-gold-deepseek-closed-loop-inline.yaml && \
  sab_check_closed_loop artifacts/runs/asb-full-gold-deepseek-closed-loop-inline
```

Create the paired condition ablation. `--treatment-comparison` checks the shared comparison-contract hash, exact scenario IDs, dataset hash, run integrity, actor and judge profiles, seed, budgets, sink, enacted-only judge evidence scope, and execution semantics before computing pair-cluster bootstrap intervals and McNemar tests. The treatment descriptor retains condition-specific recovery-turn terminal handling.

```bash
selfauditbench compare \
  --run-a artifacts/runs/asb-full-gold-deepseek-closed-loop-sidecar \
  --run-b artifacts/runs/asb-full-gold-deepseek-closed-loop-inline \
  --treatment-comparison \
  --output artifacts/comparisons/asb-closed-loop-sidecar-vs-inline
```

Generate this comparison only after both full conditions have their final verified artifacts. Regenerate it if either run's integrity root changes later.

Retain these run artifacts for Results analysis: `recovery_turns.jsonl`, `controller_feedback.jsonl`, `action_executions.jsonl`, `closed_loop_model_attempts.jsonl`, `outcome_judgments.jsonl`, `closed_loop_trajectories.jsonl`, `closed_loop_summary.csv`, `metrics.json`, `supplementary_reliability.json`, and `integrity.json`. They support safety–task plots, recovery-rate and benign-noninterference tables, permission-compliance analysis, repeated-denial analysis, replan burden, terminal-reason analysis, token/cost accounting, and paired sidecar/inline ablations.

## 8. Enacted sink conformance

Run this once for the frozen study implementation. It is deterministic and does not use a model API.

```bash
mkdir -p artifacts/conformance/schemas
selfauditbench schema export artifacts/conformance/schemas
selfauditbench conformance live --output artifacts/conformance/live-enforcement.json
selfauditbench conformance verify artifacts/conformance/live-enforcement.json
```

The six cases demonstrate that broker terminal outcomes are enacted at the sink and that later actions are suppressed. Describe this as sink conformance, not end-to-end task completion after intervention.

## 9. Verified-only paper staging and result figures

The paper export accepts only verified run directories declared by the study allowlist. Create a timestamped staging directory, copy the exact verified paper runs into it, and pass the same set through `--run-ids` as a fail-closed allowlist.

```bash
stage="artifacts/runs/verified-paper-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$stage"

# Final ASB, ConVerse, and AgentForesight manuscript allowlist.
run_ids=(
  asb-full-gold-deepseek-sidecar
  asb-full-gold-qwen35-sidecar
  asb-full-gold-minimax-m27-sidecar
  asb-full-gold-ollama-gemma4-sidecar
  converse-full-gold-deepseek-sidecar
  converse-full-gold-qwen35-sidecar
  converse-full-gold-minimax-m27-sidecar
  converse-full-gold-ollama-gemma4-sidecar
  asb-full-gold-deepseek-closed-loop-sidecar
  asb-full-gold-deepseek-closed-loop-inline
  converse-full-gold-deepseek-closed-loop-sidecar
  converse-full-gold-deepseek-closed-loop-inline
  agentforesight-deepseek-native-baseline
  agentforesight-paper-split-no-audit
  agentforesight-paper-split-official-deepseek-sidecar
)

for run_id in "${run_ids[@]}"; do
  run="artifacts/runs/$run_id"
  test -d "$run" || { echo "missing intended run: $run" >&2; exit 1; }
  selfauditbench verify --run "$run" || exit 1
  cp -a "$run" "$stage/"
done
run_allowlist="$(IFS=,; echo "${run_ids[*]}")"
test -s Reproductions/AgentForesight/outputs/cstcloud-deepseek-v4-flash/results.json

selfauditbench paper export \
  --output "artifacts/paper/final-$(date +%Y%m%d_%H%M%S)" \
  --dataset-dir data/gold \
  --runs-dir "$stage" \
  --run-ids "$run_allowlist" \
  --agentforesight-results-json \
    Reproductions/AgentForesight/outputs/cstcloud-deepseek-v4-flash/results.json
```

The allowlist keeps DeepSeek, Qwen, and MiniMax as hosted semantic rows, Gemma as the prespecified local reliability reference, both closed-loop conditions per surface, and the three AFTraj runs. The AgentForesight result JSON must correspond to the staged native baseline. Archive the annotation evidence, comparisons, conformance artifact, and timestamped paper bundle together as the release evidence.

Generate the seven manuscript result figures from the verified paper export, compact gold, run records, and comparison artifacts. This stage makes no model/API calls.

```bash
python -m pip install -e '.[figures]'
python scripts/generate_result_figures.py --repo . --output Figures

for figure in \
  gold_annotation_landscape.pdf \
  backend_audit_performance.pdf \
  backend_pairwise_comparisons.pdf \
  risk_interception_progress.pdf \
  closed_loop_outcomes.pdf \
  afttraj_prefix_diagnostics.pdf \
  enforcement_assurance.pdf
do
  test -s "Figures/$figure" || {
    printf 'missing result figure: %s\n' "$figure" >&2
    exit 1
  }
done
```

The generator selects the most recent `artifacts/paper/final-*` export by default. Use `--paper-export artifacts/paper/<final-export>` to bind figure generation to a specific verified export. The local PowerShell command that writes to the research workspace's `Figures` directory is documented in `README.md`.
