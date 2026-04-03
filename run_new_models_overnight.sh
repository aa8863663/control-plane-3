#!/bin/bash
# 9 new models overnight runner — infinite retry, never stops

cd /Users/aimeestanyer/Projects/control-plane-3

LOG="/Users/aimeestanyer/Projects/control-plane-3/new_models_overnight.log"
exec > >(tee -a "$LOG") 2>&1

echo ""
echo "========================================"
echo "NEW MODELS OVERNIGHT [$1]: $(date)"
echo "========================================"

eval "$(python3 -c "
import os
from dotenv import load_dotenv
load_dotenv('.env')
for k, v in os.environ.items():
    if any(k.startswith(p) for p in ['GROQ','OPENAI','ANTHROPIC','OPENROUTER','GOOGLE','NVIDIA','FIREWORKS','MISTRAL','COHERE','CEREBRAS','DEEPSEEK','KIMI','IBM','AWS','DATABASE_URL']):
        safe = v.replace(\"'\", \"'\\\"'\\\"'\")
        print(f\"export {k}='{safe}'\")
")"

if [ -z "$DATABASE_URL" ]; then echo "ERROR: DATABASE_URL not loaded"; exit 1; fi

run_combo() {
    local model_str="$1"
    local api="$2"
    local datafile="$3"
    local temp="$4"
    local db_model="$5"
    local dataset_label="$6"

    local already
    already=$(psql "$DATABASE_URL" -t -A -c \
        "SELECT COUNT(*) FROM runs WHERE model='$db_model' AND dataset='$dataset_label' AND ROUND(temperature::numeric,1)=$temp" \
        2>/dev/null | tr -d '[:space:]')
    if [ "${already:-0}" -ge 1 ]; then
        echo "  [SKIP] $db_model | $dataset_label | T=$temp"
        return 0
    fi

    echo ">>> $db_model | $dataset_label | T=$temp"
    local attempt=0
    while true; do
        python3 llm_safety_platform.py --model "$model_str" --api "$api" --data "$datafile" --temperature "$temp" --db-model "$db_model" && return 0
        attempt=$((attempt + 1))
        local wait=$((attempt > 10 ? 300 : attempt * 30))
        echo "  Retry $attempt — waiting ${wait}s..."
        sleep "$wait"
    done
}

run_model() {
    local db_model="$1"
    local api="$2"
    local model_str="$3"
    echo ""
    echo "=== $db_model ($api) ==="
    for temp in 0.0 0.2 0.5 0.8; do
        run_combo "$model_str" "$api" "probes_control_20.json" "$temp" "$db_model" "ctrl"
    done
    for temp in 0.0 0.2 0.5 0.8; do
        run_combo "$model_str" "$api" "probes_200.json" "$temp" "$db_model" "probes_200"
    done
    for temp in 0.0 0.2 0.5 0.8; do
        run_combo "$model_str" "$api" "probes_500.json" "$temp" "$db_model" "probes_500"
    done
    echo "=== DONE: $db_model ==="
}

case "$1" in
  mistral)
    run_model "mistral-medium-3"               "mistral" "mistral-medium-3"
    run_model "ministral-8b"                   "mistral" "ministral-8b-latest"
    run_model "mistral-nemo"                   "mistral" "open-mistral-nemo"
    run_model "magistral-medium-latest"        "mistral" "magistral-medium-latest"
    ;;
  cohere)
    run_model "command-a-03-2025"              "cohere"  "command-a-03-2025"
    run_model "command-r7b"                    "cohere"  "command-r7b-12-2024"
    ;;
  google)
    run_model "gemini-2.0-flash-lite"          "google"  "gemini-2.0-flash-lite"
    ;;
  groq)
    run_model "qwen3-32b"                      "groq"    "qwen/qwen3-32b"
    ;;
  nvidia)
    run_model "granite-3.3-8b-instruct"        "nvidia"  "ibm/granite-3.3-8b-instruct"
    run_model "phi-4-mini-instruct"            "nvidia"  "microsoft/phi-4-mini-instruct"
    ;;
  fireworks)
    run_model "kimi-k2"                        "fireworks" "accounts/fireworks/models/kimi-k2-instruct-0905"
    run_model "deepseek-r1"                    "fireworks" "deepseek-ai/DeepSeek-R1"
    ;;
  *)
    echo "Usage: $0 [mistral|cohere|google|groq|nvidia|fireworks]"
    echo "Groups: mistral=mistral-medium-3,ministral-8b,mistral-nemo,magistral | google=gemini-2.0-flash-lite | groq=qwen3-32b | fireworks=kimi-k2,deepseek-r1"
    exit 1
    ;;
esac

echo ""
echo "========================================"
echo "GROUP $1 DONE: $(date)"
echo "========================================"
