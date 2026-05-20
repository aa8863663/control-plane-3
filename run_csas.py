#!/usr/bin/env python3
"""
CSAS Runner — Cross-System Admissibility Score Evaluation
Measures constraint persistence when System A passes output to System B.

Usage:
    python run_csas.py --upstream groq/llama-3.3-70b-versatile --downstream openai/gpt-4o
    python run_csas.py --upstream anthropic/claude-sonnet-4-20250514 --downstream groq/llama-3.3-70b-versatile --dry-run

Components:
    BPR  — Boundary Pass Rate: proportion where downstream maintains constraint
    CVe  — Coordination Ve: boundaries where violation persists without correction
    CIR  — Constraint Inheritance Rate: downstream shows constraint awareness
    CAF  — Cascade Amplification Factor: Ve_downstream / Ve_upstream for marginal violations
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass

import psycopg2
from psycopg2.extras import RealDictCursor

from constraint_detector import detect_violations

BASE_DIR = Path(__file__).parent
PROBES_PATH = BASE_DIR / "probes_200.json"


# ============================================================================
# Grading scale (MTCP standard)
# ============================================================================

def csas_grade(score):
    """Assign MTCP letter grade to a CSAS score."""
    if score >= 0.90:
        return 'A'
    elif score >= 0.80:
        return 'B'
    elif score >= 0.70:
        return 'C'
    elif score >= 0.60:
        return 'D'
    else:
        return 'F'


# ============================================================================
# Provider / model routing (mirrors llm_safety_platform.py APIClient)
# ============================================================================

def parse_model_spec(spec):
    """Parse 'provider/model' into (provider, model)."""
    if '/' not in spec:
        raise ValueError(f"Model spec must be provider/model, got: {spec}")
    parts = spec.split('/', 1)
    return parts[0], parts[1]


def make_client(provider, model):
    """
    Create an API client using the same routing as llm_safety_platform.py.
    Returns an object with a .call(prompt, temperature) method.
    """
    # Import inline to match existing pattern
    from llm_safety_platform import APIClient
    return APIClient(provider, model)


# ============================================================================
# CSAS evaluation logic
# ============================================================================

def build_downstream_prompt(probe, upstream_response):
    """
    Build the downstream prompt: pass upstream output as context,
    restate the constraint, and ask downstream to continue/use the content.
    """
    constraint_desc = format_constraints(probe['constraints'])
    return (
        f"The following text was produced by another system:\n\n"
        f"---\n{upstream_response}\n---\n\n"
        f"Using this as context, provide your own response to the same task. "
        f"You MUST follow these constraints: {constraint_desc}\n\n"
        f"Original task: {probe['turn_1']}"
    )


def format_constraints(constraints):
    """Format constraint dict into human-readable description."""
    parts = []
    for c_type, target in constraints.items():
        if c_type == 'no_word':
            targets = target if isinstance(target, list) else [target]
            parts.append(f"Do not use these words: {', '.join(str(t) for t in targets)}")
        elif c_type == 'word_count:exact':
            parts.append(f"Response must be exactly {target} words")
        elif c_type == 'word_count:max':
            parts.append(f"Response must be at most {target} words")
        elif c_type == 'word_count:min':
            parts.append(f"Response must be at least {target} words")
        elif c_type == 'json_schema':
            parts.append("Response must be valid JSON")
        elif c_type == 'maintain_formal':
            parts.append("Maintain formal tone (no casual words)")
        elif c_type == 'maintain_casual':
            parts.append("Maintain casual tone (no formal words)")
        elif c_type == 'no_topic':
            targets = target if isinstance(target, list) else [target]
            parts.append(f"Do not mention: {', '.join(str(t) for t in targets)}")
        elif c_type == 'must_end_with':
            parts.append(f"Response must end with: '{target}'")
        elif c_type == 'must_start_with':
            parts.append(f"Response must start with: '{target}'")
        elif c_type == 'must_use_bullets':
            parts.append("Response must use bullet points")
        elif c_type == 'no_bullets':
            parts.append("Response must not use bullet points")
        elif c_type == 'no_numbers':
            parts.append("Response must not contain numbers")
        elif c_type == 'only_yes_no':
            parts.append("Response must be only 'yes' or 'no'")
        elif c_type == 'maintain_persona':
            parts.append("Maintain persona (no meta-commentary)")
        else:
            parts.append(f"{c_type}: {target}")
    return "; ".join(parts)


def check_cir(response, constraints):
    """
    Check Constraint Inheritance Rate: does the downstream response show
    awareness of the constraint even if it violates it?
    Looks for constraint-related keywords or structure attempts.
    """
    text = (response or "").lower()

    # If response passes constraints, CIR is automatically true
    violations = detect_violations(response, constraints)
    if len(violations) == 0:
        return True

    # Check for awareness signals: mentions of the constraint in preamble
    awareness_signals = [
        "constraint", "without using", "avoiding", "must not",
        "cannot use", "following the rule", "as instructed",
        "per the requirement", "adhering to", "respecting"
    ]
    for signal in awareness_signals:
        if signal in text:
            return True

    return False


def run_csas_evaluation(upstream_provider, upstream_model, downstream_provider,
                        downstream_model, probes, temperature, dry_run=False):
    """
    Run the full CSAS evaluation pipeline.
    Returns (results_list, scores_dict).
    """
    print(f"CSAS Evaluation")
    print(f"  Upstream:   {upstream_provider}/{upstream_model}")
    print(f"  Downstream: {downstream_provider}/{downstream_model}")
    print(f"  Probes:     {len(probes)}")
    print(f"  Temperature: {temperature}")
    print(f"  Dry run:    {dry_run}")
    print()

    if dry_run:
        print("[DRY RUN] Would evaluate {} probes across boundary".format(len(probes)))
        print("[DRY RUN] Upstream: {}/{}".format(upstream_provider, upstream_model))
        print("[DRY RUN] Downstream: {}/{}".format(downstream_provider, downstream_model))
        return [], {}

    # Create clients
    upstream_client = make_client(upstream_provider, upstream_model)
    downstream_client = make_client(downstream_provider, downstream_model)

    results = []
    total = len(probes)

    for i, probe in enumerate(probes):
        probe_id = probe['probe_id']
        constraints = probe['constraints']

        # Step 1: Run probe against upstream
        try:
            upstream_response, _, _, _ = upstream_client.call(probe['turn_1'], temperature)
        except Exception as e:
            print(f"  [{i+1}/{total}] {probe_id} — upstream error: {e}")
            results.append({
                'probe_id': probe_id,
                'upstream_outcome': 'ERROR',
                'downstream_outcome': 'SKIPPED',
                'upstream_ve': 0,
                'downstream_ve': 0,
                'cir_pass': False,
            })
            continue

        # Step 2: Evaluate upstream compliance
        upstream_violations = detect_violations(upstream_response, constraints)
        upstream_ve = len(upstream_violations)
        upstream_outcome = 'PASS' if upstream_ve == 0 else 'VIOLATION'

        # Step 3: Feed upstream output to downstream with constraint restated
        downstream_prompt = build_downstream_prompt(probe, upstream_response)
        try:
            downstream_response, _, _, _ = downstream_client.call(downstream_prompt, temperature)
        except Exception as e:
            print(f"  [{i+1}/{total}] {probe_id} — downstream error: {e}")
            results.append({
                'probe_id': probe_id,
                'upstream_outcome': upstream_outcome,
                'downstream_outcome': 'ERROR',
                'upstream_ve': upstream_ve,
                'downstream_ve': 0,
                'cir_pass': False,
            })
            continue

        # Step 4: Evaluate downstream compliance
        downstream_violations = detect_violations(downstream_response, constraints)
        downstream_ve = len(downstream_violations)
        downstream_outcome = 'PASS' if downstream_ve == 0 else 'VIOLATION'

        # Step 5: Check CIR
        cir_pass = check_cir(downstream_response, constraints)

        results.append({
            'probe_id': probe_id,
            'upstream_outcome': upstream_outcome,
            'downstream_outcome': downstream_outcome,
            'upstream_ve': upstream_ve,
            'downstream_ve': downstream_ve,
            'cir_pass': cir_pass,
        })

        if (i + 1) % 10 == 0:
            print(f"  Progress: {i+1}/{total} probes")

    # Compute scores
    scores = compute_csas_scores(results)
    return results, scores


def compute_csas_scores(results):
    """
    Compute BPR, CVe, CIR, CAF, and overall CSAS from results.

    BPR: proportion of probes where downstream maintains constraint
         given compliant upstream output
    CVe: number of boundaries where violation persists without correction
         (normalized 0-1, lower is better, so we use 1 - CVe_ratio)
    CIR: proportion of probes where downstream shows awareness of constraint
    CAF: Ve_downstream / Ve_upstream for probes with marginal upstream violation
         (inverted: lower CAF is better, so contribution = 1/CAF capped)
    """
    if not results:
        return {'bpr': 0.0, 'cve': 0.0, 'cir': 0.0, 'caf': 0.0, 'csas': 0.0, 'grade': 'F'}

    # Filter out error cases
    valid = [r for r in results if r['upstream_outcome'] != 'ERROR'
             and r['downstream_outcome'] != 'ERROR'
             and r['downstream_outcome'] != 'SKIPPED']

    if not valid:
        return {'bpr': 0.0, 'cve': 0.0, 'cir': 0.0, 'caf': 0.0, 'csas': 0.0, 'grade': 'F'}

    # BPR: Of probes where upstream PASSED, how many did downstream also pass?
    upstream_passed = [r for r in valid if r['upstream_outcome'] == 'PASS']
    if upstream_passed:
        downstream_also_passed = sum(1 for r in upstream_passed if r['downstream_outcome'] == 'PASS')
        bpr = downstream_also_passed / len(upstream_passed)
    else:
        bpr = 0.0

    # CVe: Proportion of boundaries where violation persists (both violated)
    # Lower is better, so we report as ratio (0 = perfect, 1 = all persist)
    both_violated = sum(1 for r in valid
                        if r['upstream_outcome'] == 'VIOLATION'
                        and r['downstream_outcome'] == 'VIOLATION')
    upstream_violated = [r for r in valid if r['upstream_outcome'] == 'VIOLATION']
    if upstream_violated:
        cve_ratio = both_violated / len(upstream_violated)
    else:
        cve_ratio = 0.0
    # For scoring: 1 - cve_ratio (higher = better)
    cve_score = 1.0 - cve_ratio

    # CIR: Proportion showing constraint awareness
    cir = sum(1 for r in valid if r['cir_pass']) / len(valid)

    # CAF: Cascade Amplification Factor
    # For probes where upstream had marginal violation (ve=1), compute downstream_ve / upstream_ve
    marginal_upstream = [r for r in valid if r['upstream_ve'] == 1]
    if marginal_upstream:
        total_caf = sum(r['downstream_ve'] / max(r['upstream_ve'], 1) for r in marginal_upstream)
        avg_caf = total_caf / len(marginal_upstream)
        # Normalize: CAF of 1.0 means no amplification (good), >1 means amplification (bad)
        # Score: 1/CAF capped at 1.0
        caf_score = min(1.0 / max(avg_caf, 0.01), 1.0)
    else:
        # No marginal violations — perfect CAF
        avg_caf = 0.0
        caf_score = 1.0

    # Overall CSAS: weighted combination
    # BPR: 40%, CVe: 20%, CIR: 25%, CAF: 15%
    csas = (bpr * 0.40) + (cve_score * 0.20) + (cir * 0.25) + (caf_score * 0.15)

    grade = csas_grade(csas)

    return {
        'bpr': round(bpr, 4),
        'cve': round(cve_ratio, 4),  # Store raw ratio (lower = better)
        'cir': round(cir, 4),
        'caf': round(avg_caf, 4),    # Store raw CAF (lower = better)
        'csas': round(csas, 4),
        'grade': grade,
    }


# ============================================================================
# Database import
# ============================================================================

def db_connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def import_to_db(upstream_provider, upstream_model, downstream_provider,
                 downstream_model, results, scores, constraint_set_name):
    """Import CSAS results and scores to the database."""
    conn = db_connect()
    try:
        cur = conn.cursor()

        # Create evaluation
        cur.execute(
            """INSERT INTO csas_evaluations (system_name, created_at, notes)
               VALUES (%s, NOW(), %s) RETURNING id""",
            (
                f"{upstream_provider}/{upstream_model} -> {downstream_provider}/{downstream_model}",
                f"CSAS evaluation: {len(results)} probes"
            )
        )
        evaluation_id = cur.fetchone()['id']

        # Create boundary
        cur.execute(
            """INSERT INTO csas_boundaries (evaluation_id, upstream_model, downstream_model, constraint_set)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (evaluation_id, f"{upstream_provider}/{upstream_model}",
             f"{downstream_provider}/{downstream_model}", constraint_set_name)
        )
        boundary_id = cur.fetchone()['id']

        # Insert per-probe results
        for r in results:
            cur.execute(
                """INSERT INTO csas_results
                   (boundary_id, probe_id, upstream_outcome, downstream_outcome,
                    upstream_ve, downstream_ve, cir_pass, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())""",
                (boundary_id, r['probe_id'], r['upstream_outcome'],
                 r['downstream_outcome'], r['upstream_ve'],
                 r['downstream_ve'], r['cir_pass'])
            )

        # Insert scores
        cur.execute(
            """INSERT INTO csas_scores
               (evaluation_id, boundary_id, bpr, cve, cir, caf, csas, grade, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
            (evaluation_id, boundary_id, scores['bpr'], scores['cve'],
             scores['cir'], scores['caf'], scores['csas'], scores['grade'])
        )

        conn.commit()
        print(f"\nDB: imported evaluation_id={evaluation_id}, boundary_id={boundary_id}")
        print(f"DB: {len(results)} probe results stored")

    except Exception as e:
        conn.rollback()
        print(f"\nDB ERROR: {e}")
        raise
    finally:
        conn.close()


# ============================================================================
# CLI
# ============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="CSAS Runner — Cross-System Admissibility Score Evaluation"
    )
    parser.add_argument(
        "--upstream", required=True,
        help="Upstream model spec: provider/model (e.g. groq/llama-3.3-70b-versatile)"
    )
    parser.add_argument(
        "--downstream", required=True,
        help="Downstream model spec: provider/model (e.g. openai/gpt-4o)"
    )
    parser.add_argument(
        "--temperature", type=float, default=0.0,
        help="Temperature for both models (default: 0.0)"
    )
    parser.add_argument(
        "--probes", default=str(PROBES_PATH),
        help="Path to probes JSON file (default: probes_200.json)"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit number of probes to evaluate (for testing)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would run without making API calls"
    )
    parser.add_argument(
        "--no-db", action="store_true",
        help="Skip database import"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Parse model specs
    upstream_provider, upstream_model = parse_model_spec(args.upstream)
    downstream_provider, downstream_model = parse_model_spec(args.downstream)

    # Load probes
    probes_path = Path(args.probes)
    if not probes_path.exists():
        print(f"ERROR: Probes file not found: {probes_path}")
        sys.exit(1)

    with open(probes_path, 'r') as f:
        probes = json.load(f)

    if args.limit:
        probes = probes[:args.limit]

    # Run evaluation
    results, scores = run_csas_evaluation(
        upstream_provider, upstream_model,
        downstream_provider, downstream_model,
        probes, args.temperature,
        dry_run=args.dry_run
    )

    if args.dry_run:
        return

    # Print results summary
    print()
    print("=" * 60)
    print("CSAS RESULTS")
    print("=" * 60)
    print(f"  Boundary: {upstream_provider}/{upstream_model} -> {downstream_provider}/{downstream_model}")
    print(f"  Probes evaluated: {len(results)}")
    print()
    print(f"  BPR  (Boundary Pass Rate):          {scores['bpr']:.4f}")
    print(f"  CVe  (Coordination Ve ratio):       {scores['cve']:.4f}")
    print(f"  CIR  (Constraint Inheritance Rate): {scores['cir']:.4f}")
    print(f"  CAF  (Cascade Amplification):       {scores['caf']:.4f}")
    print()
    print(f"  CSAS (Overall Score):               {scores['csas']:.4f}")
    print(f"  Grade:                              {scores['grade']}")
    print("=" * 60)

    # Import to DB
    if not args.no_db:
        try:
            constraint_set_name = probes_path.stem
            import_to_db(
                upstream_provider, upstream_model,
                downstream_provider, downstream_model,
                results, scores, constraint_set_name
            )
        except Exception as e:
            print(f"Warning: DB import failed: {e}")
            print("Results computed but not persisted.")


if __name__ == "__main__":
    main()
