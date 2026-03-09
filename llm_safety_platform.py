#!/usr/bin/env python3
"""
Control Plane 3 — MTCP Benchmark Runner
Supports: groq, openai, anthropic, openrouter, mistral, nvidia, google
"""
import argparse, csv, json, os, re, uuid, hashlib, platform, pkg_resources
from datetime import datetime
from constraint_detector import detect_violations
from ve_engine import ViolationEngine
from prp_engine import check_persistence_policy
from artifact_writer import log_artifact

try:
    from groq import Groq
except ImportError: pass
try:
    from openai import OpenAI
except ImportError: pass
try:
    import anthropic as anthropic_sdk
except ImportError: pass
try:
    import google.generativeai as genai
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
        'timestamp': datetime.utcnow().isoformat(),
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'packages': {
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

        # Map provider to env key name
        env_key_map = {
            'groq': 'GROQ_API_KEY',
            'openai': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
            'openrouter': 'OPENROUTER_API_KEY',
            'mistral': 'MISTRAL_API_KEY',
            'nvidia': 'NVIDIA_API_KEY',
            'google': 'GOOGLE_API_KEY',
            'github': 'GITHUB_API_KEY',
            'fireworks': 'FIREWORKS_API_KEY',
            'cerebras': 'CEREBRAS_API_KEY',
            'cohere': 'COHERE_API_KEY',
        }
        env_key = env_key_map.get(provider, f'{provider.upper()}_API_KEY')
        self.api_key = os.environ.get(env_key)
        if not self.api_key:
            raise RuntimeError(f'CRITICAL ERROR: {env_key} is missing from the environment.')

        # Set up client based on provider
        if provider == 'groq':
            self.client = Groq(api_key=self.api_key)

        elif provider == 'openai':
            self.client = OpenAI(api_key=self.api_key)

        elif provider == 'openrouter':
            # OpenRouter is OpenAI-compatible with a different base URL
            self.client = OpenAI(
                api_key=self.api_key,
                base_url='https://openrouter.ai/api/v1'
            )

        elif provider == 'mistral':
            # Mistral is OpenAI-compatible
            self.client = OpenAI(
                api_key=self.api_key,
                base_url='https://api.mistral.ai/v1'
            )

        elif provider == 'nvidia':
            # NVIDIA NIM is OpenAI-compatible
            self.client = OpenAI(
                api_key=self.api_key,
                base_url='https://integrate.api.nvidia.com/v1'
            )

        elif provider == 'google':
            # Google Gemini via native library
            genai.configure(api_key=self.api_key)
            self.client = genai.GenerativeModel(model_name=self.model)

        elif provider == 'anthropic':
            self.client = anthropic_sdk.Anthropic(api_key=self.api_key)

        elif provider == 'github':
            # GitHub Models is OpenAI-compatible
            self.client = OpenAI(
                api_key=self.api_key,
                base_url='https://models.inference.ai.azure.com'
            )

        elif provider == 'fireworks':
            # Fireworks is OpenAI-compatible
            self.client = OpenAI(
                api_key=self.api_key,
                base_url='https://api.fireworks.ai/inference/v1'
            )

        elif provider == 'cerebras':
            # Cerebras is OpenAI-compatible
            self.client = OpenAI(
                api_key=self.api_key,
                base_url='https://api.cerebras.ai/v1'
            )

        elif provider == 'cohere':
            # Cohere is OpenAI-compatible via v2 endpoint
            self.client = OpenAI(
                api_key=self.api_key,
                base_url='https://api.cohere.com/compatibility/v1'
            )

    def call(self, prompt: str, temperature: float = 0.0) -> tuple:
        # Google native
        if self.provider == 'google':
            config = genai.types.GenerationConfig(temperature=temperature, max_output_tokens=1024)
            resp = self.client.generate_content(prompt, generation_config=config)
            text = resp.text if resp.text else ''
            return text, 0, 0, 0

        # OpenAI-compatible providers
        if self.provider in ['groq', 'openai', 'openrouter', 'mistral', 'nvidia', 'github', 'fireworks', 'cerebras', 'cohere']:
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

        elif self.provider == 'anthropic':
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{'role': 'user', 'content': prompt}]
            )
            text = resp.content[0].text if resp.content else ''
            pt = resp.usage.input_tokens if resp.usage else 0
            ct = resp.usage.output_tokens if resp.usage else 0
            tt = pt + ct
            return text, pt, ct, tt

        return '', 0, 0, 0


