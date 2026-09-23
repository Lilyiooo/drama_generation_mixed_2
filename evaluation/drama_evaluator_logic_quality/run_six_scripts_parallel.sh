#!/usr/bin/env bash
# Six independent evaluations; rerun the same command to reuse validated artifacts.
set -euo pipefail
EVAL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GEN_ROOT="$(dirname "$EVAL_DIR")"
PYTHON="${PYTHON_BIN:-/inspire/hdd/global_user/hesiyang-CZXS25210137/anaconda3/bin/python3}"
export DRAMA_EVAL_BASE_URL="${DRAMA_EVAL_BASE_URL:-http://127.0.0.1:8000/v1}"
export DRAMA_EVAL_MODEL="${DRAMA_EVAL_MODEL:-qwen-local}"
export DRAMA_EVAL_API_KEY="${DRAMA_EVAL_API_KEY:-EMPTY}"
export DRAMA_EVAL_TEMPERATURE="${DRAMA_EVAL_TEMPERATURE:-0}"
export DRAMA_EVAL_ENABLE_THINKING="${DRAMA_EVAL_ENABLE_THINKING:-false}"
export PYTHONUNBUFFERED=1
model_label="${DRAMA_EVAL_MODEL//\//_}"
RESULT_ROOT="${DRAMA_EVAL_RESULT_ROOT:-$EVAL_DIR/output/six_lengths_subdimension_fusion_20260919_$model_label}"
args=()
dry_run=false
summarize_only=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=true; args+=("$arg") ;;
    --restart) args+=("$arg") ;;
    --summarize-only) summarize_only=true ;;
    *) echo '仅支持 --dry-run、--restart 或 --summarize-only' >&2; exit 2 ;;
  esac
done
if [[ "$dry_run" == true && "$summarize_only" == true ]]; then
  echo '--dry-run 与 --summarize-only 不能同时使用' >&2
  exit 2
fi
names=(baseline_1000-1400 memory_1000-1400 baseline_1500-2000 memory_1500-2000 baseline_2000-2500 memory_2000-2500)
old="$GEN_ROOT/outputs/six_length_experiments_20260917_175650"
new="$GEN_ROOT/outputs/three_parallel_20260918_050243"
sources=("$old/${names[0]}" "$old/${names[1]}" "$old/${names[2]}" "$new/${names[3]}" "$new/${names[4]}" "$new/${names[5]}")
mkdir -p "$RESULT_ROOT/inputs" "$RESULT_ROOT/logs"
exec 9>"$RESULT_ROOT/.batch.lock"
flock -n 9 || { echo "评测批次已在运行：$RESULT_ROOT" >&2; exit 2; }
failed=0
if [[ "$summarize_only" == false ]]; then
  # Validate every script and export verbatim before starting model requests.
  for i in "${!names[@]}"; do
    "$PYTHON" "$EVAL_DIR/tools/export_pipeline_script.py" "${sources[i]}" "$RESULT_ROOT/inputs/${names[i]}.txt"
  done
  printf '六组并行评测，单组内部并发为1。\n模型：%s\n结果目录：%s\n' "$DRAMA_EVAL_MODEL" "$RESULT_ROOT"
  pids=()
  for name in "${names[@]}"; do
    "$PYTHON" "$EVAL_DIR/evaluate_multi_agent.py" "$RESULT_ROOT/inputs/$name.txt" \
      --output-dir "$RESULT_ROOT/$name" --model "$DRAMA_EVAL_MODEL" \
      --context-mode direct --review-workers 1 --audit-workers 1 --arbitration-workers 1 \
      --max-output-tokens 16000 --timeout 1200 "${args[@]}" \
      >> "$RESULT_ROOT/logs/$name.log" 2>&1 &
    pids+=("$!")
    printf '%s：PID=%s，日志=%s/logs/%s.log\n' "$name" "$!" "$RESULT_ROOT" "$name"
  done
  trap 'kill "${pids[@]}" 2>/dev/null || true; exit 130' INT TERM
  for i in "${!pids[@]}"; do
    if wait "${pids[i]}"; then code=0; else code=$?; failed=1; fi
    if [[ "$dry_run" == false ]]; then printf '%s\n' "$code" > "$RESULT_ROOT/${names[i]}.exitcode"; fi
    printf '%s 退出码：%s\n' "${names[i]}" "$code"
  done
  trap - INT TERM
