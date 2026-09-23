#!/usr/bin/env bash
# 从已有 Qwen 分集大纲重生成正文；进程结束后运行 continuous_load.sh。
set -euo pipefail
trap 'exit 130' INT
trap 'exit 143' TERM

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TASK_ROOT=/inspire/hdd/global_user/hesiyang-CZXS25210137
CONDA_ROOT="$TASK_ROOT/anaconda3"
GEN_PYTHON="${PYTHON_BIN:-$CONDA_ROOT/bin/python3}"
LOAD_SCRIPT="$TASK_ROOT/localmodel_vllmdemo/continuous_load.sh"
SOURCE_DIR="$SCRIPT_DIR/output/60ep_0906_1302_v9_future5_state2_complete_noqd_qwen36_27b"
# 默认每次另开目录，保存本次正文、记忆和完整诊断。
export DRAMA_OUTPUT_DIR="${DRAMA_OUTPUT_DIR:-${SOURCE_DIR}_rerun_$(date +%Y%m%d_%H%M%S)_$$}"
export DRAMA_LLM_BASE_URL="${DRAMA_LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRAMA_LLM_MODEL="${DRAMA_LLM_MODEL:-qwen-local}"
export DRAMA_LLM_MAX_TOKENS="${DRAMA_LLM_MAX_TOKENS:-0}"
export DRAMA_LLM_THINKING="${DRAMA_LLM_THINKING:-0}"
export DRAMA_LLM_TIMEOUT="${DRAMA_LLM_TIMEOUT:-0}"
export DRAMA_DISABLE_PLOT_RETRIEVAL=1
export PYTHONUNBUFFERED=1

cd "$SCRIPT_DIR"
[[ -x "$GEN_PYTHON" ]]
[[ -f "$LOAD_SCRIPT" ]]
[[ -f "$TASK_ROOT/localmodel_vllmdemo/continuous_load.py" ]]
[[ -x "$CONDA_ROOT/envs/vllm-cu129/bin/python" ]]
"$GEN_PYTHON" tools/check_drama_dependencies.py
mkdir -p "$DRAMA_OUTPUT_DIR"
# Resolve before changing directory for the load script.
export DRAMA_OUTPUT_DIR="$(cd "$DRAMA_OUTPUT_DIR" && pwd)"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
started_seconds=$SECONDS
printf '生成开始：%s\n输出目录：%s\n' "$started_at" "$DRAMA_OUTPUT_DIR"

# 保留生成退出码；正常结束或报错退出后均执行 continuous_load.sh。
# Ctrl+C / SIGTERM 由上方 trap 终止整个串联脚本。
set +e
"$GEN_PYTHON" -u service/drama_by_creativity/tests/run_from_episode_outline.py \
    --source-dir "$SOURCE_DIR" \
    --output-dir "$DRAMA_OUTPUT_DIR" \
    --start-episode 1 \
    --end-episode 60 \
    2>&1 | tee "$DRAMA_OUTPUT_DIR/generation.log"
run_codes=("${PIPESTATUS[@]}")
set -e
generation_rc=${run_codes[0]}
if [[ "$generation_rc" -eq 130 || "$generation_rc" -eq 143 ]]; then
    exit "$generation_rc"
fi
elapsed_seconds=$((SECONDS - started_seconds))
{
    printf 'started_at_utc=%s\n' "$started_at"
    printf 'finished_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'elapsed_seconds=%s\n' "$elapsed_seconds"
    printf 'generation_exit_code=%s\n' "$generation_rc"
    printf 'tee_exit_code=%s\n' "${run_codes[1]}"
} | tee "$DRAMA_OUTPUT_DIR/generation_status.txt"

printf '生成进程已结束（退出码 %s），运行 continuous_load.sh。\n' "$generation_rc"
cd "$TASK_ROOT"
exec bash "$LOAD_SCRIPT" "$@"
