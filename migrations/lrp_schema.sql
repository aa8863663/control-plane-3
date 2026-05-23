-- LRP (Legitimacy Resolution Protocol) Schema
-- Framework F32: Authority establishment and cross-regime comparability
-- Created: May 2026

-- Primary evaluations table
CREATE TABLE IF NOT EXISTS lrp_evaluations (
    id SERIAL PRIMARY KEY,
    evaluation_id TEXT UNIQUE NOT NULL,
    constraint_id TEXT NOT NULL,
    authority_claim_id TEXT NOT NULL,
    legitimacy_score REAL NOT NULL,
    condition_1_met BOOLEAN NOT NULL,
    condition_2_met BOOLEAN NOT NULL,
    condition_3_met BOOLEAN NOT NULL,
    evaluated_at TIMESTAMP DEFAULT NOW(),
    evaluated_by TEXT DEFAULT 'mtcp_system',
    notes TEXT
);

-- Authority claims registry
CREATE TABLE IF NOT EXISTS lrp_authority_claims (
    id SERIAL PRIMARY KEY,
    claim_id TEXT UNIQUE NOT NULL,
    authority_source TEXT NOT NULL,
    authority_type TEXT NOT NULL,
    constraint_id TEXT NOT NULL,
    scope_boundary JSONB NOT NULL,
    resolvable BOOLEAN DEFAULT FALSE,
    registered_at TIMESTAMP DEFAULT NOW(),
    registered_by TEXT DEFAULT 'mtcp_system',
    verification_method TEXT,
    status TEXT DEFAULT 'active'
);

-- Scores history
CREATE TABLE IF NOT EXISTS lrp_scores (
    id SERIAL PRIMARY KEY,
    model_id TEXT NOT NULL,
    constraint_id TEXT NOT NULL,
    legitimacy_score REAL NOT NULL,
    computed_at TIMESTAMP DEFAULT NOW(),
    authority_claim_id TEXT,
    context TEXT
);

-- Cross-regime comparability log
CREATE TABLE IF NOT EXISTS lrp_comparability_log (
    id SERIAL PRIMARY KEY,
    claim_a_id TEXT NOT NULL,
    claim_b_id TEXT NOT NULL,
    comparable BOOLEAN NOT NULL,
    reason TEXT,
    compared_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_lrp_evaluations_constraint ON lrp_evaluations(constraint_id);
CREATE INDEX IF NOT EXISTS idx_lrp_evaluations_claim ON lrp_evaluations(authority_claim_id);
CREATE INDEX IF NOT EXISTS idx_lrp_claims_constraint ON lrp_authority_claims(constraint_id);
CREATE INDEX IF NOT EXISTS idx_lrp_claims_source ON lrp_authority_claims(authority_source);
CREATE INDEX IF NOT EXISTS idx_lrp_scores_model ON lrp_scores(model_id);
CREATE INDEX IF NOT EXISTS idx_lrp_scores_constraint ON lrp_scores(constraint_id);
CREATE INDEX IF NOT EXISTS idx_lrp_comparability_claims ON lrp_comparability_log(claim_a_id, claim_b_id);
