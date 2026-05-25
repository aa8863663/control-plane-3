#!/usr/bin/env python3
"""
Constraint Manifest Generator -- Portable verified attestation engine.
Framework F30: Constraint Manifest for model deployments.

Usage:
    python manifest_generator.py --model grok-3-mini --context general_enterprise
    python manifest_generator.py --model openai/gpt-4o --context financial_services
    python manifest_generator.py --verify <manifest_id>
    python manifest_generator.py --revoke <manifest_id> --reason score_change
    python manifest_generator.py --model grok-3-mini --context general_enterprise --dry-run
    python manifest_generator.py --model grok-3-mini --context general_enterprise --no-db
"""

import argparse
import hashlib
import hmac
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, date, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass

BASE_DIR = Path(__file__).parent
DATABASE_URL = os.environ.get("DATABASE_URL", "")
MANIFEST_SECRET = os.environ.get("MANIFEST_SECRET", "mtcp-manifest-secret-2026")
TDS_VALIDITY_DAYS = 90
ISSUER = "MTCP Research Programme"


# ============================================================================
# Grading
# ============================================================================

def bis_grade(pct):
    """Assign MTCP letter grade to a percentage score."""
    if pct is None:
        return 'F'
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


# ============================================================================
# Database
# ============================================================================

def get_db():
    """Connect to the database."""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def get_model_scores(model_id):
    """Retrieve current scores for a model from the database."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    scores = {
        "bis_score": None,
        "bis_grade": None,
        "csas_score": None,
        "csas_grade": None,
        "jrs_score": None,
        "tds_status": None,
        "acps_score": None,
        "acps_grade": None,
        "bec_integrity_score": 1.0,
        "bec_chain_id": None,
        "gate_status": None,
        "gate_context": None,
        "regulatory_compliance": None,
    }

    # Get BIS score from runs/results
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE res.outcome = 'COMPLETED') * 100.0 / NULLIF(COUNT(*), 0) AS bis
        FROM runs r
        JOIN results res ON r.id = res.run_id
        WHERE r.model ILIKE %s AND r.dataset = 'probes_500'
    """, (f"%{model_id}%",))
    row = cur.fetchone()
    if row and row['bis']:
        scores['bis_score'] = round(float(row['bis']), 2)
        scores['bis_grade'] = bis_grade(scores['bis_score'])

    # Get CSAS score from csas_scores via boundaries
    cur.execute("""
        SELECT cs.csas, cs.grade FROM csas_scores cs
        JOIN csas_boundaries cb ON cs.boundary_id = cb.id
        WHERE cb.upstream_model ILIKE %s OR cb.downstream_model ILIKE %s
        ORDER BY cs.created_at DESC LIMIT 1
    """, (f"%{model_id}%", f"%{model_id}%"))
    row = cur.fetchone()
    if row:
        scores['csas_score'] = float(row['csas']) if row['csas'] else None
        scores['csas_grade'] = row['grade']

    # Get JRS score
    cur.execute("""
        SELECT jrs_score FROM jrs_evaluations
        ORDER BY created_at DESC LIMIT 1
    """)
    row = cur.fetchone()
    if row and row['jrs_score']:
        scores['jrs_score'] = float(row['jrs_score'])

    # Get TDS status from tds_comparisons
    cur.execute("""
        SELECT drift_class FROM tds_comparisons
        WHERE model ILIKE %s
        ORDER BY evaluated_at DESC LIMIT 1
    """, (f"%{model_id}%",))
    row = cur.fetchone()
    if row:
        scores['tds_status'] = row['drift_class']
    else:
        scores['tds_status'] = 'Stable'

    # Get ACPS score from acps_scores
    cur.execute("""
        SELECT s.acps, s.grade FROM acps_scores s
        JOIN acps_evaluations e ON s.evaluation_id = e.id
        WHERE e.model ILIKE %s
        ORDER BY s.created_at DESC LIMIT 1
    """, (f"%{model_id}%",))
    row = cur.fetchone()
    if row:
        scores['acps_score'] = float(row['acps']) if row['acps'] else None
        scores['acps_grade'] = row['grade']

    # Get BEC chain info
    cur.execute("""
        SELECT chain_id, integrity_score FROM bec_chains
        WHERE chain_id ILIKE %s
        ORDER BY created_at DESC LIMIT 1
    """, (f"%{model_id}%",))
    row = cur.fetchone()
    if row:
        scores['bec_chain_id'] = row['chain_id']
        scores['bec_integrity_score'] = float(row['integrity_score']) if row['integrity_score'] else 1.0

    # Get gate decision
    cur.execute("""
        SELECT decision, deployment_context FROM gate_decisions
        WHERE model_id ILIKE %s
        ORDER BY decided_at DESC LIMIT 1
    """, (f"%{model_id}%",))
    row = cur.fetchone()
    if row:
        scores['gate_status'] = row['decision']
        scores['gate_context'] = row['deployment_context']

    # Get regulatory compliance (regulatory_mappings is not per-model, use general)
    cur.execute("""
        SELECT jurisdiction, regulation_name, deployment_context, required_grade
        FROM regulatory_mappings LIMIT 20
    """)
    rows = cur.fetchall()
    if rows:
        compliance = {}
        for r in rows:
            key = r['jurisdiction']
            if key not in compliance:
                compliance[key] = {
                    "regulation": r['regulation_name'],
                    "context": r['deployment_context'],
                    "required_grade": r['required_grade']
                }
        scores['regulatory_compliance'] = compliance

    conn.close()
    return scores


