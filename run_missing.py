#!/usr/bin/env python3
"""Run all missing model/dataset/temp combos. Skip anything already in DB."""
import os, subprocess, sys
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
import psycopg2

def already_done(db_model, dataset, temp):
    db = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = db.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM runs WHERE model=%s AND dataset=%s AND ROUND(temperature::numeric,1)=%s AND probe_count IS NOT NULL",
        (db_model, dataset, temp)
    )
    result = cur.fetchone()[0] >= 1
    db.close()
    return result

def run(api, model, datafile, temp, db_model):
    dataset = 'ctrl' if 'control' in datafile else os.path.splitext(datafile)[0]
    if already_done(db_model, dataset, temp):
        print(f'  SKIP {db_model} {dataset} T={temp}')
        return
    print(f'  RUN  {db_model} {dataset} T={temp} via {api}')
    cmd = [
        sys.executable, 'llm_safety_platform.py',
        '--api', api,
        '--model', model,
        '--data', datafile,
        '--temperature', str(temp),
        '--db-model', db_model,
    ]
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))
    if result.returncode != 0:
        print(f'  FAILED {db_model} {dataset} T={temp} — stopping')
        sys.exit(1)

JOBS = [
    # --- MISTRAL ---
    ('mistral', 'magistral-medium-latest',  'probes_500.json',        0.8, 'magistral-medium-latest'),

    ('mistral', 'mistral-medium-3',         'probes_control_20.json', 0.0, 'mistral-medium-3'),
    ('mistral', 'mistral-medium-3',         'probes_control_20.json', 0.2, 'mistral-medium-3'),
    ('mistral', 'mistral-medium-3',         'probes_control_20.json', 0.5, 'mistral-medium-3'),
    ('mistral', 'mistral-medium-3',         'probes_control_20.json', 0.8, 'mistral-medium-3'),
    ('mistral', 'mistral-medium-3',         'probes_200.json',        0.0, 'mistral-medium-3'),
    ('mistral', 'mistral-medium-3',         'probes_200.json',        0.2, 'mistral-medium-3'),
    ('mistral', 'mistral-medium-3',         'probes_200.json',        0.5, 'mistral-medium-3'),
    ('mistral', 'mistral-medium-3',         'probes_200.json',        0.8, 'mistral-medium-3'),
    ('mistral', 'mistral-medium-3',         'probes_500.json',        0.0, 'mistral-medium-3'),
    ('mistral', 'mistral-medium-3',         'probes_500.json',        0.2, 'mistral-medium-3'),
    ('mistral', 'mistral-medium-3',         'probes_500.json',        0.5, 'mistral-medium-3'),
    ('mistral', 'mistral-medium-3',         'probes_500.json',        0.8, 'mistral-medium-3'),

    ('mistral', 'ministral-8b-latest',      'probes_control_20.json', 0.0, 'ministral-8b'),
    ('mistral', 'ministral-8b-latest',      'probes_control_20.json', 0.2, 'ministral-8b'),
    ('mistral', 'ministral-8b-latest',      'probes_control_20.json', 0.5, 'ministral-8b'),
    ('mistral', 'ministral-8b-latest',      'probes_control_20.json', 0.8, 'ministral-8b'),
    ('mistral', 'ministral-8b-latest',      'probes_200.json',        0.0, 'ministral-8b'),
    ('mistral', 'ministral-8b-latest',      'probes_200.json',        0.2, 'ministral-8b'),
    ('mistral', 'ministral-8b-latest',      'probes_200.json',        0.5, 'ministral-8b'),
    ('mistral', 'ministral-8b-latest',      'probes_200.json',        0.8, 'ministral-8b'),
    ('mistral', 'ministral-8b-latest',      'probes_500.json',        0.0, 'ministral-8b'),
    ('mistral', 'ministral-8b-latest',      'probes_500.json',        0.2, 'ministral-8b'),
    ('mistral', 'ministral-8b-latest',      'probes_500.json',        0.5, 'ministral-8b'),
    ('mistral', 'ministral-8b-latest',      'probes_500.json',        0.8, 'ministral-8b'),

    ('mistral', 'open-mistral-nemo',        'probes_control_20.json', 0.0, 'mistral-nemo'),
    ('mistral', 'open-mistral-nemo',        'probes_control_20.json', 0.2, 'mistral-nemo'),
    ('mistral', 'open-mistral-nemo',        'probes_control_20.json', 0.5, 'mistral-nemo'),
    ('mistral', 'open-mistral-nemo',        'probes_control_20.json', 0.8, 'mistral-nemo'),
    ('mistral', 'open-mistral-nemo',        'probes_200.json',        0.0, 'mistral-nemo'),
    ('mistral', 'open-mistral-nemo',        'probes_200.json',        0.2, 'mistral-nemo'),
    ('mistral', 'open-mistral-nemo',        'probes_200.json',        0.5, 'mistral-nemo'),
    ('mistral', 'open-mistral-nemo',        'probes_200.json',        0.8, 'mistral-nemo'),
    ('mistral', 'open-mistral-nemo',        'probes_500.json',        0.0, 'mistral-nemo'),
    ('mistral', 'open-mistral-nemo',        'probes_500.json',        0.2, 'mistral-nemo'),
    ('mistral', 'open-mistral-nemo',        'probes_500.json',        0.5, 'mistral-nemo'),
    ('mistral', 'open-mistral-nemo',        'probes_500.json',        0.8, 'mistral-nemo'),

    # --- GOOGLE (via OpenRouter) ---
    ('openrouter', 'google/gemini-2.0-flash-lite-001', 'probes_control_20.json', 0.0, 'gemini-2.0-flash-lite'),
    ('openrouter', 'google/gemini-2.0-flash-lite-001', 'probes_control_20.json', 0.2, 'gemini-2.0-flash-lite'),
    ('openrouter', 'google/gemini-2.0-flash-lite-001', 'probes_control_20.json', 0.5, 'gemini-2.0-flash-lite'),
    ('openrouter', 'google/gemini-2.0-flash-lite-001', 'probes_control_20.json', 0.8, 'gemini-2.0-flash-lite'),
    ('openrouter', 'google/gemini-2.0-flash-lite-001', 'probes_200.json',        0.0, 'gemini-2.0-flash-lite'),
    ('openrouter', 'google/gemini-2.0-flash-lite-001', 'probes_200.json',        0.2, 'gemini-2.0-flash-lite'),
    ('openrouter', 'google/gemini-2.0-flash-lite-001', 'probes_200.json',        0.5, 'gemini-2.0-flash-lite'),
    ('openrouter', 'google/gemini-2.0-flash-lite-001', 'probes_200.json',        0.8, 'gemini-2.0-flash-lite'),
    ('openrouter', 'google/gemini-2.0-flash-lite-001', 'probes_500.json',        0.0, 'gemini-2.0-flash-lite'),
    ('openrouter', 'google/gemini-2.0-flash-lite-001', 'probes_500.json',        0.2, 'gemini-2.0-flash-lite'),
    ('openrouter', 'google/gemini-2.0-flash-lite-001', 'probes_500.json',        0.5, 'gemini-2.0-flash-lite'),
    ('openrouter', 'google/gemini-2.0-flash-lite-001', 'probes_500.json',        0.8, 'gemini-2.0-flash-lite'),

    # --- BEDROCK ---
    ('bedrock', 'qwen.qwen3-32b-v1:0',              'probes_200.json',        0.0, 'qwen3-32b'),
    ('bedrock', 'qwen.qwen3-32b-v1:0',              'probes_200.json',        0.5, 'qwen3-32b'),
    ('bedrock', 'qwen.qwen3-32b-v1:0',              'probes_200.json',        0.8, 'qwen3-32b'),
    ('bedrock', 'qwen.qwen3-32b-v1:0',              'probes_500.json',        0.0, 'qwen3-32b'),
    ('bedrock', 'qwen.qwen3-32b-v1:0',              'probes_500.json',        0.2, 'qwen3-32b'),
    ('bedrock', 'qwen.qwen3-32b-v1:0',              'probes_500.json',        0.5, 'qwen3-32b'),
    ('bedrock', 'qwen.qwen3-32b-v1:0',              'probes_500.json',        0.8, 'qwen3-32b'),

    ('bedrock', 'mistral.ministral-3-8b-instruct',  'probes_control_20.json', 0.0, 'ministral-8b'),
    ('bedrock', 'mistral.ministral-3-8b-instruct',  'probes_control_20.json', 0.2, 'ministral-8b'),
    ('bedrock', 'mistral.ministral-3-8b-instruct',  'probes_control_20.json', 0.5, 'ministral-8b'),
    ('bedrock', 'mistral.ministral-3-8b-instruct',  'probes_control_20.json', 0.8, 'ministral-8b'),
    ('bedrock', 'mistral.ministral-3-8b-instruct',  'probes_200.json',        0.0, 'ministral-8b'),
    ('bedrock', 'mistral.ministral-3-8b-instruct',  'probes_200.json',        0.2, 'ministral-8b'),
    ('bedrock', 'mistral.ministral-3-8b-instruct',  'probes_200.json',        0.5, 'ministral-8b'),
    ('bedrock', 'mistral.ministral-3-8b-instruct',  'probes_200.json',        0.8, 'ministral-8b'),
    ('bedrock', 'mistral.ministral-3-8b-instruct',  'probes_500.json',        0.0, 'ministral-8b'),
    ('bedrock', 'mistral.ministral-3-8b-instruct',  'probes_500.json',        0.2, 'ministral-8b'),
    ('bedrock', 'mistral.ministral-3-8b-instruct',  'probes_500.json',        0.5, 'ministral-8b'),
    ('bedrock', 'mistral.ministral-3-8b-instruct',  'probes_500.json',        0.8, 'ministral-8b'),

    ('bedrock', 'deepseek.v3-v1:0',                 'probes_control_20.json', 0.0, 'deepseek-v3'),
    ('bedrock', 'deepseek.v3-v1:0',                 'probes_control_20.json', 0.2, 'deepseek-v3'),
    ('bedrock', 'deepseek.v3-v1:0',                 'probes_control_20.json', 0.5, 'deepseek-v3'),
    ('bedrock', 'deepseek.v3-v1:0',                 'probes_control_20.json', 0.8, 'deepseek-v3'),
    ('bedrock', 'deepseek.v3-v1:0',                 'probes_200.json',        0.0, 'deepseek-v3'),
    ('bedrock', 'deepseek.v3-v1:0',                 'probes_200.json',        0.2, 'deepseek-v3'),
    ('bedrock', 'deepseek.v3-v1:0',                 'probes_200.json',        0.5, 'deepseek-v3'),
    ('bedrock', 'deepseek.v3-v1:0',                 'probes_200.json',        0.8, 'deepseek-v3'),
    ('bedrock', 'deepseek.v3-v1:0',                 'probes_500.json',        0.0, 'deepseek-v3'),
    ('bedrock', 'deepseek.v3-v1:0',                 'probes_500.json',        0.2, 'deepseek-v3'),
    ('bedrock', 'deepseek.v3-v1:0',                 'probes_500.json',        0.5, 'deepseek-v3'),
    ('bedrock', 'deepseek.v3-v1:0',                 'probes_500.json',        0.8, 'deepseek-v3'),

    # --- FIREWORKS ---
    ('fireworks', 'deepseek-ai/DeepSeek-R1', 'probes_500.json',      0.2, 'deepseek-r1'),
    ('fireworks', 'deepseek-ai/DeepSeek-R1', 'probes_500.json',      0.5, 'deepseek-r1'),
    ('fireworks', 'deepseek-ai/DeepSeek-R1', 'probes_500.json',      0.8, 'deepseek-r1'),
]

if __name__ == '__main__':
    filter_api = sys.argv[1] if len(sys.argv) > 1 else None
    jobs = [j for j in JOBS if not filter_api or j[0] == filter_api]
    if not jobs:
        print(f'No jobs for provider: {filter_api}')
        print('Available: mistral, google, groq, fireworks')
        sys.exit(1)
    print(f'Running {len(jobs)} jobs' + (f' for {filter_api}' if filter_api else ''))
    for i, (api, model, datafile, temp, db_model) in enumerate(jobs, 1):
        print(f'[{i}/{len(jobs)}]', end=' ')
        run(api, model, datafile, temp, db_model)
    print('All done.')
