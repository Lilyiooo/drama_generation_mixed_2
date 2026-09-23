#!/usr/bin/env bash
# 恢复 20260913_140305 概要记忆运行，从已保存记忆的下一集继续，结束后占卡。
set -euo pipefail
trap 'exit 130' INT
trap 'exit 143' TERM

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TASK_ROOT=/inspire/hdd/global_user/hesiyang-CZXS25210137
CONDA_ROOT="$TASK_ROOT/anaconda3"
GEN_PYTHON="${PYTHON_BIN:-$CONDA_ROOT/bin/python3}"
LOAD_SCRIPT="$TASK_ROOT/localmodel_vllmdemo/continuous_load.sh"
SOURCE_DIR="$SCRIPT_DIR/output/qwen36_27b_all_stages_20260913_104112"
export DRAMA_SUMMARY_MEMORY_BASELINE=true
# 规范化开关并将实验模式写入输出目录名称。
case "${DRAMA_SUMMARY_MEMORY_BASELINE:-false}" in
    1|[Tt][Rr][Uu][Ee]|[Yy][Ee][Ss]|[Oo][Nn])
        export DRAMA_SUMMARY_MEMORY_BASELINE=true
        memory_suffix="_summary"
        ;;
    0|[Ff][Aa][Ll][Ss][Ee]|[Nn][Oo]|[Oo][Ff][Ff]|"")
        export DRAMA_SUMMARY_MEMORY_BASELINE=false
        memory_suffix=""
        ;;
    *)
        echo "DRAMA_SUMMARY_MEMORY_BASELINE 请设置为 true 或 false。" >&2
        exit 2
        ;;
esac
export DRAMA_OUTPUT_DIR="$SCRIPT_DIR/output/qwen36_27b_all_stages_20260913_104112_summary_rerun_20260913_140305"
# 即使自定义了输出目录，baseline 模式也确保目录名带标识。
if [[ "$DRAMA_SUMMARY_MEMORY_BASELINE" == true ]]; then
    DRAMA_OUTPUT_DIR="${DRAMA_OUTPUT_DIR%/}"
    if [[ "${DRAMA_OUTPUT_DIR##*/}" != *summary* ]]; then
        export DRAMA_OUTPUT_DIR="${DRAMA_OUTPUT_DIR}_summary"
    fi
fi
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
# 将输出目录规范化为绝对路径。
export DRAMA_OUTPUT_DIR="$(cd "$DRAMA_OUTPUT_DIR" && pwd)"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
started_seconds=$SECONDS
printf '生成开始：%s\n输出目录：%s\n' "$started_at" "$DRAMA_OUTPUT_DIR"

# 保留生成退出码和日志。
# Ctrl+C / SIGTERM 由上方 trap 终止整个串联脚本。
set +e
"$GEN_PYTHON" -u service/drama_by_creativity/tests/run_from_episode_outline.py \
    --source-dir "$SOURCE_DIR" \
    --output-dir "$DRAMA_OUTPUT_DIR" \
    --summary-memory-baseline \
    --resume \
    --start-episode 1 \
    --end-episode 60 \
    2>&1 | tee "$DRAMA_OUTPUT_DIR/generation_resume_57.log"
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
    printf 'summary_memory_baseline=%s\n' "$DRAMA_SUMMARY_MEMORY_BASELINE"
    printf 'generation_exit_code=%s\n' "$generation_rc"
    printf 'tee_exit_code=%s\n' "${run_codes[1]}"
} | tee "$DRAMA_OUTPUT_DIR/generation_resume_57_status.txt"

printf '生成进程已结束（退出码 %s），输出目录：%s\n' "$generation_rc" "$DRAMA_OUTPUT_DIR"
printf '启动 continuous_load.sh。\n'
cd "$TASK_ROOT"
exec bash "$LOAD_SCRIPT" "$@"
