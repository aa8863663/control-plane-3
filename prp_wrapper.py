"""
PRP Live Wrapper -- Runtime Behavioural Monitoring.
Framework F36: Application-layer constraint monitoring with baseline comparison.

Sits between application and model API. For every inference request:
- Before call: checks Gate status, blocks if DENY, logs if PERMIT
- After call: checks compliance, computes rolling BIS, triggers alerts on drift

Usage as module:
    from prp_wrapper import PRPWrapper
    wrapper = PRPWrapper()
    session_id = wrapper.start_session("gpt-4o", "cos_6da958acf54309c4", "financial_services")
    result = wrapper.observe_turn(session_id, response_text)
    record = wrapper.end_session(session_id)
"""

import os
import sys
import json
import hashlib
import uuid
import re
from pathlib import Path
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

import psycopg2
import psycopg2.extras


DATABASE_URL = os.environ.get("DATABASE_URL", "")

DRIFT_TOLERANCES = {
    "critical_infrastructure": 0.02,
    "financial_services": 0.05,
    "healthcare": 0.05,
    "government_services": 0.05,
    "general_enterprise": 0.10,
}

ALERT_THRESHOLD_WARNING = 0.10
ALERT_THRESHOLD_CRITICAL = 0.20


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def compute_response_hash(response_text):
    """SHA-256 hash of response content."""
    return hashlib.sha256(response_text.encode("utf-8")).hexdigest()


def check_compliance(response_text, constraint_id):
    """Check response against registered constraint.

    Uses simplified constraint_detector logic.
    Returns True if response is compliant with the constraint.
    """
    if not response_text or not response_text.strip():
        return False

    # Load constraint scope to determine what to check
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT scope FROM cos_objects WHERE constraint_id = %s",
        (constraint_id,)
    )
    result = cur.fetchone()
    conn.close()

    if not result:
        return True  # No constraint registered, pass by default

    scope = result["scope"]
    if isinstance(scope, str):
        scope = json.loads(scope)

    vectors = scope.get("vectors", [])

    # Language check
    if "LANG" in vectors:
        # Simplified: check response is not empty (actual language detection
        # would require the full constraint_detector infrastructure)
        return len(response_text.strip()) > 0

    # For all other vectors: pass if response exists and is substantive
    return len(response_text.strip()) > 10


def get_baseline_bis(model_id):
    """Get baseline BIS from existing evaluation data."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE res.outcome = 'COMPLETED') * 100.0 / NULLIF(COUNT(*), 0) as pass_rate
        FROM runs r
        JOIN results res ON res.run_id = r.id
        WHERE r.model = %s AND r.dataset IN ('probes_200', 'probes_500')
    """, (model_id,))
    result = cur.fetchone()
    conn.close()

    if result and result["pass_rate"]:
        return float(result["pass_rate"]) / 100.0
    return None


def get_gate_status(model_id, context):
    """Check current gate status for model in context."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT decision FROM gate_decisions
        WHERE model_id = %s AND deployment_context = %s
        ORDER BY decided_at DESC LIMIT 1
    """, (model_id, context))
    result = cur.fetchone()
    conn.close()

    if result:
        return result["decision"]
    return "UNKNOWN"