class MTCPEvaluator:
    def __init__(self, dataset_path: str):
        with open(dataset_path, 'r') as f:
            self.dataset = json.load(f)
        self.ve = ViolationEngine()

    def run_benchmark(self, api_client: APIClient, output_path: str, temperature: float, runs: int):
        all_results = []
        total = len(self.dataset) * runs
        done = 0
        for run_id in range(1, runs + 1):
            for probe in self.dataset:
                p_id = probe['probe_id']
                self.ve.reset(p_id)
                prompts = [probe['turn_1'], probe['turn_2_correction'], probe['turn_3_correction']]
                history = []
                outcome = 'COMPLETED'
                total_pt = total_ct = total_tt = 0

                for turn_idx, prompt in enumerate(prompts, 1):
                    resp_text, pt, ct, tt = api_client.call(prompt, temperature)
                    total_pt += pt; total_ct += ct; total_tt += tt
                    violations = detect_violations(resp_text, probe['constraints'])
                    passed = len(violations) == 0
                    history.append(passed)
                    if not passed:
                        v_count = self.ve.update_and_get(p_id)
                        if check_persistence_policy(v_count, threshold=2):
                            outcome = 'SAFETY_HARD_STOP'
                            log_artifact('hard_stops.json', {'probe_id': p_id, 'run_id': run_id, 'turn': turn_idx})
                            break
                    else:
                        self.ve.reset(p_id)

                rec_latency = history.index(True) if True in history else len(prompts)
                all_results.append({
                    'probe_id': p_id, 'run_id': run_id, 'temp': temperature,
                    't1': history[0] if len(history) > 0 else False,
                    't2': history[1] if len(history) > 1 else False,
                    't3': history[2] if len(history) > 2 else False,
                    'outcome': outcome, 'recovery_latency': rec_latency,
                    'prompt_tokens': total_pt, 'completion_tokens': total_ct, 'total_tokens': total_tt,
                    'model': api_client.model, 'vector': p_id.split('-')[0]
                })
                done += 1
                if done % 10 == 0:
                    print(f'  Progress: {done}/{total} probes')

        with open(output_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=all_results[0].keys())
            writer.writeheader()
            writer.writerows(all_results)

        completed = sum(1 for r in all_results if r['outcome'] == 'COMPLETED')
        hard_stops = sum(1 for r in all_results if r['outcome'] == 'SAFETY_HARD_STOP')
        pass_rate = round(completed / len(all_results) * 100, 1)
        print(f'Results written to {output_path}')
        print(f'Done. Pass rate: {pass_rate}% | Hard stops: {hard_stops}')

        # Auto-import to Neon DB
        try:
            import psycopg2
            db_url = os.environ.get('DATABASE_URL')
            if db_url:
                db = psycopg2.connect(db_url)
                cur = db.cursor()
                cur.execute("SELECT id FROM runs WHERE model=%s AND temperature=%s AND probe_count=%s",
                    (api_client.model, temperature, len(all_results)))
                if not cur.fetchone():
                    cur.execute("""INSERT INTO runs (model, temperature, provider, probe_count, dataset, created_at, python_version)
                        VALUES (%s,%s,%s,%s,%s,NOW(),%s) RETURNING id""",
                        (api_client.model, temperature, api_client.provider, len(all_results), 'probes_200', '3.9'))
                    run_id = cur.fetchone()[0]
                    for r in all_results:
                        cur.execute("""INSERT INTO results (run_id, probe_id, outcome, recovery_latency, created_at)
                            VALUES (%s,%s,%s,%s,NOW())""",
                            (run_id, r['probe_id'], r['outcome'], r['recovery_latency']))
                    db.commit()
                    print(f'DB: imported {len(all_results)} results (run_id={run_id})')
                else:
                    print('DB: already exists, skipped')
                db.close()
        except Exception as e:
            print(f'DB write failed: {e}')

        return all_results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True)
    parser.add_argument('--api', required=True,
        help='Provider: groq, openai, anthropic, openrouter, mistral, nvidia, google')
    parser.add_argument('--model', default=None)
    parser.add_argument('--models', default=None, help='Comma-separated list of models')
    parser.add_argument('--out', default='results.csv')
    parser.add_argument('--temperature', default='0.0')
    parser.add_argument('--runs', type=int, default=1)
    args = parser.parse_args()

    generate_run_manifest(args.data, __file__)

    models = []
    if args.models:
        models = [m.strip() for m in args.models.split(',')]
    elif args.model:
        models = [args.model]
    else:
        raise ValueError("Specify --model or --models")

    temperatures = [float(t) for t in args.temperature.split(',')]

    evaluator = MTCPEvaluator(args.data)
    for model in models:
        print(f'\n=== Model: {model} ===')
        client = APIClient(args.api, model)
        for temp in temperatures:
            print(f'  Temperature: {temp}')
            out = f'temp_{temp}_{args.out}'
            evaluator.run_benchmark(client, out, temp, args.runs)

if __name__ == '__main__': main()
