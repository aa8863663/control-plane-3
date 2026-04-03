#!/usr/bin/env python3
"""Import missing benchmark data from backup directories into Neon DB."""
import os, csv
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
import psycopg2
from datetime import datetime

DB = os.environ['DATABASE_URL']

# Map raw model names in CSV files -> canonical DB model names
MODEL_MAP = {
    'google/gemini-2.0-flash-001': 'gemini-2.0-flash',
    'google/gemma-3-27b-it':       'gemma-3-27b-it',
    'x-ai/grok-3-mini-beta':       'grok-3-mini',
    'meta/llama-3.1-70b-instruct': 'llama-3.1-70b-instruct',
    'command-r-08-2024':           'command-r',
    'llama3.1-8b':                 'cerebras-llama-8b',
    'ibm/granite-3.3-8b-instruct': 'granite-3.3-8b-instruct',
    'microsoft/phi-4-mini-instruct':'phi-4-mini-instruct',
}

BACKUP2 = '/Users/aimeestanyer/Projects/control-plane-3_backup_20260307_234558'
BACKUP3 = '/Users/aimeestanyer/Desktop/CP3_Backup_March29_2026'

# (filepath, db_model, dataset)
IMPORTS = [
    # --- gpt-4o p200 (all 4 temps) ---
    (f'{BACKUP2}/temp_0.0_gpt-4o_results.csv',         'gpt-4o',              'probes_200'),
    (f'{BACKUP2}/temp_0.2_gpt-4o_results.csv',         'gpt-4o',              'probes_200'),
    (f'{BACKUP2}/temp_0.5_gpt-4o_results.csv',         'gpt-4o',              'probes_200'),
    (f'{BACKUP2}/temp_0.8_gpt-4o_results.csv',         'gpt-4o',              'probes_200'),
    # --- gpt-4o-mini p200 ---
    (f'{BACKUP2}/temp_0.0_gpt-4o-mini_results.csv',    'gpt-4o-mini',         'probes_200'),
    (f'{BACKUP2}/temp_0.2_gpt-4o-mini_results.csv',    'gpt-4o-mini',         'probes_200'),
    (f'{BACKUP2}/temp_0.5_gpt-4o-mini_results.csv',    'gpt-4o-mini',         'probes_200'),
    (f'{BACKUP2}/temp_0.8_gpt-4o-mini_results.csv',    'gpt-4o-mini',         'probes_200'),
    # --- gpt-3.5-turbo p200 ---
    (f'{BACKUP2}/temp_0.0_gpt-3.5-turbo_results.csv',  'gpt-3.5-turbo',       'probes_200'),
    (f'{BACKUP2}/temp_0.2_gpt-3.5-turbo_results.csv',  'gpt-3.5-turbo',       'probes_200'),
    (f'{BACKUP2}/temp_0.5_gpt-3.5-turbo_results.csv',  'gpt-3.5-turbo',       'probes_200'),
    (f'{BACKUP2}/temp_0.8_gpt-3.5-turbo_results.csv',  'gpt-3.5-turbo',       'probes_200'),
    # --- gemini-2.0-flash p200 ---
    (f'{BACKUP2}/temp_0.0_gemini-2.0-flash_results.csv', 'gemini-2.0-flash',  'probes_200'),
    (f'{BACKUP2}/temp_0.2_gemini-2.0-flash_results.csv', 'gemini-2.0-flash',  'probes_200'),
    (f'{BACKUP2}/temp_0.5_gemini-2.0-flash_results.csv', 'gemini-2.0-flash',  'probes_200'),
    (f'{BACKUP2}/temp_0.8_gemini-2.0-flash_results.csv', 'gemini-2.0-flash',  'probes_200'),
    # --- gemma-3-27b-it p200 ---
    (f'{BACKUP2}/temp_0.0_nvidia-gemma-27b_results.csv', 'gemma-3-27b-it',    'probes_200'),
    (f'{BACKUP2}/temp_0.2_nvidia-gemma-27b_results.csv', 'gemma-3-27b-it',    'probes_200'),
    (f'{BACKUP2}/temp_0.5_nvidia-gemma-27b_results.csv', 'gemma-3-27b-it',    'probes_200'),
    (f'{BACKUP2}/temp_0.8_nvidia-gemma-27b_results.csv', 'gemma-3-27b-it',    'probes_200'),
    # --- grok-3-mini p200 ---
    (f'{BACKUP2}/temp_0.0_grok-3-mini_results.csv',    'grok-3-mini',         'probes_200'),
    (f'{BACKUP2}/temp_0.2_grok-3-mini_results.csv',    'grok-3-mini',         'probes_200'),
    (f'{BACKUP2}/temp_0.5_grok-3-mini_results.csv',    'grok-3-mini',         'probes_200'),
    (f'{BACKUP2}/temp_0.8_grok-3-mini_results.csv',    'grok-3-mini',         'probes_200'),
    # --- llama-3.1-70b-instruct p200 ---
    (f'{BACKUP2}/temp_0.0_nvidia-llama-70b_results.csv', 'llama-3.1-70b-instruct', 'probes_200'),
    (f'{BACKUP2}/temp_0.2_nvidia-llama-70b_results.csv', 'llama-3.1-70b-instruct', 'probes_200'),
    (f'{BACKUP2}/temp_0.5_nvidia-llama-70b_results.csv', 'llama-3.1-70b-instruct', 'probes_200'),
    (f'{BACKUP2}/temp_0.8_nvidia-llama-70b_results.csv', 'llama-3.1-70b-instruct', 'probes_200'),
    # --- llama-3.1-70b-instruct p500 (missing T=0.0 and T=0.5) ---
    (f'{BACKUP3}/temp_0.0_nvidia_llama_500.csv',       'llama-3.1-70b-instruct', 'probes_500'),
    (f'{BACKUP3}/temp_0.5_nvidia_llama_500.csv',       'llama-3.1-70b-instruct', 'probes_500'),
    # --- llama-3.3-70b-versatile p200 (missing T=0.0 and T=0.5) ---
    (f'{BACKUP3}/llama-3.3-70b-versatile_temp0.0_results.csv', 'llama-3.3-70b-versatile', 'probes_200'),
    (f'{BACKUP3}/llama-3.3-70b-versatile_temp0.5_results.csv', 'llama-3.3-70b-versatile', 'probes_200'),
    # --- claude-haiku p200 (missing T=0.0 and T=0.5) ---
    (f'{BACKUP3}/claude-haiku-4-5-20251001_temp0.0_results.csv', 'claude-haiku-4-5-20251001', 'probes_200'),
    (f'{BACKUP3}/claude-haiku-4-5-20251001_temp0.5_results.csv', 'claude-haiku-4-5-20251001', 'probes_200'),
]

