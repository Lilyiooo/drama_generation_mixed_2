#!/usr/bin/env bash
# 从头生成到逐集大纲三轮审校、评分择优完成，不生成正文。
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export PYTHON_BIN="${PYTHON_BIN:-/inspire/hdd/global_user/hesiyang-CZXS25210137/anaconda3/bin/python3}"
export DRAMA_OUTPUT_DIR="${DRAMA_OUTPUT_DIR:-$SCRIPT_DIR/output/qwen36_27b_outline_only_$(date +%Y%m%d_%H%M%S_%N)}"
# 保持现有默认细化阶段；可用 --eventline-stages 开端 发展 高潮 结局 覆盖。
echo "本次生成到逐集大纲评分择优后停止。"
bash "$SCRIPT_DIR/run_60ep_qwen36_27b.sh" --outline-only "$@"
echo "最终逐集大纲：$DRAMA_OUTPUT_DIR/04_episode_outline_review/after.json"
echo "各版本评分与选择：$DRAMA_OUTPUT_DIR/04_episode_outline_review/selection.json"
