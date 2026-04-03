#!/bin/bash
cd /Users/aimeestanyer/Projects/control-plane-3
for temp in 0.2 0.5 0.8; do
    python3 llm_safety_platform.py --api openrouter --model deepseek/deepseek-r1 --data probes_500.json --temperature $temp --db-model deepseek-r1
done
