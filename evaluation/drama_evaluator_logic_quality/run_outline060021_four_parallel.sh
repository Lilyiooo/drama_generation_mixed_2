#!/usr/bin/env bash
# 并行评测 outlinefrom060021 的四组完整60集剧本，并汇总子维度分数与等权均分。
set -euo pipefail

EVAL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TASK_ROOT="/inspire/hdd/global_user/hesiyang-CZXS25210137"
GEN_OUTPUT="$TASK_ROOT/drama_operator_new_v9_future5_state2_complete/drama_operator_hybrid_state_pipeline_shortdrama/output"
PYTHON_BIN="${PYTHON_BIN:-$TASK_ROOT/anaconda3/bin/python3}"

export DRAMA_EVAL_BASE_URL="${DRAMA_EVAL_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRAMA_EVAL_MODEL="${DRAMA_EVAL_MODEL:-qwen-local}"
export DRAMA_EVAL_API_KEY="${DRAMA_EVAL_API_KEY:-EMPTY}"
export DRAMA_EVAL_TEMPERATURE="${DRAMA_EVAL_TEMPERATURE:-0}"
export DRAMA_EVAL_ENABLE_THINKING="${DRAMA_EVAL_ENABLE_THINKING:-false}"
export PYTHONUNBUFFERED=1

model_label="${DRAMA_EVAL_MODEL//\//_}"
RESULT_ROOT="${DRAMA_EVAL_RESULT_ROOT:-$EVAL_DIR/output/outlinefrom060021_four_20260919_$model_label}"

names=(
    baseline_1500-2000
    memory_1500-2000
    baseline_2000-2500
    memory_2000-2500
)
sources=(
    "$GEN_OUTPUT/shortdrama_baseline_1500_2000_outlinefrom060021_20260919_090316"
    "$GEN_OUTPUT/shortdrama_memory_1500_2000_outlinefrom060021_20260919_090316"
    "$GEN_OUTPUT/shortdrama_baseline_2000_2500_outlinefrom060021_20260919_124130"
    "$GEN_OUTPUT/shortdrama_memory_2000_2500_outlinefrom060021_20260919_124130"
)

args=()
dry_run=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry_run=true; args+=("$arg") ;;
        --restart) args+=("$arg") ;;
        *) echo "仅支持 --dry-run 或 --restart" >&2; exit 2 ;;
    esac
done

mkdir -p "$RESULT_ROOT/inputs" "$RESULT_ROOT/logs"
exec 9>"$RESULT_ROOT/.batch.lock"
flock -n 9 || { echo "该评测批次已经在运行：$RESULT_ROOT" >&2; exit 2; }

# 在发起模型请求前，严格检查每组是否恰好包含60集并逐字导出。
for index in "${!names[@]}"; do
    "$PYTHON_BIN" "$EVAL_DIR/tools/export_pipeline_script.py" \
        "${sources[$index]}" "$RESULT_ROOT/inputs/${names[$index]}.txt"
done

printf '四组并行评测\n模型：%s\n结果目录：%s\n' "$DRAMA_EVAL_MODEL" "$RESULT_ROOT"

pids=()
for name in "${names[@]}"; do
    "$PYTHON_BIN" "$EVAL_DIR/evaluate_multi_agent.py" "$RESULT_ROOT/inputs/$name.txt" \
        --output-dir "$RESULT_ROOT/$name" \
        --model "$DRAMA_EVAL_MODEL" \
        --context-mode direct \
        --review-workers 1 \
        --audit-workers 1 \
        --arbitration-workers 1 \
        --max-output-tokens 16000 \
        --timeout 1200 \
        "${args[@]}" \
        >>"$RESULT_ROOT/logs/$name.log" 2>&1 &
    pids+=("$!")
    printf '%s：PID=%s；日志=%s/logs/%s.log\n' "$name" "$!" "$RESULT_ROOT" "$name"
done

trap 'kill "${pids[@]}" 2>/dev/null || true; exit 130' INT TERM
failed=0
for index in "${!pids[@]}"; do
    if wait "${pids[$index]}"; then
        code=0
    else
        code=$?
        failed=1
    fi
    if [[ "$dry_run" == false ]]; then
        printf '%s\n' "$code" >"$RESULT_ROOT/${names[$index]}.exitcode"
    fi
    printf '%s 退出码：%s\n' "${names[$index]}" "$code"
done
trap - INT TERM

