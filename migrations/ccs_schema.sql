-- ============================================================
-- CCS (Constraint Conflict Score) Schema Migration
-- Control Plane 3 — Measures what happens when two simultaneously
-- active constraints are logically incompatible.
-- ============================================================

-- CCS evaluations: top-level evaluation runs
CREATE TABLE IF NOT EXISTS ccs_evaluations (
    id SERIAL PRIMARY KEY,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    temperature REAL NOT NULL DEFAULT 0.0,
    probe_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    notes TEXT
);

-- CCS conflicts: per-probe conflict resolution results
CREATE TABLE IF NOT EXISTS ccs_conflicts (
    id SERIAL PRIMARY KEY,
    evaluation_id INTEGER REFERENCES ccs_evaluations(id),
    probe_id TEXT NOT NULL,
    constraint_a TEXT NOT NULL,
    constraint_b TEXT NOT NULL,
    conflict_severity TEXT NOT NULL,
    winner TEXT,
    consistency_score REAL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- CCS patterns: detected conflict resolution patterns
CREATE TABLE IF NOT EXISTS ccs_patterns (
    id SERIAL PRIMARY KEY,
    evaluation_id INTEGER REFERENCES ccs_evaluations(id),
    pattern_type TEXT NOT NULL,
    dominant_constraint TEXT,
    consistency REAL NOT NULL,
    conflict_type TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- CCS scores: overall evaluation scores
CREATE TABLE IF NOT EXISTS ccs_scores (
    id SERIAL PRIMARY KEY,
    evaluation_id INTEGER REFERENCES ccs_evaluations(id),
    ccs REAL NOT NULL,
    grade TEXT NOT NULL,
    dominant_rate REAL,
    stochastic_rate REAL,
    failure_rate REAL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_ccs_evaluations_model ON ccs_evaluations(model);
CREATE INDEX IF NOT EXISTS idx_ccs_evaluations_provider ON ccs_evaluations(provider);
CREATE INDEX IF NOT EXISTS idx_ccs_conflicts_evaluation ON ccs_conflicts(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_ccs_conflicts_probe ON ccs_conflicts(probe_id);
CREATE INDEX IF NOT EXISTS idx_ccs_patterns_evaluation ON ccs_patterns(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_ccs_patterns_type ON ccs_patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_ccs_scores_evaluation ON ccs_scores(evaluation_id);
