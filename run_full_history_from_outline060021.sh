#!/usr/bin/env bash
# 复用 shortdrama_full_20260919_060021 的逐集大纲，
# 仅以前序所有完整剧本作为历史记忆，重新生成第 1～60 集。
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SOURCE_DIR="$SCRIPT_DIR/output/shortdrama_full_20260919_060021"
RUN_ID="${RUN_ID:-shortdrama_full_history_outlinefrom060021_$(date +%Y%m%d_%H%M%S)}"
OUT_DIR="${DRAMA_OUTPUT_DIR:-$SCRIPT_DIR/output/$RUN_ID}"
PYTHON_BIN="${PYTHON_BIN:-/inspire/hdd/global_user/hesiyang-CZXS25210137/anaconda3/bin/python3}"

export DRAMA_OUTPUT_DIR="$OUT_DIR"
export DRAMA_FULL_HISTORY_BASELINE=true
export DRAMA_SUMMARY_MEMORY_BASELINE=false
export DRAMA_DISABLE_PLOT_RETRIEVAL=1
export DRAMA_ADJUST_WORD_COUNT=false
export DRAMA_ADJUST_COHERENCE=false
export DRAMA_LLM_BASE_URL="${DRAMA_LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRAMA_LLM_MODEL="${DRAMA_LLM_MODEL:-qwen-local}"
export DRAMA_LLM_THINKING="${DRAMA_LLM_THINKING:-0}"
export DRAMA_LLM_TIMEOUT="${DRAMA_LLM_TIMEOUT:-0}"
export DRAMA_LLM_MAX_TOKENS="${DRAMA_LLM_MAX_TOKENS:-0}"
export PYTHONUNBUFFERED=1

if [[ ! -d "$SOURCE_DIR/04_episode_outline" ]]; then
    echo "找不到逐集大纲目录：$SOURCE_DIR/04_episode_outline" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"

echo "逐集大纲来源: $SOURCE_DIR"
echo "输出目录: $OUT_DIR"
echo "vLLM 接口: $DRAMA_LLM_BASE_URL"
echo "模型服务名称: $DRAMA_LLM_MODEL"
echo "记忆方式: 前序所有完整剧本（唯一历史记忆）"
echo "字数调整: 关闭"
echo "衔接调整: 关闭"

"$PYTHON_BIN" -u service/drama_by_creativity/tests/run_from_episode_outline.py \
    --source-dir "$SOURCE_DIR" \
    --output-dir "$OUT_DIR" \
    --story-id "$RUN_ID" \
    --start-episode 1 \
    --end-episode 60 \
    --baseline \
    "$@" \
    2>&1 | tee "$OUT_DIR/generation.log"