else
  echo "只汇总已有结果，不调用评测模型：$RESULT_ROOT"
fi
if [[ "$dry_run" == false ]]; then
  PYTHONPATH="$EVAL_DIR${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON" - "$RESULT_ROOT" <<'PY'
import csv
import json
import sys
from pathlib import Path

from drama_evaluator.multi_agent import DIMENSIONS, LABELS, QUALITY_MODULES, UNITS

root = Path(sys.argv[1])
names = [
    "baseline_1000-1400", "memory_1000-1400",
    "baseline_1500-2000", "memory_1500-2000",
    "baseline_2000-2500", "memory_2000-2500",
]

def labels_for(dimension):
    if dimension == "quality":
        return {key: value[0] for key, value in QUALITY_MODULES.items()}
    return {key: value[0] for key, value in UNITS[dimension].items()}

rows, csv_rows = [], []
for name in names:
    code = int((root / f"{name}.exitcode").read_text())
    result_file = root / name / "multi_agent_result.json"
    if code != 0 or not result_file.exists():
        rows.append({"experiment": name, "status": "failed", "exit_code": code})
        continue
    result = json.loads(result_file.read_text(encoding="utf-8"))
    dimensions = {}
    for dimension in DIMENSIONS:
        item = result["dimensions"][dimension]
        labels = labels_for(dimension)
        subdimensions = {
            key: {
                "label": label,
                "ledger_score": item["ledger_subdimension_scores"][key],
                "holistic_score": item["holistic_subdimension_scores"][key],
                "fused_score": item["fused_subdimension_scores"][key],
            }
            for key, label in labels.items()
        }
        dimensions[dimension] = {
            "label": LABELS[dimension],
            "subdimensions": subdimensions,
            "ledger_subdimension_mean": item["ledger_subdimension_mean"],
            "holistic_subdimension_mean": item["holistic_subdimension_mean"],
            "final_score": item["final_score"],
        }
        for key, score in subdimensions.items():
            csv_rows.append({
                "experiment": name,
                "dimension": dimension,
                "dimension_label": LABELS[dimension],
                "subdimension": key,
                "subdimension_label": score["label"],
                "ledger_score": score["ledger_score"],
                "holistic_score": score["holistic_score"],
                "fused_score": score["fused_score"],
                "dimension_final_score": item["final_score"],
            })
    rows.append({
        "experiment": name, "status": "complete", "exit_code": code,
        "dimensions": dimensions, "output_dir": str(root / name),
        "log": str(root / "logs" / f"{name}.log"),
    })

(root / "six_evaluations_detailed_summary.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
)
with (root / "subdimension_scores.csv").open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=list(csv_rows[0]) if csv_rows else ["experiment"])
    writer.writeheader()
    writer.writerows(csv_rows)

lines = [
    "# 六组剧本新评测汇总", "",
    "每个子维度融合分 = 50%审核后台账分 + 50%独立整体评分；大维度得分 = 子维度融合分的算术平均。", "",
]
for dimension in DIMENSIONS:
    labels = labels_for(dimension)
    headers = ["实验"] + list(labels.values()) + ["大维度最终分"]
    lines.extend([
        f"## {LABELS[dimension]}（子维度列均为融合分）", "",
        "|" + "|".join(headers) + "|",
        "|" + "|".join(["---"] + ["---:"] * (len(headers) - 1)) + "|",
    ])
    for row in rows:
        if row["status"] != "complete":
            lines.append("|" + "|".join([row["experiment"], "失败"] + [""] * (len(headers) - 2)) + "|")
            continue
        detail = row["dimensions"][dimension]
        values = [row["experiment"]]
        values.extend(f"{detail['subdimensions'][key]['fused_score']:.2f}" for key in labels)
        values.append(f"{detail['final_score']:.2f}")
        lines.append("|" + "|".join(values) + "|")
    lines.append("")
(root / "six_evaluations_detailed_summary.md").write_text("\n".join(lines), encoding="utf-8")

print("\n六组评测最终分：")
for row in rows:
    if row["status"] != "complete":
        print(row["experiment"], "failed")
    else:
        print(row["experiment"], {
            item["label"]: item["final_score"] for item in row["dimensions"].values()
        })
print("详细汇总：", root / "six_evaluations_detailed_summary.md")
print("子维度CSV：", root / "subdimension_scores.csv")
PY
fi
exit "$failed"
