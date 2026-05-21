-- BEC (Blockchain Evidence Chain) Schema
-- Framework F28: Cryptographic integrity for MTCP evaluation records
-- Created: May 2026

-- Primary chain records table
CREATE TABLE IF NOT EXISTS bec_records (
    id SERIAL PRIMARY KEY,
    chain_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    previous_hash TEXT NOT NULL,
    model_id TEXT NOT NULL,
    evaluation_type TEXT NOT NULL,
    evaluation_data JSONB NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    evaluator_id TEXT DEFAULT 'mtcp_system',
    record_hash TEXT NOT NULL,
    UNIQUE(chain_id, sequence_number)
);

-- Chain metadata table
CREATE TABLE IF NOT EXISTS bec_chains (
    id SERIAL PRIMARY KEY,
    chain_id TEXT UNIQUE NOT NULL,
    genesis_hash TEXT NOT NULL,
    current_length INTEGER DEFAULT 0,
    last_verified TIMESTAMP,
    integrity_score REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Verification log table
CREATE TABLE IF NOT EXISTS bec_verifications (
    id SERIAL PRIMARY KEY,
    chain_id TEXT NOT NULL,
    verified_at TIMESTAMP DEFAULT NOW(),
    records_checked INTEGER,
    records_valid INTEGER,
    integrity_score REAL NOT NULL,
    first_invalid_sequence INTEGER,
    notes TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_bec_records_chain_seq ON bec_records(chain_id, sequence_number);
CREATE INDEX IF NOT EXISTS idx_bec_records_model ON bec_records(model_id);
CREATE INDEX IF NOT EXISTS idx_bec_records_type ON bec_records(evaluation_type);
CREATE INDEX IF NOT EXISTS idx_bec_verifications_chain ON bec_verifications(chain_id);
