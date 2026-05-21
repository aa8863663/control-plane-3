-- ============================================================
-- JRS (Jurisdiction Resolution Score) Schema Migration
-- Control Plane 3 — Governance layer above CSAS
-- Measures whether constraint jurisdiction was explicitly
-- established before coordination began.
-- ============================================================

-- Constraint Jurisdiction Registry (CJR)
-- Records which system's constraint set governs each boundary
CREATE TABLE IF NOT EXISTS jrs_registry (
    id SERIAL PRIMARY KEY,
    boundary_name TEXT NOT NULL,
    upstream_model TEXT NOT NULL,
    downstream_model TEXT NOT NULL,
    governing_system TEXT NOT NULL,
    constraint_set TEXT NOT NULL,
    assignment_type TEXT NOT NULL,
    assigned_by TEXT,
    assigned_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP,
    notes TEXT
);

-- JRS evaluations linked to registry entries and CSAS evaluations
CREATE TABLE IF NOT EXISTS jrs_evaluations (
    id SERIAL PRIMARY KEY,
    registry_id INTEGER REFERENCES jrs_registry(id) ON DELETE CASCADE,
    csas_evaluation_id INTEGER REFERENCES csas_evaluations(id) ON DELETE SET NULL,
    jrs_score REAL NOT NULL,
    assignment_clarity REAL,
    re_resolution_status TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    notes TEXT
);

-- Combined scores: JRS + CSAS governance composite
CREATE TABLE IF NOT EXISTS jrs_scores (
    id SERIAL PRIMARY KEY,
    evaluation_id INTEGER NOT NULL REFERENCES jrs_evaluations(id) ON DELETE CASCADE,
    jrs REAL NOT NULL,
    csas REAL,
    combined_governance_score REAL,
    grade TEXT NOT NULL,
    jurisdiction_valid BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Re-Resolution Protocol log
CREATE TABLE IF NOT EXISTS jrs_reresolution_log (
    id SERIAL PRIMARY KEY,
    registry_id INTEGER NOT NULL REFERENCES jrs_registry(id) ON DELETE CASCADE,
    trigger_type TEXT NOT NULL,
    trigger_detail TEXT,
    previous_jrs REAL,
    new_jrs REAL,
    resolved_at TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved_by TEXT
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_jrs_registry_models ON jrs_registry(upstream_model, downstream_model);
CREATE INDEX IF NOT EXISTS idx_jrs_registry_governing ON jrs_registry(governing_system);
CREATE INDEX IF NOT EXISTS idx_jrs_evaluations_registry ON jrs_evaluations(registry_id);
CREATE INDEX IF NOT EXISTS idx_jrs_evaluations_csas ON jrs_evaluations(csas_evaluation_id);
CREATE INDEX IF NOT EXISTS idx_jrs_scores_evaluation ON jrs_scores(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_jrs_reresolution_registry ON jrs_reresolution_log(registry_id);
