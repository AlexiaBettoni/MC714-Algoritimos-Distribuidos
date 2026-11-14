#!/usr/bin/env bash
# Convenience wrapper for one coordinator-crash run. The full experiment
# matrix is available through scripts/run_experiments.py.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
exec python3 "$ROOT/scripts/run_experiments.py" \
  --scenario coordinator_crash --nodes "${NODES:-5}" \
  --loss-rates "${LOSS_RATE:-0}" --repetitions 1 \
  --timeout "${HB_TIMEOUT:-2}" --interval "${HB_INTERVAL:-0.5}" \
  --seed "${SEED:-1}" --results "${RESULTS_DIR:-$ROOT/results/experiments}"
