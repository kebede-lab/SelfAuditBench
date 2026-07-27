# ASB reproduction commands

Run from `Reproductions/ASB` in a dedicated Python environment.

## 1. Install and configure

```bash
python -m pip install -r requirements.txt

read -rsp "Official DeepSeek API key: " DEEPSEEK_API_KEY
printf "\n"
export DEEPSEEK_API_KEY
export OPENAI_API_KEY="$DEEPSEEK_API_KEY"
export BASE_URL="https://api.deepseek.com/v1"
export OPENAI_BASE_URL="$BASE_URL"
export OPENAI_API_BASE="$BASE_URL"
export MODEL_NAME="deepseek-v4-flash"
export OPENAI_MODEL="$MODEL_NAME"
export ASB_MODEL="$MODEL_NAME"
export ASB_JUDGE_MODEL="$MODEL_NAME"
export ASB_EMBEDDING_BACKEND="ollama"
export ASB_EMBEDDING_MODEL="nomic-embed-text"
export ASB_MEMORY_DB_SUFFIX="nomic-embed-text"
export ASB_OLLAMA_BASE_URL="http://localhost:11434"
```

Keep credentials in the shell environment or a private file outside the repository.

## 2. Prepare local embeddings

Start Ollama separately if it is not already running:

```bash
ollama serve
```

Then pull and test the embedding model:

```bash
ollama pull nomic-embed-text

python - <<'PY'
import os
from langchain_ollama import OllamaEmbeddings

client = OllamaEmbeddings(
    model=os.environ["ASB_EMBEDDING_MODEL"],
    base_url=os.environ["ASB_OLLAMA_BASE_URL"],
)
vector = client.embed_query("ASB embedding probe")
print("embedding_dimensions=", len(vector))
PY
```

Build compatible Chroma databases:

```bash
python scripts/rebuild_ollama_memory_db.py
```

## 3. Validate the provider and ASB path

```bash
python scripts/deepseek_smoke.py
python scripts/deepseek_auth_and_asb_smoke.py

export ASB_MAX_WORKERS=1
timeout 10m bash scripts/run_deepseek_full_reproduction.sh \
  --configs config/smoke_MP_deepseek.yml

bash scripts/run_deepseek_full_reproduction.sh --smoke-through-mp
```

## 4. Run the full reproduction

Choose concurrency for the available API quota:

```bash
export ASB_MAX_WORKERS=8
bash scripts/run_deepseek_full_reproduction.sh
```

The completed CSV and log outputs are written under `logs/`. A full `all` configuration contains 400 result rows plus its CSV header.

## 5. Summarize retained outputs

```bash
python - <<'PY'
from pathlib import Path
import csv

for path in sorted(Path("logs").glob("**/*deepseek_full.csv")):
    rows = list(csv.DictReader(path.open(errors="ignore")))
    total = len(rows)
    attack = sum(int(row.get("Attack Successful") or 0) for row in rows)
    task = sum(int(row.get("Original Task Successful") or 0) for row in rows)
    refused = sum(int(row.get("Refuse Result") or 0) for row in rows)
    print(path)
    print(f"  records={total} attack_success={attack} task_success={task} refused={refused}")
PY
```
