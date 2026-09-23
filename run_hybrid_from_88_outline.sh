#!/usr/bin/env bash
# 从既有88分逐集大纲开始，运行需求树叙事记忆 + 人物/关系/资产状态记忆。
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SOURCE_DIR="${SOURCE_DIR:-$SCRIPT_DIR/../drama_operator_new_v9_future5_state2_complete_simple/output/qwen36_27b_eight_fields_demo_20260916_060508_407704}"
RUN_ID="${RUN_ID:-shortdrama_state_88_$(date +%Y%m%d_%H%M%S)}"
export DRAMA_OUTPUT_DIR="${DRAMA_OUTPUT_DIR:-$SCRIPT_DIR/output/$RUN_ID}"
export DRAMA_SUMMARY_MEMORY_BASELINE=false
export DRAMA_FUTURE_OUTLINE_CONSISTENCY="${DRAMA_FUTURE_OUTLINE_CONSISTENCY:-false}"
export DRAMA_OUTLINE_ONLY=0
export DRAMA_DISABLE_PLOT_RETRIEVAL=1
export DRAMA_ADJUST_WORD_COUNT="${DRAMA_ADJUST_WORD_COUNT:-false}"
export DRAMA_ADJUST_COHERENCE="${DRAMA_ADJUST_COHERENCE:-false}"
export DRAMA_SUBTREE_MEMORY_LIMIT="${DRAMA_SUBTREE_MEMORY_LIMIT:-10}"
export DRAMA_STATE_MEMORY_BUDGET="${DRAMA_STATE_MEMORY_BUDGET:-6000}"
export DRAMA_STATE_MEMORY_LIMIT="${DRAMA_STATE_MEMORY_LIMIT:-20}"
export DRAMA_LLM_BASE_URL="${DRAMA_LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRAMA_LLM_MODEL="${DRAMA_LLM_MODEL:-qwen-local}"
export DRAMA_LLM_MAX_TOKENS="${DRAMA_LLM_MAX_TOKENS:-0}"
export DRAMA_LLM_THINKING="${DRAMA_LLM_THINKING:-0}"
export DRAMA_LLM_TIMEOUT="${DRAMA_LLM_TIMEOUT:-0}"
export PYTHONUNBUFFERED=1
GEN_PYTHON="${PYTHON_BIN:-/inspire/hdd/global_user/hesiyang-CZXS25210137/anaconda3/bin/python3}"

"$GEN_PYTHON" tools/check_drama_dependencies.py
mkdir -p "$DRAMA_OUTPUT_DIR"
printf '大纲来源：%s\n输出目录：%s\n记忆：需求树叙事记忆 + 人物/关系/资产当前状态\n状态检索上限：%s条，%s字符\n' \
  "$SOURCE_DIR" "$DRAMA_OUTPUT_DIR" "$DRAMA_STATE_MEMORY_LIMIT" "$DRAMA_STATE_MEMORY_BUDGET"
printf '后续逐集核心情节连续性校验：%s\n' "$DRAMA_FUTURE_OUTLINE_CONSISTENCY"

"$GEN_PYTHON" -u service/drama_by_creativity/tests/run_from_episode_outline.py \
  --source-dir "$SOURCE_DIR" \
  --output-dir "$DRAMA_OUTPUT_DIR" \
  --story-id "$RUN_ID" \
  "$@" 2>&1 | tee -a "$DRAMA_OUTPUT_DIR/generation.log"
