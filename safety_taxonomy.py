"""
Safety Taxonomy -- Classify MTCP probes by safety relevance tier.
MAFS Phase 1: Makes the dataset legible to safety researchers.

Tier 1: Directly safety critical.
Tier 2: Governance critical.
Tier 3: Operational.

Usage:
    python safety_taxonomy.py --classify-all
    python safety_taxonomy.py --probe <probe_id>
    python safety_taxonomy.py --summary
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

# Safety tier classification rules based on constraint type
TIER_RULES = {
    1: {
        "label": "Directly Safety Critical",
        "constraint_types": ["content_safety", "harm_prevention", "bias_mitigation",
                             "privacy", "deception_prevention"],
        "vectors": ["CG", "CONT"],
    },
    2: {
        "label": "Governance Critical",
        "constraint_types": ["format_compliance", "domain_restriction", "scope_limitation",
                             "regulatory", "authority"],
        "vectors": ["NCA", "SFC", "IDL", "FORM", "DOM", "SCOPE"],
    },
    3: {
        "label": "Operational",
        "constraint_types": ["language", "style", "persona", "length", "tone"],
        "vectors": ["LANG"],
    },
}


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def classify_probe(probe_id, constraint_type=None, vector=None):
    """Classify a single probe by safety tier."""
    # Determine tier based on vector and constraint type
    for tier, rules in TIER_RULES.items():
        if vector and vector in rules["vectors"]:
            return tier, rules["label"]
        if constraint_type and constraint_type in rules["constraint_types"]:
            return tier, rules["label"]

    # Default to Tier 3 if unclassifiable
    return 3, "Operational"


def classify_all(dry_run=False):
    """Classify all probes in the evaluation database."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get distinct probes from results table
    cur.execute("""
        SELECT DISTINCT res.probe_id
        FROM results res
        WHERE res.probe_id IS NOT NULL
        ORDER BY res.probe_id
    """)
    raw_probes = cur.fetchall()

    if raw_probes:
        probes = []
        for row in raw_probes:
            pid = row["probe_id"]
            vector = pid.split("-")[0] if "-" in pid else None
            probes.append({
                "probe_id": pid,
                "constraint_type": None,
                "vector": vector,
            })
    else:
        # Fall back to generating from known probe structure
        vectors = ["CG", "NCA", "SFC", "IDL", "LANG"]
        probes = []
        for v in vectors:
            for i in range(1, 107):
                probes.append({
                    "probe_id": f"{v}-{i:03d}",
                    "constraint_type": None,
                    "vector": v,
                })

    classified = 0
    tier_counts = {1: 0, 2: 0, 3: 0}

    for probe in probes:
        probe_id = probe["probe_id"]
        vector = probe.get("vector")
        constraint_type = probe.get("constraint_type")

        tier, label = classify_probe(probe_id, constraint_type, vector)
        tier_counts[tier] += 1

        if not dry_run:
            cur.execute("""
                INSERT INTO safety_taxonomy (probe_id, safety_tier, tier_label, constraint_type)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (probe_id) DO UPDATE
                SET safety_tier = EXCLUDED.safety_tier,
                    tier_label = EXCLUDED.tier_label
            """, (probe_id, tier, label, constraint_type))

        classified += 1

    if not dry_run:
        conn.commit()

    conn.close()

    return {
        "total_classified": classified,
        "tier_1_safety_critical": tier_counts[1],
        "tier_2_governance_critical": tier_counts[2],
        "tier_3_operational": tier_counts[3],
    }


def get_summary():
    """Get classification summary."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT safety_tier, tier_label, COUNT(*) as count
        FROM safety_taxonomy
        GROUP BY safety_tier, tier_label
        ORDER BY safety_tier
    """)
    results = cur.fetchall()
    conn.close()

    if not results:
        return {"status": "No classifications yet. Run --classify-all first."}

    return {
        "tiers": [dict(r) for r in results],
        "total": sum(r["count"] for r in results),
    }


def main():
    parser = argparse.ArgumentParser(description="Safety Taxonomy Classifier")
    parser.add_argument("--classify-all", action="store_true")
    parser.add_argument("--probe", type=str)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.classify_all:
        print("Classifying all probes by safety tier...")
        result = classify_all(dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
    elif args.probe:
        tier, label = classify_probe(args.probe)
        print(json.dumps({"probe_id": args.probe, "safety_tier": tier, "tier_label": label}, indent=2))
    elif args.summary:
        result = get_summary()
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
