#!/usr/bin/env python3
"""Run ctrl T=0.2/0.5/0.8 for all 27 models (ctrl T=0.0 already in DB).
Sequential: run → import → next. ~1-2 hrs total."""
import subprocess, csv, os
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

CANONICAL = {
    # grok
    "x-ai/grok-3-mini":                                    "grok-3-mini",
    "x-ai/grok-3-mini-beta":                               "grok-3-mini",
    # sonnet
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0":        "claude-sonnet-4-20250514",
    "anthropic/claude-sonnet-4.5":                         "claude-sonnet-4-20250514",
    # haiku
    "eu.anthropic.claude-haiku-4-5-20251001-v1:0":         "claude-haiku-4-5-20251001",
    # llama-3.3
    "llama-3.3-70b-versatile":                             "llama-3.3-70b-versatile",
    "meta-llama/llama-3.3-70b-instruct":                   "llama-3.3-70b-versatile",
    # llama-4
    "meta-llama/llama-4-maverick":                         "llama-4-maverick",
    "meta-llama/llama-4-scout":                            "llama-4-scout",
    # llama-3.1
    "llama-3.1-8b-instant":                                "llama-3.1-8b-instant",
    "meta-llama/llama-3.1-70b-instruct":                   "meta/llama-3.1-70b-instruct",
    "meta/llama-3.1-70b-instruct":                         "meta/llama-3.1-70b-instruct",
    # deepseek
    "deepseek/deepseek-r1":                                "deepseek-r1",
    # qwen
    "qwen/qwen-2.5-7b-instruct":                           "qwen-2.5-7b",
    # qwen3-8b
    "accounts/fireworks/models/qwen3-8b":                  "qwen/qwen3-8b",
    "qwen/qwen3-8b":                                       "qwen/qwen3-8b",
    # gemma
    "google/gemma-2-27b-it":                               "google/gemma-2-27b-it",
    "google/gemma-3-27b-it":                               "google/gemma-3-27b-it",
    # gemini
    "google/gemini-2.0-flash-001":                         "gemini-2.0-flash",
    "google/gemini-2.5-flash":                             "google/gemini-2.5-flash",
    # cerebras
    "llama3.1-8b":                                         "cerebras-llama-8b",
    # cohere
    "cohere/command-r-plus-08-2024":                       "cohere-command-r-plus",
    # nova (OpenRouter)
    "amazon/nova-lite-v1":                                 "nova-lite",
    "amazon/nova-micro-v1":                                "nova-micro",
    "amazon/nova-pro-v1":                                  "nova-pro",
    # nova (Bedrock)
    "amazon.nova-lite-v1:0":                               "nova-lite",
    "amazon.nova-micro-v1:0":                              "nova-micro",
    "amazon.nova-pro-v1:0":                                "nova-pro",
    # mistral
    "magistral-medium-latest":                             "magistral-medium-latest",
    "mistralai/mistral-large-2411":                        "mistral-large",
    "mistral-large":                                       "mistral-large",
    "mistralai/mistral-small-3.2-24b-instruct":            "mistral-small-3.2",
    "mistral-small-3.2":                                   "mistral-small-3.2",
    # openai (same canonical)
    "gpt-3.5-turbo":                                       "gpt-3.5-turbo",
    "gpt-4o":                                              "gpt-4o",
    "gpt-4o-mini":                                         "gpt-4o-mini",
    # replicate (was nvidia, now replicate)
    "ibm-granite/granite-3.3-8b-instruct":                "granite-3.3-8b",
    "ibm/granite-3.3-8b-instruct":                        "granite-3.3-8b",
    "microsoft/phi-4-mini-instruct":                       "phi-4-mini",
}

PROVIDER_FOR_CANONICAL = {
    "grok-3-mini":                   "openrouter",
    "claude-sonnet-4-20250514":      "bedrock",
    "claude-haiku-4-5-20251001":     "bedrock",
    "llama-3.3-70b-versatile":       "groq",
    "llama-4-maverick":              "openrouter",
    "llama-4-scout":                 "openrouter",
    "llama-3.1-8b-instant":          "groq",
    "meta/llama-3.1-70b-instruct":   "openrouter",
    "deepseek-r1":                   "openrouter",
    "qwen-2.5-7b":                   "openrouter",
    "qwen/qwen3-8b":                 "openrouter",
    "google/gemma-2-27b-it":         "openrouter",
    "google/gemma-3-27b-it":         "openrouter",
    "gemini-2.0-flash":              "openrouter",
    "google/gemini-2.5-flash":       "openrouter",
    "cerebras-llama-8b":             "cerebras",
    "cohere-command-r-plus":         "openrouter",
    "nova-lite":                     "openrouter",
    "nova-micro":                    "openrouter",
    "nova-pro":                      "openrouter",
    "magistral-medium-latest":       "mistral",
    "mistral-large":                 "mistral",
    "mistral-small-3.2":             "mistral",
    "gpt-3.5-turbo":                 "openai",
    "gpt-4o":                        "openai",
    "gpt-4o-mini":                   "openai",
}

# (api, model_id_for_provider, canonical_name, temperature, label)
# Skip: command-r (retired). deepseek last (slow reasoning model).
# One entry per model-temp combination.
TEMPS = ["0.2", "0.5", "0.8"]

