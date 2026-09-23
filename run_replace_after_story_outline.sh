#!/usr/bin/env bash
# 从上次详细故事大纲续跑；旧后续产物自动备份，新结果写回原目录。
set -euo pipefail
trap 'exit 130' INT
trap 'exit 143' TERM
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TASK_ROOT=/inspire/hdd/global_user/hesiyang-CZXS25210137
GEN_PYTHON="${PYTHON_BIN:-$TASK_ROOT/anaconda3/bin/python3}"
SOURCE_DIR="$SCRIPT_DIR/output/qwen36_27b_all_stages_20260913_104112"
export DRAMA_LLM_BASE_URL="${DRAMA_LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRAMA_LLM_MODEL="${DRAMA_LLM_MODEL:-qwen-local}"
export DRAMA_LLM_MAX_TOKENS="${DRAMA_LLM_MAX_TOKENS:-0}"
export DRAMA_LLM_THINKING="${DRAMA_LLM_THINKING:-0}"
export DRAMA_LLM_TIMEOUT="${DRAMA_LLM_TIMEOUT:-0}"
export DRAMA_DISABLE_PLOT_RETRIEVAL=1
# 与这份 all_stages 原运行一致，使用原记忆算法。
export DRAMA_SUMMARY_MEMORY_BASELINE=false
export PYTHONUNBUFFERED=1
cd "$SCRIPT_DIR"
"$GEN_PYTHON" tools/check_drama_dependencies.py
# 防止重复启动本续跑脚本。
exec 9>"${SOURCE_DIR}.stage_rerun.lock"
flock -n 9 || { echo '该目录已有阶段续跑进程。' >&2; exit 1; }
"$GEN_PYTHON" service/drama_by_creativity/tests/run_replace_after_story_outline.py \
    --source-dir "$SOURCE_DIR" --check-only
if [[ "${1:-}" == --check-only ]]; then
    exit 0
fi
LOG_FILE="${SOURCE_DIR}_stage_rerun_$(date +%Y%m%d_%H%M%S).log"
set +e
"$GEN_PYTHON" -u service/drama_by_creativity/tests/run_replace_after_story_outline.py \
    --source-dir "$SOURCE_DIR" 2>&1 | tee "$LOG_FILE"
run_codes=("${PIPESTATUS[@]}")
set -e
cp -- "$LOG_FILE" "$SOURCE_DIR/generation.log"
printf '生成退出码：%s；日志：%s\n' "${run_codes[0]}" "$LOG_FILE"
if [[ "${run_codes[0]}" == 130 || "${run_codes[0]}" == 143 ]]; then
    exit "${run_codes[0]}"
fi
flock -u 9
exec 9>&-
echo '生成进程已结束，启动 continuous_load.sh 占卡。'
cd "$TASK_ROOT"
exec bash "$TASK_ROOT/localmodel_vllmdemo/continuous_load.sh" "$@"
