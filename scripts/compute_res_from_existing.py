#!/usr/bin/env python3
"""
Compute RES from Existing Data
Queries the DB for all models with probes_500 data at both T=0.0 and T=0.8,
computes RES for temperature_reduction intervention, and stores results.

Usage:
    python scripts/compute_res_from_existing.py
    python scripts/compute_res_from_existing.py --dry-run
"""

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))
except ImportError:
    pass

import psycopg2
from psycopg2.extras import RealDictCursor


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


def compute_res(post_bis, baseline_bis):
    """
    Compute Remediation Effectiveness Score.
    RES = (post_bis - baseline_bis) / (100 - baseline_bis)
    Capped at [-1.0, 1.0] for edge cases.
    """
    denominator = 100.0 - baseline_bis
    if denominator <= 0:
        return 0.0
    res = (post_bis - baseline_bis) / denominator
    return round(max(-1.0, min(1.0, res)), 4)


# ============================================================================
# Main
# ============================================================================

def main():
    dry_run = '--dry-run' in sys.argv

    print("=" * 70)
    print("RES Computation from Existing Data")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)
    print()

    conn = psycopg2.connect(os.environ.get("DATABASE_URL", ""))
    conn.cursor_factory = RealDictCursor
    cur = conn.cursor()

    # Step 1: Query models with probes_500 data at both T=0.0 and T=0.8
    print("[Step 1] Querying models with probes_500 data at T=0.0 and T=0.8...")
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
        print("[ERROR] No models found with both T=0.0 and T=0.8 probes_500 data.")
        conn.close()
        sys.exit(1)

    print(f"[OK] Found {len(rows)} model/provider combinations.\n")

    # Step 2: Compute RES for each model
    print("[Step 2] Computing RES scores...")
    print()
    print(f"{'#':<4} {'Model':<45} {'Provider':<15} {'T=0.8':<7} {'T=0.0':<7} {'RES':<8} {'Abs':<8} {'Grade Change'}")
    print("─" * 115)

    results = []
    for i, row in enumerate(rows, 1):
        model = row['model']
        provider = row['provider']
        baseline_bis = float(row['baseline_bis'])
        post_bis = float(row['post_bis'])
        probe_count = row['probe_count']

        res_score = compute_res(post_bis, baseline_bis)
        abs_improvement = round(post_bis - baseline_bis, 2)
        baseline_grade = bis_grade(baseline_bis)
        post_grade = bis_grade(post_bis)
        grade_change = f"{baseline_grade}->{post_grade}" if baseline_grade != post_grade else f"{baseline_grade}(same)"

        print(f"{i:<4} {model:<45} {provider:<15} {baseline_bis:<7.1f} {post_bis:<7.1f} {res_score:<8.4f} {abs_improvement:+6.1f}pp {grade_change}")

        results.append({
            'model': model,
            'provider': provider,
            'baseline_bis': baseline_bis,
            'post_bis': post_bis,
            'baseline_grade': baseline_grade,
            'post_grade': post_grade,
            'res_score': res_score,
            'abs_improvement': abs_improvement,
            'probe_count': probe_count,
        })

    # Step 3: Insert into res_interventions
    print(f"\n[Step 3] {'Would insert' if dry_run else 'Inserting'} {len(results)} res_interventions records...")
    intervention_ids = []
    for r in results:
        if not dry_run:
            cur.execute("""
                INSERT INTO res_interventions (model, provider, intervention_type, description, baseline_bis, baseline_grade)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (r['model'], r['provider'], 'temperature_reduction',
                  'Reduce temperature from 0.8 to 0.0', r['baseline_bis'], r['baseline_grade']))
            intervention_ids.append(cur.fetchone()['id'])
        else:
            intervention_ids.append(None)

    # Step 4: Insert into res_results
    print(f"[Step 4] {'Would insert' if dry_run else 'Inserting'} {len(results)} res_results records...")
    for i, r in enumerate(results):
        if not dry_run:
            cur.execute("""
                INSERT INTO res_results (intervention_id, post_bis, post_grade, res_score, absolute_improvement, temperature, probe_count, dataset)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (intervention_ids[i], r['post_bis'], r['post_grade'], r['res_score'],
                  r['abs_improvement'], 0.0, r['probe_count'], 'probes_500'))

    # Step 5: Insert res_ceilings for top 3 and bottom 3
    sorted_results = sorted(results, key=lambda x: x['res_score'], reverse=True)
    top_3 = sorted_results[:3]
    bottom_3 = sorted_results[-3:]

    # Deduplicate
    ceiling_models = []
    seen = set()
    for r in top_3 + bottom_3:
        key = (r['model'], r['provider'])
        if key not in seen:
            seen.add(key)
            ceiling_models.append(r)

    print(f"[Step 5] {'Would insert' if dry_run else 'Inserting'} {len(ceiling_models)} res_ceilings records...")
    for r in ceiling_models:
        failure_pattern = 'stochastic' if r['res_score'] > 0.3 else 'architectural'
        if not dry_run:
            cur.execute("""
                INSERT INTO res_ceilings (model, provider, ceiling_bis, ceiling_grade, best_intervention, failure_pattern)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (r['model'], r['provider'], r['post_bis'], r['post_grade'],
                  'temperature_reduction', failure_pattern))

    if not dry_run:
        conn.commit()
        print(f"\n[OK] All data committed to database.")
    else:
        print(f"\n[DRY-RUN] No data written.")

    conn.close()

    # Step 6: Report
    print("\n" + "=" * 70)
    print("RESULTS REPORT")
    print("=" * 70)

    print(f"\n  Total models evaluated: {len(results)}")
    avg_res = sum(r['res_score'] for r in results) / len(results) if results else 0
    print(f"  Mean RES (temperature_reduction): {avg_res:.4f}")
    positive = [r for r in results if r['res_score'] > 0]
    negative = [r for r in results if r['res_score'] < 0]
    neutral = [r for r in results if r['res_score'] == 0]
    print(f"  Improved: {len(positive)} | Degraded: {len(negative)} | Neutral: {len(neutral)}")

    print(f"\n  TOP 3 — Most responsive to temperature reduction:")
    for r in top_3:
        print(f"    {r['model']:<40} RES={r['res_score']:.4f}  BIS: {r['baseline_bis']:.1f}% -> {r['post_bis']:.1f}%  ({r['baseline_grade']}->{r['post_grade']})")

    print(f"\n  BOTTOM 3 — Least responsive (or degraded):")
    for r in bottom_3:
        print(f"    {r['model']:<40} RES={r['res_score']:.4f}  BIS: {r['baseline_bis']:.1f}% -> {r['post_bis']:.1f}%  ({r['baseline_grade']}->{r['post_grade']})")

    print(f"\n  Ceiling analysis:")
    for r in ceiling_models:
        fp = 'stochastic' if r['res_score'] > 0.3 else 'architectural'
        print(f"    {r['model']:<40} Ceiling BIS: {r['post_bis']:.1f}%  Pattern: {fp}")

    print(f"\nFinished: {datetime.now().isoformat()}")


if __name__ == '__main__':
    main()
