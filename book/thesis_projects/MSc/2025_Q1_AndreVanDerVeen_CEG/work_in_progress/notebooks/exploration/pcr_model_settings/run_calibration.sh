#!/bin/bash
# Shell script to run PCRGlobWB calibration in the background

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="/home/avandervee3/MSc_AralSea"
VENV_PATH="$WORKSPACE_ROOT/venv/bin/activate"
PYTHON_SCRIPT="$SCRIPT_DIR/test_calibration_script.py"
LOG_DIR="$SCRIPT_DIR/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/calibration_${TIMESTAMP}.log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

echo "Starting PCRGlobWB calibration..."
echo "Script: $PYTHON_SCRIPT"
echo "Log file: $LOG_FILE"
echo "Time: $(date)"

# Activate virtual environment and run script
# Redirect both stdout and stderr to log file
nohup bash -c "
    source '$VENV_PATH' && \
    cd '$WORKSPACE_ROOT' && \
    python3 '$PYTHON_SCRIPT'
" > "$LOG_FILE" 2>&1 &

# Capture the PID
PID=$!

echo "Calibration started with PID: $PID"
echo "Monitor progress with: tail -f $LOG_FILE"
echo ""
echo "To check if still running: ps -p $PID"
echo "To stop: kill $PID"

