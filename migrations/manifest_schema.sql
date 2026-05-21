-- Constraint Manifest Schema
-- Framework F30: Portable verified attestation for model deployments
-- Created: May 2026

-- Manifests table (core manifest documents)
CREATE TABLE IF NOT EXISTS manifests (
    id SERIAL PRIMARY KEY,
    manifest_id UUID NOT NULL UNIQUE,
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    evaluation_date DATE NOT NULL,
    bis_score REAL NOT NULL,
    bis_grade TEXT NOT NULL,
    csas_score REAL,
    csas_grade TEXT,
    jrs_score REAL,
    tds_valid_until DATE NOT NULL,
    tds_status TEXT NOT NULL,
    gate_status TEXT NOT NULL,
    gate_context TEXT NOT NULL,
    acps_score REAL,
    acps_grade TEXT,
    regulatory_compliance JSONB,
    bec_integrity_score REAL NOT NULL DEFAULT 1.0,
    bec_chain_id TEXT,
    manifest_hash TEXT NOT NULL,
    issuer TEXT NOT NULL DEFAULT 'MTCP Research Programme',
    issuer_signature TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Manifest verifications table (verification audit log)
CREATE TABLE IF NOT EXISTS manifest_verifications (
    id SERIAL PRIMARY KEY,
    manifest_id UUID NOT NULL,
    verified_at TIMESTAMP DEFAULT NOW(),
    hash_valid BOOLEAN NOT NULL,
    signature_valid BOOLEAN NOT NULL,
    expiry_valid BOOLEAN NOT NULL,
    revocation_checked BOOLEAN NOT NULL DEFAULT TRUE,
    overall_result TEXT NOT NULL,
    verified_by TEXT,
    notes TEXT
);

-- Manifest revocations table (revocation registry)
CREATE TABLE IF NOT EXISTS manifest_revocations (
    id SERIAL PRIMARY KEY,
    revocation_id UUID NOT NULL UNIQUE,
    manifest_id UUID NOT NULL,
    revoked_at TIMESTAMP DEFAULT NOW(),
    revocation_reason TEXT NOT NULL,
    revoked_by TEXT NOT NULL DEFAULT 'MTCP Research Programme',
    notes TEXT
);

-- Manifest registry table (current state tracking)
CREATE TABLE IF NOT EXISTS manifest_registry (
    id SERIAL PRIMARY KEY,
    manifest_id UUID NOT NULL,
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    gate_context TEXT NOT NULL,
    gate_status TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    issued_at TIMESTAMP DEFAULT NOW(),
    expires_at DATE NOT NULL,
    last_verified TIMESTAMP,
    verification_count INTEGER DEFAULT 0
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_manifests_model ON manifests(model_id);
CREATE INDEX IF NOT EXISTS idx_manifests_provider ON manifests(provider);
CREATE INDEX IF NOT EXISTS idx_manifests_status ON manifests(status);
CREATE INDEX IF NOT EXISTS idx_manifests_manifest_id ON manifests(manifest_id);
CREATE INDEX IF NOT EXISTS idx_manifest_verifications_mid ON manifest_verifications(manifest_id);
CREATE INDEX IF NOT EXISTS idx_manifest_revocations_mid ON manifest_revocations(manifest_id);
CREATE INDEX IF NOT EXISTS idx_manifest_registry_model ON manifest_registry(model_id, provider);
CREATE INDEX IF NOT EXISTS idx_manifest_registry_status ON manifest_registry(status);
