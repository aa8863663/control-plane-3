#!/usr/bin/env python3
"""Overnight script: run 5 new models across all datasets (ctrl, p200, p500) x 4 temps.
Handles rate limits automatically. Auto-imports to DB. Zero babysitting required."""
import subprocess, csv, os, time
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from collections import defaultdict

CANONICAL = {
    # new models this script adds
    "qwen/qwen3-32b":                                   "qwen/qwen3-32b",
    "nousresearch/hermes-3-llama-3.1-405b:free":        "hermes-3-405b",
    "nvidia/nemotron-3-super-120b-a12b:free":           "nemotron-3-super-120b",
    "openai/gpt-oss-120b:free":                         "gpt-oss-120b",
    "deepseek/deepseek-r1-distill-qwen-32b":            "deepseek-r1-distill-32b",
    # existing models (for safety)
    "x-ai/grok-3-mini":                                 "grok-3-mini",
    "meta-llama/llama-3.3-70b-instruct":                "llama-3.3-70b-versatile",
    "deepseek/deepseek-r1":                             "deepseek-r1",
    "qwen/qwen-2.5-7b-instruct":                        "qwen-2.5-7b",
    "qwen/qwen3-8b":                                    "qwen/qwen3-8b",
    "google/gemini-2.0-flash-001":                      "gemini-2.0-flash",
    "cohere/command-r-plus-08-2024":                    "cohere-command-r-plus",
    "amazon/nova-lite-v1":                              "nova-lite",
    "amazon/nova-micro-v1":                             "nova-micro",
    "amazon/nova-pro-v1":                               "nova-pro",
}

PROVIDER_FOR_CANONICAL = {
    "qwen/qwen3-32b":           "groq",
    "hermes-3-405b":            "openrouter",
    "nemotron-3-super-120b":    "openrouter",
    "gpt-oss-120b":             "openrouter",
    "deepseek-r1-distill-32b":  "openrouter",
}

DATASETS = [
    ("probes_control_20.json", "ctrl",        20),
    ("probes_200.json",        "probes_200",  200),
    ("probes_500.json",        "probes_500",  500),
]
TEMPS = ["0.0", "0.2", "0.5", "0.8"]

# Models: (api, model_id, canonical_name)
# Groq first (fast), then OpenRouter free, then paid OpenRouter last
MODELS = [
    ("groq",       "qwen/qwen3-32b",                            "qwen/qwen3-32b"),
    ("openrouter", "deepseek/deepseek-r1-distill-qwen-32b",     "deepseek-r1-distill-32b"),
    ("openrouter", "nousresearch/hermes-3-llama-3.1-405b:free", "hermes-3-405b"),
    ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free",    "nemotron-3-super-120b"),
    ("openrouter", "openai/gpt-oss-120b:free",                  "gpt-oss-120b"),
]


def import_csv(path, canonical_name, dataset_label, conn):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print(f"  EMPTY: {path}", flush=True)
        return 0

    provider = PROVIDER_FOR_CANONICAL.get(canonical_name, "unknown")
    by_temp = defaultdict(list)
    for r in rows:
        by_temp[float(r["temp"])].append(r)

    cur = conn.cursor(cursor_factory=RealDictCursor)
    imported = 0
    for temp, temp_rows in sorted(by_temp.items()):
        cur.execute("""
            SELECT COUNT(*) as cnt FROM runs r JOIN results res ON r.id=res.run_id
            WHERE r.model=%s AND r.dataset=%s AND r.temperature=%s
        """, (canonical_name, dataset_label, temp))
        existing = cur.fetchone()["cnt"]
        expected = len(temp_rows)
        if existing >= expected:
            print(f"  SKIP (already {existing} rows): {canonical_name} {dataset_label} T={temp}", flush=True)
            continue

        cur.execute("""
            INSERT INTO runs (model, dataset, temperature, status, api_provider)
            VALUES (%s, %s, %s, 'completed', %s) RETURNING id
        """, (canonical_name, dataset_label, temp, provider))
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
        print(f"  IMPORTED run_id={run_id}  {canonical_name}  {dataset_label}  T={temp}  ({len(values)} rows)", flush=True)
        imported += len(values)
    return imported


conn = psycopg2.connect(os.environ["DATABASE_URL"])
total_imported = 0
model_results = {}

for api, model_id, canonical_name in MODELS:
    print(f"\n{'='*60}", flush=True)
    print(f"MODEL: {canonical_name}  api={api}", flush=True)
    model_ok = True

    for data_file, dataset_label, expected_probes in DATASETS:
        for temp in TEMPS:
            # Check if already done
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT COUNT(*) as cnt FROM runs r JOIN results res ON r.id=res.run_id
                WHERE r.model=%s AND r.dataset=%s AND r.temperature=%s
            """, (canonical_name, dataset_label, float(temp)))
            existing = cur.fetchone()["cnt"]
            if existing >= expected_probes:
                print(f"  SKIP (done): {dataset_label} T={temp}  ({existing} rows)", flush=True)
                continue

            label = canonical_name.replace("/","_").replace("-","_").replace(".","_").replace(":","_")
            out_file = f"new_{label}_{dataset_label}_t{temp.replace('.','')}.csv"

            print(f"\n  RUNNING: {dataset_label} T={temp}", flush=True)
            cmd = [
                "python3", "llm_safety_platform.py",
                "--data", data_file,
                "--api", api,
                "--model", model_id,
                "--temperature", temp,
                "--out", out_file,
                "--runs", "1"
            ]
            result = subprocess.run(cmd)

            if result.returncode != 0:
                print(f"  ERROR: exit {result.returncode} — skipping {dataset_label} T={temp}", flush=True)
                model_ok = False
                continue

            if not os.path.exists(out_file):
                print(f"  ERROR: no output file — skipping", flush=True)
                model_ok = False
                continue

            n = import_csv(out_file, canonical_name, dataset_label, conn)
            total_imported += n

    model_results[canonical_name] = model_ok
    status = "COMPLETE" if model_ok else "PARTIAL/ERRORS"
    print(f"\n  {canonical_name}: {status}", flush=True)

print(f"\n{'='*60}", flush=True)
print("FINAL SUMMARY:", flush=True)
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("""
SELECT model,
  MAX(CASE WHEN dataset='ctrl' THEN temps END) as ctrl,
  MAX(CASE WHEN dataset='probes_200' THEN temps END) as p200,
  MAX(CASE WHEN dataset='probes_500' THEN temps END) as p500
FROM (
  SELECT model, dataset, COUNT(DISTINCT temperature) as temps
  FROM runs GROUP BY model, dataset
) x
WHERE model IN %s
GROUP BY model ORDER BY model
""", (tuple(c for _,_,c in MODELS),))
for r in cur.fetchall():
    ctrl = str(r[1]) if r[1] else '-'
    p200 = str(r[2]) if r[2] else '-'
    p500 = str(r[3]) if r[3] else '-'
    complete = (r[1]==4 and r[2]==4 and r[3]==4)
    flag = 'COMPLETE' if complete else 'PARTIAL'
    print(f"  {r[0]:<50} ctrl={ctrl} p200={p200} p500={p500}  {flag}", flush=True)

conn.close()
print(f"\nTotal rows imported: {total_imported}", flush=True)
print("Done.", flush=True)
