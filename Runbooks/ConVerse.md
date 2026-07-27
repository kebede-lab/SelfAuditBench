# ConVerse Data and Evaluation Runbook

This is the reproducibility runbook for materializing the ConVerse control set, building the shared gold candidate manifest, and running the ConVerse gold surface. Commands assume Bash in the experiment environment. Sections 0--2 run before the shared annotation workflow; Sections 3--6 run after it.

The workflow supports **recorded-action replay with broker-mediated absorbing terminal projection** and **enacted closed-loop recovery under self-requested monotonic restriction**. Closed-loop runs feed broker decisions and reduced permissions to the acting model, mediate fresh proposals, gate the action sink, and use a role-separated outcome judge. Report ConVerse separately from ASB. The shared combined dataset documents one annotation study and supports descriptive cross-surface summaries.

Tracked YAML files under `configs/` are immutable during study execution. Use the referenced files exactly as committed.

**EXECUTION ORDER — Complete ConVerse Sections 0–2, then stop and go to `ASB.md` Sections 2–4 for the one shared full annotation and adjudication. Return here at ConVerse Section 3 only after every ASB compact verification succeeds. Never continue directly from ConVerse Section 2 to Section 3.**

## 0. Environment

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
python -m pip install -r requirements.txt
python -m pip install -e .
mkdir -p artifacts/{exploratory,runs,conformance,paper} data/gold
pytest -q

. "$HOME/.config/api-env/selfauditbench-apis.env"
```

If the token-only SelfAuditBench API environment does not exist, create it with the secure one-time block in `ASB.md`. The tracked configs define provider endpoints, model identifiers, retry settings, and all experiment parameters.

Prepare the prespecified local open-source reference only if it will be run:

```bash
mkdir -p "$HOME/.cache"
pgrep -f 'ollama serve' >/dev/null || nohup ollama serve > "$HOME/.cache/ollama-serve.log" 2>&1 &
ollama pull gemma4:12b
```

## 1. Materialize the 24 pair-specific benign controls

The candidate design requires 24 distinct ConVerse benign controls. Three source trajectories are retained as successful `rep1` items for the targets below; the four commands materialize the remaining `7 + 7 + 3 + 4 = 21` items. Reusing a benign trajectory under multiple IDs would inflate the false-alarm sample size and invalidate paired uncertainty.

| Target | Existing controls | Required total | `--repetitions` |
|---|---:|---:|---:|
| `real_estate`, persona 1 | rep1 | 8 | 8 |
| `travel_planning`, persona 1 | rep1 | 8 | 8 |
| `insurance`, persona 2 | rep1 | 4 | 4 |
| `insurance`, persona 3 | none | 4 | 4 |
| **Generated in this stage** | **3 retained** | **24 total** | **21 generated** |

Only this control-generation section uses the official DeepSeek API in explicit non-thinking mode. Its token and endpoint are isolated in `~/.config/api-env/converse-official-deepseek.env`; the SelfAuditBench replay configs and their provider tokens are unchanged. Each `--repetitions` value is the required total for that target. The runner preserves a successful existing repetition only when its own repetition number matches, then generates the missing repetition slots. Provider/runtime failures receive up to three attempts.

This execution path uses chat-completion calls for the assistant, simulated user environment, external agent, and judges. It has no embedding-model, vector-store, or retrieval-backend dependency; no Ollama embedding service is used.

```bash
install -m 700 -d "$HOME/.config/api-env"
if [ ! -f "$HOME/.config/api-env/converse-official-deepseek.env" ]; then
  read -rsp 'Official DeepSeek API token: ' OFFICIAL_DEEPSEEK_TOKEN; echo
  umask 077
  {
    printf 'export OPENAI_API_KEY=%q\n' "$OFFICIAL_DEEPSEEK_TOKEN"
    printf 'export BASE_URL=%q\n' 'https://api.deepseek.com'
    printf 'export OPENAI_BASE_URL=%q\n' 'https://api.deepseek.com'
    printf 'export OPENAI_API_BASE=%q\n' 'https://api.deepseek.com'
    printf 'export CONVERSE_MODEL=%q\n' 'deepseek-v4-flash'
    printf 'export CONVERSE_JUDGE_MODEL=%q\n' 'deepseek-v4-flash'
  } > "$HOME/.config/api-env/converse-official-deepseek.env"
  chmod 600 "$HOME/.config/api-env/converse-official-deepseek.env"
  unset OFFICIAL_DEEPSEEK_TOKEN
fi

cd /path/to/SelfAuditBench/Reproductions/ConVerse
. "$HOME/.config/api-env/converse-official-deepseek.env"

