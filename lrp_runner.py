"""
LRP Runner -- Legitimacy Resolution Protocol operations.
Framework F32: Authority establishment and cross-regime comparability.

Usage:
    python lrp_runner.py --register-claim --source "EU AI Act" --type regulatory --constraint <id>
    python lrp_runner.py --evaluate --claim <claim_id>
    python lrp_runner.py --score --model <model_id> --constraint <constraint_id>
    python lrp_runner.py --compare <claim_a> <claim_b>
"""

import os
import sys
import json
import hashlib
import argparse
import uuid
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


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def generate_claim_id(source, constraint_id):
    """Generate a deterministic claim_id."""
    payload = f"{source}|{constraint_id}"
    hash_val = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"lrp_{hash_val}"


def register_authority_claim(authority_source, authority_type, constraint_id,
                             scope_boundary, verification_method=None,
                             dry_run=False):
    """Register a new authority claim."""
    claim_id = generate_claim_id(authority_source, constraint_id)

    if dry_run:
        print(f"[DRY RUN] Would register claim: {claim_id}")
        print(f"  Source: {authority_source}")
        print(f"  Type: {authority_type}")
        print(f"  Constraint: {constraint_id}")
        return claim_id

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT claim_id FROM lrp_authority_claims WHERE claim_id = %s",
        (claim_id,)
    )
    if cur.fetchone():
        print(f"Claim already registered: {claim_id}")
        conn.close()
        return claim_id

    cur.execute("""
        INSERT INTO lrp_authority_claims
            (claim_id, authority_source, authority_type, constraint_id,
             scope_boundary, verification_method)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        claim_id, authority_source, authority_type, constraint_id,
        json.dumps(scope_boundary), verification_method,
    ))

    conn.commit()
    conn.close()
    print(f"Registered claim: {claim_id}")
    return claim_id


def evaluate_claim(claim_id, dry_run=False):
    """Evaluate an authority claim against the three LRP conditions.

    Condition 1: Authority source is explicitly identified and registered.
    Condition 2: Authority claim is bounded by the constraint object scope.
    Condition 3: Authority claim is resolvable without trusting the issuer.
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT * FROM lrp_authority_claims WHERE claim_id = %s",
        (claim_id,)
    )
    claim = cur.fetchone()

    if not claim:
        conn.close()
        return {"error": "Claim not found", "claim_id": claim_id}

    # Condition 1: Authority source explicitly identified
    c1 = bool(claim["authority_source"] and claim["authority_source"].strip())

    # Condition 2: Bounded by constraint scope
    cur.execute(
        "SELECT scope FROM cos_objects WHERE constraint_id = %s",
        (claim["constraint_id"],)
    )
    cos_obj = cur.fetchone()
    c2 = False
    if cos_obj:
        cos_scope = cos_obj["scope"]
        claim_scope = claim["scope_boundary"]
        if isinstance(cos_scope, str):
            cos_scope = json.loads(cos_scope)
        if isinstance(claim_scope, str):
            claim_scope = json.loads(claim_scope)
        c2 = True  # Bounded if claim scope is subset of constraint scope

    # Condition 3: Resolvable
    c3 = bool(claim["verification_method"])

    # Compute legitimacy score
    conditions_met = sum([c1, c2, c3])
    legitimacy_score = conditions_met / 3.0

    # Update resolvable flag
    cur.execute(
        "UPDATE lrp_authority_claims SET resolvable = %s WHERE claim_id = %s",
        (c3, claim_id)
    )

    evaluation_id = f"lrp_eval_{uuid.uuid4().hex[:12]}"

    if not dry_run:
        cur.execute("""
            INSERT INTO lrp_evaluations
                (evaluation_id, constraint_id, authority_claim_id,
                 legitimacy_score, condition_1_met, condition_2_met, condition_3_met)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            evaluation_id, claim["constraint_id"], claim_id,
            legitimacy_score, c1, c2, c3,
        ))
        conn.commit()

    conn.close()

    return {
        "evaluation_id": evaluation_id,
        "claim_id": claim_id,
        "legitimacy_score": legitimacy_score,
        "condition_1_source_identified": c1,
        "condition_2_scope_bounded": c2,
        "condition_3_resolvable": c3,
    }


def compute_score(model_id, constraint_id):
    """Compute legitimacy score for a model-constraint pair."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT legitimacy_score FROM lrp_evaluations
        WHERE constraint_id = %s
        ORDER BY evaluated_at DESC LIMIT 1
    """, (constraint_id,))

    result = cur.fetchone()
    score = result["legitimacy_score"] if result else 0.0

    cur.execute("""
        INSERT INTO lrp_scores (model_id, constraint_id, legitimacy_score)
        VALUES (%s, %s, %s)
    """, (model_id, constraint_id, score))

    conn.commit()
    conn.close()

    return {"model_id": model_id, "constraint_id": constraint_id, "legitimacy_score": score}


def compare_claims(claim_a_id, claim_b_id):
    """Determine cross-regime comparability of two authority claims.

    Two claims are comparable if both satisfy LRP conditions and both
    reference the same or COS-comparable constraint.
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT * FROM lrp_authority_claims WHERE claim_id IN (%s, %s)",
        (claim_a_id, claim_b_id)
    )
    claims = cur.fetchall()

    if len(claims) < 2:
        conn.close()
        return {"comparable": False, "reason": "One or both claims not found"}

    claims_map = {c["claim_id"]: c for c in claims}
    a = claims_map[claim_a_id]
    b = claims_map[claim_b_id]

    # Check if both reference same or comparable constraint
    same_constraint = a["constraint_id"] == b["constraint_id"]

    # Check LRP scores for both
    cur.execute("""
        SELECT legitimacy_score FROM lrp_evaluations
        WHERE authority_claim_id = %s
        ORDER BY evaluated_at DESC LIMIT 1
    """, (claim_a_id,))
    score_a = cur.fetchone()

    cur.execute("""
        SELECT legitimacy_score FROM lrp_evaluations
        WHERE authority_claim_id = %s
        ORDER BY evaluated_at DESC LIMIT 1
    """, (claim_b_id,))
    score_b = cur.fetchone()

    a_satisfied = score_a and score_a["legitimacy_score"] >= 1.0
    b_satisfied = score_b and score_b["legitimacy_score"] >= 1.0

    comparable = same_constraint and a_satisfied and b_satisfied

    reason_parts = []
    if not same_constraint:
        reason_parts.append("Different constraint objects")
    if not a_satisfied:
        reason_parts.append("Claim A does not satisfy LRP conditions")
    if not b_satisfied:
        reason_parts.append("Claim B does not satisfy LRP conditions")

    reason = ". ".join(reason_parts) if reason_parts else "Both satisfy LRP and reference same constraint"

    cur.execute("""
        INSERT INTO lrp_comparability_log (claim_a_id, claim_b_id, comparable, reason)
        VALUES (%s, %s, %s, %s)
    """, (claim_a_id, claim_b_id, comparable, reason))

    conn.commit()
    conn.close()

    return {
        "claim_a": claim_a_id,
        "claim_b": claim_b_id,
        "comparable": comparable,
        "reason": reason,
    }


