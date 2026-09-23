#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RUN_ID="${RUN_ID:-mixed_state_hybrid_gate_$(date +%Y%m%d_%H%M%S)}"
export DRAMA_OUTPUT_DIR="${DRAMA_OUTPUT_DIR:-$SCRIPT_DIR/output/$RUN_ID}"
export DRAMA_STATE_LIFECYCLE_HYBRID=0
export DRAMA_SCENE_STATE_GATE="${DRAMA_SCENE_STATE_GATE:-enforce}"
export DRAMA_SCENE_GATE_POLICY="${DRAMA_SCENE_GATE_POLICY:-conservative_v1}"
export DRAMA_STATE_MEMORY_LIMIT="${DRAMA_STATE_MEMORY_LIMIT:-20}"
export DRAMA_STATE_MEMORY_BUDGET="${DRAMA_STATE_MEMORY_BUDGET:-6000}"
export DRAMA_DISABLE_PLOT_RETRIEVAL="${DRAMA_DISABLE_PLOT_RETRIEVAL:-1}"
export DRAMA_SUMMARY_MEMORY_BASELINE=false
export DRAMA_FULL_HISTORY_BASELINE=false
export DRAMA_LLM_BASE_URL="${DRAMA_LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRAMA_LLM_MODEL="${DRAMA_LLM_MODEL:-Qwen3.6-27B}"
export DRAMA_LLM_THINKING="${DRAMA_LLM_THINKING:-0}"
export DRAMA_LLM_TIMEOUT="${DRAMA_LLM_TIMEOUT:-0}"
export DRAMA_LLM_MAX_TOKENS="${DRAMA_LLM_MAX_TOKENS:-0}"
export PYTHON_BIN="${PYTHON_BIN:-/inspire/qb-ilm/project/exploration-topic/wangqiqi-CZXS25210124/anaconda3/envs/qwen36-vllm/bin/python}"
export PYTHONUNBUFFERED=1

echo "运行目录: $SCRIPT_DIR"
echo "运行 ID: $RUN_ID"
echo "输出目录: $DRAMA_OUTPUT_DIR"
echo "模型接口: $DRAMA_LLM_BASE_URL"
echo "模型名称: $DRAMA_LLM_MODEL"
echo "新版 StructuredStateMemory + Hybrid: enabled"
echo "状态检索上限: $DRAMA_STATE_MEMORY_LIMIT 条 / $DRAMA_STATE_MEMORY_BUDGET 字符"
echo "Scene Gate: $DRAMA_SCENE_STATE_GATE"
echo "Scene Gate 策略: $DRAMA_SCENE_GATE_POLICY"

exec bash "$SCRIPT_DIR/run_60ep.sh" --story_id "$RUN_ID" "$@"
