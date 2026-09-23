#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
EVALUATOR_ROOT=/inspire/hdd/global_user/wangqiqi-CZXS25210124/drama_evaluator_logic_quality
PYTHON_BIN="${PYTHON_BIN:-/inspire/qb-ilm/project/exploration-topic/wangqiqi-CZXS25210124/anaconda3/envs/qwen36-vllm/bin/python}"
ACTION="${1:-run}"
RUNS=(R01 R02 R03)

export DRAMA_EVAL_BASE_URL="${DRAMA_EVAL_BASE_URL:-http://127.0.0.1:8001/v1}"
export DRAMA_EVAL_API_KEY="${DRAMA_EVAL_API_KEY:-EMPTY}"
export DRAMA_EVAL_MODEL=Qwen3.8-27B
export DRAMA_EVAL_TEMPERATURE=0
export DRAMA_EVAL_ENABLE_THINKING=false
export PYTHONUNBUFFERED=1

run_dir() {
    printf '%s/output/new_scriptdrama_structured_hybrid_gate_%s' "$ROOT" "$1"
}

episode_count() {
    local directory
    directory="$(run_dir "$1")/05_drama"
    find "$directory" -maxdepth 1 -type f -name 'episode_*.json' 2>/dev/null | wc -l
}

prepare_inputs() {
    local failed=0
    for run in "${RUNS[@]}"; do
        local directory count destination
        directory="$(run_dir "$run")"
        count="$(episode_count "$run" | tr -d '[:space:]')"
        if [[ "$count" != 60 ]]; then
            echo "$run 尚未生成完整：episodes=$count/60" >&2
            failed=1
            continue
        fi
        destination="$directory/drama_evaluator_logic_quality_input/full_60_episodes.txt"
        "$PYTHON_BIN" "$EVALUATOR_ROOT/tools/export_pipeline_script.py" "$directory" "$destination"
    done
    [[ "$failed" -eq 0 ]] || return 1
}

run_one() {
    local run="$1" directory script output
    directory="$(run_dir "$run")"
    script="$directory/drama_evaluator_logic_quality_input/full_60_episodes.txt"
    output="$directory/drama_evaluations_logic_quality_qwen38_v24/full_60_episodes"
    "$PYTHON_BIN" "$EVALUATOR_ROOT/evaluate_multi_agent.py" "$script" \
        --output-dir "$output" \
        --model Qwen3.8-27B \
        --context-mode direct \
        --direct-char-limit 300000 \
        --chunk-chars 100000 \
        --max-output-tokens 24576 \
        --timeout 1200 \
        --retries 3 \
        --parse-retries 3
}

show_status() {
    for run in "${RUNS[@]}"; do
        local directory count score
        directory="$(run_dir "$run")"
        count="$(episode_count "$run" | tr -d '[:space:]')"
        score="$directory/drama_evaluations_logic_quality_qwen38_v24/full_60_episodes/scores.json"
        if [[ -f "$score" ]]; then
            echo "$run: episodes=$count/60 scored=True score_file=$score"
        else
            echo "$run: episodes=$count/60 scored=False"
        fi
    done
}

case "$ACTION" in
    prepare)
        prepare_inputs
        ;;
    status)
        show_status
        ;;
    run)
        mkdir -p "$ROOT/logs"
        prepare_inputs
        models="$(curl --noproxy '*' --fail --silent --show-error "$DRAMA_EVAL_BASE_URL/models")"
        [[ "$models" == *Qwen3.8-27B* ]] || {
            echo "端口 8001 未返回 Qwen3.8-27B：$DRAMA_EVAL_BASE_URL/models" >&2
            exit 1
        }
        pids=()
        for run in "${RUNS[@]}"; do
            (set -o pipefail; run_one "$run" 2>&1 | tee -a "$ROOT/logs/new_scriptdrama_evaluation_${run}.log") &
            pids+=("$!")
            echo "$run evaluation PID=$!"
        done
        failed=0
        for index in "${!pids[@]}"; do
            if wait "${pids[index]}"; then
                code=0
            else
                code=$?
                failed=1
            fi
            echo "${RUNS[index]} evaluation exit_code=$code"
        done
        show_status
        [[ "$failed" -eq 0 ]] || {
            echo "部分评测未完成；成功结果已保留，修复后重跑同一命令即可续跑。" >&2
            exit 1
        }
        ;;
    *)
        echo "用法：bash evaluate_new_scriptdrama_runs.sh {prepare|run|status}" >&2
        exit 2
        ;;
esac
