"""
scheduled_runs.py — Weekly automated benchmark runner for Control Plane 3

Runs all models at all 4 temperatures every Monday at 02:00 UTC.
Import and call start_scheduler() from api_server.py on startup.

Each model runs one at a time to avoid API rate limits.
Results go directly into the production Neon database via llm_safety_platform.py.
Logs are written to /tmp/cp3_scheduler.log
"""

import subprocess
import os
import logging
from datetime import datetime
from typing import List, Tuple

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SCHEDULER] %(message)s",
    handlers=[
        logging.FileHandler("/tmp/cp3_scheduler.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger("cp3_scheduler")

# ── Model registry ────────────────────────────────────────────────────────────
# Format: (model_name, api_provider)
# Update this list when new models are added.

MODELS: List[Tuple[str, str]] = [
    # === ORIGINAL 11 ===
    ("grok-3-mini",                                 "openrouter"),
    ("nvidia/llama-3.3-nemotron-super-49b-v1",      "nvidia"),
    ("gpt-4o-mini",                                 "openai"),
    ("gpt-3.5-turbo",                               "openai"),
    ("llama-3.3-70b-versatile",                     "groq"),
    ("llama-3.1-8b-instant",                        "groq"),
    ("claude-sonnet-4-20250514",                    "anthropic"),
    ("claude-haiku-4-5-20251001",                   "anthropic"),
    ("gpt-4o",                                      "openai"),
    ("gemini-2.0-flash",                            "openrouter"),
    ("nvidia/gemma-3-27b-it",                       "nvidia"),
    # === NEW MODELS ===
    ("meta/llama-4-maverick-17b-128e-instruct",     "nvidia"),
    ("meta-llama/llama-4-scout",                    "openrouter"),
    ("cohere-command-r-plus",                       "openrouter"),
    ("mistral-large-latest",                        "mistral"),
    ("mistral-small-latest",                        "mistral"),
    ("deepseek/deepseek-r1",                        "openrouter"),
    ("microsoft/phi-4-mini-instruct",               "nvidia"),
    ("qwen/qwen2.5-7b-instruct",                    "nvidia"),
    ("ibm/granite-3.3-8b-instruct",                "nvidia"),
    ("qwen/qwq-32b",                                "nvidia"),
    ("amazon.nova-lite-v1:0",                       "bedrock"),
    ("amazon.nova-pro-v1:0",                        "bedrock"),
    ("amazon.nova-micro-v1:0",                      "bedrock"),
]

TEMPERATURES = [0.0, 0.2, 0.5, 0.8]

# ── Base directory (same folder as api_server.py) ─────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROBES_PATH = os.path.join(BASE_DIR, "probes_200.json")
PLATFORM = os.path.join(BASE_DIR, "llm_safety_platform.py")


def run_single(model: str, api: str, temperature: float) -> bool:
    """Run one model at one temperature. Returns True if successful."""
    out_file = f"/tmp/sched_{model.replace('/', '_')}_{temperature}.csv"
    cmd = [
        "python3", PLATFORM,
        "--data", PROBES_PATH,
        "--api", api,
        "--model", model,
        "--temperature", str(temperature),
        "--runs", "1",
        "--out", out_file,
    ]
    log.info(f"Starting: {model} @ T={temperature}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,          # 10 minute timeout per run
            cwd=BASE_DIR,
        )
        if result.returncode == 0:
            log.info(f"✓ Completed: {model} @ T={temperature}")
            return True
        else:
            log.error(f"✗ Failed: {model} @ T={temperature}\n{result.stderr[:500]}")
            return False
    except subprocess.TimeoutExpired:
        log.error(f"✗ Timeout: {model} @ T={temperature} (>10 min)")
        return False
    except Exception as e:
        log.error(f"✗ Exception: {model} @ T={temperature} — {e}")
        return False


def weekly_benchmark_job():
    """
    Main scheduled job. Runs all models at all temperatures.
    Runs sequentially to respect API rate limits.
    """
    start = datetime.utcnow()
    log.info(f"=== Weekly benchmark run started at {start.isoformat()} ===")

    total = len(MODELS) * len(TEMPERATURES)
    passed = 0
    failed = 0

    for model, api in MODELS:
        for temp in TEMPERATURES:
            ok = run_single(model, api, temp)
            if ok:
                passed += 1
            else:
                failed += 1

    end = datetime.utcnow()
    duration = (end - start).total_seconds() / 60
    log.info(
        f"=== Weekly run complete. "
        f"{passed}/{total} succeeded, {failed} failed. "
        f"Duration: {duration:.1f} min ==="
    )


# ── Scheduler setup ───────────────────────────────────────────────────────────

_scheduler = None


def start_scheduler():
    """
    Call this once from api_server.py on startup.
    Schedules the weekly job for every Monday at 02:00 UTC.
    """
    global _scheduler

    if _scheduler is not None:
        log.info("Scheduler already running — skipping init")
        return

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        weekly_benchmark_job,
        trigger=CronTrigger(day_of_week="mon", hour=2, minute=0),
        id="weekly_benchmarks",
        name="Weekly MTCP benchmark run",
        replace_existing=True,
        misfire_grace_time=3600,   # Allow up to 1hr late start if server was down
    )
    _scheduler.start()
    log.info("Scheduler started — weekly benchmarks scheduled for Monday 02:00 UTC")


def stop_scheduler():
    """Graceful shutdown — call on app teardown if needed."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")
