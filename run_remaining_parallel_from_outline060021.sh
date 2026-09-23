#!/usr/bin/env bash
# 并行完成 outlinefrom060021 批次尚未完成的三组实验。
# 已完成的 baseline 1500～2000 不重复生成。
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SOURCE_DIR="$SCRIPT_DIR/output/shortdrama_full_20260919_060021"
PYTHON_BIN="${PYTHON_BIN:-/inspire/hdd/global_user/hesiyang-CZXS25210137/anaconda3/bin/python3}"
EXISTING_MEMORY_RUN_ID="shortdrama_memory_1500_2000_outlinefrom060021_20260919_090316"
PARALLEL_BATCH_ID="${PARALLEL_BATCH_ID:-$(date +%Y%m%d_%H%M%S)}"
CONTINUOUS_LOAD_SCRIPT="/inspire/hdd/global_user/hesiyang-CZXS25210137/localmodel_vllmdemo/continuous_load.sh"

export DRAMA_LLM_BASE_URL="${DRAMA_LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRAMA_LLM_MODEL="${DRAMA_LLM_MODEL:-qwen-local}"
export DRAMA_LLM_THINKING="${DRAMA_LLM_THINKING:-0}"
export DRAMA_LLM_TIMEOUT="${DRAMA_LLM_TIMEOUT:-0}"
export DRAMA_LLM_MAX_TOKENS="${DRAMA_LLM_MAX_TOKENS:-0}"
export DRAMA_DISABLE_PLOT_RETRIEVAL=1
export DRAMA_ADJUST_WORD_COUNT=false
export DRAMA_ADJUST_COHERENCE=false
export DRAMA_SUMMARY_MEMORY_BASELINE=false
export DRAMA_SUBTREE_MEMORY_LIMIT="${DRAMA_SUBTREE_MEMORY_LIMIT:-10}"
export DRAMA_STATE_MEMORY_BUDGET="${DRAMA_STATE_MEMORY_BUDGET:-6000}"
export DRAMA_STATE_MEMORY_LIMIT="${DRAMA_STATE_MEMORY_LIMIT:-20}"
export PYTHONUNBUFFERED=1

if [[ ! -d "$SOURCE_DIR/04_episode_outline" ]]; then
    echo "找不到逐集大纲目录：$SOURCE_DIR/04_episode_outline" >&2
    exit 1
fi
if [[ ! -d "$SCRIPT_DIR/output/$EXISTING_MEMORY_RUN_ID" ]]; then
    echo "找不到待续跑的 memory 1500～2000 输出：$SCRIPT_DIR/output/$EXISTING_MEMORY_RUN_ID" >&2
    exit 1
fi
if [[ ! -f "$CONTINUOUS_LOAD_SCRIPT" ]]; then
    echo "找不到占卡脚本：$CONTINUOUS_LOAD_SCRIPT" >&2
    exit 1
fi

"$PYTHON_BIN" tools/check_drama_dependencies.py

run_generation() {
    local label="$1"
    local run_id="$2"
    local mode="$3"
    local min_words="$4"
    local max_words="$5"
    local start_episode="$6"
    local out_dir="$SCRIPT_DIR/output/$run_id"

    mkdir -p "$out_dir"
    export DRAMA_OUTPUT_DIR="$out_dir"

    local -a command=(
        "$PYTHON_BIN" -u service/drama_by_creativity/tests/run_from_episode_outline.py
        --source-dir "$SOURCE_DIR"
        --output-dir "$out_dir"
        --story-id "$run_id"
        --start-episode "$start_episode"
        --end-episode 60
        --min-word-count "$min_words"
        --max-word-count "$max_words"
    )

    if [[ "$mode" == "baseline" ]]; then
        export DRAMA_FULL_HISTORY_BASELINE=true
        command+=(--baseline)
    else
        export DRAMA_FULL_HISTORY_BASELINE=false
    fi

    {
        echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] 启动：$label"
        echo "大纲来源：$SOURCE_DIR"
        echo "输出目录：$out_dir"
        echo "生成范围：第${start_episode}～60集"
        echo "每集长度：${min_words}～${max_words}字"
        "${command[@]}"
    } 2>&1 | tee -a "$out_dir/generation.log"
}

MEMORY_1500_ID="$EXISTING_MEMORY_RUN_ID"
BASELINE_2000_ID="shortdrama_baseline_2000_2500_outlinefrom060021_${PARALLEL_BATCH_ID}"
MEMORY_2000_ID="shortdrama_memory_2000_2500_outlinefrom060021_${PARALLEL_BATCH_ID}"

declare -a PIDS=()
declare -a LABELS=()

# 第25集正文虽已保存，但其状态更新失败。重跑第25集可同时覆盖正文、需求树记忆和状态记忆，随后继续到第60集。
run_generation "memory 1500～2000（从第25集重新对齐后续跑）" \
    "$MEMORY_1500_ID" memory 1500 2000 25 &
PIDS+=("$!")
LABELS+=("memory 1500～2000")

run_generation "baseline 2000～2500" \
    "$BASELINE_2000_ID" baseline 2000 2500 1 &
PIDS+=("$!")
LABELS+=("baseline 2000～2500")

run_generation "memory 2000～2500" \
    "$MEMORY_2000_ID" memory 2000 2500 1 &
PIDS+=("$!")
LABELS+=("memory 2000～2500")

echo "已并行启动三组任务："
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
    echo "至少一组生成失败；已等待其他任务结束，不启动占卡脚本。" >&2
    exit 1
fi

echo "三组生成均已完成，开始运行占卡脚本：$CONTINUOUS_LOAD_SCRIPT"
exec bash "$CONTINUOUS_LOAD_SCRIPT"
