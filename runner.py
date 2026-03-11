#!/usr/bin/env python3
"""
CP3 / MTCP Production Evaluation Runner
Durable multi-provider orchestration for llm_safety_platform.py

Matches actual CP3 benchmark CLI:
  --data
  --api
  --model
  --temperature
  --out
  --runs

Uses actual benchmark DB schema:
  runs(model, provider, dataset, temperature, probe_count, ...)
"""

import argparse
import hashlib
import json
import logging
import os
import random
import signal
import subprocess
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor


# ============================================================================
# Paths / files
# ============================================================================

BASE_DIR = Path(__file__).parent
LOCK_FILE = BASE_DIR / "runner.lock"
STATE_FILE = BASE_DIR / "runner_state.json"
HEARTBEAT_FILE = BASE_DIR / "runner_heartbeat.json"
JOB_FILE = BASE_DIR / "providers.json"
LOG_DIR = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "runner_outputs"

LOG_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


# ============================================================================
# Benchmark datasets / CLI settings
# ============================================================================

MAIN_DATASET = "probes_200.json"
CTRL_DATASET = "probes_control_20.json"

MAIN_TEMPERATURES = "0.0,0.2,0.5,0.8"
CTRL_TEMPERATURES = "0.0"

MAIN_RUNS_EXPECTED = 4   # one per temperature
CTRL_RUNS_EXPECTED = 1   # one ctrl run at T=0.0


# ============================================================================
# Provider settings
# ============================================================================

