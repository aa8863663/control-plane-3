"""
Correction Ceiling Calculator -- Maximum achievable constraint persistence.
MAFS Phase 1: Upper bound of what any intervention can achieve.

Usage:
    python correction_ceiling_calculator.py --model gpt-4o
    python correction_ceiling_calculator.py --all
"""

import os
import sys
import json
import argparse
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

import psycopg2
import psycopg2.extras


DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def ceiling_grade(score):
    """Grade ceiling score."""
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"


def compute_ceiling(model_id, dry_run=False):
    """Compute correction ceiling from existing evaluation data.

    The ceiling is the maximum BIS achievable after full correction exhaustion.
    Extracted from temperature sensitivity data: best score at T=0.0
    represents the ceiling (most deterministic, least stochastic variance).
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get pass rate per temperature from actual data
    cur.execute("""
        SELECT r.temperature,
               COUNT(*) FILTER (WHERE res.outcome = 'COMPLETED') * 100.0 / NULLIF(COUNT(*), 0) as pass_rate
        FROM runs r
        JOIN results res ON res.run_id = r.id
        WHERE r.model = %s AND r.dataset IN ('probes_200', 'probes_500')
        GROUP BY r.temperature
        ORDER BY r.temperature
    """, (model_id,))
    scores = cur.fetchall()

    if not scores:
        conn.close()
        return {"model_id": model_id, "error": "No scores found"}

    # T=0.0 represents the ceiling (most deterministic)
    t00 = None
    all_rates = []
    for row in scores:
        rate = row["pass_rate"] or 0.0
        all_rates.append(rate)
        if row["temperature"] == 0.0:
            t00 = rate

    bis_mean = sum(all_rates) / len(all_rates) if all_rates else 50.0
    ceiling = max(t00 or bis_mean, bis_mean)
    ceiling = min(ceiling, 100.0)

    grade = ceiling_grade(ceiling)
    exhausted = (ceiling - bis_mean) < 2.0  # Within 2pp means ceiling reached

    result = {
        "model_id": model_id,
        "ceiling_score": round(ceiling, 2),
        "ceiling_grade": grade,
        "max_bis_achievable": round(ceiling, 2),
        "correction_exhausted": exhausted,
        "current_bis": round(bis_mean, 2),
        "improvement_remaining": round(ceiling - bis_mean, 2),
    }

    if not dry_run:
        cur.execute("""
            INSERT INTO correction_ceilings
                (model_id, ceiling_score, ceiling_grade, max_bis_achievable,
                 correction_exhausted)
            VALUES (%s, %s, %s, %s, %s)
        """, (model_id, ceiling, grade, ceiling, exhausted))
        conn.commit()

    conn.close()
    return result


def compute_all(dry_run=False):
    """Compute ceiling for all models."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT DISTINCT model FROM runs WHERE dataset IN ('probes_200', 'probes_500')")
    models = [r["model"] for r in cur.fetchall()]
    conn.close()

    results = []
    for model_id in models:
        result = compute_ceiling(model_id, dry_run=dry_run)
        if "error" not in result:
            results.append(result)
            print(f"  {model_id}: Ceiling={result['ceiling_score']:.1f}% Grade={result['ceiling_grade']}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Correction Ceiling Calculator")
    parser.add_argument("--model", type=str)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.all:
        results = compute_all(dry_run=args.dry_run)
        print(f"\nComputed ceilings for {len(results)} models.")
    elif args.model:
        result = compute_ceiling(args.model, dry_run=args.dry_run)
        print(json.dumps(result, indent=2, default=str))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
