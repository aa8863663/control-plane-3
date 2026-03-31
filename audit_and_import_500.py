#!/usr/bin/env python3
"""Audit all 501-row CSVs vs DB, then import anything missing."""

import csv, os, glob
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

# Canonical name map: CSV model name -> DB canonical name
# (keeps DB consistent with existing normalized names)
CANONICAL = {
    "anthropic/claude-haiku-4.5":                           "claude-haiku-4-5-20251001",
    "eu.anthropic.claude-haiku-4-5-20251001-v1:0":          "claude-haiku-4-5-20251001",
    "anthropic/claude-sonnet-4.5":                          "claude-sonnet-4-20250514",
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0":         "claude-sonnet-4-20250514",
    "command-r-plus-08-2024":                               "cohere-command-r-plus",
    "google/gemini-2.0-flash-001":                          "gemini-2.0-flash",
    "gemini-2.5-flash":                                     "google/gemini-2.5-flash",
    "openai/gpt-3.5-turbo":                                 "gpt-3.5-turbo",
    "openai/gpt-4o":                                        "gpt-4o",
    "x-ai/grok-3-mini":                                     "grok-3-mini",
    "x-ai/grok-3-mini-beta":                                "grok-3-mini",
    "llama3.1-8b":                                          "cerebras-llama-8b",
    "amazon.nova-lite-v1:0":                                "nova-lite",
    "amazon/nova-lite-v1":                                  "nova-lite",
    "amazon.nova-micro-v1:0":                               "nova-micro",
    "amazon.nova-pro-v1:0":                                 "nova-pro",
    "amazon/nova-pro-v1":                                   "nova-pro",
    "mistral-large-latest":                                 "mistral-large",
    "mistral-small-latest":                                 "mistral-small-3.2",
    "mistralai/mistral-small-3.2-24b-instruct":             "mistral-small-3.2",
}

# Provider map for new models being imported
PROVIDER = {
    "accounts/fireworks/models/qwen3-8b":   "fireworks",
    "claude-haiku-4-5-20251001":            "bedrock",
    "claude-sonnet-4-20250514":             "bedrock",
    "cohere-command-r-plus":                "cohere",
    "gemini-2.0-flash":                     "google",
    "google/gemini-2.5-flash":              "google",
    "google/gemma-2-27b-it":               "nvidia",
    "google/gemma-3-27b-it":               "nvidia",
    "gpt-3.5-turbo":                        "openai",
    "gpt-4o":                               "openai",
    "gpt-4o-mini":                          "openai",
    "grok-3-mini":                          "openrouter",
    "llama-3.1-8b-instant":                "groq",
    "llama-3.3-70b-versatile":             "groq",
    "cerebras-llama-8b":                    "cerebras",
    "meta/llama-3.1-70b-instruct":         "nvidia",
    "mistral-large":                        "mistral",
    "mistral-small-3.2":                    "mistral",
    "nova-lite":                            "bedrock",
    "nova-micro":                           "bedrock",
    "nova-pro":                             "bedrock",
}

def canonical(raw):
    return CANONICAL.get(raw, raw)

def read_csv_meta(path):
    """Return (csv_model, canonical_model, temperature) from first data row."""
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            model_raw = row.get("model", "").strip()
            temp = float(row.get("temp", 0))
            return model_raw, canonical(model_raw), temp
    return None, None, None

def read_csv_rows(path, canonical_model):
    """Return list of result dicts ready for DB insert."""
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "probe_id":          row["probe_id"],
                "temperature":       float(row["temp"]),
                "t1":                row["t1"].upper() == "TRUE",
                "t2":                row["t2"].upper() == "TRUE",
                "t3":                row["t3"].upper() == "TRUE",
                "outcome":           row["outcome"],
                "recovery_latency":  int(row["recovery_latency"]) if row["recovery_latency"] else 0,
                "prompt_tokens":     int(row["prompt_tokens"]) if row["prompt_tokens"] else 0,
                "completion_tokens": int(row["completion_tokens"]) if row["completion_tokens"] else 0,
                "total_tokens":      int(row["total_tokens"]) if row["total_tokens"] else 0,
                "vector":            row.get("vector", ""),
                "model":             canonical_model,
            })
    return rows

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor(cursor_factory=RealDictCursor)

# Load existing probes_500 runs
cur.execute("""
    SELECT model, temperature, COUNT(*) as cnt
    FROM runs r JOIN results res ON r.id = res.run_id
    WHERE r.dataset = 'probes_500'
    GROUP BY model, temperature
""")
in_db = {}
for row in cur.fetchall():
    in_db[(row["model"], float(row["temperature"]))] = row["cnt"]

# Find all 501-row CSVs
csv_files = []
for path in sorted(glob.glob("/Users/aimeestanyer/Projects/control-plane-3/**/*.csv", recursive=True)):
    try:
        with open(path) as f:
            lines = f.readlines()
        if len(lines) == 501:
            csv_files.append(path)
    except:
        pass

print(f"\n{'MODEL':<45} {'TEMP':<6} {'IN DB':<8} {'FILE'}")
print("-" * 110)

to_import = []
for path in csv_files:
    raw_model, can_model, temp = read_csv_meta(path)
    if not raw_model:
        continue
    key = (can_model, temp)
    exists = key in in_db
    status = f"YES ({in_db[key]} rows)" if exists else "NO"
    fname = os.path.basename(path)
    print(f"{can_model:<45} {temp:<6} {status:<15} {fname}")
    if not exists:
        to_import.append((path, raw_model, can_model, temp))

print(f"\n{'='*110}")
print(f"Total 501-row files: {len(csv_files)}")
print(f"Already in DB:       {len(csv_files) - len(to_import)}")
print(f"To import:           {len(to_import)}")

if not to_import:
    print("\nAll files already in DB.")
    conn.close()
    exit(0)

print("\n--- IMPORTING MISSING RUNS ---\n")

imported = 0
errors = 0
for path, raw_model, can_model, temp in to_import:
    try:
        rows = read_csv_rows(path, can_model)
        provider = PROVIDER.get(can_model, "unknown")
        fname = os.path.basename(path)

        # Insert run row
        cur.execute("""
            INSERT INTO runs (model, dataset, temperature, status, api_provider)
            VALUES (%s, 'probes_500', %s, 'completed', %s)
            RETURNING id
        """, (can_model, temp, provider))
        run_id = cur.fetchone()["id"]

        # Bulk insert results
        values = [
            (run_id, r["probe_id"], r["temperature"], r["t1"], r["t2"], r["t3"],
             r["outcome"], r["recovery_latency"], r["prompt_tokens"],
             r["completion_tokens"], r["total_tokens"], r["vector"])
            for r in rows
        ]
        execute_values(cur, """
            INSERT INTO results
              (run_id, probe_id, temperature, t1, t2, t3, outcome, recovery_latency,
               prompt_tokens, completion_tokens, total_tokens, vector)
            VALUES %s
        """, values)
        conn.commit()
        print(f"  IMPORTED  run_id={run_id}  {can_model} T={temp}  ({len(rows)} rows)  [{fname}]")
        imported += 1
    except Exception as e:
        conn.rollback()
        print(f"  ERROR     {can_model} T={temp}  {os.path.basename(path)}: {e}")
        errors += 1

print(f"\nDone. Imported: {imported}  Errors: {errors}")

# Final count
cur.execute("""
    SELECT COUNT(DISTINCT model) as models, COUNT(*) as runs
    FROM runs WHERE dataset = 'probes_500'
""")
r = cur.fetchone()
print(f"probes_500 now: {r['models']} distinct models, {r['runs']} runs total")

conn.close()
