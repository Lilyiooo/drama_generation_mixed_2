#!/usr/bin/env bash
# 复用88分逐集大纲，运行原有需求树 + Event Graph / World State 剧本生成。
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export DRAMA_SUMMARY_MEMORY_BASELINE=false
export DRAMA_OUTLINE_ONLY=0
export DRAMA_DISABLE_PLOT_RETRIEVAL=1
export DRAMA_LLM_BASE_URL="${DRAMA_LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRAMA_LLM_MODEL="${DRAMA_LLM_MODEL:-qwen-local}"
export DRAMA_LLM_MAX_TOKENS="${DRAMA_LLM_MAX_TOKENS:-0}"
export DRAMA_LLM_THINKING="${DRAMA_LLM_THINKING:-0}"
export DRAMA_LLM_TIMEOUT="${DRAMA_LLM_TIMEOUT:-0}"
export PYTHONUNBUFFERED=1
export DRAMA_ADJUST_WORD_COUNT="${DRAMA_ADJUST_WORD_COUNT:-true}"
export DRAMA_ADJUST_COHERENCE="${DRAMA_ADJUST_COHERENCE:-true}"
GEN_PYTHON="${PYTHON_BIN:-/inspire/hdd/global_user/hesiyang-CZXS25210137/anaconda3/bin/python3}"
SOURCE_DIR="$SCRIPT_DIR/output/qwen36_27b_eight_fields_demo_20260916_060508_407704"
export DRAMA_OUTPUT_DIR="${DRAMA_OUTPUT_DIR:-$SCRIPT_DIR/output/qwen36_27b_88_outline_pipeline_$(date +%Y%m%d_%H%M%S)}"
for arg in "$@"; do
    if [[ "$arg" == --summary-memory-baseline ]]; then
        echo '此脚本固定使用原有叙事记忆，不接受 --summary-memory-baseline。' >&2
        exit 2
    fi
done
"$GEN_PYTHON" -c 'from service.drama_by_creativity.script_postprocessing import word_count_adjustment_enabled, coherence_adjustment_enabled; print("字数调整：", word_count_adjustment_enabled(), "衔接调整：", coherence_adjustment_enabled())'
"$GEN_PYTHON" tools/check_drama_dependencies.py
mkdir -p "$DRAMA_OUTPUT_DIR"
printf '大纲来源：%s\n输出目录：%s\n记忆方式：未来需求树 + Event Graph / World State\n' "$SOURCE_DIR" "$DRAMA_OUTPUT_DIR"
"$GEN_PYTHON" -u service/drama_by_creativity/tests/run_from_episode_outline.py \
    --source-dir "$SOURCE_DIR" --output-dir "$DRAMA_OUTPUT_DIR" \
    --story-id APID-88-outline-pipeline "$@" \
    2>&1 | tee -a "$DRAMA_OUTPUT_DIR/generation.log"
