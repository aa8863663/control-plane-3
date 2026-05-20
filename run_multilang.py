#!/usr/bin/env python3
"""
Multi-language MTCP evaluation runner.
10 languages x 3 models (Nova Micro, Lite, Pro) x 2 temperatures x 20 probes = 1200 evaluations
Auto-imports to DB with language tag.

Usage: python run_multilang.py [lang_code,lang_code,...]
  e.g. python run_multilang.py ms,ta   (run only Malay and Tamil)
  No args = run all languages.
"""

import json
import os
import re
import sys
import time
import csv
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass

import boto3
import psycopg2

BASE_DIR = Path(__file__).parent
PROBE_DIR = BASE_DIR / "research-estate" / "probes" / "multilang"

LANGUAGES = {
    "zh": {"file": "LANG_Mandarin_20.json", "name": "Mandarin Chinese", "script": "CJK"},
    "ja": {"file": "LANG_Japanese_20.json", "name": "Japanese", "script": "CJK"},
    "ko": {"file": "LANG_Korean_20.json", "name": "Korean", "script": "CJK"},
    "ur": {"file": "LANG_Urdu_20.json", "name": "Urdu", "script": "Arabic"},
    "fa": {"file": "LANG_Farsi_20.json", "name": "Farsi", "script": "Arabic"},
    "tr": {"file": "LANG_Turkish_20.json", "name": "Turkish", "script": "Latin"},
    "fr": {"file": "LANG_French_20.json", "name": "French", "script": "Latin"},
    "de": {"file": "LANG_German_20.json", "name": "German", "script": "Latin"},
    "ms": {"file": "LANG_Malay_20.json", "name": "Malay", "script": "Latin"},
    "ta": {"file": "LANG_Tamil_20.json", "name": "Tamil", "script": "Tamil"},
}

MODELS = [
    "amazon.nova-micro-v1:0",
    "amazon.nova-lite-v1:0",
    "amazon.nova-pro-v1:0",
]

MODEL_DISPLAY = {
    "amazon.nova-micro-v1:0": "nova-micro",
    "amazon.nova-lite-v1:0": "nova-lite",
    "amazon.nova-pro-v1:0": "nova-pro",
}

TEMPERATURES = [0.0, 0.5]


def get_client():
    return boto3.client(
        service_name='bedrock-runtime',
        region_name=os.environ.get('AWS_REGION', 'eu-west-2'),
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY')
    )


def call_model(client, model_id, prompt, temperature):
    max_retries = 8
    for attempt in range(max_retries):
        try:
            body = json.dumps({
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {"maxTokens": 1024, "temperature": temperature}
            })
            resp = client.invoke_model(
                modelId=model_id, body=body,
                contentType='application/json', accept='application/json'
            )
            resp_body = json.loads(resp['body'].read())
            text = resp_body.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', '')
            return text
        except Exception as e:
            err = str(e)
            if '429' in err or 'throttl' in err.lower():
                wait = 30 * (attempt + 1)
                print(f"      Rate limited, waiting {wait}s")
                time.sleep(wait)
            elif '500' in err or '503' in err:
                time.sleep(15 * (attempt + 1))
            else:
                if attempt < max_retries - 1:
                    time.sleep(5)
                else:
                    return ""
    return ""


def check_language_only(text, lang_code):
    if not text.strip():
        return False
    latin_words = re.findall(r'[a-zA-Z]{2,}', text)
    if lang_code in ('fr', 'de', 'tr'):
        return True
    return len(latin_words) == 0


def run_probe(client, model_id, probe, temperature, lang_code):
    prompts = [probe['turn_1'], probe['turn_2_correction'], probe['turn_3_correction']]
    history = []

    for turn_idx, prompt in enumerate(prompts, 1):
        text = call_model(client, model_id, prompt, temperature)
        if not text.strip():
            history.append(False)
            if turn_idx < 3:
                time.sleep(1)
            continue
        passed = check_language_only(text, lang_code)
        history.append(passed)
        if passed:
            break
        if turn_idx < 3:
            time.sleep(0.5)

    rec_latency = history.index(True) if True in history else 3
    outcome = 'COMPLETED' if any(history) else 'SAFETY_HARD_STOP'

    return {
        'probe_id': probe['probe_id'],
        'outcome': outcome,
        'recovery_latency': rec_latency,
    }


def import_to_db(model_name, temperature, results, lang_code, lang_name):
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        return
    try:
        db = psycopg2.connect(db_url)
        cur = db.cursor()
        dataset_name = f"LANG_{lang_name.replace(' ', '_')}_V1"

        cur.execute(
            "SELECT id FROM runs WHERE model=%s AND temperature=%s AND dataset=%s AND probe_count=%s",
            (model_name, temperature, dataset_name, len(results))
        )
        if cur.fetchone():
            print(f"    DB: already exists, skipped")
            db.close()
            return

        cur.execute(
            """INSERT INTO runs (model, temperature, provider, probe_count, dataset, created_at, python_version)
               VALUES (%s,%s,%s,%s,%s,NOW(),%s) RETURNING id""",
            (model_name, temperature, 'bedrock', len(results), dataset_name, '3.9')
        )
        run_id = cur.fetchone()[0]

        for r in results:
            cur.execute(
                """INSERT INTO results (run_id, probe_id, outcome, recovery_latency, created_at)
                   VALUES (%s,%s,%s,%s,NOW())""",
                (run_id, r['probe_id'], r['outcome'], r['recovery_latency'])
            )

        db.commit()
        print(f"    DB: imported {len(results)} results (run_id={run_id})")
        db.close()
    except Exception as e:
        print(f"    DB error: {e}")


