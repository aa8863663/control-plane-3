#!/usr/bin/env python3
"""Run missing probes_500 jobs sequentially, import each to DB immediately after."""
import subprocess, csv, os
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

CANONICAL = {
    "x-ai/grok-3-mini":                                    "grok-3-mini",
    "x-ai/grok-3-mini-beta":                               "grok-3-mini",
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0":        "claude-sonnet-4-20250514",
    "anthropic/claude-sonnet-4.5":                         "claude-sonnet-4-20250514",
    "llama-3.3-70b-versatile":                             "llama-3.3-70b-versatile",
    "accounts/fireworks/models/qwen3-8b":                  "accounts/fireworks/models/qwen3-8b",
}

PROVIDER = {
    "grok-3-mini":                                  "openrouter",
    "claude-sonnet-4-20250514":                     "bedrock",
    "llama-3.3-70b-versatile":                      "groq",
    "accounts/fireworks/models/qwen3-8b":           "fireworks",
}

jobs = [
    ("openrouter", "x-ai/grok-3-mini",                               "0.5,0.8", "grok3mini_missing500"),
    ("anthropic",  "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",   "0.8",     "sonnet45_missing500"),
    ("groq",       "llama-3.3-70b-versatile",                        "0.2,0.5,0.8", "llama33_missing500"),
    ("fireworks",  "accounts/fireworks/models/qwen3-8b",             "0.8",     "qwen3_missing500"),
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

    # Group by temperature in case multiple temps in one file
    from collections import defaultdict
    by_temp = defaultdict(list)
    for r in rows:
        by_temp[float(r["temp"])].append(r)

    cur = conn.cursor(cursor_factory=RealDictCursor)
    imported = 0
    for temp, temp_rows in sorted(by_temp.items()):
        # Check if already in DB
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

for api, model, temps, label in jobs:
    out_file = f"{label}.csv"
    print(f"\n{'='*60}")
    print(f"RUNNING: {model}  temps={temps}  api={api}")

    cmd = [
        "python3", "llm_safety_platform.py",
        "--data", "probes_500.json",
        "--api", api,
        "--model", model,
        "--temperature", temps,
        "--out", out_file,
        "--runs", "1"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  ERROR running {model}:")
        print(result.stderr[-800:] if result.stderr else "(no stderr)")
        print("  Skipping import for this job.")
        continue

    if not os.path.exists(out_file):
        print(f"  Output file not found: {out_file}")
        continue

    with open(out_file) as f:
        row_count = sum(1 for _ in f) - 1
    print(f"  Output: {out_file}  ({row_count} data rows)")

    n = import_csv(out_file, conn)
    print(f"  Imported {n} result rows total")

# Final verification
print(f"\n{'='*60}")
print("FINAL probes_500 state:")
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
    print(f"  {r['model']:<50} T={r['temperature']}  {r['cnt']}{flag}")

conn.close()
