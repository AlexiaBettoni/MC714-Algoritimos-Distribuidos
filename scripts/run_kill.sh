#!/usr/bin/env bash
# Uso: HB_TIMEOUT=2 LOSS_RATE=0.1 SEED=1 scripts/run_kill.sh node3 > results/run1.json
set -euo pipefail
VICTIM=${1:-node3}
docker compose up -d --build >&2
sleep 5  
KILL_TS=$(date +%s.%N)
docker compose kill "$VICTIM" >&2
sleep $(python3 -c "print(${HB_TIMEOUT:-2}*3)")
docker compose logs --no-log-prefix --no-color > /tmp/logs.txt
docker compose down >&2
python3 scripts/analyze.py /tmp/logs.txt "$VICTIM" "$KILL_TS"
 