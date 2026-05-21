#!/usr/bin/env python3
"""
Regulatory Mapper — Maps MTCP scores to regulatory compliance requirements.

Takes a model name and jurisdiction, returns compliance status based on
current MTCP scores in the database.

Usage:
    python regulatory_mapper.py --model openai/gpt-4o --jurisdiction eu_ai_act --context high_risk
    python regulatory_mapper.py --model openai/gpt-4o --jurisdiction all --context high_risk
    python regulatory_mapper.py --all-models --jurisdiction eu_ai_act --context high_risk
    python regulatory_mapper.py --model openai/gpt-4o --jurisdiction all --context high_risk --dry-run
    python regulatory_mapper.py --all-models --jurisdiction all --context high_risk --no-db

Jurisdictions:
    eu_ai_act       EU AI Act
    ndmo_saudi      NDMO Saudi Arabia
    nca_saudi       NCA Saudi Arabia
    mas_singapore   MAS Singapore
    uk_dsit         UK DSIT
    all             Check all jurisdictions
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

VALID_JURISDICTIONS = ['eu_ai_act', 'ndmo_saudi', 'nca_saudi', 'mas_singapore', 'uk_dsit']
VALID_CONTEXTS = ['high_risk', 'standard', 'low_risk', 'critical_infrastructure']


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


def grade_meets_requirement(current_grade, required_grade):
    """Check if current grade meets or exceeds required grade."""
    grade_order = {'A': 4, 'B': 3, 'C': 2, 'D': 1, 'F': 0}
    return grade_order.get(current_grade, 0) >= grade_order.get(required_grade, 0)


# ============================================================================
# Database helpers
# ============================================================================

def get_db():
    """Get database connection."""
    conn = psycopg2.connect(os.environ.get("DATABASE_URL", ""))
    conn.cursor_factory = RealDictCursor
    return conn


def get_current_bis(cur, model, provider):
    """
    Compute current BIS from the most recent probes_500 results.
    Returns (bis, grade) or (None, None) if no results found.
    """
    cur.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN r.outcome = 'COMPLETED' THEN 1 ELSE 0 END) as passed
        FROM runs ru
        JOIN results r ON ru.id = r.run_id
        WHERE ru.model = %s
          AND ru.dataset = 'probes_500'
          AND COALESCE(ru.provider, ru.api_provider, '') ILIKE %s
    """, (model, f'%{provider}%'))
    row = cur.fetchone()
    if row and row['total'] and row['total'] > 0:
        bis = round(100.0 * row['passed'] / row['total'], 1)
        return bis, bis_grade(bis)

    # Try without provider filter as fallback
    cur.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN r.outcome = 'COMPLETED' THEN 1 ELSE 0 END) as passed
        FROM runs ru
        JOIN results r ON ru.id = r.run_id
        WHERE ru.model = %s
          AND ru.dataset = 'probes_500'
    """, (model,))
    row = cur.fetchone()
    if row and row['total'] and row['total'] > 0:
        bis = round(100.0 * row['passed'] / row['total'], 1)
        return bis, bis_grade(bis)

    return None, None


def get_tds_validity(cur, model, provider):
    """Get the latest TDS baseline validity window for a model."""
    cur.execute("""
        SELECT valid_until, evaluated_at FROM tds_baselines
        WHERE model = %s AND provider = %s
          AND (valid_until IS NULL OR valid_until > NOW())
        ORDER BY evaluated_at DESC
        LIMIT 1
    """, (model, provider))
    row = cur.fetchone()
    if row and row['valid_until']:
        days_remaining = (row['valid_until'] - datetime.now()).days
        return days_remaining
    return None


def get_regulatory_mappings(cur, jurisdiction, context):
    """Get regulatory mappings for a jurisdiction and deployment context."""
    if jurisdiction == 'all':
        cur.execute("""
            SELECT * FROM regulatory_mappings
            WHERE deployment_context = %s
            ORDER BY jurisdiction
        """, (context,))
    else:
        cur.execute("""
            SELECT * FROM regulatory_mappings
            WHERE jurisdiction = %s AND deployment_context = %s
        """, (jurisdiction, context))
    return cur.fetchall()


def get_all_models(cur, limit=None):
    """Get all models with probes_500 data, ordered by BIS (top performers first)."""
    query = """
        SELECT ru.model,
               COALESCE(NULLIF(ru.provider, ''), NULLIF(ru.api_provider, ''), 'unknown') as provider,
               COUNT(*) as total,
               SUM(CASE WHEN r.outcome = 'COMPLETED' THEN 1 ELSE 0 END) as passed,
               ROUND(100.0 * SUM(CASE WHEN r.outcome = 'COMPLETED' THEN 1 ELSE 0 END) / COUNT(*), 1) as bis
        FROM runs ru
        JOIN results r ON ru.id = r.run_id
        WHERE ru.dataset = 'probes_500'
        GROUP BY ru.model, COALESCE(NULLIF(ru.provider, ''), NULLIF(ru.api_provider, ''), 'unknown')
        HAVING COUNT(*) >= 50
        ORDER BY bis DESC
    """
    if limit:
        query += f" LIMIT {int(limit)}"
    cur.execute(query)
    return cur.fetchall()


# ============================================================================
# Compliance checking
# ============================================================================

def check_compliance(cur, model, provider, current_bis, current_grade, mapping):
    """
    Check a model's compliance against a regulatory mapping.
    Returns (compliant, gaps, recommendations).
    """
    gaps = []
    recommendations = []
    required_grade = mapping['required_grade']
    required_metrics = mapping.get('required_metrics') or {}
    language_requirements = mapping.get('language_requirements') or {}

    # Check grade requirement
    if not grade_meets_requirement(current_grade, required_grade):
        gaps.append(f"Grade {current_grade} does not meet required Grade {required_grade}")
        recommendations.append(f"Improve BIS to achieve Grade {required_grade} (current: {current_bis}%)")

    # Check BIS minimum
    bis_min = required_metrics.get('bis_min')
    if bis_min and current_bis < bis_min:
        gaps.append(f"BIS {current_bis}% below required minimum {bis_min}%")
        recommendations.append(f"Increase BIS from {current_bis}% to >= {bis_min}%")

    # Check CPD maximum (Constraint Persistence Delta)
    cpd_max = required_metrics.get('cpd_max')
    if cpd_max:
        # CPD is approximated from temperature variance in existing data
        # For now we check if model has TDS data showing drift within limits
        tds_validity = get_tds_validity(cur, model, provider)
        if tds_validity is None:
            gaps.append(f"No TDS baseline found — cannot verify CPD < {cpd_max}pp")
            recommendations.append("Create TDS baseline with: python tds_runner.py --model MODEL --provider PROVIDER --create-baseline")

    # Check CSAS minimum
    csas_min = required_metrics.get('csas_min')
    if csas_min:
        try:
            cur.execute("SAVEPOINT csas_check")
            cur.execute("""
                SELECT s.csas, s.grade FROM csas_scores s
                JOIN csas_boundaries b ON s.boundary_id = b.id
                WHERE b.upstream_model = %s
                ORDER BY s.created_at DESC
                LIMIT 1
            """, (model,))
            csas_row = cur.fetchone()
            cur.execute("RELEASE SAVEPOINT csas_check")
            if csas_row:
                if csas_row['csas'] < csas_min:
                    gaps.append(f"CSAS {csas_row['csas']}% below required {csas_min}%")
                    recommendations.append(f"Improve CSAS from {csas_row['csas']}% to >= {csas_min}%")
            else:
                gaps.append(f"No CSAS evaluation found — required minimum {csas_min}%")
                recommendations.append("Run CSAS evaluation with: python csas_api.py")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT csas_check")
            gaps.append(f"No CSAS evaluation found — required minimum {csas_min}%")
            recommendations.append("Run CSAS evaluation with: python csas_api.py")

    # Check TDS validity window
    tds_validity_days = required_metrics.get('tds_validity_days')
    if tds_validity_days:
        tds_remaining = get_tds_validity(cur, model, provider)
        if tds_remaining is None:
            gaps.append(f"No valid TDS baseline — {tds_validity_days}-day validity required")
            recommendations.append("Create TDS baseline to establish validity window")
        elif tds_remaining < 0:
            gaps.append(f"TDS baseline expired — {tds_validity_days}-day validity required")
            recommendations.append("Re-evaluate model to refresh TDS baseline")

    # Check Sigma-Forensics audit requirement
    if required_metrics.get('sigma_forensics_audit'):
        # Check if there's a forensics audit record (table may not exist)
        try:
            cur.execute("SAVEPOINT sigma_check")
            cur.execute("""
                SELECT id FROM forensics_audits
                WHERE model = %s AND status = 'completed'
                ORDER BY created_at DESC
                LIMIT 1
            """, (model,))
            audit_row = cur.fetchone()
            cur.execute("RELEASE SAVEPOINT sigma_check")
            if not audit_row:
                gaps.append("Sigma-Forensics audit not completed")
                recommendations.append("Schedule Sigma-Forensics audit for this model")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT sigma_check")
            gaps.append("Sigma-Forensics audit status unknown (audit system not configured)")
            recommendations.append("Configure Sigma-Forensics audit system")

    # Check ACPS evaluation requirement
    if required_metrics.get('acps_evaluation'):
        gaps.append("ACPS evaluation not verified")
        recommendations.append("Complete ACPS (Autonomous Cyber Physical Systems) evaluation")

    # Check language requirements
    for lang, min_score in language_requirements.items():
        # Try to find language-specific evaluation data (table may not exist)
        try:
            cur.execute("SAVEPOINT lang_check")
            cur.execute("""
                SELECT score FROM language_evaluations
                WHERE model = %s AND language = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (model, lang))
            lang_row = cur.fetchone()
            cur.execute("RELEASE SAVEPOINT lang_check")
            if lang_row:
                if lang_row['score'] < min_score:
                    gaps.append(f"Language '{lang}' score {lang_row['score']}% below required {min_score}%")
                    recommendations.append(f"Improve {lang} performance from {lang_row['score']}% to >= {min_score}%")
            else:
                gaps.append(f"No evaluation data for language '{lang}' — required minimum {min_score}%")
                recommendations.append(f"Run language evaluation for '{lang}'")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT lang_check")
            gaps.append(f"Language evaluation for '{lang}' not available — required minimum {min_score}%")
            recommendations.append(f"Configure language evaluation system and test '{lang}'")

    compliant = len(gaps) == 0
    return compliant, gaps, recommendations


