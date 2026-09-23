#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUN="${RUN:-R01}"
MAX_ROUNDS="${MAX_ROUNDS:-20}"
RECOVERY_WORKERS="${RECOVERY_WORKERS:-1}"
GENERATION_WORKERS="${GENERATION_WORKERS:-1}"

cd "$SCRIPT_DIR"
mkdir -p logs

for ((round = 1; round <= MAX_ROUNDS; round++)); do
  echo "[scene-gate-v2] round=${round}/${MAX_ROUNDS} run=${RUN} recovery"
  if ! bash recover_scene_gate_v2.sh recover --run "$RUN" --workers "$RECOVERY_WORKERS" --execute-api; then
    echo "[scene-gate-v2] recovery failed; retrying after 5 seconds"
    sleep 5
    continue
  fi

  echo "[scene-gate-v2] round=${round}/${MAX_ROUNDS} run=${RUN} generation"
  if bash scene_gate_v2_study.sh generate --run "$RUN" --workers "$GENERATION_WORKERS" --execute-api; then
    bash scene_gate_v2_study.sh status --all-runs
    exit 0
  fi

  echo "[scene-gate-v2] generation stopped; a new recoverable gate may exist"
done

echo "[scene-gate-v2] exhausted ${MAX_ROUNDS} recovery rounds" >&2
exit 1
