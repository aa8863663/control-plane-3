#!/bin/bash
# 3:30 AM deepseek-r1 check — runs any missing probes_500 temps on fireworks

cd /Users/aimeestanyer/Projects/control-plane-3

LOG="/Users/aimeestanyer/Projects/control-plane-3/deepseek_r1_check.log"
exec > >(tee -a "$LOG") 2>&1

echo ""
echo "========================================"
echo "DEEPSEEK-R1 CHECK: $(date)"
echo "========================================"

eval "$(python3 -c "
import os
from dotenv import load_dotenv
load_dotenv('.env')
for k, v in os.environ.items():
    if any(k.startswith(p) for p in ['DATABASE_URL','FIREWORKS']):
        safe = v.replace(\"'\", \"'\\\"'\\\"'\")
        print(f\"export {k}='{safe}'\")
")"

if [ -z "$DATABASE_URL" ]; then echo "ERROR: DATABASE_URL not loaded"; exit 1; fi

for temp in 0.0 0.2 0.5 0.8; do
    already=$(psql "$DATABASE_URL" -t -A -c \
        "SELECT COUNT(*) FROM runs WHERE model='deepseek-r1' AND dataset='probes_500' AND ROUND(temperature::numeric,1)=$temp" \
        2>/dev/null | tr -d '[:space:]')
    if [ "${already:-0}" -ge 1 ]; then
        echo "  [SKIP] T=$temp already in DB"
        continue
    fi
    echo ">>> deepseek-r1 | probes_500 | T=$temp (fireworks)"
    attempt=0
    while true; do
        python3 llm_safety_platform.py --model deepseek-ai/DeepSeek-R1 --api fireworks --data probes_500.json --temperature "$temp" && break
        attempt=$((attempt + 1))
        wait=$((attempt > 10 ? 300 : attempt * 30))
        echo "  Retry $attempt — waiting ${wait}s..."
        sleep "$wait"
    done
done

echo ""
echo "DEEPSEEK-R1 CHECK DONE: $(date)"
echo "========================================"
