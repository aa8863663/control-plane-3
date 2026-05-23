-- MAFS (Model Architectural Failure Surface) Schema
-- Phase 1: Architectural Failure Surface mapping
-- Created: May 2026

-- MAFS evaluations
CREATE TABLE IF NOT EXISTS mafs_evaluations (
    id SERIAL PRIMARY KEY,
    model_id TEXT NOT NULL,
    evaluation_type TEXT NOT NULL,
    constraint_type TEXT,
    safety_tier INTEGER,
    temperature REAL,
    result TEXT NOT NULL,
    is_hard_stop BOOLEAN DEFAULT FALSE,
    ve_score INTEGER,
    probe_id TEXT,
    evaluated_at TIMESTAMP DEFAULT NOW(),
    notes TEXT
);

-- AAFI scores per model
CREATE TABLE IF NOT EXISTS aafi_scores (
    id SERIAL PRIMARY KEY,
    model_id TEXT NOT NULL,
    aafi_score REAL NOT NULL,
    aafi_grade TEXT NOT NULL,
    hard_stops_total INTEGER,
    probes_total INTEGER,
    safety_tier_1_failures INTEGER DEFAULT 0,
    safety_tier_2_failures INTEGER DEFAULT 0,
    safety_tier_3_failures INTEGER DEFAULT 0,
    computed_at TIMESTAMP DEFAULT NOW()
);

-- Correction ceilings per model
CREATE TABLE IF NOT EXISTS correction_ceilings (
    id SERIAL PRIMARY KEY,
    model_id TEXT NOT NULL,
    ceiling_score REAL NOT NULL,
    ceiling_grade TEXT NOT NULL,
    max_bis_achievable REAL,
    correction_exhausted BOOLEAN DEFAULT FALSE,
    constraint_types_at_ceiling JSONB,
    computed_at TIMESTAMP DEFAULT NOW()
);

-- Cascade failure records
CREATE TABLE IF NOT EXISTS cascade_records (
    id SERIAL PRIMARY KEY,
    upstream_model_id TEXT NOT NULL,
    downstream_model_id TEXT,
    constraint_type TEXT,
    upstream_hard_stop BOOLEAN DEFAULT FALSE,
    downstream_effect TEXT,
    cascade_score REAL,
    boundary_id TEXT,
    recorded_at TIMESTAMP DEFAULT NOW()
);

-- Safety taxonomy for probes
CREATE TABLE IF NOT EXISTS safety_taxonomy (
    id SERIAL PRIMARY KEY,
    probe_id TEXT UNIQUE NOT NULL,
    safety_tier INTEGER NOT NULL,
    tier_label TEXT NOT NULL,
    constraint_type TEXT,
    description TEXT,
    classified_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_mafs_eval_model ON mafs_evaluations(model_id);
CREATE INDEX IF NOT EXISTS idx_mafs_eval_hard_stop ON mafs_evaluations(is_hard_stop);
CREATE INDEX IF NOT EXISTS idx_mafs_eval_safety ON mafs_evaluations(safety_tier);
CREATE INDEX IF NOT EXISTS idx_aafi_model ON aafi_scores(model_id);
CREATE INDEX IF NOT EXISTS idx_aafi_grade ON aafi_scores(aafi_grade);
CREATE INDEX IF NOT EXISTS idx_ceiling_model ON correction_ceilings(model_id);
CREATE INDEX IF NOT EXISTS idx_cascade_upstream ON cascade_records(upstream_model_id);
CREATE INDEX IF NOT EXISTS idx_cascade_downstream ON cascade_records(downstream_model_id);
CREATE INDEX IF NOT EXISTS idx_taxonomy_tier ON safety_taxonomy(safety_tier);
CREATE INDEX IF NOT EXISTS idx_taxonomy_probe ON safety_taxonomy(probe_id);