PROVIDER_KEYS = {
    "groq": ["GROQ_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "mistral": ["MISTRAL_API_KEY"],
    "nvidia": ["NVIDIA_API_KEY"],
    "google": ["GOOGLE_API_KEY"],
    "github": ["GITHUB_API_KEY"],
    "fireworks": ["FIREWORKS_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "cerebras": ["CEREBRAS_API_KEY"],
    "cohere": ["COHERE_API_KEY"],
    "bedrock": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
    "watsonx": ["IBM_WATSONX_API_KEY"],
}

# Providers that should be serialized internally
SERIAL_PROVIDERS = {
    "nvidia",
    "bedrock",
    "watsonx",
    "fireworks",
    "cerebras",
}

# Cooldown between jobs per provider
PROVIDER_COOLDOWNS = {
    "nvidia": 20,
    "bedrock": 30,
    "watsonx": 30,
    "fireworks": 15,
    "cerebras": 15,
    "google": 10,
    "mistral": 10,
    "openai": 10,
    "cohere": 10,
    "groq": 10,
    "deepseek": 10,
    "anthropic": 20,
    "openrouter": 20,
    "github": 10,
}

# Retry / timeout settings
MAX_RETRIES = 3
RETRY_BASE_SECONDS = 30
HEARTBEAT_INTERVAL = 15

PHASE_TIMEOUTS = {
    "main": 7200,   # 2 hours
    "ctrl": 1800,   # 30 mins
}

RETRYABLE_MARKERS = [
    "429",
    "rate limit",
    "throttl",
    "504",
    "gateway timeout",
    "temporarily unavailable",
    "timeout",
    "timed out",
    "connection reset",
    "connection aborted",
    "remote disconnected",
    "service unavailable",
    "internal server error",
    "tensorrt",
]


stop_requested = False
state_lock = threading.Lock()


# ============================================================================
# Utilities
# ============================================================================

def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def safe_name(text: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "_" for c in text)
    suffix = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    return "{}_{}".format(cleaned[:60], suffix)


def exp_backoff_seconds(attempt: int, provider: str) -> int:
    base = max(PROVIDER_COOLDOWNS.get(provider, RETRY_BASE_SECONDS), RETRY_BASE_SECONDS)
    backoff = base * (2 ** (attempt - 1))
    jitter = random.randint(0, max(1, base // 2))
    return min(backoff + jitter, 3600)


def print_line(msg: str) -> None:
    print(msg, flush=True)
    logging.info(msg)


def require_file(path: Path) -> None:
    if not path.exists():
        raise RuntimeError("Missing required file: {}".format(path))


# ============================================================================
# Database
# ============================================================================

def db_connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not loaded")
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def run_counts(provider: str, model: str) -> Tuple[int, int]:
    """
    Count existing main / ctrl runs for THIS provider+model.
    Uses actual CP3 benchmark schema: runs(provider, model, dataset, ...)
    """
    conn = db_connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
              SUM(CASE WHEN (dataset = 'probes_200' OR dataset = 'main') THEN 1 ELSE 0 END) AS main_runs,
              SUM(CASE WHEN dataset = 'ctrl' THEN 1 ELSE 0 END) AS ctrl_runs
            FROM runs
            WHERE model = %s
              AND provider = %s
            """,
            (model, provider),
        )
        row = cur.fetchone() or {}
        main_runs = int(row["main_runs"] or 0)
        ctrl_runs = int(row["ctrl_runs"] or 0)
        return main_runs, ctrl_runs
    finally:
        conn.close()


def should_run_main(provider: str, model: str) -> bool:
    main_runs, _ = run_counts(provider, model)
    return main_runs < MAIN_RUNS_EXPECTED


def should_run_ctrl(provider: str, model: str) -> bool:
    _, ctrl_runs = run_counts(provider, model)
    return ctrl_runs < CTRL_RUNS_EXPECTED


# ============================================================================
# Lock management
# ============================================================================

def acquire_lock() -> None:
    if LOCK_FILE.exists():
        try:
            with open(LOCK_FILE, "r", encoding="utf-8") as f:
                lines = [x.strip() for x in f.readlines() if x.strip()]
            if lines:
                old_pid = int(lines[0])
                if pid_alive(old_pid):
                    raise RuntimeError(
                        "Lock file exists and PID {} is still active. Another runner is running.".format(old_pid)
                    )
                logging.warning("Reclaiming stale lock from dead PID %s", old_pid)
            LOCK_FILE.unlink()
        except Exception as e:
            logging.warning("Removing corrupt or stale lock file: %s", e)
            try:
                LOCK_FILE.unlink()
            except Exception:
                pass

    with open(LOCK_FILE, "w", encoding="utf-8") as f:
        f.write("{}\n".format(os.getpid()))
        f.write("{}\n".format(now()))

    logging.info("Lock acquired by PID %s", os.getpid())


def release_lock() -> None:
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()
        logging.info("Lock released")


# ============================================================================
# State manager
# ============================================================================

class StateManager(object):
    def __init__(self) -> None:
        self.jobs = {}
        self.events = []
        self.started_at = None
        self.completed_at = None
        self.last_heartbeat = None
        self.load()

    def _job_key(self, provider: str, model: str, phase: str) -> str:
        return "{}::{}::{}".format(provider, model, phase)

    def load(self) -> None:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.jobs = data.get("jobs", {})
            self.events = data.get("events", [])
            self.started_at = data.get("started_at")
            self.completed_at = data.get("completed_at")
            self.last_heartbeat = data.get("last_heartbeat")

    def save(self) -> None:
        with state_lock:
            data = {
                "jobs": self.jobs,
                "events": self.events[-500:],
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                "last_heartbeat": self.last_heartbeat,
            }
            temp = STATE_FILE.with_suffix(".tmp")
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            temp.replace(STATE_FILE)

    def save_heartbeat(self) -> None:
        with state_lock:
            running_jobs = []
            for item in self.jobs.values():
                if item.get("status") == "running":
                    running_jobs.append({
                        "provider": item.get("provider"),
                        "model": item.get("model"),
                        "phase": item.get("phase"),
                        "attempt": item.get("attempt"),
                    })
            data = {
                "pid": os.getpid(),
                "last_heartbeat": now(),
                "running_jobs": running_jobs,
            }
            with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.last_heartbeat = data["last_heartbeat"]

    def add_event(self, message: str) -> None:
        with state_lock:
            self.events.append({
                "timestamp": now(),
                "message": message,
            })
        self.save()

    def ensure_job(self, provider: str, model: str, phase: str) -> None:
        key = self._job_key(provider, model, phase)
        if key not in self.jobs:
            self.jobs[key] = {
                "provider": provider,
                "model": model,
                "phase": phase,
                "status": "pending",
                "attempt": 0,
                "started_at": None,
                "completed_at": None,
                "error": None,
                "pid": None,
            }

    def get_job(self, provider: str, model: str, phase: str) -> Dict[str, Any]:
        with state_lock:
            self.ensure_job(provider, model, phase)
            return dict(self.jobs[self._job_key(provider, model, phase)])

    def set_job_status(
        self,
        provider: str,
        model: str,
        phase: str,
        status: str,
        error: Optional[str] = None,
        pid: Optional[int] = None,
    ) -> None:
        with state_lock:
            self.ensure_job(provider, model, phase)
            key = self._job_key(provider, model, phase)
            old_status = self.jobs[key]["status"]
            self.jobs[key]["status"] = status
            self.jobs[key]["error"] = error
            self.jobs[key]["pid"] = pid
            if status == "running" and not self.jobs[key]["started_at"]:
                self.jobs[key]["started_at"] = now()
            if status in ("done", "failed", "timed_out", "skipped", "disabled", "interrupted"):
                self.jobs[key]["completed_at"] = now()
            if old_status != status:
                self.events.append({
                    "timestamp": now(),
                    "message": "{} / {} / {}: {} -> {}".format(provider, model, phase, old_status, status),
                })
        self.save()

    def increment_attempt(self, provider: str, model: str, phase: str) -> int:
        with state_lock:
            self.ensure_job(provider, model, phase)
            key = self._job_key(provider, model, phase)
            self.jobs[key]["attempt"] += 1
            attempt = self.jobs[key]["attempt"]
        self.save()
        return attempt

    def recover_interrupted_jobs(self) -> None:
        """
        Recover any unfinished jobs from a prior crash/termination.
        Also convert timed_out to interrupted so they can retry on resume.
        """
        changed = False
        with state_lock:
            for key, job in self.jobs.items():
                if job.get("status") in ("running", "timed_out", "interrupted"):
                    self.jobs[key]["status"] = "interrupted"
                    self.jobs[key]["error"] = "Recovered for retry on resume"
                    changed = True
        if changed:
            self.save()

    def summary(self) -> Dict[str, Any]:
        by_status = defaultdict(int)
        by_phase = defaultdict(int)
        failed_jobs = []

        with state_lock:
            for item in self.jobs.values():
                by_status[item.get("status", "unknown")] += 1
                by_phase[item.get("phase", "unknown")] += 1
                if item.get("status") in ("failed", "timed_out"):
                    failed_jobs.append(
                        "{}/{}/{}".format(item.get("provider"), item.get("model"), item.get("phase"))
                    )

        return {
            "total_jobs": len(self.jobs),
            "by_status": dict(by_status),
            "by_phase": dict(by_phase),
            "failed_jobs": failed_jobs,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# ============================================================================
# Job loading / validation
# ============================================================================

def validate_jobs(data: List[Dict[str, Any]]) -> None:
    if not isinstance(data, list):
        raise ValueError("providers.json must contain a JSON list")

    for i, entry in enumerate(data):
        if "provider" not in entry:
            raise ValueError("Job {} missing provider".format(i))
        if "model" not in entry:
            raise ValueError("Job {} missing model".format(i))
        if not isinstance(entry.get("enabled", True), bool):
            raise ValueError("Job {} has non-bool enabled".format(i))
        if "priority" in entry and not isinstance(entry["priority"], int):
            raise ValueError("Job {} has non-int priority".format(i))


def load_job_queue(
    args: argparse.Namespace,
    state: StateManager,
) -> Dict[str, List[Tuple[str, str, int]]]:
    require_file(JOB_FILE)
    with open(JOB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    validate_jobs(data)

    jobs_by_provider = defaultdict(list)

    for entry in data:
        provider = entry["provider"]
        model = entry["model"]
        enabled = entry.get("enabled", True)
        priority = entry.get("priority", 50)

        if args.provider and provider != args.provider:
            continue
        if args.model and args.model not in model:
            continue

        if not enabled and not args.force:
            state.ensure_job(provider, model, "main")
            state.ensure_job(provider, model, "ctrl")
            state.set_job_status(provider, model, "main", "disabled")
            state.set_job_status(provider, model, "ctrl", "disabled")
            continue

        if not args.ctrl_only:
            if args.force or should_run_main(provider, model):
                jobs_by_provider[provider].append((model, "main", priority))
            else:
                state.ensure_job(provider, model, "main")
                state.set_job_status(provider, model, "main", "done")

        if not args.main_only:
            if args.force or should_run_ctrl(provider, model):
                jobs_by_provider[provider].append((model, "ctrl", priority))
            else:
                state.ensure_job(provider, model, "ctrl")
                state.set_job_status(provider, model, "ctrl", "done")

    for provider in jobs_by_provider:
        jobs_by_provider[provider].sort(key=lambda x: x[2], reverse=True)

    return jobs_by_provider


# ============================================================================
# Provider availability
# ============================================================================

def provider_available(provider: str) -> Tuple[bool, str]:
    required = PROVIDER_KEYS.get(provider, [])
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        return False, "missing env: " + ", ".join(missing)
    return True, ""


# ============================================================================
# Command building
# ============================================================================

def timestamp_for_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def build_command(provider: str, model: str, phase: str) -> Tuple[List[str], Path]:
    stamp = timestamp_for_filename()

    if phase == "main":
        out_file = OUTPUT_DIR / "{}_main_{}.csv".format(safe_name(model), stamp)
        cmd = [
            sys.executable,
            str(BASE_DIR / "llm_safety_platform.py"),
            "--data", MAIN_DATASET,
            "--api", provider,
            "--model", model,
            "--temperature", MAIN_TEMPERATURES,
            "--out", str(out_file),
            "--runs", "1",
        ]
        return cmd, out_file

    out_file = OUTPUT_DIR / "{}_ctrl_{}.csv".format(safe_name(model), stamp)
    cmd = [
        sys.executable,
        str(BASE_DIR / "llm_safety_platform.py"),
        "--data", CTRL_DATASET,
        "--api", provider,
        "--model", model,
        "--temperature", CTRL_TEMPERATURES,
        "--out", str(out_file),
        "--runs", "1",
    ]
    return cmd, out_file


# ============================================================================
# Subprocess execution
# ============================================================================

def run_subprocess_with_timeout(
    cmd: List[str],
    timeout_seconds: int,
    log_file: Path,
) -> Tuple[int, str]:
    last_lines = []
    try:
        with open(log_file, "w", encoding="utf-8") as log:
            log.write("===== START {} =====\n".format(now()))
            log.write("COMMAND: {}\n".format(" ".join(shlex.quote(x) for x in cmd)))
            log.flush()

            proc = subprocess.Popen(
                cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,
            )

            try:
                return_code = proc.wait(timeout=timeout_seconds)
                return return_code, ""
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    time.sleep(2)
                    if proc.poll() is None:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass
                return -1, "timeout after {} seconds".format(timeout_seconds)
    except Exception as e:
        return -1, str(e)


def tail_log_text(log_file: Path, max_lines: int = 100) -> str:
    if not log_file.exists():
        return ""
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-max_lines:]
        return "\n".join([line.strip().lower() for line in lines if line.strip()])
    except Exception:
        return ""


def retryable(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in RETRYABLE_MARKERS)


# ============================================================================
# Job execution
# ============================================================================

def process_job(
    provider: str,
    model: str,
    phase: str,
    state: StateManager,
) -> bool:
    ok, reason = provider_available(provider)
    if not ok:
        state.set_job_status(provider, model, phase, "skipped", error=reason)
        print_line("[{}] skipping {} / {} ({})".format(provider, model, phase, reason))
        return False

    # DB is source of truth first
    if phase == "main" and not should_run_main(provider, model):
        state.set_job_status(provider, model, phase, "done")
        print_line("[{}] main already complete in DB: {}".format(provider, model))
        return True

    if phase == "ctrl" and not should_run_ctrl(provider, model):
        state.set_job_status(provider, model, phase, "done")
        print_line("[{}] ctrl already complete in DB: {}".format(provider, model))
        return True

    record = state.get_job(provider, model, phase)
    if record.get("status") == "done":
        return True

    if record.get("attempt", 0) >= MAX_RETRIES:
        state.set_job_status(provider, model, phase, "failed", error="max retries exceeded")
        return False

    attempt = state.increment_attempt(provider, model, phase)
    if attempt > 1:
        sleep_for = exp_backoff_seconds(attempt, provider)
        print_line("[{}] retrying {} / {} in {}s".format(provider, model, phase, sleep_for))
        time.sleep(sleep_for)

    cmd, out_file = build_command(provider, model, phase)
    log_file = LOG_DIR / "{}_{}_{}.log".format(
        safe_name(provider),
        safe_name(model),
        phase,
    )

    state.set_job_status(provider, model, phase, "running", pid=os.getpid())
    print_line("[{}] starting {} / {}".format(provider, model, phase))
    print_line("[{}] output -> {}".format(provider, out_file))

    timeout = PHASE_TIMEOUTS.get(phase, 3600)
    rc, error = run_subprocess_with_timeout(cmd, timeout, log_file)
    tail = tail_log_text(log_file)

    # Re-check DB before declaring failure — run may have succeeded but process/log handling failed
    if phase == "main" and not should_run_main(provider, model):
        state.set_job_status(provider, model, phase, "done")
        return True

    if phase == "ctrl" and not should_run_ctrl(provider, model):
        state.set_job_status(provider, model, phase, "done")
        return True

    if rc == 0:
        state.set_job_status(provider, model, phase, "done")
        return True

    if "timeout" in (error or "").lower():
        state.set_job_status(provider, model, phase, "timed_out", error=error)
    else:
        state.set_job_status(provider, model, phase, "failed", error=error or "exit code {}".format(rc))

    if retryable("{}\n{}".format(error, tail)):
        return False

    return False


# ============================================================================
# Worker threads
# ============================================================================

def provider_worker(
    provider: str,
    jobs: List[Tuple[str, str, int]],
    state: StateManager,
    stop_event: threading.Event,
) -> None:
    print_line("=== START {} queue ===".format(provider))

    for model, phase, priority in jobs:
        del priority

        if stop_event.is_set() or stop_requested:
            print_line("[{}] stop requested; halting queue".format(provider))
            break

        success = process_job(provider, model, phase, state)

        # Retry loop is state-driven — if failed/timed_out and attempts remain,
        # rerun immediately in this queue until success or retry limit
        while not success:
            record = state.get_job(provider, model, phase)
            if record.get("attempt", 0) >= MAX_RETRIES:
                break
            if stop_event.is_set() or stop_requested:
                break
            success = process_job(provider, model, phase, state)

        time.sleep(PROVIDER_COOLDOWNS.get(provider, 10))

    print_line("=== END {} queue ===".format(provider))


def heartbeat_worker(state: StateManager, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        state.save_heartbeat()
        stop_event.wait(HEARTBEAT_INTERVAL)


# ============================================================================
# Signals
# ============================================================================

def signal_handler(signum: int, frame: Any) -> None:
    del signum, frame
    global stop_requested
    stop_requested = True
    print_line("Stop requested. Finishing current subprocess and exiting cleanly...")


# ============================================================================
# Main
# ============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CP3 Production Evaluation Runner")
    parser.add_argument("--provider", default=None, help="Run only one provider queue")
    parser.add_argument("--model", default=None, help="Run only models containing this substring")
    parser.add_argument("--main-only", action="store_true", help="Only run main probes")
    parser.add_argument("--ctrl-only", action="store_true", help="Only run control probes")
    parser.add_argument("--force", action="store_true", help="Force run even if DB says complete / job disabled")
    parser.add_argument("--resume", action="store_true", help="Resume interrupted/timed-out work from state file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run and exit")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.main_only and args.ctrl_only:
        raise RuntimeError("--main-only and --ctrl-only cannot be used together")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "runner_{}.log".format(timestamp_for_filename())),
            logging.StreamHandler(),
        ],
    )

    require_file(BASE_DIR / "llm_safety_platform.py")
    require_file(BASE_DIR / MAIN_DATASET)
    require_file(BASE_DIR / CTRL_DATASET)

    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is not loaded")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    acquire_lock()

    try:
        state = StateManager()
        if args.resume:
            state.recover_interrupted_jobs()

        if not state.started_at:
            state.started_at = now()
        state.save()

        jobs_by_provider = load_job_queue(args, state)

        total_jobs = sum(len(v) for v in jobs_by_provider.values())
        print_line("Loaded {} jobs across {} providers".format(total_jobs, len(jobs_by_provider)))

        if args.dry_run:
            for provider, jobs in jobs_by_provider.items():
                print_line("[{}] {} jobs".format(provider, len(jobs)))
                for model, phase, priority in jobs[:10]:
                    print_line("  - {} / {} (priority {})".format(model, phase, priority))
            return

        stop_event = threading.Event()

        hb = threading.Thread(target=heartbeat_worker, args=(state, stop_event), daemon=True)
        hb.start()

        workers = []
        for provider, jobs in jobs_by_provider.items():
            t = threading.Thread(
                target=provider_worker,
                args=(provider, jobs, state, stop_event),
                name="worker-{}".format(provider),
                daemon=False,
            )
            t.start()
            workers.append(t)

        for worker in workers:
            worker.join()

        stop_event.set()
        hb.join(timeout=5)

        state.completed_at = now()
        state.save()

        summary = state.summary()
        print_line("=" * 60)
        print_line("EXECUTION SUMMARY")
        print_line("=" * 60)
        print_line("Total jobs: {}".format(summary["total_jobs"]))
        print_line("By status: {}".format(summary["by_status"]))
        print_line("By phase: {}".format(summary["by_phase"]))
        if summary["failed_jobs"]:
            print_line("Failed jobs:")
            for item in summary["failed_jobs"]:
                print_line("  - {}".format(item))

        if summary["started_at"] and summary["completed_at"]:
            start = datetime.fromisoformat(summary["started_at"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(summary["completed_at"].replace("Z", "+00:00"))
            duration = (end - start).total_seconds()
            print_line("Duration: {:.0f}s ({:.1f}m)".format(duration, duration / 60.0))

        # Non-zero exit if any jobs still failed/timed out
        failed_count = summary["by_status"].get("failed", 0) + summary["by_status"].get("timed_out", 0)
        if failed_count > 0:
            sys.exit(1)

    finally:
        release_lock()


if __name__ == "__main__":
    main()
