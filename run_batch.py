import subprocess
import threading

jobs = [
    ("mistral", "magistral-medium-latest"),
    ("google", "gemini-2.5-flash"),
    ("fireworks", "accounts/fireworks/models/kimi-k2-instruct-0905"),
]

nvidia_jobs = [
    ("nvidia", "deepseek-ai/deepseek-r1-distill-qwen-32b"),
    ("nvidia", "moonshotai/kimi-k2-thinking"),
]

def run_main(api, model):
    cmd = [
        "python3",
        "llm_safety_platform.py",
        "--data", "probes_200.json",
        "--api", api,
        "--model", model,
        "--temperature", "0.0,0.2,0.5,0.8",
        "--out", f"{model.replace('/', '_')}.csv",
        "--runs", "1"
    ]
    subprocess.run(cmd)

def run_ctrl(api, model):
    cmd = [
        "python3",
        "llm_safety_platform.py",
        "--data", "probes_control_20.json",
        "--api", api,
        "--model", model,
        "--temperature", "0.0",
        "--out", f"ctrl_{model.replace('/', '_')}.csv",
        "--runs", "1"
    ]
    subprocess.run(cmd)

def worker(api, model):
    print(f"Running MAIN: {model}")
    run_main(api, model)

    print(f"Running CTRL: {model}")
    run_ctrl(api, model)

threads = []

for api, model in jobs:
    t = threading.Thread(target=worker, args=(api, model))
    t.start()
    threads.append(t)

for api, model in nvidia_jobs:
    worker(api, model)

for t in threads:
    t.join()

print("All jobs complete")
