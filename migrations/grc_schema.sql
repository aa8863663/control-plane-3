-- GRC (Governance Reference Conditions) Schema
-- Framework F33: Formal comparability conditions for coordinated systems
-- Created: May 2026

-- Primary conditions table
CREATE TABLE IF NOT EXISTS grc_conditions (
    id SERIAL PRIMARY KEY,
    evaluation_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    constraint_id TEXT,
    lrp_score REAL,
    temperature_config JSONB,
    infrastructure_config JSONB,
    jrs_score REAL,
    bec_integrity REAL,
    recorded_at TIMESTAMP DEFAULT NOW(),
    notes TEXT
);

-- Compatibility determinations
CREATE TABLE IF NOT EXISTS grc_compatibility_log (
    id SERIAL PRIMARY KEY,
    model_a TEXT NOT NULL,
    model_b TEXT NOT NULL,
    compatible BOOLEAN NOT NULL,
    grc1_met BOOLEAN NOT NULL,
    grc2_met BOOLEAN NOT NULL,
    grc3_met BOOLEAN NOT NULL,
    grc4_met BOOLEAN NOT NULL,
    grc5_met BOOLEAN NOT NULL,
    reason TEXT,
    compared_at TIMESTAMP DEFAULT NOW()
);

-- CSAS degradation classifications
CREATE TABLE IF NOT EXISTS grc_classifications (
    id SERIAL PRIMARY KEY,
    csas_id TEXT NOT NULL,
    model_a TEXT NOT NULL,
    model_b TEXT NOT NULL,
    grc_compatible BOOLEAN NOT NULL,
    classification TEXT NOT NULL,
    csas_score REAL,
    classified_at TIMESTAMP DEFAULT NOW(),
    notes TEXT
);

-- Canonical registry of comparable pairs
CREATE TABLE IF NOT EXISTS grc_canonical_registry (
    id SERIAL PRIMARY KEY,
    model_a TEXT NOT NULL,
    model_b TEXT NOT NULL,
    constraint_id TEXT,
    compatibility_score REAL NOT NULL,
    confirmed_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    status TEXT DEFAULT 'active'
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_grc_conditions_eval ON grc_conditions(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_grc_conditions_model ON grc_conditions(model_id);
CREATE INDEX IF NOT EXISTS idx_grc_compat_models ON grc_compatibility_log(model_a, model_b);
CREATE INDEX IF NOT EXISTS idx_grc_class_csas ON grc_classifications(csas_id);
CREATE INDEX IF NOT EXISTS idx_grc_class_models ON grc_classifications(model_a, model_b);
CREATE INDEX IF NOT EXISTS idx_grc_canon_models ON grc_canonical_registry(model_a, model_b);
CREATE INDEX IF NOT EXISTS idx_grc_canon_status ON grc_canonical_registry(status);