def already_done(cur, db_model, dataset, temp, probe_count):
    cur.execute(
        "SELECT COUNT(*) FROM runs WHERE model=%s AND dataset=%s AND ROUND(temperature::numeric,1)=%s AND probe_count IS NOT NULL",
        (db_model, dataset, temp)
    )
    return cur.fetchone()[0] >= 1

def import_file(cur, filepath, db_model, dataset):
    if not os.path.exists(filepath):
        print(f'  MISSING FILE: {filepath}')
        return False

    with open(filepath) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print(f'  EMPTY: {filepath}')
        return False

    temp = float(rows[0].get('temp', 0.0))
    probe_count = len(rows)

    if already_done(cur, db_model, dataset, temp, probe_count):
        print(f'  SKIP {db_model} {dataset} T={temp} (already in DB)')
        return False

    cur.execute(
        """INSERT INTO runs (model, temperature, probe_count, dataset, created_at, python_version)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (db_model, temp, probe_count, dataset, datetime.now(), '3.9')
    )
    run_id = cur.fetchone()[0]

    for row in rows:
        cur.execute(
            """INSERT INTO results (run_id, probe_id, outcome, recovery_latency, created_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (run_id, row.get('probe_id',''), row.get('outcome','UNKNOWN'),
             float(row.get('recovery_latency') or 0), datetime.now())
        )

    print(f'  IMPORTED {db_model} {dataset} T={temp} ({probe_count} rows, run_id={run_id})')
    return True

db = psycopg2.connect(DB)
cur = db.cursor()
imported = 0

for filepath, db_model, dataset in IMPORTS:
    if import_file(cur, filepath, db_model, dataset):
        db.commit()
        imported += 1

db.close()
print(f'\nDone. Imported {imported} new runs.')
