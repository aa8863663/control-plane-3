"""
BEC Runner -- Blockchain Evidence Chain operations.
Framework F28: Cryptographic integrity for MTCP evaluation records.

Usage:
    python bec_runner.py --verify --chain-id main
    python bec_runner.py --append '{"bis_score": 87.3, "grade": "B"}' --model-id gpt-4o --eval-type bis
    python bec_runner.py --status
    python bec_runner.py --init --chain-id main
"""

import os
import sys
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Load .env if available
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

import psycopg2
import psycopg2.extras


DATABASE_URL = os.environ.get("DATABASE_URL", "")

NULL_HASH = "0" * 64


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def compute_record_hash(record_id, chain_id, sequence_number, previous_hash,
                        model_id, evaluation_type, evaluation_data,
                        timestamp, evaluator_id):
    """Compute SHA-256 hash of all record fields with pipe delimiter."""
    # Normalize evaluation_data to compact JSON string
    if isinstance(evaluation_data, dict):
        eval_data_str = json.dumps(evaluation_data, separators=(",", ":"), sort_keys=True)
    else:
        eval_data_str = str(evaluation_data)

    # Normalize timestamp -- always include UTC timezone
    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        ts_str = timestamp.isoformat()
    else:
        ts_str = str(timestamp)

    payload = "|".join([
        str(record_id),
        str(chain_id),
        str(sequence_number),
        str(previous_hash),
        str(model_id),
        str(evaluation_type),
        eval_data_str,
        ts_str,
        str(evaluator_id),
    ])

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def init_chain(chain_id, dry_run=False):
    """Initialize a new chain with a genesis record."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Check if chain already exists
    cur.execute("SELECT chain_id FROM bec_chains WHERE chain_id = %s", (chain_id,))
    if cur.fetchone():
        print(f"Chain '{chain_id}' already exists.")
        conn.close()
        return False

    now = datetime.now(timezone.utc)
    sequence_number = 1
    model_id = "system"
    evaluation_type = "genesis"
    evaluation_data = {
        "chain_created": now.isoformat(),
        "purpose": f"MTCP BEC chain: {chain_id}",
        "framework": "F28",
    }
    evaluator_id = "mtcp_system"

    # For genesis, we use a placeholder record_id (will be replaced by actual serial)
    # Compute hash with placeholder, then insert, then update with real id
    # Actually, use sequence_number as the stable identifier in hash computation
    record_hash = compute_record_hash(
        sequence_number, chain_id, sequence_number, NULL_HASH,
        model_id, evaluation_type, evaluation_data,
        now, evaluator_id
    )

    if dry_run:
        print(f"[DRY RUN] Would create chain '{chain_id}' with genesis hash: {record_hash}")
        conn.close()
        return True

    try:
        cur.execute("""
            INSERT INTO bec_records
            (chain_id, sequence_number, previous_hash, model_id,
             evaluation_type, evaluation_data, timestamp, evaluator_id, record_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            chain_id, sequence_number, NULL_HASH, model_id,
            evaluation_type, json.dumps(evaluation_data, separators=(",", ":"), sort_keys=True),
            now, evaluator_id, record_hash
        ))

        cur.execute("""
            INSERT INTO bec_chains (chain_id, genesis_hash, current_length, last_verified, integrity_score)
            VALUES (%s, %s, %s, %s, %s)
        """, (chain_id, record_hash, 1, now, 1.0))

        conn.commit()
        print(f"Chain '{chain_id}' initialized. Genesis hash: {record_hash}")
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error initializing chain: {e}")
        return False
    finally:
        conn.close()


def append_record(chain_id, model_id, evaluation_type, evaluation_data,
                  evaluator_id="mtcp_system", dry_run=False):
    """Append a new record to the chain."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get the last record in the chain
    cur.execute("""
        SELECT sequence_number, record_hash
        FROM bec_records
        WHERE chain_id = %s
        ORDER BY sequence_number DESC
        LIMIT 1
    """, (chain_id,))
    last_record = cur.fetchone()

    if not last_record:
        print(f"Chain '{chain_id}' does not exist. Initialize it first with --init.")
        conn.close()
        return False

    new_sequence = last_record["sequence_number"] + 1
    previous_hash = last_record["record_hash"]
    now = datetime.now(timezone.utc)

    # Parse evaluation_data if string
    if isinstance(evaluation_data, str):
        evaluation_data = json.loads(evaluation_data)

    record_hash = compute_record_hash(
        new_sequence, chain_id, new_sequence, previous_hash,
        model_id, evaluation_type, evaluation_data,
        now, evaluator_id
    )

    if dry_run:
        print(f"[DRY RUN] Would append to chain '{chain_id}':")
        print(f"  Sequence: {new_sequence}")
        print(f"  Model: {model_id}")
        print(f"  Type: {evaluation_type}")
        print(f"  Previous hash: {previous_hash[:16]}...")
        print(f"  Record hash: {record_hash}")
        conn.close()
        return True

    try:
        cur.execute("""
            INSERT INTO bec_records
            (chain_id, sequence_number, previous_hash, model_id,
             evaluation_type, evaluation_data, timestamp, evaluator_id, record_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            chain_id, new_sequence, previous_hash, model_id,
            evaluation_type, json.dumps(evaluation_data, separators=(",", ":"), sort_keys=True),
            now, evaluator_id, record_hash
        ))

        cur.execute("""
            UPDATE bec_chains
            SET current_length = %s
            WHERE chain_id = %s
        """, (new_sequence, chain_id))

        conn.commit()
        print(f"Record appended to chain '{chain_id}'. Sequence: {new_sequence}. Hash: {record_hash}")
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error appending record: {e}")
        return False
    finally:
        conn.close()


