#!/usr/bin/env bash
# 复用88分逐集大纲，子树上的 event/detail/clue 全量检索。
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export DRAMA_SUBTREE_MEMORY_LIMIT=0
export DRAMA_OUTPUT_DIR="${DRAMA_OUTPUT_DIR:-$SCRIPT_DIR/output/qwen36_27b_88_outline_pipeline_all_subtree_$(date +%Y%m%d_%H%M%S)}"
printf '子树记忆：全部非伏笔条目（不限制10条）\n'
exec bash "$SCRIPT_DIR/run_pipeline_from_88_outline.sh" "$@"
