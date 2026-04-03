#!/usr/bin/env python3
"""
CONTROL-PLANE-3 — Step 1 import script
Imports all CSV files listed in the handoff.
Rules:
  - Python 3.9 (Optional[] not X|None)
  - psycopg2 %s placeholders
  - ON CONFLICT DO NOTHING on results inserts
  - Overrides model name from CSV with canonical DB name
  - recovery_latency stored as TEXT
  - Skips any (model, dataset, temperature) that already has a run in DB
"""

import csv
import os
import sys
from typing import Optional, List, Tuple

import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("ERROR: DATABASE_URL not set")

BASE = "/Users/aimeestanyer/Projects/control-plane-3"

# (filename, dataset, canonical_model, temperature)
IMPORTS: List[Tuple[str, str, str, float]] = [
    # ── magistral-medium-latest ctrl (T=0.0 already in DB, p200 all 4 already in DB)
    ("temp_0.2_ctrl_magistral_medium_latest_t02.csv", "ctrl",       "magistral-medium-latest", 0.2),
    ("temp_0.5_ctrl_magistral_medium_latest_t05.csv", "ctrl",       "magistral-medium-latest", 0.5),
    ("temp_0.8_ctrl_magistral_medium_latest_t08.csv", "ctrl",       "magistral-medium-latest", 0.8),
    ("temp_0.2_magistral.csv",                        "probes_200", "magistral-medium-latest", 0.2),
    ("temp_0.5_magistral.csv",                        "probes_200", "magistral-medium-latest", 0.5),
    ("temp_0.8_magistral.csv",                        "probes_200", "magistral-medium-latest", 0.8),
    ("temp_0.0_magistral_t00.csv",                    "probes_500", "magistral-medium-latest", 0.0),

    # ── ibm/granite-3.3-8b-instruct
    ("temp_0.0_granite_results.csv", "probes_200", "ibm/granite-3.3-8b-instruct", 0.0),
    ("temp_0.2_granite_results.csv", "probes_200", "ibm/granite-3.3-8b-instruct", 0.2),
    ("temp_0.5_granite_results.csv", "probes_200", "ibm/granite-3.3-8b-instruct", 0.5),
    ("temp_0.8_granite_results.csv", "probes_200", "ibm/granite-3.3-8b-instruct", 0.8),
    ("temp_0.0_ctrl_granite.csv",    "ctrl",       "ibm/granite-3.3-8b-instruct", 0.0),

    # ── microsoft/phi-4-mini-instruct
    ("temp_0.0_phi4_mini_results.csv", "probes_200", "microsoft/phi-4-mini-instruct", 0.0),
    ("temp_0.2_phi4_mini_results.csv", "probes_200", "microsoft/phi-4-mini-instruct", 0.2),
    ("temp_0.5_phi4_mini_results.csv", "probes_200", "microsoft/phi-4-mini-instruct", 0.5),
    ("temp_0.8_phi4_mini_results.csv", "probes_200", "microsoft/phi-4-mini-instruct", 0.8),
    ("temp_0.0_ctrl_phi4_results.csv", "ctrl",       "microsoft/phi-4-mini-instruct", 0.0),

    # ── deepseek-reasoner (ctrl file: model string may be deepseek-r1 in CSV — overridden below)
    ("temp_0.0_deepseek_r1_full.csv", "probes_200", "deepseek-reasoner", 0.0),
    ("temp_0.2_deepseek_r1_full.csv", "probes_200", "deepseek-reasoner", 0.2),
    ("temp_0.5_deepseek_r1_full.csv", "probes_200", "deepseek-reasoner", 0.5),
    ("temp_0.8_deepseek_r1_full.csv", "probes_200", "deepseek-reasoner", 0.8),
    ("temp_0.0_ctrl_deepseek_r1.csv", "ctrl",       "deepseek-reasoner", 0.0),

    # ── kimi-k2 (CSV model string: accounts/fireworks/models/kimi-k2-instruct-0905)
    ("temp_0.0_kimi.csv",     "probes_200", "kimi-k2", 0.0),
    ("temp_0.2_kimi.csv",     "probes_200", "kimi-k2", 0.2),
    ("temp_0.5_kimi.csv",     "probes_200", "kimi-k2", 0.5),
    ("temp_0.8_kimi.csv",     "probes_200", "kimi-k2", 0.8),
    ("temp_0.0_ctrl_kimi.csv","ctrl",       "kimi-k2", 0.0),

    # ── qwen/qwen3-32b ctrl only (p200+p500 → Step 3 API runs)
    ("temp_0.0_new_qwen_qwen3_32b_ctrl_t00.csv",  "ctrl", "qwen/qwen3-32b", 0.0),
    ("temp_0.2_groq_qwen_qwen3_32b_ctrl_t02.csv", "ctrl", "qwen/qwen3-32b", 0.2),
    ("temp_0.5_groq_qwen_qwen3_32b_ctrl_t05.csv", "ctrl", "qwen/qwen3-32b", 0.5),
    ("temp_0.8_groq_qwen_qwen3_32b_ctrl_t08.csv", "ctrl", "qwen/qwen3-32b", 0.8),

    # ── nvidia/llama-3.1-nemotron-70b-instruct (p200 → Step 3 API runs)
    ("temp_0.0_ctrl_nvidia_llama.csv",  "ctrl",       "nvidia/llama-3.1-nemotron-70b-instruct", 0.0),
    ("temp_0.0_nvidia_llama_500.csv",   "probes_500", "nvidia/llama-3.1-nemotron-70b-instruct", 0.0),
    ("temp_0.2_nvidia_llama_500.csv",   "probes_500", "nvidia/llama-3.1-nemotron-70b-instruct", 0.2),
    ("temp_0.5_nvidia_llama_500.csv",   "probes_500", "nvidia/llama-3.1-nemotron-70b-instruct", 0.5),
    ("temp_0.8_nvidia_llama_500.csv",   "probes_500", "nvidia/llama-3.1-nemotron-70b-instruct", 0.8),

    # ── claude-sonnet-4-5-20250929
    # NCA/CG probe IDs confirmed as probes_500 category prefixes → import as probes_500
    ("temp_0.0_ctrl_sonnet45.csv",          "ctrl",       "claude-sonnet-4-5-20250929", 0.0),
    ("temp_0.0_claudesonnet45_500.csv",     "probes_500", "claude-sonnet-4-5-20250929", 0.0),
    ("temp_0.2_claudesonnet45_500.csv",     "probes_500", "claude-sonnet-4-5-20250929", 0.2),
    ("temp_0.5_sonnet45_500_missing.csv",   "probes_500", "claude-sonnet-4-5-20250929", 0.5),
    ("temp_0.8_sonnet45_t08.csv",           "probes_500", "claude-sonnet-4-5-20250929", 0.8),
]

