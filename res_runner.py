#!/usr/bin/env python3
"""
RES Runner — Remediation Effectiveness Score Evaluation
Measures whether specific interventions fix constraint persistence failures.
Compares BIS before and after an intervention.

Usage:
    python res_runner.py --model openai/gpt-4o --intervention-type temperature_reduction --description "Reduce temperature from 0.8 to 0.0" --baseline-bis 72.5
    python res_runner.py --model groq/llama-3.3-70b-versatile --intervention-type prompt_engineering --description "Add explicit constraint repetition" --baseline-bis 65.0
    python res_runner.py --compute-from-db
    python res_runner.py --model openai/gpt-4o --intervention-type temperature_reduction --dry-run

RES Formula:
    RES = (post_bis - baseline_bis) / (100 - baseline_bis)
    Absolute improvement = post_bis - baseline_bis (percentage points)

Intervention types:
    prompt_engineering       — restructure prompts for clarity
    system_prompt           — modify system prompt directives
    temperature_reduction   — lower temperature for determinism
    instruction_reordering  — change order of constraints
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
DEFAULT_PROBES = BASE_DIR / "probes_200.json"

VALID_INTERVENTION_TYPES = [
    'prompt_engineering',
    'system_prompt',
    'temperature_reduction',
    'instruction_reordering',
]


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
# RES computation
# ============================================================================

def compute_res(post_bis, baseline_bis):
    """
    Compute Remediation Effectiveness Score.
    RES = (post_bis - baseline_bis) / (100 - baseline_bis)
    Capped at [-1.0, 1.0] for edge cases.
    """
    denominator = 100.0 - baseline_bis
    if denominator <= 0:
        # Already at 100%, no room for improvement
        return 0.0
    res = (post_bis - baseline_bis) / denominator
    return round(max(-1.0, min(1.0, res)), 4)


def compute_absolute_improvement(post_bis, baseline_bis):
    """Compute absolute improvement in percentage points."""
    return round(post_bis - baseline_bis, 2)


# ============================================================================
# Database helpers
# ============================================================================

def get_db():
    """Get database connection."""
    conn = psycopg2.connect(os.environ.get("DATABASE_URL", ""))
    conn.cursor_factory = RealDictCursor
    return conn


def fetch_baseline_bis(cur, model, provider):
    """
    Auto-fetch baseline BIS from tds_baselines or compute from runs.
    Returns BIS value or None.
    """
    # Try tds_baselines first
    cur.execute("""
        SELECT bis FROM tds_baselines
        WHERE model = %s AND provider = %s
        ORDER BY evaluated_at DESC
        LIMIT 1
    """, (model, provider))
    row = cur.fetchone()
    if row:
        return row['bis']

    # Fallback: compute from probes_500 runs
    cur.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN r.outcome = 'COMPLETED' THEN 1 ELSE 0 END) as passed
        FROM runs ru
        JOIN results r ON ru.id = r.run_id
        WHERE ru.model = %s AND ru.dataset = 'probes_500'
          AND COALESCE(ru.provider, ru.api_provider, '') ILIKE %s
    """, (model, f'%{provider}%'))
    row = cur.fetchone()
    if row and row['total'] and row['total'] > 0:
        return round(100.0 * row['passed'] / row['total'], 1)

    return None


def store_intervention(cur, model, provider, intervention_type, description, baseline_bis, baseline_grade):
    """Store intervention record."""
    cur.execute("""
        INSERT INTO res_interventions (model, provider, intervention_type, description, baseline_bis, baseline_grade)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (model, provider, intervention_type, description, baseline_bis, baseline_grade))
    return cur.fetchone()['id']


def store_result(cur, intervention_id, post_bis, post_grade, res_score, absolute_improvement, temperature=None, probe_count=None, dataset='probes_200'):
    """Store evaluation result."""
    cur.execute("""
        INSERT INTO res_results (intervention_id, post_bis, post_grade, res_score, absolute_improvement, temperature, probe_count, dataset)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (intervention_id, post_bis, post_grade, res_score, absolute_improvement, temperature, probe_count, dataset))
    return cur.fetchone()['id']