JOBS = []
for t in TEMPS:
    JOBS += [
        # Fast/cheap models first
        ("groq",       "llama-3.1-8b-instant",                       "llama-3.1-8b-instant",        t),
        ("groq",       "llama-3.3-70b-versatile",                    "llama-3.3-70b-versatile",      t),
        ("openai",     "gpt-3.5-turbo",                              "gpt-3.5-turbo",                t),
        ("openai",     "gpt-4o-mini",                                "gpt-4o-mini",                  t),
        ("openai",     "gpt-4o",                                     "gpt-4o",                       t),
        ("cerebras",   "llama3.1-8b",                                "cerebras-llama-8b",            t),
        # OpenRouter
        ("openrouter", "x-ai/grok-3-mini",                          "grok-3-mini",                  t),
        ("openrouter", "meta-llama/llama-4-scout",                   "llama-4-scout",                t),
        ("openrouter", "meta-llama/llama-4-maverick",                "llama-4-maverick",             t),
        ("openrouter", "meta-llama/llama-3.1-70b-instruct",         "meta/llama-3.1-70b-instruct",  t),
        ("openrouter", "qwen/qwen-2.5-7b-instruct",                 "qwen-2.5-7b",                  t),
        ("openrouter", "qwen/qwen3-8b",                              "qwen/qwen3-8b",                t),
        ("openrouter", "google/gemma-2-27b-it",                      "google/gemma-2-27b-it",        t),
        ("openrouter", "google/gemma-3-27b-it",                      "google/gemma-3-27b-it",        t),
        ("openrouter", "google/gemini-2.0-flash-001",                "gemini-2.0-flash",             t),
        ("openrouter", "google/gemini-2.5-flash",                    "google/gemini-2.5-flash",      t),
        ("openrouter", "cohere/command-r-plus-08-2024",              "cohere-command-r-plus",        t),
        ("openrouter", "amazon/nova-lite-v1",                        "nova-lite",                    t),
        ("openrouter", "amazon/nova-micro-v1",                       "nova-micro",                   t),
        ("openrouter", "amazon/nova-pro-v1",                         "nova-pro",                     t),
        # Mistral
        ("mistral",    "mistral-large",                              "mistral-large",                t),
        ("mistral",    "mistral-small-3.2",                          "mistral-small-3.2",            t),
        ("mistral",    "magistral-medium-latest",                    "magistral-medium-latest",      t),
        # Bedrock (max 1 concurrent — these run sequentially anyway)
        ("bedrock",    "eu.anthropic.claude-haiku-4-5-20251001-v1:0","claude-haiku-4-5-20251001",    t),
        ("bedrock",    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0","claude-sonnet-4-20250514",    t),
        # DeepSeek last (slow reasoning model)
        ("openrouter", "deepseek/deepseek-r1",                       "deepseek-r1",                  t),
    ]


def canonical(raw):
    return CANONICAL.get(raw, raw)


def import_csv(path, canonical_name, conn):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print(f"  EMPTY: {path}")
        return 0

    provider = PROVIDER_FOR_CANONICAL.get(canonical_name, "unknown")

    from collections import defaultdict
    by_temp = defaultdict(list)
    for r in rows:
        by_temp[float(r["temp"])].append(r)

    cur = conn.cursor(cursor_factory=RealDictCursor)
    imported = 0
    for temp, temp_rows in sorted(by_temp.items()):
        cur.execute("""
            SELECT COUNT(*) as cnt FROM runs r JOIN results res ON r.id=res.run_id
            WHERE r.model=%s AND r.dataset='ctrl' AND r.temperature=%s
        """, (canonical_name, temp))
        existing = cur.fetchone()["cnt"]
        if existing >= 20:
            print(f"  SKIP (already {existing} rows): {canonical_name} T={temp}")
            continue

        cur.execute("""
            INSERT INTO runs (model, dataset, temperature, status, api_provider)
            VALUES (%s, 'ctrl', %s, 'completed', %s) RETURNING id
        """, (canonical_name, temp, provider))
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
        print(f"  IMPORTED run_id={run_id}  {canonical_name}  T={temp}  ({len(values)} rows)", flush=True)
        imported += len(values)
    return imported


conn = psycopg2.connect(os.environ["DATABASE_URL"])
total_imported = 0

for api, model_id, canonical_name, temp in JOBS:
    label = canonical_name.replace("/", "_").replace("-", "_").replace(".", "_")
    out_file = f"ctrl_{label}_t{temp.replace('.','')}.csv"

    print(f"\n{'='*60}", flush=True)
    print(f"RUNNING: {canonical_name}  T={temp}  api={api}", flush=True)
    print(f"  model_id={model_id}  out={out_file}", flush=True)

    cmd = [
        "python3", "llm_safety_platform.py",
        "--data", "probes_control_20.json",
        "--api", api,
        "--model", model_id,
        "--temperature", temp,
        "--out", out_file,
        "--runs", "1"
    ]
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"  ERROR: {canonical_name} T={temp} exited {result.returncode} — skipping import.", flush=True)
        continue

    if not os.path.exists(out_file):
        print(f"  Output file not found: {out_file} — skipping.", flush=True)
        continue

    n = import_csv(out_file, canonical_name, conn)
    total_imported += n
    print(f"  +{n} rows imported. Running total: {total_imported}", flush=True)

print(f"\n{'='*60}", flush=True)
print("CTRL COVERAGE AFTER RUN:", flush=True)
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("""
    SELECT model, COUNT(DISTINCT temperature) as temps
    FROM runs WHERE dataset='ctrl'
    GROUP BY model ORDER BY model
""")
for r in cur.fetchall():
    flag = " COMPLETE" if r["temps"] == 4 else f" ← {r['temps']} temps"
    print(f"  {r['model']:<50} ctrl={r['temps']}{flag}", flush=True)

conn.close()
print(f"\nDone. Total rows imported: {total_imported}", flush=True)
