#!/usr/bin/env bash
set -euo pipefail

# ASB full reproduction through the official DeepSeek OpenAI-compatible endpoint.
# Server-safe defaults:
# - sequential config execution
# - foreground child jobs with exit-code checks
# - bounded per-config agent concurrency via ASB_MAX_WORKERS
# - status log under logs/_run_status/

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export BASE_URL="${BASE_URL:-https://api.deepseek.com/v1}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-$BASE_URL}"
export OPENAI_API_BASE="${OPENAI_API_BASE:-$BASE_URL}"
export ASB_MODEL="${ASB_MODEL:-deepseek-v4-flash}"
export ASB_JUDGE_MODEL="${ASB_JUDGE_MODEL:-$ASB_MODEL}"
export ASB_FOREGROUND=1
export ASB_MAX_WORKERS="${ASB_MAX_WORKERS:-16}"
ASB_RUN_MODE="full"
ASB_CONFIGS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke-through-mp)
      ASB_RUN_MODE="smoke-through-mp"
      shift
      ;;
    --configs)
      ASB_RUN_MODE="custom"
      ASB_CONFIGS="${2:-}"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage: bash scripts/run_deepseek_full_reproduction.sh [--smoke-through-mp] [--configs cfg1,cfg2,...]

Modes:
  default             Run the full ASB reproduction suite.
  --smoke-through-mp  Run tiny clean -> DPI -> OPI -> MP configs using test data.
  --configs           Run an explicit comma-separated config list.
EOF
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "ERROR: OPENAI_API_KEY is not set in the current shell." >&2
  exit 2
fi

PYTHON="${PYTHON:-python}"
RUN_ID="${ASB_RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
STATUS_DIR="$ROOT/logs/_run_status"
STATUS_LOG="$STATUS_DIR/deepseek_full_${RUN_ID}.log"
mkdir -p "$STATUS_DIR"

log_status() {
  echo "$*" | tee -a "$STATUS_LOG"
}

run_cfg() {
  local cfg="$1"
  log_status ""
  log_status "==== running $cfg at $(date -Is) ===="
  "$PYTHON" scripts/agent_attack.py --cfg_path "$cfg"
  log_status "==== finished $cfg at $(date -Is) ===="
}

run_pot_cfg() {
  local cfg="$1"
  log_status ""
  log_status "==== running $cfg at $(date -Is) ===="
  "$PYTHON" scripts/agent_attack_pot.py --cfg_path "$cfg"
  log_status "==== finished $cfg at $(date -Is) ===="
}

log_status "ASB DeepSeek official full reproduction"
log_status "root=$ROOT"
log_status "base_url=$BASE_URL"
log_status "model=$ASB_MODEL"
log_status "judge_model=$ASB_JUDGE_MODEL"
log_status "embedding_backend=${ASB_EMBEDDING_BACKEND:-ollama}"
log_status "embedding_base_url=${ASB_OLLAMA_BASE_URL:-${OLLAMA_HOST:-http://localhost:11434}}"
log_status "embedding_model=${ASB_EMBEDDING_MODEL:-nomic-embed-text}"
log_status "memory_db_suffix=${ASB_MEMORY_DB_SUFFIX:-${ASB_EMBEDDING_MODEL:-nomic-embed-text}}"
log_status "python=$PYTHON"
log_status "ASB_MAX_WORKERS=$ASB_MAX_WORKERS"
log_status "run_mode=$ASB_RUN_MODE"
log_status "status_log=$STATUS_LOG"
log_status "started=$(date -Is)"

"$PYTHON" scripts/deepseek_smoke.py 2>&1 | tee -a "$STATUS_LOG"

case "$ASB_RUN_MODE" in
  full)
    CONFIGS=(
      config/clean_deepseek_full.yml
      config/DPI_deepseek_full.yml
      config/OPI_deepseek_full.yml
      config/MP_deepseek_full.yml
      config/DPI_MP_deepseek_full.yml
      config/OPI_MP_deepseek_full.yml
      config/DPI_OPI_deepseek_full.yml
      config/mixed_deepseek_full.yml
    )
    for cfg in "${CONFIGS[@]}"; do
      run_cfg "$cfg"
    done
    run_pot_cfg config/POT_deepseek_full.yml
    ;;
  smoke-through-mp)
    CONFIGS=(
      config/smoke_clean_deepseek.yml
      config/smoke_DPI_deepseek.yml
      config/smoke_OPI_deepseek.yml
      config/smoke_MP_deepseek.yml
    )
    for cfg in "${CONFIGS[@]}"; do
      run_cfg "$cfg"
    done
    ;;
  custom)
    if [[ -z "$ASB_CONFIGS" ]]; then
      echo "ERROR: --configs requires a comma-separated config list" >&2
      exit 2
    fi
    IFS=',' read -r -a CONFIGS <<< "$ASB_CONFIGS"
    for cfg in "${CONFIGS[@]}"; do
      run_cfg "$cfg"
    done
    ;;
esac

log_status ""
log_status "completed=$(date -Is)"
log_status "Result CSV/log files are under logs/*/$ASB_MODEL/"