test -n "${OPENAI_API_KEY:-}" || { echo 'missing official DeepSeek token' >&2; exit 1; }
test "$BASE_URL" = 'https://api.deepseek.com' || { echo 'wrong ConVerse generation endpoint' >&2; exit 1; }
test "$CONVERSE_MODEL" = 'deepseek-v4-flash' || { echo 'wrong ConVerse generation model' >&2; exit 1; }

python scripts/deepseek_smoke.py
```

The probe disables DeepSeek V4 thinking mode and submits both a tiny completion and the exact structured initial-planning request used by `real_estate` persona 1.

**STOP — Continue only if the official-DeepSeek probe prints `chat_ok=1`, `converse_initial_plan_ok=1`, `base_url=https://api.deepseek.com`, and `model=deepseek-v4-flash`. If the representative initial-plan probe fails or times out, do not start any control repetitions.**

Run one complete `insurance` persona 3 trajectory as the end-to-end control-generation gate. This successful output becomes its `rep1` and is reused by the total-target command below:

```bash
python main.py --provider openai --llm_name "$CONVERSE_MODEL" \
  --judge_provider openai --judge_llm_name "$CONVERSE_JUDGE_MODEL" \
  --use_case insurance --persona_id 3 --simulation_type benign_easy \
  --baseline_mode --run_all_attacks --repetitions 1 --simulation_timeout 600 \
  --logs_folder logs

test "$(find logs/insurance -type f \
  -path '*/baseline/persona3/benign_easy/*/output_*.json' | wc -l)" -ge 1 || {
  echo 'end-to-end ConVerse control gate failed' >&2
  exit 1
}
```

**STOP — Continue only after the end-to-end gate creates a valid `insurance` persona 3 `output_*.json`. The following total targets preserve every matching completed repetition and generate the remaining controls needed for totals `8 + 8 + 4 + 4`.**

```bash
cd /path/to/SelfAuditBench/Reproductions/ConVerse
. "$HOME/.config/api-env/converse-official-deepseek.env"

python main.py --provider openai --llm_name "$CONVERSE_MODEL" \
  --judge_provider openai --judge_llm_name "$CONVERSE_JUDGE_MODEL" \
  --use_case real_estate --persona_id 1 --simulation_type benign_easy \
  --baseline_mode --run_all_attacks --repetitions 8 --simulation_timeout 600 \
  --logs_folder logs

python main.py --provider openai --llm_name "$CONVERSE_MODEL" \
  --judge_provider openai --judge_llm_name "$CONVERSE_JUDGE_MODEL" \
  --use_case travel_planning --persona_id 1 --simulation_type benign_easy \
  --baseline_mode --run_all_attacks --repetitions 8 --simulation_timeout 600 \
  --logs_folder logs

python main.py --provider openai --llm_name "$CONVERSE_MODEL" \
  --judge_provider openai --judge_llm_name "$CONVERSE_JUDGE_MODEL" \
  --use_case insurance --persona_id 2 --simulation_type benign_easy \
  --baseline_mode --run_all_attacks --repetitions 4 --simulation_timeout 600 \
  --logs_folder logs

python main.py --provider openai --llm_name "$CONVERSE_MODEL" \
  --judge_provider openai --judge_llm_name "$CONVERSE_JUDGE_MODEL" \
  --use_case insurance --persona_id 3 --simulation_type benign_easy \
  --baseline_mode --run_all_attacks --repetitions 4 --simulation_timeout 600 \
  --logs_folder logs
```

List and count the resulting benign trajectories before proceeding:

```bash
find logs -path '*/benign_easy/*/output_*.json' -type f | sort

for item in \
  "real_estate persona1 8" \
  "travel_planning persona1 8" \
  "insurance persona2 4" \
  "insurance persona3 4"
do
  read -r domain persona required <<< "$item"
  count=$(find "logs/$domain" -type f \
    -path "*/baseline/$persona/benign_easy/*/output_*.json" | wc -l)
  printf '%-18s %-9s successful=%s required=%s\n' \
    "$domain" "$persona" "$count" "$required"
done
```

The successful totals must be at least `8`, `8`, `4`, and `4`; these totals include the three existing controls. If a target is short, rerun only its missing number of repetitions. Never copy, rename, or alias an existing output to satisfy a count.

**STOP AND INSPECT — Read the generated ConVerse output files, confirm that all four target totals are met, and inspect any failure or timeout logs. Continue to Section 2 only after this inspection passes; Section 2 then enforces successful materialization plus source and content uniqueness.**

