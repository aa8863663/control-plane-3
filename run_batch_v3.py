import json
import os
import shlex
import subprocess
import threading
import time
from datetime import datetime
from queue import Queue

BASE_DIR = os.getcwd()
LOG_DIR = os.path.join(BASE_DIR, "logs")
STATUS_FILE = os.path.join(BASE_DIR, "run_batch_status.json")
MAX_RETRIES = 2
RETRY_SLEEP_SECONDS = 20

os.makedirs(LOG_DIR, exist_ok=True)

JOBS = [
    {
        "provider": "mistral",
        "model": "magistral-medium-latest",
        "enabled": True,
    },
    {
        "provider": "google",
        "model": "gemini-2.5-flash",
        "enabled": True,
    },
    {
        "provider": "fireworks",
        "model": "accounts/fireworks/models/kimi-k2-instruct-0905",
        "enabled": True,
    },
    {
        "provider": "nvidia",
        "model": "deepseek-ai/deepseek-r1-distill-qwen-32b",
        "enabled": True,
    },
    {
        "provider": "nvidia",
        "model": "moonshotai/kimi-k2-thinking",
        "enabled": True,
    },
    {
        "provider": "watsonx",
        "model": "meta-llama/llama-3-405b-instruct",
        "enabled": False,  # turn on only after IBM auth is fixed
    },
]

MAIN_DATA = "probes_200.json"
CTRL_DATA = "probes_control_20.json"
TEMPS = "0.0,0.2,0.5,0.8"


def now():
    return datetime.utcnow().isoformat() + "Z"


def safe_name(text):
    return (
        text.replace("/", "_")
        .replace(":", "_")
        .replace(".", "_")
        .replace("-", "_")
    )


def load_status():
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"updated_at": now(), "jobs": {}}


def save_status(status):
    status["updated_at"] = now()
    tmp = STATUS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, sort_keys=True)
    os.replace(tmp, STATUS_FILE)


def job_key(provider, model):
    return provider + "::" + model


def set_job_status(status, provider, model, phase, state, extra=None):
    key = job_key(provider, model)
    if key not in status["jobs"]:
        status["jobs"][key] = {
            "provider": provider,
            "model": model,
            "main": "pending",
            "ctrl": "pending",
            "last_error": "",
            "updated_at": now(),
        }
    status["jobs"][key][phase] = state
    status["jobs"][key]["updated_at"] = now()
    if extra:
        for k, v in extra.items():
            status["jobs"][key][k] = v
    save_status(status)


def print_line(msg):
    print(msg, flush=True)


def run_command(cmd, log_path):
    with open(log_path, "a", encoding="utf-8") as logf:
        logf.write("\n\n===== {} =====\n".format(now()))
        logf.write("COMMAND: {}\n".format(" ".join(shlex.quote(x) for x in cmd)))
        logf.flush()

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            logf.write(line)

        rc = proc.wait()
        logf.write("\nRETURN_CODE: {}\n".format(rc))
        return rc


def build_main_cmd(provider, model):
    return [
        "python3",
        "llm_safety_platform.py",
        "--data", MAIN_DATA,
        "--api", provider,
        "--model", model,
        "--temperature", TEMPS,
        "--out", safe_name(model) + ".csv",
        "--runs", "1",
    ]


def build_ctrl_cmd(provider, model):
    return [
        "python3",
        "llm_safety_platform.py",
        "--data", CTRL_DATA,
        "--api", provider,
        "--model", model,
        "--temperature", "0.0",
        "--out", "ctrl_" + safe_name(model) + ".csv",
        "--runs", "1",
    ]


def run_with_retries(status, provider, model, phase, cmd):
    log_path = os.path.join(LOG_DIR, "{}_{}.log".format(safe_name(model), phase))

    for attempt in range(1, MAX_RETRIES + 2):
        print_line("[{}] {} {} attempt {}/{}".format(provider, phase.upper(), model, attempt, MAX_RETRIES + 1))
        set_job_status(status, provider, model, phase, "running", {"attempt": attempt})
        rc = run_command(cmd, log_path)
        if rc == 0:
            set_job_status(status, provider, model, phase, "done", {"last_error": ""})
            return True

        err = "return_code={}".format(rc)
        set_job_status(status, provider, model, phase, "failed", {"last_error": err})

        if attempt <= MAX_RETRIES:
            print_line("[{}] {} failed for {}. Retrying in {}s".format(provider, phase, model, RETRY_SLEEP_SECONDS))
            time.sleep(RETRY_SLEEP_SECONDS)

    return False


def provider_worker(provider, jobs, status):
    print_line("=== START provider queue: {} ===".format(provider))
    for job in jobs:
        model = job["model"]

        if not job.get("enabled", True):
            set_job_status(status, provider, model, "main", "disabled")
            set_job_status(status, provider, model, "ctrl", "disabled")
            print_line("[{}] SKIP disabled {}".format(provider, model))
            continue

        key = job_key(provider, model)
        existing = status["jobs"].get(key, {})

        if existing.get("main") == "done":
            print_line("[{}] MAIN already done for {}".format(provider, model))
        else:
            ok = run_with_retries(status, provider, model, "main", build_main_cmd(provider, model))
            if not ok:
                print_line("[{}] MAIN permanently failed for {}. Skipping CTRL.".format(provider, model))
                continue

        if existing.get("ctrl") == "done":
            print_line("[{}] CTRL already done for {}".format(provider, model))
        else:
            ok = run_with_retries(status, provider, model, "ctrl", build_ctrl_cmd(provider, model))
            if not ok:
                print_line("[{}] CTRL permanently failed for {}".format(provider, model))

        if provider in ("nvidia", "fireworks", "bedrock", "watsonx"):
            time.sleep(5)

    print_line("=== END provider queue: {} ===".format(provider))


def main():
    if not os.path.exists("llm_safety_platform.py"):
        raise RuntimeError("Run this from ~/Projects/control-plane-3")

    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is not loaded")

    status = load_status()

    provider_groups = {}
    for job in JOBS:
        provider_groups.setdefault(job["provider"], []).append(job)

    threads = []
    for provider, jobs in provider_groups.items():
        t = threading.Thread(target=provider_worker, args=(provider, jobs, status), daemon=False)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    print_line("\nAll provider queues complete.")
    print_line("Status written to: {}".format(STATUS_FILE))
    print_line("Logs written to: {}".format(LOG_DIR))


if __name__ == "__main__":
    main()
