#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_RUNS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="/home/avandervee3/MSc_AralSea/venv/bin/python"
PYTHON_SCRIPT="$SCRIPT_DIR/long_runs_era5_calibrated.py"
LAUNCH_LOG="$SCRIPT_DIR/long_runs_era5_calibrated_launch.log"
PID_FILE="$SCRIPT_DIR/long_runs_era5_calibrated.pid"

cd "$MODEL_RUNS_DIR"

nohup "$VENV_PYTHON" "$PYTHON_SCRIPT" > "$LAUNCH_LOG" 2>&1 &
PID=$!

printf '%s\n' "$PID" > "$PID_FILE"

echo "Started long_runs_era5_calibrated.py with PID: $PID"
echo "Launch log: $LAUNCH_LOG"
echo "PID file: $PID_FILE"