#!/usr/bin/env python3
"""
Governance Alert Runner — Monitors all governance metrics and fires alerts
when thresholds are crossed.

Usage:
    python alert_runner.py --check-all
    python alert_runner.py --check tds
    python alert_runner.py --check csas
    python alert_runner.py --check jrs
    python alert_runner.py --check gate
    python alert_runner.py --check bec
    python alert_runner.py --check-all --dry-run

Alert types:
    tds_critical       Any model with drift_class = 'critical'
    csas_degradation   Any CSAS score < 0.97
    jrs_expired        Any JRS registry entry past expires_at
    gate_expired       Any gate decision past expires_at with no newer decision
    bec_integrity      Any BEC chain with integrity_score < 1.0
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass

import psycopg2
from psycopg2.extras import RealDictCursor

BASE_DIR = Path(__file__).parent


# ============================================================================
# Database helpers
# ============================================================================

def get_db():
    """Get database connection."""
    conn = psycopg2.connect(os.environ.get("DATABASE_URL", ""))
    conn.cursor_factory = RealDictCursor
    return conn


def alert_exists(cur, alert_type, model_id):
    """Check if an unresolved alert already exists for this type+model."""
    cur.execute("""
        SELECT id FROM governance_alerts
        WHERE alert_type = %s AND model_id = %s AND resolved = FALSE
        LIMIT 1
    """, (alert_type, model_id))
    return cur.fetchone() is not None


def create_alert(cur, alert_type, model_id, provider, threshold_crossed,
                 current_value, threshold_value, severity, details=None):
    """Insert a new governance alert."""
    cur.execute("""
        INSERT INTO governance_alerts
            (alert_type, model_id, provider, threshold_crossed, current_value,
             threshold_value, severity, details)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (alert_type, model_id, provider, threshold_crossed,
          current_value, threshold_value, severity,
          json.dumps(details) if details else None))
    return cur.fetchone()['id']


# ============================================================================
# Check: TDS Critical Drift
# ============================================================================

def check_tds(cur, dry_run=False):
    """Check for any models with critical drift in tds_comparisons."""
    print("── TDS Critical Drift Check ──")
    cur.execute("""
        SELECT model, provider, tds, drift_class, current_bis, evaluated_at
        FROM tds_comparisons
        WHERE drift_class = 'critical'
        ORDER BY evaluated_at DESC
    """)
    rows = cur.fetchall()

    new_alerts = []
    for row in rows:
        model_id = row['model']
        if alert_exists(cur, 'tds_critical', model_id):
            continue

        details = {
            'tds': row['tds'],
            'current_bis': row['current_bis'],
            'evaluated_at': str(row['evaluated_at']),
        }
        severity = 'critical'
        threshold_crossed = f"drift_class=critical (TDS={row['tds']:+.1f}pp)"

        if dry_run:
            print(f"  [DRY-RUN] Would alert: {model_id} ({row['provider']}) — {threshold_crossed}")
        else:
            alert_id = create_alert(
                cur, 'tds_critical', model_id, row['provider'],
                threshold_crossed, row['tds'], 10.0, severity, details
            )
            print(f"  [ALERT] Created alert #{alert_id}: {model_id} — {threshold_crossed}")
        new_alerts.append({'model': model_id, 'type': 'tds_critical', 'detail': threshold_crossed})

    if not rows:
        print("  [OK] No critical drift detected.")
    elif not new_alerts:
        print("  [OK] All critical drifts already have active alerts.")
    return new_alerts


# ============================================================================
# Check: CSAS Degradation
# ============================================================================

