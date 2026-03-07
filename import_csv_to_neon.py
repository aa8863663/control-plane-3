"""
import_csv_to_neon.py
Imports all new benchmark CSV results into Neon PostgreSQL.
Run: python3 import_csv_to_neon.py
"""

import os
import csv
import glob
import psycopg2
import psycopg2.extras
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL missing — run: export $(cat .env | xargs)")

# Which CSV files to import — all temp_*.csv files except control and old ones
EXCLUDE = [
    "temp_0.0_results.csv",
    "temp_0.2_results.csv",
    "temp_0.5_results.csv",
    "temp_0.8_results.csv",
    "temp_0.2_results_rerun1.csv",
    "temp_0.0_gemini-flash_results.csv",
    "temp_0.2_gemini-flash_results.csv",
    "temp_0.5_gemini-flash_results.csv",
    "temp_0.8_gemini-flash_results.csv",
]

# Model name mapping — clean up display names
MODEL_DISPLAY = {
    "x-ai/grok-3-mini-beta": "grok-3-mini-beta",
    "meta/llama-3.1-70b-instruct": "nvidia/llama-3.1-70b",
    "google/gemma-3-27b-it": "nvidia/gemma-3-27b",
    "google/gemini-2.0-flash-001": "gemini-2.0-flash-001",
    "anthropic/claude-sonnet-4": "claude-sonnet-4",
}

def get_model_from_filename(filename):
    """Extract model name from filename like temp_0.0_grok-3-mini_results.csv"""
    base = os.path.basename(filename)
    # Remove temp_X.X_ prefix and _results.csv suffix
    name = base.replace("temp_0.0_", "").replace("temp_0.2_", "").replace("temp_0.5_", "").replace("temp_0.8_", "")
    name = name.replace("_results.csv", "").replace(".csv", "")
    return name

def get_provider_from_model(model):
    if "grok" in model: return "openrouter/xai"
    if "nvidia" in model or "llama-3.1-70b" in model or "gemma-3-27b" in model: return "nvidia"
    if "gemini" in model: return "openrouter/google"
    if "gpt" in model: return "openai"
    if "claude" in model: return "anthropic"
    if "llama" in model: return "groq"
    return "unknown"

print("Connecting to Neon...")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Ensure runs table has api_provider column
cur.execute("""
    ALTER TABLE runs ADD COLUMN IF NOT EXISTS api_provider TEXT;
    ALTER TABLE runs ADD COLUMN IF NOT EXISTS probe_count INTEGER;
    ALTER TABLE runs ADD COLUMN IF NOT EXISTS dataset TEXT;
""")
conn.commit()

# Get all CSV files to import
all_csvs = glob.glob("temp_*.csv")
# Filter out control probes, excluded files, and old 105-probe files
to_import = []
for f in sorted(all_csvs):
    if f in EXCLUDE: continue
    if "ctrl_" in f: continue
    if "rerun" in f: continue
    to_import.append(f)

print(f"Found {len(to_import)} CSV files to import")

imported = 0
skipped = 0

for filepath in to_import:
    with open(filepath, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        rows = list(reader)

    if not rows:
        print(f"  SKIP (empty): {filepath}")
        skipped += 1
        continue

    # Get model and temperature from first row
    first = rows[0]
    model_raw = first.get("model", "")
    model = MODEL_DISPLAY.get(model_raw, model_raw)
    if not model:
        model = get_model_from_filename(filepath)
    temperature = float(first.get("temp", 0.0))
    provider = get_provider_from_model(model)
    probe_count = len(rows)

    # Check if this run already exists in DB
    cur.execute(
        "SELECT id FROM runs WHERE model=%s AND temperature=%s AND probe_count=%s",
        (model, temperature, probe_count)
    )
    existing = cur.fetchone()
    if existing:
        print(f"  SKIP (already imported): {filepath}")
        skipped += 1
        continue

    # Insert run record
    cur.execute("""
        INSERT INTO runs (model, temperature, api_provider, probe_count, dataset, created_at, python_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        model,
        temperature,
        provider,
        probe_count,
        "probes_200",
        datetime.now(),
        "3.9"
    ))
    run_id = cur.fetchone()[0]

    # Insert results
    result_count = 0
    for row in rows:
        outcome = row.get("outcome", "UNKNOWN")
        recovery_latency = row.get("recovery_latency", 0)
        try:
            recovery_latency = float(recovery_latency) if recovery_latency else 0.0
        except:
            recovery_latency = 0.0

        cur.execute("""
            INSERT INTO results (run_id, probe_id, outcome, recovery_latency, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            run_id,
            row.get("probe_id", ""),
            outcome,
            recovery_latency,
            datetime.now()
        ))
        result_count += 1

    conn.commit()
    print(f"  IMPORTED: {filepath} — {result_count} results (run_id={run_id}, model={model}, temp={temperature})")
    imported += 1

conn.close()
print(f"\nDone. Imported {imported} files, skipped {skipped}.")
print("Now push to GitHub: git add . && git commit -m 'Import all new benchmark results' && git push origin main --force")
