#!/bin/bash
# Monitor and restart any failed overnight groups every 20 minutes

cd /Users/aimeestanyer/Projects/control-plane-3

LOG="/Users/aimeestanyer/Projects/control-plane-3/monitor.log"
exec > >(tee -a "$LOG") 2>&1

echo "MONITOR STARTED: $(date)"

GROUPS="mistral cohere google groq nvidia fireworks"

while true; do
    echo ""
    echo "--- Monitor check: $(date) ---"

    for group in $GROUPS; do
        if ! pgrep -f "run_new_models_overnight.sh $group" > /dev/null 2>&1; then
            echo "  [$group] not running — restarting"
            bash /Users/aimeestanyer/Projects/control-plane-3/run_new_models_overnight.sh "$group" &
        else
            echo "  [$group] running OK"
        fi
    done

    # Check 4am_check models (granite ctrl, phi-4-mini ctrl still needed)
    for model_proc in "granite-3.3-8b-instruct.*probes_control" "phi-4-mini.*probes_control" "kimi-k2-instruct-0905.*probes_500" "qwen3-32b.*probes_200"; do
        if ! pgrep -f "$model_proc" > /dev/null 2>&1; then
            echo "  [one-off $model_proc] not running — covered by group scripts"
        fi
    done

    sleep 1200  # check every 20 minutes
done
