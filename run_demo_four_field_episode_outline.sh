#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export DRAMA_LLM_BASE_URL="${DRAMA_LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRAMA_LLM_MODEL="${DRAMA_LLM_MODEL:-qwen-local}"
export DRAMA_LLM_MAX_TOKENS="${DRAMA_LLM_MAX_TOKENS:-0}"
export DRAMA_LLM_THINKING="${DRAMA_LLM_THINKING:-0}"
export DRAMA_LLM_TIMEOUT="${DRAMA_LLM_TIMEOUT:-0}"
export DRAMA_DISABLE_PLOT_RETRIEVAL=1
export PYTHONUNBUFFERED=1
exec "${PYTHON_BIN:-/inspire/hdd/global_user/hesiyang-CZXS25210137/anaconda3/bin/python3}" tools/demo_four_field_episode_outline.py "$@"
