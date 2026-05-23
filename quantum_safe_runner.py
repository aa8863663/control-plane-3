"""
Quantum-Safe Runner -- Cryptographic validity and migration operations.
Framework F35: Post-quantum governance evidence.

Migrates BEC hash chain from SHA-256 to BLAKE3.
Validates cryptographic standard of all evidence records.
Tracks harvest-now decrypt-later risk classification.

Usage:
    python quantum_safe_runner.py --status
    python quantum_safe_runner.py --validate --record-type bec --record-id <id>
    python quantum_safe_runner.py --migrate --dry-run
    python quantum_safe_runner.py --migrate
    python quantum_safe_runner.py --report
"""

import os
import sys
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

import psycopg2
import psycopg2.extras

# Try to import blake3; fall back to hashlib sha3_256 as interim
try:
    import blake3
    BLAKE3_AVAILABLE = True
except ImportError:
    BLAKE3_AVAILABLE = False


DATABASE_URL = os.environ.get("DATABASE_URL", "")

VALIDITY_WINDOW_YEARS = 10
CURRENT_STANDARD = "BLAKE3" if BLAKE3_AVAILABLE else "SHA3-256"
CURRENT_ALGORITHM = "blake3" if BLAKE3_AVAILABLE else "sha3_256"

HARVEST_RISK_LEVELS = {
    1: "Gate decisions and deployment records",
    2: "Evaluation scores and BIS records",
    3: "Manifest attestations",
}


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def compute_blake3(data):
    """Compute BLAKE3 hash (or SHA3-256 fallback)."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    if BLAKE3_AVAILABLE:
        return blake3.blake3(data).hexdigest()
    else:
        return hashlib.sha3_256(data).hexdigest()


def compute_sha256(data):
    """Compute SHA-256 hash."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def validate_record(record_type, record_id, dry_run=False):
    """Validate cryptographic standard of a record."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Check current crypto standard
    cur.execute("""
        SELECT * FROM crypto_standard_records
        WHERE record_type = %s AND record_id = %s
        ORDER BY implementation_date DESC LIMIT 1
    """, (record_type, record_id))
    standard = cur.fetchone()

    now = datetime.now(timezone.utc)

    if not standard:
        # No crypto standard recorded -- assume SHA-256 (legacy)
        is_quantum_safe = False
        algorithm = "SHA-256"
        validity_end = now  # Already expired for quantum purposes
    else:
        algorithm = standard["algorithm"]
        impl_date = standard["implementation_date"]
        if hasattr(impl_date, 'tzinfo') and impl_date.tzinfo is None:
            impl_date = impl_date.replace(tzinfo=timezone.utc)
        window_years = standard.get("validity_window_years", VALIDITY_WINDOW_YEARS)
        validity_end = impl_date + timedelta(days=365 * window_years)
        is_quantum_safe = (algorithm in ("BLAKE3", "SHA3-256", "blake3", "sha3_256")
                           and now < validity_end)

    if not dry_run:
        cur.execute("""
            INSERT INTO crypto_validity_log
                (record_type, record_id, crypto_standard, algorithm,
                 validity_start, validity_end, is_quantum_safe)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            record_type, record_id, algorithm, algorithm,
            now, validity_end, is_quantum_safe,
        ))
        conn.commit()

    conn.close()

    return {
        "record_type": record_type,
        "record_id": record_id,
        "algorithm": algorithm,
        "is_quantum_safe": is_quantum_safe,
        "validity_end": validity_end.isoformat(),
        "needs_migration": not is_quantum_safe,
    }


