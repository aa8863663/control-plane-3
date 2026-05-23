-- Quantum-Safe Layer Schema
-- Framework F35: Cryptographic validity and post-quantum migration
-- Created: May 2026

-- Cryptographic validity log
CREATE TABLE IF NOT EXISTS crypto_validity_log (
    id SERIAL PRIMARY KEY,
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    crypto_standard TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    validity_start TIMESTAMP NOT NULL DEFAULT NOW(),
    validity_end TIMESTAMP NOT NULL,
    is_quantum_safe BOOLEAN DEFAULT TRUE,
    checked_at TIMESTAMP DEFAULT NOW(),
    notes TEXT
);

-- Migration registry for SHA-256 to BLAKE3
CREATE TABLE IF NOT EXISTS quantum_migration_registry (
    id SERIAL PRIMARY KEY,
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    original_algorithm TEXT NOT NULL DEFAULT 'SHA-256',
    original_hash TEXT NOT NULL,
    new_algorithm TEXT NOT NULL DEFAULT 'BLAKE3',
    new_hash TEXT,
    migrated_at TIMESTAMP,
    migration_status TEXT DEFAULT 'pending',
    verified BOOLEAN DEFAULT FALSE
);

-- Crypto standard records per evidence item
CREATE TABLE IF NOT EXISTS crypto_standard_records (
    id SERIAL PRIMARY KEY,
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    crypto_standard TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    key_length INTEGER,
    implementation_date TIMESTAMP DEFAULT NOW(),
    validity_window_years INTEGER DEFAULT 10,
    harvest_risk_level INTEGER DEFAULT 2,
    notes TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_crypto_validity_record ON crypto_validity_log(record_type, record_id);
CREATE INDEX IF NOT EXISTS idx_crypto_validity_standard ON crypto_validity_log(crypto_standard);
CREATE INDEX IF NOT EXISTS idx_crypto_validity_quantum ON crypto_validity_log(is_quantum_safe);
CREATE INDEX IF NOT EXISTS idx_quantum_migration_status ON quantum_migration_registry(migration_status);
CREATE INDEX IF NOT EXISTS idx_quantum_migration_type ON quantum_migration_registry(record_type);
CREATE INDEX IF NOT EXISTS idx_crypto_standard_record ON crypto_standard_records(record_type, record_id);
CREATE INDEX IF NOT EXISTS idx_crypto_standard_algorithm ON crypto_standard_records(algorithm);
CREATE INDEX IF NOT EXISTS idx_crypto_standard_risk ON crypto_standard_records(harvest_risk_level);
