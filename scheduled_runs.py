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
    ("x-ai/grok-3-mini",                            "openrouter"),
    ("nvidia/llama-3.3-nemotron-super-49b-v1",      "nvidia"),
    ("gpt-4o-mini",                                 "openai"),
    ("gpt-3.5-turbo",                               "openai"),
    ("llama-3.3-70b-versatile",                     "groq"),
    ("llama-3.1-8b-instant",                        "groq"),
    ("claude-sonnet-4-20250514",                    "anthropic"),
    ("claude-haiku-4-5-20251001",                   "anthropic"),
    ("gpt-4o",                                      "openai"),
    ("google/gemini-2.0-flash-001",                 "openrouter"),
    ("google/gemma-3-27b-it",                       "openrouter"),
    # === NEW MODELS ===
    ("meta/llama-4-maverick-17b-128e-instruct",     "nvidia"),
    ("meta-llama/llama-4-scout",                    "openrouter"),
    ("command-r-plus-08-2024",                      "cohere"),
    ("mistral-large-latest",                        "mistral"),
    ("mistral-small-latest",                        "mistral"),
    ("deepseek/deepseek-r1",                        "openrouter"),
    ("microsoft/phi-4-mini-instruct",               "nvidia"),
    ("qwen/qwen2.5-7b-instruct",                    "nvidia"),
    ("ibm/granite-3.3-8b-instruct",                 "nvidia"),
    ("qwen/qwq-32b",                                "nvidia"),
    ("amazon.nova-lite-v1:0",                       "bedrock"),
    ("amazon.nova-pro-v1:0",                        "bedrock"),
    ("amazon.nova-micro-v1:0",                      "bedrock"),
    # === PROVIDERS.JSON SYNC — 2026-03-27 ===
    ("magistral-medium-latest",                     "mistral"),
    ("google/gemini-2.5-flash",                     "openrouter"),
    ("accounts/fireworks/models/kimi-k2-instruct-0905", "fireworks"),
    ("deepseek-ai/deepseek-r1-distill-qwen-32b",   "nvidia"),
    ("moonshotai/kimi-k2-thinking",                 "nvidia"),
    ("llama3.1-8b",                                  "cerebras"),
    # === BEDROCK CLAUDE (ctrl probes) ===
    ("eu.anthropic.claude-sonnet-4-5-20250929-v1:0",  "bedrock"),
    ("eu.anthropic.claude-haiku-4-5-20251001-v1:0",   "bedrock"),
    ("eu.anthropic.claude-sonnet-4-6",                "bedrock"),
    ("eu.anthropic.claude-opus-4-5-20251101-v1:0",    "bedrock"),
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


# ── Governance scheduled jobs ─────────────────────────────────────────────────

def hourly_governance_alerts():
    """Run alert_runner --check-all every hour."""
    log.info("Running hourly governance alert check...")
    try:
        result = subprocess.run(
            ["python3", os.path.join(os.path.dirname(__file__), "alert_runner.py"), "--check-all"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            log.info(f"Alert check complete: {result.stdout.strip()[-100:]}")
        else:
            log.warning(f"Alert check failed: {result.stderr.strip()[-200:]}")
    except Exception as e:
        log.error(f"Alert check error: {e}")


def daily_bec_verification():
    """Run bec_runner --verify --chain-id main daily at 03:00 UTC."""
    log.info("Running daily BEC chain verification...")
    try:
        result = subprocess.run(
            ["python3", os.path.join(os.path.dirname(__file__), "bec_runner.py"), "--verify", "--chain-id", "main"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            log.info(f"BEC verify complete: {result.stdout.strip()[-100:]}")
        else:
            log.warning(f"BEC verify failed: {result.stderr.strip()[-200:]}")
    except Exception as e:
        log.error(f"BEC verify error: {e}")


def weekly_tds_check():
    """Run TDS check for all models with baselines, weekly on Tuesday."""
    log.info("Running weekly TDS drift check...")
    try:
        from tds_runner import run_tds_check
        import psycopg2
        from psycopg2.extras import RealDictCursor
        db_url = os.environ.get("DATABASE_URL", "")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT DISTINCT model FROM tds_baselines")
        models = [r["model"] for r in cur.fetchall()]
        conn.close()
        for model in models:
            try:
                run_tds_check(model, provider=None, dry_run=False, no_db=False)
                log.info(f"  TDS check complete: {model}")
            except Exception as e:
                log.warning(f"  TDS check failed for {model}: {e}")
        log.info(f"Weekly TDS check complete for {len(models)} models")
    except Exception as e:
        log.error(f"TDS check error: {e}")


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
        misfire_grace_time=3600,
    )
    _scheduler.add_job(
        hourly_governance_alerts,
        trigger=CronTrigger(minute=0),
        id="hourly_alerts",
        name="Hourly governance alert check",
        replace_existing=True,
        misfire_grace_time=300,
    )
    _scheduler.add_job(
        daily_bec_verification,
        trigger=CronTrigger(hour=3, minute=0),
        id="daily_bec_verify",
        name="Daily BEC chain verification",
        replace_existing=True,
        misfire_grace_time=1800,
    )
    _scheduler.add_job(
        weekly_tds_check,
        trigger=CronTrigger(day_of_week="tue", hour=2, minute=0),
        id="weekly_tds",
        name="Weekly TDS drift check",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    log.info("Scheduler started — benchmarks Mon 02:00, alerts hourly, BEC daily 03:00, TDS Tue 02:00")


def stop_scheduler():
    """Graceful shutdown — call on app teardown if needed."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")
