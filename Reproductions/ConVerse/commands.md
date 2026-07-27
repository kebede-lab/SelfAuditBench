# ConVerse reproduction commands

Run from `Reproductions/ConVerse` in a dedicated Python environment.

## 1. Install and configure

```bash
python -m pip install -r requirements.txt

read -rsp "Official DeepSeek API key: " DEEPSEEK_API_KEY
printf "\n"
export DEEPSEEK_API_KEY
export OPENAI_API_KEY="$DEEPSEEK_API_KEY"
export BASE_URL="https://api.deepseek.com"
export OPENAI_BASE_URL="$BASE_URL"
export OPENAI_API_BASE="$BASE_URL"
export MODEL_NAME="deepseek-v4-flash"
export OPENAI_MODEL="$MODEL_NAME"
export CONVERSE_MODEL="$MODEL_NAME"
export CONVERSE_JUDGE_MODEL="$MODEL_NAME"
```

Keep credentials in the shell environment or a private file outside the repository. This reproduction uses chat completions only and does not require an embedding backend.

## 2. Validate the provider

```bash
python scripts/deepseek_smoke.py
```

The probe must report `chat_ok=1` and `converse_initial_plan_ok=1`.

## 3. Run the smoke and full reproduction

```bash
bash scripts/run_deepseek_full_reproduction.sh --smoke
bash scripts/run_deepseek_full_reproduction.sh
```

Outputs are written below `logs/<domain>/deepseek_v4_flash/`.

## 4. Validate generated files

JSON outputs must parse and must not contain a recorded simulation failure:

```bash
python - <<'PY'
import json
from pathlib import Path

valid = 0
failed = []
for path in Path("logs").glob("**/output_*.json"):
    try:
        payload = json.loads(path.read_text())
    except Exception as exc:
        failed.append((path, f"invalid JSON: {exc}"))
        continue
    text = json.dumps(payload).lower()
    if "simulation failed with error" in text:
        failed.append((path, "simulation failure"))
    else:
        valid += 1

print("valid_outputs=", valid)
for path, reason in failed:
    print("FAILED", reason, path)
raise SystemExit(1 if failed else 0)
PY
```

The pair-specific benign control totals used by SelfAuditBench are:

```bash
for item in \
  "real_estate persona1 8" \
  "travel_planning persona1 8" \
  "insurance persona2 4" \
  "insurance persona3 4"
do
  read -r domain persona required <<< "$item"
  count=$(find "logs/$domain" -type f \
    -path "*/baseline/$persona/benign_easy/*/output_*.json" | wc -l)
  printf "%-18s %-9s successful=%s required=%s\n" \
    "$domain" "$persona" "$count" "$required"
done
```
