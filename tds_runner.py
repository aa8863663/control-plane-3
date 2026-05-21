#!/usr/bin/env python3
"""
TDS Runner — Temporal Drift Score Evaluation
Detects silent performance degradation from model updates or provider changes.

Usage:
    python tds_runner.py --model gpt-4o --provider openai
    python tds_runner.py --model gpt-4o --provider openai --create-baseline
    python tds_runner.py --all
    python tds_runner.py --model gpt-4o --provider openai --dry-run

Drift classification:
    stable      < 2pp change
    marginal    2-5pp change
    significant 5-10pp change
    critical    > 10pp change
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
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
# Grading scale (MTCP standard)
# ============================================================================

def bis_grade(pct):
    """Assign MTCP letter grade to a BIS percentage."""
    if pct >= 90:
        return 'A'
    elif pct >= 80:
        return 'B'
    elif pct >= 70:
        return 'C'
    elif pct >= 60:
        return 'D'
    else:
        return 'F'


# ============================================================================
# Drift classification
# ============================================================================

def classify_drift(tds_value):
    """
    Classify drift based on absolute percentage point change.
    Uses absolute value so degradation and improvement are symmetrical.
    """
    abs_tds = abs(tds_value)
    if abs_tds < 2:
        return 'stable'
    elif abs_tds < 5:
        return 'marginal'
    elif abs_tds < 10:
        return 'significant'
    else:
        return 'critical'


def alert_level_for_drift(drift_class):
    """Map drift class to alert level."""
    mapping = {
        'stable': None,
        'marginal': 'info',
        'significant': 'warning',
        'critical': 'critical',
    }
    return mapping.get(drift_class)


# ============================================================================
# Database helpers
# ============================================================================

def get_db():
    """Get database connection."""
    conn = psycopg2.connect(os.environ.get("DATABASE_URL", ""))
    conn.cursor_factory = RealDictCursor
    return conn


def get_latest_baseline(cur, model, provider):
    """Get the most recent valid baseline for a model/provider."""
    cur.execute("""
        SELECT * FROM tds_baselines
        WHERE model = %s AND provider = %s
          AND (valid_until IS NULL OR valid_until > NOW())
        ORDER BY evaluated_at DESC
        LIMIT 1
    """, (model, provider))
    return cur.fetchone()


def get_current_bis(cur, model, provider):
    """
    Compute current BIS from the most recent probes_500 results.
    Returns (bis, run_ids) or (None, None) if no results found.
    """
    cur.execute("""
        SELECT ru.id as run_id,
               COUNT(*) as total,
               SUM(CASE WHEN r.outcome = 'COMPLETED' THEN 1 ELSE 0 END) as passed
        FROM runs ru
        JOIN results r ON ru.id = r.run_id
        WHERE ru.model = %s
          AND ru.dataset = 'probes_500'
          AND COALESCE(ru.provider, ru.api_provider, '') ILIKE %s
        GROUP BY ru.id
        ORDER BY ru.created_at DESC
        LIMIT 5
    """, (model, f'%{provider}%'))
    rows = cur.fetchall()
    if not rows:
        # Try without provider filter as fallback
        cur.execute("""
            SELECT ru.id as run_id,
                   COUNT(*) as total,
                   SUM(CASE WHEN r.outcome = 'COMPLETED' THEN 1 ELSE 0 END) as passed
            FROM runs ru
            JOIN results r ON ru.id = r.run_id
            WHERE ru.model = %s
              AND ru.dataset = 'probes_500'
            GROUP BY ru.id
            ORDER BY ru.created_at DESC
            LIMIT 5
        """, (model,))
        rows = cur.fetchall()

    if not rows:
        return None, None

    total_passed = sum(r['passed'] for r in rows)
    total_count = sum(r['total'] for r in rows)
    bis = round(100.0 * total_passed / total_count, 1) if total_count > 0 else 0
    run_ids = [str(r['run_id']) for r in rows]
    return bis, run_ids


# ============================================================================
# Core TDS logic
# ============================================================================

def compute_tds(current_bis, baseline_bis):
    """Compute Temporal Drift Score (percentage point change)."""
    return round(current_bis - baseline_bis, 2)


def compute_drift_velocity(tds_value, days_elapsed):
    """Compute drift velocity (TDS per day)."""
    if days_elapsed and days_elapsed > 0:
        return round(tds_value / days_elapsed, 4)
    return None


def create_baseline(cur, model, provider, bis, grade, run_ids=None, valid_days=90):
    """Create a new TDS baseline entry."""
    valid_until = datetime.now() + timedelta(days=valid_days)
    cur.execute("""
        INSERT INTO tds_baselines (model, provider, dataset, bis, grade, evaluated_at, valid_until, run_ids)
        VALUES (%s, %s, 'probes_500', %s, %s, NOW(), %s, %s)
        RETURNING id
    """, (model, provider, bis, grade, valid_until, run_ids))
    return cur.fetchone()['id']


def store_comparison(cur, baseline_id, model, provider, current_bis, current_grade, tds_value, drift_velocity, drift_class, days_elapsed):
    """Store a TDS comparison result."""
    cur.execute("""
        INSERT INTO tds_comparisons
            (baseline_id, model, provider, current_bis, current_grade, tds, drift_velocity, drift_class, days_elapsed, evaluated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
    """, (baseline_id, model, provider, current_bis, current_grade, tds_value, drift_velocity, drift_class, days_elapsed))
    return cur.fetchone()['id']


def store_alert(cur, comparison_id, model, alert_level, drift_class, tds_value, message):
    """Store a TDS alert."""
    cur.execute("""
        INSERT INTO tds_alerts (comparison_id, model, alert_level, drift_class, tds, message)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (comparison_id, model, alert_level, drift_class, tds_value, message))
    return cur.fetchone()['id']


