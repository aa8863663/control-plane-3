-- ============================================================
-- CSAS (Cross-System Admissibility Score) Schema Migration
-- Control Plane 3 — Multi-model coordination evaluation
-- ============================================================

-- Evaluation sessions
CREATE TABLE IF NOT EXISTS csas_evaluations (
    id SERIAL PRIMARY KEY,
    system_name TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    notes TEXT
);

-- Boundary definitions (upstream -> downstream model pairs)
CREATE TABLE IF NOT EXISTS csas_boundaries (
    id SERIAL PRIMARY KEY,
    evaluation_id INTEGER NOT NULL REFERENCES csas_evaluations(id) ON DELETE CASCADE,
    upstream_model TEXT NOT NULL,
    downstream_model TEXT NOT NULL,
    constraint_set TEXT NOT NULL
);

-- Per-probe results for each boundary
CREATE TABLE IF NOT EXISTS csas_results (
    id SERIAL PRIMARY KEY,
    boundary_id INTEGER NOT NULL REFERENCES csas_boundaries(id) ON DELETE CASCADE,
    probe_id TEXT NOT NULL,
    upstream_outcome TEXT NOT NULL,
    downstream_outcome TEXT NOT NULL,
    upstream_ve INTEGER NOT NULL DEFAULT 0,
    downstream_ve INTEGER NOT NULL DEFAULT 0,
    cir_pass BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Computed scores per boundary and evaluation
CREATE TABLE IF NOT EXISTS csas_scores (
    id SERIAL PRIMARY KEY,
    evaluation_id INTEGER NOT NULL REFERENCES csas_evaluations(id) ON DELETE CASCADE,
    boundary_id INTEGER NOT NULL REFERENCES csas_boundaries(id) ON DELETE CASCADE,
    bpr REAL NOT NULL,
    cve REAL NOT NULL,
    cir REAL NOT NULL,
    caf REAL NOT NULL,
    csas REAL NOT NULL,
    grade TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_csas_boundaries_evaluation ON csas_boundaries(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_csas_results_boundary ON csas_results(boundary_id);
CREATE INDEX IF NOT EXISTS idx_csas_scores_evaluation ON csas_scores(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_csas_scores_boundary ON csas_scores(boundary_id);
CREATE INDEX IF NOT EXISTS idx_csas_boundaries_models ON csas_boundaries(upstream_model, downstream_model);
