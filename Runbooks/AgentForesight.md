# AgentForesight AFTraj Prefix-Diagnostic Runbook

This is the authoritative SelfAuditBench workflow for the AgentForesight AFTraj held-out
paper split. Run every command from `/path/to/SelfAuditBench`.

## Evidence scope

AFTraj supplies curated safe/unsafe labels and a decisive-error step. Its evidence scope is:

- native and SelfAuditBench prefix localization;
- Exact-F1, absolute step shift, safe-prefix false-alarm rate, and step accuracy;
- audit/schema reliability, provider failures, latency, and token accounting.

ASB and ConVerse supply the adjudicated harm boundaries, accepted interventions, minimal permission deltas, and enacted recovery outcomes. The manuscript presents AFTraj as a separate prefix-localization and reliability surface and presents ASB/ConVerse as separate recorded-action and closed-loop surfaces.

## 1. Environment

```bash
set -euo pipefail
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
python -m pip install -r requirements.txt
python -m pip install -e .

export PROJECT_ROOT=/path/to/SelfAuditBench/Reproductions
export AF_ROOT="$PROJECT_ROOT/AgentForesight"
mkdir -p artifacts/exploratory artifacts/runs artifacts/verification ~/.config/api-env
chmod 700 ~/.config/api-env
```

The tracked hosted sidecar configs use the official DeepSeek endpoint and read
`DEEPSEEK_API_KEY` from the shared protected API environment. Never print or commit the
token.

```bash
test -s ~/.config/api-env/selfauditbench-apis.env || {
  echo "Missing ~/.config/api-env/selfauditbench-apis.env; create it in ASB runbook Section 0." >&2
  exit 1
}
chmod 600 ~/.config/api-env/selfauditbench-apis.env
. ~/.config/api-env/selfauditbench-apis.env
test -n "${DEEPSEEK_API_KEY:-}"
```

Use the checked-in configs exactly as tracked:

- `configs/agentforesight-official-deepseek-smoke.yaml`: 12-item hosted smoke run;
- `configs/agentforesight-official-deepseek-sidecar.yaml`: full held-out sidecar diagnostic;
- `configs/agentforesight-no-audit.yaml`: full processing baseline;
- `configs/agentforesight-sidecar.example.yaml`: documentation only, not runnable evidence.

Tracked experiment configs are immutable during execution. Every backend uses a reviewed tracked config.

## 2. Normalize and freeze diagnostic datasets

```bash
test -s "$AF_ROOT/data/aftraj_safe.parquet"
test -s "$AF_ROOT/data/aftraj_unsafe.parquet"
test -s "$AF_ROOT/data/splits_test.json"

selfauditbench ingest agentforesight \
  "$AF_ROOT/data" \
  artifacts/exploratory/agentforesight-paper-test.jsonl \
  --paper-test-split

selfauditbench dataset summary \
  artifacts/exploratory/agentforesight-paper-test.jsonl \
  --output artifacts/exploratory/agentforesight-paper-test.dataset_summary.json

head -n 12 artifacts/exploratory/agentforesight-paper-test.jsonl \
  > artifacts/exploratory/agentforesight-smoke-12.jsonl
selfauditbench dataset summary \
  artifacts/exploratory/agentforesight-smoke-12.jsonl \
  --output artifacts/exploratory/agentforesight-smoke-12.dataset_summary.json

sha256sum \
  artifacts/exploratory/agentforesight-paper-test.jsonl \
  artifacts/exploratory/agentforesight-paper-test.dataset_summary.json \
  artifacts/exploratory/agentforesight-smoke-12.jsonl \
  artifacts/exploratory/agentforesight-smoke-12.dataset_summary.json \
  > artifacts/verification/agentforesight-datasets.sha256
sha256sum -c artifacts/verification/agentforesight-datasets.sha256
```

Require `prefix_reliability_only` in every summary; any other status here is an error.

```bash
python - <<'PY'
import json
from pathlib import Path

paths = [
    Path("artifacts/exploratory/agentforesight-paper-test.dataset_summary.json"),
    Path("artifacts/exploratory/agentforesight-smoke-12.dataset_summary.json"),
]
for path in paths:
    value = json.loads(path.read_text())
    status = value["headline_eligibility"]["status"]
    print(path.name, value["scenario_count"], status)
    if status != "prefix_reliability_only":
        raise SystemExit(f"unexpected AFTraj claim status: {status}")
PY
```