# ============================================================================
# Runner entry points
# ============================================================================

def run_tds_check(model, provider, dry_run=False, no_db=False, create_baseline_flag=False):
    """
    Run TDS check for a single model/provider.
    Returns a result dict with drift details.
    """
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()

        # Get current BIS
        current_bis, run_ids = get_current_bis(cur, model, provider)
        if current_bis is None:
            print(f"  [SKIP] No probes_500 results found for {model} ({provider})")
            return None

        current_grade = bis_grade(current_bis)
        print(f"  Current BIS: {current_bis}% (Grade {current_grade})")

        # If creating a baseline, do that and exit
        if create_baseline_flag:
            if dry_run or no_db:
                print(f"  [DRY-RUN] Would create baseline: BIS={current_bis}%, Grade={current_grade}")
                return {
                    'model': model, 'provider': provider,
                    'action': 'create_baseline',
                    'bis': current_bis, 'grade': current_grade,
                }
            baseline_id = create_baseline(cur, model, provider, current_bis, current_grade, run_ids)
            conn.commit()
            print(f"  [OK] Baseline created (id={baseline_id}): BIS={current_bis}%, Grade={current_grade}")
            return {
                'model': model, 'provider': provider,
                'action': 'create_baseline',
                'baseline_id': baseline_id,
                'bis': current_bis, 'grade': current_grade,
            }

        # Get baseline for comparison
        baseline = get_latest_baseline(cur, model, provider)
        if not baseline:
            print(f"  [SKIP] No baseline found for {model} ({provider}). Use --create-baseline to create one.")
            return None

        baseline_bis = baseline['bis']
        baseline_grade = baseline['grade']
        baseline_date = baseline['evaluated_at']

        # Compute drift
        tds_value = compute_tds(current_bis, baseline_bis)
        days_elapsed = (datetime.now() - baseline_date).days if baseline_date else None
        drift_velocity = compute_drift_velocity(tds_value, days_elapsed)
        drift_class = classify_drift(tds_value)

        print(f"  Baseline BIS: {baseline_bis}% (Grade {baseline_grade}, {days_elapsed} days ago)")
        print(f"  TDS: {tds_value:+.1f}pp | Velocity: {drift_velocity or 'N/A'}/day | Class: {drift_class.upper()}")

        result = {
            'model': model,
            'provider': provider,
            'baseline_bis': baseline_bis,
            'baseline_grade': baseline_grade,
            'current_bis': current_bis,
            'current_grade': current_grade,
            'tds': tds_value,
            'drift_velocity': drift_velocity,
            'drift_class': drift_class,
            'days_elapsed': days_elapsed,
        }

        if dry_run or no_db:
            print(f"  [DRY-RUN] Would store comparison. Drift class: {drift_class}")
            return result

        # Store comparison
        comparison_id = store_comparison(
            cur, baseline['id'], model, provider,
            current_bis, current_grade, tds_value,
            drift_velocity, drift_class, days_elapsed
        )

        # Create alert if significant or critical
        alert_level = alert_level_for_drift(drift_class)
        if alert_level in ('warning', 'critical'):
            direction = "degraded" if tds_value < 0 else "improved"
            message = (
                f"{model} ({provider}) has {direction} by {abs(tds_value):.1f}pp "
                f"over {days_elapsed} days. "
                f"Grade: {baseline_grade} -> {current_grade}. "
                f"Drift class: {drift_class}."
            )
            alert_id = store_alert(cur, comparison_id, model, alert_level, drift_class, tds_value, message)
            print(f"  [ALERT] {alert_level.upper()}: {message} (alert_id={alert_id})")
            result['alert_id'] = alert_id
            result['alert_level'] = alert_level

        conn.commit()
        print(f"  [OK] Comparison stored (id={comparison_id})")
        result['comparison_id'] = comparison_id
        return result

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"  [ERROR] {e}")
        raise
    finally:
        if conn:
            conn.close()


