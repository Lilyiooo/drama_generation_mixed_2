#!/usr/bin/env bash
# 使用本地 vLLM，从创意开始生成 60 集组合记忆版完整剧本。
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RUN_ID="${RUN_ID:-shortdrama_full_$(date +%Y%m%d_%H%M%S)}"
export DRAMA_OUTPUT_DIR="${DRAMA_OUTPUT_DIR:-$SCRIPT_DIR/output/$RUN_ID}"
export DRAMA_DISABLE_PLOT_RETRIEVAL=1
export DRAMA_SUMMARY_MEMORY_BASELINE=false
export DRAMA_FUTURE_OUTLINE_CONSISTENCY="${DRAMA_FUTURE_OUTLINE_CONSISTENCY:-false}"
export DRAMA_STATE_MEMORY_LIMIT="${DRAMA_STATE_MEMORY_LIMIT:-20}"
export DRAMA_STATE_MEMORY_BUDGET="${DRAMA_STATE_MEMORY_BUDGET:-6000}"
export DRAMA_LLM_BASE_URL="${DRAMA_LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
# 使用 vLLM 的 served-model-name，与 test_vllm.py 保持一致。
export DRAMA_LLM_MODEL="${DRAMA_LLM_MODEL:-qwen-local}"
export DRAMA_LLM_THINKING="${DRAMA_LLM_THINKING:-0}"
export DRAMA_LLM_TIMEOUT="${DRAMA_LLM_TIMEOUT:-0}"
# 与 test_vllm.py 默认行为一致，由 vLLM 管理剩余输出预算。
export DRAMA_LLM_MAX_TOKENS="${DRAMA_LLM_MAX_TOKENS:-0}"
export PYTHON_BIN="${PYTHON_BIN:-/inspire/hdd/global_user/hesiyang-CZXS25210137/anaconda3/bin/python3}"
export PYTHONUNBUFFERED=1

echo "vLLM 接口: $DRAMA_LLM_BASE_URL"
echo "模型服务名称: $DRAMA_LLM_MODEL"
echo "运行 ID: $RUN_ID"
echo "状态检索上限: $DRAMA_STATE_MEMORY_LIMIT 条，$DRAMA_STATE_MEMORY_BUDGET 字符"
echo "后续逐集核心情节连续性校验: $DRAMA_FUTURE_OUTLINE_CONSISTENCY"
echo "输出目录: $DRAMA_OUTPUT_DIR"
exec bash "$SCRIPT_DIR/run_60ep.sh" --story_id "$RUN_ID" "$@"
