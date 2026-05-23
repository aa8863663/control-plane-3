"""
COS Runner -- Constraint Object Specification operations.
Framework F31: Governed constraint as a formal object.

Usage:
    python cos_runner.py --register --name "Arabic only" --scope '{"models": ["all"], "vectors": ["LANG"]}'
    python cos_runner.py --get <constraint_id>
    python cos_runner.py --compare <id_a> <id_b>
    python cos_runner.py --validate <constraint_id>
    python cos_runner.py --link <constraint_id> --model <model_id> --evaluation <eval_id>
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


def generate_constraint_id(name, scope):
    """Generate a deterministic constraint_id from name and scope."""
    payload = f"{name}|{json.dumps(scope, sort_keys=True)}"
    hash_val = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"cos_{hash_val}"


def register_constraint(name, description, provenance, scope,
                        validity_conditions, inheritance_rules,
                        expiry=None, dry_run=False):
    """Register a new constraint object in the COS registry."""
    constraint_id = generate_constraint_id(name, scope)

    if dry_run:
        print(f"[DRY RUN] Would register: {constraint_id}")
        print(f"  Name: {name}")
        print(f"  Scope: {json.dumps(scope)}")
        return constraint_id

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT constraint_id FROM cos_objects WHERE constraint_id = %s",
        (constraint_id,)
    )
    existing = cur.fetchone()

    if existing:
        print(f"Constraint already registered: {constraint_id}")
        conn.close()
        return constraint_id

    cur.execute("""
        INSERT INTO cos_objects
            (constraint_id, name, description, provenance, scope,
             validity_conditions, inheritance_rules, expiry)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        constraint_id,
        name,
        description,
        json.dumps(provenance),
        json.dumps(scope),
        json.dumps(validity_conditions),
        json.dumps(inheritance_rules),
        expiry,
    ))

    conn.commit()
    conn.close()
    print(f"Registered constraint: {constraint_id}")
    return constraint_id


def get_constraint(constraint_id):
    """Retrieve a full constraint object."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT * FROM cos_objects WHERE constraint_id = %s",
        (constraint_id,)
    )
    result = cur.fetchone()
    conn.close()

    if not result:
        print(f"Constraint not found: {constraint_id}")
        return None

    return dict(result)


def compare_constraints(id_a, id_b):
    """Determine if two constraint objects are comparable.

    Two constraints are comparable if they have equivalent scope
    and validity conditions (Constraint Identity Lemma).
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT * FROM cos_objects WHERE constraint_id IN (%s, %s)",
        (id_a, id_b)
    )
    results = cur.fetchall()
    conn.close()

    if len(results) < 2:
        return {
            "comparable": False,
            "reason": "One or both constraint objects not found.",
            "id_a": id_a,
            "id_b": id_b,
        }

    obj_a = {r["constraint_id"]: r for r in results}[id_a]
    obj_b = {r["constraint_id"]: r for r in results}[id_b]

    if id_a == id_b:
        return {
            "comparable": True,
            "reason": "Same constraint object.",
            "id_a": id_a,
            "id_b": id_b,
        }

    scope_match = obj_a["scope"] == obj_b["scope"]
    validity_match = obj_a["validity_conditions"] == obj_b["validity_conditions"]

    if scope_match and validity_match:
        return {
            "comparable": True,
            "reason": "Equivalent scope and validity conditions.",
            "id_a": id_a,
            "id_b": id_b,
        }

    reasons = []
    if not scope_match:
        reasons.append("Scope differs.")
    if not validity_match:
        reasons.append("Validity conditions differ.")

    return {
        "comparable": False,
        "reason": " ".join(reasons),
        "id_a": id_a,
        "id_b": id_b,
    }


def validate_constraint(constraint_id):
    """Check whether a constraint object is still valid."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT * FROM cos_objects WHERE constraint_id = %s",
        (constraint_id,)
    )
    obj = cur.fetchone()

    if not obj:
        conn.close()
        return {"valid": False, "reason": "Not found."}

    now = datetime.now(timezone.utc)
    is_valid = True
    reason = "Active and within validity window."

    if obj["status"] != "active":
        is_valid = False
        reason = f"Status is {obj['status']}."
    elif obj["expiry"] and obj["expiry"] < now:
        is_valid = False
        reason = "Expired."

    cur.execute("""
        INSERT INTO cos_validity_checks
            (constraint_id, is_valid, reason)
        VALUES (%s, %s, %s)
    """, (constraint_id, is_valid, reason))

    conn.commit()
    conn.close()

    return {"valid": is_valid, "reason": reason, "constraint_id": constraint_id}


def link_to_evaluation(constraint_id, model_id=None, evaluation_id=None):
    """Link a constraint object to a model or evaluation."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO cos_registry (constraint_id, model_id, evaluation_id)
        VALUES (%s, %s, %s)
    """, (constraint_id, model_id, evaluation_id))

    conn.commit()
    conn.close()
    print(f"Linked {constraint_id} -> model={model_id}, eval={evaluation_id}")


def main():
    parser = argparse.ArgumentParser(description="COS Runner -- Constraint Object operations")
    parser.add_argument("--register", action="store_true", help="Register a new constraint")
    parser.add_argument("--get", type=str, help="Get constraint by ID")
    parser.add_argument("--compare", nargs=2, metavar=("ID_A", "ID_B"), help="Compare two constraints")
    parser.add_argument("--validate", type=str, help="Validate constraint")
    parser.add_argument("--link", type=str, help="Link constraint to evaluation")
    parser.add_argument("--name", type=str, help="Constraint name")
    parser.add_argument("--description", type=str, default="", help="Description")
    parser.add_argument("--scope", type=str, default='{}', help="Scope JSON")
    parser.add_argument("--provenance", type=str, default='{}', help="Provenance JSON")
    parser.add_argument("--validity", type=str, default='{}', help="Validity conditions JSON")
    parser.add_argument("--inheritance", type=str, default='{"inheritable": true}', help="Inheritance JSON")
    parser.add_argument("--model", type=str, help="Model ID for linking")
    parser.add_argument("--evaluation", type=str, help="Evaluation ID for linking")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to database")

    args = parser.parse_args()

    if args.register:
        if not args.name:
            print("Error: --name required for registration")
            sys.exit(1)
        cid = register_constraint(
            name=args.name,
            description=args.description,
            provenance=json.loads(args.provenance),
            scope=json.loads(args.scope),
            validity_conditions=json.loads(args.validity),
            inheritance_rules=json.loads(args.inheritance),
            dry_run=args.dry_run,
        )
        print(f"constraint_id: {cid}")

    elif args.get:
        result = get_constraint(args.get)
        if result:
            print(json.dumps(result, indent=2, default=str))

    elif args.compare:
        result = compare_constraints(args.compare[0], args.compare[1])
        print(json.dumps(result, indent=2))

    elif args.validate:
        result = validate_constraint(args.validate)
        print(json.dumps(result, indent=2))

    elif args.link:
        link_to_evaluation(args.link, model_id=args.model, evaluation_id=args.evaluation)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
