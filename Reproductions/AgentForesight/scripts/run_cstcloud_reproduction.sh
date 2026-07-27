#!/usr/bin/env bash
set -euo pipefail

: "${OPENAI_API_KEY:?OPENAI_API_KEY must be set in the current shell.}"

export AGENTFORESIGHT_BASE_URL="${AGENTFORESIGHT_BASE_URL:-${BASE_URL:-${OPENAI_BASE_URL:-https://uni-api.cstcloud.cn/v1}}}"
export AGENTFORESIGHT_MODEL="${AGENTFORESIGHT_MODEL:-${MODEL_NAME:-deepseek-v4-flash}}"
export AGENTFORESIGHT_DATA_DIR="${AGENTFORESIGHT_DATA_DIR:-./data}"
export AGENTFORESIGHT_OUTPUT_DIR="${AGENTFORESIGHT_OUTPUT_DIR:-./outputs/cstcloud-${AGENTFORESIGHT_MODEL}}"

mkdir -p "$AGENTFORESIGHT_OUTPUT_DIR"

python -m inference.infer_api \
  --model "$AGENTFORESIGHT_MODEL" \
  --base-url "$AGENTFORESIGHT_BASE_URL" \
  --data-dir "$AGENTFORESIGHT_DATA_DIR" \
  --output-dir "$AGENTFORESIGHT_OUTPUT_DIR" \
  "$@"
