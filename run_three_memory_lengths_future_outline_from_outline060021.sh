#!/usr/bin/env bash
# 复用 shortdrama_full_20260919_060021 的逐集大纲，并行生成三组 memory 版本完整剧本。
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SOURCE_DIR="$SCRIPT_DIR/output/shortdrama_full_20260919_060021"
PYTHON_BIN="${PYTHON_BIN:-/inspire/hdd/global_user/hesiyang-CZXS25210137/anaconda3/bin/python3}"
BATCH_ID="${BATCH_ID:-$(date +%Y%m%d_%H%M%S)}"

export DRAMA_LLM_BASE_URL="${DRAMA_LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRAMA_LLM_MODEL="${DRAMA_LLM_MODEL:-qwen-local}"
export DRAMA_LLM_THINKING="${DRAMA_LLM_THINKING:-0}"
export DRAMA_LLM_TIMEOUT="${DRAMA_LLM_TIMEOUT:-0}"
export DRAMA_LLM_MAX_TOKENS="${DRAMA_LLM_MAX_TOKENS:-0}"
export DRAMA_DISABLE_PLOT_RETRIEVAL=1
export DRAMA_ADJUST_WORD_COUNT=false
export DRAMA_ADJUST_COHERENCE=false
export DRAMA_SUMMARY_MEMORY_BASELINE=false
export DRAMA_FULL_HISTORY_BASELINE=false
export DRAMA_FUTURE_OUTLINE_CONSISTENCY="${DRAMA_FUTURE_OUTLINE_CONSISTENCY:-true}"
export DRAMA_SUBTREE_MEMORY_LIMIT="${DRAMA_SUBTREE_MEMORY_LIMIT:-10}"
export DRAMA_STATE_MEMORY_BUDGET="${DRAMA_STATE_MEMORY_BUDGET:-6000}"
export DRAMA_STATE_MEMORY_LIMIT="${DRAMA_STATE_MEMORY_LIMIT:-20}"
export PYTHONUNBUFFERED=1

if [[ ! -d "$SOURCE_DIR/04_episode_outline" ]]; then
    echo "找不到逐集大纲目录：$SOURCE_DIR/04_episode_outline" >&2
    exit 1
fi

"$PYTHON_BIN" tools/check_drama_dependencies.py

run_generation() {
    local min_words="$1"
    local max_words="$2"
    local run_id="shortdrama_memory_futureoutline_${min_words}_${max_words}_outlinefrom060021_${BATCH_ID}"
    local out_dir="$SCRIPT_DIR/output/$run_id"

    mkdir -p "$out_dir"
    {
        echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] 启动 memory ${min_words}～${max_words}字/集"
        echo "大纲来源：$SOURCE_DIR"
        echo "输出目录：$out_dir"
        echo "后续核心情节连续性校验：$DRAMA_FUTURE_OUTLINE_CONSISTENCY"
        "$PYTHON_BIN" -u service/drama_by_creativity/tests/run_from_episode_outline.py \
            --source-dir "$SOURCE_DIR" \
            --output-dir "$out_dir" \
            --story-id "$run_id" \
            --start-episode 1 \
            --end-episode 60 \
            --min-word-count "$min_words" \
            --max-word-count "$max_words" \
            --future-outline-consistency "$DRAMA_FUTURE_OUTLINE_CONSISTENCY"
    } 2>&1 | tee -a "$out_dir/generation.log"
}

declare -a PIDS=()
declare -a LABELS=()

run_generation 1000 1400 &
PIDS+=("$!")
LABELS+=("memory 1000～1400")

run_generation 1500 2000 &
PIDS+=("$!")
LABELS+=("memory 1500～2000")

run_generation 2000 2500 &
PIDS+=("$!")
LABELS+=("memory 2000～2500")

echo "已并行启动三组生成，批次号：$BATCH_ID"
for index in "${!PIDS[@]}"; do
    echo "  PID ${PIDS[$index]}：${LABELS[$index]}"
done

failed=0
for index in "${!PIDS[@]}"; do
    if wait "${PIDS[$index]}"; then
        echo "[完成] ${LABELS[$index]}"
    else
        status=$?
        echo "[失败] ${LABELS[$index]}，退出码：$status" >&2
        failed=1
    fi
done

if (( failed != 0 )); then
    echo "至少一组生成失败；其他任务已等待结束。" >&2
    exit 1
fi

echo "三组剧本均已生成完成，批次号：$BATCH_ID"
echo "输出目录前缀：$SCRIPT_DIR/output/shortdrama_memory_futureoutline_*_outlinefrom060021_${BATCH_ID}"
