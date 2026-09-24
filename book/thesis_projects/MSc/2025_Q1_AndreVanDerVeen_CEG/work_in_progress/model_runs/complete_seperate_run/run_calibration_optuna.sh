#!/usr/bin/env bash
set -euo pipefail

# Always run relative to this script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Optional: activate your venv if you use one
# source ../.venv/bin/activate

LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
RUN_TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/calibration_${RUN_TS}.log"

# Launch detached to survive terminal hangups:
#   bash run_calibration.sh --detach
if [[ "${1:-}" == "--detach" ]]; then
	shift || true
	DETACH_LOG="$LOG_DIR/nohup_${RUN_TS}.log"
	CALIBRATION_DETACHED=1 nohup bash "$0" "$@" > "$DETACH_LOG" 2>&1 < /dev/null &
	PID=$!
	echo "$PID" > "$LOG_DIR/calibration.pid"
	echo "Started detached calibration"
	echo "PID: $PID"
	echo "Nohup log: $DETACH_LOG"
	echo "Calibration log: $LOG_FILE"
	exit 0
fi

# Use unbuffered output so progress appears in logs immediately.
python -u standalone_calibration_optuna.py 2>&1 | tee -a "$LOG_FILE"