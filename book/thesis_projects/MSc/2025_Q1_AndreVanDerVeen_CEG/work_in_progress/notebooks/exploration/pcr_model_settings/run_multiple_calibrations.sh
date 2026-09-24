#!/bin/bash
# Run N independent CMA-ES calibrations in parallel.
# Each run gets its own CALIBRATION_RUN_ID, perturbed starting point,
# CMA-ES seed, and output directory so results never collide.
#
# Usage:
#   ./run_multiple_calibrations.sh          # default 3 runs
#   N_RUNS=5 ./run_multiple_calibrations.sh # custom number of runs

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
N_RUNS="${N_RUNS:-3}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/experiment_example.py"

# Workspace root is four levels up from the pcr_model_settings directory.
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../../../../../.." && pwd)"
VENV_ACTIVATE="$WORKSPACE_ROOT/venv/bin/activate"

LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    echo "ERROR: experiment script not found: $PYTHON_SCRIPT"
    exit 1
fi

if [[ ! -f "$VENV_ACTIVATE" ]]; then
    echo "WARNING: virtualenv not found at $VENV_ACTIVATE"
    echo "         Continuing without activating it — ensure the correct"
    echo "         Python environment is already active."
    VENV_ACTIVATE=""
fi

# ---------------------------------------------------------------------------
# Launch runs
# ---------------------------------------------------------------------------
echo "Launching $N_RUNS independent calibration runs..."
echo "Script : $PYTHON_SCRIPT"
echo "Logs   : $LOG_DIR/"
echo ""

PIDS=()
for i in $(seq 1 "$N_RUNS"); do
    LOG_FILE="$LOG_DIR/calibration_run_${i}.log"
    echo "Starting run $i -> $LOG_FILE"

    if [[ -n "$VENV_ACTIVATE" ]]; then
        nohup bash -c "
            source '$VENV_ACTIVATE'
            cd '$WORKSPACE_ROOT'
            CALIBRATION_RUN_ID=$i python '$PYTHON_SCRIPT'
        " > "$LOG_FILE" 2>&1 &
    else
        nohup bash -c "
            cd '$WORKSPACE_ROOT'
            CALIBRATION_RUN_ID=$i python '$PYTHON_SCRIPT'
        " > "$LOG_FILE" 2>&1 &
    fi

    PIDS+=($!)
done

echo ""
echo "All $N_RUNS runs launched.  PIDs: ${PIDS[*]}"
echo ""
echo "Monitor progress:"
for i in $(seq 1 "$N_RUNS"); do
    echo "  tail -f $LOG_DIR/calibration_run_${i}.log"
done
echo ""

PID_CSV="$(IFS=,; echo "${PIDS[*]}")"
echo "Optional resource checks (run in another terminal):"
echo "  pidstat -dru -h -p ${PIDS[*]} 5"
echo "  watch -n 5 \"ps -p ${PID_CSV} -o pid,%cpu,%mem,rss,etime,cmd\""
echo ""
echo "Wait for all runs to finish:"
echo "  wait ${PIDS[*]}"
echo ""

echo "Check if any run is still running:"
echo "  ps aux | grep experiment_example"
