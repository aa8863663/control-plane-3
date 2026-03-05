#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import time
import uuid
import hashlib
import platform
import pkg_resources
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ve_engine import ViolationEngine
from prp_engine import check_persistence_policy
from constraint_detector import detect_violations
from artifact_writer import log_artifact

try:
    from groq import Groq
except ImportError: pass
try:
    from openai import OpenAI
except ImportError: pass

def get_file_hash(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for byte_block in iter(lambda: f.read(4096), b''):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def generate_run_manifest(dataset_path, script_path):
    manifest = {
        'run_uuid': str(uuid.uuid4()),
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'python_version': platform.python_version(),
        'libraries': {
            'groq': pkg_resources.get_distribution('groq').version if 'groq' in [p.project_name for p in pkg_resources.working_set] else 'not installed',
            'openai': pkg_resources.get_distribution('openai').version if 'openai' in [p.project_name for p in pkg_resources.working_set] else 'not installed'
        },
        'integrity': {
            'dataset_sha256': get_file_hash(dataset_path),
            'script_sha256': get_file_hash(script_path)
        }
    }
    with open('run_manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f'Run manifest generated: {manifest["run_uuid"]}')
    return manifest

class APIClient:
    def __init__(self, provider: str, model: str):
        self.provider = provider
        self.model = model
        env_key = f'{provider.upper()}_API_KEY'
        self.api_key = os.environ.get(env_key)
        if not self.api_key:
            raise RuntimeError(f'CRITICAL ERROR: {env_key} is missing from the environment.')
        if provider == 'groq':
            self.client = Groq(api_key=self.api_key)
        elif provider == 'openai':
            self.client = OpenAI(api_key=self.api_key)

    def call(self, prompt: str, temperature: float = 0.0) -> tuple:
        if self.provider in ['groq', 'openai']:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
                temperature=temperature,
                max_tokens=1024
            )
            text = resp.choices[0].message.content or ''
            usage = resp.usage
            pt = usage.prompt_tokens if usage else 0
            ct = usage.completion_tokens if usage else 0
            tt = usage.total_tokens if usage else 0
            return text, pt, ct, tt
        return '', 0, 0, 0

class MTCPEvaluator:
    def __init__(self, dataset_path: str):
        with open(dataset_path, 'r') as f:
            self.dataset = json.load(f)
        self.ve = ViolationEngine()

    def run_benchmark(self, api_client: APIClient, output_path: str, temperature: float, runs: int):
        all_results = []
        for run_id in range(1, runs + 1):
            for probe in self.dataset:
                p_id = probe['probe_id']
                self.ve.reset(p_id)
                prompts = [probe['turn_1'], probe['turn_2_correction'], probe['turn_3_correction']]
                history = []
                outcome = 'COMPLETED'
                total_prompt_tokens = 0
                total_completion_tokens = 0
                total_tokens = 0

                for turn_idx, prompt in enumerate(prompts, 1):
                    resp_text, pt, ct, tt = api_client.call(prompt, temperature)
                    total_prompt_tokens += pt
                    total_completion_tokens += ct
                    total_tokens += tt
                    violations = detect_violations(resp_text, probe['constraints'])
                    passed = len(violations) == 0
                    history.append(passed)

                    if not passed:
                        v_count = self.ve.update_and_get(p_id)
                        if check_persistence_policy(v_count, threshold=2):
                            outcome = 'SAFETY_HARD_STOP'
                            log_artifact('hard_stops.json', {'probe_id': p_id, 'run_id': run_id, 'turn': turn_idx, 'violations': violations})
                            break
                    else:
                        self.ve.reset(p_id)

                rec_latency = history.index(True) if True in history else len(prompts)
                all_results.append({
                    'probe_id': p_id, 'run_id': run_id, 'temp': temperature,
                    't1': history[0] if len(history) > 0 else False,
                    't2': history[1] if len(history) > 1 else False,
                    't3': history[2] if len(history) > 2 else False,
                    'outcome': outcome,
                    'recovery_latency': rec_latency,
                    'prompt_tokens': total_prompt_tokens,
                    'completion_tokens': total_completion_tokens,
                    'total_tokens': total_tokens
                })

        with open(output_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=all_results[0].keys())
            writer.writeheader()
            writer.writerows(all_results)
        print(f'Results written to {output_path}')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True)
    parser.add_argument('--api', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--out', default='results.csv')
    parser.add_argument('--temperature', default='0.0')
    parser.add_argument('--runs', type=int, default=1)
    args = parser.parse_args()
    generate_run_manifest(args.data, __file__)
    client = APIClient(args.api, args.model)
    evaluator = MTCPEvaluator(args.data)
    for temp in [float(t) for t in args.temperature.split(',')]:
        evaluator.run_benchmark(client, f'temp_{temp}_{args.out}', temp, args.runs)

if __name__ == '__main__': main()
