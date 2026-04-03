#!/bin/bash
# 4 AM completion check + run missing models
# Loads .env via Python (avoids bash parse errors from & in DATABASE_URL)

cd /Users/aimeestanyer/Projects/control-plane-3

LOG="/Users/aimeestanyer/Projects/control-plane-3/4am_check.log"
exec > >(tee -a "$LOG") 2>&1

echo ""
echo "========================================"
echo "4 AM CHECK: $(date)"
echo "========================================"

# Load env vars via Python to avoid bash parse errors on special chars
eval "$(python3 -c "
import os
from dotenv import load_dotenv
load_dotenv('.env')
for k, v in os.environ.items():
    if any(k.startswith(p) for p in ['GROQ','OPENAI','ANTHROPIC','OPENROUTER','GOOGLE','NVIDIA','FIREWORKS','MISTRAL','COHERE','CEREBRAS','DEEPSEEK','KIMI','IBM','AWS','DATABASE_URL']):
        safe = v.replace(\"'\", \"'\\\"'\\\"'\")
        print(f\"export {k}='{safe}'\")
")"

if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not loaded. Aborting."
    exit 1
fi

echo "Env loaded OK."

# Query DB for completion status
STATUS=$(psql "$DATABASE_URL" -t -A -F'|' -c "
SELECT model,
  COUNT(DISTINCT CASE WHEN dataset='ctrl' THEN temperature END) as ctrl_temps,
  COUNT(DISTINCT CASE WHEN dataset='probes_200' THEN temperature END) as p200_temps,
  COUNT(DISTINCT CASE WHEN dataset='probes_500' THEN temperature END) as p500_temps
FROM runs
GROUP BY model
ORDER BY model;
" 2>/dev/null)

echo ""
echo "--- DB STATUS ---"
echo "$STATUS"
echo ""

run_missing() {
    local model_str="$1"
    local api="$2"
    local datafile="$3"
    local temp="$4"
    echo ">>> Running: $model_str | $datafile | T=$temp"
    local attempt=0
    while [ $attempt -lt 5 ]; do
        python3 llm_safety_platform.py --model "$model_str" --api "$api" --data "$datafile" --temperature "$temp" && return 0
        attempt=$((attempt + 1))
        wait_secs=$((attempt * 30))
        echo "  Shell retry $attempt/5 — waiting ${wait_secs}s..."
        sleep $wait_secs
    done
    echo "!!! FAILED after 5 shell retries: $model_str | $datafile | T=$temp"
    return 1
}

already_done() {
    local model="$1"
    local dataset="$2"
    local temp="$3"
    local count
    count=$(psql "$DATABASE_URL" -t -A -c \
        "SELECT COUNT(*) FROM runs WHERE model='$model' AND dataset='$dataset' AND ROUND(temperature::numeric,1)=$temp AND status='completed'" 2>/dev/null)
    [ "${count:-0}" -ge 1 ]
}

# Model → provider mapping
get_provider() {
    case "$1" in
        granite-3.3-8b-instruct)         echo "replicate|ibm-granite/granite-3.3-8b-instruct" ;;
        phi-4-mini-instruct)              echo "nvidia|microsoft/phi-4-mini-instruct" ;;
        phi-4)                            echo "openrouter|microsoft/phi-4" ;;
        kimi-k2*)                         echo "fireworks|accounts/fireworks/models/kimi-k2-instruct-0905" ;;
        kimi-k2-instruct-0905)            echo "fireworks|accounts/fireworks/models/kimi-k2-instruct-0905" ;;
        deepseek-r1-distill*)             echo "openrouter|deepseek/deepseek-r1-distill-qwen-32b" ;;
        deepseek-r1)                      echo "fireworks|deepseek-ai/DeepSeek-R1" ;;
        magistral-medium-latest)          echo "mistral|magistral-medium-latest" ;;
        qwen3-32b)                        echo "groq|qwen/qwen3-32b" ;;
        command-r)                        echo "cohere|command-r-08-2024" ;;
        mistral-medium-3)                 echo "mistral|mistral-medium-3" ;;
        ministral-8b)                     echo "mistral|ministral-8b-latest" ;;
        mistral-nemo)                     echo "mistral|open-mistral-nemo" ;;
        command-a-03-2025)                echo "cohere|command-a-03-2025" ;;
        command-r7b)                      echo "cohere|command-r7b-12-2024" ;;
        gemini-2.0-flash-lite)            echo "google|gemini-2.0-flash-lite" ;;
        mixtral-8x7b)                     echo "groq|mixtral-8x7b-32768" ;;
        gemma2-9b-it)                     echo "groq|gemma2-9b-it" ;;
        deepseek-r1-distill-llama-70b)    echo "groq|deepseek-r1-distill-llama-70b" ;;
        *)                                echo "" ;;
    esac
}

# Parse status and run missing combos
while IFS='|' read -r model ctrl p200 p500; do
    model=$(echo "$model" | xargs)
    ctrl=$(echo "$ctrl" | xargs)
    p200=$(echo "$p200" | xargs)
    p500=$(echo "$p500" | xargs)

    [ "$ctrl" -eq 4 ] && [ "$p200" -eq 4 ] && [ "$p500" -eq 4 ] 2>/dev/null && continue

    provider_info=$(get_provider "$model")
    [ -z "$provider_info" ] && continue

    api="${provider_info%%|*}"
    model_str="${provider_info##*|}"

    echo "--- Checking $model (ctrl=$ctrl/4, p200=$p200/4, p500=$p500/4) ---"

    if [ "${ctrl:-0}" -lt 4 ] 2>/dev/null; then
        for temp in 0.0 0.2 0.5 0.8; do
            already_done "$model" "ctrl" "$temp" || run_missing "$model_str" "$api" "probes_control_20.json" "$temp"
        done
    fi

    if [ "${p200:-0}" -lt 4 ] 2>/dev/null; then
        for temp in 0.0 0.2 0.5 0.8; do
            already_done "$model" "probes_200" "$temp" || run_missing "$model_str" "$api" "probes_200.json" "$temp"
        done
    fi

    if [ "${p500:-0}" -lt 4 ] 2>/dev/null; then
        for temp in 0.0 0.2 0.5 0.8; do
            already_done "$model" "probes_500" "$temp" || run_missing "$model_str" "$api" "probes_500.json" "$temp"
        done
    fi

done <<< "$STATUS"

echo ""
echo "--- FINAL STATUS ---"
psql "$DATABASE_URL" -c "
SELECT model,
  COUNT(DISTINCT CASE WHEN dataset='ctrl' THEN temperature END) as ctrl_temps,
  COUNT(DISTINCT CASE WHEN dataset='probes_200' THEN temperature END) as p200_temps,
  COUNT(DISTINCT CASE WHEN dataset='probes_500' THEN temperature END) as p500_temps,
  CASE WHEN
    COUNT(DISTINCT CASE WHEN dataset='ctrl' THEN temperature END) = 4
    AND COUNT(DISTINCT CASE WHEN dataset='probes_200' THEN temperature END) = 4
    AND COUNT(DISTINCT CASE WHEN dataset='probes_500' THEN temperature END) = 4
  THEN 'COMPLETE' ELSE 'incomplete' END as status
FROM runs
GROUP BY model
ORDER BY status, model;"

echo ""
echo "========================================"
echo "4 AM CHECK DONE: $(date)"
echo "========================================"
