"""
GRC Runner -- Governance Reference Conditions operations.
Framework F33: Comparability conditions for coordinated systems.

Usage:
    python grc_runner.py --record --model <model_id> --evaluation <eval_id>
    python grc_runner.py --compare <model_a> <model_b>
    python grc_runner.py --classify <csas_id> --model-a <a> --model-b <b>
    python grc_runner.py --conditions <evaluation_id>
"""

import os
import sys
import json
import argparse
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

JRS_MIN_THRESHOLD = 0.75


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def record_conditions(model_id, evaluation_id, constraint_id=None,
                      lrp_score=None, temperature_config=None,
                      infrastructure_config=None, jrs_score=None,
                      bec_integrity=None, dry_run=False):
    """Record governance reference conditions for an evaluation."""
    if dry_run:
        print(f"[DRY RUN] Would record GRC for {model_id} / {evaluation_id}")
        return

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO grc_conditions
            (evaluation_id, model_id, constraint_id, lrp_score,
             temperature_config, infrastructure_config, jrs_score, bec_integrity)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        evaluation_id, model_id, constraint_id, lrp_score,
        json.dumps(temperature_config or {}),
        json.dumps(infrastructure_config or {}),
        jrs_score, bec_integrity,
    ))

    conn.commit()
    conn.close()
    print(f"Recorded GRC conditions for {model_id} / {evaluation_id}")


def get_conditions(evaluation_id):
    """Retrieve GRC conditions for an evaluation."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT * FROM grc_conditions WHERE evaluation_id = %s",
        (evaluation_id,)
    )
    result = cur.fetchone()
    conn.close()
    return dict(result) if result else None


def compare_models(model_a, model_b):
    """Determine GRC compatibility between two models.

    Five conditions must hold:
    GRC-1: Same constraint object or COS-comparable equivalent.
    GRC-2: Both satisfied LRP conditions.
    GRC-3: Same or formally equivalent evaluation conditions.
    GRC-4: Both JRS scores above minimum threshold.
    GRC-5: Both BEC chains intact (integrity 1.0).
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get most recent GRC records for each model
    cur.execute("""
        SELECT * FROM grc_conditions WHERE model_id = %s
        ORDER BY recorded_at DESC LIMIT 1
    """, (model_a,))
    cond_a = cur.fetchone()

    cur.execute("""
        SELECT * FROM grc_conditions WHERE model_id = %s
        ORDER BY recorded_at DESC LIMIT 1
    """, (model_b,))
    cond_b = cur.fetchone()

    if not cond_a or not cond_b:
        result = {
            "model_a": model_a, "model_b": model_b,
            "compatible": False,
            "reason": "Missing GRC conditions for one or both models.",
            "grc1": False, "grc2": False, "grc3": False, "grc4": False, "grc5": False,
        }
        conn.close()
        return result

    # GRC-1: Same or comparable constraint
    grc1 = (cond_a["constraint_id"] == cond_b["constraint_id"]
            and cond_a["constraint_id"] is not None)

    # GRC-2: Both LRP satisfied (score >= 1.0)
    lrp_a = cond_a.get("lrp_score") or 0.0
    lrp_b = cond_b.get("lrp_score") or 0.0
    grc2 = (lrp_a >= 1.0 and lrp_b >= 1.0)

    # GRC-3: Same evaluation conditions (temperature config match)
    grc3 = (cond_a["temperature_config"] == cond_b["temperature_config"])

    # GRC-4: Both JRS above threshold
    jrs_a = cond_a.get("jrs_score") or 0.0
    jrs_b = cond_b.get("jrs_score") or 0.0
    grc4 = (jrs_a >= JRS_MIN_THRESHOLD and jrs_b >= JRS_MIN_THRESHOLD)

    # GRC-5: Both BEC integrity = 1.0
    bec_a = cond_a.get("bec_integrity") or 0.0
    bec_b = cond_b.get("bec_integrity") or 0.0
    grc5 = (bec_a >= 1.0 and bec_b >= 1.0)

    compatible = all([grc1, grc2, grc3, grc4, grc5])

    reasons = []
    if not grc1:
        reasons.append("Different or missing constraint objects")
    if not grc2:
        reasons.append("LRP not satisfied for both")
    if not grc3:
        reasons.append("Evaluation conditions differ")
    if not grc4:
        reasons.append("JRS below threshold for one or both")
    if not grc5:
        reasons.append("BEC integrity below 1.0 for one or both")

    reason = ". ".join(reasons) if reasons else "All five GRC conditions satisfied"

    # Log the comparison
    cur.execute("""
        INSERT INTO grc_compatibility_log
            (model_a, model_b, compatible, grc1_met, grc2_met,
             grc3_met, grc4_met, grc5_met, reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (model_a, model_b, compatible, grc1, grc2, grc3, grc4, grc5, reason))

    conn.commit()
    conn.close()

    return {
        "model_a": model_a, "model_b": model_b,
        "compatible": compatible,
        "compatibility_score": 1.0 if compatible else 0.0,
        "grc1_same_constraint": grc1,
        "grc2_lrp_satisfied": grc2,
        "grc3_same_conditions": grc3,
        "grc4_jrs_above_threshold": grc4,
        "grc5_bec_intact": grc5,
        "reason": reason,
    }


def classify_csas(csas_id, model_a, model_b, csas_score=None):
    """Classify CSAS degradation as governance failure or structural divergence.

    Per the Comparability Lemma: CSAS degradation is only classifiable as
    governance failure when GRC compatibility is confirmed.
    """
    comparison = compare_models(model_a, model_b)

    if comparison["compatible"]:
        classification = "governance_failure"
    else:
        classification = "structural_divergence"

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO grc_classifications
            (csas_id, model_a, model_b, grc_compatible, classification, csas_score)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (csas_id, model_a, model_b, comparison["compatible"],
          classification, csas_score))

    conn.commit()
    conn.close()

    return {
        "csas_id": csas_id,
        "model_a": model_a,
        "model_b": model_b,
        "grc_compatible": comparison["compatible"],
        "classification": classification,
        "csas_score": csas_score,
    }


def main():
    parser = argparse.ArgumentParser(description="GRC Runner -- Governance Reference Conditions")
    parser.add_argument("--record", action="store_true", help="Record GRC conditions")
    parser.add_argument("--compare", nargs=2, metavar=("MODEL_A", "MODEL_B"), help="Compare two models")
    parser.add_argument("--classify", type=str, help="Classify CSAS degradation")
    parser.add_argument("--conditions", type=str, help="Get conditions for evaluation")
    parser.add_argument("--model", type=str)
    parser.add_argument("--model-a", type=str)
    parser.add_argument("--model-b", type=str)
    parser.add_argument("--evaluation", type=str)
    parser.add_argument("--constraint", type=str)
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.record:
        if not args.model or not args.evaluation:
            print("Error: --model and --evaluation required")
            sys.exit(1)
        record_conditions(
            model_id=args.model,
            evaluation_id=args.evaluation,
            constraint_id=args.constraint,
            dry_run=args.dry_run,
        )

    elif args.compare:
        result = compare_models(args.compare[0], args.compare[1])
        print(json.dumps(result, indent=2, default=str))

    elif args.classify:
        if not args.model_a or not args.model_b:
            print("Error: --model-a and --model-b required")
            sys.exit(1)
        result = classify_csas(args.classify, args.model_a, args.model_b)
        print(json.dumps(result, indent=2, default=str))

    elif args.conditions:
        result = get_conditions(args.conditions)
        if result:
            print(json.dumps(result, indent=2, default=str))
        else:
            print("No conditions found")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