The 12-item file is a deterministic prefix of the normalized full held-out split and is used only as the smoke gate before the full hosted run.

## 3. Import the native AgentForesight baseline

```bash
test -s "$AF_ROOT/outputs/cstcloud-deepseek-v4-flash/per_sample.jsonl"
test -s "$AF_ROOT/outputs/cstcloud-deepseek-v4-flash/results.json"

selfauditbench ingest agentforesight-results \
  "$AF_ROOT/outputs/cstcloud-deepseek-v4-flash/per_sample.jsonl" \
  artifacts/exploratory/agentforesight-paper-test.jsonl \
  artifacts/runs/agentforesight-deepseek-native-baseline \
  --skip-paper-export

selfauditbench verify \
  --run artifacts/runs/agentforesight-deepseek-native-baseline \
  > artifacts/verification/agentforesight-deepseek-native-baseline.json
```

Require the imported run to verify; `legacy_unverified` is not acceptable evidence.

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("artifacts/verification/agentforesight-deepseek-native-baseline.json")
value = json.loads(path.read_text())
print(value)
if value["status"] != "verified":
    raise SystemExit("native baseline is not verified")
PY
```

## 4. Run the processing baseline and hosted smoke gate

AgentForesight has one tracked hosted backend, so it has no multi-backend smoke/full fan-out. The no-audit processing baseline and the official DeepSeek smoke have distinct run IDs and may execute concurrently in two terminals. Initialize each new terminal independently. Do not run this hosted lane concurrently with another official DeepSeek run when latency, provider reliability, and token accounting are being measured.

```bash
set -euo pipefail
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
mkdir -p artifacts/runs artifacts/verification
```

Terminal 1 — no-audit full-split processing baseline; this makes no model calls:

```bash
set -euo pipefail
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
mkdir -p artifacts/runs artifacts/verification
selfauditbench run replay \
  --config configs/agentforesight-no-audit.yaml \
  --skip-paper-export
selfauditbench verify \
  --run artifacts/runs/agentforesight-paper-split-no-audit \
  > artifacts/verification/agentforesight-paper-split-no-audit.json
```

Terminal 2 — tracked 12-item official DeepSeek sidecar smoke config. Run the terminal setup above first, then:

```bash
set -euo pipefail
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
mkdir -p artifacts/runs artifacts/verification
. ~/.config/api-env/selfauditbench-apis.env
selfauditbench run replay \
  --config configs/agentforesight-official-deepseek-smoke.yaml \
  --skip-paper-export
selfauditbench verify \
  --run artifacts/runs/agentforesight-smoke-12-official-deepseek-sidecar \
  > artifacts/verification/agentforesight-smoke-12-official-deepseek-sidecar.json
```

Do not start the full hosted run unless integrity is verified, the backend smoke gate
passes, and the dataset claim status is prefix-only. The following gate belongs in Terminal 2 after the smoke command finishes:

```bash
python - <<'PY'
import json
from pathlib import Path

run = Path("artifacts/runs/agentforesight-smoke-12-official-deepseek-sidecar")
verification = json.loads(
    Path("artifacts/verification/agentforesight-smoke-12-official-deepseek-sidecar.json").read_text()
)
supplement = json.loads((run / "supplementary_reliability.json").read_text())
gates = supplement["run_gates"]
print("integrity:", verification["status"])
print("decision:", gates["decision"])
print("backend_ready:", gates["backend_ready_for_full_run"])
print("dataset_claim_status:", gates["dataset_claim_status"])
if verification["status"] != "verified":
    raise SystemExit("smoke run is not verified")
if not gates["backend_ready_for_full_run"]:
    raise SystemExit("backend failed smoke; do not run the full diagnostic")
if gates["dataset_claim_status"] != "prefix_reliability_only":
    raise SystemExit("AFTraj claim status must be prefix_reliability_only")