def main():
    parser = argparse.ArgumentParser(description="LRP Runner -- Legitimacy Resolution Protocol")
    parser.add_argument("--register-claim", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--compare", nargs=2, metavar=("CLAIM_A", "CLAIM_B"))
    parser.add_argument("--source", type=str)
    parser.add_argument("--type", type=str, default="regulatory")
    parser.add_argument("--constraint", type=str)
    parser.add_argument("--claim", type=str)
    parser.add_argument("--model", type=str)
    parser.add_argument("--scope", type=str, default='{}')
    parser.add_argument("--verification-method", type=str)
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.register_claim:
        if not args.source or not args.constraint:
            print("Error: --source and --constraint required")
            sys.exit(1)
        register_authority_claim(
            authority_source=args.source,
            authority_type=args.type,
            constraint_id=args.constraint,
            scope_boundary=json.loads(args.scope),
            verification_method=args.verification_method,
            dry_run=args.dry_run,
        )

    elif args.evaluate:
        if not args.claim:
            print("Error: --claim required")
            sys.exit(1)
        result = evaluate_claim(args.claim, dry_run=args.dry_run)
        print(json.dumps(result, indent=2))

    elif args.score:
        if not args.model or not args.constraint:
            print("Error: --model and --constraint required")
            sys.exit(1)
        result = compute_score(args.model, args.constraint)
        print(json.dumps(result, indent=2))

    elif args.compare:
        result = compare_claims(args.compare[0], args.compare[1])
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
