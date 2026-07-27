# AgentForesight reproduction commands

Run from `Reproductions/AgentForesight` in a dedicated Python environment.

## 1. Install and configure

```bash
python -m pip install -r requirements.txt

read -rsp "CST Cloud API key: " CSTCLOUD_API_KEY
printf "\n"
export OPENAI_API_KEY="$CSTCLOUD_API_KEY"
export DEEPSEEK_API_KEY="$CSTCLOUD_API_KEY"
export BASE_URL="https://uni-api.cstcloud.cn/v1"
export OPENAI_BASE_URL="$BASE_URL"
export OPENAI_API_BASE="$BASE_URL"
export AGENTFORESIGHT_BASE_URL="$BASE_URL"
export MODEL_NAME="deepseek-v4-flash"
export AGENTFORESIGHT_MODEL="$MODEL_NAME"
export AGENTFORESIGHT_TIMEOUT_SECONDS="300"
export AGENTFORESIGHT_MAX_RETRIES="5"
```

Keep credentials in the shell environment or a private file outside the repository.

## 2. Acquire and verify AFTraj

The required dataset files are included under `data/`. To download them again:

```bash
python scripts/download_aftraj.py --output-dir ./data
```

Verify the full corpus and official paper split:

```bash
python - <<'PY'
from inference.data import load_aftraj

full = load_aftraj("./data")
paper = load_aftraj("./data", paper_test_split=True)
print("full_total=", len(full))
print("full_safe=", sum(row.label == "safe" for row in full))
print("full_unsafe=", sum(row.label == "unsafe" for row in full))
print("paper_test_total=", len(paper))
print("paper_test_safe=", sum(row.label == "safe" for row in paper))
print("paper_test_unsafe=", sum(row.label == "unsafe" for row in paper))
PY
```

Expected counts are 2,276 full trajectories and 332 held-out trajectories.

## 3. Validate the provider

```bash
python scripts/cstcloud_smoke.py

python -m inference.infer_api \
  --splits safe \
  --max-trajs 1 \
  --data-dir ./data \
  --output-dir ./outputs/smoke-safe \
  --macro-domain

python -m inference.infer_api \
  --splits unsafe \
  --max-trajs 1 \
  --data-dir ./data \
  --output-dir ./outputs/smoke-unsafe \
  --macro-domain
```

## 4. Run the held-out reproduction

```bash
bash scripts/run_cstcloud_reproduction.sh \
  --paper-test-split \
  --macro-domain \
  --resume
```

`--resume` skips completed trajectory IDs and retries unfinished rows without overwriting completed outputs.

## 5. Inspect results

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("outputs/cstcloud-deepseek-v4-flash/results.json")
results = json.loads(path.read_text())
for domain, metrics in results["by_domain"].items():
    print(domain, metrics)
PY
```

The retained paper-split output contains 169 safe and 163 unsafe trajectories.