def verify_chain(chain_id):
    """Verify the integrity of a chain. Returns integrity score."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get all records in order
    cur.execute("""
        SELECT id, chain_id, sequence_number, previous_hash, model_id,
               evaluation_type, evaluation_data, timestamp, evaluator_id, record_hash
        FROM bec_records
        WHERE chain_id = %s
        ORDER BY sequence_number ASC
    """, (chain_id,))
    records = cur.fetchall()

    if not records:
        print(f"Chain '{chain_id}' not found or empty.")
        conn.close()
        return None

    total = len(records)
    valid = 0
    first_invalid = None

    for i, record in enumerate(records):
        # Step 1: Recompute hash
        recomputed = compute_record_hash(
            record["sequence_number"],
            record["chain_id"],
            record["sequence_number"],
            record["previous_hash"],
            record["model_id"],
            record["evaluation_type"],
            record["evaluation_data"],
            record["timestamp"],
            record["evaluator_id"],
        )

        if recomputed != record["record_hash"]:
            if first_invalid is None:
                first_invalid = record["sequence_number"]
            print(f"  FAIL [seq {record['sequence_number']}]: Hash mismatch (recomputed vs stored)")
            continue

        # Step 2: Verify chain linkage
        if i == 0:
            if record["previous_hash"] != NULL_HASH:
                if first_invalid is None:
                    first_invalid = record["sequence_number"]
                print(f"  FAIL [seq {record['sequence_number']}]: Genesis record has non-null previous_hash")
                continue
        else:
            expected_prev = records[i - 1]["record_hash"]
            if record["previous_hash"] != expected_prev:
                if first_invalid is None:
                    first_invalid = record["sequence_number"]
                print(f"  FAIL [seq {record['sequence_number']}]: previous_hash does not match predecessor")
                continue

        # Step 3: Continuity check
        expected_seq = i + 1
        if record["sequence_number"] != expected_seq:
            if first_invalid is None:
                first_invalid = record["sequence_number"]
            print(f"  FAIL [seq {record['sequence_number']}]: Expected sequence {expected_seq}")
            continue

        valid += 1

    integrity_score = valid / total if total > 0 else 0.0
    now = datetime.now(timezone.utc)

    # Record the verification
    try:
        cur.execute("""
            INSERT INTO bec_verifications
            (chain_id, verified_at, records_checked, records_valid,
             integrity_score, first_invalid_sequence, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            chain_id, now, total, valid, integrity_score, first_invalid,
            "Automated verification via bec_runner.py"
        ))

        cur.execute("""
            UPDATE bec_chains
            SET last_verified = %s, integrity_score = %s
            WHERE chain_id = %s
        """, (now, integrity_score, chain_id))

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Warning: Could not record verification result: {e}")

    conn.close()

    # Report
    status = "INTACT" if integrity_score == 1.0 else "COMPROMISED" if integrity_score >= 0.95 else "BROKEN"
    print(f"\nChain: {chain_id}")
    print(f"Records checked: {total}")
    print(f"Records valid: {valid}")
    print(f"Integrity score: {integrity_score:.4f}")
    print(f"Status: {status}")
    if first_invalid:
        print(f"First invalid sequence: {first_invalid}")

    return integrity_score


def get_status():
    """List all chains with their integrity scores."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT chain_id, genesis_hash, current_length, last_verified,
               integrity_score, created_at
        FROM bec_chains
        ORDER BY created_at ASC
    """)
    chains = cur.fetchall()
    conn.close()

    if not chains:
        print("No BEC chains found.")
        return []

    print(f"{'Chain ID':<20} {'Length':<8} {'Integrity':<12} {'Last Verified':<22} {'Status'}")
    print("-" * 80)
    for chain in chains:
        score = chain["integrity_score"] or 0.0
        status = "INTACT" if score == 1.0 else "COMPROMISED" if score >= 0.95 else "BROKEN"
        last_v = str(chain["last_verified"])[:19] if chain["last_verified"] else "Never"
        print(f"{chain['chain_id']:<20} {chain['current_length']:<8} {score:<12.4f} {last_v:<22} {status}")

    return chains


def main():
    parser = argparse.ArgumentParser(description="BEC Runner -- Blockchain Evidence Chain operations")
    parser.add_argument("--chain-id", default="main", help="Chain identifier (default: main)")
    parser.add_argument("--verify", action="store_true", help="Verify chain integrity")
    parser.add_argument("--append", type=str, help="Append a record (JSON evaluation data)")
    parser.add_argument("--model-id", type=str, default="unknown", help="Model ID for append")
    parser.add_argument("--eval-type", type=str, default="bis", help="Evaluation type (bis, csas, tds, etc.)")
    parser.add_argument("--evaluator-id", type=str, default="mtcp_system", help="Evaluator ID")
    parser.add_argument("--init", action="store_true", help="Initialize a new chain")
    parser.add_argument("--status", action="store_true", help="Show status of all chains")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no database writes)")

    args = parser.parse_args()

    if args.status:
        get_status()
    elif args.init:
        init_chain(args.chain_id, dry_run=args.dry_run)
    elif args.verify:
        verify_chain(args.chain_id)
    elif args.append:
        append_record(
            chain_id=args.chain_id,
            model_id=args.model_id,
            evaluation_type=args.eval_type,
            evaluation_data=args.append,
            evaluator_id=args.evaluator_id,
            dry_run=args.dry_run,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
