import subprocess
import threading

# Missing probes_500 runs to complete
# Format: (api, model, temperatures)
jobs = [
    # grok-3-mini T=0.5 and T=0.8 via openrouter
    ("openrouter", "x-ai/grok-3-mini", "0.5,0.8"),

    # claude-sonnet-4-20250514 T=0.8 via anthropic
    ("anthropic", "eu.anthropic.claude-sonnet-4-5-20250929-v1:0", "0.8"),

    # llama-3.3-70b-versatile T=0.2/0.5/0.8 via groq
    ("groq", "llama-3.3-70b-versatile", "0.2,0.5,0.8"),

    # qwen3-8b T=0.8 via fireworks
    ("fireworks", "accounts/fireworks/models/qwen3-8b", "0.8"),
]


def run_job(api, model, temps):
    safe_name = model.replace("/", "_").replace(":", "_")
    out_file = f"missing500_{safe_name}_t{temps.replace(',','_')}.csv"
    cmd = [
        "python3", "llm_safety_platform.py",
        "--data", "probes_500.json",
        "--api", api,
        "--model", model,
        "--temperature", temps,
        "--out", out_file,
        "--runs", "1"
    ]
    print(f"[START] {model}  temps={temps}  api={api}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[DONE]  {model}  temps={temps} -> {out_file}")
    else:
        print(f"[ERROR] {model}  temps={temps}")
        print(result.stderr[-500:] if result.stderr else "(no stderr)")


threads = []
for api, model, temps in jobs:
    t = threading.Thread(target=run_job, args=(api, model, temps))
    t.start()
    threads.append(t)

for t in threads:
    t.join()

print("\nAll missing_500 runs complete.")