## 2. Ingest and build the source-unique selection

Do not manually replace any `regenerate:` entry in `data/gold/candidates.yaml`. Rebuild the manifest from real paths after generation. Candidate selection normalizes the source roots and reserves trajectory-content fingerprints while choosing all 48 pairs, so different rows or files with identical observable content are skipped. Manifest validation then rejects placeholders and repeated source references; packet materialization independently rechecks all 96 sources, normalized contents, and pair members.

**The `annotate select` command below rebuilds `data/gold/candidates.yaml`; the following `--final-ready` command is the mandatory gate before the shared annotation packet may be created.**

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab

selfauditbench ingest converse Reproductions/ConVerse/logs artifacts/exploratory/converse.jsonl
selfauditbench dataset summary artifacts/exploratory/converse.jsonl \
  --output artifacts/exploratory/converse.summary.json
selfauditbench ingest asb Reproductions/ASB/logs artifacts/exploratory/asb.jsonl
selfauditbench dataset summary artifacts/exploratory/asb.jsonl \
  --output artifacts/exploratory/asb.summary.json

selfauditbench annotate select \
  --asb-root Reproductions/ASB/logs \
  --converse-root Reproductions/ConVerse/logs \
  --output data/gold/candidates.yaml
selfauditbench annotate validate data/gold/candidates.yaml --final-ready
```

Stop if `--final-ready` fails. The remedy is to generate the missing real source trajectory and rerun ingestion/selection, never to weaken validation.

**STOP — If `--final-ready` passes, do not execute ConVerse Section 3 yet. Now go to `ASB.md` and complete Sections 2–4 exactly once. Those sections create the full 96-item packet, pause for both independent annotations, pause for human adjudication, create the final gold dataset, and verify the full and smoke compacts. Return to ConVerse Section 3 only after ASB Section 4 declares the annotation complete.**

## 3. Backend runner and hard verification gate

Confirm that the shared workflow produced the ConVerse inputs used below:

**RETURN POINT — Resume here only after `ASB.md` Sections 2–4 have completed successfully. The following check confirms that the full ConVerse gold compact, its derived smoke subset, and the shared annotation-evidence manifest exist. No annotation or adjudication is performed in this runbook.**

```bash
for path in \
  data/gold/selfauditbench-gold-converse.jsonl \
  data/gold/selfauditbench-gold-converse.integrity.json \
  data/gold/selfauditbench-gold-readiness-converse.jsonl \
  data/gold/selfauditbench-gold-readiness-converse.integrity.json \
  data/gold/selfauditbench-gold.annotation_evidence.json
do
  test -s "$path" || { echo "missing shared-study output: $path" >&2; exit 1; }
done
```

Sections 2--4 of `ASB.md` define compact integrity and study-shape verification. Continue only after every check in those sections passes.

**If any required file is missing, stop and go back to `ASB.md` Section 3 or 4 as appropriate. If all files exist and their ASB verification succeeded, define the helpers below and continue to ConVerse Section 4 for the smoke run.**

Every new terminal has its own shell state. The runnable terminal blocks below repeat this setup so each block can be pasted into a fresh terminal as written. The helper selects only the token; the tracked YAML is authoritative.

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
type sab_run sab_closed_loop sab_check_run sab_check_smoke sab_check_closed_loop
```

The tracked DeepSeek configs use `https://api.deepseek.com` with thinking disabled. `DEEPSEEK_API_KEY` must therefore contain the official DeepSeek API token, not a CSTCloud token. Qwen and MiniMax use their tracked CSTCloud routes. Qwen3.5 thinking is disabled with its OpenAI-compatible `enable_thinking` control, and the Ollama Gemma configs disable thinking through the OpenAI-compatible reasoning control.

`selfauditbench verify` must report a verified run. Exclude `legacy_unverified` and `corrupt` runs from analysis and paper staging.

## 4. Adjudicated gold smoke, then full ConVerse replay

After the shared full annotation, adjudication, compact export, and integrity verification succeed, open four terminals. Run the Section 3 terminal setup in every terminal, then launch one smoke command in each terminal. These runs are safe to execute concurrently because the tracked configs have distinct run IDs and output directories.

**SMOKE STAGE ONLY — Start all desired smoke terminals in parallel, wait for every smoke and its check to finish, and do not start any full command yet.**

Terminal 1 — DeepSeek:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/converse-some-gold-deepseek-sidecar.yaml deepseek && \
  sab_check_smoke artifacts/runs/converse-some-gold-deepseek-sidecar
