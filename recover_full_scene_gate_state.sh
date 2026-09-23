#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/inspire/qb-ilm/project/exploration-topic/wangqiqi-CZXS25210124/anaconda3/envs/qwen36-vllm/bin/python}"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1
cd "$SCRIPT_DIR"
exec "$PYTHON_BIN" tools/recover_full_scene_gate_state.py "$@"