def migrate_records(dry_run=False):
    """Migrate all SHA-256 BEC records to BLAKE3."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Find all BEC records using SHA-256
    cur.execute("""
        SELECT id, chain_id, sequence_number, record_hash, model_id,
               evaluation_type, evaluation_data, timestamp, evaluator_id
        FROM bec_records
        ORDER BY chain_id, sequence_number
    """)
    records = cur.fetchall()

    migrated = 0
    skipped = 0

    for record in records:
        # Check if already migrated
        cur.execute("""
            SELECT id FROM quantum_migration_registry
            WHERE record_type = 'bec' AND record_id = %s AND migration_status = 'complete'
        """, (str(record["id"]),))
        if cur.fetchone():
            skipped += 1
            continue

        # Compute new BLAKE3 hash
        eval_data_str = json.dumps(record["evaluation_data"], separators=(",", ":"), sort_keys=True)
        ts_str = record["timestamp"].isoformat() if record["timestamp"] else ""

        payload = "|".join([
            str(record["id"]),
            str(record["chain_id"]),
            str(record["sequence_number"]),
            str(record["model_id"]),
            str(record["evaluation_type"]),
            eval_data_str,
            ts_str,
            str(record.get("evaluator_id", "mtcp_system")),
        ])

        new_hash = compute_blake3(payload)

        if dry_run:
            print(f"  [DRY RUN] Record {record['id']}: SHA-256 -> {CURRENT_STANDARD}")
            migrated += 1
            continue

        # Log the migration
        cur.execute("""
            INSERT INTO quantum_migration_registry
                (record_type, record_id, original_algorithm, original_hash,
                 new_algorithm, new_hash, migrated_at, migration_status, verified)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            "bec", str(record["id"]), "SHA-256", record["record_hash"],
            CURRENT_STANDARD, new_hash, datetime.now(timezone.utc),
            "complete", True,
        ))

        # Record new crypto standard
        cur.execute("""
            INSERT INTO crypto_standard_records
                (record_type, record_id, crypto_standard, algorithm,
                 validity_window_years, harvest_risk_level)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            "bec", str(record["id"]), CURRENT_STANDARD, CURRENT_ALGORITHM,
            VALIDITY_WINDOW_YEARS, 2,
        ))

        migrated += 1

    if not dry_run:
        conn.commit()

    conn.close()

    return {
        "total_records": len(records),
        "migrated": migrated,
        "skipped": skipped,
        "algorithm": CURRENT_STANDARD,
        "blake3_available": BLAKE3_AVAILABLE,
    }


def generate_report():
    """Generate quantum-safe migration status report."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Count records by migration status
    cur.execute("""
        SELECT migration_status, COUNT(*) as count
        FROM quantum_migration_registry
        GROUP BY migration_status
    """)
    migration_counts = {r["migration_status"]: r["count"] for r in cur.fetchall()}

    # Count records by algorithm
    cur.execute("""
        SELECT algorithm, COUNT(*) as count
        FROM crypto_standard_records
        GROUP BY algorithm
    """)
    algorithm_counts = {r["algorithm"]: r["count"] for r in cur.fetchall()}

    # Count quantum-safe records
    cur.execute("""
        SELECT is_quantum_safe, COUNT(*) as count
        FROM crypto_validity_log
        GROUP BY is_quantum_safe
    """)
    validity_counts = {str(r["is_quantum_safe"]): r["count"] for r in cur.fetchall()}

    # Count BEC records total
    cur.execute("SELECT COUNT(*) as count FROM bec_records")
    bec_total = cur.fetchone()["count"]

    conn.close()

    return {
        "bec_records_total": bec_total,
        "migration_status": migration_counts,
        "algorithms_in_use": algorithm_counts,
        "quantum_safe_status": validity_counts,
        "current_standard": CURRENT_STANDARD,
        "blake3_available": BLAKE3_AVAILABLE,
        "validity_window_years": VALIDITY_WINDOW_YEARS,
    }


def get_status():
    """Get overall quantum-safe status."""
    report = generate_report()
    print(json.dumps(report, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(description="Quantum-Safe Runner")
    parser.add_argument("--status", action="store_true", help="Show overall status")
    parser.add_argument("--validate", action="store_true", help="Validate a record")
    parser.add_argument("--migrate", action="store_true", help="Migrate BEC to BLAKE3")
    parser.add_argument("--report", action="store_true", help="Generate migration report")
    parser.add_argument("--record-type", type=str, default="bec")
    parser.add_argument("--record-id", type=str)
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if args.status:
        get_status()

    elif args.validate:
        if not args.record_id:
            print("Error: --record-id required")
            sys.exit(1)
        result = validate_record(args.record_type, args.record_id, dry_run=args.dry_run)
        print(json.dumps(result, indent=2, default=str))

    elif args.migrate:
        print(f"Migrating BEC records to {CURRENT_STANDARD}...")
        result = migrate_records(dry_run=args.dry_run)
        print(json.dumps(result, indent=2, default=str))

    elif args.report:
        result = generate_report()
        print(json.dumps(result, indent=2, default=str))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
