#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/inspire/qb-ilm/project/exploration-topic/wangqiqi-CZXS25210124/anaconda3/envs/qwen36-vllm/bin/python}"

export PYTHONUNBUFFERED=1
export DRAMA_LLM_BASE_URL="${DRAMA_LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRAMA_LLM_API_KEY="${DRAMA_LLM_API_KEY:-EMPTY}"
export DRAMA_EVAL_BASE_URL="${DRAMA_EVAL_BASE_URL:-http://127.0.0.1:8001/v1}"
export DRAMA_EVAL_API_KEY="${DRAMA_EVAL_API_KEY:-EMPTY}"
export DRAMA_EVAL_MODEL="Qwen3.8-27B"
export DRAMA_EVAL_TEMPERATURE="0"
export DRAMA_EVAL_ENABLE_THINKING="false"

exec "$PYTHON_BIN" "$ROOT/tools/outline_history_baseline.py" "$@"
