#!/usr/bin/env bash
# 使用 shortdrama_full_20260919_060021 的同一份逐集大纲，顺序生成四组完整剧本：
#   1. 1500～2000字，前序完整剧本 baseline
#   2. 1500～2000字，需求树 + 状态记忆
#   3. 2000～2500字，前序完整剧本 baseline
#   4. 2000～2500字，需求树 + 状态记忆
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
export DRAMA_SUBTREE_MEMORY_LIMIT="${DRAMA_SUBTREE_MEMORY_LIMIT:-10}"
export DRAMA_STATE_MEMORY_BUDGET="${DRAMA_STATE_MEMORY_BUDGET:-6000}"
export DRAMA_STATE_MEMORY_LIMIT="${DRAMA_STATE_MEMORY_LIMIT:-20}"
export PYTHONUNBUFFERED=1

if [[ ! -d "$SOURCE_DIR/04_episode_outline" ]]; then
    echo "找不到逐集大纲目录：$SOURCE_DIR/04_episode_outline" >&2
    exit 1
fi

"$PYTHON_BIN" tools/check_drama_dependencies.py

run_group() {
    local mode="$1"
    local min_words="$2"
    local max_words="$3"
    local mode_label baseline_flag

    if [[ "$mode" == "baseline" ]]; then
        mode_label="baseline"
        baseline_flag="--baseline"
        export DRAMA_FULL_HISTORY_BASELINE=true
    else
        mode_label="memory"
        baseline_flag=""
        export DRAMA_FULL_HISTORY_BASELINE=false
    fi

    local run_id="shortdrama_${mode_label}_${min_words}_${max_words}_outlinefrom060021_${BATCH_ID}"
    local out_dir="$SCRIPT_DIR/output/$run_id"
    mkdir -p "$out_dir"
    export DRAMA_OUTPUT_DIR="$out_dir"

    echo
    echo "============================================================"
    echo "开始生成：$mode_label，${min_words}～${max_words}字/集"
    echo "大纲来源：$SOURCE_DIR"
    echo "输出目录：$out_dir"
    echo "============================================================"

    local -a command=(
        "$PYTHON_BIN" -u service/drama_by_creativity/tests/run_from_episode_outline.py
        --source-dir "$SOURCE_DIR"
        --output-dir "$out_dir"
        --story-id "$run_id"
        --start-episode 1
        --end-episode 60
        --min-word-count "$min_words"
        --max-word-count "$max_words"
    )
    if [[ -n "$baseline_flag" ]]; then
        command+=("$baseline_flag")
    fi
    "${command[@]}" 2>&1 | tee "$out_dir/generation.log"
}

run_group baseline 1500 2000
run_group memory   1500 2000
run_group baseline 2000 2500
run_group memory   2000 2500

echo
echo "四组剧本均已生成完成，批次号：$BATCH_ID"

CONTINUOUS_LOAD_SCRIPT="/inspire/hdd/global_user/hesiyang-CZXS25210137/localmodel_vllmdemo/continuous_load.sh"
if [[ ! -f "$CONTINUOUS_LOAD_SCRIPT" ]]; then
    echo "找不到占卡脚本：$CONTINUOUS_LOAD_SCRIPT" >&2
    exit 1
fi

echo "开始运行占卡脚本：$CONTINUOUS_LOAD_SCRIPT"
exec bash "$CONTINUOUS_LOAD_SCRIPT"