def get_provider_for_model(model_id):
    """Determine provider from model_id or database."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    # Check if provider is embedded in model_id
    if '/' in model_id:
        return model_id.split('/')[0]

    # Look up from database
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT COALESCE(NULLIF(provider, ''), NULLIF(api_provider, ''), 'unknown') as prov
        FROM runs WHERE model ILIKE %s LIMIT 1
    """, (f"%{model_id}%",))
    row = cur.fetchone()
    conn.close()
    if row:
        return row['prov']
    return 'unknown'


# ============================================================================
# Hash and Signature
# ============================================================================

def compute_manifest_hash(fields):
    """Compute SHA-256 hash of manifest fields using pipe-delimited concatenation."""
    parts = []
    field_order = [
        'manifest_id', 'model_id', 'provider', 'evaluation_date',
        'bis_score', 'bis_grade', 'csas_score', 'csas_grade',
        'jrs_score', 'tds_valid_until', 'tds_status',
        'gate_status', 'gate_context', 'acps_score', 'acps_grade',
        'regulatory_compliance', 'bec_integrity_score', 'bec_chain_id'
    ]
    for key in field_order:
        val = fields.get(key)
        if val is None:
            parts.append("null")
        elif isinstance(val, dict):
            parts.append(json.dumps(val, sort_keys=True))
        else:
            parts.append(str(val))

    payload = "|".join(parts)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def compute_signature(manifest_hash, secret=None):
    """Compute HMAC-SHA256 signature over manifest_hash."""
    if secret is None:
        secret = MANIFEST_SECRET
    return hmac.HMAC(
        secret.encode('utf-8'),
        manifest_hash.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


# ============================================================================
# Manifest Operations
# ============================================================================

def generate_manifest(model_id, context, provider=None, dry_run=False, no_db=False):
    """Generate a Constraint Manifest for a model."""
    evaluation_date = date.today().isoformat()
    tds_valid_until = (date.today() + timedelta(days=TDS_VALIDITY_DAYS)).isoformat()
    manifest_uuid = str(uuid.uuid4())

    if no_db:
        # Use placeholder scores for no-db mode
        scores = {
            "bis_score": 0.0,
            "bis_grade": "F",
            "csas_score": None,
            "csas_grade": None,
            "jrs_score": None,
            "tds_status": "Stable",
            "acps_score": None,
            "acps_grade": None,
            "bec_integrity_score": 1.0,
            "bec_chain_id": None,
            "gate_status": "DENY",
            "gate_context": context,
            "regulatory_compliance": None,
        }
        if provider is None:
            provider = "unknown"
    else:
        scores = get_model_scores(model_id)
        if provider is None:
            provider = get_provider_for_model(model_id)

    # Clean model_id (remove provider prefix if present)
    clean_model = model_id.split('/')[-1] if '/' in model_id else model_id

    # Override gate_context with requested context
    scores['gate_context'] = context

    # Build manifest fields
    fields = {
        "manifest_id": manifest_uuid,
        "model_id": clean_model,
        "provider": provider,
        "evaluation_date": evaluation_date,
        "bis_score": scores['bis_score'],
        "bis_grade": scores['bis_grade'],
        "csas_score": scores['csas_score'],
        "csas_grade": scores['csas_grade'],
        "jrs_score": scores['jrs_score'],
        "tds_valid_until": tds_valid_until,
        "tds_status": scores['tds_status'],
        "gate_status": scores['gate_status'] or "DENY",
        "gate_context": context,
        "acps_score": scores['acps_score'],
        "acps_grade": scores['acps_grade'],
        "regulatory_compliance": scores['regulatory_compliance'],
        "bec_integrity_score": scores['bec_integrity_score'],
        "bec_chain_id": scores['bec_chain_id'],
        "runtime_monitor_enabled": scores.get('runtime_monitor_enabled', False),
        "last_session_coherence_hash": scores.get('last_session_coherence_hash'),
        "permanence_architecture_version": "1.0",
    }

    # Compute hash and signature
    manifest_hash = compute_manifest_hash(fields)
    signature = compute_signature(manifest_hash)

    # Complete manifest
    manifest = {
        **fields,
        "manifest_hash": manifest_hash,
        "issuer": ISSUER,
        "issuer_signature": signature,
    }

    if dry_run:
        print("\n[DRY RUN] Manifest generated (not stored):")
        print(json.dumps(manifest, indent=2, default=str))
        return manifest

    if not no_db:
        # Store in database
        store_manifest(manifest)

    print("\nManifest generated successfully:")
    print(json.dumps(manifest, indent=2, default=str))
    return manifest


def store_manifest(manifest):
    """Store manifest in the database."""
    import psycopg2

    conn = get_db()
    cur = conn.cursor()

    # Insert into manifests table
    cur.execute("""
        INSERT INTO manifests (
            manifest_id, model_id, provider, evaluation_date,
            bis_score, bis_grade, csas_score, csas_grade,
            jrs_score, tds_valid_until, tds_status,
            gate_status, gate_context, acps_score, acps_grade,
            regulatory_compliance, bec_integrity_score, bec_chain_id,
            manifest_hash, issuer, issuer_signature
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """, (
        manifest['manifest_id'], manifest['model_id'], manifest['provider'],
        manifest['evaluation_date'], manifest['bis_score'], manifest['bis_grade'],
        manifest['csas_score'], manifest['csas_grade'], manifest['jrs_score'],
        manifest['tds_valid_until'], manifest['tds_status'],
        manifest['gate_status'], manifest['gate_context'],
        manifest['acps_score'], manifest['acps_grade'],
        json.dumps(manifest['regulatory_compliance']) if manifest['regulatory_compliance'] else None,
        manifest['bec_integrity_score'], manifest['bec_chain_id'],
        manifest['manifest_hash'], manifest['issuer'], manifest['issuer_signature']
    ))

    # Insert into manifest_registry
    cur.execute("""
        INSERT INTO manifest_registry (
            manifest_id, model_id, provider, gate_context,
            gate_status, status, expires_at
        ) VALUES (%s, %s, %s, %s, %s, 'active', %s)
    """, (
        manifest['manifest_id'], manifest['model_id'], manifest['provider'],
        manifest['gate_context'], manifest['gate_status'],
        manifest['tds_valid_until']
    ))

    conn.close()
    print(f"  Stored in database. manifest_id: {manifest['manifest_id']}")


def verify_manifest(manifest_id_or_data):
    """Verify a Constraint Manifest using the three-step protocol."""
    if isinstance(manifest_id_or_data, dict):
        manifest = manifest_id_or_data
    else:
        # Load from database
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM manifests WHERE manifest_id = %s", (manifest_id_or_data,))
        manifest = cur.fetchone()
        conn.close()
        if not manifest:
            print(f"  Manifest {manifest_id_or_data} not found.")
            return {"result": "REJECTED", "reason": "not_found"}
        manifest = dict(manifest)

    result = {
        "manifest_id": manifest.get('manifest_id'),
        "hash_valid": False,
        "signature_valid": False,
        "expiry_valid": False,
        "revoked": False,
        "result": "REJECTED",
        "reasons": []
    }

    # Step 1: Hash verification
    fields = {
        "manifest_id": str(manifest['manifest_id']),
        "model_id": manifest['model_id'],
        "provider": manifest['provider'],
        "evaluation_date": str(manifest['evaluation_date']),
        "bis_score": manifest['bis_score'],
        "bis_grade": manifest['bis_grade'],
        "csas_score": manifest['csas_score'],
        "csas_grade": manifest['csas_grade'],
        "jrs_score": manifest['jrs_score'],
        "tds_valid_until": str(manifest['tds_valid_until']),
        "tds_status": manifest['tds_status'],
        "gate_status": manifest['gate_status'],
        "gate_context": manifest['gate_context'],
        "acps_score": manifest['acps_score'],
        "acps_grade": manifest['acps_grade'],
        "regulatory_compliance": manifest['regulatory_compliance'] if isinstance(manifest['regulatory_compliance'], dict) else (json.loads(manifest['regulatory_compliance']) if manifest['regulatory_compliance'] else None),
        "bec_integrity_score": manifest['bec_integrity_score'],
        "bec_chain_id": manifest['bec_chain_id'],
    }
    expected_hash = compute_manifest_hash(fields)
    if expected_hash == manifest['manifest_hash']:
        result['hash_valid'] = True
    else:
        result['reasons'].append("hash_mismatch")

    # Step 2: Signature verification
    expected_sig = compute_signature(manifest['manifest_hash'])
    if expected_sig == manifest['issuer_signature']:
        result['signature_valid'] = True
    else:
        result['reasons'].append("signature_invalid")

    # Step 3: Expiry verification
    valid_until = manifest['tds_valid_until']
    if isinstance(valid_until, str):
        valid_until = date.fromisoformat(valid_until)
    elif isinstance(valid_until, datetime):
        valid_until = valid_until.date()

    if date.today() <= valid_until:
        result['expiry_valid'] = True
    else:
        result['reasons'].append("manifest_expired")

    # Check revocation
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT * FROM manifest_revocations WHERE manifest_id = %s",
            (str(manifest['manifest_id']),)
        )
        revocation = cur.fetchone()
        conn.close()
        if revocation:
            result['revoked'] = True
            result['reasons'].append("manifest_revoked")
    except Exception:
        pass

    # Final determination
    if result['hash_valid'] and result['signature_valid'] and result['expiry_valid'] and not result['revoked']:
        result['result'] = "VERIFIED"

    # Store verification record
    try:
        import psycopg2
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO manifest_verifications (
                manifest_id, hash_valid, signature_valid, expiry_valid,
                revocation_checked, overall_result
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            str(manifest['manifest_id']),
            result['hash_valid'], result['signature_valid'],
            result['expiry_valid'], True, result['result']
        ))
        conn.close()
    except Exception:
        pass

    print(f"\nVerification result for {manifest.get('manifest_id')}:")
    print(f"  Hash valid: {result['hash_valid']}")
    print(f"  Signature valid: {result['signature_valid']}")
    print(f"  Expiry valid: {result['expiry_valid']}")
    print(f"  Revoked: {result['revoked']}")
    print(f"  Result: {result['result']}")
    if result['reasons']:
        print(f"  Reasons: {', '.join(result['reasons'])}")

    return result


