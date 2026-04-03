# CLAUDE CODE HANDOFF — SESSION 2
# Generated: 2026-03-31 ~19:30 BST
# Read every word before touching anything.

---

## IDENTITY & LEGAL

- Public name: **A. Abby** — NEVER write "Aimee Stanyer" in any output, commit, or file
- ICO case open vs OpenAI — route ALL grok via openrouter, NEVER xai direct
- DO NOT contact Credo AI, Monitaur, Arthur AI, Luminos until arXiv is live
- NEVER publish or expose: probes_200.json, probes_control_20.json, probes_500.json
- DO NOT reuse: emergency_fix.sh, diagnose_leaderboard.py

---

## PROJECT LOCATION

- Repo: ~/Projects/control-plane-3
- DB: Neon PostgreSQL EU Frankfurt — credentials in .env
- GitHub: github.com/aa8863663/control-plane-3 (private)
- Live site: https://mtcp.live

---

## CODE RULES — DO NOT DEVIATE

- Python 3.9 — use Optional[] not X | None
- psycopg2: use %s not ?
- id and run_id columns are TEXT — always quote in WHERE clauses
- recovery_latency is TEXT — cast to FLOAT for AVG
- Bedrock: max 1 concurrent request, eu. prefix required on all model names

---

## WHAT IS CURRENTLY RUNNING (started ~19:15 BST 2026-03-31)

30 benchmark runs were launched in parallel as background processes writing to log files in logs/.
An auto-importer script is also running — it watches for CSVs every 30 seconds and imports
each one to the DB the moment it lands. You do NOT need to manually import anything.

### Running processes (check with: ps aux | grep llm_safety | grep -v grep | wc -l)
Target: 30 llm_safety_platform.py processes. Count will drop as jobs complete.

### Auto-importer
Check its output with:
  cat /private/tmp/claude-501/-Users-aimeestanyer/d622b4d0-ef31-4495-b2ab-6877e5e2c29a/tasks/bwjkooas8.output

It will print "IMPORTED..." for each CSV it processes and "All 39 files processed." when done.

### CSVs being generated (check with: ls ~/Projects/control-plane-3/*_t0*.csv 2>/dev/null)

OpenRouter jobs:
  grok3mini_t05.csv, grok3mini_t08.csv
  deepseek_t00.csv, deepseek_t02.csv, deepseek_t05.csv, deepseek_t08.csv
  maverick_t00.csv, maverick_t02.csv, maverick_t05.csv, maverick_t08.csv
  scout_t00.csv, scout_t02.csv, scout_t05.csv, scout_t08.csv
  qwen25_t00.csv, qwen25_t02.csv, qwen25_t05.csv, qwen25_t08.csv
  llama33_t02.csv, llama33_t05.csv, llama33_t08.csv
  gemma2_ctrl.csv, gemma2_p200_t00.csv, gemma2_p200_t02.csv, gemma2_p200_t05.csv, gemma2_p200_t08.csv

Bedrock:
  sonnet45_t08.csv

Mistral:
  magistral_t00.csv, magistral_t02.csv, magistral_t05.csv, magistral_t08.csv

Nvidia:
  granite_t00.csv, granite_t02.csv, granite_t05.csv, granite_t08.csv
  phi4mini_t00.csv, phi4mini_t02.csv, phi4mini_t05.csv, phi4mini_t08.csv

### CANONICAL model name mappings (what llm_safety writes vs what goes in DB)
  x-ai/grok-3-mini                    → grok-3-mini
  meta-llama/llama-3.3-70b-instruct   → llama-3.3-70b-versatile
  meta-llama/llama-4-maverick         → llama-4-maverick
  meta-llama/llama-4-scout            → llama-4-scout
  deepseek/deepseek-r1                → deepseek-r1
  qwen/qwen-2.5-7b-instruct           → qwen-2.5-7b
  google/gemma-2-27b-it               → google/gemma-2-27b-it
  ibm/granite-3.3-8b-instruct         → granite-3.3-8b
  microsoft/phi-4-mini-instruct       → phi-4-mini
  eu.anthropic.claude-sonnet-4-5-20250929-v1:0 → claude-sonnet-4-20250514
  magistral-medium-latest             → magistral-medium-latest

---

## DB STATE AT SESSION START (19:10 BST)

COMPLETE (ctrl=1, p200=4, p500=4):
  cerebras-llama-8b, claude-haiku-4-5-20251001, cohere-command-r-plus,
  gemini-2.0-flash, google/gemini-2.5-flash, google/gemma-3-27b-it,
  gpt-3.5-turbo, gpt-4o, gpt-4o-mini, llama-3.1-8b-instant,
  meta/llama-3.1-70b-instruct, mistral-large, mistral-small-3.2,
  nova-lite, nova-micro, nova-pro

