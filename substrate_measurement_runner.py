"""
Substrate Measurement Runner — Computes four holon vectors from existing data.
Framework F38: Agent Substrate Measurement.

Usage:
    python substrate_measurement_runner.py --model grok-3-mini
    python substrate_measurement_runner.py --all
"""
import os, sys, json, argparse
from pathlib import Path
from datetime import datetime, timezone
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError: pass
import psycopg2, psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn

def bis_grade(pct):
    if pct >= 90: return "A"
    elif pct >= 80: return "B"
    elif pct >= 70: return "C"
    elif pct >= 60: return "D"
    else: return "F"

def compute_knowledge_integrity(model_id, cur):
    """Vector 1: consistency across knowledge domains (probe vectors)."""
    cur.execute("""
        SELECT LEFT(res.probe_id, POSITION('-' IN res.probe_id)-1) as vector,
               COUNT(*) FILTER (WHERE res.outcome = 'COMPLETED') * 100.0 / NULLIF(COUNT(*), 0) as pass_rate
        FROM runs r JOIN results res ON res.run_id = r.id
        WHERE r.model = %s AND r.dataset IN ('probes_200','probes_500')
        GROUP BY 1
    """, (model_id,))
    rows = cur.fetchall()
    if not rows: return None, 0, 0
    rates = [float(r["pass_rate"]) for r in rows if r["pass_rate"]]
    if not rates: return None, 0, 0
    mean = sum(rates) / len(rates)
    variance = max(rates) - min(rates) if len(rates) > 1 else 0
    consistency = max(0, 1.0 - (variance / 100.0))
    return round(consistency, 4), len(rates), sum(1 for r in rates if abs(r - mean) < 15)

def compute_context_provenance(model_id, cur):
    """Vector 2: consistency across providers (if multi-provider data exists)."""
    cur.execute("""
        SELECT r.provider,
               COUNT(*) FILTER (WHERE res.outcome = 'COMPLETED') * 100.0 / NULLIF(COUNT(*), 0) as pass_rate
        FROM runs r JOIN results res ON res.run_id = r.id
        WHERE r.model = %s AND r.dataset IN ('probes_200','probes_500')
        GROUP BY r.provider
    """, (model_id,))
    rows = cur.fetchall()
    if not rows or len(rows) < 1: return 1.0, 1, 1  # Single provider = consistent
    rates = [float(r["pass_rate"]) for r in rows if r["pass_rate"]]
    if len(rates) <= 1: return 1.0, len(rates), len(rates)
    variance = max(rates) - min(rates)
    consistency = max(0, 1.0 - (variance / 100.0))
    mean = sum(rates) / len(rates)
    consistent = sum(1 for r in rates if abs(r - mean) < 10)
    return round(consistency, 4), len(rates), consistent

def compute_schema_persistence(model_id, cur):
    """Vector 3: core BIS measurement."""
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE res.outcome = 'COMPLETED') * 100.0 / NULLIF(COUNT(*), 0) as pass_rate
        FROM runs r JOIN results res ON res.run_id = r.id
        WHERE r.model = %s AND r.dataset IN ('probes_200','probes_500')
    """, (model_id,))
    row = cur.fetchone()
    if not row or not row["pass_rate"]: return None, None
    bis = float(row["pass_rate"])
    return round(bis / 100.0, 4), round(bis, 2)

def compute_projection_consistency(model_id, cur):
    """Vector 4: consistency across output formats (datasets as proxy)."""
    cur.execute("""
        SELECT r.dataset,
               COUNT(*) FILTER (WHERE res.outcome = 'COMPLETED') * 100.0 / NULLIF(COUNT(*), 0) as pass_rate
        FROM runs r JOIN results res ON res.run_id = r.id
        WHERE r.model = %s
        GROUP BY r.dataset
    """, (model_id,))
    rows = cur.fetchall()
    if not rows: return 1.0, 0, 0
    rates = [float(r["pass_rate"]) for r in rows if r["pass_rate"]]
    if len(rates) <= 1: return 1.0 if rates else 0.0, len(rates), len(rates)
    variance = max(rates) - min(rates)
    consistency = max(0, 1.0 - (variance / 100.0))
    mean = sum(rates) / len(rates)
    consistent = sum(1 for r in rates if abs(r - mean) < 20)
    return round(consistency, 4), len(rates), consistent

def compute_holon(knowledge, context, schema, projection):
    """Composite Holon Completeness Score (equal weights)."""
    scores = [s for s in [knowledge, context, schema, projection] if s is not None]
    if not scores: return None
    return round(sum(scores) / len(scores), 4)

def measure_model(model_id, dry_run=False):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    k_score, k_tested, k_consistent = compute_knowledge_integrity(model_id, cur)
    c_score, c_tested, c_consistent = compute_context_provenance(model_id, cur)
    s_score, bis_mean = compute_schema_persistence(model_id, cur)
    p_score, p_tested, p_consistent = compute_projection_consistency(model_id, cur)

    holon = compute_holon(k_score, c_score, s_score, p_score)
    grade = bis_grade(holon * 100) if holon else "F"

    if not dry_run and k_score is not None:
        cur.execute("INSERT INTO substrate_knowledge_scores (model_id, knowledge_integrity_score, domains_tested, domains_consistent) VALUES (%s,%s,%s,%s)",
                    (model_id, k_score, k_tested, k_consistent))
        cur.execute("INSERT INTO substrate_context_scores (model_id, context_provenance_score, providers_tested, providers_consistent) VALUES (%s,%s,%s,%s)",
                    (model_id, c_score, c_tested, c_consistent))
        cur.execute("INSERT INTO substrate_schema_scores (model_id, schema_persistence_score, bis_mean, grade) VALUES (%s,%s,%s,%s)",
                    (model_id, s_score, bis_mean, bis_grade(bis_mean) if bis_mean else "F"))
        cur.execute("INSERT INTO substrate_projection_scores (model_id, projection_consistency_score, formats_tested, formats_consistent) VALUES (%s,%s,%s,%s)",
                    (model_id, p_score, p_tested, p_consistent))
        conn.commit()

    conn.close()
    return {
        "model_id": model_id,
        "knowledge_integrity": k_score,
        "context_provenance": c_score,
        "schema_persistence": s_score,
        "projection_consistency": p_score,
        "holon_completeness": holon,
        "holon_grade": grade,
    }

def main():
    parser = argparse.ArgumentParser(description="Substrate Measurement Runner")
    parser.add_argument("--model", type=str)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.all:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT DISTINCT model FROM runs WHERE dataset IN ('probes_200','probes_500')")
        models = [r["model"] for r in cur.fetchall()]
        conn.close()
        results = []
        for m in sorted(models):
            r = measure_model(m, dry_run=args.dry_run)
            results.append(r)
            print(f"  {m}: Holon={r['holon_completeness']:.3f} ({r['holon_grade']})" if r['holon_completeness'] else f"  {m}: NO DATA")
        print(f"\nComputed substrate for {len(results)} models.")
        return results
    elif args.model:
        r = measure_model(args.model, dry_run=args.dry_run)
        print(json.dumps(r, indent=2, default=str))
        return [r]
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