# Expected row counts per dataset (for validation warnings)
EXPECTED_ROWS = {
    "ctrl":       20,
    "probes_200": 200,
    "probes_500": 500,
}

CSV_COLS = [
    "probe_id", "run_id", "temp", "t1", "t2", "t3",
    "outcome", "recovery_latency", "prompt_tokens",
    "completion_tokens", "total_tokens", "model", "vector",
]


def run_already_exists(cur, model: str, dataset: str, temperature: float) -> Optional[str]:
    cur.execute(
        "SELECT id FROM runs WHERE model = %s AND dataset = %s AND temperature = %s LIMIT 1",
        (model, dataset, temperature),
    )
    row = cur.fetchone()
    return row[0] if row else None


def insert_run(cur, model: str, dataset: str, temperature: float, probe_count: int) -> str:
    cur.execute(
        """
        INSERT INTO runs (model, temperature, status, dataset, probe_count)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (model, temperature, "completed", dataset, probe_count),
    )
    return str(cur.fetchone()[0])


def insert_results(cur, run_id: str, rows: List[dict]) -> int:
    inserted = 0
    for row in rows:
        cur.execute(
            """
            INSERT INTO results
                (run_id, probe_id, outcome, recovery_latency, t1, t2, t3, total_tokens)
            VALUES
                (%s, %s, %s, %s::text, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                run_id,
                row["probe_id"],
                row["outcome"],
                str(row["recovery_latency"]),
                row["t1"],
                row["t2"],
                row["t3"],
                row["total_tokens"],
            ),
        )
        inserted += cur.rowcount
    return inserted


def parse_bool(val: str) -> Optional[bool]:
    if val.strip().lower() == "true":
        return True
    if val.strip().lower() == "false":
        return False
    return None


def load_csv(filepath: str) -> List[dict]:
    rows = []
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def main() -> None:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False

    total_files = len(IMPORTS)
    skipped = 0
    imported = 0

    for i, (filename, dataset, model, temperature) in enumerate(IMPORTS, 1):
        filepath = os.path.join(BASE, filename)
        prefix = f"[{i:02d}/{total_files}] {model} | {dataset} | T={temperature}"

        if not os.path.exists(filepath):
            print(f"{prefix}  ⚠  FILE MISSING — {filename}")
            skipped += 1
            continue

        with conn.cursor() as cur:
            existing_id = run_already_exists(cur, model, dataset, temperature)
            if existing_id:
                print(f"{prefix}  ⟳  already in DB (run {existing_id}) — skipping")
                skipped += 1
                continue

        rows = load_csv(filepath)
        if not rows:
            print(f"{prefix}  ⚠  EMPTY FILE — {filename}")
            skipped += 1
            continue

        expected = EXPECTED_ROWS.get(dataset)
        if expected and len(rows) != expected:
            print(f"{prefix}  ⚠  ROW COUNT {len(rows)} ≠ expected {expected} — importing anyway")

        try:
            with conn.cursor() as cur:
                run_id = insert_run(cur, model, dataset, temperature, len(rows))

                parsed_rows = []
                for r in rows:
                    parsed_rows.append({
                        "probe_id":         r["probe_id"],
                        "outcome":          r["outcome"],
                        "recovery_latency": r.get("recovery_latency", "0"),
                        "t1":               parse_bool(r.get("t1", "False")),
                        "t2":               parse_bool(r.get("t2", "False")),
                        "t3":               parse_bool(r.get("t3", "False")),
                        "total_tokens":     int(r["total_tokens"]) if r.get("total_tokens") else None,
                    })

                n = insert_results(cur, run_id, parsed_rows)

            conn.commit()
            print(f"{prefix}  ✓  run_id={run_id}  {n}/{len(rows)} results inserted")
            imported += 1

        except Exception as e:
            conn.rollback()
            print(f"{prefix}  ✗  ERROR — {e}")
            skipped += 1

    conn.close()
    print(f"\nDone — {imported} files imported, {skipped} skipped/errored")
    print("Next: run Step 2 coverage query")


if __name__ == "__main__":
    main()