def store_ceiling(cur, model, provider, ceiling_bis, ceiling_grade, best_intervention=None, failure_pattern=None):
    """Store ceiling record."""
    cur.execute("""
        INSERT INTO res_ceilings (model, provider, ceiling_bis, ceiling_grade, best_intervention, failure_pattern)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (model, provider, ceiling_bis, ceiling_grade, best_intervention, failure_pattern))
    return cur.fetchone()['id']


# ============================================================================
# Compute RES from existing DB data
# ============================================================================

def compute_res_from_db(dry_run=False, no_db=False):
    """
    Compute RES for temperature_reduction using existing evaluations.
    Finds models with probes_500 data at both T=0.0 and T=0.8,
    then computes RES = (post_bis - baseline_bis) / (100 - baseline_bis).
    """
    conn = get_db()
    cur = conn.cursor()

    print("[INFO] Querying DB for models with probes_500 data at T=0.0 and T=0.8...")

    # Find models with evaluations at both temperatures
    cur.execute("""
        WITH temp_scores AS (
            SELECT
                ru.model,
                COALESCE(NULLIF(ru.provider, ''), NULLIF(ru.api_provider, ''), 'unknown') as provider,
                ru.temperature,
                COUNT(*) as total,
                SUM(CASE WHEN r.outcome = 'COMPLETED' THEN 1 ELSE 0 END) as passed
            FROM runs ru
            JOIN results r ON ru.id = r.run_id
            WHERE ru.dataset = 'probes_500'
              AND ru.temperature IN (0.0::real, 0.8::real)
            GROUP BY ru.model, COALESCE(NULLIF(ru.provider, ''), NULLIF(ru.api_provider, ''), 'unknown'), ru.temperature
            HAVING COUNT(*) >= 50
        ),
        t00 AS (
            SELECT model, provider, ROUND(100.0 * passed / total, 1) as bis, total as probe_count
            FROM temp_scores WHERE temperature = 0.0::real
        ),
        t08 AS (
            SELECT model, provider, ROUND(100.0 * passed / total, 1) as bis, total as probe_count
            FROM temp_scores WHERE temperature = 0.8::real
        )
        SELECT
            t08.model,
            t08.provider,
            t08.bis as baseline_bis,
            t00.bis as post_bis,
            t00.probe_count
        FROM t08
        JOIN t00 ON t08.model = t00.model AND t08.provider = t00.provider
        ORDER BY (t00.bis - t08.bis) DESC
    """)

    rows = cur.fetchall()

    if not rows:
        print("[WARN] No models found with both T=0.0 and T=0.8 probes_500 data.")
        conn.close()
        return []

    print(f"[INFO] Found {len(rows)} model/provider combinations with both temperatures.\n")
    print(f"{'Model':<45} {'Provider':<15} {'T=0.8 BIS':<10} {'T=0.0 BIS':<10} {'RES':<8} {'Abs Impr':<10}")
    print("─" * 100)

    results = []
    for row in rows:
        model = row['model']
        provider = row['provider']
        baseline_bis = float(row['baseline_bis'])
        post_bis = float(row['post_bis'])
        probe_count = row['probe_count']

        res_score = compute_res(post_bis, baseline_bis)
        abs_improvement = compute_absolute_improvement(post_bis, baseline_bis)
        baseline_grade = bis_grade(baseline_bis)
        post_grade = bis_grade(post_bis)

        print(f"{model:<45} {provider:<15} {baseline_bis:<10.1f} {post_bis:<10.1f} {res_score:<8.4f} {abs_improvement:+.1f}pp")

        result = {
            'model': model,
            'provider': provider,
            'baseline_bis': baseline_bis,
            'baseline_grade': baseline_grade,
            'post_bis': post_bis,
            'post_grade': post_grade,
            'res_score': res_score,
            'absolute_improvement': abs_improvement,
            'probe_count': probe_count,
        }
        results.append(result)

        if not dry_run and not no_db:
            # Store intervention
            intervention_id = store_intervention(
                cur, model, provider,
                'temperature_reduction',
                'Reduce temperature from 0.8 to 0.0',
                baseline_bis, baseline_grade
            )
            # Store result
            store_result(
                cur, intervention_id,
                post_bis, post_grade, res_score, abs_improvement,
                temperature=0.0, probe_count=probe_count, dataset='probes_500'
            )

    # Store ceilings for top 3 and bottom 3 by RES
    if results and not dry_run and not no_db:
        sorted_results = sorted(results, key=lambda x: x['res_score'], reverse=True)

        # Top 3 (most improved by temperature reduction)
        top_3 = sorted_results[:3]
        # Bottom 3 (least improved or degraded)
        bottom_3 = sorted_results[-3:]

        ceiling_models = top_3 + bottom_3
        # Deduplicate
        seen = set()
        unique_ceilings = []
        for r in ceiling_models:
            key = (r['model'], r['provider'])
            if key not in seen:
                seen.add(key)
                unique_ceilings.append(r)

        print(f"\n[INFO] Storing ceilings for {len(unique_ceilings)} models (top 3 + bottom 3 by RES)...")
        for r in unique_ceilings:
            failure_pattern = 'stochastic' if r['res_score'] > 0.3 else 'architectural'
            store_ceiling(
                cur, r['model'], r['provider'],
                r['post_bis'], r['post_grade'],
                best_intervention='temperature_reduction',
                failure_pattern=failure_pattern
            )

    if not dry_run and not no_db:
        conn.commit()
        print(f"\n[OK] Stored {len(results)} interventions + results to DB.")
    else:
        print(f"\n[DRY-RUN] Would store {len(results)} interventions + results.")

    conn.close()

    # Summary
    if results:
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        sorted_res = sorted(results, key=lambda x: x['res_score'], reverse=True)
        print(f"\n  Top 3 (most responsive to temperature reduction):")
        for r in sorted_res[:3]:
            print(f"    {r['model']:<40} RES={r['res_score']:.4f}  ({r['baseline_bis']:.1f}% -> {r['post_bis']:.1f}%)")
        print(f"\n  Bottom 3 (least responsive):")
        for r in sorted_res[-3:]:
            print(f"    {r['model']:<40} RES={r['res_score']:.4f}  ({r['baseline_bis']:.1f}% -> {r['post_bis']:.1f}%)")
        avg_res = sum(r['res_score'] for r in results) / len(results)
        print(f"\n  Mean RES: {avg_res:.4f}")
        print(f"  Models evaluated: {len(results)}")

    return results


# ============================================================================
# Single model evaluation
# ============================================================================

def run_res_evaluation(model, provider, intervention_type, description, baseline_bis=None,
                       probes=None, temperature=None, dry_run=False, no_db=False):
    """
    Run RES evaluation for a single model with a given intervention.
    For temperature_reduction, uses existing DB data rather than making API calls.
    """
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()

        # Parse model string (provider/model-name format)
        if '/' in model and not provider:
            provider, model = model.split('/', 1)

        # Get baseline BIS
        if baseline_bis is None:
            baseline_bis = fetch_baseline_bis(cur, model, provider)
            if baseline_bis is None:
                print(f"  [ERROR] No baseline BIS found for {model} ({provider}). Use --baseline-bis to specify.")
                return None
            print(f"  [AUTO] Fetched baseline BIS from DB: {baseline_bis}%")

        baseline_grade = bis_grade(baseline_bis)
        print(f"  Baseline: BIS={baseline_bis}% (Grade {baseline_grade})")
        print(f"  Intervention: {intervention_type} — {description}")

        # For temperature_reduction, compute post-intervention BIS from existing data
        if intervention_type == 'temperature_reduction':
            post_temp = temperature if temperature is not None else 0.0
            cur.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN r.outcome = 'COMPLETED' THEN 1 ELSE 0 END) as passed
                FROM runs ru
                JOIN results r ON ru.id = r.run_id
                WHERE ru.model = %s
                  AND ru.dataset = 'probes_500'
                  AND ru.temperature = %s
                  AND COALESCE(ru.provider, ru.api_provider, '') ILIKE %s
            """, (model, post_temp, f'%{provider}%'))
            row = cur.fetchone()
            if not row or not row['total'] or row['total'] == 0:
                print(f"  [ERROR] No T={post_temp} results found for {model} ({provider})")
                return None
            post_bis = round(100.0 * row['passed'] / row['total'], 1)
            probe_count = row['total']
        else:
            # For other intervention types, we would run probes here
            # But since we're computing from existing data, skip API calls
            print(f"  [INFO] Non-temperature interventions require live evaluation.")
            print(f"  [INFO] Use --compute-from-db for batch computation from existing data.")
            return None

        post_grade = bis_grade(post_bis)
        res_score = compute_res(post_bis, baseline_bis)
        abs_improvement = compute_absolute_improvement(post_bis, baseline_bis)

        print(f"  Post-intervention: BIS={post_bis}% (Grade {post_grade})")
        print(f"  RES: {res_score:.4f}")
        print(f"  Absolute improvement: {abs_improvement:+.1f}pp")

        result = {
            'model': model,
            'provider': provider,
            'intervention_type': intervention_type,
            'description': description,
            'baseline_bis': baseline_bis,
            'baseline_grade': baseline_grade,
            'post_bis': post_bis,
            'post_grade': post_grade,
            'res_score': res_score,
            'absolute_improvement': abs_improvement,
            'probe_count': probe_count,
        }

        if dry_run or no_db:
            print(f"  [DRY-RUN] Would store intervention + result.")
            return result

        # Store to DB
        intervention_id = store_intervention(
            cur, model, provider, intervention_type, description,
            baseline_bis, baseline_grade
        )
        result_id = store_result(
            cur, intervention_id, post_bis, post_grade, res_score, abs_improvement,
            temperature=temperature or 0.0, probe_count=probe_count, dataset='probes_500'
        )
        conn.commit()
        print(f"  [OK] Stored intervention (id={intervention_id}), result (id={result_id})")
        result['intervention_id'] = intervention_id
        result['result_id'] = result_id
        return result

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"  [ERROR] {e}")
        raise
    finally:
        if conn:
            conn.close()


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="RES Runner — Remediation Effectiveness Score")
    parser.add_argument('--model', type=str, help='Model name (provider/model-name format)')
    parser.add_argument('--intervention-type', type=str, choices=VALID_INTERVENTION_TYPES,
                        help='Type of intervention applied')
    parser.add_argument('--description', type=str, help='Description of the intervention')
    parser.add_argument('--baseline-bis', type=float, help='Known baseline BIS (or auto-fetch from DB)')
    parser.add_argument('--probes', type=str, default=str(DEFAULT_PROBES), help='Probes file path')
    parser.add_argument('--temperature', type=float, help='Temperature for post-intervention evaluation')
    parser.add_argument('--compute-from-db', action='store_true',
                        help='Compute RES from existing DB data (temperature_reduction)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would happen without writing to DB')
    parser.add_argument('--no-db', action='store_true', help='Run without database writes')

    args = parser.parse_args()

    print("=" * 60)
    print("RES Runner — Remediation Effectiveness Score")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)
    print()

    if args.compute_from_db:
        results = compute_res_from_db(dry_run=args.dry_run, no_db=args.no_db)
    elif args.model:
        if not args.intervention_type:
            parser.error("--intervention-type is required when using --model")
        if not args.description:
            parser.error("--description is required when using --model")

        # Parse provider/model
        provider = None
        model = args.model
        if '/' in model:
            provider, model = model.split('/', 1)

        print(f"── {model} ({provider}) ──")
        result = run_res_evaluation(
            model=model,
            provider=provider,
            intervention_type=args.intervention_type,
            description=args.description,
            baseline_bis=args.baseline_bis,
            probes=args.probes,
            temperature=args.temperature,
            dry_run=args.dry_run,
            no_db=args.no_db,
        )
        results = [result] if result else []
    else:
        parser.error("Either --model or --compute-from-db is required")

    print()
    print(f"Finished: {datetime.now().isoformat()}")
    if not results:
        print("No results produced.")
        sys.exit(1)


if __name__ == '__main__':
    main()
