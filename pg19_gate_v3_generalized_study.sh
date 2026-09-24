#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -n "${CONDA_PREFIX:-}" && -x "$CONDA_PREFIX/bin/python" ]]; then
    PYTHON_BIN="$CONDA_PREFIX/bin/python"
  else
    PYTHON_BIN="$(command -v python)"
  fi
fi
export PYTHON_BIN

exec "$PYTHON_BIN" -u "$ROOT/tools/pg19_gate_v3_generalized_study.py" "$@"
