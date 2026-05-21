-- ============================================================
-- RES (Remediation Effectiveness Score) Schema Migration
-- Control Plane 3 — Measures whether specific interventions
-- fix constraint persistence failures. Compares BIS before
-- and after an intervention.
-- ============================================================

-- RES interventions: what was tried
CREATE TABLE IF NOT EXISTS res_interventions (
    id SERIAL PRIMARY KEY,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    intervention_type TEXT NOT NULL,
    description TEXT NOT NULL,
    baseline_bis REAL NOT NULL,
    baseline_grade TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- RES results: post-intervention evaluation
CREATE TABLE IF NOT EXISTS res_results (
    id SERIAL PRIMARY KEY,
    intervention_id INTEGER REFERENCES res_interventions(id),
    post_bis REAL NOT NULL,
    post_grade TEXT NOT NULL,
    res_score REAL NOT NULL,
    absolute_improvement REAL NOT NULL,
    temperature REAL,
    probe_count INTEGER,
    dataset TEXT DEFAULT 'probes_200',
    evaluated_at TIMESTAMP DEFAULT NOW()
);

-- RES ceilings: max achievable BIS per model
CREATE TABLE IF NOT EXISTS res_ceilings (
    id SERIAL PRIMARY KEY,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    ceiling_bis REAL NOT NULL,
    ceiling_grade TEXT NOT NULL,
    best_intervention TEXT,
    failure_pattern TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- RES recommendations: what to try next
CREATE TABLE IF NOT EXISTS res_recommendations (
    id SERIAL PRIMARY KEY,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    current_grade TEXT NOT NULL,
    target_grade TEXT NOT NULL,
    recommended_intervention TEXT NOT NULL,
    expected_res REAL,
    confidence TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_res_interventions_model ON res_interventions(model);
CREATE INDEX IF NOT EXISTS idx_res_interventions_provider ON res_interventions(provider);
CREATE INDEX IF NOT EXISTS idx_res_interventions_type ON res_interventions(intervention_type);
CREATE INDEX IF NOT EXISTS idx_res_interventions_model_provider ON res_interventions(model, provider);
CREATE INDEX IF NOT EXISTS idx_res_results_intervention ON res_results(intervention_id);
CREATE INDEX IF NOT EXISTS idx_res_ceilings_model ON res_ceilings(model);
CREATE INDEX IF NOT EXISTS idx_res_ceilings_provider ON res_ceilings(provider);
CREATE INDEX IF NOT EXISTS idx_res_ceilings_model_provider ON res_ceilings(model, provider);
CREATE INDEX IF NOT EXISTS idx_res_recommendations_model ON res_recommendations(model);
CREATE INDEX IF NOT EXISTS idx_res_recommendations_provider ON res_recommendations(provider);
CREATE INDEX IF NOT EXISTS idx_res_recommendations_model_provider ON res_recommendations(model, provider);