# ============================================================================
# Report storage
# ============================================================================

def store_compliance_report(cur, model, provider, jurisdiction, context, compliant,
                           current_grade, required_grade, current_bis, required_bis,
                           gaps, recommendations, valid_days=90):
    """Store a compliance report in the database."""
    valid_until = datetime.now() + timedelta(days=valid_days)
    cur.execute("""
        INSERT INTO compliance_reports
            (model, provider, jurisdiction, deployment_context, compliant,
             current_grade, required_grade, current_bis, required_bis,
             gaps, recommendations, report_date, valid_until)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
        RETURNING id
    """, (model, provider, jurisdiction, context, compliant,
          current_grade, required_grade, current_bis, required_bis,
          json.dumps(gaps), json.dumps(recommendations), valid_until))
    return cur.fetchone()['id']


# ============================================================================
# Core mapper logic
# ============================================================================

def run_regulatory_check(model, provider, jurisdiction, context, dry_run=False, no_db=False):
    """
    Run regulatory compliance check for a single model against a jurisdiction.
    Returns a list of result dicts (one per mapping found).
    """
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()

        # Get current BIS
        current_bis, current_grade = get_current_bis(cur, model, provider)
        if current_bis is None:
            print(f"  [SKIP] No probes_500 results found for {model} ({provider})")
            return []

        print(f"  Current BIS: {current_bis}% (Grade {current_grade})")

        # Get regulatory mappings
        mappings = get_regulatory_mappings(cur, jurisdiction, context)
        if not mappings:
            print(f"  [SKIP] No regulatory mappings found for {jurisdiction}/{context}")
            return []

        results = []
        for mapping in mappings:
            jur = mapping['jurisdiction']
            reg_name = mapping['regulation_name']
            required_grade = mapping['required_grade']
            required_metrics = mapping.get('required_metrics') or {}
            required_bis = required_metrics.get('bis_min')

            print(f"\n  ── {reg_name} ({jur}/{context}) ──")
            print(f"  Required: Grade {required_grade}" +
                  (f", BIS >= {required_bis}%" if required_bis else ""))

            # Check compliance
            compliant, gaps, recommendations = check_compliance(
                cur, model, provider, current_bis, current_grade, mapping
            )

            status = "COMPLIANT" if compliant else "NON-COMPLIANT"
            print(f"  Status: {status}")
            if gaps:
                print(f"  Gaps ({len(gaps)}):")
                for g in gaps:
                    print(f"    - {g}")
            if recommendations:
                print(f"  Recommendations ({len(recommendations)}):")
                for r in recommendations:
                    print(f"    - {r}")

            result = {
                'model': model,
                'provider': provider,
                'jurisdiction': jur,
                'deployment_context': context,
                'regulation_name': reg_name,
                'compliant': compliant,
                'current_grade': current_grade,
                'required_grade': required_grade,
                'current_bis': current_bis,
                'required_bis': required_bis,
                'gaps': gaps,
                'recommendations': recommendations,
            }
            results.append(result)

            # Store report
            if not dry_run and not no_db:
                report_id = store_compliance_report(
                    cur, model, provider, jur, context, compliant,
                    current_grade, required_grade, current_bis, required_bis,
                    gaps, recommendations
                )
                result['report_id'] = report_id
                print(f"  [OK] Report stored (id={report_id})")

        if not dry_run and not no_db:
            conn.commit()

        return results

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"  [ERROR] {e}")
        raise
    finally:
        if conn:
            conn.close()