PARTIAL (in progress — being filled by running jobs):
  grok-3-mini          ctrl=1 p200=4 p500=2  → adding T=0.5, T=0.8
  claude-sonnet-4-20250514  ctrl=1 p200=4 p500=3  → adding T=0.8
  llama-3.3-70b-versatile   ctrl=1 p200=4 p500=1  → adding T=0.2, T=0.5, T=0.8
  accounts/fireworks/models/qwen3-8b  ctrl=- p200=- p500=3  → NOTE: still needs ctrl + p200 (not in current batch)

INCOMPLETE (has p500 but NO ctrl, NO p200 — being filled):
  google/gemma-2-27b-it  ctrl=- p200=- p500=4  → adding ctrl T=0.0 + p200 all 4 temps

MISSING p500 (being filled by running jobs):
  deepseek-r1, granite-3.3-8b, llama-4-maverick, llama-4-scout,
  magistral-medium-latest, phi-4-mini, qwen-2.5-7b

RETIRED — skip always:
  command-r

---

## WHAT TO DO WHEN YOU ARRIVE

### Step 1 — Check if auto-importer is still running
  ps aux | grep "python3 << " | grep -v grep
  cat /private/tmp/claude-501/-Users-aimeestanyer/d622b4d0-ef31-4495-b2ab-6877e5e2c29a/tasks/bwjkooas8.output | tail -30

### Step 2 — Check how many CSVs have landed and been imported
  ls ~/Projects/control-plane-3/maverick_t00.csv ~/Projects/control-plane-3/scout_t00.csv 2>&1
  # Run the full coverage query (Step 3) to see DB state

### Step 3 — Coverage query (run anytime to check state)
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
      flag = 'COMPLETE' if r[3] == 4 else ('PARTIAL' if r[3] else 'MISSING')
      print(f"{r[0]:<50} ctrl={ctrl} p200={p200} p500={p500}  {flag}")
  conn.close()
  PYEOF

### Step 4 — If any job failed (CSV missing after an hour), re-run it
  # Check logs for errors:
  tail -20 ~/Projects/control-plane-3/logs/maverick_t00.log
  # Re-run individually (example):
  cd ~/Projects/control-plane-3 && export $(grep -v '^#' .env | xargs)
  python3 llm_safety_platform.py --data probes_500.json --api openrouter \
    --model meta-llama/llama-4-maverick --temperature 0.0 --out maverick_t00.csv --runs 1

### Step 5 — If auto-importer has stopped, import manually
  # run_and_import_missing_500.py has the import_csv function
  # Or import a specific CSV:
  cd ~/Projects/control-plane-3 && export $(grep -v '^#' .env | xargs) && python3 << 'PYEOF'
  import csv, os, psycopg2
  from psycopg2.extras import RealDictCursor, execute_values
  # ... use import_csv function from run_and_import_missing_500.py
  PYEOF

### Step 6 — STILL OUTSTANDING after this batch (NOT in current runs)
  accounts/fireworks/models/qwen3-8b still needs ctrl and probes_200 runs.
  Run via fireworks api, model accounts/fireworks/models/qwen3-8b.

### Step 7 — When all models are COMPLETE
  Run coverage query. Every model except command-r should show COMPLETE.
  Target: 28-29 COMPLETE models = publishable dataset.

### Step 8 — Git push
  cd ~/Projects/control-plane-3
  git add -A && git commit -m "complete: all probes_500 runs imported, full dataset ready" && git push origin main

---

## OUTSTANDING TASKS (do NOT action until data is complete and pushed)

- Chase Jeremy Gomsrud for arXiv cs.AI endorsement — CRITICAL blocker for publication
- Regulatory submission emails — template ready, doesn't need arXiv first
- Python 3.9 → 3.10 upgrade — deadline April 29 2026
- Fix SPF/DKIM (Zoho + GoDaddy)
- Build /pricing page + wire Stripe
- Fix certificate download (FIX_CERTIFICATE_DOWNLOAD.md in ~/Downloads)
- Check leaderboard at https://mtcp.live shows canonical model names, no duplicates

---

## DEPLOY COMMAND (when needed)
  cd ~/Projects/control-plane-3
  git add . && git commit -m "fix: description" && git push origin main
  Render auto-deploys in ~3-4 min.

---
END OF HANDOFF