```

Terminal 2 — Qwen3.5:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/converse-some-gold-qwen35-sidecar.yaml qwen35 && \
  sab_check_smoke artifacts/runs/converse-some-gold-qwen35-sidecar
```

Terminal 3 — MiniMax M2.7:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/converse-some-gold-minimax-m27-sidecar.yaml minimax-m27 && \
  sab_check_smoke artifacts/runs/converse-some-gold-minimax-m27-sidecar
```

Terminal 4 — local Gemma 4 supplementary reference:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/converse-some-gold-ollama-gemma4-sidecar.yaml ollama-gemma4 && \
  sab_check_run artifacts/runs/converse-some-gold-ollama-gemma4-sidecar
```

Promote only hosted backends that pass all smoke checks. Failed hosted runs are stress/reliability evidence and are ineligible for headline semantic rows. Gemma 4 is the prespecified local open-source reliability baseline and is supplementary when it does not satisfy the hosted smoke gate.

**FULL-RUN GATE — Continue only after all smoke terminals have ended and each hosted backend you intend to promote printed a passing smoke gate. Do not launch a hosted full run whose smoke failed.**

Reuse the four terminals, or open new terminals and repeat the Section 3 setup. Launch one full command per promoted backend so the eligible full runs execute concurrently.

Terminal 1 — DeepSeek, only if promoted:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/converse-full-gold-deepseek-sidecar.yaml deepseek && \
  sab_check_run artifacts/runs/converse-full-gold-deepseek-sidecar
```

Terminal 2 — Qwen3.5, only if promoted:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/converse-full-gold-qwen35-sidecar.yaml qwen35 && \
  sab_check_run artifacts/runs/converse-full-gold-qwen35-sidecar
```

Terminal 3 — MiniMax M2.7, only if promoted:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/converse-full-gold-minimax-m27-sidecar.yaml minimax-m27 && \
  sab_check_run artifacts/runs/converse-full-gold-minimax-m27-sidecar
```

Terminal 4 — local Gemma 4 supplementary reference, if included:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_run configs/converse-full-gold-ollama-gemma4-sidecar.yaml ollama-gemma4 && \
  sab_check_run artifacts/runs/converse-full-gold-ollama-gemma4-sidecar
```

Generate the complete pairwise backend-comparison matrix only after all four intended
ConVerse full runs exist and verify under the same gold compact and evaluation contract.
This stage reads completed artifacts and makes no model/API calls. DeepSeek versus Qwen is
the primary hosted contrast; DeepSeek/Qwen/MiniMax contrasts provide hosted-backend
robustness. Every contrast containing Gemma is supplementary and must be interpreted
together with its schema, completion, and failure-reliability results rather than promoted
to a headline semantic result.

```bash
set -euo pipefail
mkdir -p artifacts/comparisons

backends=(deepseek qwen35 minimax-m27 ollama-gemma4)
for backend in "${backends[@]}"; do
  selfauditbench verify \
    --run "artifacts/runs/converse-full-gold-${backend}-sidecar"
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
    --run-a "artifacts/runs/converse-full-gold-${backend_a}-sidecar" \
    --run-b "artifacts/runs/converse-full-gold-${backend_b}-sidecar" \
    --output "artifacts/comparisons/converse-${backend_a}-vs-${backend_b}.json"
done
```

This produces six ConVerse JSON files and six matching Markdown summaries. Preserve all
twelve; the structured files support plotting and statistical analysis, while the Markdown
files provide directly inspectable result summaries.

Comparison files bind the source runs' integrity roots. If `score`, `report`, or any other operation changes a source run's integrity root after comparison, regenerate every affected comparison before release staging.

## 5. Enacted closed-loop recovery and paired condition comparison

Run both conditions on the pair-complete smoke subset first. Both conditions activate the same DeepSeek actor immediately before the first recorded proposal and share the pre-action context, utility target, outcome-free transition catalog, permissions, budgets, seed, normalized sink, and Qwen outcome judge. Sidecar externally audits each fresh proposal; inline emits a controller-bound self-audit with the proposal.

Use a clean output directory for the study execution and preserve each verified run as immutable evidence.

Open two terminals and run the Section 3 setup in each.

Terminal 1 — sidecar closed-loop smoke:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_closed_loop configs/converse-some-gold-deepseek-closed-loop-sidecar.yaml && \
  sab_check_closed_loop artifacts/runs/converse-some-gold-deepseek-closed-loop-sidecar
```

Terminal 2 — inline closed-loop smoke:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_closed_loop configs/converse-some-gold-deepseek-closed-loop-inline.yaml && \
  sab_check_closed_loop artifacts/runs/converse-some-gold-deepseek-closed-loop-inline
```

