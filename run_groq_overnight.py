#!/usr/bin/env python3
"""Overnight: qwen3-32b, kimi-k2, gpt-oss-120b, gpt-oss-20b via Groq. Zero babysitting."""
import subprocess, csv, os, time
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from collections import defaultdict

CANONICAL = {
    "qwen/qwen3-32b":               "qwen/qwen3-32b",
    "moonshotai/kimi-k2-instruct":  "kimi-k2",
    "openai/gpt-oss-120b":          "gpt-oss-120b",
    "openai/gpt-oss-20b":           "gpt-oss-20b",
}

DATASETS = [
    ("probes_control_20.json", "ctrl",       20),
    ("probes_200.json",        "probes_200", 200),
    ("probes_500.json",        "probes_500", 500),
]
TEMPS = ["0.0", "0.2", "0.5", "0.8"]

MODELS = [
    ("groq", "qwen/qwen3-32b",              "qwen/qwen3-32b"),
    ("groq", "moonshotai/kimi-k2-instruct", "kimi-k2"),
    ("groq", "openai/gpt-oss-120b",         "gpt-oss-120b"),
    ("groq", "openai/gpt-oss-20b",          "gpt-oss-20b"),
]


def import_csv(path, canonical_name, dataset_label, conn):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print(f"  EMPTY: {path}", flush=True)
        return 0
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
        if cur.fetchone()["cnt"] >= len(temp_rows):
            print(f"  SKIP (done): {canonical_name} {dataset_label} T={temp}", flush=True)
            continue
        cur.execute("""
            INSERT INTO runs (model, dataset, temperature, status, api_provider)
            VALUES (%s, %s, %s, 'completed', 'groq') RETURNING id
        """, (canonical_name, dataset_label, temp))
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


def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

conn = get_conn()

for api, model_id, canonical_name in MODELS:
    print(f"\n{'='*60}", flush=True)
    print(f"MODEL: {canonical_name}  api={api}", flush=True)
    model_ok = True

    for data_file, dataset_label, expected_probes in DATASETS:
        for temp in TEMPS:
            if conn.closed:
                conn = get_conn()
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute("""
                    SELECT COUNT(*) as cnt FROM runs r JOIN results res ON r.id=res.run_id
                    WHERE r.model=%s AND r.dataset=%s AND r.temperature=%s
                """, (canonical_name, dataset_label, float(temp)))
            except psycopg2.OperationalError:
                conn = get_conn()
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute("""
                    SELECT COUNT(*) as cnt FROM runs r JOIN results res ON r.id=res.run_id
                    WHERE r.model=%s AND r.dataset=%s AND r.temperature=%s
                """, (canonical_name, dataset_label, float(temp)))
            if cur.fetchone()["cnt"] >= expected_probes:
                print(f"  SKIP (done): {dataset_label} T={temp}", flush=True)
                continue

            label = canonical_name.replace("/","_").replace("-","_").replace(".","_").replace(":","_")
            out_file = f"groq_{label}_{dataset_label}_t{temp.replace('.','')}.csv"
            print(f"\n  RUNNING: {dataset_label} T={temp}", flush=True)

            result = subprocess.run([
                "python3", "llm_safety_platform.py",
                "--data", data_file, "--api", api,
                "--model", model_id, "--temperature", temp,
                "--out", out_file, "--runs", "1"
            ])

            actual_file = f"temp_{float(temp)}_{out_file}"
            if result.returncode != 0 or not os.path.exists(actual_file):
                print(f"  ERROR: {dataset_label} T={temp} failed (returncode={result.returncode})", flush=True)
                model_ok = False
                continue

            import_csv(actual_file, canonical_name, dataset_label, conn)

    print(f"\n  {canonical_name}: {'COMPLETE' if model_ok else 'PARTIAL/ERRORS'}", flush=True)

print("\nAll Groq models done.", flush=True)
conn.close()
