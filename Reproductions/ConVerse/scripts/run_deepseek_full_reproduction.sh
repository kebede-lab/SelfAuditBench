#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export BASE_URL="${BASE_URL:-https://uni-api.cstcloud.cn/v1}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-$BASE_URL}"
export OPENAI_API_BASE="${OPENAI_API_BASE:-$BASE_URL}"
export CONVERSE_MODEL="${CONVERSE_MODEL:-${MODEL_NAME:-deepseek-v4-flash}}"
export CONVERSE_JUDGE_MODEL="${CONVERSE_JUDGE_MODEL:-$CONVERSE_MODEL}"
export CONVERSE_TIMEOUT="${CONVERSE_TIMEOUT:-600}"
export CONVERSE_REPETITIONS="${CONVERSE_REPETITIONS:-1}"
CONVERSE_RUN_MODE="full"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke)
      CONVERSE_RUN_MODE="smoke"
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: bash scripts/run_deepseek_full_reproduction.sh [--smoke]

Modes:
  default  Run the configured full ConVerse reproduction.
  --smoke  Run one tiny DeepSeek-backed ConVerse case before the full run.
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
RUN_ID="${CONVERSE_RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
STATUS_DIR="$ROOT/logs/_run_status"
STATUS_LOG="$STATUS_DIR/deepseek_full_${RUN_ID}.log"
mkdir -p "$STATUS_DIR"

log_status() {
  echo "$*" | tee -a "$STATUS_LOG"
}

run_case() {
  local use_case="$1"
  local persona="$2"
  local sim_type="$3"
  local mode_flag="$4"
  local mode_name="$5"
  local logs_folder="$6"
  shift 6
  log_status ""
  log_status "==== use_case=$use_case persona=$persona sim_type=$sim_type mode=$mode_name at $(date -Is) ===="
  "$PYTHON" main.py \
    --provider openai \
    --llm_name "$CONVERSE_MODEL" \
    --judge_provider openai \
    --judge_llm_name "$CONVERSE_JUDGE_MODEL" \
    --use_case "$use_case" \
    --persona_id "$persona" \
    --simulation_type "$sim_type" \
    "$mode_flag" \
    --repetitions "$CONVERSE_REPETITIONS" \
    --simulation_timeout "$CONVERSE_TIMEOUT" \
    --logs_folder "$logs_folder" \
    "$@"
  log_status "==== finished use_case=$use_case persona=$persona sim_type=$sim_type mode=$mode_name at $(date -Is) ===="
}

log_status "ConVerse DeepSeek full reproduction"
log_status "root=$ROOT"
log_status "base_url=$BASE_URL"
log_status "model=$CONVERSE_MODEL"
log_status "judge_model=$CONVERSE_JUDGE_MODEL"
log_status "python=$PYTHON"
log_status "run_mode=$CONVERSE_RUN_MODE"
log_status "status_log=$STATUS_LOG"
log_status "started=$(date -Is)"

"$PYTHON" scripts/deepseek_smoke.py 2>&1 | tee -a "$STATUS_LOG"

if [[ "$CONVERSE_RUN_MODE" == "smoke" ]]; then
  export CONVERSE_TIMEOUT="${CONVERSE_SMOKE_TIMEOUT:-300}"
  export CONVERSE_REPETITIONS="1"
  run_case "travel_planning" "1" "benign_easy" "--baseline_mode" "baseline" "logs/_smoke" 
  log_status ""
  log_status "completed=$(date -Is)"
  log_status "Smoke results are under logs/_smoke/"
  exit 0
fi

USE_CASES=(${CONVERSE_USE_CASES:-travel_planning real_estate insurance})
PERSONAS=(${CONVERSE_PERSONAS:-1 2 3 4})
SIM_TYPES=(${CONVERSE_SIM_TYPES:-security privacy benign_easy})
MODES=(${CONVERSE_MODES:-baseline})

for use_case in "${USE_CASES[@]}"; do
  for persona in "${PERSONAS[@]}"; do
    for sim_type in "${SIM_TYPES[@]}"; do
      for mode in "${MODES[@]}"; do
        if [[ "$mode" == "baseline" ]]; then
          run_case "$use_case" "$persona" "$sim_type" "--baseline_mode" "baseline" "logs" --run_all_attacks
        elif [[ "$mode" == "taskconfined" ]]; then
          run_case "$use_case" "$persona" "$sim_type" "--taskconfined_mode" "taskconfined" "logs" --run_all_attacks
        else
          echo "ERROR: unknown CONVERSE_MODES entry: $mode" >&2
          exit 3
        fi
      done
    done
  done
done

log_status ""
log_status "completed=$(date -Is)"
log_status "Results are under logs/"