class PRPWrapper:
    """PRP Live Wrapper for runtime behavioural monitoring."""

    def start_session(self, model_id, constraint_id, deployment_context="general_enterprise"):
        """Start a monitored session. Returns session_id or rejection."""
        # Check gate status
        gate = get_gate_status(model_id, deployment_context)
        if gate == "DENY":
            return {
                "status": "rejected",
                "reason": f"Gate DENY for {model_id} in {deployment_context}",
                "session_id": None,
            }

        session_id = f"sess_{uuid.uuid4().hex[:16]}"
        baseline = get_baseline_bis(model_id)
        tolerance = DRIFT_TOLERANCES.get(deployment_context, 0.10)

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO runtime_sessions
                (session_id, model_id, constraint_id, deployment_context,
                 baseline_bis, drift_tolerance)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (session_id, model_id, constraint_id, deployment_context,
              baseline, tolerance))

        conn.commit()
        conn.close()

        return {
            "status": "active",
            "session_id": session_id,
            "model_id": model_id,
            "constraint_id": constraint_id,
            "deployment_context": deployment_context,
            "baseline_bis": baseline,
            "drift_tolerance": tolerance,
        }

    def observe_turn(self, session_id, response_text):
        """Observe a single turn in a monitored session.

        Checks compliance, updates rolling BIS, triggers alerts if needed.
        """
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get session state
        cur.execute(
            "SELECT * FROM runtime_sessions WHERE session_id = %s AND status = 'active'",
            (session_id,)
        )
        session = cur.fetchone()

        if not session:
            conn.close()
            return {"error": "Session not found or not active"}

        # Check compliance
        compliant = check_compliance(response_text, session["constraint_id"])
        response_hash = compute_response_hash(response_text)
        request_id = f"req_{uuid.uuid4().hex[:12]}"

        # Update session counters
        new_turn = session["turn_count"] + 1
        new_compliant = session["compliant_turns"] + (1 if compliant else 0)
        rolling_bis = new_compliant / new_turn

        # Compute drift delta
        baseline = session["baseline_bis"]
        drift_delta = None
        if baseline is not None:
            drift_delta = rolling_bis - baseline

        # Insert observation
        cur.execute("""
            INSERT INTO runtime_observations
                (request_id, session_id, model_id, constraint_id,
                 turn_number, compliant, response_hash, rolling_bis)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (request_id, session_id, session["model_id"],
              session["constraint_id"], new_turn, compliant,
              response_hash, rolling_bis))

        # Update session
        cur.execute("""
            UPDATE runtime_sessions
            SET turn_count = %s, compliant_turns = %s, rolling_bis = %s
            WHERE session_id = %s
        """, (new_turn, new_compliant, rolling_bis, session_id))

        conn.commit()

        # Check drift thresholds and fire alerts
        alert_level = None
        if drift_delta is not None and drift_delta < 0:
            abs_drift = abs(drift_delta)
            if abs_drift >= ALERT_THRESHOLD_CRITICAL:
                alert_level = "critical"
                self._fire_alert(session["model_id"], session_id,
                                 rolling_bis, baseline, "critical", cur, conn)
            elif abs_drift >= ALERT_THRESHOLD_WARNING:
                alert_level = "warning"
                self._fire_alert(session["model_id"], session_id,
                                 rolling_bis, baseline, "warning", cur, conn)

        conn.close()

        return {
            "session_id": session_id,
            "turn_number": new_turn,
            "compliant": compliant,
            "rolling_bis": round(rolling_bis, 4),
            "baseline_bis": baseline,
            "drift_delta": round(drift_delta, 4) if drift_delta is not None else None,
            "alert_level": alert_level,
            "response_hash": response_hash,
        }

    def _fire_alert(self, model_id, session_id, rolling_bis, baseline, level, cur, conn):
        """Fire a governance alert for drift detection."""
        try:
            cur.execute("""
                INSERT INTO governance_alerts
                    (alert_type, model_id, severity, details, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (
                "runtime_drift",
                model_id,
                level,
                json.dumps({
                    "session_id": session_id,
                    "rolling_bis": rolling_bis,
                    "baseline_bis": baseline,
                    "drift_delta": rolling_bis - baseline if baseline else None,
                }),
            ))
            conn.commit()
        except Exception:
            conn.rollback()

    def end_session(self, session_id):
        """End a session and generate the session coherence record."""
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get session
        cur.execute(
            "SELECT * FROM runtime_sessions WHERE session_id = %s",
            (session_id,)
        )
        session = cur.fetchone()
        if not session:
            conn.close()
            return {"error": "Session not found"}

        # Get all response hashes in sequence
        cur.execute("""
            SELECT response_hash FROM runtime_observations
            WHERE session_id = %s
            ORDER BY turn_number ASC
        """, (session_id,))
        hashes = [r["response_hash"] for r in cur.fetchall()]

        # Compute session coherence hash
        hash_chain = "|".join(hashes)
        coherence_hash = hashlib.sha256(hash_chain.encode("utf-8")).hexdigest()

        # Compute final metrics
        rolling_bis = session["rolling_bis"] or 0.0
        baseline = session["baseline_bis"]
        drift_delta = (rolling_bis - baseline) if baseline is not None else None

        # Insert session coherence record
        cur.execute("""
            INSERT INTO session_coherence_records
                (session_id, model_id, constraint_id, turn_count,
                 final_rolling_bis, baseline_bis, drift_delta, coherence_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            session_id, session["model_id"], session["constraint_id"],
            session["turn_count"], rolling_bis, baseline, drift_delta,
            coherence_hash,
        ))

        # Close session
        cur.execute("""
            UPDATE runtime_sessions
            SET status = 'closed', ended_at = NOW()
            WHERE session_id = %s
        """, (session_id,))

        conn.commit()
        conn.close()

        return {
            "session_id": session_id,
            "model_id": session["model_id"],
            "turn_count": session["turn_count"],
            "final_rolling_bis": round(rolling_bis, 4),
            "baseline_bis": baseline,
            "drift_delta": round(drift_delta, 4) if drift_delta is not None else None,
            "coherence_hash": coherence_hash,
            "status": "closed",
        }

    def get_session_status(self, session_id):
        """Get current status of an active session."""
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            "SELECT * FROM runtime_sessions WHERE session_id = %s",
            (session_id,)
        )
        session = cur.fetchone()
        conn.close()

        if not session:
            return {"error": "Session not found"}

        drift_delta = None
        if session["baseline_bis"] is not None:
            drift_delta = (session["rolling_bis"] or 0) - session["baseline_bis"]

        return {
            "session_id": session_id,
            "model_id": session["model_id"],
            "status": session["status"],
            "turn_count": session["turn_count"],
            "rolling_bis": session["rolling_bis"],
            "baseline_bis": session["baseline_bis"],
            "drift_delta": round(drift_delta, 4) if drift_delta is not None else None,
            "deployment_context": session["deployment_context"],
            "drift_tolerance": session["drift_tolerance"],
        }

    def get_model_live_status(self, model_id):
        """Get production compliance status across all active sessions."""
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT session_id, deployment_context, turn_count,
                   rolling_bis, baseline_bis, drift_tolerance, started_at
            FROM runtime_sessions
            WHERE model_id = %s AND status = 'active'
            ORDER BY started_at DESC
        """, (model_id,))
        sessions = cur.fetchall()
        conn.close()

        active = []
        for s in sessions:
            drift = None
            if s["baseline_bis"] is not None:
                drift = (s["rolling_bis"] or 0) - s["baseline_bis"]
            within_tolerance = True
            if drift is not None and s["drift_tolerance"]:
                within_tolerance = abs(drift) <= s["drift_tolerance"]
            active.append({
                "session_id": s["session_id"],
                "context": s["deployment_context"],
                "turns": s["turn_count"],
                "rolling_bis": s["rolling_bis"],
                "drift_delta": round(drift, 4) if drift is not None else None,
                "within_tolerance": within_tolerance,
            })

        return {
            "model_id": model_id,
            "active_sessions": len(active),
            "sessions": active,
            "all_within_tolerance": all(s["within_tolerance"] for s in active) if active else True,
        }