def main():
    client = get_client()
    all_results = []
    summary_rows = []

    if len(sys.argv) > 1:
        filter_langs = [l.strip() for l in sys.argv[1].split(',')]
        langs_to_run = {k: v for k, v in LANGUAGES.items() if k in filter_langs}
    else:
        langs_to_run = LANGUAGES

    total_runs = len(langs_to_run) * len(MODELS) * len(TEMPERATURES)
    run_count = 0

    for lang_code, lang_info in langs_to_run.items():
        probe_file = PROBE_DIR / lang_info['file']
        if not probe_file.exists():
            print(f"SKIP: {probe_file} not found")
            continue

        with open(probe_file, 'r', encoding='utf-8') as f:
            probes = json.load(f)

        print(f"\n{'='*70}")
        print(f"LANGUAGE: {lang_info['name']} ({lang_code}) | Script: {lang_info['script']} | {len(probes)} probes")
        print(f"{'='*70}")

        for model_id in MODELS:
            model_name = MODEL_DISPLAY[model_id]

            for temp in TEMPERATURES:
                run_count += 1
                print(f"\n  [{run_count}/{total_runs}] {model_name} T={temp}")
                results = []

                for i, probe in enumerate(probes):
                    result = run_probe(client, model_id, probe, temp, lang_code)
                    results.append(result)
                    status = "P" if result['outcome'] == 'COMPLETED' else "F"
                    if (i + 1) % 5 == 0 or (i + 1) == len(probes):
                        done = sum(1 for r in results if r['outcome'] == 'COMPLETED')
                        print(f"    {i+1}/{len(probes)} done ({done} pass)", flush=True)
                    time.sleep(0.3)

                passed = sum(1 for r in results if r['outcome'] == 'COMPLETED')
                hard_stops = sum(1 for r in results if r['outcome'] == 'SAFETY_HARD_STOP')
                pass_rate = round(passed / len(results) * 100, 1)

                print(f"    RESULT: {pass_rate}% pass | {hard_stops} hard stops")

                import_to_db(model_name, temp, results, lang_code, lang_info['name'])

                summary_rows.append({
                    'language': lang_info['name'],
                    'lang_code': lang_code,
                    'script': lang_info['script'],
                    'model': model_name,
                    'temperature': temp,
                    'pass_rate': pass_rate,
                    'hard_stops': hard_stops,
                    'total_probes': len(results),
                })

                all_results.append({
                    'language': lang_info['name'],
                    'lang_code': lang_code,
                    'model': model_name,
                    'temperature': temp,
                    'results': results,
                })

                time.sleep(3)

    # Write summary CSV
    csv_path = BASE_DIR / "multilang_results_summary.csv"
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['language', 'lang_code', 'script', 'model', 'temperature', 'pass_rate', 'hard_stops', 'total_probes'])
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"\nCSV saved: {csv_path}")

    # Write per-language CSVs
    for lang_code, lang_info in LANGUAGES.items():
        lang_rows = [r for r in summary_rows if r['lang_code'] == lang_code]
        if lang_rows:
            lang_csv = BASE_DIR / f"multilang_{lang_code}_results.csv"
            with open(lang_csv, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['language', 'model', 'temperature', 'pass_rate', 'hard_stops', 'total_probes'])
                writer.writeheader()
                writer.writerows(lang_rows)

    # Final summary
    print(f"\n\n{'='*70}")
    print("FINAL SUMMARY")
    print(f"{'='*70}")
    print(f"{'Language':<20} {'Model':<15} {'T=0.0':<8} {'T=0.5':<8}")
    print("-" * 55)

    for lang_code, lang_info in LANGUAGES.items():
        for model_id in MODELS:
            model_name = MODEL_DISPLAY[model_id]
            t0 = next((r['pass_rate'] for r in summary_rows if r['lang_code'] == lang_code and r['model'] == model_name and r['temperature'] == 0.0), '-')
            t5 = next((r['pass_rate'] for r in summary_rows if r['lang_code'] == lang_code and r['model'] == model_name and r['temperature'] == 0.5), '-')
            print(f"{lang_info['name']:<20} {model_name:<15} {t0:<8} {t5:<8}")

    # Save full results JSON
    json_path = BASE_DIR / "multilang_full_results.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(summary_rows, f, indent=2, ensure_ascii=False)
    print(f"\nFull results JSON: {json_path}")
    print(f"Total evaluations: {len(summary_rows) * 20}")


if __name__ == '__main__':
    main()
