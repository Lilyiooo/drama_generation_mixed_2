#!/usr/bin/env bash
# Usage: bash run_local_three_scripts.sh baseline|pipeline1|pipeline2 [evaluator options]
set -euo pipefail
EVAL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TASK_ROOT=/inspire/hdd/global_user/hesiyang-CZXS25210137
SOURCE_ROOT="$TASK_ROOT/drama_operator_new_v9_future5_state2_complete/drama_operator_new_v9_future5_state2_complete_simple/output"
GEN_PYTHON="${PYTHON_BIN:-$TASK_ROOT/anaconda3/bin/python3}"
case "${1:-}" in
 baseline) folder=qwen36_27b_full_history_20260916_113537_979877 ;;
 pipeline1) folder=qwen36_27b_88_outline_pipeline_20260916_105755 ;;
 pipeline2) folder=qwen36_27b_88_outline_pipeline_20260916_111213 ;;
 *) echo '用法：bash run_local_three_scripts.sh baseline|pipeline1|pipeline2 [--dry-run 等评测参数]' >&2; exit 2 ;;
esac
label="$1"
shift
export DRAMA_EVAL_BASE_URL="${DRAMA_EVAL_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRAMA_EVAL_MODEL="${DRAMA_EVAL_MODEL:-qwen-local}"
export DRAMA_EVAL_API_KEY="${DRAMA_EVAL_API_KEY:-EMPTY}"
export DRAMA_EVAL_TEMPERATURE="${DRAMA_EVAL_TEMPERATURE:-0}"
export DRAMA_EVAL_ENABLE_THINKING="${DRAMA_EVAL_ENABLE_THINKING:-false}"
export PYTHONUNBUFFERED=1
model_label="${DRAMA_EVAL_MODEL//\//_}"
RESULT_ROOT="${DRAMA_EVAL_RESULT_ROOT:-$EVAL_DIR/output/three_scripts_$model_label}"
mkdir -p "$RESULT_ROOT/inputs" "$RESULT_ROOT/$label"
# Prevent overlapping runs of the same script into the same reports directory.
exec 9>"$RESULT_ROOT/$label/.runner.lock"
flock -n 9 || { echo '该结果目录已有评测进程运行。' >&2; exit 2; }
"$GEN_PYTHON" "$EVAL_DIR/tools/export_pipeline_script.py" "$SOURCE_ROOT/$folder" "$RESULT_ROOT/inputs/$label.txt"
printf '接口：%s\n模型：%s\n评测组：%s\n输出目录：%s\n' "$DRAMA_EVAL_BASE_URL" "$DRAMA_EVAL_MODEL" "$label" "$RESULT_ROOT/$label"
"$GEN_PYTHON" "$EVAL_DIR/evaluate_multi_agent.py" "$RESULT_ROOT/inputs/$label.txt" \
    --output-dir "$RESULT_ROOT/$label" --model "$DRAMA_EVAL_MODEL" \
    --context-mode direct --review-workers 1 --audit-workers 1 --arbitration-workers 1 \
    --max-output-tokens 16000 --timeout 1200 "$@" \
    2>&1 | tee -a "$RESULT_ROOT/$label/evaluation.log"