The two conditions have distinct run IDs and may run concurrently, subject to the shared DeepSeek and Qwen account rate limits. Never start two processes with the same config/run ID: an exclusive run-directory lease rejects the second process before it can reset or append artifacts.

`sab_check_closed_loop` is the same general readiness check for smoke and full runs. It requires exactly one result per dataset scenario, complete outcome-judge coverage, shared-actor activation on every scenario in both conditions, and a recorded semantic transition for every enacted operational actor action. Duplicate, missing, or unexpected result IDs fail even when integrity hashes verify. The judge receives only initial pre-action context, enacted sink receipts, and controller feedback; recorded future events are excluded. A terminal `none` proposes no operation and may omit an inline audit, while operational actions and refusals are audit-bound. Refusal and no-op terminal actions do not require a recorded transition. Repeated completed or unsupported catalog proposals terminate as measured actor stalls after one repair and never reach the sink. Actor stalls and bounded replan/step exhaustion are behavioral terminal outcomes rather than infrastructure failures; the check prints their rates. A failure message lists exact scenario-set, incomplete-scenario, or unresolved-action details.

The recovery actor and outcome judge use the same bounded JSON-object extractor. Provider-added Markdown fences or short wrappers are removed before strict schema validation, and outcome-judge rationales have a 2,000-character bound. No separate provider smoke or setup command is required before the two closed-loop smoke blocks.

The two conditions may use the same DeepSeek and Qwen accounts concurrently. Run them sequentially only when the attempt artifacts or terminal output report provider, authentication, timeout, or rate-limit failures. Unmatched enacted actions, schema failures outside bounded actor adaptation, and permission-delta failures are deterministic infrastructure failures rather than evidence of backend concurrency. Repaired-or-stalled unsupported proposals, actor stalls, and bounded budget terminals are reportable agent outcomes.

**CLOSED-LOOP FULL GATE — Wait for both closed-loop smoke checks to pass before starting either 48-item condition.**

Then launch the two full conditions concurrently in the same two initialized terminals, or repeat Section 3 in two new terminals.

Terminal 1 — sidecar closed-loop full:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_closed_loop configs/converse-full-gold-deepseek-closed-loop-sidecar.yaml && \
  sab_check_closed_loop artifacts/runs/converse-full-gold-deepseek-closed-loop-sidecar
```

Terminal 2 — inline closed-loop full:

```bash
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
. "$HOME/.config/api-env/selfauditbench-apis.env"
. scripts/runbook_helpers.sh
sab_closed_loop configs/converse-full-gold-deepseek-closed-loop-inline.yaml && \
  sab_check_closed_loop artifacts/runs/converse-full-gold-deepseek-closed-loop-inline
```

Create the paired treatment ablation under the shared comparison contract, which fixes the enacted-only judge evidence scope as well as the dataset, sink, budgets, seed, actor, and judge profiles. The treatment descriptor retains condition-specific recovery-turn terminal handling:

```bash
selfauditbench compare \
  --run-a artifacts/runs/converse-full-gold-deepseek-closed-loop-sidecar \
  --run-b artifacts/runs/converse-full-gold-deepseek-closed-loop-inline \
  --treatment-comparison \
  --output artifacts/comparisons/converse-closed-loop-sidecar-vs-inline
```

Generate this comparison only after both full conditions have verified artifacts. Regenerate it whenever either run's integrity root changes.

The run directory records recovery turns, broker feedback with permission snapshots, action-sink receipts, model attempts and repairs, independent outcome judgments, terminal trajectories, per-scenario CSV rows, aggregate metrics, runtime/cost summaries, and integrity hashes. These artifacts directly support surface-specific safety, task, joint safe-task, recovery, noninterference, permission-compliance, repetition, terminal-state, and replan-burden analyses.

## 6. Conformance and release artifacts

Run deterministic enacted-sink conformance once for the frozen study implementation and verify the emitted artifact:

```bash
mkdir -p artifacts/conformance/schemas
selfauditbench schema export artifacts/conformance/schemas
selfauditbench conformance live --output artifacts/conformance/live-enforcement.json
selfauditbench conformance verify artifacts/conformance/live-enforcement.json
```

This supports the secondary sink-conformance claim only. It does not turn recorded replay into native task evaluation.

After both ConVerse comparison stages and conformance verification succeed, use `ASB.md` Section 9 for the single cross-surface verified-only paper export and seven result figures. That allowlist contains the declared ASB, ConVerse, and AgentForesight full runs and produces one cross-surface release bundle.