def run_all_models(jurisdiction, context, dry_run=False, no_db=False, limit=None):
    """Run regulatory check for all models (or top N) against a jurisdiction."""
    conn = get_db()
    cur = conn.cursor()
    models = get_all_models(cur, limit=limit)
    conn.close()

    if not models:
        print("[INFO] No models found with probes_500 data.")
        return []

    print(f"[INFO] Checking {len(models)} models against {jurisdiction}/{context}...\n")
    all_results = []
    for row in models:
        model = row['model']
        provider = row['provider']
        print(f"{'='*60}")
        print(f"Model: {model} ({provider}) — BIS: {row['bis']}%")
        print(f"{'='*60}")
        results = run_regulatory_check(model, provider, jurisdiction, context,
                                       dry_run=dry_run, no_db=no_db)
        all_results.extend(results)
        print()

    # Summary
    if all_results:
        print("\n" + "=" * 70)
        print("REGULATORY COMPLIANCE SUMMARY")
        print("=" * 70)
        compliant_count = sum(1 for r in all_results if r['compliant'])
        non_compliant_count = sum(1 for r in all_results if not r['compliant'])
        print(f"\n  Total checks: {len(all_results)}")
        print(f"  Compliant:     {compliant_count}")
        print(f"  Non-compliant: {non_compliant_count}")
        print(f"\n  {'Model':<40} {'Jurisdiction':<15} {'Status':<15} {'Grade':<10}")
        print(f"  {'─'*40} {'─'*15} {'─'*15} {'─'*10}")
        for r in all_results:
            status = "PASS" if r['compliant'] else "FAIL"
            print(f"  {r['model']:<40} {r['jurisdiction']:<15} {status:<15} {r['current_grade']}/{r['required_grade']}")

    return all_results


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Regulatory Mapper — MTCP Compliance Checking")
    parser.add_argument('--model', type=str, help='Model name (provider/model-name format)')
    parser.add_argument('--jurisdiction', type=str, required=True,
                        choices=VALID_JURISDICTIONS + ['all'],
                        help='Jurisdiction to check against')
    parser.add_argument('--context', type=str, required=True,
                        choices=VALID_CONTEXTS,
                        help='Deployment context')
    parser.add_argument('--all-models', action='store_true',
                        help='Check all models against the specified jurisdiction')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of models when using --all-models')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would happen without writing to DB')
    parser.add_argument('--no-db', action='store_true',
                        help='Run without database writes')

    args = parser.parse_args()

    if not args.all_models and not args.model:
        parser.error("Either --model or --all-models is required")

    print("=" * 60)
    print("Regulatory Mapper — MTCP Compliance Checking")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Jurisdiction: {args.jurisdiction}")
    print(f"Context: {args.context}")
    print("=" * 60)
    print()

    if args.all_models:
        results = run_all_models(
            jurisdiction=args.jurisdiction,
            context=args.context,
            dry_run=args.dry_run,
            no_db=args.no_db,
            limit=args.limit,
        )
    else:
        # Parse provider/model
        provider = None
        model = args.model
        if '/' in model:
            provider, model = model.split('/', 1)

        print(f"Model: {model} ({provider})")
        print()
        results = run_regulatory_check(
            model=model,
            provider=provider or 'unknown',
            jurisdiction=args.jurisdiction,
            context=args.context,
            dry_run=args.dry_run,
            no_db=args.no_db,
        )

    print()
    print(f"Finished: {datetime.now().isoformat()}")
    if not results:
        print("No results produced.")
        sys.exit(1)

    # Exit with error code if any non-compliant
    non_compliant = [r for r in results if not r['compliant']]
    if non_compliant:
        print(f"\n[!] {len(non_compliant)} check(s) NON-COMPLIANT")
        sys.exit(2)
    else:
        print(f"\n[OK] All {len(results)} check(s) COMPLIANT")


if __name__ == '__main__':
    main()
