# SESSION DEBRIEF — 2026-03-31 ~22:30 BST
# For the next Claude session. Read this before touching anything.

---

## IDENTITY & LEGAL (non-negotiable)
- Public name: A. Abby — NEVER write "Aimee Stanyer" anywhere
- ICO case vs OpenAI — route ALL grok via openrouter, NEVER xai direct
- NEVER expose: probes_200.json, probes_control_20.json, probes_500.json
- DO NOT contact Credo AI, Monitaur, Arthur AI, Luminos until arXiv is live
- DO NOT reuse: emergency_fix.sh, diagnose_leaderboard.py

---

## PROJECT
- Repo: ~/Projects/control-plane-3
- DB: Neon PostgreSQL EU Frankfurt — credentials in .env
- GitHub: github.com/aa8863663/control-plane-3 (private)
- Live site: https://mtcp.live

## CODE RULES
- Python 3.9 — use Optional[] not X | None
- psycopg2: use %s not ?
- id and run_id are TEXT — always quote in WHERE clauses
- recovery_latency is TEXT — cast to FLOAT for AVG
- Bedrock: max 1 concurrent request, eu. prefix on all model names

---

## WHAT IS RUNNING RIGHT NOW

### 1. p500 jobs (started ~19:15 BST) — still in progress
Check with: ps aux | grep llm_safety | grep -v grep | wc -l

Still running when this was written (~22:30 BST):
  deepseek-r1 T=0.0/0.2/0.5/0.8  — via openrouter (SLOW — reasoning model, 2-6 hrs)
  grok-3-mini T=0.5/0.8           — via openrouter
  magistral-medium-latest T=0.0/0.2/0.5/0.8 — via mistral
  qwen/qwen3-8b p500 T=0.8        — via openrouter

### 2. ctrl extra temps (started ~22:10 BST, PID 27119)
Script: run_ctrl_extra_temps.py
Log: logs/ctrl_extra_temps.log
Purpose: adds ctrl T=0.2/0.5/0.8 for all 27 models (T=0.0 already in DB)
Check with: grep -E "(RUNNING|IMPORTED|ERROR|Pass rate|SKIP|Done)" logs/ctrl_extra_temps.log | tail -30
Expected runtime: ~1.5-3 hrs

---

## DB STATE (~22:30 BST)

All models: ctrl=1 (only T=0.0 so far), p200=4, p500=4
EXCEPT:
  deepseek-r1: p500=- (running)
  grok-3-mini: p500=2 (T=0.5/0.8 running)
  magistral-medium-latest: p500=- (running)
  qwen/qwen3-8b: p500=3 (T=0.8 running)

Once run_ctrl_extra_temps.py finishes: all models will have ctrl=4
Once p500 jobs finish: all models will have p500=4

TARGET: ctrl=4, p200=4, p500=4 for all 27 models (excluding command-r which is retired)

RETIRED — always skip: command-r
DELETED this session: granite-3.3-8b, phi-4-mini (Nvidia 504 errors)

---

## STEPS FOR NEXT SESSION

### 1. Check what's still running
ps aux | grep llm_safety | grep -v grep
Check ctrl script: grep -c "IMPORTED" logs/ctrl_extra_temps.log
Check p500: tail -5 logs/deepseek_t08.log

### 2. If ctrl script is still running, wait for it
tail -f logs/ctrl_extra_temps.log

### 3. Run coverage query
cd ~/Projects/control-plane-3 && export $(grep -v '^#' .env | xargs) && python3 << 'PYEOF'
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("""
SELECT model,
  MAX(CASE WHEN dataset = 'ctrl' THEN temps END) as ctrl,
  MAX(CASE WHEN dataset = 'probes_200' THEN temps END) as p200,
  MAX(CASE WHEN dataset = 'probes_500' THEN temps END) as p500
FROM (
  SELECT model, dataset, COUNT(DISTINCT temperature) as temps
  FROM runs GROUP BY model, dataset
) x
GROUP BY model ORDER BY model;
""")
for r in cur.fetchall():
    ctrl = str(r[1]) if r[1] else '-'
    p200 = str(r[2]) if r[2] else '-'
    p500 = str(r[3]) if r[3] else '-'
    complete = (r[1]==4 and r[2]==4 and r[3]==4)
    flag = 'COMPLETE' if complete else 'PARTIAL'
    print(f"{r[0]:<50} ctrl={ctrl} p200={p200} p500={p500}  {flag}")
conn.close()
PYEOF

### 4. Re-run any failed jobs
Check ctrl failures: grep -A2 "ERROR" logs/ctrl_extra_temps.log
Re-run a single ctrl job example:
  cd ~/Projects/control-plane-3 && export $(grep -v '^#' .env | xargs)
  python3 llm_safety_platform.py --data probes_control_20.json --api openrouter \
    --model x-ai/grok-3-mini --temperature 0.2 --out ctrl_grok_t02.csv --runs 1

Then import it manually (use import_csv from run_ctrl_extra_temps.py).

### 5. When everything is COMPLETE — git push
cd ~/Projects/control-plane-3
git add -A && git commit -m "complete: all probes_500 runs imported, full dataset ready" && git push origin main

### 6. Check leaderboard at https://mtcp.live shows correct model names, no duplicates

---

## CANONICAL MODEL NAME MAP (raw API ID → DB canonical)
See CANONICAL dict in run_ctrl_extra_temps.py for full list.
Key mappings:
  x-ai/grok-3-mini                    → grok-3-mini
  meta-llama/llama-3.3-70b-instruct   → llama-3.3-70b-versatile
  meta-llama/llama-4-maverick         → llama-4-maverick
  meta-llama/llama-4-scout            → llama-4-scout
  deepseek/deepseek-r1                → deepseek-r1
  qwen/qwen-2.5-7b-instruct           → qwen-2.5-7b
  google/gemma-2-27b-it               → google/gemma-2-27b-it
  google/gemini-2.0-flash-001         → gemini-2.0-flash
  cohere/command-r-plus-08-2024       → cohere-command-r-plus
  amazon/nova-lite-v1                 → nova-lite
  amazon/nova-micro-v1                → nova-micro
  amazon/nova-pro-v1                  → nova-pro
  mistralai/mistral-large-2411        → mistral-large
  mistralai/mistral-small-3.2-24b-instruct → mistral-small-3.2
  eu.anthropic.claude-sonnet-4-5-20250929-v1:0 → claude-sonnet-4-20250514
  eu.anthropic.claude-haiku-4-5-20251001-v1:0  → claude-haiku-4-5-20251001
  meta-llama/llama-3.1-70b-instruct   → meta/llama-3.1-70b-instruct
  llama3.1-8b (cerebras)              → cerebras-llama-8b

---

## TARGET
28 COMPLETE models (excluding command-r which is retired) = publishable dataset

## OUTSTANDING (do NOT action until data complete and pushed)
- Chase Jeremy Gomsrud for arXiv cs.AI endorsement — CRITICAL blocker
- Regulatory submission emails — template ready, doesn't need arXiv first
- Python 3.9 → 3.10 upgrade — deadline April 29 2026
- Fix SPF/DKIM (Zoho + GoDaddy)
- Build /pricing page + wire Stripe
- Fix certificate download (FIX_CERTIFICATE_DOWNLOAD.md in ~/Downloads)
