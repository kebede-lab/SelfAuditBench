#!/usr/bin/env bash

# Source this file from each terminal used for ASB or ConVerse runs.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "source scripts/runbook_helpers.sh; do not execute it" >&2
  exit 2
fi

sab_run() {
  local config="$1" backend="$2"
  case "$backend" in
    deepseek)
      test -n "${DEEPSEEK_API_KEY:-}" || { echo "missing DEEPSEEK_API_KEY" >&2; return 2; }
      export OPENAI_API_KEY="$DEEPSEEK_API_KEY"
      ;;
    qwen35)
      test -n "${QWEN_API_KEY:-}" || { echo "missing QWEN_API_KEY" >&2; return 2; }
      export OPENAI_API_KEY="$QWEN_API_KEY"
      ;;
    minimax-m27)
      test -n "${MINIMAX_API_KEY:-}" || { echo "missing MINIMAX_API_KEY" >&2; return 2; }
      export OPENAI_API_KEY="$MINIMAX_API_KEY"
      ;;
    ollama-gemma4)
      export OPENAI_API_KEY=ollama
      ;;
    *)
      echo "unknown backend: $backend" >&2
      return 2
      ;;
  esac
  test -f "$config" || { echo "missing tracked config: $config" >&2; return 2; }
  selfauditbench run replay --config "$config" --skip-paper-export
}

sab_closed_loop() {
  local config="$1"
  test -n "${DEEPSEEK_API_KEY:-}" || { echo "missing DEEPSEEK_API_KEY" >&2; return 2; }
  test -n "${QWEN_API_KEY:-}" || { echo "missing QWEN_API_KEY" >&2; return 2; }
  test -f "$config" || { echo "missing tracked config: $config" >&2; return 2; }
  selfauditbench run closed-loop --config "$config" --skip-paper-export
}

sab_check_run() {
  local run_dir="$1"
  selfauditbench report --run "$run_dir" &&
    selfauditbench verify --run "$run_dir"
}

sab_check_smoke() {
  local run_dir="$1"
  sab_check_run "$run_dir" || return
  python - "$run_dir" <<'PY'
import json
import sys
from pathlib import Path

from selfauditbench.evaluation.supplementary import normalize_run_gates

run = Path(sys.argv[1])
summary = json.loads((run / "supplementary_reliability.json").read_text(encoding="utf-8"))
gates = normalize_run_gates(summary)
print(json.dumps(gates, indent=2, sort_keys=True))
if not gates["backend_ready_for_full_run"]:
    raise SystemExit("smoke gate failed; do not promote this hosted backend")
PY
}

sab_check_closed_loop() {
  local run_dir="$1"
  sab_check_run "$run_dir" || return
  python - "$run_dir" <<'PY'
import json
import sys
from pathlib import Path

from selfauditbench.evaluation.supplementary import closed_loop_readiness_check

run = Path(sys.argv[1])
metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
print(json.dumps(metrics["closed_loop_recovery"], indent=2, sort_keys=True))
check, failures = closed_loop_readiness_check(run)
print(json.dumps({"closed_loop_readiness_check": check}, indent=2, sort_keys=True))

if failures:
    raise SystemExit(
        "closed-loop readiness check failed; exclude this run from comparisons "
        "and paper export:\n- "
        + "\n- ".join(failures)
    )
PY
}

sab_closed_loop_suite() {
  if (( $# == 0 || $# % 2 != 0 )); then
    echo "usage: sab_closed_loop_suite CONFIG RUN_DIR [CONFIG RUN_DIR ...]" >&2
    return 2
  fi

  local config run_dir label
  local -a passed=()
  local -a failed=()

  while (( $# )); do
    config="$1"
    run_dir="$2"
    shift 2
    label="$(basename "$config" .yaml)"

    printf '\n============================================================\n'
    printf 'Closed-loop condition: %s\n' "$label"
    printf '============================================================\n'

    if ! sab_closed_loop "$config"; then
      failed+=("$label: execution failed")
      echo "Continuing to the next closed-loop condition." >&2
      continue
    fi
    if ! sab_check_closed_loop "$run_dir"; then
      failed+=("$label: readiness check failed")
      echo "Continuing to the next closed-loop condition." >&2
      continue
    fi
    passed+=("$label")
  done

  printf '\n============================================================\n'
  printf 'Closed-loop batch summary\n'
  printf '============================================================\n'
  if (( ${#passed[@]} )); then
    printf 'PASSED: %s\n' "${passed[@]}"
  else
    echo "PASSED: none"
  fi
  if (( ${#failed[@]} )); then
    printf 'FAILED: %s\n' "${failed[@]}" >&2
    return 1
  fi
  echo "FAILED: none"
}
