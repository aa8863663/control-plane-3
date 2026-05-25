-- Permanence Architecture Schema
-- Framework F37: Payload binding and boundary persistence
-- Created: May 2026

-- Add permanence fields to BEC records
ALTER TABLE bec_records ADD COLUMN IF NOT EXISTS payload_binding_hash TEXT;
ALTER TABLE bec_records ADD COLUMN IF NOT EXISTS permanence_verified BOOLEAN DEFAULT FALSE;

-- Permanence verification log
CREATE TABLE IF NOT EXISTS permanence_verifications (
    id SERIAL PRIMARY KEY,
    evaluation_id TEXT NOT NULL,
    chain_id TEXT NOT NULL,
    record_id INTEGER,
    payload_binding_hash TEXT NOT NULL,
    constraint_id TEXT,
    crypto_standard TEXT NOT NULL DEFAULT 'SHA3-256',
    permanence_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_permanence_eval ON permanence_verifications(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_permanence_chain ON permanence_verifications(chain_id);
