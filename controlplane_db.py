#!/usr/bin/env python3
"""
Control-Plane-3 SQLite Persistence System
==========================================

Single-file database manager for benchmark results.

Usage:
    # Initialize database
    python controlplane_db.py init

    # Import existing results
    python controlplane_db.py import --dir .

    # Query recent runs
    python controlplane_db.py query --latest 5

    # Query specific run
    python controlplane_db.py query --run <run_id>

    # Query by temperature
    python controlplane_db.py query --by-temp
"""
import argparse
import csv
import json
import re
import sqlite3
import sys
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from contextlib import contextmanager
import uuid as uuid_lib

# ============================================================================
# CONFIGURATION
# ============================================================================

PASS_OUTCOMES = {"COMPLETED"}
FAIL_OUTCOMES = {"SAFETY_HARD_STOP"}

# ============================================================================
# SCHEMA DEFINITIONS
# ============================================================================

CREATE_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    dataset TEXT,
    temperature REAL,
    runs_requested INTEGER,
    manifest_run_uuid TEXT,
    dataset_sha256 TEXT,
    script_sha256 TEXT,
    python_version TEXT,
    notes TEXT
);
"""

CREATE_RESULTS_TABLE = """
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    probe_id TEXT,
    batch_run_id INTEGER,
    t1 INTEGER,
    t2 INTEGER,
    t3 INTEGER,
    outcome TEXT,
    recovery_latency INTEGER,
    raw_path TEXT,
    csv_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
"""

CREATE_ARTIFACTS_TABLE = """
CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
"""

CREATE_RESULTS_RUN_ID_INDEX = """
CREATE INDEX IF NOT EXISTS idx_results_run_id ON results(run_id);
"""

CREATE_RESULTS_PROBE_ID_INDEX = """
CREATE INDEX IF NOT EXISTS idx_results_probe_id ON results(probe_id);
"""

CREATE_ARTIFACTS_RUN_ID_INDEX = """
CREATE INDEX IF NOT EXISTS idx_artifacts_run_id ON artifacts(run_id);
"""

ALL_SCHEMAS = [
    CREATE_RUNS_TABLE,
    CREATE_RESULTS_TABLE,
    CREATE_ARTIFACTS_TABLE,
    CREATE_RESULTS_RUN_ID_INDEX,
    CREATE_RESULTS_PROBE_ID_INDEX,
    CREATE_ARTIFACTS_RUN_ID_INDEX,
]

# ============================================================================
# DATABASE CONNECTION HELPERS
# ============================================================================

@contextmanager
def get_connection(db_path: str):
    """Context manager for database connections."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

def insert_run(
    conn: sqlite3.Connection,
    run_id: str,
    temperature: float,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    dataset: Optional[str] = None,
    runs_requested: Optional[int] = None,
    manifest_run_uuid: Optional[str] = None,
    dataset_sha256: Optional[str] = None,
    script_sha256: Optional[str] = None,
    python_version: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Insert a new run record."""
    created_at = datetime.utcnow().isoformat()

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO runs (
            id, created_at, provider, model, dataset, temperature,
            runs_requested, manifest_run_uuid, dataset_sha256,
            script_sha256, python_version, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id, created_at, provider, model, dataset, temperature,
            runs_requested, manifest_run_uuid, dataset_sha256,
            script_sha256, python_version, notes,
        ),
    )
    return run_id

def insert_result(
    conn: sqlite3.Connection,
    run_id: str,
    csv_path: str,
    probe_id: Optional[str] = None,
    batch_run_id: Optional[int] = None,
    t1: Optional[int] = None,
    t2: Optional[int] = None,
    t3: Optional[int] = None,
    outcome: Optional[str] = None,
    recovery_latency: Optional[int] = None,
    raw_path: Optional[str] = None,
) -> int:
    """Insert a result row."""
    created_at = datetime.utcnow().isoformat()

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO results (
            run_id, probe_id, batch_run_id, t1, t2, t3,
            outcome, recovery_latency, raw_path, csv_path, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id, probe_id, batch_run_id, t1, t2, t3,
            outcome, recovery_latency, raw_path, csv_path, created_at,
        ),
    )
    return cursor.lastrowid

def insert_artifact(
    conn: sqlite3.Connection,
    run_id: str,
    kind: str,
    path: str,
    sha256: Optional[str] = None,
) -> int:
    """Insert an artifact reference."""
    created_at = datetime.utcnow().isoformat()

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO artifacts (run_id, kind, path, sha256, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (run_id, kind, path, sha256, created_at),
    )
    return cursor.lastrowid

def check_csv_already_imported(conn: sqlite3.Connection, csv_path: str) -> bool:
    """Check if a CSV file has already been imported."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM results WHERE csv_path = ? LIMIT 1",
        (csv_path,)
    )
    return cursor.fetchone() is not None