if [[ "$dry_run" == true ]]; then
    echo "dry-run完成：输入与预计调用量已检查，未调用评测模型。"
    exit "$failed"
fi

"$PYTHON_BIN" - "$RESULT_ROOT" <<'PY'
import csv
import json
import sys
from pathlib import Path

from drama_evaluator.multi_agent import DIMENSIONS, LABELS, QUALITY_MODULES, UNITS

root = Path(sys.argv[1])
names = ["baseline_1500-2000", "memory_1500-2000", "baseline_2000-2500", "memory_2000-2500"]
rows = []
csv_rows = []

def child_labels(dimension):
    if dimension == "quality":
        return {key: value[0] for key, value in QUALITY_MODULES.items()}
    return {key: value[0] for key, value in UNITS[dimension].items()}

for name in names:
    code_path = root / f"{name}.exitcode"
    code = int(code_path.read_text()) if code_path.exists() else 1
    result_path = root / name / "multi_agent_result.json"
    if code != 0 or not result_path.exists():
        rows.append({"experiment": name, "status": "failed", "exit_code": code})
        continue
    result = json.loads(result_path.read_text(encoding="utf-8"))
    dimensions = {}
    for dimension in DIMENSIONS:
        item = result["dimensions"][dimension]
        labels = child_labels(dimension)
        detail = {
            "label": LABELS[dimension],
            "subdimension_scores": {
                key: {
                    "label": label,
                    "ledger_score": item["ledger_subdimension_scores"][key],
                    "holistic_score": item["holistic_subdimension_scores"][key],
                    "fused_score": item["fused_subdimension_scores"][key],
                }
                for key, label in labels.items()
            },
            "ledger_subdimension_mean": item["ledger_subdimension_mean"],
            "holistic_subdimension_mean": item["holistic_subdimension_mean"],
            "final_score": item["final_score"],
        }
        dimensions[dimension] = detail
        for key, sub in detail["subdimension_scores"].items():
            csv_rows.append({
                "experiment": name,
                "dimension": dimension,
                "dimension_label": LABELS[dimension],
                "subdimension": key,
                "subdimension_label": sub["label"],
                "ledger_score": sub["ledger_score"],
                "holistic_score": sub["holistic_score"],
                "fused_score": sub["fused_score"],
                "dimension_final_score": detail["final_score"],
            })
    rows.append({
        "experiment": name,
        "status": "complete",
        "exit_code": code,
        "dimensions": dimensions,
        "output_dir": str((root / name).resolve()),
        "log": str((root / "logs" / f"{name}.log").resolve()),
    })

(root / "four_evaluations_detailed_summary.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
)
with (root / "subdimension_scores.csv").open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=list(csv_rows[0]) if csv_rows else ["experiment"])
    writer.writeheader()
    writer.writerows(csv_rows)

lines = ["# outlinefrom060021 四组评测详细汇总", "",
         "每个子维度融合分 = 50%审核后台账分 + 50%独立整体评分；大维度得分 = 子维度融合分的算术平均。", ""]
for dimension in DIMENSIONS:
    labels = child_labels(dimension)
    headers = ["实验"] + list(labels.values()) + ["大维度最终均分"]
    lines.extend([
        f"## {LABELS[dimension]}（表内子维度均为融合分）", "",
        "|" + "|".join(headers) + "|",
        "|" + "|".join(["---"] + ["---:"] * (len(headers) - 1)) + "|",
    ])
    for row in rows:
        if row.get("status") != "complete":
            lines.append("|" + "|".join([row["experiment"], "评测失败"] + [""] * (len(headers) - 2)) + "|")
            continue
        detail = row["dimensions"][dimension]
        values = [row["experiment"]]
        values.extend(f"{detail['subdimension_scores'][key]['fused_score']:.2f}" for key in labels)
        values.append(f"{detail['final_score']:.2f}")
        lines.append("|" + "|".join(values) + "|")
    lines.append("")

(root / "four_evaluations_detailed_summary.md").write_text("\n".join(lines), encoding="utf-8")
print("\n四组评测汇总：")
for row in rows:
    if row.get("status") != "complete":
        print(row["experiment"], "failed")
        continue
    print(row["experiment"], {
        detail["label"]: detail["final_score"] for detail in row["dimensions"].values()
    })
print("详细Markdown：", root / "four_evaluations_detailed_summary.md")
print("详细CSV：", root / "subdimension_scores.csv")
PY

exit "$failed"
