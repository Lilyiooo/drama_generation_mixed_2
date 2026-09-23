#!/usr/bin/env bash
# Usage: bash run_local_nmf_no_obligations.sh [--dry-run | --restart | other evaluator options]
set -euo pipefail
EVAL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TASK_ROOT=/inspire/hdd/global_user/hesiyang-CZXS25210137
SOURCE_DIR="$TASK_ROOT/drama-generation/outputs/qwen36_27b_88_outline_nmf_no_obligations_prompt_20260917_125008"
GEN_PYTHON="${PYTHON_BIN:-$TASK_ROOT/anaconda3/bin/python3}"
label=nmf_no_obligations_20260917_125008
export DRAMA_EVAL_BASE_URL="${DRAMA_EVAL_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRAMA_EVAL_MODEL="${DRAMA_EVAL_MODEL:-qwen-local}"
export DRAMA_EVAL_API_KEY="${DRAMA_EVAL_API_KEY:-EMPTY}"
export DRAMA_EVAL_TEMPERATURE="${DRAMA_EVAL_TEMPERATURE:-0}"
export DRAMA_EVAL_ENABLE_THINKING="${DRAMA_EVAL_ENABLE_THINKING:-false}"
export PYTHONUNBUFFERED=1
model_label="${DRAMA_EVAL_MODEL//\//_}"
RESULT_ROOT="${DRAMA_EVAL_RESULT_ROOT:-$EVAL_DIR/output/memory_variants_$model_label}"
mkdir -p "$RESULT_ROOT/inputs" "$RESULT_ROOT/$label"
# Prevent overlapping runs of the same script into the same reports directory.
exec 9>"$RESULT_ROOT/$label/.runner.lock"
flock -n 9 || { echo '该结果目录已有评测进程运行。' >&2; exit 2; }
"$GEN_PYTHON" "$EVAL_DIR/tools/export_pipeline_script.py" "$SOURCE_DIR" "$RESULT_ROOT/inputs/$label.txt"
printf '接口：%s\n模型：%s\n评测组：%s\n输出目录：%s\n' "$DRAMA_EVAL_BASE_URL" "$DRAMA_EVAL_MODEL" "$label" "$RESULT_ROOT/$label"
"$GEN_PYTHON" "$EVAL_DIR/evaluate_multi_agent.py" "$RESULT_ROOT/inputs/$label.txt" \
    --output-dir "$RESULT_ROOT/$label" --model "$DRAMA_EVAL_MODEL" \
    --context-mode direct --review-workers 1 --audit-workers 1 --arbitration-workers 1 \
    --max-output-tokens 16000 --timeout 1200 "$@" \
    2>&1 | tee -a "$RESULT_ROOT/$label/evaluation.log"