def get_recent_runs(conn: sqlite3.Connection, limit: int = 10) -> List[Dict[str, Any]]:
    """Get the most recent runs."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, created_at, provider, model, dataset, temperature, runs_requested
        FROM runs
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [dict(row) for row in cursor.fetchall()]

def get_run_by_id(conn: sqlite3.Connection, run_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific run by ID."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
    row = cursor.fetchone()
    return dict(row) if row else None

def get_run_stats(conn: sqlite3.Connection, run_id: str) -> Dict[str, Any]:
    """Get summary statistics for a specific run."""
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            outcome,
            COUNT(*) as count
        FROM results
        WHERE run_id = ?
        GROUP BY outcome
        """,
        (run_id,),
    )
    outcome_counts = {row['outcome']: row['count'] for row in cursor.fetchall()}

    cursor.execute(
        """
        SELECT
            COUNT(*) as total_count,
            AVG(recovery_latency) as avg_recovery_latency,
            COUNT(DISTINCT probe_id) as unique_probes
        FROM results
        WHERE run_id = ?
        """,
        (run_id,),
    )
    stats = dict(cursor.fetchone())

    pass_count = sum(outcome_counts.get(outcome, 0) for outcome in PASS_OUTCOMES)
    fail_count = sum(outcome_counts.get(outcome, 0) for outcome in FAIL_OUTCOMES)
    total = stats['total_count']
    other_count = total - pass_count - fail_count
    pass_rate = (pass_count / total * 100) if total > 0 else 0.0

    return {
        'outcome_counts': outcome_counts,
        'total_count': total,
        'pass_count': pass_count,
        'fail_count': fail_count,
        'other_count': other_count,
        'unique_probes': stats['unique_probes'],
        'avg_recovery_latency': stats['avg_recovery_latency'],
        'pass_rate': pass_rate,
    }

