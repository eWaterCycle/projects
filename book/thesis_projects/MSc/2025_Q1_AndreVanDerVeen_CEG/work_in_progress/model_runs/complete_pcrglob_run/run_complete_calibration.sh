#!/usr/bin/env bash
# Run complete_calibration.py with core-aware defaults.
#
# Defaults:
#   N_WORKERS = max(1, nproc - RESERVE_CORES), with RESERVE_CORES=1
#   POP_SIZE  = N_WORKERS * POP_MULTIPLIER, with POP_MULTIPLIER=2
#   RUN_MODE  = full (alternatives: prepare, validate)
#   BACKGROUND = 1 (run with nohup and write log)
#
# Examples:
#   ./run_complete_calibration.sh
#   RUN_MODE=validate BACKGROUND=0 ./run_complete_calibration.sh
#   RUN_MODE=prepare SKIP_FORCING_LOAD=1 BACKGROUND=0 ./run_complete_calibration.sh
#   CALIBRATION_RUN_ID=2 N_WORKERS=3 POP_SIZE=6 ./run_complete_calibration.sh
#   CONFIG_FILE=/path/to/template.yaml ./run_complete_calibration.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$({
    if git -C "$SCRIPT_DIR" rev-parse --show-toplevel >/dev/null 2>&1; then
        git -C "$SCRIPT_DIR" rev-parse --show-toplevel
    else
        cd "$SCRIPT_DIR/../../../../../../../.." && pwd
    fi
})"

VENV_PYTHON="$WORKSPACE_ROOT/venv/bin/python3"
PYTHON_SCRIPT="${PYTHON_SCRIPT:-$SCRIPT_DIR/complete_calibration.py}"
CONFIG_FILE="${CONFIG_FILE:-$SCRIPT_DIR/data/configs/template.yaml}"

CALIBRATION_RUN_ID="${CALIBRATION_RUN_ID:-1}"
RESERVE_CORES="${RESERVE_CORES:-1}"
POP_MULTIPLIER="${POP_MULTIPLIER:-2}"
RUN_MODE="${RUN_MODE:-full}"
SKIP_FORCING_LOAD="${SKIP_FORCING_LOAD:-0}"
BACKGROUND="${BACKGROUND:-1}"

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    echo "ERROR: Python script not found: $PYTHON_SCRIPT"
    exit 1
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "ERROR: Config file not found: $CONFIG_FILE"
    exit 1
fi

if ! [[ "$RESERVE_CORES" =~ ^[0-9]+$ ]]; then
    echo "ERROR: RESERVE_CORES must be a non-negative integer, got '$RESERVE_CORES'"
    exit 1
fi

if ! [[ "$POP_MULTIPLIER" =~ ^[0-9]+$ ]] || [[ "$POP_MULTIPLIER" -lt 1 ]]; then
    echo "ERROR: POP_MULTIPLIER must be an integer >= 1, got '$POP_MULTIPLIER'"
    exit 1
fi

if ! [[ "$CALIBRATION_RUN_ID" =~ ^[0-9]+$ ]] || [[ "$CALIBRATION_RUN_ID" -lt 1 ]]; then
    echo "ERROR: CALIBRATION_RUN_ID must be an integer >= 1, got '$CALIBRATION_RUN_ID'"
    exit 1
fi

if [[ "$SKIP_FORCING_LOAD" != "0" && "$SKIP_FORCING_LOAD" != "1" ]]; then
    echo "ERROR: SKIP_FORCING_LOAD must be 0 or 1, got '$SKIP_FORCING_LOAD'"
    exit 1
fi

if [[ "$BACKGROUND" != "0" && "$BACKGROUND" != "1" ]]; then
    echo "ERROR: BACKGROUND must be 0 or 1, got '$BACKGROUND'"
    exit 1
fi