def revoke_manifest(manifest_id, reason="administrative"):
    """Revoke a Constraint Manifest."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    valid_reasons = ['score_change', 'provider_change', 'administrative']
    if reason not in valid_reasons:
        print(f"  Invalid reason. Must be one of: {valid_reasons}")
        return None

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Verify manifest exists
    cur.execute("SELECT * FROM manifests WHERE manifest_id = %s", (manifest_id,))
    manifest = cur.fetchone()
    if not manifest:
        print(f"  Manifest {manifest_id} not found.")
        conn.close()
        return None

    # Check if already revoked
    cur.execute("SELECT * FROM manifest_revocations WHERE manifest_id = %s", (manifest_id,))
    existing = cur.fetchone()
    if existing:
        print(f"  Manifest {manifest_id} is already revoked.")
        conn.close()
        return None

    revocation_id = str(uuid.uuid4())

    # Insert revocation record
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO manifest_revocations (
            revocation_id, manifest_id, revocation_reason, revoked_by
        ) VALUES (%s, %s, %s, %s)
    """, (revocation_id, manifest_id, reason, ISSUER))

    # Update manifest status
    cur.execute("""
        UPDATE manifests SET status = 'revoked' WHERE manifest_id = %s
    """, (manifest_id,))

    # Update registry
    cur.execute("""
        UPDATE manifest_registry SET status = 'revoked' WHERE manifest_id = %s
    """, (manifest_id,))

    conn.close()

    result = {
        "revocation_id": revocation_id,
        "manifest_id": manifest_id,
        "reason": reason,
        "revoked_by": ISSUER,
        "revoked_at": datetime.now(timezone.utc).isoformat()
    }

    print(f"\nManifest revoked:")
    print(f"  Revocation ID: {revocation_id}")
    print(f"  Manifest ID: {manifest_id}")
    print(f"  Reason: {reason}")

    return result


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Constraint Manifest Generator (Framework F30)")
    parser.add_argument("--model", type=str, help="Model identifier (e.g., grok-3-mini)")
    parser.add_argument("--context", type=str, help="Deployment context")
    parser.add_argument("--provider", type=str, help="Override provider")
    parser.add_argument("--verify", type=str, help="Verify a manifest by ID")
    parser.add_argument("--revoke", type=str, help="Revoke a manifest by ID")
    parser.add_argument("--reason", type=str, default="administrative",
                        help="Revocation reason (score_change, provider_change, administrative)")
    parser.add_argument("--dry-run", action="store_true", help="Generate without storing")
    parser.add_argument("--no-db", action="store_true", help="Run without database")
    args = parser.parse_args()

    if args.verify:
        verify_manifest(args.verify)
    elif args.revoke:
        revoke_manifest(args.revoke, args.reason)
    elif args.model:
        if not args.context:
            print("Error: --context is required for manifest generation.")
            sys.exit(1)
        generate_manifest(
            model_id=args.model,
            context=args.context,
            provider=args.provider,
            dry_run=args.dry_run,
            no_db=args.no_db
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