def check_csas(cur, dry_run=False):
    """Check for any CSAS scores below 0.97."""
    print("── CSAS Degradation Check ──")
    cur.execute("""
        SELECT s.csas, s.grade, s.created_at,
               b.upstream_model, b.downstream_model
        FROM csas_scores s
        JOIN csas_boundaries b ON s.boundary_id = b.id
        WHERE s.csas < 0.97
        ORDER BY s.created_at DESC
    """)
    rows = cur.fetchall()

    new_alerts = []
    for row in rows:
        model_id = f"{row['upstream_model']}/{row['downstream_model']}"
        if alert_exists(cur, 'csas_degradation', model_id):
            continue

        details = {
            'csas': row['csas'],
            'grade': row['grade'],
            'upstream_model': row['upstream_model'],
            'downstream_model': row['downstream_model'],
            'evaluated_at': str(row['created_at']),
        }
        severity = 'critical' if row['csas'] < 0.90 else 'warning'
        threshold_crossed = f"CSAS={row['csas']:.4f} (threshold=0.97)"

        if dry_run:
            print(f"  [DRY-RUN] Would alert: {model_id} — {threshold_crossed}")
        else:
            alert_id = create_alert(
                cur, 'csas_degradation', model_id, None,
                threshold_crossed, row['csas'], 0.97, severity, details
            )
            print(f"  [ALERT] Created alert #{alert_id}: {model_id} — {threshold_crossed}")
        new_alerts.append({'model': model_id, 'type': 'csas_degradation', 'detail': threshold_crossed})

    if not rows:
        print("  [OK] All CSAS scores >= 0.97.")
    elif not new_alerts:
        print("  [OK] All CSAS degradations already have active alerts.")
    return new_alerts


# ============================================================================
# Check: JRS Expired
# ============================================================================

def check_jrs(cur, dry_run=False):
    """Check for any JRS registry entries past their expiry."""
    print("── JRS Expired Check ──")
    cur.execute("""
        SELECT id, boundary_name, upstream_model, downstream_model,
               governing_system, expires_at
        FROM jrs_registry
        WHERE expires_at < NOW() AND expires_at IS NOT NULL
        ORDER BY expires_at DESC
    """)
    rows = cur.fetchall()

    new_alerts = []
    for row in rows:
        model_id = f"{row['upstream_model']}/{row['downstream_model']}"
        if alert_exists(cur, 'jrs_expired', model_id):
            continue

        details = {
            'boundary_name': row['boundary_name'],
            'upstream_model': row['upstream_model'],
            'downstream_model': row['downstream_model'],
            'governing_system': row['governing_system'],
            'expires_at': str(row['expires_at']),
        }
        severity = 'warning'
        threshold_crossed = f"JRS registry expired at {row['expires_at']}"

        if dry_run:
            print(f"  [DRY-RUN] Would alert: {model_id} — {threshold_crossed}")
        else:
            alert_id = create_alert(
                cur, 'jrs_expired', model_id, None,
                threshold_crossed, None, None, severity, details
            )
            print(f"  [ALERT] Created alert #{alert_id}: {model_id} — {threshold_crossed}")
        new_alerts.append({'model': model_id, 'type': 'jrs_expired', 'detail': threshold_crossed})

    if not rows:
        print("  [OK] No expired JRS registry entries.")
    elif not new_alerts:
        print("  [OK] All JRS expirations already have active alerts.")
    return new_alerts


# ============================================================================
# Check: Gate Expired
# ============================================================================

def check_gate(cur, dry_run=False):
    """Check for gate decisions past expiry with no newer decision."""
    print("── Gate Expired Check ──")
    cur.execute("""
        SELECT gd.id, gd.model_id, gd.provider, gd.deployment_context,
               gd.decision, gd.expires_at
        FROM gate_decisions gd
        WHERE gd.expires_at < NOW()
          AND gd.expires_at IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM gate_decisions gd2
              WHERE gd2.model_id = gd.model_id
                AND gd2.provider = gd.provider
                AND gd2.deployment_context = gd.deployment_context
                AND gd2.decided_at > gd.decided_at
          )
        ORDER BY gd.expires_at ASC
    """)
    rows = cur.fetchall()

    new_alerts = []
    for row in rows:
        model_id = row['model_id']
        alert_model_key = f"{model_id}/{row['deployment_context']}"
        if alert_exists(cur, 'gate_expired', alert_model_key):
            continue

        details = {
            'decision_id': row['id'],
            'deployment_context': row['deployment_context'],
            'decision': row['decision'],
            'expires_at': str(row['expires_at']),
        }
        severity = 'warning'
        threshold_crossed = f"Gate decision expired at {row['expires_at']} ({row['deployment_context']})"

        if dry_run:
            print(f"  [DRY-RUN] Would alert: {alert_model_key} — {threshold_crossed}")
        else:
            alert_id = create_alert(
                cur, 'gate_expired', alert_model_key, row['provider'],
                threshold_crossed, None, None, severity, details
            )
            print(f"  [ALERT] Created alert #{alert_id}: {alert_model_key} — {threshold_crossed}")
        new_alerts.append({'model': alert_model_key, 'type': 'gate_expired', 'detail': threshold_crossed})

    if not rows:
        print("  [OK] No expired gate decisions without renewal.")
    elif not new_alerts:
        print("  [OK] All gate expirations already have active alerts.")
    return new_alerts