def get_stats_by_temperature(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Get aggregated statistics grouped by temperature."""
    cursor = conn.cursor()

    # Add token aggregates per temperature (schema-aware)
    cursor.execute("PRAGMA table_info(results)")
    cols = {row["name"] for row in cursor.fetchall()}

    if "total_tokens" in cols:
        token_expr = "res.total_tokens"
    elif "tokens" in cols:
        token_expr = "res.tokens"
    elif "token_count" in cols:
        token_expr = "res.token_count"
    elif "tokens_total" in cols:
        token_expr = "res.tokens_total"
    elif "prompt_tokens" in cols and "completion_tokens" in cols:
        token_expr = "(COALESCE(res.prompt_tokens,0) + COALESCE(res.completion_tokens,0))"
    else:
        token_expr = "NULL"

    cursor.execute(f"""
        SELECT r.temperature,
               COUNT(res.id) as total_rows,
               SUM({token_expr}) as sum_tokens,
               AVG({token_expr}) as avg_tokens
        FROM runs r
        LEFT JOIN results res ON r.id = res.run_id
        GROUP BY r.temperature
    """)
    token_map = {row["temperature"]: dict(row) for row in cursor.fetchall()}


    cursor.execute(
        """
        SELECT
            r.temperature,
            COUNT(DISTINCT r.id) as num_runs,
            COUNT(res.id) as total_results,
            res.outcome,
            COUNT(res.outcome) as outcome_count,
            AVG(res.recovery_latency) as avg_recovery_latency
        FROM runs r
        LEFT JOIN results res ON r.id = res.run_id
        GROUP BY r.temperature, res.outcome
        ORDER BY r.temperature
        """
    )

    temp_data = {}
    for row in cursor.fetchall():
        temp = row['temperature']
        tok = token_map.get(temp, {})
        sum_tokens = tok.get("sum_tokens") or 0
        avg_tokens = tok.get("avg_tokens")

        if temp not in temp_data:
            temp_data[temp] = {
                'num_runs': row['num_runs'],
                'total_results': 0,
                'outcomes': {},
                'avg_recovery_latency': row['avg_recovery_latency'],
            }

        outcome = row['outcome']
        count = row['outcome_count']
        if outcome:
            temp_data[temp]['outcomes'][outcome] = count
            temp_data[temp]['total_results'] += count

    results = []
    for temp in sorted(temp_data.keys()):
        data = temp_data[temp]
        tok = token_map.get(temp, {}) if 'token_map' in locals() else {}
        sum_tokens = tok.get('sum_tokens') or 0
        avg_tokens = tok.get('avg_tokens')
        outcomes = data['outcomes']

        pass_count = sum(outcomes.get(outcome, 0) for outcome in PASS_OUTCOMES)
        fail_count = sum(outcomes.get(outcome, 0) for outcome in FAIL_OUTCOMES)
        total = data['total_results']
        other_count = total - pass_count - fail_count
        pass_rate = (pass_count / total * 100) if total > 0 else 0.0

        results.append({
            'temperature': temp,
            'num_runs': data['num_runs'],
            'total_results': total,
            'pass_count': pass_count,
            'fail_count': fail_count,
            'other_count': other_count,
            'pass_rate': pass_rate,
            "sum_tokens": sum_tokens,
            "avg_tokens": avg_tokens,
            'avg_recovery_latency': data['avg_recovery_latency'],
        })

    return results

# ============================================================================
# IMPORT UTILITIES
# ============================================================================

def extract_temperature_from_filename(filename: str) -> Optional[float]:
    """Extract temperature from filename like 'temp_0.5_results.csv'."""
    match = re.search(r'temp_([0-9.]+)_results', filename)
    if match:
        return float(match.group(1))
    return None

def load_manifest(directory: Path) -> Dict[str, Any]:
    """Load run_manifest.json if it exists."""
    manifest_path = directory / "run_manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load manifest: {e}")
    return {}

def compute_file_sha256(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def import_csv_file(
    conn: sqlite3.Connection,
    csv_path: Path,
    run_id: str,
    raw_json_path: Optional[Path] = None
 ): 
    """Import a single CSV file into the results table."""
    print(f" Importing: {csv_path.name}")
    
    raw_path_str = str(raw_json_path) if raw_json_path and raw_json_path.exists() else None

    count = 0
    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            probe_id = row.get("probe_id") or row.get("Probe ID")
            batch_run_id = row.get("run_id") or row.get("Run ID")
            t1 = row.get("t1") or row.get("T1")
            t2 = row.get("t2") or row.get("T2")
            t3 = row.get("t3") or row.get("T3")
            passed = row.get("passed") or row.get("Passed")

            outcome = row.get("outcome") or row.get("Outcome")
            # If CSV doesn't have "outcome", derive it from "passed"
            if (outcome is None or outcome == "") and passed is not None:
                p = str(passed).strip().lower()
                is_pass = p in ("1", "true", "t", "yes", "y", "pass", "passed", "completed")
                outcome = "COMPLETED" if is_pass else "SAFETY_HARD_STOP"

            recovery_latency = row.get("recovery_latency") or row.get("Recovery Latency")

            batch_run_id_int = int(batch_run_id) if batch_run_id and str(batch_run_id).isdigit() else None
            t1_int = int(t1) if t1 and str(t1) in ("0", "1") else None
            t2_int = int(t2) if t2 and str(t2) in ("0", "1") else None
            t3_int = int(t3) if t3 and str(t3) in ("0", "1") else None
            recovery_latency_int = int(float(recovery_latency)) if recovery_latency not in (None, "") else None
            insert_result(
                conn=conn,
                run_id=run_id,
                csv_path=str(csv_path),
                probe_id=probe_id,
                batch_run_id=batch_run_id_int,
                t1=t1_int,
                t2=t2_int,
                t3=t3_int,
                outcome=outcome,
                recovery_latency=recovery_latency_int,
                raw_path=raw_path_str,
            )
            count += 1

    print(f" → Inserted {count} result rows")

def import_artifacts(conn: sqlite3.Connection, run_id: str, directory: Path):
    """Import references to artifact files."""
    artifact_files = {
        'manifest': 'run_manifest.json',
        'hard_stops': 'hard_stops.json',
        'breach_snapshots': 'breach_snapshots.json',
    }

    for kind, filename in artifact_files.items():
        filepath = directory / filename
        if filepath.exists():
            sha256 = compute_file_sha256(filepath)
            insert_artifact(conn, run_id, kind, str(filepath), sha256)
            print(f"  Linked artifact: {filename} ({kind})")

# ============================================================================
# COMMAND HANDLERS
# ============================================================================

def cmd_init(args):
    """Initialize the database."""
    db_path = args.db
    db_file = Path(db_path)

    print(f"Initializing database: {db_file.absolute()}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    print("Creating tables and indexes...")
    for schema in ALL_SCHEMAS:
        cursor.execute(schema)

    conn.commit()
    conn.close()

    print(f"✓ Database initialized successfully!")
    print(f"  Location: {db_file.absolute()}")
    print(f"  Tables: runs, results, artifacts")

def cmd_import(args):
    """Import existing results from directory."""
    db_path = args.db
    directory = Path(args.dir)

    if not directory.exists():
        print(f"Error: Directory not found: {directory}")
        sys.exit(1)

    print("=" * 70)
    print("Control-Plane-3 Result Importer")
    print("=" * 70)

    manifest = load_manifest(directory)
    manifest_run_uuid = manifest.get('uuid') or manifest.get('run_uuid')

    provider = manifest.get('provider')
    model = manifest.get('model')
    runs_requested = manifest.get('runs_count') or manifest.get('runs_requested')
    dataset = manifest.get('dataset')
    dataset_sha256 = manifest.get('dataset_sha256')
    script_sha256 = manifest.get('script_sha256')
    python_version = manifest.get('python_version')

    csv_files = sorted(directory.glob('temp_*_results*.csv'))
    if not csv_files:
        print("\n⚠ No temp_*_results.csv files found!")
        return

    print(f"\nFound {len(csv_files)} CSV file(s) to import:")
    for csv_file in csv_files:
        print(f"  - {csv_file.name}")

    with get_connection(db_path) as conn:
        for csv_path in csv_files:
            temperature = extract_temperature_from_filename(csv_path.name)
            if temperature is None:
                print(f"\n⚠ Skipping {csv_path.name} (could not extract temperature)")
                continue

            print(f"\n--- Processing {csv_path.name} (temp={temperature}) ---")

            if check_csv_already_imported(conn, str(csv_path)):
                print(f"  ⚠ Already imported (skipping)")
                continue

            run_id = str(uuid_lib.uuid4())

            insert_run(
                conn=conn,
                run_id=run_id,
                temperature=temperature,
                provider=provider,
                model=model,
                dataset=dataset,
                runs_requested=runs_requested,
                manifest_run_uuid=manifest_run_uuid,
                dataset_sha256=dataset_sha256,
                script_sha256=script_sha256,
                python_version=python_version,
            )
            print(f"  Created run: {run_id}")

            raw_json_path = directory / csv_path.name.replace('_results.csv', '_results_raw.json')

            import_csv_file(conn, csv_path, run_id, raw_json_path)

            csv_sha256 = compute_file_sha256(csv_path)
            insert_artifact(conn, run_id, 'csv', str(csv_path), csv_sha256)

            if raw_json_path.exists():
                raw_sha256 = compute_file_sha256(raw_json_path)
                insert_artifact(conn, run_id, 'raw_json', str(raw_json_path), raw_sha256)
                print(f"  Linked raw JSON: {raw_json_path.name}")

            import_artifacts(conn, run_id, directory)

    print("\n" + "=" * 70)
    print("✓ Import complete!")
    print("=" * 70)

def cmd_query(args):
    """Query the database."""
    db_path = args.db

    with get_connection(db_path) as conn:
        if args.latest:
            runs = get_recent_runs(conn, args.latest)

            if not runs:
                print("No runs found in database.")
                return

            print(f"\n{'='*80}")
            print(f"Recent Runs (last {args.latest})")
            print(f"{'='*80}\n")

            for i, run in enumerate(runs, 1):
                print(f"{i}. Run ID: {run['id']}")
                print(f"   Created: {run['created_at']}")
                print(f"   Model: {run.get('provider', 'N/A')}/{run.get('model', 'N/A')}")
                print(f"   Temperature: {run.get('temperature', 'N/A')}")
                print(f"   Dataset: {run.get('dataset', 'N/A')}")
                print(f"   Runs Requested: {run.get('runs_requested', 'N/A')}")
                print()

        elif args.run:
            run_id = args.run
            run = get_run_by_id(conn, run_id)

            if not run:
                print(f"Run not found: {run_id}")
                return

            stats = get_run_stats(conn, run_id)

            print(f"\n{'='*80}")
            print(f"Run Details: {run_id}")
            print(f"{'='*80}\n")

            print("Metadata:")
            print(f"  Created: {run['created_at']}")
            print(f"  Provider: {run.get('provider', 'N/A')}")
            print(f"  Model: {run.get('model', 'N/A')}")
            print(f"  Temperature: {run.get('temperature', 'N/A')}")
            print(f"  Dataset: {run.get('dataset', 'N/A')}")
            print(f"  Runs Requested: {run.get('runs_requested', 'N/A')}")

            print("\nResult Statistics:")
            print(f"  Total Results: {stats['total_count']}")
            print(f"  Unique Probes: {stats['unique_probes']}")
            print(f"  Pass Count: {stats['pass_count']}")
            print(f"  Fail Count: {stats['fail_count']}")
            print(f"  Other Count: {stats['other_count']}")
            print(f"  Pass Rate: {stats['pass_rate']:.1f}%")

            if stats['avg_recovery_latency'] is not None:
                print(f"  Avg Recovery Latency: {stats['avg_recovery_latency']:.2f}ms")

            print("\nOutcome Breakdown:")
            for outcome, count in stats['outcome_counts'].items():
                print(f"  {outcome}: {count}")
            print()

        elif args.by_temp:
            stats = get_stats_by_temperature(conn)

            if not stats:
                print("No data found in database.")
                return

            print(f"\n{'='*80}")
            print("Statistics by Temperature")
            print(f"{'='*80}\n")

            print(f"{'Temp':<8} {'Runs':<6} {'Total':<8} {'Pass':<8} {'Fail':<8} {'Other':<8} {'Pass%':<8} {'Avg Latency':<12} {'SumTok':<10} {'AvgTok':<10}")
            print("-" * 90)

            for stat in stats:
                temp = stat['temperature']
                num_runs = stat['num_runs']
                total = stat['total_results']
                pass_count = stat['pass_count']
                fail_count = stat['fail_count']
                other_count = stat['other_count']
                pass_rate = stat['pass_rate']
                avg_latency = stat['avg_recovery_latency']

                latency_str = f"{avg_latency:.1f}ms" if avg_latency else "N/A"

                sumtok = stat.get('sum_tokens', 0) or 0
                avgtok = stat.get('avg_tokens', None)
                avgtok_str = f"{avgtok:.1f}" if isinstance(avgtok, (int, float)) else "N/A"
                print(f"{temp:<8.1f} {stat.get('num_runs', 0):<6} {stat.get('total_results', 0):<8} {stat.get('pass_count', 0):<8} {stat.get('fail_count', 0):<8} {stat.get('other_count', 0):<8} {stat.get('pass_rate', 0):<7.1f}% {str(stat.get('avg_recovery_latency') or 'N/A'):<12} {sumtok:<10} {avgtok_str:<10}")
            print()

        else:
            print("Please specify --latest, --run, or --by-temp")

# ============================================================================
# MAIN CLI
# ============================================================================

def cmd_export(args):
    import zipfile
    import json
    import csv
    import shutil
    from pathlib import Path

    db_path = args.db
    out_path = args.out

    with get_connection(db_path) as conn:
        cur = conn.cursor()

        run_id = args.run
        if args.latest:
            cur.execute("SELECT id FROM runs ORDER BY created_at DESC LIMIT 1")
            row = cur.fetchone()
            if not row:
                print("No runs found.")
                return
            run_id = row["id"]

        if not run_id:
            print("Provide --run <RUN_ID> or --latest")
            return

        cur.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
        run_row = cur.fetchone()
        if not run_row:
            print("Run not found:", run_id)
            return
        run_meta = dict(run_row)

        cur.execute("SELECT * FROM results WHERE run_id = ?", (run_id,))
        rows = [dict(r) for r in cur.fetchall()]

        artifacts = []
        try:
            cur.execute("SELECT kind, path, sha256 FROM artifacts WHERE run_id = ?", (run_id,))
            artifacts = [dict(r) for r in cur.fetchall()]
        except Exception:
            artifacts = []

        stats = get_run_stats(conn, run_id)

    bundle_dir = Path("_bundle_tmp")
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir()
    (bundle_dir / "artifacts").mkdir()

    present = 0
    for a in artifacts:
        try:
            if a.get("path") and Path(a["path"]).exists():
                present += 1
        except Exception:
            pass

    summary = []
    summary.append("# Audit Bundle")
    summary.append(f"Run ID: {run_id}")
    summary.append(f"Created: {run_meta.get('created_at')}")
    summary.append(f"Temp: {run_meta.get('temperature')}")
    pr = stats.get("pass_rate")
    summary.append(f"Pass rate: {pr:.1f}%" if isinstance(pr, (int, float)) else f"Pass rate: {pr}")
    summary.append(f"Total results: {stats.get('total_count')}")
    summary.append(f"Pass: {stats.get('pass_count')}  Fail: {stats.get('fail_count')}")
    summary.append(f"Artifacts on disk: {present}/{len(artifacts)}")
    (bundle_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    (bundle_dir / "run.json").write_text(
        json.dumps({"run": run_meta, "stats": stats, "artifacts": artifacts}, indent=2),
        encoding="utf-8"
    )

    if rows:
        fieldnames = list(rows[0].keys())
        with open(bundle_dir / "results.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
    else:
        (bundle_dir / "results.csv").write_text("", encoding="utf-8")

    for a in artifacts:
        try:
            p = Path(a["path"])
        except Exception:
            continue
        if p.exists() and p.is_file():
            target = bundle_dir / "artifacts" / p.name
            try:
                target.write_bytes(p.read_bytes())
            except Exception:
                pass

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for fp in bundle_dir.rglob("*"):
            if fp.is_file():
                z.write(fp, arcname=str(fp.relative_to(bundle_dir)))

    print("✅ Exported:", out_path)


def main():
    parser = argparse.ArgumentParser(
        description='Control-Plane-3 SQLite Persistence System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python controlplane_db.py init
  python controlplane_db.py import --dir .
  python controlplane_db.py query --latest 5
  python controlplane_db.py query --run <run_id>
  python controlplane_db.py query --by-temp
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    export_parser = subparsers.add_parser('export', help='Export an audit bundle ZIP')

    export_parser.add_argument('--db', default='controlplane.db', help='Database path')

    export_parser.add_argument('--run', metavar='RUN_ID', help='Run ID to export (optional)')

    export_parser.add_argument('--latest', action='store_true', help='Export latest run')

    export_parser.add_argument('--out', default='audit_bundle.zip', help='Output zip filename')

    init_parser = subparsers.add_parser('init', help='Initialize database')
    init_parser.add_argument('--db', default='controlplane.db', help='Database path')

    import_parser = subparsers.add_parser('import', help='Import results')
    import_parser.add_argument('--db', default='controlplane.db', help='Database path')
    import_parser.add_argument('--dir', required=True, help='Directory with result files')

    query_parser = subparsers.add_parser('query', help='Query database')
    query_parser.add_argument('--db', default='controlplane.db', help='Database path')
    query_group = query_parser.add_mutually_exclusive_group()
    query_group.add_argument('--latest', type=int, metavar='N', help='Show last N runs')
    query_group.add_argument('--run', metavar='RUN_ID', help='Show stats for specific run')
    query_group.add_argument('--by-temp', action='store_true', help='Show stats by temperature')
    query_parser.add_argument('--price-per-1k', type=float, default=None, help='Estimate cost using $ per 1k tokens')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == 'init':
        cmd_init(args)
    elif args.command == 'import':
        cmd_import(args)
    elif args.command == 'query':
        cmd_query(args)
    elif args.command == 'export':
        cmd_export(args)
if __name__ == "__main__":
    main()
