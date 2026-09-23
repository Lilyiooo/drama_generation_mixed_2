#!/usr/bin/env bash
# 从创意开始生成60集；剧本阶段仅使用此前全部完整剧本作为历史记忆。
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RUN_ID="${RUN_ID:-shortdrama_full_history_$(date +%Y%m%d_%H%M%S)}"
export DRAMA_OUTPUT_DIR="${DRAMA_OUTPUT_DIR:-$SCRIPT_DIR/output/$RUN_ID}"
export DRAMA_FULL_HISTORY_BASELINE=true
export DRAMA_SUMMARY_MEMORY_BASELINE=false
export DRAMA_DISABLE_PLOT_RETRIEVAL=1
export DRAMA_LLM_BASE_URL="${DRAMA_LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRAMA_LLM_MODEL="${DRAMA_LLM_MODEL:-qwen-local}"
export DRAMA_LLM_THINKING="${DRAMA_LLM_THINKING:-0}"
export DRAMA_LLM_TIMEOUT="${DRAMA_LLM_TIMEOUT:-0}"
export DRAMA_LLM_MAX_TOKENS="${DRAMA_LLM_MAX_TOKENS:-0}"
export PYTHON_BIN="${PYTHON_BIN:-/inspire/hdd/global_user/hesiyang-CZXS25210137/anaconda3/bin/python3}"
export PYTHONUNBUFFERED=1

echo "vLLM 接口: $DRAMA_LLM_BASE_URL"
echo "模型服务名称: $DRAMA_LLM_MODEL"
echo "记忆方式: 前序所有完整剧本（不生成需求树，不抽取状态记忆）"
echo "输出目录: $DRAMA_OUTPUT_DIR"

exec bash "$SCRIPT_DIR/run_60ep.sh" \
    --story_id "$RUN_ID" \
    --full-history-baseline \
    "$@"
