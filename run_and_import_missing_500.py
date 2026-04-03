#!/usr/bin/env python3
"""Run missing probes_500 jobs sequentially, one temperature at a time.
Each job streams output live. Import to DB immediately after each temp completes."""
import subprocess, csv, os, sys
import psycopg2
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
from psycopg2.extras import RealDictCursor, execute_values

CANONICAL = {
    # grok
    "x-ai/grok-3-mini":                                    "grok-3-mini",
    "x-ai/grok-3-mini-beta":                               "grok-3-mini",
    # sonnet
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0":        "claude-sonnet-4-20250514",
    "anthropic/claude-sonnet-4.5":                         "claude-sonnet-4-20250514",
    # llama-3.3 (groq and openrouter)
    "llama-3.3-70b-versatile":                             "llama-3.3-70b-versatile",
    "meta-llama/llama-3.3-70b-instruct":                   "llama-3.3-70b-versatile",
    # llama-4
    "meta-llama/llama-4-maverick":                         "llama-4-maverick",
    "meta-llama/llama-4-scout":                            "llama-4-scout",
    # deepseek
    "deepseek/deepseek-r1":                                "deepseek-r1",
    # qwen
    "qwen/qwen-2.5-7b-instruct":                           "qwen-2.5-7b",
    # qwen3-8b (fireworks or openrouter)
    "accounts/fireworks/models/qwen3-8b":                  "qwen/qwen3-8b",
    "qwen/qwen3-8b":                                       "qwen/qwen3-8b",
    # gemma (same canonical name)
    "google/gemma-2-27b-it":                               "google/gemma-2-27b-it",
    # replicate models
    "ibm-granite/granite-3.3-8b-instruct":                 "granite-3.3-8b",
    "ibm/granite-3.3-8b-instruct":                         "granite-3.3-8b",
    "microsoft/phi-4-mini-instruct":                       "phi-4-mini",
    # mistral
    "magistral-medium-latest":                             "magistral-medium-latest",
}

PROVIDER = {
    "grok-3-mini":                                  "openrouter",
    "claude-sonnet-4-20250514":                     "bedrock",
    "llama-3.3-70b-versatile":                      "openrouter",
    "llama-4-maverick":                             "openrouter",
    "llama-4-scout":                                "openrouter",
    "deepseek-r1":                                  "openrouter",
    "qwen-2.5-7b":                                  "openrouter",
    "google/gemma-2-27b-it":                        "openrouter",
    "accounts/fireworks/models/qwen3-8b":           "fireworks",
    "granite-3.3-8b":                               "nvidia",
    "phi-4-mini":                                   "nvidia",
    "magistral-medium-latest":                      "mistral",
}

# Each entry: (api, model, temperature, output_label)
# One temperature per job so failures don't block others
jobs = [
    ("nvidia", "ibm/granite-3.3-8b-instruct",                      "0.0", "granite_t00"),
    ("nvidia", "ibm/granite-3.3-8b-instruct",                      "0.2", "granite_t02"),
    ("nvidia", "ibm/granite-3.3-8b-instruct",                      "0.5", "granite_t05"),
    ("nvidia", "ibm/granite-3.3-8b-instruct",                      "0.8", "granite_t08"),
]

def canonical(raw):
    return CANONICAL.get(raw, raw)

def import_csv(path, conn):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print(f"  EMPTY: {path}")
        return 0

    raw_model = rows[0]["model"].strip()
    can_model = canonical(raw_model)
    provider  = PROVIDER.get(can_model, "unknown")

    from collections import defaultdict
    by_temp = defaultdict(list)
    for r in rows:
        by_temp[float(r["temp"])].append(r)

    cur = conn.cursor(cursor_factory=RealDictCursor)
    imported = 0
    for temp, temp_rows in sorted(by_temp.items()):
        cur.execute("""
            SELECT COUNT(*) as cnt FROM runs r JOIN results res ON r.id=res.run_id
            WHERE r.model=%s AND r.dataset='probes_500' AND r.temperature=%s
        """, (can_model, temp))
        existing = cur.fetchone()["cnt"]
        if existing >= 500:
            print(f"  SKIP (already {existing} rows): {can_model} T={temp}")
            continue

        cur.execute("""
            INSERT INTO runs (model, dataset, temperature, status, api_provider)
            VALUES (%s, 'probes_500', %s, 'completed', %s) RETURNING id
        """, (can_model, temp, provider))
        run_id = cur.fetchone()["id"]

        values = [
            (run_id, r["probe_id"], float(r["temp"]),
             r["t1"].upper()=="TRUE", r["t2"].upper()=="TRUE", r["t3"].upper()=="TRUE",
             r["outcome"], int(r["recovery_latency"] or 0),
             int(r["prompt_tokens"] or 0), int(r["completion_tokens"] or 0),
             int(r["total_tokens"] or 0), r.get("vector",""))
            for r in temp_rows
        ]
        execute_values(cur, """
            INSERT INTO results
              (run_id, probe_id, temperature, t1, t2, t3, outcome, recovery_latency,
               prompt_tokens, completion_tokens, total_tokens, vector)
            VALUES %s
        """, values)
        conn.commit()
        print(f"  IMPORTED run_id={run_id}  {can_model}  T={temp}  ({len(values)} rows)")
        imported += len(values)
    return imported

conn = psycopg2.connect(os.environ["DATABASE_URL"])

for api, model, temp, label in jobs:
    out_file = f"{label}.csv"
    print(f"\n{'='*60}", flush=True)
    print(f"RUNNING: {model}  T={temp}  api={api}", flush=True)
    print(f"Output: {out_file}", flush=True)

    cmd = [
        "python3", "llm_safety_platform.py",
        "--data", "probes_500.json",
        "--api", api,
        "--model", model,
        "--temperature", temp,
        "--out", out_file,
        "--runs", "1"
    ]
    # Stream output live — no capture_output
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"  ERROR: {model} T={temp} exited with code {result.returncode} — skipping import.", flush=True)
        continue

    if not os.path.exists(out_file):
        print(f"  Output file not found: {out_file} — skipping import.", flush=True)
        continue

    with open(out_file) as f:
        row_count = sum(1 for _ in f) - 1
    print(f"  {row_count} data rows in {out_file}", flush=True)

    n = import_csv(out_file, conn)
    print(f"  Imported {n} result rows to DB.", flush=True)

print(f"\n{'='*60}", flush=True)
print("FINAL probes_500 state:", flush=True)
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("""
    SELECT model, temperature, COUNT(*) as cnt
    FROM runs r JOIN results res ON r.id=res.run_id
    WHERE r.dataset='probes_500'
    GROUP BY model, temperature
    ORDER BY model, temperature
""")
for r in cur.fetchall():
    flag = " ✓" if r["cnt"] == 500 else f" ← {r['cnt']} rows"
    print(f"  {r['model']:<50} T={r['temperature']}  {r['cnt']}{flag}", flush=True)

conn.close()
