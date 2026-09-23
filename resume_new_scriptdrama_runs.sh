#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/inspire/qb-ilm/project/exploration-topic/wangqiqi-CZXS25210124/anaconda3/envs/qwen36-vllm/bin/python}"
ACTION="${1:-run}"
RUNS=(R01 R02 R03)

run_id() {
    printf 'new_scriptdrama_structured_hybrid_gate_%s' "$1"
}

output_dir() {
    printf '%s/output/%s' "$ROOT" "$(run_id "$1")"
}

source_dir() {
    printf '%s/recovery_sources/%s' "$ROOT" "$(run_id "$1")"
}

episode_count() {
    find "$(output_dir "$1")/05_drama" -maxdepth 1 -type f -name 'episode_*.json' 2>/dev/null | wc -l
}

memory_episode_count() {
    local memory
    memory="$(output_dir "$1")/narrative_memory/$(run_id "$1")/memory_state.json"
    if [[ ! -f "$memory" ]]; then
        echo 0
        return
    fi
    "$PYTHON_BIN" -c 'import json,sys; print(int(json.load(open(sys.argv[1], encoding="utf-8")).get("last_updated_episode", -1)) + 1)' "$memory"
}

structured_episode_count() {
    local memory
    memory="$(output_dir "$1")/structured_state/$(run_id "$1")/state_memory.json"
    if [[ ! -f "$memory" ]]; then
        echo 0
        return
    fi
    "$PYTHON_BIN" -c 'import json,sys; print(int(json.load(open(sys.argv[1], encoding="utf-8")).get("last_updated_episode", -1)) + 1)' "$memory"
}

verify_progress() {
    local run="$1" scripts narrative structured
    scripts="$(episode_count "$run" | tr -d '[:space:]')"
    narrative="$(memory_episode_count "$run" | tr -d '[:space:]')"
    structured="$(structured_episode_count "$run" | tr -d '[:space:]')"
    if [[ "$scripts" != "$narrative" || "$scripts" != "$structured" ]]; then
        echo "$run 进度不一致：scripts=$scripts narrative=$narrative structured=$structured" >&2
        return 1
    fi
}

prepare_sources() {
    for run in "${RUNS[@]}"; do
        local output source
        output="$(output_dir "$run")"
        source="$(source_dir "$run")"
        verify_progress "$run"
        for required in \
            generation_background.json \
            01_script_proposal/01_world_view.json \
            01_script_proposal/02_role_setting.json \
            03_story_outline/outline.json \
            04_future_map/future_map.json \
            04_future_map/episode_contributions.json; do
            [[ -f "$output/$required" ]] || {
                echo "$run 缺少恢复所需资产：$output/$required" >&2
                return 1
            }
        done
        compgen -G "$output/04_episode_outline/*.json" >/dev/null || {
            echo "$run 缺少分集大纲：$output/04_episode_outline" >&2
            return 1
        }
        mkdir -p "$source"
        cp -a "$output/generation_background.json" "$source/"
        cp -a "$output/01_script_proposal" "$source/"
        cp -a "$output/03_story_outline" "$source/"
        cp -a "$output/04_episode_outline" "$source/"
        echo "$run 恢复源已准备：$source"
    done
}

show_status() {
    for run in "${RUNS[@]}"; do
        local scripts narrative structured gates
        scripts="$(episode_count "$run" | tr -d '[:space:]')"
        narrative="$(memory_episode_count "$run" | tr -d '[:space:]')"
        structured="$(structured_episode_count "$run" | tr -d '[:space:]')"
        gates="$(find "$(output_dir "$run")/scene_state_gate" -type f -name outcome.json 2>/dev/null | wc -l | tr -d '[:space:]')"
        echo "$run: episodes=$scripts/60 narrative=$narrative structured=$structured gate_outcomes=$gates"
    done
}

run_one() {
    local run="$1" id output source
    id="$(run_id "$run")"
    output="$(output_dir "$run")"
    source="$(source_dir "$run")"
    verify_progress "$run"
    if [[ "$(episode_count "$run" | tr -d '[:space:]')" == 60 ]]; then
        echo "$run 已完成 60/60，跳过"
        return 0
    fi
    (
        flock -n 9 || {
            echo "$run 已有恢复进程持有锁：$output/.resume_generation.lock" >&2
            exit 2
        }
        export DRAMA_OUTPUT_DIR="$output"
        export DRAMA_STATE_LIFECYCLE_HYBRID=0
        export DRAMA_SCENE_STATE_GATE=enforce
        export DRAMA_SCENE_GATE_POLICY=conservative_v1
        export DRAMA_STATE_MEMORY_LIMIT=20
        export DRAMA_STATE_MEMORY_BUDGET=6000
        export DRAMA_DISABLE_PLOT_RETRIEVAL=1
        export DRAMA_SUMMARY_MEMORY_BASELINE=false
        export DRAMA_FULL_HISTORY_BASELINE=false
        export DRAMA_FUTURE_OUTLINE_CONSISTENCY=false
        export DRAMA_ADJUST_WORD_COUNT=false
        export DRAMA_ADJUST_COHERENCE=false
        export DRAMA_LLM_BASE_URL="${DRAMA_LLM_BASE_URL:-http://127.0.0.1:8000/v1}"
        export DRAMA_LLM_MODEL="${DRAMA_LLM_MODEL:-Qwen3.6-27B}"
        export DRAMA_LLM_THINKING="${DRAMA_LLM_THINKING:-0}"
        export DRAMA_LLM_TIMEOUT="${DRAMA_LLM_TIMEOUT:-0}"
        export DRAMA_LLM_MAX_TOKENS="${DRAMA_LLM_MAX_TOKENS:-0}"
        export PYTHONUNBUFFERED=1
        cd "$ROOT"
        "$PYTHON_BIN" -u service/drama_by_creativity/tests/run_from_episode_outline.py \
            --source-dir "$source" \
            --output-dir "$output" \
            --story-id "$id" \
            --resume \
            --reuse-future-map \
            --end-episode 60
    ) 9>"$output/.resume_generation.lock"
}

case "$ACTION" in
    prepare)
        prepare_sources
        show_status
        ;;
    status)
        show_status
        ;;
    run)
        mkdir -p "$ROOT/logs"
        prepare_sources
        models="$(curl --noproxy '*' --fail --silent --show-error "${DRAMA_LLM_BASE_URL:-http://127.0.0.1:8000/v1}/models")"
        [[ "$models" == *Qwen3.6-27B* ]] || {
            echo "端口 8000 未返回 Qwen3.6-27B" >&2
            exit 1
        }
        pids=()
        for run in "${RUNS[@]}"; do
            (set -o pipefail; run_one "$run" 2>&1 | tee -a "$ROOT/logs/resume_new_scriptdrama_${run}.log") &
            pids+=("$!")
            echo "$run resume PID=$!"
        done
        failed=0
        for index in "${!pids[@]}"; do
            if wait "${pids[index]}"; then
                code=0
            else
                code=$?
                failed=1
            fi
            echo "${RUNS[index]} resume exit_code=$code"
        done
        show_status
        [[ "$failed" -eq 0 ]] || {
            echo "部分轨迹未完成；已成功内容保留，直接重跑同一命令继续。" >&2
            exit 1
        }
        ;;
    *)
        echo "用法：bash resume_new_scriptdrama_runs.sh {prepare|run|status}" >&2
        exit 2
        ;;
esac