# ============================================================================
# Check: BEC Integrity
# ============================================================================

def check_bec(cur, dry_run=False):
    """Check for any BEC chains with integrity_score < 1.0."""
    print("── BEC Integrity Check ──")
    cur.execute("""
        SELECT chain_id, integrity_score, current_length, last_verified
        FROM bec_chains
        WHERE integrity_score < 1.0
        ORDER BY integrity_score ASC
    """)
    rows = cur.fetchall()

    new_alerts = []
    for row in rows:
        model_id = f"bec:{row['chain_id']}"
        if alert_exists(cur, 'bec_integrity', model_id):
            continue

        details = {
            'chain_id': row['chain_id'],
            'integrity_score': row['integrity_score'],
            'current_length': row['current_length'],
            'last_verified': str(row['last_verified']),
        }
        severity = 'critical' if row['integrity_score'] < 0.95 else 'warning'
        threshold_crossed = f"BEC integrity={row['integrity_score']:.4f} (threshold=1.0)"

        if dry_run:
            print(f"  [DRY-RUN] Would alert: {model_id} — {threshold_crossed}")
        else:
            alert_id = create_alert(
                cur, 'bec_integrity', model_id, None,
                threshold_crossed, row['integrity_score'], 1.0, severity, details
            )
            print(f"  [ALERT] Created alert #{alert_id}: {model_id} — {threshold_crossed}")
        new_alerts.append({'model': model_id, 'type': 'bec_integrity', 'detail': threshold_crossed})

    if not rows:
        print("  [OK] All BEC chains have perfect integrity.")
    elif not new_alerts:
        print("  [OK] All BEC integrity issues already have active alerts.")
    return new_alerts


# ============================================================================
# Runner
# ============================================================================

CHECK_MAP = {
    'tds': check_tds,
    'csas': check_csas,
    'jrs': check_jrs,
    'gate': check_gate,
    'bec': check_bec,
}


def run_checks(checks, dry_run=False):
    """Run specified checks and return all new alerts."""
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()

        all_alerts = []
        for check_name in checks:
            check_fn = CHECK_MAP[check_name]
            alerts = check_fn(cur, dry_run=dry_run)
            all_alerts.extend(alerts)
            print()

        if not dry_run:
            conn.commit()

        return all_alerts
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[ERROR] {e}")
        raise
    finally:
        if conn:
            conn.close()


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Governance Alert Runner — Threshold Monitoring")
    parser.add_argument('--check-all', action='store_true', help='Run all governance checks')
    parser.add_argument('--check', type=str, choices=['tds', 'csas', 'jrs', 'gate', 'bec'],
                        help='Run a specific check')
    parser.add_argument('--dry-run', action='store_true', help='Report without creating alerts')

    args = parser.parse_args()

    if not args.check_all and not args.check:
        parser.error("Either --check-all or --check <type> is required")

    print("=" * 60)
    print("Governance Alert Runner")
    print(f"Started: {datetime.now().isoformat()}")
    if args.dry_run:
        print("Mode: DRY-RUN (no alerts will be created)")
    print("=" * 60)
    print()

    if args.check_all:
        checks = list(CHECK_MAP.keys())
    else:
        checks = [args.check]

    all_alerts = run_checks(checks, dry_run=args.dry_run)

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    if all_alerts:
        print(f"  New alerts: {len(all_alerts)}")
        for alert in all_alerts:
            print(f"    [{alert['type']}] {alert['model']} — {alert['detail']}")
    else:
        print("  No new alerts generated. All thresholds within limits.")

    print()
    print(f"Finished: {datetime.now().isoformat()}")


if __name__ == '__main__':
    main()