N_CORES="$(nproc)"
N_WORKERS_DEFAULT=$((N_CORES - RESERVE_CORES))
if [[ "$N_WORKERS_DEFAULT" -lt 1 ]]; then
    N_WORKERS_DEFAULT=1
fi

N_WORKERS="${N_WORKERS:-$N_WORKERS_DEFAULT}"
POP_SIZE_DEFAULT=$((N_WORKERS * POP_MULTIPLIER))
POP_SIZE="${POP_SIZE:-$POP_SIZE_DEFAULT}"

if ! [[ "$N_WORKERS" =~ ^[0-9]+$ ]] || [[ "$N_WORKERS" -lt 1 ]]; then
    echo "ERROR: N_WORKERS must be an integer >= 1, got '$N_WORKERS'"
    exit 1
fi

if ! [[ "$POP_SIZE" =~ ^[0-9]+$ ]] || [[ "$POP_SIZE" -lt 1 ]]; then
    echo "ERROR: POP_SIZE must be an integer >= 1, got '$POP_SIZE'"
    exit 1
fi

ARGS=(--config "$CONFIG_FILE")
case "$RUN_MODE" in
    full)
        ;;
    prepare)
        ARGS+=(--prepare-only)
        ;;
    validate)
        ARGS+=(--validate-only)
        ;;
    *)
        echo "ERROR: RUN_MODE must be one of: full, prepare, validate. Got '$RUN_MODE'"
        exit 1
        ;;
esac

if [[ "$SKIP_FORCING_LOAD" == "1" ]]; then
    ARGS+=(--skip-forcing-load)
fi

LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/complete_calibration_${RUN_MODE}_run${CALIBRATION_RUN_ID}_${TIMESTAMP}.log"

echo "Starting complete calibration..."
echo "Script             : $PYTHON_SCRIPT"
echo "Config             : $CONFIG_FILE"
echo "Workspace          : $WORKSPACE_ROOT"
echo "Run ID             : $CALIBRATION_RUN_ID"
echo "Run mode           : $RUN_MODE"
echo "Skip forcing load  : $SKIP_FORCING_LOAD"
echo "Detected cores     : $N_CORES"
echo "Reserve cores      : $RESERVE_CORES"
echo "Workers            : $N_WORKERS"
echo "Population size    : $POP_SIZE"
echo "Population formula : workers * $POP_MULTIPLIER"
echo "Background         : $BACKGROUND"
echo "Log file           : $LOG_FILE"
echo "Time               : $(date)"

if [[ -x "$VENV_PYTHON" ]]; then
    PYTHON_BIN="$VENV_PYTHON"
    echo "Python executable  : $PYTHON_BIN"
else
    PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
    echo "WARNING: virtualenv python not found at $VENV_PYTHON"
    echo "         Running with current Python executable: $PYTHON_BIN"
fi

if [[ "$BACKGROUND" == "1" ]]; then
    nohup env \
        CALIBRATION_RUN_ID="$CALIBRATION_RUN_ID" \
        N_WORKERS="$N_WORKERS" \
        POP_MULTIPLIER="$POP_MULTIPLIER" \
        POP_SIZE="$POP_SIZE" \
        "$PYTHON_BIN" "$PYTHON_SCRIPT" "${ARGS[@]}" > "$LOG_FILE" 2>&1 &

    PID=$!

    echo ""
    echo "Calibration started with PID: $PID"
    echo "Monitor progress: tail -f $LOG_FILE"
    echo "Check process   : ps -p $PID -o pid,%cpu,%mem,etime,cmd"
    echo "Stop process    : kill $PID"
else
    echo ""
    echo "Running in foreground..."
    env \
        CALIBRATION_RUN_ID="$CALIBRATION_RUN_ID" \
        N_WORKERS="$N_WORKERS" \
        POP_MULTIPLIER="$POP_MULTIPLIER" \
        POP_SIZE="$POP_SIZE" \
        "$PYTHON_BIN" "$PYTHON_SCRIPT" "${ARGS[@]}"
fi
