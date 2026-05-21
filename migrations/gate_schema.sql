-- Admissibility Gate Schema
-- Framework F29: Binary enforcement for deployment decisions
-- Created: May 2026

-- Gate decisions table (hash-chained using BEC architecture)
CREATE TABLE IF NOT EXISTS gate_decisions (
    id SERIAL PRIMARY KEY,
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    deployment_context TEXT NOT NULL,
    bis_score REAL,
    bis_grade TEXT,
    csas_score REAL,
    csas_grade TEXT,
    jrs_score REAL,
    tds_status TEXT,
    tds_valid BOOLEAN,
    decision TEXT NOT NULL,
    deny_reasons JSONB,
    previous_gate_hash TEXT,
    gate_hash TEXT NOT NULL,
    decided_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);

-- Gate thresholds table (configurable per deployment context)
CREATE TABLE IF NOT EXISTS gate_thresholds (
    id SERIAL PRIMARY KEY,
    deployment_context TEXT UNIQUE NOT NULL,
    min_bis REAL NOT NULL,
    min_bis_grade TEXT NOT NULL,
    min_csas REAL,
    min_jrs REAL,
    max_tds_drift TEXT,
    requires_csas BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Gate expiry log
CREATE TABLE IF NOT EXISTS gate_expiry_log (
    id SERIAL PRIMARY KEY,
    decision_id INTEGER REFERENCES gate_decisions(id),
    expired_at TIMESTAMP DEFAULT NOW(),
    expiry_reason TEXT NOT NULL
);

-- Gate registry (current state per model/context)
CREATE TABLE IF NOT EXISTS gate_registry (
    id SERIAL PRIMARY KEY,
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    deployment_context TEXT NOT NULL,
    current_decision_id INTEGER REFERENCES gate_decisions(id),
    last_evaluated TIMESTAMP,
    next_evaluation TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_gate_decisions_model ON gate_decisions(model_id);
CREATE INDEX IF NOT EXISTS idx_gate_decisions_context ON gate_decisions(deployment_context);
CREATE INDEX IF NOT EXISTS idx_gate_decisions_decision ON gate_decisions(decision);
CREATE INDEX IF NOT EXISTS idx_gate_decisions_expires ON gate_decisions(expires_at);
CREATE INDEX IF NOT EXISTS idx_gate_registry_model ON gate_registry(model_id, deployment_context);
CREATE INDEX IF NOT EXISTS idx_gate_expiry_decision ON gate_expiry_log(decision_id);