def run_all_models(dry_run=False, no_db=False):
    """Run TDS check for all models that have baselines."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT model, provider FROM tds_baselines
        WHERE valid_until IS NULL OR valid_until > NOW()
        ORDER BY model, provider
    """)
    models = cur.fetchall()
    conn.close()

    if not models:
        print("[INFO] No active baselines found. Use --create-baseline to create baselines first.")
        return []

    print(f"[INFO] Checking {len(models)} model/provider combinations...\n")
    results = []
    for row in models:
        model, provider = row['model'], row['provider']
        print(f"── {model} ({provider}) ──")
        result = run_tds_check(model, provider, dry_run=dry_run, no_db=no_db)
        if result:
            results.append(result)
        print()

    # Summary
    if results:
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        for r in results:
            if 'tds' in r:
                flag = ""
                if r['drift_class'] == 'critical':
                    flag = " *** CRITICAL ***"
                elif r['drift_class'] == 'significant':
                    flag = " ** WARNING **"
                print(f"  {r['model']:40s} TDS={r['tds']:+.1f}pp  [{r['drift_class'].upper()}]{flag}")

    return results


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="TDS Runner — Temporal Drift Score Evaluation")
    parser.add_argument('--model', type=str, help='Model name to check')
    parser.add_argument('--provider', type=str, help='Provider name')
    parser.add_argument('--all', action='store_true', help='Check all models with active baselines')
    parser.add_argument('--create-baseline', action='store_true', help='Create a new baseline from current BIS')
    parser.add_argument('--dry-run', action='store_true', help='Show what would happen without writing to DB')
    parser.add_argument('--no-db', action='store_true', help='Run without database writes')

    args = parser.parse_args()

    if not args.all and not args.model:
        parser.error("Either --model or --all is required")

    if args.model and not args.provider:
        parser.error("--provider is required when using --model")

    print("=" * 60)
    print("TDS Runner — Temporal Drift Score")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)
    print()

    if args.all:
        results = run_all_models(dry_run=args.dry_run, no_db=args.no_db)
    else:
        print(f"── {args.model} ({args.provider}) ──")
        result = run_tds_check(
            args.model, args.provider,
            dry_run=args.dry_run,
            no_db=args.no_db,
            create_baseline_flag=args.create_baseline,
        )
        results = [result] if result else []

    print()
    print(f"Finished: {datetime.now().isoformat()}")
    if not results:
        print("No results produced.")
        sys.exit(1)

    # Exit with error code if any critical drift detected
    critical = [r for r in results if r.get('drift_class') == 'critical']
    if critical:
        print(f"\n[!] {len(critical)} model(s) have CRITICAL drift!")
        sys.exit(2)


if __name__ == '__main__':
    main()