PY
```

## 5. Run and verify the full sidecar diagnostic

**FULL-RUN GATE — Wait for the hosted smoke verification and Python gate in Section 4 to pass. AgentForesight has only one tracked hosted backend, so run this full diagnostic in one initialized terminal rather than starting a backend matrix.**

Reuse Terminal 2, or open a new terminal and repeat the Section 4 terminal setup before running:

```bash
set -euo pipefail
cd /path/to/SelfAuditBench
. "$(conda info --base)/etc/profile.d/conda.sh"
conda activate sab
mkdir -p artifacts/runs artifacts/verification
. ~/.config/api-env/selfauditbench-apis.env
selfauditbench run replay \
  --config configs/agentforesight-official-deepseek-sidecar.yaml \
  --skip-paper-export
selfauditbench verify \
  --run artifacts/runs/agentforesight-paper-split-official-deepseek-sidecar \
  > artifacts/verification/agentforesight-paper-split-official-deepseek-sidecar.json
```

Verify every declared full run together and reject corrupt artifacts or runs outside the declared set.

```bash
python - <<'PY'
import json
from pathlib import Path

names = [
    "agentforesight-deepseek-native-baseline",
    "agentforesight-paper-split-no-audit",
    "agentforesight-paper-split-official-deepseek-sidecar",
]
for name in names:
    path = Path("artifacts/verification") / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"missing verification record: {path}")
    value = json.loads(path.read_text())
    print(name, value["status"], value.get("root_digest"))
    if value["status"] != "verified":
        raise SystemExit(f"run is not manuscript-eligible: {name}")
PY
```

If `score` or `report` is run after verification, it refreshes derived artifacts and the
integrity manifest. Verify again before staging.

## 6. Separate ASB/ConVerse conformance verification

The independently generated ASB/ConVerse sink-conformance artifact is verified separately:

```bash
test -s artifacts/conformance/live-enforcement.json
selfauditbench conformance verify artifacts/conformance/live-enforcement.json
```

The AFTraj evidence scope is prefix localization and reliability.

## 7. Stage verified runs and export paper assets

Never point the final paper export at a mixed `artifacts/runs` directory. Smoke,
`legacy_unverified`, corrupt, partially refreshed, or unrelated runs can otherwise enter
tables. Stage only runs whose current verification result is exactly `verified`, and pass
the same IDs with `--run-ids` as a second allowlist.

```bash
set -euo pipefail
STAGE=artifacts/staging/agentforesight-final
test ! -e "$STAGE" || { echo "Refusing to overwrite $STAGE"; exit 1; }
mkdir -p "$STAGE/runs" "$STAGE/datasets"

RUN_IDS=(
  agentforesight-deepseek-native-baseline
  agentforesight-paper-split-no-audit
  agentforesight-paper-split-official-deepseek-sidecar
)

for name in "${RUN_IDS[@]}"; do
  result="$(selfauditbench verify --run "artifacts/runs/$name")"
  status="$(python -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$result")"
  test "$status" = verified || { echo "$name is $status; refusing to stage"; exit 1; }
  cp -a "artifacts/runs/$name" "$STAGE/runs/"
done
RUN_ALLOWLIST="$(IFS=,; echo "${RUN_IDS[*]}")"

cp -a artifacts/exploratory/agentforesight-paper-test.jsonl "$STAGE/datasets/"
sha256sum -c artifacts/verification/agentforesight-datasets.sha256

OUT=artifacts/paper/frozen-agentforesight
test ! -e "$OUT" || { echo "Refusing to overwrite $OUT"; exit 1; }
selfauditbench paper export \
  --dataset-dir "$STAGE/datasets" \
  --runs-dir "$STAGE/runs" \
  --run-ids "$RUN_ALLOWLIST" \
  --agentforesight-results-json \
    "$AF_ROOT/outputs/cstcloud-deepseek-v4-flash/results.json" \
  --output "$OUT"

sha256sum "$OUT/paper_export_manifest.json" \
  > "$OUT/paper_export_manifest.sha256"
sha256sum -c "$OUT/paper_export_manifest.sha256"
```

Use `tables/agentforesight_prefix_by_domain.*` plus the separated reliability/API tables.
Any paper text derived from this export must retain the prefix-only diagnostic wording in
the claim boundary above.

The cross-surface manuscript bundle and seven result figures are generated once through `ASB.md` Section 9 after the declared ASB, ConVerse, closed-loop, and AgentForesight runs all verify.
